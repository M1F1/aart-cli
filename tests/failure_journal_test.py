"""CP-53, §215, INV-333–INV-336: failures aart-cli meets are journaled, reported and sent.

The journal (`state/failures.sqlite3`) keeps what `domain.failures` keeps; each place that meets a
failure records it without changing how it ends; `consume report` shows the journal; the
telemetry sender sends what waits as `aart_cli.failed` while failures are sent, and skips it
otherwise. `failure_domain_test` holds what a failure is and its fingerprint.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli import _default_telemetry, cli, tui
from aart_cli.application.consumer_ui import ConsumerActionKind
from aart_cli.application.consumer_views import (
    SETTING_ROWS,
    TELEMETRY_ERRORS_ROW,
    ConsumerSettings,
    setting_purpose,
    settings_from_data,
    settings_to_data,
)
from aart_cli.commands import report
from aart_cli.configuration.seed import baked_failures_sent
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.failures import FailureKind, JournaledFailure, failure_of, grouped
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.telemetry import FAILED, contract_moment, parse_failures_sent
from aart_cli.io import failure_journal, telemetry_sync, usage_hook
from aart_cli.io.consumer_settings import read_consumer_settings, write_consumer_settings
from aart_cli.io.failure_journal import (
    FailureJournal,
    note_diagnostics,
    noting,
    record_failure,
)
from aart_cli.io.telemetry_consent import announce_turned_on
from aart_cli.io.telemetry_store import TelemetrySetting
from aart_cli.tui_consumer import render_settings
from tests.credential_fixtures import assignment
from tests.release_default_telemetry_injection_test import _load
from tests.telemetry_sync_test import CLIENT, Clock, FakeServer, Home, _sync

#: `tests/conftest.py`: this module's commands journal their failures, each in a home of its own.
RECORDS_FAILURES = True

MOMENT = "2026-11-02T09:00:00.000000Z"
EVENT = "5b0d6f2e-7c1a-4e8b-9d3f-1a2b3c4d5e6f"
PRIVATE = "/Users/someone/private-project " + assignment("token", "secret")


class OddFailure(Exception):
    """An exception type of a module other than builtins."""


def _failure(place: str = "consume.update", kind: FailureKind = FailureKind.CRASH):
    made = failure_of(
        kind,
        place,
        "KeyError" if kind is FailureKind.CRASH else None,
        (("aart_cli.cli", "main", 362),),
        (),
        None if kind is FailureKind.CRASH else 1,
        "3.11.9",
        "darwin",
    )
    assert made is not None
    return made


def _raise_inside_aart_cli() -> BaseException:
    """A real exception raised inside aart-cli's own package, with this module's frame around it."""

    try:
        contract_moment(datetime(2026, 11, 2))  # no time zone: aart-cli refuses it
    except ValueError as error:
        return error
    raise AssertionError("contract_moment accepted a moment without a time zone")


def _raised_from_one_inside_aart_cli(*, explicit: bool) -> BaseException:
    """An exception this module raised from, or while handling, one aart-cli raised."""

    try:
        try:
            contract_moment(datetime(2026, 11, 2))
        except ValueError as inner:
            if explicit:
                raise RuntimeError(PRIVATE) from inner
            raise RuntimeError(PRIVATE)  # noqa: B904 -- the implicit context is the claim
    except RuntimeError as error:
        return error
    raise AssertionError("contract_moment accepted a moment without a time zone")


def _home(test: unittest.TestCase) -> str:
    temporary = tempfile.TemporaryDirectory()
    test.addCleanup(temporary.cleanup)
    return temporary.name


def _journal(home: str) -> FailureJournal:
    return FailureJournal(str(Path(home) / "state"))


def _entries(home: str) -> tuple[JournaledFailure, ...]:
    entries = _journal(home).entries()
    assert isinstance(entries, Ok), entries
    return entries.value


class TheJournalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = _home(self)
        self.journal = _journal(self.home)

    def test_a_failure_is_kept_waiting_in_a_private_file_and_read_back_whole(self) -> None:
        self.assertIsInstance(self.journal.record(_failure(), MOMENT, "0.24.0", EVENT), Ok)

        self.assertEqual(stat.S_IMODE(os.stat(self.journal.path).st_mode), 0o600)
        self.assertEqual(
            _entries(self.home),
            (JournaledFailure(EVENT, MOMENT, "0.24.0", "waiting", _failure()),),
        )
        counts = self.journal.counts()
        assert isinstance(counts, Ok)
        self.assertEqual(counts.value.waiting, 1)

    def test_only_the_newest_are_kept(self) -> None:
        with mock.patch.object(failure_journal, "MAX_KEPT", 3):
            for number in range(5):
                event = f"5b0d6f2e-7c1a-4e8b-9d3f-00000000000{number}"
                self.journal.record(_failure(f"place-{number}"), MOMENT, "0.24.0", event)

        self.assertEqual(
            [entry.failure.place for entry in _entries(self.home)],
            ["place-4", "place-3", "place-2"],
        )

    def test_settled_failures_no_longer_wait_and_forgetting_deletes_them_all(self) -> None:
        self.journal.record(_failure(), MOMENT, "0.24.0", EVENT)
        now = datetime(2026, 11, 2, tzinfo=timezone.utc)

        self.assertEqual(self.journal.settle((EVENT,), "sent", now), Ok(1))
        self.assertEqual(self.journal.settle((EVENT,), "rejected", now), Ok(0))
        waiting = self.journal.waiting(limit=10)
        self.assertEqual(waiting, Ok(()))
        self.assertEqual(_entries(self.home)[0].state, "sent")
        with self.assertRaises(ValueError):
            self.journal.settle((EVENT,), "waiting", now)

        self.assertIsInstance(self.journal.forget(), Ok)
        self.assertEqual(_entries(self.home), ())

    def test_a_journal_of_another_schema_is_reported_and_never_rewritten(self) -> None:
        Path(self.journal.path).parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(self.journal.path)) as connection:
            connection.execute("PRAGMA user_version = 7")
        before = Path(self.journal.path).read_bytes()

        self.assertIsInstance(self.journal.record(_failure(), MOMENT, "0.24.0", EVENT), Err)
        self.assertIsInstance(self.journal.entries(), Err)
        self.assertEqual(Path(self.journal.path).read_bytes(), before)

    def test_a_row_that_is_not_a_failure_waits_as_none_and_is_never_reported(self) -> None:
        self.journal.record(_failure(), MOMENT, "0.24.0", EVENT)
        with contextlib.closing(sqlite3.connect(self.journal.path)) as connection:
            connection.execute('UPDATE failure SET document = \'{"message": "x"}\'')
            connection.commit()

        waiting = self.journal.waiting(limit=10)
        assert isinstance(waiting, Ok)
        self.assertEqual([item.failure for item in waiting.value], [None])
        self.assertEqual(_entries(self.home), ())


class RecordingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = _home(self)

    def test_a_crash_keeps_aart_clis_frames_and_type_and_none_of_its_message(self) -> None:
        error = _raise_inside_aart_cli()

        with mock.patch.object(telemetry_sync, "maybe_sync") as synced:
            self.assertTrue(
                record_failure(self.home, FailureKind.CRASH, "consume.update", error=error)
            )

        (entry,) = _entries(self.home)
        self.assertEqual(entry.failure.exception, "ValueError")
        self.assertEqual(len(entry.failure.frames), 1)
        self.assertTrue(entry.failure.frames[0].startswith("aart_cli.domain.telemetry:"))
        self.assertIn(entry.failure.platform, {"darwin", "linux", "other"})
        synced.assert_called_once_with(self.home)
        raw = Path(_journal(self.home).path).read_bytes()
        self.assertNotIn(str(error).encode(), raw)
        self.assertNotIn(b"failure_journal_test", raw)

    def test_what_a_crash_was_raised_from_is_kept_by_type_and_frames_never_its_message(
        self,
    ) -> None:
        """B-267: an explicit cause, or the exception being handled, in order."""

        for explicit in (True, False):
            with self.subTest(explicit=explicit):
                home = _home(self)
                error = _raised_from_one_inside_aart_cli(explicit=explicit)

                record_failure(home, FailureKind.CRASH, "consume.update", error=error, sync=False)

                (entry,) = _entries(home)
                self.assertEqual(entry.failure.exception, "RuntimeError")
                self.assertEqual(entry.failure.frames, ())
                (cause,) = entry.failure.causes
                self.assertEqual(cause.exception, "ValueError")
                self.assertEqual(len(cause.frames), 1)
                self.assertTrue(cause.frames[0].startswith("aart_cli.domain.telemetry:"))
                raw = Path(_journal(home).path).read_bytes()
                self.assertNotIn(PRIVATE.encode(), raw)
                self.assertNotIn(str(error.__cause__ or error.__context__).encode(), raw)

    def test_a_context_raised_from_none_is_not_a_cause_and_a_cycle_ends(self) -> None:
        try:
            try:
                raise KeyError("x")
            except KeyError:
                raise OddFailure(PRIVATE) from None
        except OddFailure as error:
            hidden = error
        first, second = OddFailure("a"), ValueError("b")
        first.__cause__, second.__cause__ = second, first

        record_failure(self.home, FailureKind.CRASH, "tui", error=hidden, sync=False)
        record_failure(self.home, FailureKind.CRASH, "tui", error=first, sync=False)

        hidden_entry, cycle_entry = sorted(
            _entries(self.home), key=lambda entry: len(entry.failure.causes)
        )
        self.assertEqual(hidden_entry.failure.causes, ())
        self.assertEqual([cause.exception for cause in cycle_entry.failure.causes], ["ValueError"])

    def test_a_long_chain_keeps_the_nearest_five(self) -> None:
        error: BaseException = ValueError("0")
        for number in range(1, 9):
            outer = OSError(str(number))
            outer.__cause__ = error
            error = outer

        record_failure(self.home, FailureKind.CRASH, "tui", error=error, sync=False)

        (entry,) = _entries(self.home)
        self.assertEqual(entry.failure.exception, "OSError")
        self.assertEqual(
            [cause.exception for cause in entry.failure.causes],
            ["OSError", "OSError", "OSError", "OSError", "OSError"],
        )

    def test_a_type_outside_builtins_is_named_with_its_module_and_a_local_one_is_not(
        self,
    ) -> None:
        class Local(Exception):
            pass

        record_failure(self.home, FailureKind.CRASH, "tui", error=OddFailure(PRIVATE), sync=False)
        record_failure(self.home, FailureKind.CRASH, "tui", error=Local(PRIVATE), sync=False)

        self.assertEqual(
            [entry.failure.exception for entry in _entries(self.home)],
            ["Exception", f"{__name__}.OddFailure"],
        )

    def test_it_never_raises_and_keeps_nothing_it_cannot(self) -> None:
        blocked = Path(self.home) / "state"
        blocked.write_text("not a directory", encoding="utf-8")

        for home, place in ((self.home, "consume.update"), ("relative", "tui"), (self.home, "")):
            with self.subTest(home=home, place=place):
                self.assertFalse(record_failure(home, FailureKind.ERROR, place, sync=False))

    def test_codes_are_noted_only_inside_noting(self) -> None:
        reported = (
            Diagnostic(DiagnosticCode("registry-unreachable"), Severity.ERROR, PRIVATE),
            Diagnostic(DiagnosticCode("no-source-configured"), Severity.ERROR, "x"),
        )
        note_diagnostics(reported)
        with noting() as codes:
            note_diagnostics(reported)
            with noting() as inner:
                note_diagnostics(reported[:1])

        self.assertEqual(codes, ["registry-unreachable", "no-source-configured"])
        self.assertEqual(inner, ["registry-unreachable"])


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(message=st.text(min_size=1, max_size=60), place=st.sampled_from(("tui", "consume.list")))
def test_no_message_reaches_the_journal(message: str, place: str) -> None:
    """INV-333: whatever an exception says, the journal holds none of it."""

    with tempfile.TemporaryDirectory() as home:
        error = RuntimeError(f"[{message}]")
        assert record_failure(home, FailureKind.CRASH, place, error=error, sync=False)
        raw = Path(home, "state", "failures.sqlite3").read_bytes()
        assert f"[{message}]".encode() not in raw


class _Command:
    """`cli.main` in an application home of its own."""

    def __init__(self, test: unittest.TestCase) -> None:
        self.home = _home(test)
        self.user = _home(test)
        self.environment = {"HOME": self.user, "AART_CLI_HOME": self.home}

    def __call__(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(os.environ, self.environment),
            mock.patch.object(telemetry_sync, "spawn_sync", return_value=False),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class ACommandsFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run = _Command(self)

    def test_a_nonzero_exit_is_an_error_with_its_place_code_and_diagnostics(self) -> None:
        code, out, _ = self.run("consume", "list", "--json")

        self.assertEqual(code, 1)
        (entry,) = _entries(self.run.home)
        self.assertEqual(
            (entry.failure.kind, entry.failure.place), (FailureKind.ERROR, "consume.list")
        )
        self.assertEqual(entry.failure.exit_code, 1)
        self.assertEqual(
            entry.failure.diagnostics,
            tuple(item["code"] for item in json.loads(out)["diagnostics"]),
        )

    def test_a_crash_is_recorded_and_raised_as_it_was(self) -> None:
        def broken(request):
            raise KeyError(PRIVATE)

        with mock.patch.dict(cli.DISPATCH, {"telemetry": broken}), self.assertRaises(KeyError):
            self.run("consume", "telemetry", "status")

        (entry,) = _entries(self.run.home)
        self.assertEqual(entry.failure.place, "consume.telemetry.status")
        self.assertEqual(entry.failure.exception, "KeyError")
        self.assertIn("aart_cli.cli:_dispatch", " ".join(entry.failure.frames))
        self.assertNotIn(PRIVATE.encode(), Path(_journal(self.run.home).path).read_bytes())

    def test_ctrl_c_is_an_interruption_and_still_ends_the_command(self) -> None:
        def interrupted(request):
            raise KeyboardInterrupt

        with (
            mock.patch.dict(cli.DISPATCH, {"usage": interrupted}),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run("consume", "usage", "show")

        self.assertEqual(_entries(self.run.home)[0].failure.kind, FailureKind.INTERRUPTED)

    def test_success_records_nothing(self) -> None:
        code, _, _ = self.run("consume", "report")

        self.assertEqual(code, 0)
        self.assertFalse(_journal(self.run.home).exists())

    def test_the_place_is_the_commands_words_never_an_argument(self) -> None:
        parser = cli.build_parser()
        for argv, place in (
            (["consume", "update", "corp/skill/secret-name"], "consume.update"),
            (["consume", "registry", "list"], "consume.registry.list"),
            (["consume", "telemetry", "errors", "off"], "consume.telemetry.errors"),
            (["maintain", "candidate", "list"], "maintain.candidate.list"),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(report.command_place(parser.parse_args(argv)), place)


class RecordingNeverChangesWhatFailedTest(unittest.TestCase):
    """INV-335: exit code, stdout and stderr are what they are without the journal."""

    def test_a_failing_command_ends_the_same_whatever_the_journal_does(self) -> None:
        run = _Command(self)
        without = mock.patch.object(report, "record_in_application_home", lambda *a, **k: None)
        with without:
            expected = run("consume", "list")
        self.assertEqual(run("consume", "list"), expected)
        self.assertTrue(_journal(run.home).exists())
        with mock.patch.object(failure_journal.FailureJournal, "record", side_effect=OSError):
            self.assertEqual(run("consume", "list"), expected)
        with mock.patch.object(failure_journal, "failure_of", side_effect=RuntimeError):
            self.assertEqual(run("consume", "list"), expected)

    def test_a_hook_that_crashes_stays_silent_exits_zero_and_is_journaled(self) -> None:
        home = _home(self)
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(usage_hook, "record", side_effect=RuntimeError(PRIVATE)),
            mock.patch.object(telemetry_sync, "maybe_sync") as synced,
            mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}"))),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(usage_hook.main(["claude", home]), 0)

        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))
        self.assertEqual(
            [(e.failure.kind, e.failure.place) for e in _entries(home)],
            [(FailureKind.CRASH, "usage-hook")],
        )
        synced.assert_called_once_with(home)

    def test_the_senders_crash_waits_for_the_next_synchronisation(self) -> None:
        home = _home(self)
        with (
            mock.patch.object(telemetry_sync, "synchronise", side_effect=RuntimeError(PRIVATE)),
            mock.patch.object(telemetry_sync, "maybe_sync") as synced,
        ):
            self.assertEqual(telemetry_sync.main([home]), 0)

        self.assertEqual(_entries(home)[0].failure.place, "telemetry-sync")
        synced.assert_not_called()

    def test_the_terminal_reports_as_it_did_and_journals_the_crash(self) -> None:
        home = _home(self)
        error = _raise_inside_aart_cli()
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"AART_CLI_HOME": home}),
            mock.patch.object(telemetry_sync, "spawn_sync", return_value=False),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(tui._render_internal_failure(error, user_home=home), 2)

        self.assertEqual(out.getvalue().splitlines(), list(tui.internal_failure_lines(error)))
        self.assertEqual(_entries(home)[0].failure.place, "tui")


class TheTerminalsActionsTest(unittest.TestCase):
    def test_an_action_that_stopped_is_an_error_at_its_place(self) -> None:
        from tests.author_mode_test import _composed, _environment

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            with mock.patch.object(telemetry_sync, "spawn_sync", return_value=False):
                actions.record_action_failed(ConsumerActionKind.INSTALL)

            (entry,) = _entries(str(env.paths.data_root))
        self.assertEqual(
            (entry.failure.kind, entry.failure.place), (FailureKind.ERROR, "tui.install")
        )

    def test_the_shell_tells_each_action_that_stopped_and_both_terminals_journal_it(self) -> None:
        from aart_cli.application.author_views import AuthorDraft
        from aart_cli.application.consumer_views import ConsumerScreen
        from aart_cli.tui_consumer import run_consumer_shell
        from tests.author_mode_test import _composed, _environment, _state
        from tests.consumer_shell_test import FakeTerminal

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            stopped: list[ConsumerActionKind] = []
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
                on_action_failed=stopped.append,
            )
        self.assertEqual(stopped, [ConsumerActionKind.AUTHOR_WORKSPACE])
        actions = mock.Mock(settings=ConsumerSettings())
        with mock.patch.object(tui, "run_consumer_shell") as shell:
            tui.run_consumer_text(actions)
        self.assertEqual(shell.call_args.kwargs["on_action_failed"], actions.record_action_failed)


class TheReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run = _Command(self)
        journal = _journal(self.run.home)
        moments = ("2026-11-01T08:00:00.000000Z", "2026-11-02T08:00:00.000000Z")
        for number, (version, moment) in enumerate(
            (("0.23.0", moments[0]), ("0.24.0", moments[1]))
        ):
            journal.record(_failure(), moment, version, f"{EVENT[:-1]}{number}")
        journal.record(
            _failure("consume.list", FailureKind.ERROR),
            "2026-11-01T09:00:00.000000Z",
            "0.24.0",
            f"{EVENT[:-1]}9",
        )

    def test_it_groups_by_fingerprint_newest_first_as_a_block_to_paste(self) -> None:
        code, out, _ = self.run("consume", "report")

        self.assertEqual(code, 0, out)
        self.assertIn("```", out)
        first = out.index("crash in consume.update: 2 times")
        self.assertLess(first, out.index("error in consume.list: once"))
        self.assertIn("aart-cli 0.24.0, 0.23.0", out)
        self.assertIn(_failure().fingerprint, out)
        self.assertIn("aart_cli.cli:main:362", out)

    def test_it_says_what_each_crash_was_raised_from_after_its_frames(self) -> None:
        caused = failure_of(
            FailureKind.CRASH,
            "consume.install",
            "RuntimeError",
            (("aart_cli.cli", "main", 362),),
            (),
            None,
            "3.12.4",
            "linux",
            causes=(
                ("OSError", (("aart_cli.io.receipt_store", "_write", 412),)),
                ("PermissionError", ()),
            ),
        )
        assert caused is not None
        _journal(self.run.home).record(
            caused, "2026-11-03T08:00:00.000000Z", "0.25.0", f"{EVENT[:-1]}8"
        )

        out = self.run("consume", "report")[1]

        block = out[out.index("crash in consume.install") :]
        self.assertIn(
            "   frames, innermost last:\n"
            "     aart_cli.cli:main:362\n"
            "   raised from OSError, frames innermost last:\n"
            "     aart_cli.io.receipt_store:_write:412\n"
            "   raised from PermissionError\n",
            block,
        )
        self.assertNotIn("raised from", out[: out.index("crash in consume.install")])

    def test_it_says_printing_sends_nothing_and_never_that_nothing_was_sent(self) -> None:
        """While telemetry is on a journaled failure may already have been sent (§215): the
        report itself sends nothing, and where to see what is sent is the status."""

        out = self.run("consume", "report")[1]

        self.assertEqual(
            out.splitlines()[0],
            "aart-cli failures, seen last first. Printing this sends nothing; "
            "`consume telemetry status` says whether failures are sent.",
        )
        self.assertNotIn("left this machine", out)

    def test_json_says_the_same_and_limit_bounds_it(self) -> None:
        code, out, _ = self.run("consume", "report", "--json", "--limit", "1")

        self.assertEqual(code, 0, out)
        document = json.loads(out)
        (group,) = document["failures"]
        self.assertEqual(
            (group["place"], group["count"], group["versions"]),
            ("consume.update", 2, ["0.24.0", "0.23.0"]),
        )
        self.assertEqual(group["failure"], _failure().document())
        self.assertEqual(self.run("consume", "report", "--limit", "0")[0], 1)

    def test_grouping_counts_every_entry_once(self) -> None:
        entries = _entries(self.run.home)
        groups = grouped(entries)

        self.assertEqual(sum(group.count for group in groups), len(entries))
        self.assertEqual(groups[0].first_seen, "2026-11-01T08:00:00.000000Z")
        self.assertEqual(groups[0].last_seen, "2026-11-02T08:00:00.000000Z")

    def test_an_empty_journal_says_so(self) -> None:
        empty = _Command(self)

        self.assertEqual(empty("consume", "report")[1], "No failures are journaled here.\n")


class SendingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Home(self)
        self.journal = FailureJournal(self.home.state)
        self.server = FakeServer()
        self.clock = Clock()

    def _record(self, number: int, version: str = "0.24.0", place: str = "consume.update") -> str:
        event = f"5b0d6f2e-7c1a-4e8b-9d3f-{number:012d}"
        self.journal.record(_failure(place), MOMENT, version, event)
        return event

    def _states(self) -> list[str]:
        return [entry.state for entry in _entries(self.home.path)]

    def test_failures_journaled_before_telemetry_was_on_are_sent_once_it_is(self) -> None:
        first = self._record(1)
        self.assertFalse(_sync(self.home, self.server, self.clock).started)

        self.home.enable()
        report = _sync(self.home, self.server, self.clock)

        self.assertEqual(report.sent, 1)
        (request,) = self.server.requests
        (event,) = request["events"]
        self.assertEqual(
            (event["event_id"], event["event_type"], event["source"]),
            (first, FAILED, "aart_cli"),
        )
        self.assertEqual(event["failure"], _failure().document())
        self.assertEqual(request["client_id"], CLIENT)
        self.assertEqual(self._states(), ["sent"])
        self.clock.advance(hours=1)
        self.assertFalse(_sync(self.home, self.server, self.clock).started)

    def test_each_batch_is_from_one_version_and_says_which(self) -> None:
        self.home.enable()
        self._record(1, "0.23.0")
        self._record(2, "0.24.0")
        self._record(3, "0.23.0")

        _sync(self.home, self.server, self.clock)

        self.assertEqual(
            [(r["client_version"], len(r["events"])) for r in self.server.requests],
            [("0.23.0", 2), ("0.24.0", 1)],
        )

    def test_turned_off_what_waits_is_skipped_and_never_sent(self) -> None:
        self.home.enable()
        self._record(1)
        write_consumer_settings(ConsumerSettings(telemetry_errors=False), data_root=self.home.path)
        self.home.use()

        report = _sync(self.home, self.server, self.clock)

        self.assertEqual((report.sent, report.skipped), (1, 1))
        self.assertNotIn(FAILED, json.dumps(self.server.requests))
        self.assertEqual(self._states(), ["skipped"])

    def test_a_rejected_failure_is_not_sent_again_and_a_down_server_keeps_it(self) -> None:
        self.home.enable()
        self._record(1)
        self.server.down = True
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual((report.sent, report.reason), (0, "unavailable"))
        self.assertEqual(self._states(), ["waiting"])

        self.server.down, self.server.status = False, 422
        self.clock.advance(hours=2)
        report = _sync(self.home, self.server, self.clock, force=True)

        self.assertEqual(report.rejected, 1)
        self.assertEqual(self._states(), ["rejected"])

    def test_a_failure_waiting_makes_a_synchronisation_due(self) -> None:
        self.home.enable()
        spawned: list[str] = []
        self.assertFalse(telemetry_sync.maybe_sync(self.home.path, spawn=spawned.append))

        self._record(1)

        telemetry_sync.maybe_sync(self.home.path, now=self.clock, spawn=spawned.append)
        self.assertEqual(spawned, [self.home.path])


class TheChoiceTest(unittest.TestCase):
    def test_the_build_sets_the_default_and_refuses_what_it_cannot_mean(self) -> None:
        self.assertEqual(_default_telemetry.ERRORS, "")
        self.assertTrue(baked_failures_sent())
        self.assertFalse(baked_failures_sent("off"))
        self.assertFalse(baked_failures_sent("maybe"))
        self.assertIsInstance(parse_failures_sent("maybe"), Err)

    def test_the_injector_bakes_it_and_the_release_records_it(self) -> None:
        injector = _load("inject_default_telemetry")
        namespace: dict[str, object] = {}
        exec(  # noqa: S102
            compile(injector.render_from("", "test", errors=" OFF "), "<rendered>", "exec"),
            namespace,
        )
        self.assertEqual((namespace["UNMANAGED_USES"], namespace["ERRORS"]), ("", "off"))
        with self.assertRaises(SystemExit):
            injector.render_from("", "test", errors="sometimes")
        root = Path(__file__).resolve().parent.parent
        workflow = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        variable = "AART_CLI_TELEMETRY_ERRORS"
        self.assertEqual(workflow.count(f"{variable}: ${{{{ vars.{variable} }}}}"), 2)
        release = _load("release")
        for raw in ("", "on", "TRUE", "off", " False\n"):
            with self.subTest(raw=raw), mock.patch.dict(os.environ, {variable: raw}):
                self.assertEqual(release.telemetry_errors_value(), parse_failures_sent(raw).value)

    def test_a_persons_choice_overrules_the_build_and_is_kept_only_once_made(self) -> None:
        with mock.patch.object(_default_telemetry, "ERRORS", "off"):
            self.assertFalse(ConsumerSettings().sends_failures)
            self.assertTrue(ConsumerSettings(telemetry_errors=True).sends_failures)
            self.assertIs(ConsumerSettings().toggled(TELEMETRY_ERRORS_ROW).telemetry_errors, True)
        self.assertIn(TELEMETRY_ERRORS_ROW, SETTING_ROWS)
        self.assertIs(ConsumerSettings().toggled(TELEMETRY_ERRORS_ROW).telemetry_errors, False)
        self.assertNotIn("telemetry_failures", settings_to_data(ConsumerSettings()))
        for chosen in (True, False):
            data = settings_to_data(ConsumerSettings(telemetry_errors=chosen))
            self.assertEqual(
                settings_from_data(data), Ok(ConsumerSettings(telemetry_errors=chosen))
            )
        self.assertIsInstance(settings_from_data({"telemetry_failures": "yes"}), Err)

    def test_settings_draws_it_under_telemetry_and_says_what_is_sent(self) -> None:
        drawn = "\n".join(render_settings(ConsumerSettings(), focus=TELEMETRY_ERRORS_ROW))

        self.assertIn("> Failures aart-cli met: sent", drawn)
        off = "\n".join(render_settings(ConsumerSettings(telemetry_errors=False)))
        self.assertIn("Failures aart-cli met: not sent", off)
        self.assertIn("never a message", setting_purpose(TELEMETRY_ERRORS_ROW))

    def test_the_command_keeps_it_status_reports_it_and_forget_deletes_the_journal(self) -> None:
        run = _Command(self)
        before = replace(ConsumerSettings(), show_updates=False)
        write_consumer_settings(before, data_root=run.home)

        code, out, _ = run("consume", "telemetry", "errors", "off", "--json")

        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["errors"], {"sent": False, "chosen": True})
        self.assertEqual(
            read_consumer_settings(run.home), Ok(replace(before, telemetry_errors=False))
        )
        _, out, _ = run("consume", "telemetry", "status")
        self.assertIn("failures aart-cli met: not sent (your choice)", out)
        _journal(run.home).record(_failure(), MOMENT, "0.24.0", EVENT)
        _, out, _ = run("consume", "telemetry", "status", "--json")
        self.assertEqual(json.loads(out)["journal"]["waiting"], 1)

        code, out, _ = run("consume", "telemetry", "disable", "--forget")

        self.assertEqual(code, 0, out)
        self.assertEqual(_entries(run.home), ())

    def test_turning_on_says_failures_are_sent_and_how_to_stop_it(self) -> None:
        setting = TelemetrySetting(True, "https://telemetry.example.com", CLIENT, "key")
        for failures in (True, False):
            said: list[str] = []
            announce_turned_on(setting, said.append, unmanaged=False, failures=failures)
            self.assertEqual("errors off" in " ".join(said), failures)


if __name__ == "__main__":
    unittest.main()
