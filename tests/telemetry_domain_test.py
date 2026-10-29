"""CP-50: what is sent to a telemetry server, where, and when (§213, INV-322–INV-327).

The contract is docs/telemetry-api-v1.md with contract/telemetry-api-v1.examples.json, kept
identical in aart-telemetry-server. The digests below are the same constants that repository's
contract test holds: a change made on one side only is red here or there.
"""

from __future__ import annotations

import hashlib
import json
import string
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.domain.artifact_usage import InstalledName, UsageKind
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.telemetry import (
    AUTH_PAUSE,
    BACKOFF,
    BATCH_SIZE,
    SYNC_INTERVAL,
    AnswerKind,
    SyncState,
    TelemetryEvent,
    after_failure,
    after_success,
    batch_document,
    classify_answer,
    contract_moment,
    lifecycle_event,
    parse_telemetry_endpoint,
    sync_due,
    use_event,
)
from tests.credential_fixtures import credential_url

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "docs" / "telemetry-api-v1.md"
EXAMPLES = ROOT / "contract" / "telemetry-api-v1.examples.json"
CONTRACT_SHA256 = {
    "docs/telemetry-api-v1.md": "c06bc119e642b3969fa8444a301ee28bd704058984d681d9896bb0009d401763",
    "contract/telemetry-api-v1.examples.json": (
        "af9022f4889ffca325353416c088608925f327feac0176b1f21cedf6374004e9"
    ),
}

ID = "7515ec68-1e98-46ca-bd90-9f6a70c84d11"
CLIENT = "0b6f4d1e-8f8a-4a43-9a52-2f0f5d0f6a11"
NOW = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)
INSTALLED = (
    InstalledName("claude", UsageKind.SKILL, "release-notes", "corp/skill/release-notes", "1.2.0"),
    InstalledName("opencode", UsageKind.MCP, "jira", "corp/mcp/jira-mcp", "2.0.1"),
    InstalledName("opencode", UsageKind.MCP, "jira_cloud", "corp/mcp/jira-cloud", None),
)


def _examples() -> dict:
    return json.loads(EXAMPLES.read_text(encoding="utf-8"))


class TheContractIsSharedTest(unittest.TestCase):
    def test_the_copies_are_the_ones_the_server_holds(self) -> None:
        for relative, digest in CONTRACT_SHA256.items():
            with self.subTest(relative):
                held = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                self.assertEqual(held, digest)

    def test_every_valid_example_is_an_event_this_client_could_send(self) -> None:
        for example in _examples()["valid"]:
            request = example["request"]
            events = tuple(TelemetryEvent(**event) for event in request["events"])
            self.assertEqual(
                batch_document(request["client_id"], request["client_version"], events), request
            )

    def test_no_invalid_example_can_be_built(self) -> None:
        for example in _examples()["invalid"]:
            with self.subTest(example["name"]), self.assertRaises((ValueError, TypeError)):
                TelemetryEvent(**example["event"])


class TheAddressTest(unittest.TestCase):
    def test_https_anywhere_and_http_only_to_loopback(self) -> None:
        for raw, expected in (
            ("https://telemetry.example.com", "https://telemetry.example.com"),
            ("https://telemetry.example.com:8443/base/", "https://telemetry.example.com:8443/base"),
            (" http://127.0.0.1:8000 ", "http://127.0.0.1:8000"),
            ("http://localhost:8000/", "http://localhost:8000"),
            ("http://[::1]:8000", "http://[::1]:8000"),
        ):
            with self.subTest(raw):
                self.assertEqual(parse_telemetry_endpoint(raw), Ok(expected))

    def test_a_credential_a_query_or_plain_http_elsewhere_is_refused_unrepeated(self) -> None:
        for raw in (
            "http://telemetry.example.com",
            "http://10.0.0.1:8000",
            credential_url("telemetry.example.com", held="pw"),
            "https://token@telemetry.example.com",
            "https://telemetry.example.com/?token=abc",
            "https://telemetry.example.com/#frag",
            "ftp://telemetry.example.com",
            "https://",
            "https://telemetry.example.com:99999",
            "telemetry.example.com",
        ):
            with self.subTest(raw):
                parsed = parse_telemetry_endpoint(raw)
                self.assertIsInstance(parsed, Err)
                assert isinstance(parsed, Err)
                self.assertNotIn("example.com", parsed.diagnostics[0].message)

    @given(
        user=st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=12),
        scheme=st.sampled_from(("http", "https")),
        host=st.sampled_from(("127.0.0.1", "localhost", "telemetry.example.com")),
    )
    def test_no_address_with_a_user_is_ever_accepted(
        self, user: str, scheme: str, host: str
    ) -> None:
        self.assertIsInstance(parse_telemetry_endpoint(f"{scheme}://{user}@{host}"), Err)


