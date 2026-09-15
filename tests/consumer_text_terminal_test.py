"""The canonical application in a terminal that cannot host curses (ERR05).

Text was not a second application. `run()` degraded to `_run_text`, the characterized wizard, which
is built on `ConsumerApplicationService` and through it on the whole legacy consumer, lifecycle,
installation and setup-engine stack. So a no-TTY environment -- CI, a pipe, a dumb terminal, an SSH
session without a pty -- got a different product from the one a terminal gets, and CP-14 step 7
could not retire that stack while it was the only thing the text route had.

ERR05 says text is legitimate for exactly one condition: the terminal cannot host curses. It says
nothing about it being a different application, and the shell already takes its terminal as a port
of two methods. So the fallback is the same canonical application, drawn with `print` and driven by
`input()`.

A line editor has no arrow keys and no bare Escape, so the adapter names them: a word for the keys
a line cannot send, a single character for everything else, and a blank line for Enter.
"""

from __future__ import annotations

import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import ConsumerSettings
from agent_artifacts.domain.result import Ok
from agent_artifacts.tui_consumer import key_name


def _reader(*lines: str):
    """`input()`, scripted; every script ends by running out, which is what a closed stdin is."""

    remaining = list(lines)

    def read(_prompt: str = "") -> str:
        if not remaining:
            raise EOFError
        return remaining.pop(0)

    return read


class TextTerminalKeyTest(unittest.TestCase):
    def test_a_single_character_line_is_that_key(self) -> None:
        terminal = tui._TextTerminal(_reader("q", "i", " "), lambda _line: None)

        self.assertEqual(
            [key_name(terminal.key()) for _ in range(3)],
            ["q", "i", " "],
        )

    def test_a_blank_line_is_enter_because_that_is_what_pressing_return_sends(self) -> None:
        terminal = tui._TextTerminal(_reader(""), lambda _line: None)

        self.assertEqual(key_name(terminal.key()), "enter")

    def test_the_keys_a_line_editor_cannot_send_have_names(self) -> None:
        terminal = tui._TextTerminal(
            _reader("up", "down", "esc", "escape", "back", "enter"), lambda _line: None
        )

        self.assertEqual(
            [key_name(terminal.key()) for _ in range(6)],
            ["up", "down", "escape", "escape", "backspace", "enter"],
        )

    def test_a_name_is_matched_without_regard_to_case_or_surrounding_space(self) -> None:
        terminal = tui._TextTerminal(_reader("  Down  ", "ESC"), lambda _line: None)

        self.assertEqual([key_name(terminal.key()) for _ in range(2)], ["down", "escape"])

    def test_an_unknown_word_means_nothing_rather_than_something(self) -> None:
        """Taking the first character of "delete" would act on d, which no one asked for."""

        terminal = tui._TextTerminal(_reader("delete"), lambda _line: None)

        self.assertEqual(key_name(terminal.key()), "")

    def test_a_closed_stdin_quits_and_answers_the_discard_prompt(self) -> None:
        """Otherwise a pipe that ends mid-selection redraws the prompt forever."""

        terminal = tui._TextTerminal(_reader(), lambda _line: None)

        self.assertEqual([key_name(terminal.key()) for _ in range(3)], ["q", "y", "y"])

    def test_drawing_writes_every_line_of_the_frame(self) -> None:
        written: list[str] = []
        terminal = tui._TextTerminal(_reader(), written.append)

        terminal.draw(("AART / Dashboard", "", "3 installed"))

        self.assertIn("AART / Dashboard", written)
        self.assertIn("3 installed", written)


class CanonicalTextRouteTest(unittest.TestCase):
    def test_the_text_route_runs_the_same_application_the_terminal_route_runs(self) -> None:
        """One shell, one reducer, one screen source -- in a terminal that cannot host curses."""

        actions = mock.Mock()
        actions.settings = ConsumerSettings()
        written: list[str] = []

        with mock.patch.object(tui, "run_consumer_shell", return_value=ConsumerUiState()) as shell:
            tui.run_consumer_text(actions, read=_reader("q"), write=written.append)

        shell.assert_called_once()
        self.assertIs(shell.call_args.args[0], actions.source.return_value)
        self.assertIs(shell.call_args.kwargs["action_handler"], actions)
        self.assertIs(shell.call_args.kwargs["settings_writer"], actions.save_settings)


class TextRouteEndToEndTest(unittest.TestCase):
    def test_a_person_on_a_pipe_reaches_the_dashboard_and_leaves(self) -> None:
        """The production composition over a real machine; only stdin and stdout are scripted."""

        import datetime as dt
        import os

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env:
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project),
                    user_home=str(env.home),
                    today=dt.date(2026, 9, 1),
                )
                self.assertIsInstance(composed, Ok, composed)
                written: list[str] = []
                state = tui.run_consumer_text(
                    composed.value, read=_reader("q"), write=written.append
                )

        drawn = "\n".join(written)
        self.assertTrue(state.exited)
        self.assertIn("AART / Dashboard", drawn)
        self.assertIn("1 registries", drawn)

    def test_the_marketplace_a_pipe_reaches_is_the_one_the_registry_approved(self) -> None:
        """Not a different product: the offers are the canonical application's own."""

        import datetime as dt
        import os

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env:
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project),
                    user_home=str(env.home),
                    today=dt.date(2026, 9, 1),
                )
                self.assertIsInstance(composed, Ok, composed)
                written: list[str] = []
                tui.run_consumer_text(
                    # A blank line is Return, and the dashboard opens on Marketplace.
                    composed.value,
                    read=_reader("", "q"),
                    write=written.append,
                )

        self.assertIn("company/skill/code-review@1.2.0", "\n".join(written))


if __name__ == "__main__":
    unittest.main()
