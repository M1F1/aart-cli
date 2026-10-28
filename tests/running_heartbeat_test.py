"""§203, INV-305, D-490: a running action beats, so a slow one is never mistaken for a hung one.

The owner asked for a moving mark while an install runs. An action runs on the loop's thread, so
the screen held its last frame for as long as the action took. A heartbeat now redraws that frame
from its own thread with a turning mark and the seconds taken, over the step the action reached,
and never while the terminal is lent to a credential prompt.
"""

from __future__ import annotations

import threading
import unittest
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import tui
from aart_cli.application.consumer_ui import ConsumerUiCommand
from aart_cli.tui_consumer import HEARTBEAT_MARKS, Heartbeat, heartbeat_frame
from tests.consumer_shell_test import FakeTerminal
from tests.running_installation_screen_test import ReportingHandler, _drive

FRAME = ("AART / Marketplace / Installing", "", "body", "[q] Quit")


class TickingTerminal(FakeTerminal):
    """A terminal a heartbeat can draw on, which says when it has been beaten on."""

    def __init__(self, *codes: int) -> None:
        super().__init__(*codes)
        self.ticks: list[tuple[str, ...]] = []
        self.beaten = threading.Event()

    def tick(self, lines: tuple[str, ...]) -> None:
        self.ticks.append(lines)
        if len(self.ticks) >= 3:
            self.beaten.set()


class SlowHandler(ReportingHandler):
    """Reports both steps, then takes long enough to be beaten on before returning."""

    def __init__(self, terminal: TickingTerminal) -> None:
        super().__init__()
        self._terminal = terminal

    def handle(self, command: ConsumerUiCommand):
        update = super().handle(command)
        self._terminal.beaten.wait(5)
        return update


class HeartbeatFrameTest(unittest.TestCase):
    @given(st.integers(0, 1000), st.floats(0, 10_000, allow_nan=False))
    def test_the_heading_carries_a_turning_mark_and_the_seconds(
        self, beat: int, elapsed: float
    ) -> None:
        beaten = heartbeat_frame(FRAME, beat, elapsed)

        mark = HEARTBEAT_MARKS[beat % len(HEARTBEAT_MARKS)]
        self.assertEqual(beaten[0], f"{FRAME[0]}   {mark} working {int(elapsed)}s")
        self.assertEqual(beaten[1:], FRAME[1:])

    def test_consecutive_beats_turn_the_mark(self) -> None:
        marks = {
            heartbeat_frame(FRAME, beat, 0)[0].split("   ")[-1][0]
            for beat in range(len(HEARTBEAT_MARKS))
        }

        self.assertEqual(len(marks), len(HEARTBEAT_MARKS))

    def test_an_empty_frame_stays_empty(self) -> None:
        self.assertEqual(heartbeat_frame((), 3, 1.0), ())


class HeartbeatTest(unittest.TestCase):
    def test_it_beats_until_the_action_returns_and_then_stops(self) -> None:
        terminal = TickingTerminal()

        with Heartbeat(terminal, FRAME, interval=0.005):
            self.assertTrue(terminal.beaten.wait(5))
        stopped = len(terminal.ticks)
        threading.Event().wait(0.05)

        self.assertEqual(len(terminal.ticks), stopped)
        self.assertTrue(all(lines[0].startswith(FRAME[0] + "   ") for lines in terminal.ticks))

    def test_it_beats_over_the_frame_it_was_last_shown(self) -> None:
        terminal = TickingTerminal()
        later = ("AART / Marketplace / Installing", "", "▸ harness", "[q] Quit")

        with Heartbeat(terminal, FRAME, interval=0.005) as heartbeat:
            heartbeat.show(later)
            terminal.ticks.clear()
            terminal.beaten.clear()
            self.assertTrue(terminal.beaten.wait(5))

        self.assertTrue(all(lines[2] == "▸ harness" for lines in terminal.ticks))

    def test_a_terminal_that_cannot_tick_is_left_as_it_was(self) -> None:
        terminal = FakeTerminal()

        with Heartbeat(terminal, FRAME, interval=0.001):
            threading.Event().wait(0.02)

        self.assertEqual(terminal.frames, [])


class TheShellBeatsTest(unittest.TestCase):
    def test_an_install_is_beaten_on_over_the_step_it_reached(self) -> None:
        terminal = TickingTerminal(ord("\n"))
        with mock.patch("tests.running_installation_screen_test.FakeTerminal", lambda *_: terminal):
            _drive(SlowHandler(terminal))

        self.assertTrue(terminal.beaten.is_set())
        self.assertTrue(any("working" in lines[0] for lines in terminal.ticks))
        self.assertTrue(any("harness:tabnine" in "\n".join(lines) for lines in terminal.ticks))

    def test_no_beat_outlives_the_action(self) -> None:
        terminal = TickingTerminal(ord("\n"))
        with mock.patch("tests.running_installation_screen_test.FakeTerminal", lambda *_: terminal):
            _drive(SlowHandler(terminal))
        after = len(terminal.ticks)
        threading.Event().wait(0.5)

        self.assertEqual(len(terminal.ticks), after)


class _Screen:
    """Enough of a curses window to be drawn on."""

    def __init__(self) -> None:
        self.drawn: list[str] = []

    def getmaxyx(self) -> tuple[int, int]:
        return (24, 80)

    def clear(self) -> None:
        self.drawn.clear()

    def addstr(self, _row: int, _column: int, line: str) -> None:
        self.drawn.append(line)

    def refresh(self) -> None:
        pass


class TheLoanHoldsTheScreenTest(unittest.TestCase):
    def test_a_beat_is_skipped_while_the_screen_is_held(self) -> None:
        screen, lock = _Screen(), threading.Lock()
        terminal = tui._CursesTerminal(screen, lock)

        with lock:
            terminal.tick(FRAME)
        self.assertEqual(screen.drawn, [])
        terminal.tick(FRAME)
        self.assertIn("body", screen.drawn)

    def test_the_handover_holds_the_screen_for_the_whole_loan(self) -> None:
        screen, lock = _Screen(), threading.Lock()
        handover = tui._CursesHandover(columns=80)
        handover.bind(screen, lock)

        with (
            mock.patch("curses.def_prog_mode"),
            mock.patch("curses.endwin"),
            mock.patch("curses.reset_prog_mode"),
            mock.patch.object(handover, "_say"),
        ):
            with handover():
                held = lock.locked()

        self.assertTrue(held)
        self.assertFalse(lock.locked())


if __name__ == "__main__":
    unittest.main()