def _state(draw_moment: st.DrawFn) -> SyncState:
    moments = st.one_of(
        st.none(),
        st.integers(-7200, 7200).map(lambda seconds: NOW + timedelta(seconds=seconds)),
    )
    return SyncState(
        last_success_at=draw_moment(moments),
        last_attempt_at=draw_moment(moments),
        next_retry_at=draw_moment(moments),
        failures=draw_moment(st.integers(0, 9)),
    )


class WhenItIsDueTest(unittest.TestCase):
    @given(data=st.data(), pending=st.integers(0, 10_000), manual=st.booleans())
    def test_due_exactly_on_time_never_on_count(
        self, data: st.DataObject, pending: int, manual: bool
    ) -> None:
        state = _state(data.draw)
        waited = state.next_retry_at is None or NOW >= state.next_retry_at
        interval = (
            manual or state.last_success_at is None or NOW - state.last_success_at >= SYNC_INTERVAL
        )
        self.assertEqual(
            sync_due(state, NOW, pending=pending, manual=manual),
            pending > 0 and waited and interval,
        )

    def test_the_brief_s_scenarios(self) -> None:
        self.assertTrue(sync_due(SyncState(), NOW, pending=1))
        five = SyncState(last_success_at=NOW - timedelta(minutes=5))
        self.assertFalse(sync_due(five, NOW, pending=500))
        eleven = SyncState(last_success_at=NOW - timedelta(minutes=11))
        self.assertTrue(sync_due(eleven, NOW, pending=1))
        backing_off = SyncState(next_retry_at=NOW + timedelta(seconds=1))
        self.assertFalse(sync_due(backing_off, NOW, pending=1, manual=True))
        self.assertTrue(sync_due(five, NOW, pending=1, manual=True))

    @given(failures=st.integers(0, 20), jitter=st.floats(0, 0.999))
    def test_backoff_grows_to_its_cap_and_success_clears_it(
        self, failures: int, jitter: float
    ) -> None:
        state = SyncState(failures=failures, last_success_at=NOW - timedelta(days=1))
        failed = after_failure(state, NOW, AnswerKind.UNAVAILABLE, jitter=jitter)
        base = BACKOFF[min(failures + 1, len(BACKOFF)) - 1]
        assert failed.next_retry_at is not None
        self.assertGreaterEqual(failed.next_retry_at - NOW, base)
        self.assertLessEqual(failed.next_retry_at - NOW, base * 1.2)
        self.assertEqual(failed.failures, failures + 1)
        self.assertEqual(failed.last_success_at, state.last_success_at)
        self.assertFalse(sync_due(failed, NOW, pending=1, manual=True))
        self.assertEqual(after_success(failed, NOW), SyncState(NOW, NOW))

    def test_a_refused_authorisation_pauses_for_an_hour(self) -> None:
        failed = after_failure(SyncState(), NOW, AnswerKind.UNAUTHORISED, jitter=0.0)
        self.assertEqual((failed.next_retry_at, failed.paused), (NOW + AUTH_PAUSE, "unauthorised"))


class TheAnswerTest(unittest.TestCase):
    SENT = ("00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002")

    @given(
        status=st.one_of(st.none(), st.integers(100, 599)),
        named=st.lists(st.sampled_from((*SENT, "00000000-0000-4000-8000-00000000000f", 7))),
        field=st.sampled_from(("acknowledged_event_ids", "rejected_events")),
    )
    def test_only_ids_that_were_sent_are_ever_marked(
        self, status: int | None, named: list, field: str
    ) -> None:
        body = {
            field: named
            if field == "acknowledged_event_ids"
            else [{"event_id": item} for item in named]
        }
        answer = classify_answer(status, body, self.SENT)
        self.assertLessEqual(set(answer.event_ids), set(self.SENT))
        if answer.kind is AnswerKind.STORED:
            self.assertEqual(status, 200)

    def test_each_status_means_what_the_contract_says(self) -> None:
        sent = self.SENT
        self.assertEqual(
            classify_answer(200, {"acknowledged_event_ids": [sent[0]]}, sent).event_ids,
            (sent[0],),
        )
        self.assertIs(classify_answer(200, {}, sent).kind, AnswerKind.UNAVAILABLE)
        rejected = classify_answer(422, {"rejected_events": [{"event_id": sent[1]}]}, sent)
        self.assertEqual((rejected.kind, rejected.event_ids), (AnswerKind.REJECTED, (sent[1],)))
        for status in (400, 413):
            self.assertIs(classify_answer(status, None, sent).kind, AnswerKind.SPLIT)
        self.assertIs(classify_answer(422, {"rejected_events": []}, sent).kind, AnswerKind.SPLIT)
        for status in (401, 403):
            self.assertIs(classify_answer(status, None, sent).kind, AnswerKind.UNAUTHORISED)
        for status in (None, 429, 500, 503, 302):
            self.assertIs(classify_answer(status, None, sent).kind, AnswerKind.UNAVAILABLE)


