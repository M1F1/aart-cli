from __future__ import annotations

import unittest
from unittest.mock import patch

from aart_cli import cli
from aart_cli.application.mcp_smoke import (
    McpCallResult,
    McpTool,
    SmokeDeclaration,
    SmokeOutcome,
    SmokeStage,
    SmokeStageResult,
)
from aart_cli.commands import mcp
from aart_cli.domain.result import Ok
from aart_cli.io.mcp_smoke import DirectSmokeRun
from aart_cli.protocol.json import JsonArray, JsonObject
from tests.mcp_smoke_selection_test import installed


class McpSmokeCliTest(unittest.TestCase):
    def test_selected_and_bulk_forms_map_to_one_request_shape(self) -> None:
        selected = cli._to_request(
            cli.build_parser().parse_args(
                [
                    "mcp",
                    "test",
                    "local/mcp/identity@1.0.0",
                    "--harness",
                    "opencode,tabnine",
                    "--scope",
                    "project",
                    "--project",
                    "/work",
                    "--json",
                    "--show-response",
                ]
            )
        )
        self.assertEqual(selected.command, "mcp")
        self.assertEqual(selected.mcp_action, "test")
        self.assertEqual(selected.profiles, ("opencode", "tabnine"))
        self.assertFalse(selected.all_installed)
        self.assertTrue(selected.show_response)

        self.assertFalse(selected.prompt_only)
        self.assertIsNone(selected.report_path)

        operator = cli._to_request(
            cli.build_parser().parse_args(
                ["mcp", "test", "--all", "--harness", "claude", "--prompt"]
            )
        )
        self.assertTrue(operator.prompt_only)

        graded = cli._to_request(
            cli.build_parser().parse_args(
                ["mcp", "test", "--all", "--harness", "claude", "--report", "out.json"]
            )
        )
        self.assertEqual(graded.report_path, "out.json")

        bulk = cli._to_request(
            cli.build_parser().parse_args(
                ["mcp", "test", "--all", "--harness", "opencode", "--scope", "user"]
            )
        )
        self.assertTrue(bulk.all_installed)
        self.assertEqual(bulk.names, ())

    def test_dispatch_uses_the_mcp_handler(self) -> None:
        seen = []

        def run(request):
            seen.append(request)
            return 17

        with patch.dict(cli.DISPATCH, {"mcp": run}):
            status = cli.main(["mcp", "test", "--all", "--harness", "opencode"])
        self.assertEqual(status, 17)
        self.assertEqual(seen[0].mcp_action, "test")

    def test_target_report_never_contains_configuration_or_raw_tool_payload(self) -> None:
        declaration = SmokeDeclaration(
            "read_identity",
            JsonObject((("tenant", JsonObject((("configuration", "tenant"),))),)),
            15,
        )
        tool = McpTool(
            "read_identity",
            JsonObject((("type", "object"),)),
        )
        raw_result = McpCallResult(
            content=JsonArray((JsonObject((("type", "text"), ("text", "raw-private-response"))),))
        )
        harness_stages = (
            SmokeStageResult(SmokeStage.MODEL_PROVIDER, SmokeOutcome.PASS, "model passed"),
            SmokeStageResult(SmokeStage.HARNESS, SmokeOutcome.NOT_VERIFIED, "service unverified"),
            SmokeStageResult(SmokeStage.MODEL_ASSESSMENT, SmokeOutcome.PASS, "assessment passed"),
            "1.0.0",
            "direct-and-harness",
        )
        with (
            patch.object(
                mcp, "_configuration_values", return_value=({"tenant": "private-value"}, None)
            ),
            patch.object(mcp, "_declaration", return_value=(declaration, None)),
            patch.object(
                mcp,
                "execute_stdio_smoke",
                return_value=Ok(DirectSmokeRun("2025-11-25", (tool,), raw_result)),
            ),
            patch.object(mcp, "_harness_stages", return_value=harness_stages),
        ):
            report = mcp._target(installed("local", "opencode"), "/managed", show_response=False)

        rendered = repr(report)
        self.assertNotIn("private-value", rendered)
        self.assertNotIn("raw-private-response", rendered)

    def test_show_response_is_explicit_bounded_and_redacts_known_configuration(self) -> None:
        result = McpCallResult(
            content=JsonArray(
                (JsonObject((("type", "text"), ("text", "tenant-private\n" + "x" * 70000))),)
            )
        )
        preview = mcp._response_preview(result, sensitive=("tenant-private",))
        self.assertNotIn("tenant-private", preview["content"])
        self.assertIn("<redacted>", preview["content"])
        self.assertTrue(preview["truncated"])
        self.assertLessEqual(len(preview["content"].encode("utf-8")), 65536)

    def test_no_harness_is_started_and_coverage_says_so(self) -> None:
        """D-368: AART drives no harness, so every installation is direct until a report arrives.

        This replaces a test that singled Tabnine out for lacking an allowed-tools boundary. That
        distinction existed only because AART used to submit the prompt itself.
        """

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)
        tool = McpTool("read_identity", JsonObject((("type", "object"),)))
        result = McpCallResult(
            content=JsonArray((JsonObject((("type", "text"), ("text", "Ada"))),))
        )
        with (
            patch.object(mcp, "_configuration_values", return_value=({}, None)),
            patch.object(mcp, "_declaration", return_value=(declaration, None)),
            patch.object(
                mcp,
                "execute_stdio_smoke",
                return_value=Ok(DirectSmokeRun("2025-11-25", (tool,), result)),
            ),
        ):
            report = mcp._target(installed("local", "tabnine"), "/managed", show_response=True)

        self.assertEqual(report["coverage"], "direct")
        stages = {stage["stage"]: stage["outcome"] for stage in report["stages"]}
        self.assertEqual(stages["mcp-startup-and-protocol"], "PASS")
        self.assertEqual(stages["harness-to-model-provider"], "NOT RUN")
        self.assertIn("response", report)

    def test_an_absent_harness_report_does_not_fail_an_otherwise_successful_direct_run(
        self,
    ) -> None:
        """§170.5 and INV-251: no report is an honest non-success, not a failure.

        The alternative readings are both wrong -- failing the run punishes someone for not having
        run a harness session, and counting the stages as passes would claim evidence nobody
        gathered.
        """

        # A declared service read plus the expectation that proves it: without both, the service
        # stage is not a PASS and no run passes, capability or not.
        declaration = SmokeDeclaration(
            "read_identity",
            JsonObject(()),
            15,
            JsonObject((("text_contains", "Ada"),)),
            True,
        )
        tool = McpTool("read_identity", JsonObject((("type", "object"),)))
        result = McpCallResult(
            content=JsonArray((JsonObject((("type", "text"), ("text", "Ada"))),)),
        )
        with (
            patch.object(mcp, "_configuration_values", return_value=({}, None)),
            patch.object(mcp, "_declaration", return_value=(declaration, None)),
            patch.object(
                mcp,
                "execute_stdio_smoke",
                return_value=Ok(DirectSmokeRun("2025-11-25", (tool,), result)),
            ),
        ):
            report = mcp._target(installed("local", "tabnine"), "/managed")

        self.assertEqual(report["coverage"], "direct")
        self.assertIs(report["ok"], True)
        stages = {stage["stage"]: stage["outcome"] for stage in report["stages"]}
        self.assertEqual(stages["mcp-startup-and-protocol"], "PASS")
        self.assertEqual(stages["mcp-to-external-service"], "PASS")
        # Present and honest, rather than absent or quietly green.
        for absent in (
            "harness-to-model-provider",
            "harness-to-mcp-to-external-service",
            "model-assessment",
        ):
            self.assertEqual(stages[absent], "NOT RUN")

    def test_an_unverified_service_stage_still_fails_a_direct_run(self) -> None:
        """The exclusion is narrow: it drops the harness stages and nothing else.

        Without this, the previous test could pass because `ok` ignored every non-PASS stage
        rather than because it ignored exactly the three that capability excluded. The declared
        service read has no expectation, so it is claimed and unproven -- required, and not a pass.
        """

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15, None, True)
        tool = McpTool("read_identity", JsonObject((("type", "object"),)))
        result = McpCallResult(
            content=JsonArray((JsonObject((("type", "text"), ("text", "Ada"))),))
        )
        with (
            patch.object(mcp, "_configuration_values", return_value=({}, None)),
            patch.object(mcp, "_declaration", return_value=(declaration, None)),
            patch.object(
                mcp,
                "execute_stdio_smoke",
                return_value=Ok(DirectSmokeRun("2025-11-25", (tool,), result)),
            ),
        ):
            report = mcp._target(installed("local", "tabnine"), "/managed")

        self.assertIs(report["ok"], False)
        stages = {stage["stage"]: stage["outcome"] for stage in report["stages"]}
        self.assertEqual(stages["mcp-to-external-service"], "NOT VERIFIED")

    def test_an_undeclared_service_read_does_not_block_a_zero_exit(self) -> None:
        """B-164: the stage nobody declared is outside the required set (§170.3, §170.5).

        Before this, the service stage was in the required set unconditionally and nothing could
        satisfy it, so every working installation exited non-zero.
        """

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)
        tool = McpTool("read_identity", JsonObject((("type", "object"),)))
        result = McpCallResult(
            content=JsonArray((JsonObject((("type", "text"), ("text", "Ada"))),))
        )
        with (
            patch.object(mcp, "_configuration_values", return_value=({}, None)),
            patch.object(mcp, "_declaration", return_value=(declaration, None)),
            patch.object(
                mcp,
                "execute_stdio_smoke",
                return_value=Ok(DirectSmokeRun("2025-11-25", (tool,), result)),
            ),
        ):
            report = mcp._target(installed("local", "tabnine"), "/managed")

        self.assertIs(report["ok"], True)
        stages = {stage["stage"]: stage["outcome"] for stage in report["stages"]}
        # Present and honest rather than absent or quietly green.
        self.assertEqual(stages["mcp-to-external-service"], "NOT CONFIGURED")

    def test_the_response_preview_is_absent_unless_it_was_asked_for(self) -> None:
        """Default non-disclosure: `--show-response` is the only way a response reaches output."""

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)
        tool = McpTool("read_identity", JsonObject((("type", "object"),)))
        result = McpCallResult(
            content=JsonArray((JsonObject((("type", "text"), ("text", "Ada"))),))
        )
        with (
            patch.object(mcp, "_configuration_values", return_value=({}, None)),
            patch.object(mcp, "_declaration", return_value=(declaration, None)),
            patch.object(
                mcp,
                "execute_stdio_smoke",
                return_value=Ok(DirectSmokeRun("2025-11-25", (tool,), result)),
            ),
        ):
            report = mcp._target(installed("local", "tabnine"), "/managed")

        self.assertNotIn("response", report)


