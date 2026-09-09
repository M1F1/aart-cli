"""One Selection containing artifacts a harness reads, offered the same way as ones it starts.

`offer_installation` is the one place a whole Selection is planned, and until now it could only
plan MCP servers: it called `plan_artifact_installation`, which refuses anything that declares no
launch contract. A Selection with a Skill in it therefore refused entirely -- not just the Skill.

The discriminator is what the artifact declares, not a flag somebody passes. An artifact that says
how it starts is installed; one that says nothing is placed. Both planners already refuse the
other's case, so the choice cannot silently go the wrong way.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.installation_offer import ArtifactPlacement, offer_installation
from agent_artifacts.application.installation_proposal import (
    PlannedInstallation,
    PlannedPlacement,
)
from agent_artifacts.domain.effects import DeliverArtifact, DeliveryKind
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.inspection import RemediationCapability, RemediationCapabilityKind
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.receipts import ArtifactDelivery
from agent_artifacts.domain.reconciliation import CurrentState
from agent_artifacts.domain.requirements import HarnessRequirement
from agent_artifacts.domain.result import Err, Ok
from tests.artifact_installation_test import (
    INTERPRETER,
    PAYLOAD_SOURCE,
    _capabilities,
    _facts,
    _Inspector,
    _Keychain,
)
from tests.artifact_placement_test import _resolved as _resolved_skill
from tests.installation_offer_test import _placement
from tests.installation_proposal_test import ROOT

SKILL_ROOT = "/home/agent/.agent-artifacts/runtimes/public/skill/code-review"


def _skill_placement(harness: str = "claude", **overrides: object) -> ArtifactPlacement:
    fields: dict[str, object] = {
        "artifact": _resolved_skill(),
        "description": InstallDescription(),
        "root": SKILL_ROOT,
        "payload_source": PAYLOAD_SOURCE,
        "payload_digest": ObjectDigest("sha256", "a" * 64),
        "deliveries": (
            ArtifactDelivery(
                harness,
                f"{SKILL_ROOT}/payload",
                f"/work/project/.{harness}/skills/code-review",
                DeliveryKind.TREE,
                ObjectDigest("sha256", "f" * 64),
            ),
        ),
    }
    fields.update(overrides)
    return ArtifactPlacement(**fields)  # type: ignore[arg-type]


def _nothing_installed(planned):
    return CurrentState(planned.coordinate)


def _machine() -> tuple[RemediationCapability, ...]:
    """This machine, plus permission to configure the harness that would read the Skill."""

    return _capabilities() + (
        RemediationCapability(RemediationCapabilityKind.HARNESS_CONFIGURATION, "claude"),
    )


def _offer(*placements):
    return offer_installation(
        placements,
        policy=EffectivePolicy(),
        facts=_facts(),
        inspect=_Inspector(_machine()),
        observe=_nothing_installed,
        base_interpreter=INTERPRETER,
        resolvers=(_Keychain(),),
    )


class PlacementOfferTest(unittest.TestCase):
    def test_an_artifact_that_starts_nothing_is_planned_as_a_placement(self) -> None:
        offered = _offer(_skill_placement())
        assert isinstance(offered, Ok), getattr(offered, "diagnostics", ())
        (planned,) = offered.value.installations
        self.assertIsInstance(planned, PlannedPlacement)
        self.assertEqual("skill/code-review", str(planned.coordinate.artifact))

    def test_a_selection_may_hold_both_kinds_at_once(self) -> None:
        offered = _offer(_placement(), _skill_placement())
        assert isinstance(offered, Ok), getattr(offered, "diagnostics", ())
        self.assertEqual(
            [PlannedInstallation, PlannedPlacement],
            [type(item) for item in offered.value.installations],
        )

    def test_the_harness_that_reads_it_is_measured_like_any_other_requirement(self) -> None:
        offered = _offer(_skill_placement())
        assert isinstance(offered, Ok), getattr(offered, "diagnostics", ())
        (planned,) = offered.value.installations
        self.assertEqual(
            ("claude",),
            tuple(
                item.harness
                for item in planned.requirements
                if isinstance(item, HarnessRequirement)
            ),
        )

    def test_what_is_already_where_it_would_be_delivered_is_observed_first(self) -> None:
        seen = []
        offer_installation(
            (_skill_placement(),),
            policy=EffectivePolicy(),
            facts=_facts(),
            inspect=_Inspector(_machine()),
            observe=lambda planned: seen.append(planned) or CurrentState(planned.coordinate),
            base_interpreter=INTERPRETER,
        )
        (observed,) = seen
        self.assertIsInstance(observed, PlannedPlacement)

    def test_a_placement_with_nowhere_to_deliver_refuses_the_whole_offer(self) -> None:
        self.assertIsInstance(_offer(_skill_placement(deliveries=())), Err)

    def test_an_mcp_artifact_given_deliveries_is_still_installed_not_placed(self) -> None:
        # The description decides. An MCP server that somehow arrived with deliveries is an
        # installation with something odd attached, not a Skill.
        placement = _placement(
            deliveries=(
                ArtifactDelivery(
                    "claude",
                    f"{ROOT}/payload",
                    "/work/project/.claude/skills/github",
                    DeliveryKind.TREE,
                    ObjectDigest("sha256", "f" * 64),
                ),
            )
        )
        offered = _offer(placement)
        assert isinstance(offered, Ok), getattr(offered, "diagnostics", ())
        (planned,) = offered.value.installations
        self.assertIsInstance(planned, PlannedInstallation)


class PlacementProposalTest(unittest.TestCase):
    def test_the_effects_a_placement_would_run_are_deliveries(self) -> None:
        from agent_artifacts.application.consumer_session import begin_installation
        from tests.installation_proposal_test import _selection

        offered = _offer(_skill_placement())
        assert isinstance(offered, Ok), getattr(offered, "diagnostics", ())
        begun = begin_installation(
            offered.value.installations,
            _selection(_resolved_skill()),
            offered.value.facts,
            EffectivePolicy(),
            observed=offered.value.observed,
            selected_remediations=offered.value.selected(),
        )
        assert isinstance(begun, Ok), getattr(begun, "diagnostics", ())
        self.assertTrue(
            any(isinstance(effect, DeliverArtifact) for effect in begun.value.proposal.effects)
        )

    def test_no_launcher_is_written_for_something_that_starts_nothing(self) -> None:
        from agent_artifacts.application.consumer_session import begin_installation
        from agent_artifacts.domain.effects import WriteFile
        from tests.installation_proposal_test import _selection

        offered = _offer(_skill_placement())
        assert isinstance(offered, Ok), getattr(offered, "diagnostics", ())
        begun = begin_installation(
            offered.value.installations,
            _selection(_resolved_skill()),
            offered.value.facts,
            EffectivePolicy(),
            observed=offered.value.observed,
            selected_remediations=offered.value.selected(),
        )
        assert isinstance(begun, Ok), getattr(begun, "diagnostics", ())
        self.assertFalse(
            any(isinstance(effect, WriteFile) for effect in begun.value.proposal.effects)
        )


if __name__ == "__main__":
    unittest.main()