class WhatIsSentTest(unittest.TestCase):
    MOMENT = "2026-10-29T18:15:00.000000Z"

    def test_a_use_is_sent_as_the_installed_artifact(self) -> None:
        skill = use_event(ID, self.MOMENT, "claude", UsageKind.SKILL, "release-notes", INSTALLED)
        assert skill is not None
        self.assertEqual(
            skill.document(),
            {
                "event_id": ID,
                "occurred_at": self.MOMENT,
                "event_type": "artifact.used",
                "source": "claude_hook",
                "artifact_id": "release-notes",
                "artifact_type": "skill",
                "artifact_version": "1.2.0",
            },
        )
        tool = use_event(ID, self.MOMENT, "opencode", UsageKind.MCP, "jira_cloud_search", INSTALLED)
        assert tool is not None
        self.assertEqual((tool.artifact_id, tool.source), ("jira-cloud", "opencode_plugin"))
        self.assertNotIn("artifact_version", tool.document())

    def test_a_use_nothing_installed_answers_to_is_never_sent(self) -> None:
        for harness, kind, name in (
            ("claude", UsageKind.SKILL, "my-own-skill"),
            ("claude", UsageKind.MCP, "jira"),
            ("opencode", UsageKind.MCP, "jirafe_x"),
            ("tabnine", UsageKind.SKILL, "release-notes"),
        ):
            with self.subTest(name):
                self.assertIsNone(use_event(ID, self.MOMENT, harness, kind, name, INSTALLED))

    @given(name=st.text(min_size=1, max_size=60))
    def test_no_name_a_harness_gives_reaches_an_event_unless_installed(self, name: str) -> None:
        event = use_event(ID, self.MOMENT, "opencode", UsageKind.MCP, name, INSTALLED)
        if event is not None:
            self.assertIn(event.artifact_id, {"jira-mcp", "jira-cloud"})
            self.assertNotIn(name, json.dumps(event.document()).replace(event.artifact_id, ""))

    def test_lifecycle_events_name_the_artifact_and_its_version(self) -> None:
        installed = lifecycle_event(ID, self.MOMENT, "install", "corp/mcp/jira-mcp@2.0.1")
        assert installed is not None
        self.assertEqual(
            (installed.event_type, installed.artifact_type, installed.artifact_id),
            ("artifact.installed", "mcp", "jira-mcp"),
        )
        self.assertEqual(installed.artifact_version, "2.0.1")
        for intent, expected in (
            ("update", "artifact.updated"),
            ("downgrade", "artifact.updated"),
            ("uninstall", "artifact.removed"),
        ):
            event = lifecycle_event(ID, self.MOMENT, intent, "corp/skill/x@1")
            self.assertEqual(event and event.event_type, expected)
        self.assertIsNone(lifecycle_event(ID, self.MOMENT, "repair", "corp/skill/x@1"))
        self.assertIsNone(lifecycle_event(ID, self.MOMENT, "install", "not a coordinate"))

    def test_a_batch_is_bounded_and_its_moments_are_utc(self) -> None:
        event = TelemetryEvent(ID, self.MOMENT, "artifact.used", "claude_hook", "a", "skill")
        with self.assertRaises(ValueError):
            batch_document(CLIENT, "0.22.0", (event,) * (BATCH_SIZE + 1))
        with self.assertRaises(ValueError):
            batch_document(CLIENT.upper(), "0.22.0", (event,))
        self.assertEqual(
            contract_moment(datetime(2026, 10, 29, 20, 15, tzinfo=timezone(timedelta(hours=2)))),
            "2026-10-29T18:15:00.000000Z",
        )


if __name__ == "__main__":
    unittest.main()
