"""The desired state of an artifact a harness reads, and the effect that puts it there.

A placed artifact converges to a payload and one delivery per harness. It has no launcher, no
runtime environment and no dependencies, and this is where that has to be true rather than merely
unmentioned: a reconciler compares components, so a LAUNCHER component nobody installed is drift
that repairs into a process that should not exist.

Delivery is deliberately its own effect at CONFIGURATION_MUTATION rather than a `CopyTree`. The
destination belongs to the harness, not to AART. A policy ceiling that refuses to register an MCP
server has to refuse writing a Skill straight into the directory that same harness reads, and a
LOCAL_MUTATION copy would have slipped underneath it -- which is exactly the material risk Fast
review is forbidden to hide.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.installed_state import (
    desired_state_from_placement,
    removal_state_from_placement,
)
from agent_artifacts.domain.effects import (
    DeliverArtifact,
    DeliveryKind,
    RiskClass,
    WithdrawArtifact,
    effect_to_data,
)
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ObjectDigest
from agent_artifacts.domain.receipts import ArtifactDelivery, PlacedArtifactReceipt
from agent_artifacts.domain.reconciliation import Component, ComponentState

ROOT = "/home/agent/.agent-artifacts/runtimes/public/skill/code-review"
SOURCE = f"{ROOT}/payload/skill"


def _coordinate() -> ArtifactCoordinate:
    return ArtifactCoordinate("public", "skill", "code-review")


def _digest(character: str = "a") -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _delivery(harness: str = "claude", destination: str | None = None) -> ArtifactDelivery:
    return ArtifactDelivery(
        harness,
        SOURCE,
        destination or f"/work/project/.{harness}/skills/code-review",
        DeliveryKind.TREE,
        _digest("b"),
    )


def _receipt(deliveries: tuple[ArtifactDelivery, ...] = ()) -> PlacedArtifactReceipt:
    return PlacedArtifactReceipt("skill/code-review", ROOT, _digest(), deliveries or (_delivery(),))


class DeliveryEffectTest(unittest.TestCase):
    def test_delivery_is_a_configuration_mutation_not_a_local_one(self) -> None:
        effect = DeliverArtifact("claude", "skill/code-review", SOURCE, "/p/.claude/x", "tree")
        self.assertEqual(RiskClass.CONFIGURATION_MUTATION, effect.risk)
        self.assertGreater(effect.risk, RiskClass.LOCAL_MUTATION)

    def test_withdrawing_a_delivery_is_reversible_while_the_payload_stands(self) -> None:
        effect = WithdrawArtifact("claude", "skill/code-review", "/p/.claude/x", "tree")
        self.assertEqual(RiskClass.CONFIGURATION_MUTATION, effect.risk)
        self.assertTrue(effect.capabilities.reversible)

    def test_a_delivery_says_which_shape_it_places(self) -> None:
        data = effect_to_data(
            DeliverArtifact("claude", "skill/code-review", SOURCE, "/p/.claude/x", "file")
        )
        self.assertEqual("deliver-artifact", data["kind"])
        self.assertEqual("file", data["delivery"])
        self.assertEqual("configuration-mutation", data["risk"])
        self.assertEqual("/p/.claude/x", data["destination"])

    def test_a_delivery_of_an_unknown_shape_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            DeliverArtifact("claude", "skill/code-review", SOURCE, "/p/.claude/x", "symlink")

    def test_a_delivery_with_a_blank_harness_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            DeliverArtifact("", "skill/code-review", SOURCE, "/p/.claude/x", "tree")


class PlacedDesiredStateTest(unittest.TestCase):
    def test_a_placed_artifact_converges_to_a_payload_and_its_deliveries(self) -> None:
        state = desired_state_from_placement(
            _coordinate(), _receipt(), payload_source="/store/objects/aaa"
        )
        self.assertEqual(
            [Component.PAYLOAD, Component.DELIVERY],
            [component.id.component for component in state.components],
        )

    def test_no_launcher_runtime_or_dependency_component_is_invented(self) -> None:
        state = desired_state_from_placement(
            _coordinate(), _receipt(), payload_source="/store/objects/aaa"
        )
        present = {component.id.component for component in state.components}
        self.assertNotIn(Component.LAUNCHER, present)
        self.assertNotIn(Component.RUNTIME_ENVIRONMENT, present)
        self.assertNotIn(Component.RUNTIME_DEPENDENCIES, present)

    def test_an_omitted_payload_source_omits_the_payload_rather_than_guessing_it(self) -> None:
        state = desired_state_from_placement(_coordinate(), _receipt())
        self.assertEqual(
            [Component.DELIVERY], [component.id.component for component in state.components]
        )

    def test_each_harness_reads_its_own_named_delivery(self) -> None:
        receipt = _receipt((_delivery("claude"), _delivery("codex")))
        state = desired_state_from_placement(_coordinate(), receipt)
        self.assertEqual(
            ["claude", "codex"], sorted(component.id.name for component in state.components)
        )

    def test_the_delivery_effect_carries_the_payload_it_places(self) -> None:
        state = desired_state_from_placement(_coordinate(), _receipt())
        (effect,) = state.components[0].effects
        assert isinstance(effect, DeliverArtifact)
        self.assertEqual("skill/code-review", effect.artifact)
        self.assertEqual("/work/project/.claude/skills/code-review", effect.destination)
        self.assertTrue(effect.source.startswith(ROOT))

    def test_two_deliveries_to_one_harness_are_refused_by_the_receipt(self) -> None:
        with self.assertRaises(ValueError):
            _receipt((_delivery("claude"), _delivery("claude", "/work/project/.claude/other")))


class PlacedRemovalStateTest(unittest.TestCase):
    def test_removal_withdraws_every_delivery_and_removes_the_payload(self) -> None:
        state = removal_state_from_placement(_coordinate(), _receipt())
        self.assertTrue(
            all(component.target is ComponentState.ABSENT for component in state.components)
        )
        self.assertEqual(
            [Component.PAYLOAD, Component.DELIVERY],
            [component.id.component for component in state.components],
        )

    def test_removal_withdraws_from_the_harness_rather_than_deleting_a_path_it_owns(self) -> None:
        state = removal_state_from_placement(_coordinate(), _receipt())
        delivery = next(
            component
            for component in state.components
            if component.id.component is Component.DELIVERY
        )
        (effect,) = delivery.effects
        assert isinstance(effect, WithdrawArtifact)
        self.assertEqual("claude", effect.harness)
        self.assertEqual("/work/project/.claude/skills/code-review", effect.destination)


if __name__ == "__main__":
    unittest.main()
