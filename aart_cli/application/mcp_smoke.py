"""Pure planning and result evaluation for installed MCP smoke verification.

Process execution, filesystem reads, credential providers and harness CLIs stay outside this
module. The types here keep each claim separate so a successful JSON-RPC call cannot silently
become proof of service access or harness execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
    NOT_VERIFIED = "NOT VERIFIED"
    UNSUPPORTED = "UNSUPPORTED"


class SmokeStage(str, Enum):
    INSTALLATION = "installation-configuration"
    PROTOCOL = "mcp-startup-and-protocol"
    EXPECTATION = "result-expectation"
    SERVICE = "mcp-to-external-service"
    MODEL_PROVIDER = "harness-to-model-provider"
    HARNESS = "harness-to-mcp-to-external-service"
    MODEL_ASSESSMENT = "model-assessment"


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
    expect: JsonObject | None = None


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
    service_observed: bool = False


@dataclass(frozen=True, slots=True)
class SmokeEvaluation:
    protocol: SmokeStageResult
    expectation: SmokeStageResult
    service: SmokeStageResult


@dataclass(frozen=True, slots=True)
class SmokeSelection:
    targets: tuple[InstalledRecord, ...]
    failure: str | None = None


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
            matches = [
                record
                for record in eligible
                if selector
                in {
                    str(record.coordinate),
                    installation_key(record.coordinate, record.receipt.owner),
                }
            ]
            if not matches:
                return SmokeSelection((), f"selector {selector!r} names no installed MCP target")
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
    expectation = fields.get("expect")
    if (
        not isinstance(tool, str)
        or not isinstance(arguments, JsonObject)
        or isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= 60
        or not (expectation is None or isinstance(expectation, JsonObject))
        or fields.get("read_only") is not True
    ):
        return None
    return SmokeDeclaration(tool, arguments, timeout, expectation)


def _python(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _python(item) for key, item in value.entries}
    if isinstance(value, JsonArray):
        return [_python(item) for item in value.items]
    return value


_SUPPORTED_SCHEMA_KEYS = frozenset(
    {"type", "properties", "required", "additionalProperties", "items", "enum", "const"}
)


def _validate_schema(value: JsonValue, schema: JsonObject, pointer: str = "$") -> str | None:
    fields = dict(schema.entries)
    unsupported = sorted(fields.keys() - _SUPPORTED_SCHEMA_KEYS)
    if unsupported:
        return f"unsupported JSON Schema keyword {unsupported[0]!r} at {pointer}"
    if "const" in fields and value != fields["const"]:
        return f"value at {pointer} does not equal const"
    if "enum" in fields:
        choices = fields["enum"]
        if not isinstance(choices, JsonArray):
            return f"enum at {pointer} is malformed"
        if value not in choices.items:
            return f"value at {pointer} is outside enum"
    expected = fields.get("type")
    matches = {
        "object": isinstance(value, JsonObject),
        "array": isinstance(value, JsonArray),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expected is not None:
        if not isinstance(expected, str) or expected not in matches:
            return f"schema type at {pointer} is unsupported"
        if not matches[expected]:
            return f"value at {pointer} is not {expected}"
    if isinstance(value, JsonObject):
        members = dict(value.entries)
        properties = fields.get("properties", JsonObject(()))
        if not isinstance(properties, JsonObject):
            return f"properties at {pointer} is malformed"
        property_schemas = dict(properties.entries)
        required = fields.get("required", JsonArray(()))
        if not isinstance(required, JsonArray) or any(
            not isinstance(item, str) for item in required.items
        ):
            return f"required at {pointer} is malformed"
        for name in required.items:
            if name not in members:
                return f"required field {name!r} is missing at {pointer}"
        additional = fields.get("additionalProperties", True)
        if not isinstance(additional, bool):
            return f"additionalProperties at {pointer} is unsupported"
        if not additional:
            unknown = sorted(members.keys() - property_schemas.keys())
            if unknown:
                return f"field {unknown[0]!r} is not allowed at {pointer}"
        for name, member in members.items():
            child = property_schemas.get(name)
            if child is None:
                continue
            if not isinstance(child, JsonObject):
                return f"schema for {pointer}.{name} is malformed"
            failure = _validate_schema(member, child, f"{pointer}.{name}")
            if failure is not None:
                return failure
    if isinstance(value, JsonArray) and "items" in fields:
        item_schema = fields["items"]
        if not isinstance(item_schema, JsonObject):
            return f"items at {pointer} is malformed"
        for index, item in enumerate(value.items):
            failure = _validate_schema(item, item_schema, f"{pointer}[{index}]")
            if failure is not None:
                return failure
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


def _expectation_failure(expect: JsonObject, result: McpCallResult) -> str | None:
    fields = dict(expect.entries)
    if set(fields) == {"text_contains"}:
        needle = fields["text_contains"]
        assert isinstance(needle, str)
        text = "\n".join(
            str(dict(item.entries)["text"])
            for item in (() if result.content is None else result.content.items)
            if isinstance(item, JsonObject)
            and dict(item.entries).get("type") == "text"
            and isinstance(dict(item.entries).get("text"), str)
        )
        return None if needle in text else "declared text was not present"
    path = fields.get("structured_path")
    if not isinstance(path, str) or "equals" not in fields:
        return "expectation is malformed"
    current = result.structured_content
    for component in path.split("."):
        if not isinstance(current, JsonObject):
            return f"structured path {path!r} was not present"
        current = current.get(component)
        if current is None:
            return f"structured path {path!r} was not present"
    return (
        None
        if current == fields["equals"]
        else f"structured path {path!r} did not equal expected value"
    )


def evaluate_tool_call(
    declaration: SmokeDeclaration,
    tools: Iterable[McpTool],
    result: McpCallResult | None,
) -> SmokeEvaluation:
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

    if protocol.outcome is not SmokeOutcome.PASS:
        expectation = SmokeStageResult(
            SmokeStage.EXPECTATION,
            SmokeOutcome.NOT_RUN,
            f"depends on {SmokeStage.PROTOCOL.value}",
        )
        service = SmokeStageResult(
            SmokeStage.SERVICE,
            SmokeOutcome.NOT_RUN,
            f"depends on {SmokeStage.PROTOCOL.value}",
        )
        return SmokeEvaluation(protocol, expectation, service)

    assert result is not None
    if declaration.expect is None:
        expectation = SmokeStageResult(
            SmokeStage.EXPECTATION,
            SmokeOutcome.NOT_CONFIGURED,
            "the declaration has no optional expectation",
        )
    else:
        failed = _expectation_failure(declaration.expect, result)
        expectation = SmokeStageResult(
            SmokeStage.EXPECTATION,
            SmokeOutcome.PASS if failed is None else SmokeOutcome.FAIL,
            "declared expectation matched" if failed is None else failed,
        )
    service = SmokeStageResult(
        SmokeStage.SERVICE,
        SmokeOutcome.PASS if result.service_observed else SmokeOutcome.NOT_VERIFIED,
        (
            "the declared read reached the protected fixture service"
            if result.service_observed
            else "the response does not independently prove external-service access"
        ),
    )
    return SmokeEvaluation(protocol, expectation, service)


def aggregate_success(results: Iterable[SmokeStageResult]) -> bool:
    values = tuple(results)
    return bool(values) and all(item.outcome is SmokeOutcome.PASS for item in values)


__all__ = [
    "McpCallResult",
    "McpTool",
    "SmokeDeclaration",
    "SmokeEvaluation",
    "SmokeOutcome",
    "SmokeSelection",
    "SmokeStage",
    "SmokeStageResult",
    "aggregate_success",
    "declaration_from_intent",
    "evaluate_tool_call",
    "select_installed_mcps",
]
