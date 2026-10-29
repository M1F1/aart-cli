"""CP-50, D-505: a build that names a server starts with telemetry on, and turning it on sends
Activity's history, each record once (§213, INV-322).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli import _default_telemetry, cli
from aart_cli.application.consumer_views import ActivityRecord, project_receipt_detail
from aart_cli.cli_parser import build_parser
from aart_cli.domain.result import Ok
from aart_cli.domain.telemetry import history_event_id
from aart_cli.io import telemetry_sync
from aart_cli.io.activity_store import ActivityDatabase
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.io.telemetry_consent import queue_history, turn_on, turn_on_by_default
from aart_cli.io.telemetry_store import TelemetryOutbox, WaitingEvent
from aart_cli.io.usage_hook import record
from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.consumer_activity_test import lifecycle_outcome
from tests.consumer_application_e2e_test import _actions
from tests.telemetry_sync_test import CLIENT, Clock, FakeServer, Home, _sync

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SERVER = "https://telemetry.example.com"
EARLIER = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


def _hook(home: Home, name: str = "github") -> None:
    payload = json.dumps({"tool_name": f"mcp__{name}__search", "cwd": "/work/project"}).encode()
    with mock.patch.object(telemetry_sync, "spawn_sync", return_value=False):
        assert record("claude", home.path, payload, now=EARLIER)


def _action(home: Home) -> None:
    detail = project_receipt_detail(ActivityRecord("2026-10-02T10:00:00Z", lifecycle_outcome()))
    with mock.patch.object(telemetry_sync, "spawn_sync", return_value=False):
        assert isinstance(LocalReceiptStore(home.state).record_action(detail), Ok)


def _ids(home: Home) -> list[str]:
    waiting = home.outbox.waiting(limit=10_000)
    assert isinstance(waiting, Ok)
    return [item.event_id for item in waiting.value]


def _on(home: Home) -> None:
    assert isinstance(turn_on(home.path, SERVER, CLIENT, sync=lambda _: False), Ok)


class TheEventIdTest(unittest.TestCase):
    @given(
        key=st.text(min_size=1, max_size=40),
        record=st.text(min_size=1, max_size=20),
        index=st.integers(0, 50),
    )
    def test_one_record_has_one_id_and_no_other_record_shares_it(
        self, key: str, record: str, index: int
    ) -> None:
        drawn = history_event_id(key, record, index)
        self.assertIsNotNone(_UUID.fullmatch(drawn))
        self.assertEqual(history_event_id(key, record, index), drawn)
        self.assertNotEqual(history_event_id(key + "x", record, index), drawn)
        self.assertNotEqual(history_event_id(key, record + "x", index), drawn)
        self.assertNotEqual(history_event_id(key, record, index + 1), drawn)

    def test_nothing_unnamed_has_an_id(self) -> None:
        for key, record_name, index in (("", "use-1", 0), ("k", "", 0), ("k", "use-1", -1)):
            with self.subTest(key=key, record=record_name, index=index):
                with self.assertRaises(ValueError):
                    history_event_id(key, record_name, index)


class TurningItOnSendsTheHistoryTest(unittest.TestCase):
    def test_what_activity_holds_is_queued_with_its_own_moments(self) -> None:
        home = Home(self)
        _hook(home)
        _hook(home, "my-own-mcp")
        _action(home)
        self.assertFalse(home.outbox.exists())

        _on(home)

        waiting = home.outbox.waiting(limit=100).value
        self.assertEqual(len(waiting), 3)
        self.assertEqual(
            sorted(item.occurred_at for item in waiting),
            [
                "2026-10-01T09:30:00.000000Z",
                "2026-10-01T09:30:00.000000Z",
                "2026-10-02T10:00:00.000000Z",
            ],
        )

    def test_a_record_queued_live_and_again_from_the_history_is_kept_once(self) -> None:
        home = Home(self)
        _on(home)
        _hook(home)
        _action(home)
        live = _ids(home)
        self.assertEqual(len(live), 2)
        self.assertIsInstance(queue_history(home.path), Ok)
        self.assertEqual(_ids(home), live)

    def test_turning_it_on_again_after_forgetting_sends_nothing_twice(self) -> None:
        home = Home(self)
        server, clock = FakeServer(), Clock()
        _hook(home)
        _on(home)
        _sync(home, server, clock)
        home.outbox.disable(forget=True)
        self.assertEqual(home.counts().sent, 0)
        _hook(home)
        _on(home)
        clock.advance(minutes=11)
        _sync(home, server, clock)
        self.assertEqual(len(server.stored), 2)
        self.assertEqual(sum(len(r["events"]) for r in server.requests), 3)

    def test_a_receipt_activity_cannot_decode_is_skipped(self) -> None:
        home = Home(self)
        _hook(home)
        ActivityDatabase(home.state).record_action("2026-10-02T10:00:00+00:00", b"not json")
        _on(home)
        self.assertEqual(home.counts().waiting, 1)

    @settings(max_examples=40, deadline=None)
    @given(steps=st.lists(st.sampled_from(("on", "off", "forget", "use", "action")), max_size=12))
    def test_the_outbox_holds_each_record_once_if_recorded_while_on_or_there_when_turned_on(
        self, steps: list[str]
    ) -> None:
        home = Home(self)
        on = False
        records: list[int] = []  # events each Activity record amounts to, in order
        covered: set[int] = set()
        for step in steps:
            if step == "on":
                _on(home)
                on = True
                covered |= set(range(len(records)))
            elif step in ("off", "forget"):
                home.outbox.disable(forget=step == "forget")
                on = False
                if step == "forget":
                    covered = set()
            else:
                if step == "use":
                    _hook(home)
                else:
                    _action(home)
                records.append(1)
                if on:
                    covered.add(len(records) - 1)
        self.assertEqual(home.counts().waiting, sum(records[index] for index in covered))


class TheBuildTurnsItOnOnceTest(unittest.TestCase):
    def test_a_build_without_a_server_turns_nothing_on(self) -> None:
        home = Home(self)
        _hook(home)
        self.assertIsNone(turn_on_by_default(home.path, None, sync=self.fail))
        self.assertFalse(home.outbox.exists())

    def test_a_build_with_a_server_turns_it_on_where_nobody_decided_and_sends(self) -> None:
        home = Home(self)
        _hook(home)
        started: list[str] = []
        setting = turn_on_by_default(home.path, SERVER, sync=lambda h: started.append(h) is None)
        assert setting is not None
        self.assertEqual((setting.enabled, setting.endpoint), (True, SERVER))
        self.assertEqual(home.counts().waiting, 1)
        self.assertEqual(started, [home.path])
        self.assertIsNone(turn_on_by_default(home.path, SERVER, sync=self.fail))

    def test_a_person_who_turned_it_off_is_never_turned_on_again(self) -> None:
        for forget in (False, True):
            with self.subTest(forget=forget):
                home = Home(self)
                _hook(home)
                self.assertIsInstance(home.outbox.disable(forget=forget), Ok)
                self.assertIsNone(turn_on_by_default(home.path, SERVER, sync=self.fail))
                self.assertFalse(home.outbox.setting().value.enabled)
                self.assertEqual(home.counts().waiting, 0)
                _hook(home)
                self.assertEqual(home.counts().waiting, 0)

    def test_many_first_starts_at_once_turn_it_on_once(self) -> None:
        home = Home(self)
        _hook(home)
        results: list[object] = []
        barrier = threading.Barrier(8)

        def start() -> None:
            barrier.wait(5)
            results.append(turn_on_by_default(home.path, SERVER, sync=lambda _: False))

        threads = [threading.Thread(target=start) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(home.counts().waiting, 1)

    def test_a_broken_outbox_never_fails_the_start(self) -> None:
        home = Home(self)
        Path(home.state).mkdir(parents=True, exist_ok=True)
        Path(home.outbox.path).write_bytes(b"not a database")
        self.assertIsNone(turn_on_by_default(home.path, SERVER, sync=self.fail))


class TheCommandLineSaysSoTest(unittest.TestCase):
    def setUp(self) -> None:
        user = tempfile.TemporaryDirectory()
        self.addCleanup(user.cleanup)
        application = tempfile.TemporaryDirectory()
        self.addCleanup(application.cleanup)
        self.user_home = user.name
        self.home = application.name
        patches = (
            mock.patch.dict(os.environ, {"AART_CLI_HOME": self.home, "HOME": self.user_home}),
            mock.patch.object(_default_telemetry, "ENDPOINT", SERVER),
            mock.patch.object(telemetry_sync, "spawn_sync", return_value=False),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def _outbox(self) -> Path:
        return Path(self.home) / "state" / "telemetry.sqlite3"

    def test_the_first_consume_command_turns_it_on_and_says_so_on_stderr_once(self) -> None:
        code, out, err = self._run("consume", "usage", "show", "--json")
        self.assertEqual(code, 0)
        json.loads(out)
        self.assertIn(f"Telemetry is on: this aart-cli sends to {SERVER}", err)
        self.assertIn("consume telemetry disable", err)
        self.assertTrue(self._outbox().exists())
        _, _, again = self._run("consume", "usage", "show")
        self.assertNotIn("Telemetry is on", again)

    def test_a_first_telemetry_command_decides_nothing_by_itself(self) -> None:
        self._run("consume", "telemetry", "status")
        self.assertFalse(self._outbox().exists())
        code, _, err = self._run("consume", "telemetry", "disable")
        self.assertEqual(code, 0)
        self.assertNotIn("Telemetry is on", err)
        self._run("consume", "usage", "show")
        _, out, _ = self._run("consume", "telemetry", "status", "--json")
        self.assertFalse(json.loads(out)["enabled"])

    def test_only_a_consume_command_that_may_send_and_does_not_decide_turns_it_on(self) -> None:
        parser = build_parser()
        for argv, turns in (
            (["consume", "usage", "show"], True),
            (["consume", "update"], True),
            (["consume", "update", "--offline"], False),
            (["consume", "telemetry", "status"], False),
            (["consume", "telemetry", "disable"], False),
        ):
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertEqual(cli._turns_telemetry_on(args, cli._to_request(args)), turns)

    def test_enable_queues_the_history_and_says_so(self) -> None:
        home = Home(self)
        _hook(home)
        with mock.patch.dict(os.environ, {"AART_CLI_HOME": home.path}):
            code, out, _ = self._run("consume", "telemetry", "enable")
        self.assertEqual(code, 0)
        self.assertIn("1 event(s) Activity already held", out)
        self.assertEqual(home.counts().waiting, 1)


class TheProductionPathsTest(unittest.TestCase):
    """A real install from a build that names a server, and the TUI's composition."""

    def setUp(self) -> None:
        for patch in (
            mock.patch.object(_default_telemetry, "ENDPOINT", SERVER),
            mock.patch.object(telemetry_sync, "spawn_sync", return_value=False),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    @staticmethod
    def _waiting(env) -> tuple[WaitingEvent, ...]:
        waiting = TelemetryOutbox(f"{env.paths.data_root}/state").waiting(limit=100)
        assert isinstance(waiting, Ok)
        return waiting.value

    def test_an_install_the_build_turned_it_on_for_is_queued_once(self) -> None:
        with _environment() as env:
            with contextlib.redirect_stderr(io.StringIO()) as said:
                _, review = env.run("consume", "install", COORDINATE, "--profile", "claude")
            self.assertIn("Telemetry is on", said.getvalue())
            self.assertEqual(self._waiting(env), ())
            with contextlib.redirect_stderr(io.StringIO()) as said:
                code, payload = env.run(
                    "consume",
                    "install",
                    COORDINATE,
                    "--profile",
                    "claude",
                    "--expect",
                    review["review_digest"],
                    "--yes",
                )
            self.assertEqual(code, 0, payload)
            self.assertNotIn("Telemetry is on", said.getvalue())
            installed = [item.event for item in self._waiting(env)]
            self.assertEqual(
                [(e.event_type, e.artifact_id) for e in installed if e is not None],
                [("artifact.installed", "code-review")],
            )
            self.assertEqual(
                queue_history(str(env.paths.data_root)), Ok(0), "the history holds it already"
            )

    def test_the_tui_turns_it_on_where_nobody_decided_once(self) -> None:
        with _environment() as env:
            actions = _actions(env)
            setting = actions.turn_telemetry_on_by_default()
            assert setting is not None
            self.assertEqual((setting.enabled, setting.endpoint), (True, SERVER))
            self.assertIsNone(actions.turn_telemetry_on_by_default())


if __name__ == "__main__":
    unittest.main()
