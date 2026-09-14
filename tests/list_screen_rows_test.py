"""CP-23 task 14: list screens draw their rows with the cursor, and describe them only in Verbose.

The audit found Activity and Doctor drawing lists with no cursor although Enter and `r` act on the
row under it, User variables and credentials naming itself again under the trail, and its artifact
view putting prose and every file path among its rows.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from agent_artifacts.tui_consumer import CanonicalScreenSource, _reload, compose_frame
from tests import user_inputs_area_test
from tests.consumer_shell_test import screens
from tests.frame_contract import frame_violations, toggle_violations


def _verbose(state: ConsumerUiState) -> ConsumerUiState:
    toggled, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE))
    return toggled


def _every_cursor(source, state):
    for cursor in range(len(state.rows)):
        at = replace(state, cursor=cursor)
        yield at
        yield _verbose(at)


class ActivityRowsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CanonicalScreenSource(screens())
        state = ConsumerUiState(ConsumerSession(ConsumerScreen.ACTIVITY), workspace="/lab")
        self.state = _reload(self.source, state, entering=True)

    def test_each_entry_is_a_row_under_its_day_with_the_cursor_on_one(self) -> None:
        actions = [line for line in self.source.actions(self.state) if line.strip()]

        self.assertEqual(len([line for line in actions if line.startswith("> ")]), 1)
        self.assertNotIn("Activity", actions)
        for drawn in _every_cursor(self.source, self.state):
            with self.subTest(cursor=drawn.cursor, profile=drawn.session.profile):
                self.assertEqual(frame_violations(self.source, drawn), ())
                self.assertEqual(toggle_violations(self.source, drawn), ())

    def test_the_review_identity_describes_the_entry_under_the_cursor_in_verbose(self) -> None:
        entry = self.source.screens.activity.entries[1]
        at = _verbose(replace(self.state, cursor=self.state.rows.index(entry.recorded_at)))

        described = compose_frame(self.source, at).described

        self.assertIn(f"Review identity: {entry.review_digest}", described)
        self.assertEqual(
            self.source.actions(at), self.source.actions(replace(at, session=self.state.session))
        )


class UserInputRowsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source, self.coordinate = user_inputs_area_test.UserInputsAreaProjectionTest._source(
            None
        )  # type: ignore[arg-type]

    def _at(self, screen: ConsumerScreen) -> ConsumerUiState:
        state = ConsumerUiState(
            ConsumerSession(screen),
            settings=ConsumerSettings(),
            focus=self.coordinate,
            user_inputs_artifact=self.coordinate,
        )
        return _reload(self.source, state, entering=True)

    def test_both_views_keep_the_contract_on_every_row_in_both_profiles(self) -> None:
        for screen in (ConsumerScreen.CREDENTIALS, ConsumerScreen.USER_INPUT_DETAILS):
            state = self._at(screen)
            for drawn in _every_cursor(self.source, state):
                with self.subTest(screen=screen, cursor=drawn.cursor):
                    self.assertEqual(frame_violations(self.source, drawn), ())

    def test_a_file_path_describes_the_configuration_row_rather_than_widening_it(self) -> None:
        state = self._at(ConsumerScreen.USER_INPUT_DETAILS)
        verbose = _verbose(state)
        blocks = compose_frame(self.source, verbose)

        self.assertIn("claude: /opt/agents/mcp/github/config/claude.conf", blocks.described)
        self.assertEqual(self.source.actions(verbose), self.source.actions(state))
        self.assertNotIn("/opt/agents", "\n".join(self.source.actions(verbose)))
        self.assertEqual(blocks.status[0], f"- {self.coordinate}")


if __name__ == "__main__":
    unittest.main()
