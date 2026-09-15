"""CP-13 — the keyboard, end to end: real key codes through the reducer onto canonical views.

Nothing here fakes an event.  Each test types the codes a terminal would deliver, names them the
way the curses shell does, and asserts against the same view models the renderers draw, so a
binding cannot drift from what a person actually experiences.
"""

from __future__ import annotations

import datetime as dt
import unittest

from agent_artifacts.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ActivityRecord,
    ConsumerScreen,
    PresentationProfile,
    project_activity,
)
from agent_artifacts.tui_consumer import key_name, render_activity
from tests.consumer_activity_test import lifecycle_outcome

#: The codes a terminal delivers for the keys §161.1 makes global.
ESCAPE, ENTER, BACKSPACE = 27, 10, 263
UP, DOWN = 259, 258
SPACE, SLASH, QUESTION = 32, ord("/"), ord("?")

ROWS = ("mcp/github", "mcp/jira", "skill/review")


def press(
    state: ConsumerUiState,
    *codes: int,
    detail: ConsumerScreen | None = None,
) -> ConsumerUiState:
    """Type these key codes, the way the curses shell would deliver them."""

    for code in codes:
        name = key_name(code)
        if not name:
            continue
        event = key_event(name, state, detail=detail)
        if event is None:
            continue
        state, _ = reduce_consumer_ui(state, event)
    return state


def at(screen: ConsumerScreen, rows: tuple[str, ...] = ROWS) -> ConsumerUiState:
    """A session sitting on `screen`, reached the way a person reaches it, showing `rows`."""

    state = ConsumerUiState()
    if screen is not ConsumerScreen.DASHBOARD:
        state, _ = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=screen)
        )
    state, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=rows))
    return state


def quit_pressed(state: ConsumerUiState):
    event = key_event("q", state)
    assert event is not None
    return reduce_consumer_ui(state, event)


class KeyboardNavigationTest(unittest.TestCase):
    def test_arrows_move_the_cursor_and_wrap_without_selecting_anything(self):
        state = press(at(ConsumerScreen.MARKETPLACE), DOWN, DOWN)
        self.assertEqual(state.current_row, "skill/review")

        state = press(state, DOWN)
        self.assertEqual(state.current_row, "mcp/github")

        state = press(state, UP)
        self.assertEqual(state.current_row, "skill/review")
        self.assertEqual(state.selection, ())

    def test_vi_keys_move_the_cursor_the_way_the_existing_frontend_does(self):
        state = press(at(ConsumerScreen.MARKETPLACE), ord("j"), ord("j"), ord("k"))
        self.assertEqual(state.current_row, "mcp/jira")

    def test_space_ticks_the_row_under_the_cursor_and_ticks_it_off_again(self):
        state = press(at(ConsumerScreen.MARKETPLACE), DOWN, SPACE)
        self.assertEqual(state.selection, ("mcp/jira",))

        state = press(state, SPACE)
        self.assertEqual(state.selection, ())

    def test_space_does_nothing_where_there_is_nothing_to_select(self):
        state = press(at(ConsumerScreen.INSTALLED), SPACE)
        self.assertEqual(state.selection, ())

    def test_escape_goes_back_and_q_leaves(self):
        state = press(at(ConsumerScreen.MARKETPLACE), ESCAPE)
        self.assertEqual(state.session.screen, ConsumerScreen.DASHBOARD)

        state, commands = quit_pressed(state)
        self.assertTrue(state.exited)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.EXIT)

    def test_enter_opens_the_detail_the_screen_names_and_back_returns_to_the_row(self):
        state = press(at(ConsumerScreen.MARKETPLACE), DOWN)
        opened = press(state, ENTER, detail=ConsumerScreen.ARTIFACT_DETAILS)
        self.assertEqual(opened.session.screen, ConsumerScreen.ARTIFACT_DETAILS)

        returned = press(opened, ESCAPE)
        self.assertEqual(returned.session.screen, ConsumerScreen.MARKETPLACE)
        self.assertEqual(returned.current_row, "mcp/jira")


