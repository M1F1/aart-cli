"""Pure planning and result evaluation for installed MCP smoke verification.

Process execution, filesystem reads and credential providers stay outside this module. Two stages
are evaluated (§170.2, D-378): the installation is usable, and its server completes the declared
call. Neither is presented as proof that the service behind the server was reached.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from functools import lru_cache
from typing import Iterable

from aart_cli.domain.harness import Scope
from aart_cli.domain.installation_owner import installation_key
from aart_cli.domain.receipts import InstallationReceipt, InstalledRecord
from aart_cli.protocol.json import JsonArray, JsonObject, JsonValue


class SmokeOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_CONFIGURED = "NOT CONFIGURED"
    NOT_RUN = "NOT RUN"
    UNSUPPORTED = "UNSUPPORTED"


class SmokeStage(str, Enum):
    INSTALLATION = "installation-configuration"
    PROTOCOL = "mcp-startup-and-protocol"


@dataclass(frozen=True, slots=True)
class SmokeStageResult:
    stage: SmokeStage
    outcome: SmokeOutcome
    reason: str


@dataclass(frozen=True, slots=True)
class SmokeDeclaration:
    tool: str
    arguments: JsonObject
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class McpNumber:
    """A number an MCP server wrote with a fraction, or beyond the protocol's integers, exactly.

    aart-cli's own documents carry no such number (protocol JSON forbids them), but a server's
    schemas and answers do: FastMCP writes a `float` parameter's bounds and default as `0.0` and
    `1.0` (§205). The smoke reads them into the trees it validates and nowhere else; protocol
    code never sees one. A whole number is never one of these: `2.0` is read as the integer 2.
    """

    value: Fraction

    def __post_init__(self) -> None:
        if not isinstance(self.value, Fraction):
            raise ValueError("an MCP number is an exact fraction")


@dataclass(frozen=True, slots=True)
class McpTool:
    name: str
    input_schema: JsonObject
    output_schema: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class McpCallResult:
    """The protocol evidence retained from one tool call, without its raw payload in reports."""

    content: JsonArray | None = None
    structured_content: JsonValue | None = None
    is_error: bool | None = None
    jsonrpc_error: str | None = None


@dataclass(frozen=True, slots=True)
class SmokeSelection:
    targets: tuple[InstalledRecord, ...]
    failure: str | None = None


def _names(record: InstalledRecord, selector: str) -> bool:
    """`ALIAS/KIND/NAME[@VERSION]`, as `consume inputs` reads it, or the installation key.

    A version, when given, must be the installed one (§170.1); the artifact is named whole.
    """

    coordinate = str(record.coordinate)
    return selector in {
        coordinate,
        coordinate.partition("@")[0],
        installation_key(record.coordinate, record.receipt.owner),
    }


def _no_target(selector: str, eligible: list[InstalledRecord]) -> str:
    artifact = selector.partition("@")[0]
    alike = sorted(
        {
            str(record.coordinate)
            for record in eligible
            if str(record.coordinate).partition("@")[0] == artifact
        }
    )
    hint = f"; did you mean {' or '.join(alike)}?" if alike else ""
    return f"selector {selector!r} names no installed MCP target{hint}"


def select_installed_mcps(
    records: Iterable[InstalledRecord],
    *,
    scope: Scope,
    root: str,
    harnesses: frozenset[str],
    selectors: tuple[str, ...],
    all_installed: bool,
) -> SmokeSelection:
    """Resolve only concrete MCP installation owners in one explicit local target scope."""

    if all_installed == bool(selectors):
        return SmokeSelection((), "choose exactly one of --all or installed MCP selectors")
    eligible: list[InstalledRecord] = []
    for record in records:
        receipt = record.receipt
        owner = receipt.owner
        if (
            record.coordinate.artifact.kind != "mcp"
            or not isinstance(receipt, InstallationReceipt)
            or owner is None
            or owner.scope is not scope
            or owner.root != root
            or owner.harness not in harnesses
        ):
            continue
        eligible.append(record)
    if all_installed:
        selected = eligible
    else:
        selected = []
        for selector in selectors:
            matches = [record for record in eligible if _names(record, selector)]
            if not matches:
                return SmokeSelection((), _no_target(selector, eligible))
            selected.extend(matches)
    unique = {
        installation_key(record.coordinate, record.receipt.owner): record for record in selected
    }
    ordered = tuple(unique[key] for key in sorted(unique))
    if not ordered:
        return SmokeSelection((), "the selected local scope contains no installed MCP targets")
    return SmokeSelection(ordered)


def declaration_from_intent(value: JsonValue | None) -> SmokeDeclaration | None:
    """Read the normalized parser-owned block stored in the canonical authoring extension."""

    if not isinstance(value, JsonObject):
        return None
    fields = dict(value.entries)
    tool = fields.get("tool")
    arguments = fields.get("arguments")
    timeout = fields.get("timeout_seconds")
    if (
        fields.keys() != {"tool", "arguments", "timeout_seconds", "read_only"}
        or not isinstance(tool, str)
        or not isinstance(arguments, JsonObject)
        or isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= 60
        or fields.get("read_only") is not True
    ):
        return None
    return SmokeDeclaration(tool, arguments, timeout)


def _python(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _python(item) for key, item in value.entries}
    if isinstance(value, JsonArray):
        return [_python(item) for item in value.items]
    return value


#: Refusing a keyword this validator does not implement is deliberate: an unimplemented keyword is
#: a constraint that would otherwise go unapplied, and validating less than a schema states is the
#: failure worth stopping for.
_SUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        # The bounds a generated schema puts on a number, a string, an array or an object (§203).
        # Each is applied below, so allowing it validates no less than the schema states.
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
        # How a generated schema says "optional" or "one of these shapes": each branch is
        # validated, and a keyword this does not implement in a branch is still refused.
        "anyOf",
        "oneOf",
        "allOf",
        # What FastMCP writes for Pydantic's constrained strings, dicts, tuples and nested or
        # recursive models (§205). Each is applied below; `$defs` only holds what `$ref` reaches.
        "pattern",
        "patternProperties",
        "propertyNames",
        "prefixItems",
        "$ref",
        "$defs",
        "definitions",
    }
)

#: Annotations constrain nothing. JSON Schema files these under basic meta-data: they describe a
#: value for whoever reads the schema, and no instance is ever invalid because of one. So the
#: reason the allowlist above is closed does not reach them, and ignoring them still applies every
#: constraint the schema states.
#:
#: Refusing them refused the servers rather than the schemas. A real MCP server puts `description`
#: on nearly every property and `default` on every optional one, so a declared call against it was
#: rejected before invocation over a word that could not have changed the verdict (B-174).
_ANNOTATION_SCHEMA_KEYS = frozenset(
    {
        "$comment",
        "$id",
        "$schema",
        "default",
        "deprecated",
        "description",
        "examples",
        "readOnly",
        "title",
        "writeOnly",
        # Annotations too: in JSON Schema 2020-12 a format and a content type are described, not
        # asserted, unless a vocabulary says otherwise, and no MCP schema declares one (§203).
        "format",
        "contentEncoding",
        "contentMediaType",
        # OpenAPI's hint for a Pydantic tagged union. JSON Schema does not know it, and the
        # `oneOf` beside it decides which branch a value is, so reading it would decide nothing.
        "discriminator",
    }
)


def _annotation(key: str) -> bool:
    """A keyword that constrains nothing: a basic annotation, or a vendor extension.

    `x-` is how a schema producer marks its own keywords (fastmcp writes `x-fastmcp-wrap-result` on
    every output schema). JSON Schema ignores a keyword it does not know, and an `x-` one is never
    a constraint, so it is passed over rather than refused like an unimplemented one (§203).
    """

    return key in _ANNOTATION_SCHEMA_KEYS or key.startswith("x-")


def _number(value: object) -> int | Fraction | None:
    """The value as a number, or None when it is not one; a boolean is never a number."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, McpNumber):
        return value.value
    return None


