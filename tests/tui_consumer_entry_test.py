"""The canonical machine source is ready without cutting over before actions are live."""

from __future__ import annotations

import datetime as dt
import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_session import assemble_consumer_machine
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import MCP_TARGETS
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.tui_consumer import ConsumerOffers, MarketplaceEntry
from tests.tui_marketplace_test import _catalog

TODAY = dt.date(2026, 8, 31)


def _row():
    from agent_artifacts.tui_marketplace import MarketplaceTarget, project_marketplace_rows

    rows = project_marketplace_rows(
        _catalog(), MarketplaceTarget(("claude",), "darwin", "project", "copy")
    )
    return rows[0]


class CanonicalConsumerEntryTest(unittest.TestCase):
    def test_the_legacy_entry_stays_until_the_canonical_shell_can_execute_actions(self) -> None:
        with (
            mock.patch.object(tui, "_curses_supported", return_value=True),
            mock.patch.object(tui, "_runtime_source_stage_context", return_value=Ok(mock.Mock())),
            mock.patch.object(tui, "run_consumer") as canonical,
            mock.patch.object(tui, "_run_curses", return_value=0) as legacy_curses,
        ):
            code = tui.run(project="/work/project", user_home="/users/alice")

        self.assertEqual(code, 0)
        canonical.assert_not_called()
        legacy_curses.assert_called_once()

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
        self.assertEqual(arguments["credential_providers"][0].provider, "macos-keychain")

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