class KeyboardSearchTest(unittest.TestCase):
    def test_while_the_filter_is_open_every_printable_key_types_into_it(self):
        state = press(at(ConsumerScreen.MARKETPLACE), SLASH, *map(ord, "quit?"))
        self.assertTrue(state.searching)
        self.assertEqual(state.search, "quit?")
        self.assertFalse(state.exited)
        self.assertFalse(state.help_visible)

    def test_backspace_edits_the_query_and_enter_keeps_what_is_on_screen(self):
        state = press(at(ConsumerScreen.MARKETPLACE), SLASH, *map(ord, "gith"), BACKSPACE, ENTER)
        self.assertFalse(state.searching)
        self.assertEqual(state.search, "git")

    def test_escape_drops_the_filter_and_the_query_together(self):
        state = press(at(ConsumerScreen.MARKETPLACE), SLASH, *map(ord, "git"), ESCAPE)
        self.assertFalse(state.searching)
        self.assertEqual(state.search, "")
        self.assertEqual(state.session.screen, ConsumerScreen.MARKETPLACE)

    def test_a_filter_hides_rows_without_unticking_or_losing_the_cursor(self):
        state = press(at(ConsumerScreen.MARKETPLACE), DOWN, SPACE)
        state = press(state, SLASH, *map(ord, "jira"), ENTER)
        state, _ = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=("mcp/jira",))
        )
        self.assertEqual(state.selection, ("mcp/jira",))
        self.assertEqual(state.current_row, "mcp/jira")

        state, _ = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=ROWS)
        )
        self.assertEqual(state.selection, ("mcp/jira",))
        self.assertEqual(state.current_row, "mcp/jira")

    def test_a_screen_with_nothing_to_filter_ignores_the_filter_key(self):
        state = press(at(ConsumerScreen.DASHBOARD, rows=()), SLASH, *map(ord, "git"))
        self.assertFalse(state.searching)
        self.assertEqual(state.search, "")


class KeyboardDisclosureTest(unittest.TestCase):
    def test_v_toggles_disclosure_without_touching_the_selection_or_the_screen(self):
        state = press(at(ConsumerScreen.MARKETPLACE), DOWN, SPACE)

        verbose = press(state, ord("v"))
        self.assertIs(verbose.session.profile, PresentationProfile.VERBOSE)
        self.assertIs(verbose.settings.profile, PresentationProfile.VERBOSE)
        self.assertEqual(verbose.selection, state.selection)
        self.assertEqual(verbose.session.screen, state.session.screen)

        back_to_fast = press(verbose, ord("v"))
        self.assertIs(back_to_fast.session.profile, PresentationProfile.FAST)
        self.assertEqual(back_to_fast.selection, state.selection)

    def test_question_toggles_help_without_leaving_the_screen(self):
        state = press(at(ConsumerScreen.MARKETPLACE), QUESTION)
        self.assertTrue(state.help_visible)
        self.assertEqual(state.session.screen, ConsumerScreen.MARKETPLACE)
        self.assertFalse(press(state, QUESTION).help_visible)

    def test_the_profile_the_keyboard_holds_is_the_one_the_renderer_uses(self):
        record = ActivityRecord("2026-08-31T14:32:00Z", lifecycle_outcome())
        view = project_activity((record,), today=dt.date(2026, 8, 31))
        state = press(at(ConsumerScreen.ACTIVITY, rows=("2026-08-31T14:32",)), ord("v"))

        rendered = "\n".join(render_activity(view, state.session.profile))

        self.assertIn("sha256:", rendered)
        self.assertNotIn("sha256:", "\n".join(render_activity(view, PresentationProfile.FAST)))


class KeyboardQuitTest(unittest.TestCase):
    def test_quitting_with_a_selection_asks_first_and_n_keeps_working(self):
        state = press(at(ConsumerScreen.MARKETPLACE), SPACE)

        state, commands = quit_pressed(state)
        self.assertTrue(state.quit_pending)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.CONFIRM_QUIT)

        kept = press(state, ord("n"))
        self.assertFalse(kept.exited)
        self.assertFalse(kept.quit_pending)
        self.assertEqual(kept.selection, ("mcp/github",))

    def test_at_the_prompt_the_answer_keys_are_the_only_ones_that_act(self):
        state = press(at(ConsumerScreen.MARKETPLACE), SPACE)
        state, _ = quit_pressed(state)

        unchanged = press(state, SLASH, QUESTION, DOWN)
        self.assertEqual(unchanged, state)

        self.assertTrue(press(state, ord("y")).exited)


if __name__ == "__main__":
    unittest.main()
