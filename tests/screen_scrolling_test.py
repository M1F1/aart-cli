"""Every screen taller than the terminal scrolls with PgUp and PgDn (§206, INV-311).

Only Marketplace used to page. Screen 07 with many settings, screen 07b with many credentials and
the Ready summary drew past the bottom row, and curses clipped the rest away, so what was cut could
be neither read nor reached. These tests hold the pure viewport, the reducer and the legend; the
end-to-end test drives the shared consumer and maintainer loop at a real terminal height.
"""

from __future__ import annotations

import dataclasses
import json
import os
import unittest
from unittest import mock

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.tui_consumer import run_consumer_shell
from aart_cli.tui_layout import Frame, footer_start, render, screen_viewport, wrap_lines
from tests.artifact_installation_e2e_test import MANIFEST, SERVER_SOURCE
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions, _at, _Terminal
from tests.consumer_shell_test import ENTER, ESCAPE, INSTALL_CUSTOM, RIGHT, SPACE, UP

KEYS = ("[Enter] Open", "", "[Esc] Back  [q] Quit")
TRAIL = ("Install  ✓ Artifacts → ▸ Configuration",)


def _form(count: int, focused: int) -> Frame:
    rows = []
    for index in range(count):
        rows.append(f"{'>' if index == focused else ' '} setting-{index:03d}: value")
        rows.append(f"    what setting-{index:03d} is for")
    return Frame(trail=TRAIL, actions=tuple(rows), status=("3 of 9 set",), keys=KEYS)


def _drawn(viewport, columns: int) -> tuple[str, ...]:
    return wrap_lines(render(viewport.frame), width=columns + 1)


def _body(viewport) -> tuple[str, ...]:
    return viewport.frame.actions


class ScreenViewportTest(unittest.TestCase):
    def test_a_frame_that_fits_is_drawn_whole_and_is_not_paged(self):
        view = _form(3, 0)
        viewport = screen_viewport(view, columns=80, height=40, offset=7, follow=False)
        self.assertEqual(viewport.frame, view)
        self.assertEqual(viewport.offset, 0)
        self.assertFalse(viewport.paged)

    def test_no_height_means_no_terminal_and_nothing_is_paged(self):
        view = _form(60, 0)
        viewport = screen_viewport(view, columns=80, height=0, offset=0, follow=True)
        self.assertEqual(viewport.frame, view)
        self.assertFalse(viewport.paged)

    def test_a_tall_frame_keeps_its_trail_and_keys_and_says_what_is_below(self):
        viewport = screen_viewport(_form(60, 0), columns=80, height=20, offset=0, follow=True)
        lines = _drawn(viewport, 80)
        self.assertTrue(viewport.paged)
        self.assertLessEqual(len(lines), 20)
        self.assertEqual(lines[0], TRAIL[0])
        self.assertEqual(lines[footer_start(lines) :][-1], KEYS[-1])
        self.assertIn("> setting-000: value", lines)
        self.assertRegex(_body(viewport)[-1], r"^↓ \d+ more lines below; PgDn$")
        self.assertNotIn("above", "\n".join(lines))

    def test_paging_down_shows_later_lines_and_says_what_is_above(self):
        viewport = screen_viewport(_form(60, 0), columns=80, height=20, offset=30, follow=False)
        self.assertEqual(viewport.offset, 30)
        self.assertEqual(_body(viewport)[0], "↑ 30 more lines above; PgUp")
        self.assertIn("  setting-015: value", _body(viewport))
        self.assertNotIn("> setting-000: value", _body(viewport))

    def test_following_brings_the_focused_row_into_view(self):
        viewport = screen_viewport(_form(60, 40), columns=80, height=20, offset=0, follow=True)
        self.assertIn("> setting-040: value", _body(viewport))
        # The row's own explanation, the line under it, is kept in view with it.
        self.assertIn("    what setting-040 is for", _body(viewport))
        stay = screen_viewport(
            _form(60, 40), columns=80, height=20, offset=viewport.offset, follow=True
        )
        self.assertEqual(stay.offset, viewport.offset)

    def test_a_page_beyond_the_end_is_clamped_to_the_last_full_page(self):
        last = screen_viewport(_form(60, 0), columns=80, height=20, offset=10_000, follow=False)
        again = screen_viewport(
            _form(60, 0), columns=80, height=20, offset=last.offset - 1, follow=False
        )
        self.assertEqual(again.offset, last.offset - 1)
        self.assertIn("    what setting-059 is for", _body(last))
        self.assertEqual(_body(last)[-1], "3 of 9 set")

    @settings(max_examples=60, deadline=None)
    @given(
        count=st.integers(min_value=1, max_value=50),
        focus=st.integers(min_value=0, max_value=49),
        columns=st.integers(min_value=20, max_value=140),
        height=st.integers(min_value=16, max_value=60),
        offset=st.integers(min_value=0, max_value=200),
        follow=st.booleans(),
    )
    def test_any_frame_fits_keeps_its_ends_and_pages_reach_every_line(
        self, count, focus, columns, height, offset, follow
    ):
        view = _form(count, min(focus, count - 1))
        whole = wrap_lines(render(view), width=columns + 1)
        footer = whole[footer_start(whole) :]
        viewport = screen_viewport(
            view, columns=columns, height=height, offset=offset, follow=follow
        )
        lines = _drawn(viewport, columns)
        self.assertLessEqual(len(lines), height)
        self.assertEqual(lines[footer_start(lines) :], footer)
        self.assertEqual(lines[0], whole[0])
        if not viewport.paged:
            self.assertEqual(lines, whole)
            return
        if follow:
            self.assertTrue(any(line.startswith(">") for line in _body(viewport)))
        # Every page is a run of the body, in order, and the pages together hold all of it.
        body = wrap_lines(
            render(dataclasses.replace(view, trail=(), keys=(), context="")), width=columns + 1
        )
        covered: set[int] = set()
        page = 0
        while True:
            shown = screen_viewport(view, columns=columns, height=height, offset=page, follow=False)
            middle = list(_body(shown))
            if middle[0].startswith("↑ "):
                middle.pop(0)
            if middle[-1].startswith("↓ "):
                middle.pop()
            self.assertEqual(tuple(middle), body[shown.offset : shown.offset + len(middle)])
            covered.update(range(shown.offset, shown.offset + len(middle)))
            if shown.offset < page:
                break
            page += 1
        self.assertEqual(covered, set(range(len(body))))


