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
                (
                    JsonObject(
                        (("type", "text"), ("text", "tenant-private\n" + "x" * 70000))
                    ),
                )
            )
        )
        preview = mcp._response_preview(result, sensitive=("tenant-private",))
        self.assertNotIn("tenant-private", preview["content"])
        self.assertIn("<redacted>", preview["content"])
        self.assertTrue(preview["truncated"])
        self.assertLessEqual(len(preview["content"].encode("utf-8")), 65536)

    def test_tabnine_runs_the_direct_route_without_starting_its_harness(self) -> None:
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
            patch.object(mcp, "run_harness_smoke") as harness,
        ):
            report = mcp._target(
                installed("local", "tabnine"), "/managed", show_response=True
            )

        harness.assert_not_called()
        self.assertEqual(report["coverage"], "direct")
        stages = {stage["stage"]: stage["outcome"] for stage in report["stages"]}
        self.assertEqual(stages["mcp-startup-and-protocol"], "PASS")
        self.assertEqual(stages["harness-to-model-provider"], "NOT RUN")
        self.assertIn("response", report)


if __name__ == "__main__":
    unittest.main()