def _ecma_ends(pattern: str) -> str:
    """The pattern with each `$` outside a class made `\\Z`, as ECMA-262 reads it.

    Python's `$` also matches before a final newline, so `^[A-Z]+$` would take `"PROJ\\n"`, which
    JSON Schema's ECMA-262 pattern refuses. A `$` escaped or inside `[...]` is a literal and stays.
    """

    written: list[str] = []
    escaped = in_class = False
    for index, character in enumerate(pattern):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif in_class:
            in_class = character != "]" or pattern[index - 1] == "["
        elif character == "[":
            in_class = True
        elif character == "$":
            written.append("\\Z")
            continue
        written.append(character)
    return "".join(written)


@lru_cache(maxsize=256)
def _compiled(pattern: str) -> re.Pattern[str] | None:
    """A JSON Schema pattern as Python reads it, or None when Python cannot read it the same way.

    `re.ASCII` gives `\\d`, `\\w` and `\\b` their ECMA-262 meaning. ECMA-only syntax such as `\\p{L}`
    or `(?<name>...)` does not compile, so it is refused rather than read as something else.
    """

    try:
        return re.compile(_ecma_ends(pattern), re.ASCII)
    except re.error:
        return None


def _bound(value: JsonValue, pointer: str, fields: dict[str, JsonValue]) -> str | None:
    """The numeric, length and size bounds a schema states, applied to the value."""

    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"):
        if key in fields and _number(fields[key]) is None:
            return f"{key} at {pointer} is unsupported"
    for key in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"):
        limit = fields.get(key)
        if key in fields and (isinstance(limit, bool) or not isinstance(limit, int)):
            return f"{key} at {pointer} is unsupported"
    number = _number(value)
    if number is not None:
        checks = (
            ("minimum", lambda limit: number >= limit, "is below minimum"),
            ("maximum", lambda limit: number <= limit, "is above maximum"),
            ("exclusiveMinimum", lambda limit: number > limit, "is not above exclusiveMinimum"),
            ("exclusiveMaximum", lambda limit: number < limit, "is not below exclusiveMaximum"),
            ("multipleOf", lambda limit: limit > 0 and number % limit == 0, "is not a multipleOf"),
        )
        for key, holds, failure in checks:
            if key in fields and not holds(_number(fields[key])):
                return f"value at {pointer} {failure}"
    if isinstance(value, str):
        noun, measured = "Length", len(value)
    elif isinstance(value, JsonArray):
        noun, measured = "Items", len(value.items)
    elif isinstance(value, JsonObject):
        noun, measured = "Properties", len(value.entries)
    else:
        noun, measured = "", 0
    if noun:
        low, high = fields.get(f"min{noun}"), fields.get(f"max{noun}")
        if isinstance(low, int) and measured < low:
            return f"value at {pointer} is shorter than min{noun}"
        if isinstance(high, int) and measured > high:
            return f"value at {pointer} is longer than max{noun}"
    if fields.get("uniqueItems") is True and isinstance(value, JsonArray):
        seen: list[JsonValue] = []
        for item in value.items:
            if item in seen:
                return f"items at {pointer} are not unique"
            seen.append(item)
    elif "uniqueItems" in fields and not isinstance(fields["uniqueItems"], bool):
        return f"uniqueItems at {pointer} is unsupported"
    if "pattern" in fields:
        written = fields["pattern"]
        compiled = _compiled(written) if isinstance(written, str) else None
        if compiled is None:
            return f"unsupported JSON Schema pattern at {pointer}: {written!r}"
        if isinstance(value, str) and compiled.search(value) is None:
            return f"value at {pointer} does not match pattern"
    return None