class ScrollReducerTest(unittest.TestCase):
    def _state(self, screen=ConsumerScreen.REQUIRED_INPUTS, **changes) -> ConsumerUiState:
        state = ConsumerUiState(session=ConsumerSession(screen=screen), viewport_rows=30)
        return dataclasses.replace(state, **changes)

    def test_page_down_moves_half_a_terminal_and_stops_following_the_cursor(self):
        state, commands = reduce_consumer_ui(
            self._state(scroll=4), ConsumerUiEvent(ConsumerUiEventKind.SCROLL, text="down")
        )
        self.assertEqual((state.scroll, state.scroll_follows, commands), (19, False, ()))
        state, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.SCROLL, text="up"))
        self.assertEqual(state.scroll, 4)
        state, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.SCROLL, text="up"))
        self.assertEqual(state.scroll, 0)

    def test_a_short_terminal_still_moves_at_least_one_line(self):
        state, _ = reduce_consumer_ui(
            self._state(viewport_rows=1), ConsumerUiEvent(ConsumerUiEventKind.SCROLL, text="down")
        )
        self.assertEqual(state.scroll, 1)

    def test_moving_the_cursor_follows_it_again_and_keeps_the_page(self):
        state = self._state(scroll=12, scroll_follows=False, rows=("a", "b"))
        moved, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down"))
        self.assertEqual((moved.scroll, moved.scroll_follows), (12, True))

    def test_another_screen_starts_at_its_top(self):
        state = self._state(screen=ConsumerScreen.DASHBOARD, scroll=12, scroll_follows=False)
        moved, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.SETTINGS),
        )
        self.assertIs(moved.session.screen, ConsumerScreen.SETTINGS)
        self.assertEqual((moved.scroll, moved.scroll_follows), (0, True))

    def test_page_keys_scroll_every_screen_but_not_while_searching(self):
        for screen in (
            ConsumerScreen.REQUIRED_INPUTS,
            ConsumerScreen.INSTALL_CREDENTIALS,
            ConsumerScreen.READY,
            ConsumerScreen.MARKETPLACE,
        ):
            for key, direction in (("page-up", "up"), ("page-down", "down")):
                event = key_event(key, self._state(screen=screen))
                self.assertEqual(event, ConsumerUiEvent(ConsumerUiEventKind.SCROLL, text=direction))
        self.assertIsNone(key_event("page-down", self._state(searching=True)))

    def test_the_legend_offers_scrolling_only_when_the_screen_is_taller(self):
        def offered(state):
            return any(binding.key == "PgUp/PgDn" for binding in key_bindings(state))

        self.assertFalse(offered(self._state()))
        self.assertTrue(offered(self._state(scrollable=True)))
        self.assertFalse(offered(self._state(scrollable=True, searching=True)))

    def test_the_state_refuses_a_negative_page(self):
        with self.assertRaises(ValueError):
            self._state(scroll=-1)
        with self.assertRaises(ValueError):
            self._state(scroll_follows=1)


