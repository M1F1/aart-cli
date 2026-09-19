"""CP-25.12: screen 22 separates one artifact's group from the next (issue #12).

Each installed artifact is drawn as three lines -- its coordinate, its Configuration summary and
its Credentials summary -- and adjacent groups touched. A reader scanning the list had to count
indentation to tell whose Credentials line they were looking at, which is the one thing a grouped
list exists to make obvious.

Exactly one empty line, between groups only: no leading blank, no trailing blank, and nothing about
the empty state, the cursor, search, selection or Fast/Verbose changes.
"""

from __future__ import annotations

import datetime as dt
import unittest

from aart_cli.application.consumer_session import assemble_consumer_machine
from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    _reload,
    frame,
    render_user_inputs_area,
    screens_from,
)
from tests.consumer_session_test import OTHER, TOKEN, inspection, observed

TODAY = dt.date(2026, 9, 14)


def _screens(*names: str):
    """The screens a machine with these artifacts installed would show, each with one credential."""

    credentials = {"github": TOKEN, "jira": OTHER}
    machine = assemble_consumer_machine(
        tuple(inspection(name, credentials=(credentials[name],)) for name in names),
        credentials=tuple(observed(credentials[name]) for name in names),
        today=TODAY,
    )
    return screens_from(machine)


def _coordinate(name: str) -> str:
    return str(inspection(name).record.coordinate)


class TheGroupsAreSeparatedTest(unittest.TestCase):
    def test_nothing_installed_says_so_in_one_line(self) -> None:
        drawn = render_user_inputs_area(_screens(), (), "")

        self.assertEqual(drawn, ("No installed artifact has runtime inputs.",))

    def test_one_artifact_is_three_lines_with_no_blank_around_them(self) -> None:
        """A single group has nothing to be separated from, so it gains nothing."""

        coordinate = _coordinate("github")

        drawn = render_user_inputs_area(_screens("github"), (coordinate,), coordinate)

        self.assertEqual(
            drawn,
            (
                f"> {coordinate}",
                "    Configuration: none (0 harness file(s))",
                "    Credentials: \u2713 github-token  Ready  Used by 1",
            ),
        )

    def test_two_artifacts_are_parted_by_exactly_one_empty_line(self) -> None:
        first, second = _coordinate("github"), _coordinate("jira")
        rows = (first, second)

        drawn = render_user_inputs_area(_screens("github", "jira"), rows, first)

        self.assertEqual(
            drawn,
            (
                f"> {first}",
                "    Configuration: none (0 harness file(s))",
                "    Credentials: \u2713 github-token  Ready  Used by 1",
                "",
                f"  {second}",
                "    Configuration: none (0 harness file(s))",
                "    Credentials: \u2713 jira-token  Ready  Used by 1",
            ),
        )

    def test_the_separator_does_not_move_when_the_cursor_does(self) -> None:
        """The blank line belongs to the list's shape, not to whichever row is focused."""

        first, second = _coordinate("github"), _coordinate("jira")
        rows = (first, second)
        screens = _screens("github", "jira")

        on_first = render_user_inputs_area(screens, rows, first)
        on_second = render_user_inputs_area(screens, rows, second)

        self.assertEqual([index for index, line in enumerate(on_first) if not line], [3])
        self.assertEqual([index for index, line in enumerate(on_second) if not line], [3])
        self.assertTrue(on_second[4].startswith("> "))

    def test_the_separators_are_one_fewer_than_the_groups(self) -> None:
        rows = tuple(_coordinate(name) for name in ("github", "jira"))
        screens = _screens("github", "jira")

        drawn = render_user_inputs_area(screens, rows, rows[0])

        self.assertEqual(drawn.count(""), len(rows) - 1)
        self.assertTrue(drawn[0])
        self.assertTrue(drawn[-1])


class TheDrawnScreenKeepsItsShapeTest(unittest.TestCase):
    """Through the real frame, because a renderer's lines are not yet a screen."""

    def _state(self, screens) -> tuple[CanonicalScreenSource, ConsumerUiState]:
        source = CanonicalScreenSource(screens)
        state = _reload(
            source, ConsumerUiState(ConsumerSession(ConsumerScreen.CREDENTIALS)), entering=True
        )
        return source, state

    def test_the_rows_are_still_one_per_artifact(self) -> None:
        """A separator is drawn, never selectable: the cursor still lands on artifacts only."""

        source, state = self._state(_screens("github", "jira"))

        self.assertEqual(state.rows, tuple(_coordinate(name) for name in ("github", "jira")))

    def test_the_frame_neither_opens_nor_closes_on_a_blank_line(self) -> None:
        source, state = self._state(_screens("github", "jira"))

        drawn = frame(source, state)

        self.assertTrue(drawn[0].strip())
        self.assertTrue(drawn[-1].strip())
        self.assertNotIn("\n\n\n", "\n".join(drawn))


if __name__ == "__main__":
    unittest.main()