class McpSmokeReportRouteTest(unittest.TestCase):
    """The harness stages when an operator report is supplied (D-368, §170.4)."""

    def _report(self, **over):
        from aart_cli.application.harness_report import HarnessAssessment, SmokeReportEntry

        fields = {
            "installation": "x",
            "called": True,
            "result": McpCallResult(
                content=JsonArray((JsonObject((("type", "text"), ("text", "Ada"))),))
            ),
            "assessment": HarnessAssessment("PASS", "It read the user.", None, "bounded"),
        }
        fields.update(over)
        return SmokeReportEntry(**fields)

    def _run(self, declaration, entry):
        tool = McpTool("read_identity", JsonObject((("type", "object"),)))
        result = McpCallResult(
            content=JsonArray((JsonObject((("type", "text"), ("text", "Ada"))),))
        )
        with (
            patch.object(mcp, "_configuration_values", return_value=({}, None)),
            patch.object(mcp, "_declaration", return_value=(declaration, None)),
            patch.object(
                mcp,
                "execute_stdio_smoke",
                return_value=Ok(DirectSmokeRun("2025-11-25", (tool,), result)),
            ),
        ):
            return mcp._target(installed("local", "claude"), "/managed", entry=entry)

    def test_a_reported_call_is_graded_by_the_direct_evaluator_and_labelled_attested(self) -> None:
        """The report transports the observation; the runner keeps the verdict (INV-251)."""

        declaration = SmokeDeclaration(
            "read_identity", JsonObject(()), 15, JsonObject((("text_contains", "Ada"),)), True
        )
        report = self._run(declaration, self._report())

        self.assertEqual(report["coverage"], "direct-and-attested")
        stages = {stage["stage"]: stage["outcome"] for stage in report["stages"]}
        self.assertEqual(stages["harness-to-mcp-to-external-service"], "PASS")
        self.assertEqual(stages["harness-to-model-provider"], "PASS")

    def test_a_reported_result_that_fails_the_declared_expectation_does_not_pass(self) -> None:
        """A report is not believed. An unfaithful or invented copy fails the declared check."""

        declaration = SmokeDeclaration(
            "read_identity", JsonObject(()), 15, JsonObject((("text_contains", "Grace"),)), True
        )
        report = self._run(declaration, self._report())

        stages = {stage["stage"]: stage["outcome"] for stage in report["stages"]}
        self.assertEqual(stages["harness-to-mcp-to-external-service"], "FAIL")
        self.assertIs(report["ok"], False)

    def test_a_report_that_says_the_tool_was_not_called_fails_the_harness_stage(self) -> None:
        """Both shapes of "not called" fail, including the self-contradictory one.

        A report saying `called: false` while carrying a result is not evidence of a call; it is a
        report that disagrees with itself, and grading its payload would take the model's word for
        something it just denied.
        """

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)
        for label, entry in (
            ("nothing carried", self._report(called=False, result=None)),
            ("contradicts itself", self._report(called=False)),
        ):
            with self.subTest(label=label):
                report = self._run(declaration, entry)
                stages = {stage["stage"]: stage["outcome"] for stage in report["stages"]}
                self.assertEqual(stages["harness-to-mcp-to-external-service"], "FAIL")


if __name__ == "__main__":
    unittest.main()
