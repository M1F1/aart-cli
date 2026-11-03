"""§215, B-265, INV-335: an end by SIGTERM or SIGHUP is journaled, and the process still ends by it.

A closed terminal sends SIGHUP and a supervisor SIGTERM; neither raises anything `cli.main` or the
terminal application can catch. Each test runs a real process and sends it the real signal, since
what is claimed is how that process ends.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from aart_cli.domain.failures import FailureKind
from aart_cli.io.failure_journal import FailureJournal
from aart_cli.io.termination import TerminationGuard

ROOT = Path(__file__).resolve().parent.parent

_GUARDED = """
import os, signal, sys, time
from aart_cli.io.termination import TerminationGuard

kept = sys.argv[1]
number = getattr(signal, sys.argv[2])
before = sys.argv[3]
if before == "ignored":
    signal.signal(number, signal.SIG_IGN)
elif before == "handled":
    signal.signal(number, lambda *_: print("its own handler", flush=True))

def record(place, code):
    with open(kept, "a", encoding="utf-8") as file:
        file.write(f"{place} {code}\\n")
    if before == "failing":
        raise OSError("the journal is gone")

with TerminationGuard(record, "consume.list") as guard:
    guard.place = "tui.install"
    os.kill(os.getpid(), number)
    time.sleep(0.2)
print("still running", flush=True)
"""

_COMMAND = """
import os, signal, sys
from aart_cli import cli

def stopped(args, request):
    os.kill(os.getpid(), getattr(signal, sys.argv[1]))
    return 0

cli._dispatch = stopped
sys.exit(cli.main(["consume", "list"]))
"""


def _python(script: str, *arguments: str, environment: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, "-c", script, *arguments],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONPATH": str(ROOT), **(environment or {})},
        check=False,
    )


class TheGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.kept = Path(temporary.name) / "kept"

    def _kept(self) -> str:
        return self.kept.read_text("utf-8") if self.kept.exists() else ""

    def test_each_signal_is_journaled_at_the_place_held_and_still_ends_the_process(self) -> None:
        for name, code in (("SIGTERM", 143), ("SIGHUP", 129)):
            with self.subTest(name):
                self.kept.unlink(missing_ok=True)
                ended = _python(_GUARDED, str(self.kept), name, "default")

                self.assertEqual(ended.returncode, -getattr(signal, name))
                self.assertEqual(self._kept(), f"tui.install {code}\n")
                self.assertNotIn("still running", ended.stdout)

    def test_a_record_that_fails_never_keeps_the_process_alive(self) -> None:
        ended = _python(_GUARDED, str(self.kept), "SIGTERM", "failing")

        self.assertEqual(ended.returncode, -signal.SIGTERM)
        self.assertEqual(ended.stderr, "")

    def test_a_signal_ignored_or_handled_before_is_left_as_it_was(self) -> None:
        ignored = _python(_GUARDED, str(self.kept), "SIGHUP", "ignored")
        handled = _python(_GUARDED, str(self.kept), "SIGTERM", "handled")

        self.assertEqual((ignored.returncode, ignored.stdout), (0, "still running\n"))
        self.assertEqual(
            (handled.returncode, handled.stdout), (0, "its own handler\nstill running\n")
        )
        self.assertEqual(self._kept(), "")

    def test_leaving_gives_back_the_default_and_outside_the_main_thread_takes_nothing(
        self,
    ) -> None:
        record = mock.Mock()
        with TerminationGuard(record, "tui"):
            self.assertIsNot(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)
        self.assertIs(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)
        self.assertIs(signal.getsignal(signal.SIGHUP), signal.SIG_DFL)

        seen: list[object] = []

        def elsewhere() -> None:
            with TerminationGuard(record, "tui"):
                seen.append(signal.getsignal(signal.SIGTERM))

        thread = threading.Thread(target=elsewhere)
        thread.start()
        thread.join()
        self.assertEqual(seen, [signal.SIG_DFL])
        record.assert_not_called()


class ACommandEndedBySignalTest(unittest.TestCase):
    def test_it_is_an_interruption_at_its_place_with_the_shells_exit_code(self) -> None:
        for name, code in (("SIGTERM", 143), ("SIGHUP", 129)):
            with self.subTest(name), tempfile.TemporaryDirectory() as home:
                ended = _python(_COMMAND, name, environment={"HOME": home, "AART_CLI_HOME": home})

                self.assertEqual(ended.returncode, -getattr(signal, name))
                entries = FailureJournal(str(Path(home) / "state")).entries()
                (entry,) = entries.value  # type: ignore[union-attr]
                failure = entry.failure
                self.assertEqual(
                    (failure.kind, failure.place, failure.exit_code, failure.exception),
                    (FailureKind.INTERRUPTED, "consume.list", code, None),
                )


_TERMINAL = """
import os, signal, sys
from datetime import date
from aart_cli import tui
from aart_cli.application.consumer_ui import ConsumerActionKind