@dataclass(frozen=True, slots=True)
class _Reading:
    """What validation carries down a schema: its root, for `$ref`, and the references followed
    since the value last moved, so a reference that leads back to itself is caught."""

    root: JsonObject
    followed: frozenset[str] = frozenset()

    def moved(self) -> "_Reading":
        return _Reading(self.root)


def _resolved(reference: str, root: JsonObject) -> JsonValue | None:
    """What a `#/...` JSON Pointer reaches inside the tool's own schema, or None."""

    node: JsonValue = root
    for raw in reference.removeprefix("#").split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, JsonObject) and part in node.keys():
            node = node.get(part)
        elif isinstance(node, JsonArray) and part.isdigit() and int(part) < len(node.items):
            node = node.items[int(part)]
        else:
            return None
    return node


def _reference(
    value: JsonValue, pointer: str, fields: dict[str, JsonValue], reading: _Reading
) -> str | None:
    """`$ref` into the tool's own schema, followed; one anywhere else is never fetched (§205)."""

    if "$ref" not in fields:
        return None
    reference = fields["$ref"]
    if not isinstance(reference, str) or not (reference == "#" or reference.startswith("#/")):
        return (
            f"unsupported JSON Schema $ref {reference!r} at {pointer}: only a reference into "
            "the tool's own schema is read"
        )
    if reference in reading.followed:
        return f"unsupported JSON Schema $ref {reference!r} at {pointer} leads back to itself"
    target = _resolved(reference, reading.root)
    if not isinstance(target, JsonObject):
        return f"$ref {reference!r} at {pointer} does not resolve to a schema"
    return _validate_schema(
        value, target, pointer, _Reading(reading.root, reading.followed | {reference})
    )


