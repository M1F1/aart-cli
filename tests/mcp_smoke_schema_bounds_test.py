"""§203, D-490: `consume mcp test` applies the bounds a generated tool schema states.

An enterprise run of `consume mcp test` against a fastmcp server (Atlassian's `jira_search`) was
refused before the call: `unsupported JSON Schema keyword 'minimum' at $.limit`. The server worked.
Its input schema bounds `limit` with `minimum` and `maximum`, and every fastmcp output schema
carries `x-fastmcp-wrap-result`, so the validator refused every server of that kind. It now applies
the bounds, the `anyOf`/`oneOf`/`allOf` branches and a list of types, passes over `x-` extensions
and the 2020-12 annotations, and still refuses a keyword it does not implement.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.mcp_smoke import (
    McpCallResult,
    McpTool,
    SmokeDeclaration,
    SmokeOutcome,
    evaluate_tool_call,
)
from aart_cli.protocol.json import JsonArray, JsonObject


def obj(**values: object) -> JsonObject:
    return JsonObject(tuple(values.items()))  # type: ignore[arg-type]


def arr(*values: object) -> JsonArray:
    return JsonArray(values)  # type: ignore[arg-type]


#: The shape of `jira_search` as the enterprise run met it: a bounded `limit`, an optional
#: `fields` that may be null, and fastmcp's wrapped output.
JIRA_INPUT = obj(
    type="object",
    properties=obj(
        jql=obj(type="string", description="JQL query", minLength=1),
        limit=obj(type="integer", default=10, minimum=1, maximum=50),
        fields=obj(anyOf=arr(obj(type="string"), obj(type="null")), default=None),
    ),
    required=arr("jql"),
)
JIRA_OUTPUT = obj(
    type="object",
    properties=obj(result=obj(type="string")),
    required=arr("result"),
    **{"x-fastmcp-wrap-result": True},
)


def _preflight(schema: JsonObject, arguments: JsonObject):
    """The refusal the stdio route reports before sending anything; NOT_RUN is "allowed"."""

    return evaluate_tool_call(
        SmokeDeclaration("tool", arguments, 15), (McpTool("tool", schema, None),), None
    )


def _answered(output: JsonObject, structured: JsonObject):
    tool = McpTool("jira_search", JIRA_INPUT, output)
    return evaluate_tool_call(
        SmokeDeclaration("jira_search", obj(jql="assignee = currentUser()", limit=5), 15),
        (tool,),
        McpCallResult(structured_content=structured),
    )


class TheReportedServerPassesTest(unittest.TestCase):
    def test_jira_search_s_declared_call_is_allowed(self) -> None:
        protocol = _preflight(JIRA_INPUT, obj(jql="assignee = currentUser()", limit=5))

        self.assertEqual(protocol.outcome, SmokeOutcome.NOT_RUN, protocol.reason)

    def test_a_fastmcp_wrapped_answer_passes(self) -> None:
        protocol = _answered(JIRA_OUTPUT, obj(result="[]"))

        self.assertEqual(protocol.outcome, SmokeOutcome.PASS, protocol.reason)

    def test_the_wrapped_answer_is_still_checked(self) -> None:
        protocol = _answered(JIRA_OUTPUT, obj(other="[]"))

        self.assertEqual(protocol.outcome, SmokeOutcome.FAIL)
        self.assertIn("'result'", protocol.reason)


class BoundsAreAppliedTest(unittest.TestCase):
    def test_each_bound_refuses_a_value_outside_it(self) -> None:
        cases = (
            (obj(type="integer", maximum=50), 51),
            (obj(type="integer", exclusiveMinimum=0), 0),
            (obj(type="integer", exclusiveMaximum=10), 10),
            (obj(type="integer", multipleOf=5), 7),
            (obj(type="string", minLength=2), "a"),
            (obj(type="string", maxLength=2), "abc"),
            (obj(type="array", minItems=1), arr()),
            (obj(type="array", maxItems=1), arr(1, 2)),
            (obj(type="array", uniqueItems=True), arr(1, 1)),
            (obj(type="object", minProperties=1), obj()),
            (obj(type="object", maxProperties=0), obj(a=1)),
        )
        for schema, value in cases:
            with self.subTest(schema=schema):
                protocol = _preflight(obj(type="object", properties=obj(v=schema)), obj(v=value))
                self.assertEqual(protocol.outcome, SmokeOutcome.FAIL, protocol.reason)

    @given(st.integers(-100, 100), st.integers(-100, 100))
    def test_minimum_holds_exactly_when_the_value_reaches_it(self, value: int, low: int) -> None:
        schema = obj(type="object", properties=obj(v=obj(type="integer", minimum=low)))

        protocol = _preflight(schema, obj(v=value))

        self.assertEqual(protocol.outcome is SmokeOutcome.NOT_RUN, value >= low, protocol.reason)

    def test_a_list_of_types_takes_any_of_them(self) -> None:
        schema = obj(type="object", properties=obj(v=obj(type=arr("string", "null"))))

        self.assertEqual(_preflight(schema, obj(v=None)).outcome, SmokeOutcome.NOT_RUN)
        self.assertEqual(_preflight(schema, obj(v=3)).outcome, SmokeOutcome.FAIL)


class BranchesAreAppliedTest(unittest.TestCase):
    def test_any_of_one_of_and_all_of(self) -> None:
        number, text = obj(type="integer"), obj(type="string")
        cases = (
            (obj(anyOf=arr(number, text)), "x", SmokeOutcome.NOT_RUN),
            (obj(anyOf=arr(number, text)), True, SmokeOutcome.FAIL),
            (obj(oneOf=arr(number, obj(minimum=0))), 5, SmokeOutcome.FAIL),
            (obj(oneOf=arr(number, text)), 5, SmokeOutcome.NOT_RUN),
            (obj(allOf=arr(number, obj(minimum=0))), -1, SmokeOutcome.FAIL),
            (obj(allOf=arr(number, obj(minimum=0))), 1, SmokeOutcome.NOT_RUN),
        )
        for schema, value, outcome in cases:
            with self.subTest(schema=schema, value=value):
                protocol = _preflight(obj(type="object", properties=obj(v=schema)), obj(v=value))
                self.assertEqual(protocol.outcome, outcome, protocol.reason)

    def test_an_unimplemented_keyword_in_a_branch_is_still_refused(self) -> None:
        schema = obj(anyOf=arr(obj(type="string", **{"not": obj(const="b")}), obj(type="null")))

        protocol = _preflight(obj(type="object", properties=obj(v=schema)), obj(v="abc"))

        self.assertEqual(protocol.outcome, SmokeOutcome.UNSUPPORTED)
        self.assertIn("'not'", protocol.reason)


class ExtensionsConstrainNothingTest(unittest.TestCase):
    @given(st.from_regex(r"x-[a-z][a-z-]{0,20}", fullmatch=True))
    def test_any_x_keyword_is_passed_over(self, keyword: str) -> None:
        schema = obj(type="object", **{keyword: True})

        self.assertEqual(_preflight(schema, obj()).outcome, SmokeOutcome.NOT_RUN)

    def test_format_is_an_annotation(self) -> None:
        schema = obj(type="object", properties=obj(v=obj(type="string", format="date-time")))

        self.assertEqual(_preflight(schema, obj(v="not a date")).outcome, SmokeOutcome.NOT_RUN)

    def test_a_reference_outside_the_schema_is_still_refused(self) -> None:
        """§205 reads a reference into the tool's own schema; one elsewhere is never fetched."""

        schema = obj(type="object", properties=obj(v=obj(**{"$ref": "https://example.invalid/v"})))

        self.assertEqual(_preflight(schema, obj(v=1)).outcome, SmokeOutcome.UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
