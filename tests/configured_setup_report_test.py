"""Configured setup refusal and usage-report consent remain explicit at both front ends.

The install route now reaches the setup engine, but omitting effect approval at the CLI or choosing
``n`` in the shell still applies no setup effect and keeps the declaration visible as pending.
Usage reporting is a second consent boundary: the terminal defaults to no, previews exact redacted
bytes before a provider is called, and treats provider failure as advisory.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import sys
import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession
from agent_artifacts.configuration.model import ReportingMode
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    SourceAlias,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.reporting.application import ReportingApplicationService
from agent_artifacts.reporting.model import ReportingDestination, ReportingSubmission
from agent_artifacts.tui_consumer import run_consumer_shell
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AuthoredSetup
from tests.configured_setup_gap_test import AUTHORED, CONFIGURED, COORDINATE, RECIPE
from tests.consumer_shell_test import ENTER, SPACE, FakeTerminal

TODAY = dt.date(2026, 9, 1)


def _declaring_setup():
    return _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE))


class ConfiguredInstallCommandReportTest(unittest.TestCase):
    def test_the_install_names_the_setup_it_did_not_run(self) -> None:
        with _declaring_setup() as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertEqual(
                payload["pending_setup"],
                [
                    {
                        "coordinate": "company/skill/code-review@1.2.0",
                        "object_digest": payload["pending_setup"][0]["object_digest"],
                        "recipe": "setup/installer.json",
                        "platforms": ["darwin"],
                        "manual": "SETUP.md",
                    }
                ],
            )
            # Declining setup remains an explicit, recoverable outcome.
            self.assertFalse((env.project / CONFIGURED).exists())

    def test_usage_reporting_defaults_to_no_on_the_shell_terminal_port(self) -> None:
        calls: list[bytes] = []

        def opened(plan):
            calls.append(plan.payload)
            return Ok(ReportingSubmission("browser-opened"))

        reporting = ReportingApplicationService(
            ReportingDestination(ReportingMode.PROMPT, "github.com", "org/registry"),
            opened,
            lambda _plan: self.fail("automatic provider used in prompt mode"),
        )
        with _declaring_setup() as env:
            with (
                mock.patch.dict(os.environ, env.xdg, clear=False),
                mock.patch.object(tui, "load_local_reporting_service", return_value=Ok(reporting)),
            ):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project), user_home=str(env.home), today=TODAY
                )
            assert isinstance(composed, Ok)
            terminal = FakeTerminal(
                SPACE,
                ord("i"),
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                ord("y"),
                ENTER,
            )

            with mock.patch.dict(os.environ, env.xdg, clear=False):
                finished = run_consumer_shell(
                    composed.value.source(),
                    terminal,
                    state=ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE)),
                    action_handler=composed.value,
                    settings_writer=composed.value.save_settings,
                )

            self.assertEqual(finished.session.screen, ConsumerScreen.SUCCESS)
            self.assertEqual(calls, [])
            self.assertFalse(
                any(
                    "Exact redacted usage report payload" in "\n".join(frame)
                    for frame in terminal.frames
                )
            )

    @unittest.skipUnless(
        sys.platform == "darwin",
        "the setup engine accepts only darwin recipes (setup.py:562), so applying one elsewhere is "
        "refused for the platform before the effect this asserts on is reached",
    )
    def test_shell_previews_exact_payload_and_reporting_failure_is_advisory(self) -> None:
        called_at_frame: list[int] = []
        failure = Err(
            (
                Diagnostic(
                    DiagnosticCode("reporting-provider-failed"),
                    Severity.ERROR,
                    "provider unavailable",
                ),
            )
        )
        with _declaring_setup() as env:
            terminal = FakeTerminal(
                SPACE,
                ord("i"),
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                ord("y"),
                ord("y"),
                ord("y"),
            )

            def unavailable(_plan):
                called_at_frame.append(len(terminal.frames))
                return failure

            reporting = ReportingApplicationService(
                ReportingDestination(ReportingMode.PROMPT, "github.com", "org/registry"),
                unavailable,
                lambda _plan: self.fail("automatic provider used in prompt mode"),
            )
            with (
                mock.patch.dict(os.environ, env.xdg, clear=False),
                mock.patch.object(tui, "load_local_reporting_service", return_value=Ok(reporting)),
            ):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project), user_home=str(env.home), today=TODAY
                )
            assert isinstance(composed, Ok)

            with mock.patch.dict(os.environ, env.xdg, clear=False):
                finished = run_consumer_shell(
                    composed.value.source(),
                    terminal,
                    state=ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE)),
                    action_handler=composed.value,
                    settings_writer=composed.value.save_settings,
                )

            payload_frames = [
                index
                for index, frame in enumerate(terminal.frames)
                if '"report_type":"aart-usage-session"' in "\n".join(frame)
            ]
            self.assertTrue(payload_frames)
            self.assertEqual(len(called_at_frame), 1)
            self.assertLess(payload_frames[0], called_at_frame[0])
            self.assertTrue(
                any("outcome is unchanged" in "\n".join(frame) for frame in terminal.frames)
            )
            self.assertEqual(finished.session.screen, ConsumerScreen.SUCCESS)
            self.assertTrue((env.project / CONFIGURED).exists())

    def test_the_named_object_is_the_one_the_receipt_recorded(self) -> None:
        """The report is derived from the durable record, not from what the action believed.

        An install that reported a setup declaration read off the plan it just executed would be
        reporting its own intention back to itself. What is asserted here is that the object the
        report names is the object the receipt on disk names -- so the report is a statement about
        the machine, and it stays true for a reader that arrives afterwards.
        """

        with _declaring_setup() as env:
            _, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            store = LocalReceiptStore(str(pathlib.Path(env.paths.data_root) / "state"))
            record = store.record(
                ArtifactCoordinate(
                    SourceAlias("company"), ArtifactIdentity("skill", "code-review"), "1.2.0"
                )
            )
            self.assertIsInstance(record, Ok, getattr(record, "diagnostics", ()))
            assert isinstance(record, Ok)

            self.assertEqual(
                payload["pending_setup"][0]["object_digest"],
                str(record.value.receipt.object_digest),
            )

    def test_an_artifact_that_declares_no_setup_is_not_reported_as_pending(self) -> None:
        """The key is absent, not an empty list every install now carries."""

        with _environment() as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertNotIn("pending_setup", payload)

    def test_the_text_output_names_it_too(self) -> None:
        with _declaring_setup() as env:
            code, text = env.run_text(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, text)
            self.assertIn("setup", text.lower())
            self.assertIn("company/skill/code-review@1.2.0", text)


class ConsumerShellReportTest(unittest.TestCase):
    def test_the_shell_names_the_setup_that_did_not_run(self) -> None:
        with _declaring_setup() as env:
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project), user_home=str(env.home), today=TODAY
                )
            self.assertIsInstance(composed, Ok, getattr(composed, "diagnostics", ()))
            assert isinstance(composed, Ok)
            handler = composed.value
            terminal = FakeTerminal(SPACE, ord("i"), ENTER, ENTER, ENTER, ENTER, ord("n"))

            with mock.patch.dict(os.environ, env.xdg, clear=False):
                finished = run_consumer_shell(
                    handler.source(),
                    terminal,
                    state=ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE)),
                    action_handler=handler,
                    settings_writer=handler.save_settings,
                )

            self.assertEqual(finished.session.screen, ConsumerScreen.SUCCESS)
            self.assertTrue(
                any(any("etup" in line for line in frame) for frame in terminal.frames),
                "no drawn frame says the installed Skill is still unconfigured",
            )
            self.assertFalse((env.project / CONFIGURED).exists())


if __name__ == "__main__":
    unittest.main()
