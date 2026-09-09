"""Keeping an artifact a harness reads between processes, beside the ones a harness starts.

The Installed list is one list (D-069), so one record type carries either receipt. The two receipts
stay separate types -- an MCP receipt cannot lose its launcher without something noticing -- and the
record says which it holds. A document written before placements existed carries no such marker, and
is read as what every one of them is: an installation that starts a process.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.receipts import ArtifactDelivery, PlacedArtifactReceipt
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason
from agent_artifacts.io.receipt_store import RECEIPT_UNREADABLE, LocalReceiptStore

COORDINATE = ArtifactCoordinate(
    SourceAlias("public"), ArtifactIdentity("skill", "code-review"), "2.0.0"
)
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/reviewers@1.0.0")
ROOT = "/opt/agents/.agent-artifacts/runtimes/public/skill/code-review"


def _digest(character: str = "a") -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _receipt(harness: str = "claude") -> PlacedArtifactReceipt:
    return PlacedArtifactReceipt(
        "skill/code-review",
        ROOT,
        _digest(),
        (
            ArtifactDelivery(
                harness,
                f"{ROOT}/payload",
                f"/work/project/.{harness}/skills/code-review",
                DeliveryKind.TREE,
                _digest("b"),
            ),
        ),
    )


class PlacedReceiptStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = LocalReceiptStore(self.temporary.name)

    def test_a_placed_artifact_is_read_back_as_what_it_was_written_as(self) -> None:
        self.assertIsInstance(
            self.store.record_installation(COORDINATE, _receipt(), ownership=(KIT,)), Ok
        )
        record = self.store.record(COORDINATE)
        assert isinstance(record, Ok)
        self.assertIsInstance(record.value.receipt, PlacedArtifactReceipt)
        self.assertEqual((KIT,), record.value.ownership)

    def test_what_it_delivered_survives_the_process_that_wrote_it(self) -> None:
        self.store.record_installation(COORDINATE, _receipt())
        record = self.store.record(COORDINATE)
        assert isinstance(record, Ok)
        (delivery,) = record.value.receipt.deliveries
        self.assertEqual("claude", delivery.harness)
        self.assertEqual("/work/project/.claude/skills/code-review", delivery.destination)
        self.assertEqual(DeliveryKind.TREE, delivery.kind)

    def test_a_placement_resolves_no_credentials_and_says_so(self) -> None:
        self.store.record_installation(COORDINATE, _receipt())
        record = self.store.record(COORDINATE)
        assert isinstance(record, Ok)
        self.assertEqual((), record.value.credential_references)

    def test_it_is_listed_beside_the_artifacts_a_harness_starts(self) -> None:
        self.store.record_installation(COORDINATE, _receipt())
        listed = self.store.installations()
        assert isinstance(listed, Ok)
        self.assertEqual((COORDINATE,), tuple(item.coordinate for item in listed.value))

    def test_the_document_says_which_of_the_two_receipts_it_holds(self) -> None:
        self.store.record_installation(COORDINATE, _receipt())
        path = pathlib.Path(self.store.path_for(COORDINATE))
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("placed", document["kind"])

    def test_a_record_written_before_placements_existed_is_still_an_installation(self) -> None:
        # Every document written before this marker existed holds an installation receipt, so an
        # absent marker is that fact rather than an unreadable record.
        self.store.record_installation(COORDINATE, _receipt())
        path = pathlib.Path(self.store.path_for(COORDINATE))
        document = json.loads(path.read_text(encoding="utf-8"))
        del document["kind"]
        path.write_text(json.dumps(document), encoding="utf-8")
        refused = self.store.record(COORDINATE)
        assert isinstance(refused, Err)
        self.assertEqual(RECEIPT_UNREADABLE, refused.diagnostics[0].code)

    def test_a_document_claiming_a_kind_nobody_writes_is_reported_not_guessed(self) -> None:
        self.store.record_installation(COORDINATE, _receipt())
        path = pathlib.Path(self.store.path_for(COORDINATE))
        document = json.loads(path.read_text(encoding="utf-8"))
        document["kind"] = "something-else"
        path.write_text(json.dumps(document), encoding="utf-8")
        record = self.store.record(COORDINATE)
        assert isinstance(record, Err)
        self.assertEqual(RECEIPT_UNREADABLE, record.diagnostics[0].code)

    def test_a_placed_document_read_as_an_installation_is_refused_rather_than_emptied(self) -> None:
        self.store.record_installation(COORDINATE, _receipt())
        path = pathlib.Path(self.store.path_for(COORDINATE))
        document = json.loads(path.read_text(encoding="utf-8"))
        document["kind"] = "installation"
        path.write_text(json.dumps(document), encoding="utf-8")
        self.assertIsInstance(self.store.record(COORDINATE), Err)


if __name__ == "__main__":
    unittest.main()
