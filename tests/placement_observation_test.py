"""What a machine currently answers for an artifact a harness reads.

The counterpart of `observe_installation`. There is no launcher to measure and no interpreter to
find; what there is, is a payload in the artifact's own tree and one delivery per harness that is
either what was delivered, something else, or gone.

The distinction that matters is between a delivery that is not there and one nobody could measure.
A destination that could not be read is `UNKNOWN`, not `ABSENT`: reading it as absent would plan a
delivery over a file somebody may have been editing, which is exactly the failure a receipt exists
to prevent (D-029).
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from agent_artifacts.application.installation_verification import (
    DeliveryObservation,
    PlacementObservation,
)
from agent_artifacts.application.installed_state import (
    current_state_from_placement,
    desired_state_from_placement,
)
from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.receipts import ArtifactDelivery, PlacedArtifactReceipt
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    DriftKind,
    compare_states,
)
from agent_artifacts.io.runtime_projection import observe_placement

COORDINATE = ArtifactCoordinate(
    SourceAlias("public"), ArtifactIdentity("skill", "code-review"), "2.0.0"
)


def _digest(character: str = "a") -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


class _Placed:
    """A real artifact tree and a real harness directory it was delivered into."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = pathlib.Path(self.temporary.name)
        self.root = self.base / "runtimes" / "skill" / "code-review"
        (self.root / "payload").mkdir(parents=True)
        (self.root / "payload" / "SKILL.md").write_text("# review\n", encoding="utf-8")
        self.destination = self.base / "project" / ".claude" / "guidelines" / "review.md"
        self.destination.parent.mkdir(parents=True)
        self.destination.write_text("be kind\n", encoding="utf-8")

    def _receipt(self, digest: ObjectDigest | None = None) -> PlacedArtifactReceipt:
        from agent_artifacts.protocol.hashing import sha256_bytes

        return PlacedArtifactReceipt(
            "skill/code-review",
            str(self.root),
            _digest(),
            (
                ArtifactDelivery(
                    "claude",
                    str(self.root / "payload" / "SKILL.md"),
                    str(self.destination),
                    DeliveryKind.FILE,
                    digest or sha256_bytes(b"be kind\n"),
                ),
            ),
        )


class PlacementObservationTest(_Placed, unittest.TestCase):
    def test_a_delivered_file_is_measured_where_the_harness_reads_it(self) -> None:
        observed = observe_placement(self._receipt())
        self.assertTrue(observed.payload_present)
        (delivery,) = observed.deliveries
        self.assertEqual("claude", delivery.harness)
        self.assertTrue(delivery.present)
        self.assertIsNotNone(delivery.digest)

    def test_a_delivery_somebody_removed_is_absent_and_carries_no_digest(self) -> None:
        self.destination.unlink()
        (delivery,) = observe_placement(self._receipt()).deliveries
        self.assertFalse(delivery.present)
        self.assertIsNone(delivery.digest)

    def test_a_payload_somebody_removed_is_reported_rather_than_assumed(self) -> None:
        import shutil

        shutil.rmtree(self.root / "payload")
        self.assertFalse(observe_placement(self._receipt()).payload_present)

    def test_a_directory_where_a_file_was_delivered_is_present_but_unmeasurable(self) -> None:
        self.destination.unlink()
        self.destination.mkdir()
        (delivery,) = observe_placement(self._receipt()).deliveries
        self.assertTrue(delivery.present)
        self.assertIsNone(delivery.digest)


class PlacementCurrentStateTest(_Placed, unittest.TestCase):
    def _states(self, observation: PlacementObservation, receipt=None):
        receipt = receipt or self._receipt()
        desired = desired_state_from_placement(COORDINATE, receipt, payload_source="/store/x")
        current = current_state_from_placement(desired, receipt, observation)
        return {component.id: component.state for component in current.components}

    def test_an_untouched_placement_matches_every_component(self) -> None:
        states = self._states(observe_placement(self._receipt()))
        self.assertEqual(ComponentState.MATCHED, states[ComponentId(Component.PAYLOAD)])
        self.assertEqual(ComponentState.MATCHED, states[ComponentId(Component.DELIVERY, "claude")])

    def test_a_delivery_somebody_edited_is_divergent_not_absent(self) -> None:
        self.destination.write_text("edited\n", encoding="utf-8")
        states = self._states(observe_placement(self._receipt()))
        self.assertEqual(
            ComponentState.DIVERGENT, states[ComponentId(Component.DELIVERY, "claude")]
        )

    def test_a_delivery_somebody_removed_is_absent(self) -> None:
        self.destination.unlink()
        states = self._states(observe_placement(self._receipt()))
        self.assertEqual(ComponentState.ABSENT, states[ComponentId(Component.DELIVERY, "claude")])

    def test_a_delivery_nobody_could_measure_is_unknown_rather_than_absent(self) -> None:
        observation = PlacementObservation(True, (DeliveryObservation("claude", True, None),))
        states = self._states(observation)
        self.assertEqual(ComponentState.UNKNOWN, states[ComponentId(Component.DELIVERY, "claude")])

    def test_a_delivery_nobody_looked_at_is_left_out_and_compares_as_unobserved(self) -> None:
        # D-029: a component nobody observed is not reported as fine. It is absent from the
        # current state, and the comparison is what names it.
        receipt = self._receipt()
        desired = desired_state_from_placement(COORDINATE, receipt, payload_source="/store/x")
        current = current_state_from_placement(desired, receipt, PlacementObservation(True, ()))
        self.assertNotIn(
            ComponentId(Component.DELIVERY, "claude"),
            {component.id for component in current.components},
        )
        (drift,) = compare_states(desired, current)
        self.assertEqual(ComponentId(Component.DELIVERY, "claude"), drift.component)
        self.assertEqual(DriftKind.UNOBSERVED, drift.kind)

    def test_a_missing_payload_is_absent(self) -> None:
        states = self._states(PlacementObservation(False, (DeliveryObservation("claude", False),)))
        self.assertEqual(ComponentState.ABSENT, states[ComponentId(Component.PAYLOAD)])


if __name__ == "__main__":
    unittest.main()
