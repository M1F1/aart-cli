"""§205, INV-310, D-493: `consume mcp test` reads every schema FastMCP generates.

The fixtures are what real servers said to `tools/list` over stdio on 2026-10-28, kept verbatim
apart from each tool's prose description:

- `mcp-atlassian-0.23.1-tools.json`: sooperset's mcp-atlassian 0.23.1 on FastMCP 3.4.11, all 98
  tools. 0.21.1 is the same server on FastMCP 2.14.7, 73 tools.
- `fastmcp-*-pydantic-shapes.json`: a FastMCP server written for this test, whose tools take the
  Pydantic shapes real servers use: a nested model, a recursive one (3.4 only: 2.14 itself fails
  on it), a discriminated union, a dict, a tuple, a set, an enum, a Literal, a date, a UUID, a
  Decimal, a bounded float, and a dict whose keys are constrained.

The enterprise run that started this refused `jira_get_issue` over `pattern` on its issue key.
"""

from __future__ import annotations

import json
import re
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.mcp_smoke import (
    McpNumber,
    McpTool,
    SmokeDeclaration,
    SmokeOutcome,
    evaluate_tool_call,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.io.installed_smoke import _response_preview
from aart_cli.io.mcp_smoke import _call, _tools
from aart_cli.protocol.json import JsonObject

FIXTURES = Path(__file__).parent / "fixtures" / "mcp"
SERVERS = (
    "mcp-atlassian-0.23.1-tools.json",
    "mcp-atlassian-0.21.1-tools.json",
    "fastmcp-3.4.11-pydantic-shapes.json",
    "fastmcp-2.14.7-pydantic-shapes.json",
)

#: One value for each pattern the fixtures carry. A pattern missing here fails the test that
#: builds arguments, so a refreshed fixture cannot add one that nothing exercises.
MATCHING = {
    r"^[A-Z][A-Z0-9_]+-\d+(?:-\d+)*$": "PROJ-1",
    r"^[A-Z][A-Z0-9_]+$": "PROJ",
    r"^[a-z]+$": "lab",
    r"^[A-Z]+-\d+$": "AB-1",
    r"^[A-Z][A-Z0-9_]+-\d+$": "PROJ-1",
    r"^x": "x1",
}
ISSUE_KEY = r"^[A-Z][A-Z0-9_]+-\d+(?:-\d+)*$"


def _listed(name: str) -> tuple[McpTool, ...]:
    document = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    tools = _tools({"result": {"tools": document["tools"]}})
    assert isinstance(tools, Ok), tools
    return tools.value


def _raw(name: str) -> dict[str, dict]:
    document = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return {tool["name"]: tool for tool in document["tools"]}


def _resolve(reference: str, root: dict) -> dict:
    node = root
    for part in reference.removeprefix("#/").split("/"):
        node = node[part]
    return node


def _instance(schema: dict, root: dict, depth: int = 0) -> object:
    """A value meeting `schema` that fills every property, so every subschema is read."""

    if "$ref" in schema:
        return _instance(_resolve(schema["$ref"], root), root, depth + 1)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return _instance(schema[key][0], root, depth + 1)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type", "object" if "properties" in schema else None)
    if isinstance(kind, list):
        kind = kind[0]
    if kind == "string":
        if "pattern" in schema:
            return MATCHING[schema["pattern"]]
        return "x" * max(1, schema.get("minLength", 1))
    if kind in ("integer", "number"):
        low = schema.get("minimum", schema.get("exclusiveMinimum", 0))
        step = schema.get("multipleOf", 1)
        value = low if "minimum" in schema else low + step
        return value if kind == "number" else int(value)
    if kind == "boolean":
        return True
    if kind == "null":
        return None
    if kind == "array":
        prefix = [_instance(item, root, depth + 1) for item in schema.get("prefixItems", ())]
        if prefix:
            return prefix
        # A recursive model ends here: an empty list meets it, and the level above was read.
        if depth > 6:
            return []
        return [_instance(schema.get("items", {}), root, depth + 1)]
    if kind == "object":
        value = {
            name: _instance(member, root, depth + 1)
            for name, member in schema.get("properties", {}).items()
        }
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            names = schema.get("propertyNames", {}).get("enum", ["extra"])
            value[names[0]] = _instance(extra, root, depth + 1)
        for pattern, member in schema.get("patternProperties", {}).items():
            value[MATCHING[pattern]] = _instance(member, root, depth + 1)
        return value
    return None


def _arguments(value: object) -> JsonObject:
    """The arguments as the declaration would carry them, frozen the way the route freezes."""

    called = _call({"result": {"structuredContent": value}})
    assert isinstance(called, Ok), called
    assert isinstance(called.value.structured_content, JsonObject)
    return called.value.structured_content


def _preflight(tools: tuple[McpTool, ...], name: str, arguments: object):
    declaration = SmokeDeclaration(name, _arguments(arguments), 15)
    return evaluate_tool_call(declaration, tools, None)


class EveryGeneratedSchemaIsReadTest(unittest.TestCase):
    def test_a_call_filling_every_field_of_every_tool_is_allowed(self) -> None:
        for server in SERVERS:
            tools, raw = _listed(server), _raw(server)
            for name, tool in raw.items():
                with self.subTest(server=server, tool=name):
                    arguments = _instance(tool["inputSchema"], tool["inputSchema"])

                    protocol = _preflight(tools, name, arguments)

                    self.assertEqual(protocol.outcome, SmokeOutcome.NOT_RUN, protocol.reason)

    def test_an_answer_meeting_every_output_schema_passes(self) -> None:
        for server in SERVERS:
            tools, raw = _listed(server), _raw(server)
            for name, tool in raw.items():
                if "outputSchema" not in tool:
                    continue
                with self.subTest(server=server, tool=name):
                    schema = tool["outputSchema"]
                    answered = _call({"result": {"structuredContent": _instance(schema, schema)}})
                    assert isinstance(answered, Ok), answered
                    declaration = SmokeDeclaration(
                        name, _arguments(_instance(tool["inputSchema"], tool["inputSchema"])), 15
                    )

                    protocol = evaluate_tool_call(declaration, tools, answered.value)

                    self.assertEqual(protocol.outcome, SmokeOutcome.PASS, protocol.reason)


class TheReportedToolIsCheckedTest(unittest.TestCase):
    """`jira_get_issue`'s issue key, which the enterprise run refused over `pattern`."""

    def setUp(self) -> None:
        self.tools = _listed("mcp-atlassian-0.23.1-tools.json")

    def test_an_issue_key_is_allowed(self) -> None:
        for key in ("PROJ-1", "AB_C-12", "PROJ-1-2"):
            with self.subTest(key=key):
                protocol = _preflight(self.tools, "jira_get_issue", {"issue_key": key})

                self.assertEqual(protocol.outcome, SmokeOutcome.NOT_RUN, protocol.reason)

    def test_what_is_not_an_issue_key_is_refused_by_its_pattern(self) -> None:
        for key in ("proj-1", "PROJ", "PROJ-1x", "1PROJ-1", "P-1", "PROJ-١"):
            with self.subTest(key=key):
                protocol = _preflight(self.tools, "jira_get_issue", {"issue_key": key})

                self.assertEqual(protocol.outcome, SmokeOutcome.FAIL)
                self.assertEqual(protocol.reason, "value at $.issue_key does not match pattern")

    @given(st.text(alphabet="AZ09_-a", max_size=10))
    def test_a_key_is_allowed_exactly_when_the_pattern_finds_it(self, key: str) -> None:
        protocol = _preflight(self.tools, "jira_get_issue", {"issue_key": key})

        found = re.search(ISSUE_KEY, key, re.ASCII) is not None
        self.assertEqual(protocol.outcome is SmokeOutcome.NOT_RUN, found, protocol.reason)


def _one(schema: object, *, defs: object = None) -> tuple[McpTool, ...]:
    document = {"type": "object", "properties": {"v": schema}}
    if defs is not None:
        document["$defs"] = defs
    tools = _tools({"result": {"tools": [{"name": "t", "inputSchema": document}]}})
    assert isinstance(tools, Ok), tools
    return tools.value


def _check(schema: object, value: object, *, defs: object = None):
    return _preflight(_one(schema, defs=defs), "t", {"v": value})


class KeywordsTest(unittest.TestCase):
    def test_a_pattern_is_searched_for_not_anchored(self) -> None:
        self.assertEqual(_check({"pattern": "b"}, "abc").outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check({"pattern": "^b"}, "abc").outcome, SmokeOutcome.FAIL)

    def test_a_pattern_ends_where_javascript_s_does(self) -> None:
        """JSON Schema patterns are ECMA-262: `$` is the end, never before a final newline."""

        self.assertEqual(_check({"pattern": "^a$"}, "a\n").outcome, SmokeOutcome.FAIL)
        self.assertEqual(_check({"pattern": "^a$"}, "a").outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check({"pattern": "^[$]$"}, "$").outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check({"pattern": "a\\$"}, "a$").outcome, SmokeOutcome.NOT_RUN)

    def test_a_pattern_applies_only_to_a_string(self) -> None:
        self.assertEqual(_check({"pattern": "^a"}, 5).outcome, SmokeOutcome.NOT_RUN)

    def test_a_pattern_this_cannot_read_is_refused_not_ignored(self) -> None:
        for pattern in ("(?<name>a)", "\\p{L}", "("):
            with self.subTest(pattern=pattern):
                protocol = _check({"pattern": pattern}, "a")

                self.assertEqual(protocol.outcome, SmokeOutcome.UNSUPPORTED)
                self.assertIn("pattern", protocol.reason)

    def test_additional_properties_as_a_schema_checks_the_other_members(self) -> None:
        schema = {"type": "object", "additionalProperties": {"type": "integer"}}

        self.assertEqual(_check(schema, {"a": 1}).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check(schema, {"a": "x"}).reason, "value at $.v.a is not integer")

    def test_property_names_and_pattern_properties(self) -> None:
        named = {"type": "object", "propertyNames": {"enum": ["a", "b"]}}
        patterned = {"type": "object", "patternProperties": {"^x": {"type": "integer"}}}

        self.assertEqual(_check(named, {"a": 1}).outcome, SmokeOutcome.NOT_RUN)
        self.assertIn("property name 'c' at $.v", _check(named, {"c": 1}).reason)
        self.assertEqual(_check(named, {"c": 1}).outcome, SmokeOutcome.FAIL)
        self.assertEqual(_check(patterned, {"x1": 1, "y": "s"}).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check(patterned, {"x1": "s"}).reason, "value at $.v.x1 is not integer")

    def test_pattern_properties_count_as_declared_when_nothing_else_is_allowed(self) -> None:
        schema = {
            "type": "object",
            "patternProperties": {"^x": {"type": "integer"}},
            "additionalProperties": False,
        }

        self.assertEqual(_check(schema, {"x1": 1}).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check(schema, {"y": 1}).reason, "field 'y' is not allowed at $.v")

    def test_prefix_items_check_each_position_and_items_the_rest(self) -> None:
        pair = {"type": "array", "prefixItems": [{"type": "integer"}, {"type": "string"}]}
        rest = {**pair, "items": {"type": "boolean"}}

        self.assertEqual(_check(pair, [1, "a"]).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check(pair, ["a", 1]).reason, "value at $.v[0] is not integer")
        self.assertEqual(_check(rest, [1, "a", True]).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check(rest, [1, "a", 3]).reason, "value at $.v[2] is not boolean")

    def test_a_reference_into_the_schema_is_followed(self) -> None:
        defs = {"Child": {"type": "object", "required": ["name"]}}
        schema = {"$ref": "#/$defs/Child"}

        self.assertEqual(_check(schema, {"name": "a"}, defs=defs).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(
            _check(schema, {}, defs=defs).reason, "required field 'name' is missing at $.v"
        )

    def test_a_recursive_model_is_checked_at_every_depth(self) -> None:
        tools = _listed("fastmcp-3.4.11-pydantic-shapes.json")
        raw = _raw("fastmcp-3.4.11-pydantic-shapes.json")["shapes"]["inputSchema"]
        arguments = _instance(raw, raw)
        arguments["tree"] = {"label": "a", "children": [{"label": "b", "children": [{}]}]}

        protocol = _preflight(tools, "shapes", arguments)

        self.assertEqual(
            protocol.reason, "required field 'label' is missing at $.tree.children[0].children[0]"
        )

    def test_a_reference_that_resolves_to_nothing_or_to_itself_is_refused(self) -> None:
        cases = (
            ({"$ref": "#/$defs/Missing"}, None, SmokeOutcome.FAIL),
            (
                {"$ref": "#/$defs/Loop"},
                {"Loop": {"$ref": "#/$defs/Loop"}},
                SmokeOutcome.UNSUPPORTED,
            ),
            ({"$ref": "#/properties/v"}, None, SmokeOutcome.UNSUPPORTED),
        )
        for schema, defs, outcome in cases:
            with self.subTest(schema=schema):
                protocol = _check(schema, 1, defs=defs)

                self.assertEqual(protocol.outcome, outcome, protocol.reason)
                self.assertIn("$ref", protocol.reason)

    def test_a_discriminated_union_is_decided_by_its_branches(self) -> None:
        tools = _listed("fastmcp-3.4.11-pydantic-shapes.json")
        raw = _raw("fastmcp-3.4.11-pydantic-shapes.json")["shapes"]["inputSchema"]
        arguments = _instance(raw, raw)

        for pet, outcome in (
            ({"kind": "dog", "good": False}, SmokeOutcome.NOT_RUN),
            ({"kind": "cat", "lives": "nine"}, SmokeOutcome.FAIL),
        ):
            with self.subTest(pet=pet):
                protocol = _preflight(tools, "shapes", {**arguments, "pet": pet})

                self.assertEqual(protocol.outcome, outcome, protocol.reason)


class NumbersWithAFractionTest(unittest.TestCase):
    """FastMCP writes a `float` parameter's bounds and default as numbers with a fraction."""

    def test_a_fraction_is_kept_exactly_and_a_whole_one_is_an_integer(self) -> None:
        called = _call({"result": {"structuredContent": {"a": 0.1, "b": 2.0, "c": 1e300}}})

        assert isinstance(called, Ok), called
        members = dict(called.value.structured_content.entries)
        self.assertEqual(members["a"], McpNumber(Fraction(1, 10)))
        self.assertEqual(members["b"], 2)
        self.assertIsInstance(members["b"], int)
        self.assertEqual(members["c"], McpNumber(Fraction(10**300)))

    def test_what_is_not_a_number_is_refused(self) -> None:
        for raw in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(raw=raw):
                self.assertIsInstance(_call({"result": {"structuredContent": {"a": raw}}}), Err)

    def test_a_bounded_float_parameter_is_checked(self) -> None:
        ratio = {"type": "number", "minimum": 0.0, "maximum": 1.0}

        self.assertEqual(_check(ratio, 0.5).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check(ratio, 1.5).reason, "value at $.v is above maximum")
        self.assertEqual(_check({"type": "integer"}, 2.0).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_check({"type": "integer"}, 2.5).reason, "value at $.v is not integer")

    def test_a_whole_number_beyond_the_protocol_s_integers_is_still_an_integer(self) -> None:
        for whole in (1e300, 2**70, -(2**64)):
            with self.subTest(whole=whole):
                self.assertEqual(_check({"type": "integer"}, whole).outcome, SmokeOutcome.NOT_RUN)

    def test_multiple_of_a_fraction_is_exact(self) -> None:
        self.assertEqual(_check({"multipleOf": 0.1}, 0.3).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(
            _check({"multipleOf": 0.5}, 1.25).reason, "value at $.v is not a multipleOf"
        )

    @given(
        st.decimals(-1000, 1000, places=3, allow_nan=False, allow_infinity=False),
        st.decimals(-1000, 1000, places=3, allow_nan=False, allow_infinity=False),
    )
    def test_minimum_holds_exactly_when_the_written_value_reaches_it(
        self, value: Decimal, low: Decimal
    ) -> None:
        line = (
            '{"result":{"tools":[{"name":"t","inputSchema":{"type":"object","properties":'
            f'{{"v":{{"type":"number","minimum":{low}}}}}}}}}]}}}}'
        )
        tools = _tools(json.loads(line))
        assert isinstance(tools, Ok), tools
        arguments = _call(json.loads(f'{{"result":{{"structuredContent":{{"v":{value}}}}}}}'))
        assert isinstance(arguments, Ok), arguments

        protocol = evaluate_tool_call(
            SmokeDeclaration("t", arguments.value.structured_content, 15), tools.value, None
        )

        self.assertEqual(protocol.outcome is SmokeOutcome.NOT_RUN, value >= low, protocol.reason)

    def test_an_answer_with_a_fraction_is_shown_as_it_was_said(self) -> None:
        called = _call({"result": {"structuredContent": {"ratio": 0.25}, "content": []}})
        assert isinstance(called, Ok), called

        preview = _response_preview(called.value, sensitive=())

        self.assertIn('"ratio":0.25', preview["content"])


if __name__ == "__main__":
    unittest.main()
