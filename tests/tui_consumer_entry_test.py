"""The default terminal route is the canonical consumer application (B-025).

The three composition tests below were written against `tui._canonical_consumer_source`, a
wrapper that read the machine and handed back only the screens. It is gone with the rest of the
wizard surface; the same reads now happen once inside `_canonical_consumer_actions`, whose
`source()` is what the shell draws, so that is what they drive.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import sys
import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_session import assemble_consumer_machine
from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import ConsumerSettings
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import (
    DELIVERY_TARGETS,
    HOOK_TARGETS,
    MCP_TARGETS,
    MEMORY_TARGETS,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.tui_consumer import (
    ConsumerOffers,
    MarketplaceEntry,
    run_consumer_shell,
)
from tests.marketplace_fixtures import effective_configuration
from tests.tui_marketplace_test import _catalog

TODAY = dt.date(2026, 8, 31)


def _row():
    from agent_artifacts.tui_marketplace import MarketplaceTarget, project_marketplace_rows

    rows = project_marketplace_rows(
        _catalog(), MarketplaceTarget(("claude",), "darwin", "project", "copy")
    )
    return rows[0]


class CanonicalConsumerEntryTest(unittest.TestCase):
    def test_curses_shortens_the_escape_prefix_delay(self) -> None:
        """The curses default waits about a second for a possible escape sequence (B-078)."""

        actions = mock.Mock()
        actions.settings = ConsumerSettings()
        finished = ConsumerUiState(exited=True)
        with (
            mock.patch("curses.set_escdelay") as set_delay,
            mock.patch("curses.wrapper", side_effect=lambda callback: callback(mock.Mock())),
            mock.patch.object(tui, "run_consumer_shell", return_value=finished),
        ):
            returned = tui.run_consumer(actions)

        self.assertIs(returned, finished)
        set_delay.assert_called_once()
        self.assertLessEqual(set_delay.call_args.args[0], 100)

    def test_curses_keeps_the_navigation_legend_visible_when_the_body_is_tall(self) -> None:
        """The legend is chrome, not body text that scrolling or clipping may hide (B-077)."""

        class _Screen:
            def __init__(self) -> None:
                self.written: list[tuple[int, int, str]] = []

            def clear(self) -> None:
                self.written.clear()

            def getmaxyx(self) -> tuple[int, int]:
                return 6, 80

            def addstr(self, row: int, column: int, value: str) -> None:
                self.written.append((row, column, value))

            def refresh(self) -> None:
                pass

        screen = _Screen()
        terminal = tui._CursesTerminal(screen)

        terminal.draw(("heading", "one", "two", "three", "four", "five", "navigation legend"))

        self.assertEqual(screen.written[-1], (4, 0, "navigation legend"))

    def test_a_terminal_gets_the_canonical_application_and_nothing_else(self) -> None:
        """B-025: the default TTY route is the canonical consumer application.

        The legacy wizard it was once chosen over is gone (D-113, D-116); what this holds now is
        that a terminal that can host curses runs the application and does not also degrade.
        """

        actions = mock.Mock()
        with (
            mock.patch.object(tui, "_curses_supported", return_value=True),
            mock.patch.object(tui, "_canonical_consumer_actions", return_value=Ok(actions)),
            mock.patch.object(tui, "run_consumer", return_value=None) as canonical,
            mock.patch.object(tui, "run_consumer_text", return_value=None) as degradation,
        ):
            code = tui.run(project="/work/project", user_home="/users/alice")

        self.assertEqual(code, 0)
        canonical.assert_called_once_with(actions)
        degradation.assert_not_called()

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
                tui,
                "_canonical_consumer_configuration",
                return_value=Ok(effective_configuration(())),
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

    def test_a_machine_that_cannot_be_read_refuses_rather_than_opening_anything(self) -> None:
        """An unreadable machine is not an empty one, and degrading would read the same state."""

        output = io.StringIO()
        refusal = Err((Diagnostic(DiagnosticCode("state-unreadable"), Severity.ERROR, "no"),))
        with (
            mock.patch.object(tui, "_curses_supported", return_value=True),
            mock.patch.object(tui, "_canonical_consumer_actions", return_value=refusal),
            mock.patch.object(tui, "run_consumer") as canonical,
            mock.patch.object(tui, "run_consumer_text", return_value=None) as degradation,
            contextlib.redirect_stdout(output),
        ):
            code = tui.run(project="/work/project", user_home="/users/alice")

        self.assertEqual(code, 2)
        canonical.assert_not_called()
        degradation.assert_not_called()
        self.assertIn("state-unreadable", output.getvalue())

    def test_the_machine_reader_receives_the_managed_state_and_harness_scope(self) -> None:
        machine = assemble_consumer_machine((), today=TODAY)
        with (
            mock.patch.object(tui, "read_consumer_machine", return_value=Ok(machine)) as read,
            mock.patch.object(
                tui,
                "_canonical_consumer_configuration",
                return_value=Ok(effective_configuration(())),
            ),
            mock.patch.object(tui, "read_consumer_offers", return_value=Ok(ConsumerOffers())),
        ):
            composed = tui._canonical_consumer_actions(
                project="/work/project",
                user_home="/users/alice",
                today=TODAY,
            )

        self.assertIsInstance(composed, Ok, composed)
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
            mock.patch.object(
                tui,
                "_canonical_consumer_configuration",
                return_value=Ok(effective_configuration(())),
            ),
            mock.patch.object(tui, "read_consumer_offers", return_value=Ok(offers)) as read,
        ):
            composed = tui._canonical_consumer_actions(
                project="/work/project",
                user_home="/users/alice",
                today=TODAY,
            )

        self.assertIsInstance(composed, Ok, composed)
        self.assertEqual(composed.value.source().screens.marketplace, offers.artifacts)
        # Measured harnesses only: an offer marked compatible with one nobody measured is a claim
        # AART cannot keep. Every measured table counts, not only the MCP one -- a harness this
        # machine can deliver Skills and instructions to is one it accepts, whether or not it also
        # starts a server (B-086).
        measured = {harness for harness, _ in MCP_TARGETS}
        measured.update(harness for harness, _ in MEMORY_TARGETS)
        measured.update(harness for harness, _ in HOOK_TARGETS)
        measured.update(harness for harness, _, _ in DELIVERY_TARGETS)
        self.assertEqual(read.call_args.kwargs["target"].profiles, tuple(sorted(measured)))

    def test_an_unreadable_configuration_refuses_rather_than_offering_nothing(self) -> None:
        """An empty Marketplace and an unreadable one are different facts.

        ERR03, carried from the retired wizard loader: the refusal that comes back is the one the
        boundary raised, not a rewrapping of it. A composition that replaced a typed diagnostic
        with one of its own would hide which read failed from the person who has to fix it.
        """

        machine = assemble_consumer_machine((), today=TODAY)
        refusal = Err(
            (Diagnostic(DiagnosticCode("configuration-unreadable"), Severity.ERROR, "no"),)
        )
        with (
            mock.patch.object(tui, "read_consumer_machine", return_value=Ok(machine)),
            mock.patch.object(
                tui,
                "_canonical_consumer_configuration",
                return_value=Ok(effective_configuration(())),
            ),
            mock.patch.object(tui, "read_consumer_offers", return_value=refusal),
        ):
            composed = tui._canonical_consumer_actions(
                project="/work/project",
                user_home="/users/alice",
                today=TODAY,
            )

        self.assertIs(composed, refusal)


if __name__ == "__main__":
    unittest.main()
