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
    def declaration(self, expect=None):
        return SmokeDeclaration("read_identity", obj(), 15, expect)

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
                self.assertEqual(evaluated.protocol.outcome, SmokeOutcome.PASS)
                self.assertEqual(evaluated.expectation.outcome, SmokeOutcome.NOT_CONFIGURED)
                self.assertEqual(evaluated.service.outcome, SmokeOutcome.NOT_VERIFIED)

    def test_protocol_errors_and_malformed_results_do_not_run_dependants(self) -> None:
        results = (
            McpCallResult(jsonrpc_error="server failed"),
            McpCallResult(is_error=True),
            McpCallResult(is_error="yes"),  # type: ignore[arg-type]
            McpCallResult(content=JsonArray((obj(type="text"),))),
        )
        for result in results:
            with self.subTest(result=result):
                evaluated = evaluate_tool_call(self.declaration(), (self.tool(),), result)
                self.assertEqual(evaluated.protocol.outcome, SmokeOutcome.FAIL)
                self.assertEqual(evaluated.expectation.outcome, SmokeOutcome.NOT_RUN)
                self.assertEqual(evaluated.service.outcome, SmokeOutcome.NOT_RUN)

    def test_required_arguments_fail_before_invocation(self) -> None:
        schema = obj(
            type="object",
            properties=obj(tenant=obj(type="string")),
            required=JsonArray(("tenant",)),
        )
        evaluated = evaluate_tool_call(
            self.declaration(), (McpTool("read_identity", schema),), None
        )
        self.assertEqual(evaluated.protocol.outcome, SmokeOutcome.FAIL)
        self.assertIn("required field", evaluated.protocol.reason)

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
        self.assertEqual(failed.protocol.outcome, SmokeOutcome.FAIL)

        unsupported = evaluate_tool_call(
            self.declaration(),
            (self.tool(obj(oneOf=JsonArray((obj(type="string"),)))),),
            McpCallResult(structured_content="Ada"),
        )
        self.assertEqual(unsupported.protocol.outcome, SmokeOutcome.UNSUPPORTED)

    def test_both_expectation_forms_share_the_protocol_result(self) -> None:
        text = evaluate_tool_call(
            self.declaration(obj(text_contains="Ada")),
            (self.tool(),),
            McpCallResult(content=JsonArray((obj(type="text", text="Hello Ada"),))),
        )
        structured = evaluate_tool_call(
            self.declaration(obj(structured_path="user.login", equals="ada")),
            (self.tool(),),
            McpCallResult(structured_content=obj(user=obj(login="ada"))),
        )
        self.assertEqual(text.expectation.outcome, SmokeOutcome.PASS)
        self.assertEqual(structured.expectation.outcome, SmokeOutcome.PASS)

        wrong = evaluate_tool_call(
            self.declaration(obj(text_contains="Grace")),
            (self.tool(),),
            McpCallResult(content=JsonArray((obj(type="text", text="Hello Ada"),))),
        )
        self.assertEqual(wrong.protocol.outcome, SmokeOutcome.PASS)
        self.assertEqual(wrong.expectation.outcome, SmokeOutcome.FAIL)

    def test_service_proof_is_independent_of_successful_or_cached_content(self) -> None:
        cached = evaluate_tool_call(
            self.declaration(obj(text_contains="Ada")),
            (self.tool(),),
            McpCallResult(content=JsonArray((obj(type="text", text="Ada"),))),
        )
        observed = evaluate_tool_call(
            self.declaration(obj(text_contains="Ada")),
            (self.tool(),),
            McpCallResult(
                content=JsonArray((obj(type="text", text="Ada"),)), service_observed=True
            ),
        )
        self.assertEqual(cached.protocol.outcome, SmokeOutcome.PASS)
        self.assertEqual(cached.expectation.outcome, SmokeOutcome.PASS)
        self.assertEqual(cached.service.outcome, SmokeOutcome.NOT_VERIFIED)
        self.assertEqual(observed.service.outcome, SmokeOutcome.PASS)

    def test_aggregate_refuses_empty_skipped_and_unverified_runs(self) -> None:
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
