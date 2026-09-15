"""CP-23 task 14.8: every declared screen and conditional state obeys one frame contract."""

from __future__ import annotations

import unittest
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.consumer_ui import (
    CONFIG_CONTINUE_ROW,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerScreen, PresentationProfile
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.tui import _CursesTerminal, _TextTerminal
from agent_artifacts.tui_consumer import _reload, frame
from agent_artifacts.tui_layout import SECTION_RULE, anchor, footer_start
from tests.frame_contract import (
    frame_violations,
    key_violations,
    literal_violations,
    toggle_violations,
)
from tests.screen_cases import RECORDED_SCREENS, ScreenCase, conditional_cases, screen_cases


def _profiles(case: ScreenCase):
    for profile in PresentationProfile:
        yield replace(
            case.state,
            session=replace(case.state.session, profile=profile),
            settings=replace(case.state.settings, profile=profile),
        )


def _cursors(case: ScreenCase):
    for state in _profiles(case):
        yield state
        for cursor in range(len(state.rows)):
            yield replace(state, cursor=cursor)


class RecordedFrameMatrixTest(unittest.TestCase):
    def test_the_recorded_matrix_covers_both_screen_catalogs_exactly(self) -> None:
        cases = screen_cases()

        self.assertEqual(
            set(RECORDED_SCREENS),
            {*ConsumerScreen, *MaintainerScreen},
        )
        self.assertEqual(len(cases), len(ConsumerScreen) + len(MaintainerScreen))

    def test_every_recorded_cursor_in_both_profiles_obeys_all_shared_laws(self) -> None:
        for case in (*screen_cases(), *conditional_cases()):
            for state in _cursors(case):
                with self.subTest(
                    case=case.label,
                    row=state.current_row,
                    profile=state.session.profile,
                ):
                    self.assertEqual(frame_violations(case.source, state), ())
                    self.assertEqual(key_violations(case.source, state), ())
                    self.assertEqual(literal_violations(case.source, state), ())
                    self.assertEqual(toggle_violations(case.source, state), ())

    def test_every_offered_row_has_a_working_move_or_action(self) -> None:
        for case in screen_cases():
            for cursor in range(len(case.state.rows)):
                state = replace(case.state, cursor=cursor)
                with self.subTest(case=case.label, row=state.current_row):
                    enter = key_event("enter", state, detail=case.source.detail(state))
                    local = tuple(
                        key_event(key, state, detail=case.source.detail(state))
                        for key in (" ", "i", "r", "u", "s", "a", "d", "c")
                    )
                    disabled_continue = state.current_row == CONFIG_CONTINUE_ROW and (
                        (
                            state.session.screen is ConsumerScreen.CONFIGURATION_VALUE
                            and not state.configuration_draft.ready
                        )
                        or (
                            state.session.screen is ConsumerScreen.REQUIRED_INPUTS
                            and state.config_form_active
                            and not state.config_draft.ready
                        )
                    )
                    self.assertTrue(
                        disabled_continue
                        or enter is not None
                        or any(event is not None for event in local)
                    )


class TerminalProjectionMatrixTest(unittest.TestCase):
    class _Screen:
        def __init__(self, height: int, width: int = 240) -> None:
            self.height = height
            self.width = width
            self.rows: dict[int, str] = {}

        def clear(self) -> None:
            self.rows.clear()

        def getmaxyx(self):
            return self.height, self.width

        def addstr(self, row: int, _column: int, text: str) -> None:
            self.rows[row] = text

        def refresh(self) -> None:
            pass

        def getch(self) -> int:
            return ord("q")

    def test_text_and_tall_curses_receive_the_same_composed_frame(self) -> None:
        for case in screen_cases():
            lines = frame(case.source, case.state)
            written: list[str] = []
            _TextTerminal(lambda _prompt: "q", written.append).draw(lines)
            screen = self._Screen(len(lines) + 3)
            _CursesTerminal(screen).draw(lines)

            with self.subTest(case=case.label):
                self.assertEqual(tuple(written[: len(lines)]), lines)
                expected = anchor(lines, height=screen.height - 1)
                self.assertEqual(
                    tuple(screen.rows[index] for index in range(len(expected))), expected
                )

    def test_clipped_curses_keeps_the_complete_footer(self) -> None:
        for case in screen_cases():
            lines = frame(case.source, case.state)
            footer = lines[footer_start(lines) :]
            height = max(len(footer) + 1, 2)
            screen = self._Screen(height)
            _CursesTerminal(screen).draw(lines)
            drawn = tuple(screen.rows[index] for index in sorted(screen.rows))

            with self.subTest(case=case.label):
                self.assertEqual(drawn[-len(footer) :], footer[: height - 1])
                self.assertIn(SECTION_RULE, drawn)


class FrameSequencePropertiesTest(unittest.TestCase):
    @given(keys=st.lists(st.sampled_from(("up", "down", "v")), max_size=40))
    def test_move_and_profile_sequences_preserve_the_shared_laws(self, keys: list[str]) -> None:
        case = next(item for item in screen_cases() if item.screen is ConsumerScreen.INSTALLED)
        state = case.state
        for key in keys:
            event = key_event(key, state, detail=case.source.detail(state))
            if event is None:
                continue
            state, _ = reduce_consumer_ui(state, event)
            state = _reload(case.source, state)

        self.assertEqual(frame_violations(case.source, state), ())
        self.assertEqual(key_violations(case.source, state), ())
        self.assertEqual(toggle_violations(case.source, state), ())


if __name__ == "__main__":
    unittest.main()
