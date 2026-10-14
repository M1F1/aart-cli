from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from aart_cli import cli
from aart_cli.application.mcp_smoke import McpCallResult, McpTool, SmokeDeclaration
from aart_cli.domain.result import Ok
from aart_cli.io import installed_smoke
from aart_cli.io.mcp_smoke import DirectSmokeRun
from aart_cli.protocol.json import JsonArray, JsonObject
from tests.mcp_smoke_selection_test import installed


def _tool() -> McpTool:
    return McpTool("read_identity", JsonObject((("type", "object"),)))


def _text(value: str) -> McpCallResult:
    return McpCallResult(content=JsonArray((JsonObject((("type", "text"), ("text", value))),)))


@contextlib.contextmanager
def _installed_run(declaration, result, *, config=None, config_failure=None):
    with (
        patch.object(
            installed_smoke,
            "_configuration_values",
            return_value=(config or {}, config_failure),
        ),
        patch.object(installed_smoke, "_declaration", return_value=(declaration, None)),
        patch.object(
            installed_smoke,
            "execute_stdio_smoke",
            return_value=Ok(DirectSmokeRun("2025-11-25", (_tool(),), result)),
        ) as started,
    ):
        yield started


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

    def test_the_harness_route_is_gone(self) -> None:
        """D-378: no prompt, no report to grade, and no `mcp report` action to check one."""

        for argv in (
            ["mcp", "test", "--all", "--harness", "claude", "--prompt"],
            ["mcp", "test", "--all", "--harness", "claude", "--report", "out.json"],
            ["mcp", "report", "out.json"],
        ):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cli.build_parser().parse_args(argv)

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
        with _installed_run(
            declaration, _text("raw-private-response"), config={"tenant": "private-value"}
        ):
            report = installed_smoke.smoke_installation(installed("local", "opencode"), "/managed")

        rendered = repr(report)
        self.assertNotIn("private-value", rendered)
        self.assertNotIn("raw-private-response", rendered)

    def test_show_response_is_explicit_bounded_and_redacts_known_configuration(self) -> None:
        preview = installed_smoke._response_preview(
            _text("tenant-private\n" + "x" * 70000), sensitive=("tenant-private",)
        )
        self.assertNotIn("tenant-private", preview["content"])
        self.assertIn("<redacted>", preview["content"])
        self.assertTrue(preview["truncated"])
        self.assertLessEqual(len(preview["content"].encode("utf-8")), 65536)

    def test_there_are_exactly_two_stages_and_both_passing_is_success(self) -> None:
        """§170.2, INV-250: installation then protocol, and nothing reported beyond them."""

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)
        with _installed_run(declaration, _text("Ada")):
            report = installed_smoke.smoke_installation(installed("local", "tabnine"), "/managed")

        self.assertEqual(
            [(stage.stage.value, stage.outcome.value) for stage in report.stages],
            [("installation-configuration", "PASS"), ("mcp-startup-and-protocol", "PASS")],
        )
        self.assertIs(report.ok, True)

    def test_a_blocked_installation_leaves_the_protocol_stage_not_run(self) -> None:
        """The server is never started when its installation is not usable."""

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)
        with _installed_run(
            declaration, _text("Ada"), config_failure="the installed launcher is absent"
        ) as started:
            report = installed_smoke.smoke_installation(installed("local", "tabnine"), "/managed")

        started.assert_not_called()
        self.assertEqual([stage.outcome.value for stage in report.stages], ["BLOCKED", "NOT RUN"])
        self.assertIn("installation-configuration", report.stages[1].reason)
        self.assertIs(report.ok, False)

    def test_an_mcp_error_result_fails_the_protocol_stage(self) -> None:
        """The one way a protocol pass can say something about the service (§170.2)."""

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)
        with _installed_run(declaration, McpCallResult(content=JsonArray(()), is_error=True)):
            report = installed_smoke.smoke_installation(installed("local", "claude"), "/managed")

        self.assertEqual(report.stages[1].outcome.value, "FAIL")
        self.assertIs(report.ok, False)

    def test_the_response_preview_is_present_only_when_asked_for(self) -> None:
        """Default non-disclosure: `--show-response` is the only way a response reaches output."""

        declaration = SmokeDeclaration("read_identity", JsonObject(()), 15)
        record = installed("local", "tabnine")
        with _installed_run(declaration, _text("Ada")):
            hidden = installed_smoke.smoke_installation(record, "/managed")
            shown = installed_smoke.smoke_installation(record, "/managed", show_response=True)

        self.assertIsNone(hidden.response)
        self.assertIsNotNone(shown.response)


if __name__ == "__main__":
    unittest.main()
