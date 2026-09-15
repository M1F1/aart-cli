"""A Skill that was really delivered, read back from disk by something that never planned it.

`read_consumer_machine` is what the canonical shell and `status` open on. Until now it could only
answer for artifacts a harness starts, so a delivered Skill either did not appear or appeared as an
unadopted legacy record with health `unknown` and no action (D-069). This is the evidence that a
placed installation crosses that seam like any other: recorded, re-read in another call that has
seen no plan, observed on the real filesystem, and healthy because it really is.

The interesting case is the damaged one. A Skill somebody edited in the harness directory has to
come back as drift on that delivery alone -- not as a missing installation, and not as fine.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import tempfile
import unittest

from agent_artifacts.domain.effects import DeliverArtifact, DeliveryKind
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    SourceAlias,
)
from agent_artifacts.domain.receipts import ArtifactDelivery, PlacedArtifactReceipt
from agent_artifacts.domain.reconciliation import Component
from agent_artifacts.domain.result import Ok
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason
from agent_artifacts.io.consumer_machine import read_consumer_machine
from agent_artifacts.io.execution import DeliveryEffectInterpreter
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.io.runtime_projection import tree_digest_at
from agent_artifacts.protocol.hashing import file_entry, tree_digest
from agent_artifacts.protocol.paths import parse_relative_path

COORDINATE = ArtifactCoordinate(
    SourceAlias("public"), ArtifactIdentity("skill", "code-review"), "2.0.0"
)
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/reviewers@1.0.0")
TODAY = dt.date(2026, 8, 31)


def _path(value: str):
    parsed = parse_relative_path(value)
    assert isinstance(parsed, Ok)
    return parsed.value


class PlacedMachineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = pathlib.Path(self.temporary.name)
        self.state_root = self.base / "state"
        self.project_root = self.base / "project"
        self.user_home = self.base / "home"
        self.data_root = self.base / "data"
        for directory in (self.project_root, self.user_home, self.data_root):
            directory.mkdir(parents=True)

        self.root = self.data_root / "runtimes" / "public" / "skill" / "code-review"
        payload = self.root / "payload"
        payload.mkdir(parents=True)
        (payload / "SKILL.md").write_text("# review\n", encoding="utf-8")
        (payload / "reference.md").write_text("detail\n", encoding="utf-8")
        self.destination = self.project_root / ".claude" / "skills" / "code-review"

        digest = tree_digest(
            (
                file_entry(_path("SKILL.md"), b"# review\n"),
                file_entry(_path("reference.md"), b"detail\n"),
            )
        )
        assert isinstance(digest, Ok)
        # The tree that is really on disk. A placeholder here would describe some other
        # installation, and every "ready" asserted below would be about a payload nobody has.
        measured = tree_digest_at(str(payload))
        assert measured is not None
        self.receipt = PlacedArtifactReceipt(
            "skill/code-review",
            str(self.root),
            measured,
            (
                ArtifactDelivery(
                    "claude",
                    str(payload),
                    str(self.destination),
                    DeliveryKind.TREE,
                    digest.value,
                ),
            ),
        )
        # Deliver it for real, then record it, in that order -- the same order an install runs in.
        interpreter = DeliveryEffectInterpreter("skill/code-review", self.receipt.deliveries)
        delivered = interpreter.apply(
            DeliverArtifact(
                "claude",
                "skill/code-review",
                str(payload),
                str(self.destination),
                DeliveryKind.TREE,
            )
        )
        assert isinstance(delivered, Ok), delivered
        recorded = LocalReceiptStore(str(self.state_root)).record_installation(
            COORDINATE, self.receipt, ownership=(KIT,)
        )
        assert isinstance(recorded, Ok), recorded

    def _machine(self):
        machine = read_consumer_machine(
            state_root=str(self.state_root),
            harness_root=str(self.project_root),
            today=TODAY,
            project_root=str(self.project_root),
            user_home=str(self.user_home),
            data_root=str(self.data_root),
        )
        assert isinstance(machine, Ok), machine
        return machine.value

    def test_a_delivered_skill_is_installed_and_ready_when_it_really_is(self) -> None:
        machine = self._machine()
        (installed,) = machine.installed
        self.assertEqual(str(COORDINATE), installed.coordinate)
        self.assertEqual("ready", installed.health)
        self.assertEqual((), installed.drift)

    def test_it_is_answered_by_its_receipt_rather_than_as_a_legacy_manifest_row(self) -> None:
        # D-069 carries an installation no canonical receipt answers for as unadopted: health
        # unknown, one unobserved drift, no offered action. A placed receipt answers for this one.
        (installed,) = self._machine().installed
        self.assertNotEqual("unknown", installed.health)
        self.assertNotEqual((), installed.actions)

    def test_the_collection_that_asked_for_it_still_owns_it(self) -> None:
        (installed,) = self._machine().installed
        self.assertEqual(
            [("collection", "public/collection/reviewers@1.0.0")],
            [(item.kind, item.owner) for item in installed.ownership],
        )

    def test_a_skill_somebody_edited_drifts_on_the_delivery_alone(self) -> None:
        (self.destination / "SKILL.md").write_text("# edited\n", encoding="utf-8")
        (installed,) = self._machine().installed
        self.assertNotEqual("ready", installed.health)
        (drift,) = installed.drift
        self.assertEqual(Component.DELIVERY.value, drift.component.split(":")[0])

    def test_a_skill_somebody_deleted_is_missing_rather_than_uninstalled(self) -> None:
        import shutil

        shutil.rmtree(self.destination)
        (installed,) = self._machine().installed
        self.assertEqual(str(COORDINATE), installed.coordinate)
        (drift,) = installed.drift
        self.assertEqual("missing", drift.kind)

    def test_no_launcher_is_looked_for_and_none_is_reported_missing(self) -> None:
        (installed,) = self._machine().installed
        components = {item.component.split(":")[0] for item in installed.drift}
        self.assertNotIn(Component.LAUNCHER.value, components)
        self.assertEqual("ready", installed.health)


if __name__ == "__main__":
    unittest.main()
