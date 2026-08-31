"""Reading back what an installation left behind, across process boundaries.

A receipt is only evidence if it survives the process that wrote it.  These tests fix the parse as
the exact inverse of the projection, and refuse -- rather than guess -- when a document on disk is
not the thing it claims to be.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import tempfile
import unittest

from agent_artifacts.application.consumer_views import (
    ActivityRecord,
    activity_from_receipts,
    project_receipt_detail,
    receipt_detail_from_data,
    receipt_detail_to_data,
)
from agent_artifacts.domain.credentials import CredentialProviderRef, CredentialReference
from agent_artifacts.domain.harness import McpRegistration, Scope, mcp_target
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.launch import Transport
from agent_artifacts.domain.receipts import (
    InstallationReceipt,
    config_fingerprint,
    installation_receipt_from_data,
    installation_receipt_to_data,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason
from agent_artifacts.io.receipt_store import RECEIPT_UNREADABLE, LocalReceiptStore
from tests.consumer_activity_test import lifecycle_outcome

COORDINATE = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.6.0")
DIRECT = OwnershipReason(OwnershipKind.DIRECT, "public/mcp/github@1.6.0")
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")
ROOT = "/opt/agents/.tabnine/agent/aart/mcp/github"
TODAY = dt.date(2026, 8, 31)


def receipt(**override) -> InstallationReceipt:
    fields = {
        "artifact": "mcp/github",
        "root": ROOT,
        "launcher": f"{ROOT}/launch.sh",
        "launcher_digest": ObjectDigest("sha256", "a" * 64),
        "interpreter": f"{ROOT}/runtime/.venv/bin/python",
        "transport": Transport.STDIO,
        "registrations": (
            McpRegistration(mcp_target("tabnine", Scope.PROJECT), "github", f"{ROOT}/launch.sh"),
        ),
        "credentials": (
            CredentialReference(
                InputId("github-token"), CredentialProviderRef("macos-keychain", "aart", "work")
            ),
        ),
        "config": (config_fingerprint(InputId("org"), "acme"),),
    }
    fields.update(override)
    return InstallationReceipt(**fields)  # type: ignore[arg-type]


class ReceiptParsingTest(unittest.TestCase):
    def test_a_receipt_survives_being_written_down_and_read_back(self):
        original = receipt()

        parsed = installation_receipt_from_data(
            json.loads(json.dumps(installation_receipt_to_data(original)))
        )

        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        self.assertEqual(parsed.value, original)

    def test_a_reference_whose_parts_contain_punctuation_still_round_trips(self):
        awkward = CredentialReference(
            InputId("token"), CredentialProviderRef("vault", "team@acme:prod", "a/b@c")
        )

        parsed = installation_receipt_from_data(
            installation_receipt_to_data(receipt(credentials=(awkward,)))
        )

        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        self.assertEqual(parsed.value.credentials, (awkward,))

    def test_a_document_that_is_not_a_receipt_is_refused_rather_than_guessed_at(self):
        complete = installation_receipt_to_data(receipt())
        cases = (
            ("not a mapping", []),
            ("missing launcher", {k: v for k, v in complete.items() if k != "launcher"}),
            ("wrong digest shape", {**complete, "launcher_digest": "sha256"}),
            ("unknown transport", {**complete, "transport": "sse"}),
            ("launcher outside root", {**complete, "launcher": "/elsewhere/launch.sh"}),
            (
                "unmeasured harness",
                {
                    **complete,
                    "registrations": [
                        {**complete["registrations"][0], "harness": "nothing-measured"}  # type: ignore[index]
                    ],
                },
            ),
        )
        for name, document in cases:
            with self.subTest(document=name):
                parsed = installation_receipt_from_data(document)
                self.assertIsInstance(parsed, Err)
                self.assertTrue(parsed.diagnostics)


class ReceiptStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.store = LocalReceiptStore(str(self.root))

    def test_an_installation_is_recorded_and_read_back_by_coordinate(self):
        recorded = self.store.record_installation(COORDINATE, receipt())
        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))

        read = self.store.installation(COORDINATE)

        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        self.assertEqual(read.value, receipt())

    def test_recording_the_same_installation_again_replaces_one_record(self):
        self.store.record_installation(COORDINATE, receipt())
        self.store.record_installation(COORDINATE, receipt(interpreter=f"{ROOT}/other/python"))

        listed = self.store.installations()

        self.assertIsInstance(listed, Ok, getattr(listed, "diagnostics", ()))
        self.assertEqual(len(listed.value), 1)
        self.assertEqual(listed.value[0].coordinate, COORDINATE)
        self.assertTrue(listed.value[0].receipt.interpreter.endswith("other/python"))

    def test_an_artifact_nothing_installed_is_absent_rather_than_an_error(self):
        self.assertIsInstance(self.store.installation(COORDINATE), Err)
        self.assertEqual(self.store.installations().value, ())

    def test_forgetting_an_installation_removes_only_that_record(self):
        other = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "jira"), "2.0.0")
        self.store.record_installation(COORDINATE, receipt())
        self.store.record_installation(other, receipt(artifact="mcp/jira"))

        self.assertIsInstance(self.store.forget_installation(COORDINATE), Ok)

        remaining = self.store.installations().value
        self.assertEqual([item.coordinate for item in remaining], [other])

    def test_a_corrupt_record_is_reported_rather_than_returned_as_an_installation(self):
        self.store.record_installation(COORDINATE, receipt())
        path = pathlib.Path(self.store.path_for(COORDINATE))
        path.write_text("{not json", encoding="utf-8")

        read = self.store.installation(COORDINATE)
        listed = self.store.installations()

        self.assertIsInstance(read, Err)
        self.assertEqual(read.diagnostics[0].code, RECEIPT_UNREADABLE)
        self.assertIsInstance(listed, Err)

    def test_why_an_artifact_is_installed_is_recorded_beside_what_it_left_behind(self):
        self.store.record_installation(COORDINATE, receipt(), ownership=(KIT, DIRECT))

        listed = self.store.installations()

        self.assertIsInstance(listed, Ok, getattr(listed, "diagnostics", ()))
        self.assertEqual(listed.value[0].ownership, (KIT, DIRECT))
        self.assertEqual(listed.value[0].coordinate, COORDINATE)
        self.assertEqual(listed.value[0].receipt, receipt())

    def test_an_installation_nobody_claimed_reads_back_owned_by_nobody(self):
        self.store.record_installation(COORDINATE, receipt())

        self.assertEqual(self.store.installations().value[0].ownership, ())

    def test_a_record_rewritten_without_saying_who_owns_it_keeps_the_owners_it_had(self):
        self.store.record_installation(COORDINATE, receipt(), ownership=(KIT,))

        self.store.record_installation(COORDINATE, receipt(interpreter=f"{ROOT}/other/python"))

        record = self.store.record(COORDINATE)
        self.assertIsInstance(record, Ok, getattr(record, "diagnostics", ()))
        self.assertEqual(record.value.ownership, (KIT,))
        self.assertTrue(record.value.receipt.interpreter.endswith("other/python"))

    def test_a_record_told_that_nobody_owns_it_says_nobody_owns_it(self):
        self.store.record_installation(COORDINATE, receipt(), ownership=(KIT,))

        self.store.record_installation(COORDINATE, receipt(), ownership=())

        self.assertEqual(self.store.record(COORDINATE).value.ownership, ())

    def test_ownership_that_is_not_ownership_is_refused_rather_than_dropped(self):
        self.store.record_installation(COORDINATE, receipt(), ownership=(DIRECT,))
        path = pathlib.Path(self.store.path_for(COORDINATE))
        document = json.loads(path.read_text(encoding="utf-8"))
        document["ownership"] = [{"kind": "borrowed", "owner": "somebody"}]
        path.write_text(json.dumps(document), encoding="utf-8")

        read = self.store.installations()

        self.assertIsInstance(read, Err)
        self.assertEqual(read.diagnostics[0].code, RECEIPT_UNREADABLE)

    def test_a_recorded_receipt_is_readable_only_by_its_owner(self):
        self.store.record_installation(COORDINATE, receipt())
        mode = pathlib.Path(self.store.path_for(COORDINATE)).stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)


class ActivityStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = LocalReceiptStore(temporary.name)

    def detail(self, moment: str = "2026-08-31T14:32:00Z"):
        return project_receipt_detail(ActivityRecord(moment, lifecycle_outcome()))

    def test_a_receipt_survives_being_written_down_and_read_back(self):
        original = self.detail()

        parsed = receipt_detail_from_data(json.loads(json.dumps(receipt_detail_to_data(original))))

        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        self.assertEqual(parsed.value, original)

    def test_recorded_actions_come_back_newest_first(self):
        for moment in ("2026-08-30T16:02:00Z", "2026-08-31T14:32:00Z", "2026-08-31T10:41:00Z"):
            recorded = self.store.record_action(self.detail(moment))
            self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))

        actions = self.store.actions()

        self.assertIsInstance(actions, Ok, getattr(actions, "diagnostics", ()))
        self.assertEqual(
            [item.recorded_at[:16] for item in actions.value],
            ["2026-08-31T14:32", "2026-08-31T10:41", "2026-08-30T16:02"],
        )

    def test_the_timeline_reads_the_same_whether_it_came_from_memory_or_from_disk(self):
        record = ActivityRecord("2026-08-31T14:32:00Z", lifecycle_outcome())
        self.store.record_action(project_receipt_detail(record))

        from_disk = activity_from_receipts(self.store.actions().value, today=TODAY)

        self.assertEqual([day.label for day in from_disk.days], ["Today"])
        entry = from_disk.days[0].entries[0]
        self.assertEqual(entry.summary, "Installed public/mcp/github@1.6.0")
        self.assertEqual(entry.time, "14:32")
        self.assertEqual(entry.review_digest, str(record.outcome.plan.review_digest))

    def test_only_the_most_recent_actions_are_read_when_a_limit_is_given(self):
        for hour in range(5):
            self.store.record_action(self.detail(f"2026-08-31T1{hour}:00:00Z"))

        actions = self.store.actions(limit=2)

        self.assertEqual(
            [item.recorded_at[:13] for item in actions.value], ["2026-08-31T14", "2026-08-31T13"]
        )

    def test_a_corrupt_action_is_reported_rather_than_skipped_silently(self):
        self.store.record_action(self.detail())
        stray = pathlib.Path(self.store.actions_directory) / "2026-08-31T00:00:00+00:00-bad.json"
        stray.write_text("{not json", encoding="utf-8")

        actions = self.store.actions()

        self.assertIsInstance(actions, Err)
        self.assertEqual(actions.diagnostics[0].code, RECEIPT_UNREADABLE)


if __name__ == "__main__":
    unittest.main()
