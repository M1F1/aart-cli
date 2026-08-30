"""CP-12 lifecycle intents are different desired states over one reconciler."""

from __future__ import annotations

import unittest

from agent_artifacts.application.intents import (
    InstalledHealth,
    LifecycleIntentKind,
    MemberHealth,
    collection_health,
    configure_intent,
    credential_rotation_intent,
    downgrade_intent,
    harness_reconfiguration_intent,
    install_intent,
    installation_health,
    plan_lifecycle_intent,
    repair_intent,
    uninstall_intent,
    update_intent,
)
from agent_artifacts.application.reconciliation import RepairPlan
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    ReplaceCredential,
    UnconfigureHarness,
    WriteFile,
)
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
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

V1 = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.5.0")
V2 = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "2.0.0")
LAUNCHER = ComponentId(Component.LAUNCHER)
TOKEN = ComponentId(Component.CREDENTIAL, "github-token")
HARNESS = ComponentId(Component.HARNESS, "tabnine")


def launcher(digest: str = "a") -> DesiredComponent:
    return DesiredComponent(
        LAUNCHER,
        (WriteFile("/opt/aart/mcp/github/launch.sh", "sha256:" + digest * 64, True),),
    )


def token(provider: str = "macos-keychain") -> DesiredComponent:
    return DesiredComponent(
        TOKEN,
        (ReplaceCredential("github-token", provider),),
    )


def harness(destination: str = ".tabnine/agent/settings.json") -> DesiredComponent:
    return DesiredComponent(
        HARNESS,
        (ConfigureHarness("tabnine", "mcp/github", destination),),
    )


def desired(coordinate: ArtifactCoordinate = V1) -> DesiredState:
    return DesiredState(coordinate, (launcher(), token(), harness()))


def observed(
    coordinate: ArtifactCoordinate = V1,
    *,
    launcher_state: ComponentState = ComponentState.MATCHED,
    token_state: ComponentState = ComponentState.MATCHED,
    harness_state: ComponentState = ComponentState.MATCHED,
) -> CurrentState:
    return CurrentState(
        coordinate,
        (
            ObservedComponent(LAUNCHER, launcher_state),
            ObservedComponent(TOKEN, token_state),
            ObservedComponent(HARNESS, harness_state),
        ),
    )


class LifecycleIntentTest(unittest.TestCase):
    def test_every_intent_lowers_through_the_same_repair_plan(self) -> None:
        old = desired()
        newer = DesiredState(V2, old.components)
        removal = DesiredState(
            V1,
            (
                DesiredComponent(
                    HARNESS,
                    (UnconfigureHarness("tabnine", "github", ".tabnine/agent/settings.json"),),
                    target=ComponentState.ABSENT,
                ),
            ),
        )
        intents_and_current = (
            (install_intent(old), observed()),
            (update_intent(old, newer), observed(V2)),
            (configure_intent(old, (launcher("b"),)), observed()),
            (repair_intent(old), observed()),
            (credential_rotation_intent(old, (token("one-password"),)), observed()),
            (
                harness_reconfiguration_intent(old, (harness(".tabnine/agent/settings-v2.json"),)),
                observed(),
            ),
            (downgrade_intent(newer, old), observed()),
            (
                uninstall_intent(old, removal),
                CurrentState(V1, (ObservedComponent(HARNESS, ComponentState.MATCHED),)),
            ),
        )

        self.assertEqual(
            [item.kind for item, _current in intents_and_current],
            list(LifecycleIntentKind),
        )
        for intent, current in intents_and_current:
            planned = plan_lifecycle_intent(intent, current, policy=EffectivePolicy())
            self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
            self.assertIsInstance(planned.value.repair, RepairPlan)

    def test_component_specific_intents_refuse_unrelated_replacements(self) -> None:
        with self.assertRaises(ValueError):
            configure_intent(desired(), (token(),))
        with self.assertRaises(ValueError):
            credential_rotation_intent(desired(), (launcher(),))
        with self.assertRaises(ValueError):
            harness_reconfiguration_intent(desired(), (launcher(),))

    def test_update_and_downgrade_have_semantic_direction(self) -> None:
        with self.assertRaises(ValueError):
            update_intent(desired(V2), desired(V1))
        with self.assertRaises(ValueError):
            downgrade_intent(desired(V1), desired(V2))
        with self.assertRaises(ValueError):
            update_intent(desired(V1), desired(V1))

    def test_collection_uninstall_retains_an_artifact_owned_elsewhere(self) -> None:
        collection = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-kit@1.0.0")
        direct = OwnershipReason(OwnershipKind.DIRECT, "public/mcp/github@1.5.0")
        removal = DesiredState(V1, ())
        intent = uninstall_intent(
            desired(), removal, ownership=(collection, direct), release=(collection,)
        )

        self.assertTrue(intent.retained)
        self.assertEqual(intent.retained_ownership, (direct,))
        self.assertEqual(intent.desired, desired())
        planned = plan_lifecycle_intent(intent, observed(), policy=EffectivePolicy())
        self.assertIsInstance(planned, Ok)
        self.assertEqual(planned.value.repair.steps, ())

    def test_the_final_owner_removal_uses_the_uninstall_desired_state(self) -> None:
        collection = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-kit@1.0.0")
        removal = DesiredState(V1, ())
        intent = uninstall_intent(
            desired(), removal, ownership=(collection,), release=(collection,)
        )
        self.assertFalse(intent.retained)
        self.assertEqual(intent.desired, removal)


class InstalledHealthTest(unittest.TestCase):
    def test_health_distinguishes_ready_update_attention_and_broken(self) -> None:
        wanted = desired()
        self.assertIs(installation_health(wanted, observed()), InstalledHealth.READY)
        self.assertIs(
            installation_health(wanted, observed(), update_available=True),
            InstalledHealth.UPDATE,
        )
        self.assertIs(
            installation_health(wanted, observed(token_state=ComponentState.UNKNOWN)),
            InstalledHealth.ATTENTION,
        )
        self.assertIs(
            installation_health(wanted, observed(launcher_state=ComponentState.ABSENT)),
            InstalledHealth.BROKEN,
        )

    def test_collection_health_propagates_and_names_unhealthy_members(self) -> None:
        health = collection_health(
            (
                MemberHealth("mcp/github", InstalledHealth.READY),
                MemberHealth("mcp/database", InstalledHealth.BROKEN),
                MemberHealth("skill/review", InstalledHealth.ATTENTION),
            )
        )
        self.assertIs(health.status, InstalledHealth.BROKEN)
        self.assertEqual(
            [item.artifact for item in health.members_requiring_attention],
            ["mcp/database", "skill/review"],
        )


if __name__ == "__main__":
    unittest.main()
