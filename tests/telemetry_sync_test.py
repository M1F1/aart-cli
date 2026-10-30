"""CP-50: the outbox, and sending it (§213, INV-322, INV-324–INV-326, INV-328).

The scenarios are the owner's brief's acceptance tests, against a controlled clock and a fake
`post`; `http_post` and the detached process run against a real loopback HTTP server that
follows docs/telemetry-api-v1.md. The server's own tests (aart-cli-telemetry-server) hold the server
side: storing once, deduplication and the dashboard.
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    ActivityRecord,
    ConsumerSettings,
    project_receipt_detail,
)
from aart_cli.domain.artifact_usage import ArtifactUse, UsageKind
from aart_cli.domain.harness import McpRegistration, Scope, mcp_target
from aart_cli.domain.result import Ok
from aart_cli.domain.telemetry import BATCH_PATH, BATCH_SIZE, SyncState
from aart_cli.io import telemetry_sync
from aart_cli.io.consumer_settings import write_consumer_settings
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.io.telemetry_store import OutboxCounts, TelemetryOutbox
from aart_cli.io.telemetry_sync import http_post, maybe_sync, synchronise
from aart_cli.io.usage_hook import record
from tests.consumer_activity_test import lifecycle_outcome
from tests.receipt_store_test import COORDINATE, receipt

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "aart_cli" / "io" / "usage_hook.py"
START = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)
CLIENT = "0b6f4d1e-8f8a-4a43-9a52-2f0f5d0f6a11"


class Clock:
    def __init__(self, moment: datetime = START) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta: float) -> None:
        self.moment += timedelta(**delta)


class FakeServer:
    """A `post` that follows the contract, with a switch for being down."""

    def __init__(self) -> None:
        self.stored: dict[str, dict] = {}
        self.requests: list[dict] = []
        self.down = False
        self.status: int | None = None
        self.lose_answer = False

    def __call__(self, url: str, body: bytes, timeout: float) -> tuple[int | None, object]:
        assert url.endswith(BATCH_PATH)
        if self.down:
            return None, None
        document = json.loads(body)
        self.requests.append(document)
        if self.status is not None:
            return self.status, None
        for event in document["events"]:
            self.stored.setdefault(event["event_id"], event)
        if self.lose_answer:
            return None, None
        return 200, {"acknowledged_event_ids": [e["event_id"] for e in document["events"]]}


def _use(name: str = "github", harness: str = "claude") -> ArtifactUse:
    return ArtifactUse(harness, UsageKind.MCP, name, "/work/project")


class Home:
    """An application home with one installed MCP, `github`, registered in Claude Code."""

    def __init__(self, test: unittest.TestCase) -> None:
        temporary = tempfile.TemporaryDirectory()
        test.addCleanup(temporary.cleanup)
        self.path = temporary.name
        self.state = str(Path(self.path) / "state")
        self.outbox = TelemetryOutbox(self.state)
        self.records = 0
        installed = receipt(
            registrations=(
                McpRegistration(mcp_target("claude", Scope.USER), "github", "/opt/github/launch"),
            )
        )
        recorded = LocalReceiptStore(self.state).record_installation(COORDINATE, installed)
        assert isinstance(recorded, Ok), recorded

    def enable(self, endpoint: str = "http://127.0.0.1:9") -> None:
        assert isinstance(self.outbox.enable(endpoint, CLIENT), Ok)

    def use(self, count: int = 1, name: str = "github", moment: datetime = START) -> None:
        for _ in range(count):
            self.records += 1
            stamp = moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            self.outbox.record_use(_use(name), stamp, f"use-{self.records}")

    def counts(self):
        counts = self.outbox.counts()
        assert isinstance(counts, Ok)
        return counts.value

    def state_of(self) -> SyncState:
        state = self.outbox.sync_state()
        assert isinstance(state, Ok)
        return state.value


def _sync(home: Home, server: FakeServer, clock: Clock, **kwargs):
    return synchronise(home.path, post=server, now=clock, jitter=lambda: 0.0, **kwargs)


class TheOutboxTest(unittest.TestCase):
    def test_nothing_is_kept_before_telemetry_is_on_or_after_it_is_off(self) -> None:
        home = Home(self)
        home.use()
        self.assertFalse(home.outbox.exists())
        home.enable()
        home.use(2)
        home.outbox.disable(forget=False)
        home.use(3)
        self.assertEqual(home.counts().waiting, 2)
        home.enable()
        home.use()
        self.assertEqual(home.counts().waiting, 3)

    @settings(max_examples=40, deadline=None)
    @given(steps=st.lists(st.sampled_from(("on", "off", "use", "action")), max_size=12))
    def test_the_outbox_holds_exactly_what_was_recorded_while_on(self, steps: list[str]) -> None:
        home = Home(self)
        on = False
        expected = 0
        detail = project_receipt_detail(ActivityRecord("2026-10-29T18:00:00Z", lifecycle_outcome()))
        store = LocalReceiptStore(home.state)
        for step in steps:
            if step == "on":
                home.enable()
                on = True
            elif step == "off":
                home.outbox.disable(forget=False)
                on = False
            elif step == "use":
                home.use()
                expected += on
            else:
                with mock.patch.object(telemetry_sync, "spawn_sync", return_value=False):
                    store.record_action(detail)
                expected += on
        self.assertEqual(home.counts().waiting, expected)

    def test_owner_only_and_one_installation_id_until_forgotten(self) -> None:
        home = Home(self)
        home.enable()
        self.assertEqual(stat.S_IMODE(os.stat(home.outbox.path).st_mode), 0o600)
        first = home.outbox.setting().value.client_id
        home.outbox.enable("https://telemetry.example.com", "11111111-1111-4111-8111-111111111111")
        self.assertEqual(home.outbox.setting().value.client_id, first)
        home.use()
        home.outbox.disable(forget=True)
        # Forgotten, the decision stays: off, with nothing kept and no installation id.
        forgotten = home.outbox.setting().value
        self.assertEqual((forgotten.enabled, forgotten.client_id), (False, ""))
        self.assertEqual(home.counts(), OutboxCounts())
        self.assertEqual(home.state_of(), SyncState())
        again = "22222222-2222-4222-8222-222222222222"
        home.outbox.enable("https://telemetry.example.com", again)
        self.assertEqual(home.outbox.setting().value.client_id, again)

    def test_another_schema_version_is_reported_and_left(self) -> None:
        home = Home(self)
        Path(home.state).mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(home.outbox.path) as connection:
            connection.execute("PRAGMA user_version = 9")
        before = Path(home.outbox.path).read_bytes()
        self.assertNotIsInstance(home.outbox.setting(), Ok)
        self.assertNotIsInstance(home.outbox.record_use(_use(), "x", "use-1"), Ok)
        self.assertEqual(Path(home.outbox.path).read_bytes(), before)


class TheBriefsScenariosTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Home(self)
        self.home.enable()
        self.server = FakeServer()
        self.clock = Clock()

    def test_1_the_first_event_ever_starts_a_sync_that_marks_it_sent(self) -> None:
        spawned: list[str] = []
        self.home.use()
        self.assertTrue(
            maybe_sync(
                self.home.path, now=self.clock, spawn=lambda home: spawned.append(home) is None
            )
        )
        self.assertEqual(spawned, [self.home.path])
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual((report.sent, self.home.counts().waiting), (1, 0))
        self.assertEqual(self.home.state_of().last_success_at, START)
        event = next(iter(self.server.stored.values()))
        self.assertEqual(
            (event["event_type"], event["source"], event["artifact_id"], event["artifact_version"]),
            ("artifact.used", "claude_hook", "github", "1.6.0"),
        )

    def test_2_five_minutes_after_a_success_nothing_is_sent(self) -> None:
        self.home.use()
        _sync(self.home, self.server, self.clock)
        self.clock.advance(minutes=5)
        self.home.use(500)
        self.assertFalse(maybe_sync(self.home.path, now=self.clock, spawn=self.fail))
        self.assertFalse(_sync(self.home, self.server, self.clock).started)
        self.assertEqual((len(self.server.requests), self.home.counts().waiting), (1, 500))

    def test_3_eleven_minutes_after_a_success_everything_waiting_goes_in_batches(self) -> None:
        self.home.use()
        _sync(self.home, self.server, self.clock)
        self.clock.advance(minutes=11)
        self.home.use(2 * BATCH_SIZE + 17)
        with mock.patch.object(telemetry_sync, "spawn_sync", return_value=False):
            LocalReceiptStore(self.home.state).record_action(
                project_receipt_detail(ActivityRecord("2026-10-29T18:11:00Z", lifecycle_outcome()))
            )
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual(report.sent, 2 * BATCH_SIZE + 18)
        self.assertEqual(len(self.server.requests), 1 + 3)
        self.assertLessEqual(max(len(r["events"]) for r in self.server.requests), BATCH_SIZE)
        kinds = {event["event_type"] for event in self.server.stored.values()}
        self.assertEqual(kinds, {"artifact.used", "artifact.installed"})

    def test_4_and_5_a_server_down_keeps_everything_and_backs_off_then_recovers(self) -> None:
        self.server.down = True
        self.home.use(3)
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual((report.sent, report.reason), (0, "unavailable"))
        self.assertEqual(self.home.counts().waiting, 3)
        retry = self.home.state_of().next_retry_at
        self.assertEqual(retry, START + timedelta(minutes=1))
        for seconds in (1, 30, 59):
            self.clock.moment = START + timedelta(seconds=seconds)
            self.home.use()
            self.assertFalse(maybe_sync(self.home.path, now=self.clock, spawn=self.fail))
        self.server.down = False
        self.clock.moment = START + timedelta(minutes=1)
        self.assertTrue(maybe_sync(self.home.path, now=self.clock, spawn=lambda home: True))
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual((report.sent, self.home.counts().waiting), (6, 0))
        self.assertEqual(self.home.state_of(), SyncState(self.clock.moment, self.clock.moment))

    def test_6_a_lost_answer_resends_the_same_ids(self) -> None:
        self.home.use(2)
        self.server.lose_answer = True
        _sync(self.home, self.server, self.clock)
        self.assertEqual(self.home.counts().waiting, 2)
        self.server.lose_answer = False
        self.clock.advance(minutes=1)
        _sync(self.home, self.server, self.clock)
        first, second = self.server.requests
        self.assertEqual(
            [e["event_id"] for e in first["events"]], [e["event_id"] for e in second["events"]]
        )
        self.assertEqual((len(self.server.stored), self.home.counts().sent), (2, 2))

    def test_only_what_the_server_acknowledged_is_marked_sent(self) -> None:
        self.home.use(3)
        waiting = self.home.outbox.waiting(limit=10).value
        kept = waiting[0].event_id

        def partly(url: str, body: bytes, timeout: float):
            return 200, {"acknowledged_event_ids": [kept, "not-one-of-ours"]}

        report = synchronise(self.home.path, post=partly, now=self.clock, jitter=lambda: 0.0)
        # The second request is acknowledged with nothing it carried: that is no answer, so back off.
        self.assertEqual((report.sent, report.requests, report.reason), (1, 2, "unavailable"))
        self.assertEqual((self.home.counts().sent, self.home.counts().waiting), (1, 2))
        self.assertNotIn(kept, [item.event_id for item in self.home.outbox.waiting(limit=10).value])

    def test_7_a_held_lock_lets_nobody_else_send(self) -> None:
        self.home.use()
        held = os.open(self.home.outbox.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, held)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual(report.reason, "another synchronisation is running")
        self.assertEqual(self.server.requests, [])

    def test_7_concurrent_triggers_send_once(self) -> None:
        self.home.use(5)
        gate = threading.Event()

        def slow(url: str, body: bytes, timeout: float):
            gate.wait(5)
            return self.server(url, body, timeout)

        reports = []
        threads = [
            threading.Thread(
                target=lambda: reports.append(
                    synchronise(self.home.path, post=slow, now=self.clock, jitter=lambda: 0.0)
                )
            )
            for _ in range(8)
        ]
        for thread in threads:
            thread.start()
        time.sleep(0.3)
        gate.set()
        for thread in threads:
            thread.join(10)
        self.assertEqual(len(self.server.requests), 1)
        self.assertEqual(sum(report.sent for report in reports), 5)

    def test_9_a_sender_that_dies_mid_request_leaves_everything_waiting(self) -> None:
        self.home.use(4)

        def dies(url: str, body: bytes, timeout: float):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            synchronise(self.home.path, post=dies, now=self.clock, jitter=lambda: 0.0)
        self.assertEqual(self.home.counts().waiting, 4)
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual(report.sent, 4)

    def test_a_use_of_nothing_installed_is_skipped_never_sent_when_chosen_so(self) -> None:
        # D-508: sent by default; `telemetry_unmanaged_test` holds that and the choice itself.
        write_consumer_settings(
            ConsumerSettings(telemetry_unmanaged=False), data_root=self.home.path
        )
        self.home.use(name="my-own-mcp")
        self.home.use(name="github")
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual((report.sent, report.skipped), (1, 1))
        self.assertNotIn("my-own-mcp", json.dumps(self.server.requests))
        self.assertNotIn("/work/project", json.dumps(self.server.requests))

    def test_rejected_events_are_set_aside_and_the_rest_sent(self) -> None:
        self.home.use(3)
        waiting = self.home.outbox.waiting(limit=10).value
        bad = waiting[1].event_id

        def picky(url: str, body: bytes, timeout: float):
            events = json.loads(body)["events"]
            if any(e["event_id"] == bad for e in events):
                return 422, {"rejected_events": [{"index": 0, "event_id": bad}]}
            return self.server(url, body, timeout)

        report = synchronise(self.home.path, post=picky, now=self.clock, jitter=lambda: 0.0)
        self.assertEqual((report.sent, report.rejected), (2, 1))
        self.assertEqual(self.home.counts().rejected, 1)

    def test_a_request_refused_whole_is_split_down_to_the_one_event(self) -> None:
        self.home.use(8)
        bad = self.home.outbox.waiting(limit=10).value[5].event_id

        def whole(url: str, body: bytes, timeout: float):
            events = json.loads(body)["events"]
            if any(e["event_id"] == bad for e in events):
                return 413, None
            return self.server(url, body, timeout)

        report = synchronise(self.home.path, post=whole, now=self.clock, jitter=lambda: 0.0)
        self.assertEqual((report.sent, report.rejected), (7, 1))

    def test_a_refused_authorisation_pauses_for_an_hour_unless_forced(self) -> None:
        self.home.use()
        self.server.status = 401
        report = _sync(self.home, self.server, self.clock)
        self.assertEqual(report.reason, "unauthorised")
        self.clock.advance(minutes=59)
        self.assertFalse(_sync(self.home, self.server, self.clock, manual=True).started)
        self.server.status = None
        self.assertEqual(_sync(self.home, self.server, self.clock, force=True).sent, 1)

    def test_manual_sync_ignores_the_interval_but_not_the_backoff(self) -> None:
        self.home.use()
        _sync(self.home, self.server, self.clock)
        self.home.use()
        self.assertFalse(_sync(self.home, self.server, self.clock).started)
        self.assertEqual(_sync(self.home, self.server, self.clock, manual=True).sent, 1)

    def test_a_disabled_outbox_sends_nothing(self) -> None:
        self.home.use()
        self.home.outbox.disable(forget=False)
        self.assertFalse(maybe_sync(self.home.path, now=self.clock, spawn=self.fail))
        self.assertFalse(_sync(self.home, self.server, self.clock, force=True).started)


class ContractHandler(BaseHTTPRequestHandler):
    stored: dict[str, dict] = {}
    mode = "ok"

    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802 -- the standard library's name
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).last_headers = dict(self.headers)
        if self.mode == "slow":
            time.sleep(3)
        if self.mode == "error":
            self.send_response(500)
            self.end_headers()
            return
        document = json.loads(body)
        for event in document["events"]:
            type(self).stored.setdefault(event["event_id"], event)
        answer = json.dumps(
            {"acknowledged_event_ids": [e["event_id"] for e in document["events"]]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)


class OverRealHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        ContractHandler.stored = {}
        ContractHandler.mode = "ok"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ContractHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def test_http_post_reads_each_answer_and_never_uses_a_proxy_for_loopback(self) -> None:
        body = json.dumps({"events": [{"event_id": "x"}]}).encode()
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""}):
            self.assertEqual(
                http_post(self.url + BATCH_PATH, body, 5),
                (200, {"acknowledged_event_ids": ["x"]}),
            )
        self.assertIn("aart-cli/", ContractHandler.last_headers["User-Agent"])
        ContractHandler.mode = "error"
        self.assertEqual(http_post(self.url + BATCH_PATH, body, 5), (500, None))
        ContractHandler.mode = "slow"
        self.assertEqual(http_post(self.url + BATCH_PATH, body, 0.5), (None, None))
        self.assertEqual(http_post("http://127.0.0.1:1" + BATCH_PATH, body, 2), (None, None))

    def test_8_a_harness_hook_records_and_a_detached_process_delivers(self) -> None:
        home = Home(self)
        home.enable(self.url)
        payload = json.dumps(
            {
                "tool_name": "mcp__github__search",
                "tool_input": {"q": "held-out-argument"},
                "cwd": "/work/project",
            }
        ).encode()
        started = time.monotonic()
        finished = subprocess.run(
            [sys.executable, "-I", str(HOOK), "claude", home.path],
            input=payload,
            capture_output=True,
            timeout=30,
            cwd=home.path,
        )
        hook_seconds = time.monotonic() - started
        self.assertEqual((finished.returncode, finished.stdout), (0, b""))
        deadline = time.monotonic() + 15
        while not ContractHandler.stored and time.monotonic() < deadline:
            time.sleep(0.1)
        events = list(ContractHandler.stored.values())
        self.assertEqual(
            [(e["artifact_id"], e["source"]) for e in events], [("github", "claude_hook")]
        )
        self.assertNotIn("held-out-argument", json.dumps(events))
        self.assertLess(hook_seconds, 5)
        deadline = time.monotonic() + 5
        while home.counts().sent != 1 and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual(home.counts().sent, 1)


class NeverFailsWhatTriggeredItTest(unittest.TestCase):
    def test_a_broken_outbox_never_fails_the_hook_or_the_action(self) -> None:
        home = Home(self)
        Path(home.state).mkdir(parents=True, exist_ok=True)
        Path(home.outbox.path).write_bytes(b"not a database")
        payload = json.dumps({"tool_name": "mcp__github__search", "cwd": "/w"}).encode()
        self.assertTrue(record("claude", home.path, payload))
        detail = project_receipt_detail(ActivityRecord("2026-10-29T18:00:00Z", lifecycle_outcome()))
        self.assertIsInstance(LocalReceiptStore(home.state).record_action(detail), Ok)
        self.assertFalse(maybe_sync(home.path))

    def test_maybe_sync_swallows_whatever_the_spawn_does(self) -> None:
        home = Home(self)
        home.enable()
        home.use()

        def explodes(_: str) -> bool:
            raise OSError("no fork")

        self.assertFalse(maybe_sync(home.path, spawn=explodes))
        self.assertFalse(maybe_sync(home.path, spawn=lambda _: False))


if __name__ == "__main__":
    unittest.main()
