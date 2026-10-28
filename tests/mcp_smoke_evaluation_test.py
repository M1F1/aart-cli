from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.mcp_smoke import (
    McpCallResult,
    McpTool,
    SmokeDeclaration,
    SmokeOutcome,
    SmokeStage,
    SmokeStageResult,
    aggregate_success,
    evaluate_tool_call,
)
from aart_cli.protocol.json import JsonArray, JsonObject


def obj(**values):
    return JsonObject(tuple(values.items()))


EMPTY_INPUT = obj(type="object", properties=obj(), additionalProperties=False)


class McpSmokeEvaluationTest(unittest.TestCase):
    def declaration(self):
        return SmokeDeclaration("read_identity", obj(), 15)

    def tool(self, output=None):
        return McpTool("read_identity", EMPTY_INPUT, output)

    def test_supported_text_structured_image_and_empty_results_pass_protocol(self) -> None:
        results = (
            McpCallResult(content=JsonArray((obj(type="text", text="Ada"),))),
            McpCallResult(structured_content=obj(user=obj(login="ada"))),
            McpCallResult(
                content=JsonArray((obj(type="image", data="AA==", mimeType="image/png"),))
            ),
            McpCallResult(content=JsonArray(())),
        )
        for result in results:
            with self.subTest(result=result):
                evaluated = evaluate_tool_call(self.declaration(), (self.tool(),), result)
                self.assertEqual(evaluated.stage, SmokeStage.PROTOCOL)
                self.assertEqual(evaluated.outcome, SmokeOutcome.PASS)

    def test_protocol_errors_and_malformed_results_fail_the_protocol_stage(self) -> None:
        results = (
            McpCallResult(jsonrpc_error="server failed"),
            McpCallResult(is_error=True),
            McpCallResult(is_error="yes"),  # type: ignore[arg-type]
            McpCallResult(content=JsonArray((obj(type="text"),))),
        )
        for result in results:
            with self.subTest(result=result):
                evaluated = evaluate_tool_call(self.declaration(), (self.tool(),), result)
                self.assertEqual(evaluated.outcome, SmokeOutcome.FAIL)

    def test_required_arguments_fail_before_invocation(self) -> None:
        schema = obj(
            type="object",
            properties=obj(tenant=obj(type="string")),
            required=JsonArray(("tenant",)),
        )
        evaluated = evaluate_tool_call(
            self.declaration(), (McpTool("read_identity", schema),), None
        )
        self.assertEqual(evaluated.outcome, SmokeOutcome.FAIL)
        self.assertIn("required field", evaluated.reason)

    def test_output_schema_is_checked_and_unsupported_keywords_are_visible(self) -> None:
        output = obj(
            type="object",
            properties=obj(login=obj(type="string")),
            required=JsonArray(("login",)),
        )
        failed = evaluate_tool_call(
            self.declaration(),
            (self.tool(output),),
            McpCallResult(structured_content=obj(id=7)),
        )
        self.assertEqual(failed.outcome, SmokeOutcome.FAIL)

        unsupported = evaluate_tool_call(
            self.declaration(),
            (self.tool(obj(type="string", **{"not": obj(const="Ada")})),),
            McpCallResult(structured_content="Ada"),
        )
        self.assertEqual(unsupported.outcome, SmokeOutcome.UNSUPPORTED)

    def test_a_passing_call_says_nothing_about_the_service(self) -> None:
        """INV-250: the reason names the call, never service access, whatever the text says."""

        evaluated = evaluate_tool_call(
            self.declaration(),
            (self.tool(),),
            McpCallResult(content=JsonArray((obj(type="text", text="Error: unauthorized"),))),
        )
        self.assertEqual(evaluated.outcome, SmokeOutcome.PASS)
        self.assertNotIn("service", evaluated.reason)

    def test_aggregate_refuses_empty_and_skipped_runs(self) -> None:
        self.assertFalse(aggregate_success(()))
        self.assertTrue(
            aggregate_success((SmokeStageResult(SmokeStage.PROTOCOL, SmokeOutcome.PASS, "ok"),))
        )
        for outcome in SmokeOutcome:
            if outcome is SmokeOutcome.PASS:
                continue
            with self.subTest(outcome=outcome):
                self.assertFalse(
                    aggregate_success((SmokeStageResult(SmokeStage.PROTOCOL, outcome, "not pass"),))
                )

    @given(st.lists(st.sampled_from(tuple(SmokeOutcome)), min_size=1, max_size=20))
    def test_aggregate_passes_exactly_when_every_stage_passes(
        self, outcomes: list[SmokeOutcome]
    ) -> None:
        stages = tuple(
            SmokeStageResult(SmokeStage.PROTOCOL, outcome, "bounded") for outcome in outcomes
        )
        self.assertEqual(
            aggregate_success(stages),
            all(outcome is SmokeOutcome.PASS for outcome in outcomes),
        )


if __name__ == "__main__":
    unittest.main()


class McpSmokeSchemaAnnotationTest(unittest.TestCase):
    """A schema's annotations are read past; a constraint this validator lacks is still refused.

    The shape below is copied from a real server's `tools/list`: every property carries a
    `description`, and every optional one a `default`. Under a closed allowlist that was an
    unsupported keyword, so a declared call was refused before invocation over a word that cannot
    make any value invalid -- the validator refused the server rather than the schema (B-173).
    """

    ANNOTATED = obj(
        type="object",
        title="list_dags arguments",
        description="Arguments for listing DAGs.",
        properties=obj(
            tag=obj(type="string", description="Optional tag to filter by", default=""),
            limit=obj(type="integer", description="How many to return", default=100),
        ),
    )

    def _refusal(self, schema, arguments):
        declaration = SmokeDeclaration("list_dags", arguments, 15)
        tool = McpTool("list_dags", schema, None)
        # `None` is the preflight the stdio route makes before it sends anything: NOT_RUN means
        # the call was allowed to happen, anything else is the refusal it reports instead.
        return evaluate_tool_call(declaration, (tool,), None)

    def test_annotations_do_not_refuse_a_declared_call(self) -> None:
        protocol = self._refusal(self.ANNOTATED, obj(limit=5))

        self.assertEqual(protocol.outcome, SmokeOutcome.NOT_RUN)

    def test_a_constraint_this_validator_cannot_apply_is_still_refused(self) -> None:
        constrained = obj(
            type="object",
            properties=obj(
                tag=obj(type="string", description="Which tag", **{"not": obj(const="p")})
            ),
        )

        protocol = self._refusal(constrained, obj(tag="project"))

        self.assertNotEqual(protocol.outcome, SmokeOutcome.NOT_RUN)
        # Named, because the point of refusing is to say which constraint went unapplied.
        self.assertIn("'not'", protocol.reason)

    def test_an_annotation_never_makes_a_value_invalid(self) -> None:
        # `default` says what an absent value would have been. Supplying a different one is the
        # ordinary case, and a validator that read `default` as a constraint would refuse it.
        protocol = self._refusal(self.ANNOTATED, obj(tag="project:x", limit=7))

        self.assertEqual(protocol.outcome, SmokeOutcome.NOT_RUN)