home = os.environ["HOME"]
actions = tui._canonical_consumer_actions(project=home, user_home=home, today=date(2026, 11, 3))
with actions.value.journaling_terminations() as running:
    if sys.argv[2] == "install":
        running(ConsumerActionKind.INSTALL)
    elif sys.argv[2] == "after":
        running(ConsumerActionKind.INSTALL)
        running(None)
    os.kill(os.getpid(), getattr(signal, sys.argv[1]))
"""


class TheTerminalEndedBySignalTest(unittest.TestCase):
    def test_it_is_an_interruption_at_the_action_running_or_else_at_the_terminal(self) -> None:
        for name, running, place, code in (
            ("SIGHUP", "install", "tui.install", 129),
            ("SIGTERM", "after", "tui", 143),
            ("SIGHUP", "none", "tui", 129),
        ):
            with self.subTest(name=name, running=running), tempfile.TemporaryDirectory() as home:
                ended = _python(
                    _TERMINAL,
                    name,
                    running,
                    environment={"HOME": home, "AART_CLI_HOME": home},
                )

                self.assertEqual(ended.returncode, -getattr(signal, name), ended.stderr)
                entries = FailureJournal(str(Path(home) / "state")).entries()
                (entry,) = entries.value  # type: ignore[union-attr]
                self.assertEqual(
                    (entry.failure.kind, entry.failure.place, entry.failure.exit_code),
                    (FailureKind.INTERRUPTED, place, code),
                )

    def test_the_shell_tells_which_action_runs_and_both_terminals_hold_the_guard(self) -> None:
        from aart_cli import tui
        from aart_cli.application.author_views import AuthorDraft
        from aart_cli.application.consumer_ui import ConsumerActionKind
        from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSettings
        from aart_cli.tui_consumer import run_consumer_shell
        from tests.author_mode_test import _composed, _environment, _state
        from tests.consumer_shell_test import FakeTerminal

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            told: list[object] = []
            handle = actions.handle

            def handled(command):
                told.append("handling")
                return handle(command)

            with mock.patch.object(actions, "handle", side_effect=handled):
                run_consumer_shell(
                    actions.source(),
                    FakeTerminal(10),
                    state=_state(
                        ConsumerScreen.AUTHOR_WORKSPACE,
                        author_draft=AuthorDraft(workspace=str(env.project / "missing")),
                        rows=("workspace", "save"),
                        cursor=1,
                    ),
                    action_handler=actions,
                    settings_writer=actions.save_settings,
                    on_action_running=told.append,
                )
        self.assertEqual(told, [ConsumerActionKind.AUTHOR_WORKSPACE, "handling", None])

        actions = mock.MagicMock(settings=ConsumerSettings())
        running = actions.journaling_terminations.return_value.__enter__.return_value
        with mock.patch.object(tui, "run_consumer_shell") as shell:
            tui.run_consumer_text(actions)
        self.assertEqual(shell.call_args.kwargs["on_action_running"], running)
        actions.journaling_terminations.return_value.__exit__.assert_called_once()

    def test_the_full_screen_terminal_holds_the_guard_too(self) -> None:
        from aart_cli import tui
        from aart_cli.application.consumer_ui import ConsumerUiState
        from aart_cli.application.consumer_views import ConsumerSettings

        actions = mock.MagicMock(settings=ConsumerSettings())
        running = actions.journaling_terminations.return_value.__enter__.return_value
        with (
            mock.patch("curses.set_escdelay"),
            mock.patch("curses.wrapper", side_effect=lambda callback: callback(mock.Mock())),
            mock.patch.object(
                tui, "run_consumer_shell", return_value=ConsumerUiState(exited=True)
            ) as shell,
        ):
            tui.run_consumer(actions)

        self.assertEqual(shell.call_args.kwargs["on_action_running"], running)
        actions.journaling_terminations.return_value.__exit__.assert_called_once()
