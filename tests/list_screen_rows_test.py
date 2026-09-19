"""CP-23 task 14: list screens draw their rows with the cursor, and describe them only in Verbose.

The audit found Activity and Doctor drawing lists with no cursor although Enter and `r` act on the
row under it, User variables and credentials naming itself again under the trail, and its artifact
view putting prose and every file path among its rows. A Collection preview drew its coordinate,
counts and warning where its rows belong and its members nowhere a cursor could stand, while Space
ticked them; Verbose listed them a second time.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from aart_cli.tui_consumer import CanonicalScreenSource, _reload, compose_frame
from tests import user_inputs_area_test
from tests.consumer_marketplace_shell_test import COLLECTION, drive
from tests.consumer_marketplace_shell_test import screens as marketplace_screens
from tests.consumer_shell_test import ENTER, SPACE, UP, _at, screens
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


class SettingsRowsTest(unittest.TestCase):
    def test_v_changes_only_the_row_that_shows_the_detail_level(self) -> None:
        source = CanonicalScreenSource(screens())
        state = _reload(source, ConsumerUiState(ConsumerSession(ConsumerScreen.SETTINGS)))
        for drawn in _every_cursor(source, state):
            with self.subTest(cursor=drawn.cursor, profile=drawn.session.profile):
                self.assertEqual(frame_violations(source, drawn), ())
                self.assertEqual(toggle_violations(source, drawn), ())
        changed = set(source.actions(_verbose(state))) - set(source.actions(state))

        self.assertEqual(changed, {"> Detail level: Verbose"})


class CollectionRowsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CanonicalScreenSource(marketplace_screens())
        # The shell hands back the state it quit from; these are the screens it quit on.
        preview, _ = drive(UP, ENTER, state=_at(ConsumerScreen.MARKETPLACE))
        custom, _ = drive(UP, ENTER, ENTER, SPACE, state=_at(ConsumerScreen.MARKETPLACE))
        self.preview = replace(preview, exited=False)
        self.custom = replace(custom, exited=False)

    def test_the_members_are_the_rows_ticked_as_the_selection_makes_them(self) -> None:
        self.assertEqual(
            self.source.actions(self.custom),
            ("> [ ] company/mcp/database@1.0.0", "  [x] company/skill/review@1.0.0"),
        )
        for state in (self.preview, self.custom):
            for drawn in _every_cursor(self.source, state):
                with self.subTest(screen=drawn.session.screen, cursor=drawn.cursor):
                    self.assertEqual(frame_violations(self.source, drawn), ())
                    self.assertEqual(toggle_violations(self.source, drawn), ())

    def test_the_details_summarize_the_collection_rather_than_list_its_members(self) -> None:
        """§161.4: counts and prerequisites; the members are rows only in the Contents."""

        self.assertEqual(self.preview.rows, ())
        for drawn in (self.preview, _verbose(self.preview)):
            self.assertEqual(frame_violations(self.source, drawn), ())
        fast = compose_frame(self.source, self.preview)
        verbose = compose_frame(self.source, _verbose(self.preview))
        self.assertIn("- 2 / 2 selected", fast.status)
        self.assertNotIn("- 2 selected", fast.status)
        self.assertNotIn("company/mcp/database@1.0.0", "\n".join(fast.status))
        self.assertIn("company/mcp/database@1.0.0", "\n".join(verbose.status))

    def test_what_the_selection_amounts_to_is_the_state_of_the_view(self) -> None:
        status = self.source.status(self.custom)

        self.assertEqual(status[0], str(COLLECTION))
        self.assertIn("1 / 2 selected", status)
        self.assertIn("Warning: Custom selection", status)
        self.assertFalse(any("Selection identity" in line for line in status))
        verbose = self.source.status(_verbose(self.custom))
        identity = self.source.collection(str(COLLECTION), self.custom.selection).semantic_identity
        self.assertIn(f"Selection identity: {identity}", verbose)
        self.assertNotIn("Contents:", verbose)

    def test_verbose_describes_the_member_under_the_cursor(self) -> None:
        at = _verbose(replace(self.custom, cursor=1))

        described = compose_frame(self.source, at).described

        self.assertEqual(described[0].split(), ["Artifact", "review"])


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
