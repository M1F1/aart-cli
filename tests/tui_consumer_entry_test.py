"""The default terminal route is the canonical consumer application (B-025)."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import sys
import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_session import assemble_consumer_machine
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import MCP_TARGETS
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.tui_consumer import (
    ConsumerOffers,
    MarketplaceEntry,
    run_consumer_shell,
)
from tests.tui_marketplace_test import _catalog

TODAY = dt.date(2026, 8, 31)


def _row():
    from agent_artifacts.tui_marketplace import MarketplaceTarget, project_marketplace_rows

    rows = project_marketplace_rows(
        _catalog(), MarketplaceTarget(("claude",), "darwin", "project", "copy")
    )
    return rows[0]


class CanonicalConsumerEntryTest(unittest.TestCase):
    def test_a_terminal_gets_the_canonical_application_and_not_the_legacy_wizard(self) -> None:
        """B-025: the default TTY route is the canonical consumer application."""

        actions = mock.Mock()
        with (
            mock.patch.object(tui, "_curses_supported", return_value=True),
            mock.patch.object(tui, "_canonical_consumer_actions", return_value=Ok(actions)),
            mock.patch.object(tui, "run_consumer", return_value=None) as canonical,
            mock.patch.object(tui, "_run_curses", return_value=0) as legacy_curses,
            mock.patch.object(tui, "_run_text", return_value=0) as legacy_text,
            mock.patch.object(tui, "_runtime_source_stage_context") as legacy_composition,
        ):
            code = tui.run(project="/work/project", user_home="/users/alice")

        self.assertEqual(code, 0)
        canonical.assert_called_once_with(actions)
        legacy_curses.assert_not_called()
        legacy_text.assert_not_called()
        # Nothing of the wizard is even composed: composing it would open the same local state a
        # second time, and a failure would then be reported by whichever half opened it first.
        legacy_composition.assert_not_called()

    def test_the_application_is_run_through_its_own_injected_action_handler(self) -> None:
        """A shell without a handler refuses every action, so the two are composed together."""

        machine = assemble_consumer_machine((), today=TODAY)
        drawn: list = []

        class _Terminal:
            def draw(self, lines) -> None:
                drawn.append(lines)

            def key(self) -> int:
                return ord("q")

        with (
            mock.patch.object(tui, "read_consumer_machine", return_value=Ok(machine)),
            mock.patch.object(tui, "read_consumer_offers", return_value=Ok(ConsumerOffers())),
            mock.patch.object(
                tui, "_canonical_consumer_configuration", return_value=Ok(mock.Mock())
            ),
        ):
            composed = tui._canonical_consumer_actions(
                project="/work/project", user_home="/users/alice", today=TODAY
            )
            self.assertIsInstance(composed, Ok, composed)
            finished = run_consumer_shell(
                composed.value.source(), _Terminal(), action_handler=composed.value
            )

        self.assertTrue(finished.exited)
        self.assertTrue(drawn)

    def test_a_machine_that_cannot_be_read_refuses_rather_than_opening_the_wizard(self) -> None:
        """An unreadable machine is not an empty one, and the wizard would read the same state."""

        output = io.StringIO()
        refusal = Err((Diagnostic(DiagnosticCode("state-unreadable"), Severity.ERROR, "no"),))
        with (
            mock.patch.object(tui, "_curses_supported", return_value=True),
            mock.patch.object(tui, "_canonical_consumer_actions", return_value=refusal),
            mock.patch.object(tui, "_run_text", return_value=0) as legacy_text,
            contextlib.redirect_stdout(output),
        ):
            code = tui.run(project="/work/project", user_home="/users/alice")

        self.assertEqual(code, 2)
        legacy_text.assert_not_called()
        self.assertIn("state-unreadable", output.getvalue())

    def test_the_machine_reader_receives_the_managed_state_and_harness_scope(self) -> None:
        machine = assemble_consumer_machine((), today=TODAY)
        with mock.patch.object(tui, "read_consumer_machine", return_value=Ok(machine)) as read:
            loaded = tui._canonical_consumer_source(
                project="/work/project",
                user_home="/users/alice",
                today=TODAY,
            )

        self.assertIsInstance(loaded, Ok)
        arguments = read.call_args.kwargs
        self.assertEqual(arguments["harness_root"], "/work/project")
        self.assertTrue(arguments["state_root"].endswith("agent-artifacts/state"))
        self.assertEqual(arguments["today"], TODAY)
        # The adapters the machine is measured through are the ones the actions can act on.
        self.assertEqual(
            tuple(item.provider for item in arguments["credential_providers"]),
            ("macos-keychain",) if sys.platform == "darwin" else (),
        )

    def test_the_composed_source_carries_the_configured_marketplace(self) -> None:
        """The offers are read once, beside the machine, not derived inside a draw (D-051)."""

        machine = assemble_consumer_machine((), today=TODAY)
        offers = ConsumerOffers((MarketplaceEntry(_row()),))
        with (
            mock.patch.object(tui, "read_consumer_machine", return_value=Ok(machine)),
            mock.patch.object(tui, "read_consumer_offers", return_value=Ok(offers)) as read,
        ):
            loaded = tui._canonical_consumer_source(
                project="/work/project",
                user_home="/users/alice",
                today=TODAY,
            )

        self.assertIsInstance(loaded, Ok)
        self.assertEqual(loaded.value.screens.marketplace, offers.artifacts)
        # Measured harnesses only: an offer marked compatible with one nobody measured is a claim
        # AART cannot keep.
        self.assertEqual(
            read.call_args.kwargs["target"].profiles,
            tuple(sorted({harness for harness, _ in MCP_TARGETS})),
        )

    def test_an_unreadable_configuration_refuses_rather_than_offering_nothing(self) -> None:
        """An empty Marketplace and an unreadable one are different facts."""

        machine = assemble_consumer_machine((), today=TODAY)
        refusal = Err(
            (Diagnostic(DiagnosticCode("configuration-unreadable"), Severity.ERROR, "no"),)
        )
        with (
            mock.patch.object(tui, "read_consumer_machine", return_value=Ok(machine)),
            mock.patch.object(tui, "read_consumer_offers", return_value=refusal),
        ):
            loaded = tui._canonical_consumer_source(
                project="/work/project",
                user_home="/users/alice",
                today=TODAY,
            )

        self.assertIsInstance(loaded, Err)


if __name__ == "__main__":
    unittest.main()