def _branches(
    value: JsonValue, pointer: str, fields: dict[str, JsonValue], reading: _Reading
) -> str | None:
    """`allOf`, `anyOf` and `oneOf`: every, at least one, or exactly one branch holds."""

    for key in ("allOf", "anyOf", "oneOf"):
        if key not in fields:
            continue
        branches = fields[key]
        if (
            not isinstance(branches, JsonArray)
            or not branches.items
            or any(not isinstance(item, JsonObject) for item in branches.items)
        ):
            return f"{key} at {pointer} is malformed"
        failures = [
            _validate_schema(value, branch, pointer, reading)
            for branch in branches.items
            if isinstance(branch, JsonObject)
        ]
        # A branch this cannot read is not a branch that failed: refusing keeps it from deciding.
        unsupported = next(
            (item for item in failures if item and item.startswith("unsupported JSON Schema")),
            None,
        )
        if unsupported is not None:
            return unsupported
        held = sum(item is None for item in failures)
        if key == "allOf" and held != len(failures):
            return next(item for item in failures if item is not None)
        if key == "anyOf" and not held:
            return f"value at {pointer} matches no anyOf branch"
        if key == "oneOf" and held != 1:
            return f"value at {pointer} matches {held} oneOf branches, not one"
    return None


def _members(
    members: dict[str, JsonValue], pointer: str, fields: dict[str, JsonValue], reading: _Reading
) -> str | None:
    """An object's members against `properties`, `patternProperties`, `additionalProperties` and
    `propertyNames`: a member that no property or pattern names is an additional one."""

    properties = fields.get("properties", JsonObject(()))
    if not isinstance(properties, JsonObject):
        return f"properties at {pointer} is malformed"
    property_schemas = dict(properties.entries)
    patterned = fields.get("patternProperties", JsonObject(()))
    if not isinstance(patterned, JsonObject) or any(
        not isinstance(schema, JsonObject) for _, schema in patterned.entries
    ):
        return f"patternProperties at {pointer} is malformed"
    patterns: list[tuple[re.Pattern[str], JsonObject]] = []
    for written, schema in patterned.entries:
        compiled = _compiled(written)
        if compiled is None:
            return f"unsupported JSON Schema patternProperties pattern at {pointer}: {written!r}"
        if isinstance(schema, JsonObject):
            patterns.append((compiled, schema))
    additional = fields.get("additionalProperties", True)
    if not isinstance(additional, (bool, JsonObject)):
        return f"additionalProperties at {pointer} is unsupported"
    names = fields.get("propertyNames")
    if names is not None and not isinstance(names, JsonObject):
        return f"propertyNames at {pointer} is malformed"
    for name, member in members.items():
        if isinstance(names, JsonObject):
            failure = _validate_schema(name, names, pointer, reading.moved())
            if failure is not None:
                return f"property name {name!r} at {pointer} is not allowed: {failure}"
        place = f"{pointer}.{name}"
        child = property_schemas.get(name)
        if child is not None and not isinstance(child, JsonObject):
            return f"schema for {place} is malformed"
        matched = [schema for compiled, schema in patterns if compiled.search(name)]
        if child is None and not matched:
            if additional is False:
                return f"field {name!r} is not allowed at {pointer}"
            if isinstance(additional, JsonObject):
                matched = [additional]
        for schema in (*((child,) if isinstance(child, JsonObject) else ()), *matched):
            failure = _validate_schema(member, schema, place, reading.moved())
            if failure is not None:
                return failure
    return None


