"""Planning an artifact a harness reads, where an installation's two halves still have to meet.

The package half of a placement is thin: a Skill declares no runtime, no dependencies and no way of
starting, because nothing starts. The machine half is where it lives -- which harnesses read it,
from what inside its payload, and to where. Neither half can produce a placement alone, and this is
where the join happens without either guessing at the other.

The refusals matter more here than for an MCP server. An artifact that declares how it starts is an
installation, and planning it as a placement would silently drop its launcher: the payload would
land where the harness reads and nothing would ever run it, with no step missing from the plan to
say so.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.artifact_placement import (
    PLACEMENT_NOT_PLANNABLE,
    plan_artifact_placement,
)
from agent_artifacts.application.installation_proposal import (
    PlannedPlacement,
    intended_placement_receipt,
    placement_desired_state,
)
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.effects import DeliverArtifact, DeliveryKind
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.inputs import EnvironmentBinding, SecretInput
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.launch import LaunchContract, Transport
from agent_artifacts.domain.python_runtime import RequirementsFile
from agent_artifacts.domain.receipts import ArtifactDelivery
from agent_artifacts.domain.reconciliation import Component
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
)
from agent_artifacts.domain.requirements import HarnessRequirement
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason, ResolvedArtifact

ROOT = "/home/agent/.agent-artifacts/runtimes/public/skill/code-review"
PAYLOAD_SOURCE = "/var/lib/aart/store/skill/code-review/2.0.0"
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/reviewers@1.0.0")


def _digest(character: str = "a") -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _resolved(kind: str = "skill", name: str = "code-review") -> ResolvedArtifact:
    coordinate = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity(kind, name), "2.0.0")
    return ResolvedArtifact(
        RegistryArtifactVersion(
            coordinate,
            CandidateId("b" * 64),
            _digest("a"),
            _digest("c"),
            _digest("d"),
            _digest("d"),
            _digest("e"),
            PromotionMode.VENDORED,
            PublicationStage.PUBLISHED,
        ),
        (KIT,),
    )


def _delivery(harness: str = "claude") -> ArtifactDelivery:
    return ArtifactDelivery(
        harness,
        f"{ROOT}/payload/skill",
        f"/work/project/.{harness}/skills/code-review",
        DeliveryKind.TREE,
        _digest("f"),
    )


def _plan(**overrides: object):
    fields: dict[str, object] = {
        "root": ROOT,
        "payload_source": PAYLOAD_SOURCE,
        "payload_digest": _digest(),
        "deliveries": (_delivery(),),
    }
    fields.update(overrides)
    artifact = fields.pop("artifact", None) or _resolved()
    description = fields.pop("description", None) or InstallDescription()
    return plan_artifact_placement(artifact, description, **fields)  # type: ignore[arg-type]


class PlacementPlanningTest(unittest.TestCase):
    def test_an_artifact_that_starts_nothing_is_plannable(self) -> None:
        planned = _plan()
        assert isinstance(planned, Ok)
        self.assertIsInstance(planned.value, PlannedPlacement)
        self.assertEqual(ROOT, planned.value.environment.root)
        self.assertEqual(PAYLOAD_SOURCE, planned.value.payload_source)

    def test_every_harness_that_reads_it_becomes_a_requirement(self) -> None:
        planned = _plan(deliveries=(_delivery("claude"), _delivery("codex")))
        assert isinstance(planned, Ok)
        self.assertEqual(
            ["claude", "codex"],
            sorted(
                item.harness
                for item in planned.value.requirements
                if isinstance(item, HarnessRequirement)
            ),
        )

    def test_an_artifact_that_declares_how_it_starts_is_not_a_placement(self) -> None:
        description = InstallDescription(
            contract=LaunchContract("server.py", Transport.STDIO), runtime="python"
        )
        refused = _plan(description=description)
        assert isinstance(refused, Err)
        self.assertEqual(PLACEMENT_NOT_PLANNABLE, refused.diagnostics[0].code)

    def test_dependencies_nothing_would_ever_run_are_refused(self) -> None:
        description = InstallDescription(
            runtime="python", dependencies=RequirementsFile("requirements.txt")
        )
        self.assertIsInstance(_plan(description=description), Err)

    def test_a_secret_with_no_launcher_to_resolve_it_is_refused(self) -> None:
        description = InstallDescription(
            inputs=(SecretInput(InputId("token"), EnvironmentBinding("TOKEN")),)
        )
        self.assertIsInstance(_plan(description=description), Err)

    def test_a_placement_nothing_reads_is_refused(self) -> None:
        self.assertIsInstance(_plan(deliveries=()), Err)

    def test_a_delivery_from_outside_the_artifact_root_is_refused(self) -> None:
        stray = ArtifactDelivery(
            "claude", "/etc/motd", "/work/project/.claude/skills/x", DeliveryKind.FILE, _digest()
        )
        self.assertIsInstance(_plan(deliveries=(stray,)), Err)

    def test_an_unusable_root_is_reported_rather_than_normalized(self) -> None:
        self.assertIsInstance(_plan(root="relative/path"), Err)


class PlacementLoweringTest(unittest.TestCase):
    def test_the_receipt_it_means_to_leave_names_what_it_delivered(self) -> None:
        planned = _plan()
        assert isinstance(planned, Ok)
        receipt = intended_placement_receipt(planned.value)
        self.assertEqual("skill/code-review", receipt.artifact)
        self.assertEqual(ROOT, receipt.root)
        self.assertEqual(("claude",), tuple(item.harness for item in receipt.deliveries))

    def test_the_state_it_converges_on_has_a_payload_and_a_delivery_and_no_launcher(self) -> None:
        planned = _plan()
        assert isinstance(planned, Ok)
        state = placement_desired_state(planned.value)
        self.assertEqual(
            [Component.PAYLOAD, Component.DELIVERY],
            [component.id.component for component in state.components],
        )
        (effect,) = state.components[1].effects
        self.assertIsInstance(effect, DeliverArtifact)

    def test_the_payload_is_copied_from_where_the_plan_says_and_nowhere_else(self) -> None:
        planned = _plan()
        assert isinstance(planned, Ok)
        state = placement_desired_state(planned.value)
        (copy,) = state.components[0].effects
        self.assertEqual(PAYLOAD_SOURCE, copy.source)


if __name__ == "__main__":
    unittest.main()
