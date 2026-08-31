"""An installed artifact a harness reads rather than starts.

INV-010 says artifact kind, package format and runtime protocol are separate dimensions, and the
canonical receipt did not keep them separate: it required a launcher, an interpreter and a transport
of every installation. Only an MCP server has those. A Skill, a guideline, a hook and a memory are
installed by being placed where a harness reads them, and nothing starts.

So four of the five kinds could not be planned, executed or recorded canonically at all (B-033), and
the legacy installer stayed the only thing that could describe them. This is the record that closes
that: identity, the payload it placed, and where each harness reads it from -- with the process
fields absent rather than invented, because a Skill has no interpreter and writing one down would
make a later reconciler look for a process nobody installed.
"""

from __future__ import annotations

import unittest

from agent_artifacts.domain.identifiers import InputId, ObjectDigest
from agent_artifacts.domain.receipts import (
    ArtifactDelivery,
    DeliveryKind,
    PlacedArtifactReceipt,
    config_fingerprint,
    placed_artifact_receipt_from_data,
    placed_artifact_receipt_to_data,
)
from agent_artifacts.domain.result import Err, Ok

ROOT = "/home/agent/.agent-artifacts/runtimes/public/skill/code-review"


def _digest(character: str = "a") -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _delivery(harness: str = "claude", destination: str | None = None) -> ArtifactDelivery:
    return ArtifactDelivery(
        harness,
        f"{ROOT}/payload/skill",
        destination or f"/work/project/.{harness}/skills/code-review",
        DeliveryKind.TREE,
        _digest("b"),
    )


def _receipt(**overrides) -> PlacedArtifactReceipt:
    fields = {
        "artifact": "skill/code-review",
        "root": ROOT,
        "payload_digest": _digest(),
        "deliveries": (_delivery(),),
    }
    fields.update(overrides)
    return PlacedArtifactReceipt(**fields)  # type: ignore[arg-type]


class PlacedArtifactReceiptTest(unittest.TestCase):
    def test_an_artifact_that_starts_nothing_is_a_complete_receipt(self) -> None:
        receipt = _receipt()

        self.assertEqual(receipt.artifact, "skill/code-review")
        self.assertEqual(receipt.deliveries[0].harness, "claude")

    def test_it_records_where_each_harness_reads_the_artifact_from(self) -> None:
        receipt = _receipt(deliveries=(_delivery("claude"), _delivery("tabnine")))

        self.assertEqual([item.harness for item in receipt.deliveries], ["claude", "tabnine"])

    def test_an_install_that_delivered_nothing_is_refused(self) -> None:
        """Placed in its own tree and read by nobody is not an installation, it is a download."""

        with self.assertRaises(ValueError):
            _receipt(deliveries=())

    def test_two_deliveries_to_one_destination_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            _receipt(deliveries=(_delivery("claude"), _delivery("claude")))

    def test_a_relative_destination_is_refused(self) -> None:
        """A harness resolves its own path from a working directory nobody here controls."""

        with self.assertRaises(ValueError):
            _receipt(deliveries=(_delivery(destination=".claude/skills/code-review"),))

    def test_a_relative_root_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _receipt(root="runtimes/skill/code-review")

    def test_it_carries_config_fingerprints_rather_than_config_values(self) -> None:
        receipt = _receipt(config=(config_fingerprint(InputId("style"), "terse"),))

        self.assertNotIn("terse", str(placed_artifact_receipt_to_data(receipt)))


class PlacedArtifactReceiptRoundTripTest(unittest.TestCase):
    def test_a_receipt_survives_being_written_and_read_back(self) -> None:
        receipt = _receipt(
            deliveries=(_delivery("claude"), _delivery("tabnine")),
            config=(config_fingerprint(InputId("style"), "terse"),),
        )

        parsed = placed_artifact_receipt_from_data(placed_artifact_receipt_to_data(receipt))

        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        self.assertEqual(parsed.value, receipt)

    def test_a_record_missing_its_deliveries_is_reported_rather_than_read_as_empty(self) -> None:
        data = placed_artifact_receipt_to_data(_receipt())
        del data["deliveries"]

        parsed = placed_artifact_receipt_from_data(data)

        self.assertIsInstance(parsed, Err, parsed)

    def test_a_record_naming_an_unknown_delivery_kind_is_refused(self) -> None:
        data = placed_artifact_receipt_to_data(_receipt())
        data["deliveries"][0]["kind"] = "symlink"  # type: ignore[index]

        parsed = placed_artifact_receipt_from_data(data)

        self.assertIsInstance(parsed, Err, parsed)


class DeliverySourceTest(unittest.TestCase):
    def test_a_delivery_is_made_from_inside_the_artifact_that_owns_it(self) -> None:
        outside = ArtifactDelivery(
            "claude",
            "/etc/anything",
            "/work/project/.claude/skills/code-review",
            DeliveryKind.TREE,
            _digest("b"),
        )
        with self.assertRaises(ValueError):
            _receipt(deliveries=(outside,))

    def test_a_relative_delivery_source_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            ArtifactDelivery("claude", "payload/skill", "/work/x", DeliveryKind.TREE, _digest("b"))

    def test_the_source_survives_a_round_trip(self) -> None:
        restored = placed_artifact_receipt_from_data(placed_artifact_receipt_to_data(_receipt()))
        assert isinstance(restored, Ok)
        self.assertEqual(f"{ROOT}/payload/skill", restored.value.deliveries[0].source)

    def test_a_delivery_missing_its_source_is_reported_not_defaulted(self) -> None:
        data = placed_artifact_receipt_to_data(_receipt())
        deliveries = data["deliveries"]
        assert isinstance(deliveries, list)
        del deliveries[0]["source"]
        self.assertIsInstance(placed_artifact_receipt_from_data(data), Err)


if __name__ == "__main__":
    unittest.main()