def _items(
    items: tuple[JsonValue, ...], pointer: str, fields: dict[str, JsonValue], reading: _Reading
) -> str | None:
    """`prefixItems` for the leading positions and `items` for every one after them (2020-12)."""

    prefix = fields.get("prefixItems", JsonArray(()))
    if not isinstance(prefix, JsonArray) or any(
        not isinstance(schema, JsonObject) for schema in prefix.items
    ):
        return f"prefixItems at {pointer} is malformed"
    rest = fields.get("items")
    if rest is not None and not isinstance(rest, JsonObject):
        return f"items at {pointer} is malformed"
    for index, item in enumerate(items):
        schema = prefix.items[index] if index < len(prefix.items) else rest
        if not isinstance(schema, JsonObject):
            continue
        failure = _validate_schema(item, schema, f"{pointer}[{index}]", reading.moved())
        if failure is not None:
            return failure
    return None


def _validate_schema(
    value: JsonValue, schema: JsonObject, pointer: str = "$", reading: _Reading | None = None
) -> str | None:
    reading = _Reading(schema) if reading is None else reading
    fields = dict(schema.entries)
    unsupported = sorted(
        key for key in fields.keys() - _SUPPORTED_SCHEMA_KEYS if not _annotation(key)
    )
    if unsupported:
        return f"unsupported JSON Schema keyword {unsupported[0]!r} at {pointer}"
    referred = _reference(value, pointer, fields, reading)
    if referred is not None:
        return referred
    branched = _branches(value, pointer, fields, reading)
    if branched is not None:
        return branched
    bounded = _bound(value, pointer, fields)
    if bounded is not None:
        return bounded
    if "const" in fields and value != fields["const"]:
        return f"value at {pointer} does not equal const"
    if "enum" in fields:
        choices = fields["enum"]
        if not isinstance(choices, JsonArray):
            return f"enum at {pointer} is malformed"
        if value not in choices.items:
            return f"value at {pointer} is outside enum"
    expected = fields.get("type")
    number = _number(value)
    matches = {
        "object": isinstance(value, JsonObject),
        "array": isinstance(value, JsonArray),
        "string": isinstance(value, str),
        # 2020-12: a number whose fraction is zero is an integer, however it was written.
        "integer": number is not None and number.denominator == 1,
        "number": number is not None,
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    # One type, or a list of them, which is how a schema producer often says "or null" (§203).
    named = (
        (expected,)
        if isinstance(expected, str)
        else tuple(expected.items)
        if isinstance(expected, JsonArray) and expected.items
        else None
    )
    if expected is not None:
        if named is None or any(not isinstance(item, str) or item not in matches for item in named):
            return f"schema type at {pointer} is unsupported"
        if not any(matches[item] for item in named if isinstance(item, str)):
            return f"value at {pointer} is not {' or '.join(str(item) for item in named)}"
    if isinstance(value, JsonObject):
        members = dict(value.entries)
        required = fields.get("required", JsonArray(()))
        if not isinstance(required, JsonArray) or any(
            not isinstance(item, str) for item in required.items
        ):
            return f"required at {pointer} is malformed"
        for name in required.items:
            if name not in members:
                return f"required field {name!r} is missing at {pointer}"
        membered = _members(members, pointer, fields, reading)
        if membered is not None:
            return membered
    if isinstance(value, JsonArray):
        return _items(value.items, pointer, fields, reading)
    return None


def _content_failure(content: JsonArray | None) -> str | None:
    if content is None:
        return None
    for index, item in enumerate(content.items):
        if not isinstance(item, JsonObject):
            return f"content item {index} is not an object"
        fields = dict(item.entries)
        kind = fields.get("type")
        if kind == "text" and isinstance(fields.get("text"), str):
            continue
        if (
            kind == "image"
            and isinstance(fields.get("data"), str)
            and isinstance(fields.get("mimeType"), str)
        ):
            continue
        if (
            kind == "resource_link"
            and isinstance(fields.get("uri"), str)
            and isinstance(fields.get("name"), str)
        ):
            # A link is evidence returned by the tool. The evaluator never fetches it.
            continue
        return f"content item {index} has an unsupported or malformed type"
    return None


def evaluate_tool_call(
    declaration: SmokeDeclaration,
    tools: Iterable[McpTool],
    result: McpCallResult | None,
) -> SmokeStageResult:
    """The protocol stage: the declared tool exists, takes these arguments, and its call is valid."""

    available = {tool.name: tool for tool in tools}
    tool = available.get(declaration.tool)
    if tool is None:
        protocol = SmokeStageResult(
            SmokeStage.PROTOCOL, SmokeOutcome.FAIL, "declared tool was not advertised"
        )
    else:
        argument_failure = _validate_schema(declaration.arguments, tool.input_schema)
        if argument_failure is not None:
            outcome = (
                SmokeOutcome.UNSUPPORTED
                if argument_failure.startswith("unsupported JSON Schema")
                else SmokeOutcome.FAIL
            )
            protocol = SmokeStageResult(SmokeStage.PROTOCOL, outcome, argument_failure)
        elif result is None:
            protocol = SmokeStageResult(
                SmokeStage.PROTOCOL, SmokeOutcome.NOT_RUN, "tool call did not complete"
            )
        elif result.jsonrpc_error is not None:
            protocol = SmokeStageResult(
                SmokeStage.PROTOCOL, SmokeOutcome.FAIL, "MCP returned a JSON-RPC error"
            )
        elif result.is_error is not None and not isinstance(result.is_error, bool):
            protocol = SmokeStageResult(
                SmokeStage.PROTOCOL, SmokeOutcome.FAIL, "MCP result has malformed isError"
            )
        elif result.is_error is True:
            protocol = SmokeStageResult(
                SmokeStage.PROTOCOL, SmokeOutcome.FAIL, "MCP result reports isError"
            )
        else:
            content_failure = _content_failure(result.content)
            output_failure = (
                None
                if tool.output_schema is None
                else _validate_schema(result.structured_content, tool.output_schema)
            )
            failure = content_failure or output_failure
            if failure is None:
                protocol = SmokeStageResult(
                    SmokeStage.PROTOCOL, SmokeOutcome.PASS, "declared MCP tool call completed"
                )
            else:
                outcome = (
                    SmokeOutcome.UNSUPPORTED
                    if failure.startswith("unsupported JSON Schema")
                    else SmokeOutcome.FAIL
                )
                protocol = SmokeStageResult(SmokeStage.PROTOCOL, outcome, failure)

    return protocol


def aggregate_success(results: Iterable[SmokeStageResult]) -> bool:
    values = tuple(results)
    return bool(values) and all(item.outcome is SmokeOutcome.PASS for item in values)


__all__ = [
    "McpCallResult",
    "McpNumber",
    "McpTool",
    "SmokeDeclaration",
    "SmokeOutcome",
    "SmokeSelection",
    "SmokeStage",
    "SmokeStageResult",
    "aggregate_success",
    "declaration_from_intent",
    "evaluate_tool_call",
    "select_installed_mcps",
]
