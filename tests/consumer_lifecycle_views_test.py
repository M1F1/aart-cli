from __future__ import annotations

import dataclasses
import json
import unittest

from agent_artifacts.application.consumer_views import (
    CredentialRecordView,
    PresentationProfile,
    project_credential_record,
    project_installed_artifact,
    project_installed_collection,
    project_lifecycle_outcome,
    project_lifecycle_plan,
)
from agent_artifacts.application.execution import (
    ExecutionOutcome,
    LifecycleExecutionOutcome,
    StepOutcome,
    StepStatus,
)
from agent_artifacts.application.intents import (
    InstalledHealth,
    MemberHealth,
    install_intent,
    plan_lifecycle_intent,
    repair_intent,
    uninstall_intent,
)
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.effects import CopyTree, WriteFile
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    ObservedComponent,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason
from agent_artifacts.tui_consumer import (
    render_installed_artifact,
    render_installed_collection,
    render_lifecycle_outcome,
    render_lifecycle_plan,
)


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _coordinate() -> ArtifactCoordinate:
    return ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0")


def _desired() -> DesiredState:
    return DesiredState(
        _coordinate(),
        (
            DesiredComponent(
                ComponentId(Component.PAYLOAD),
                (CopyTree("/cache/github", "/artifacts/github/payload"),),
            ),
            DesiredComponent(
                ComponentId(Component.LAUNCHER),
                (WriteFile("/artifacts/github/launch.sh", str(_digest("a")), True),),
            ),
        ),
    )


def _current(*, launcher: ComponentState = ComponentState.MATCHED) -> CurrentState:
    return CurrentState(
        _coordinate(),
        (
            ObservedComponent(ComponentId(Component.PAYLOAD), ComponentState.MATCHED),
            ObservedComponent(ComponentId(Component.LAUNCHER), launcher),
        ),
    )


class InstalledConsumerViewsTest(unittest.TestCase):
    def test_installed_artifact_uses_canonical_health_and_minimal_drift(self) -> None:
        desired = _desired()
        ownership = (
            OwnershipReason(OwnershipKind.COLLECTION, "company/collection/developer@1.0.0"),
        )

        ready = project_installed_artifact(desired, _current(), ownership=ownership)
        broken = project_installed_artifact(
            desired,
            _current(launcher=ComponentState.DIVERGENT),
            ownership=ownership,
        )

        self.assertEqual(ready.health, InstalledHealth.READY.value)
        self.assertEqual(broken.health, InstalledHealth.BROKEN.value)
        self.assertEqual(tuple(item.component for item in broken.drift), ("launcher",))
        self.assertIn("repair", broken.actions)
        self.assertNotIn("repair", ready.actions)
        rendered = "\n".join(render_installed_artifact(broken, PresentationProfile.FAST))
        self.assertIn("launcher", rendered)
        self.assertNotIn("copy-tree", rendered)

    def test_collection_health_names_members_that_need_attention(self) -> None:
        view = project_installed_collection(
            "company/collection/developer@1.0.0",
            (
                MemberHealth("company/mcp/github@1.0.0", InstalledHealth.BROKEN),
                MemberHealth("company/skill/review@1.0.0", InstalledHealth.READY),
            ),
        )

        self.assertEqual(view.health, InstalledHealth.BROKEN.value)
        self.assertEqual(view.members_requiring_attention, ("company/mcp/github@1.0.0",))
        rendered = "\n".join(render_installed_collection(view, PresentationProfile.FAST))
        self.assertIn("company/mcp/github@1.0.0", rendered)


class LifecycleConsumerViewsTest(unittest.TestCase):
    def test_repair_review_is_the_minimal_reconciliation_plan(self) -> None:
        planned = plan_lifecycle_intent(
            repair_intent(_desired()),
            _current(launcher=ComponentState.DIVERGENT),
            policy=EffectivePolicy(),
        )
        assert isinstance(planned, Ok), planned

        view = project_lifecycle_plan(planned.value)
        fast = "\n".join(render_lifecycle_plan(view, PresentationProfile.FAST))
        verbose = "\n".join(render_lifecycle_plan(view, PresentationProfile.VERBOSE))

        self.assertEqual(tuple(item.component for item in view.drift), ("launcher",))
        self.assertEqual(tuple(item.component for item in view.steps), ("launcher",))
        self.assertIn(view.review_digest, fast)
        self.assertNotIn("content_digest", fast)
        self.assertIn("write-file", verbose)

    def test_retained_uninstall_explains_that_no_shared_artifact_is_removed(self) -> None:
        ownership = (
            OwnershipReason(OwnershipKind.COLLECTION, "company/collection/developer@1.0.0"),
            OwnershipReason(OwnershipKind.DIRECT, str(_coordinate())),
        )
        intent = uninstall_intent(
            _desired(),
            _desired(),
            ownership=ownership,
            release=(ownership[0],),
        )
        planned = plan_lifecycle_intent(intent, _current(), policy=EffectivePolicy())
        assert isinstance(planned, Ok), planned

        view = project_lifecycle_plan(planned.value)
        rendered = "\n".join(render_lifecycle_plan(view, PresentationProfile.FAST))

        self.assertTrue(view.retained)
        self.assertEqual(view.steps, ())
        self.assertIn("still owned directly", rendered)
        self.assertIn("No installed component will be removed", rendered)

    def test_partial_outcome_is_not_rendered_as_success(self) -> None:
        desired = _desired()
        planned = plan_lifecycle_intent(
            install_intent(desired),
            CurrentState(_coordinate()),
            policy=EffectivePolicy(),
        )
        assert isinstance(planned, Ok), planned
        repair = planned.value.repair
        primary = ExecutionOutcome(
            repair.review_digest,
            (
                StepOutcome(repair.steps[0].component, repair.steps[0].effect, StepStatus.APPLIED),
                StepOutcome(repair.steps[1].component, repair.steps[1].effect, StepStatus.FAILED),
            ),
            False,
            repair.drift,
        )
        outcome = LifecycleExecutionOutcome(planned.value, primary)

        view = project_lifecycle_outcome(outcome)
        rendered = "\n".join(render_lifecycle_outcome(view, PresentationProfile.FAST))

        self.assertEqual(view.status, "partially-applied")
        self.assertNotIn("Success", rendered)
        self.assertIn("attention", rendered.lower())
        self.assertEqual(len(view.residual_drift), 2)


class CredentialConsumerViewsTest(unittest.TestCase):
    def test_credential_record_is_reference_only_and_delete_is_dependency_governed(self) -> None:
        reference = CredentialReference(
            InputId("github-token"),
            CredentialProviderRef("macos-keychain", "github.com", "work"),
        )
        observation = CredentialObservation(
            reference,
            ProviderState.AVAILABLE,
            CredentialState.PRESENT,
            "reference resolves",
        )

        depended_on = project_credential_record(
            observation,
            dependants=("company/mcp/github@1.0.0",),
        )
        unused = project_credential_record(observation)

        self.assertNotIn("delete", depended_on.actions)
        self.assertIn("delete", unused.actions)
        fields = {field.name for field in dataclasses.fields(CredentialRecordView)}
        self.assertFalse(fields & {"value", "material", "default"})
        encoded = json.dumps(dataclasses.asdict(depended_on), sort_keys=True)
        self.assertNotIn('"value"', encoded)
        self.assertIn("company/mcp/github@1.0.0", encoded)


if __name__ == "__main__":
    unittest.main()