if __name__ == "__main__":
    unittest.main()


PAGE_DOWN, PAGE_UP = 338, 339


def _fifteen_settings() -> tuple[tuple[str, str], ...]:
    """An MCP server declaring fifteen settings, each with a default."""

    manifest = json.loads(json.dumps(MANIFEST))
    manifest["inputs"] = [
        {
            "id": f"setting-{index:02d}",
            "kind": "config",
            "default": f"value-{index:02d}",
            "inject": {"type": "environment", "variable": f"SETTING_{index:02d}"},
            "help": {"label": f"Setting number {index:02d}"},
        }
        for index in range(1, 16)
    ]
    return (
        ("github/aart-cli.json", json.dumps(manifest)),
        ("github/server.py", SERVER_SOURCE),
        ("github/requirements.txt", "# no third-party packages\n"),
    )


class _Short(_Terminal):
    rows = 20
    columns = 99


def _run(env, handler, terminal, screen: ConsumerScreen) -> None:
    with mock.patch.dict(os.environ, env.xdg, clear=False):
        run_consumer_shell(
            handler.source(),
            terminal,
            state=_at(screen),
            action_handler=handler,
            settings_writer=handler.save_settings,
        )


class ScrollingE2ETest(unittest.TestCase):
    """The shared consumer and maintainer loop, at twenty rows, on fifteen settings."""

    def _fits(self, terminal) -> None:
        for frame in terminal.frames:
            self.assertLessEqual(len(wrap_lines(frame, width=100)), 20, "\n".join(frame))

    def test_page_down_reaches_the_last_setting_of_screen_22a(self):
        # The owner's report: User Variables and Credentials did not scroll either.
        with _environment(authored=_fifteen_settings()) as env:
            handler = _actions(env)
            # 07a as it is (§209); 07: Set later; then Ready and the install with their defaults.
            install = _Terminal(
                SPACE, *INSTALL_CUSTOM, RIGHT, SPACE, ENTER, ENTER, UP, *(ENTER,) * 3
            )
            _run(env, handler, install, ConsumerScreen.MARKETPLACE)
            self.assertTrue(install.screen_containing("Success"), install.last)
            terminal = _Short(ENTER, *(PAGE_DOWN,) * 5, ESCAPE, ESCAPE)
            _run(env, handler, terminal, ConsumerScreen.CREDENTIALS)

        self._fits(terminal)
        drawn = ["\n".join(frame) for frame in terminal.frames]
        details = next(text for text in drawn if "> setting-01" in text)
        self.assertIn("PgUp/PgDn", details)
        self.assertNotIn("setting-15", details)
        self.assertTrue(
            any("setting-15" in text and "more lines above" in text for text in drawn), drawn[-1]
        )

    def test_page_down_reaches_the_last_setting_of_a_form_taller_than_the_terminal(self):
        with _environment(authored=_fifteen_settings()) as env:
            handler = _actions(env)
            terminal = _Short(
                SPACE,
                *INSTALL_CUSTOM,
                RIGHT,
                SPACE,
                ENTER,
                # 07a as it is: the scope comes before the form (§209).
                ENTER,
                *(PAGE_DOWN,) * 8,
                PAGE_UP,
                ESCAPE,
                ESCAPE,
                ESCAPE,
                ESCAPE,
            )
            _run(env, handler, terminal, ConsumerScreen.MARKETPLACE)

        drawn = ["\n".join(frame) for frame in terminal.frames]
        self._fits(terminal)
        form = [text for text in drawn if "Setting number 01" in text or "setting-01" in text]
        self.assertTrue(form, terminal.last)
        first = form[0]
        self.assertIn("PgUp/PgDn", first)
        self.assertRegex(first, r"↓ \d+ more lines? below; PgDn")
        self.assertNotIn("Setting number 15", first)
        last = next(text for text in drawn if "Setting number 15" in text)
        self.assertRegex(last, r"↑ \d+ more lines? above; PgUp")
        # The end clamps: the PgDn after the last page draws the same page again.
        at_end = [index for index, text in enumerate(drawn) if text == last]
        self.assertGreater(len(at_end), 1)
        # One PgUp moves at once, rather than first undoing PgDn presses that went nowhere.
        self.assertNotEqual(drawn[at_end[-1] + 1], last)
