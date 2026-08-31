"""What a finished lifecycle action leaves in the store, and what it deliberately does not.

Recording is a decision, not a side effect of succeeding.  A partial install has to leave a record
even though it failed -- otherwise its leftovers belong to nobody -- and a rolled-back update has to
leave the record it already had, because the previous installation is the one that is still true.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.execution import (
    ExecutionOutcome,
    LifecycleExecutionOutcome,
    StepOutcome,
    StepStatus,
)
from agent_artifacts.application.intents import (
    LifecyclePlan,
    install_intent,
    repair_intent,
    uninstall_intent,
    update_intent,
)
from agent_artifacts.application.receipt_recording import (
    RECORDING_INCOMPLETE,
    RecordedOutcome,
    record_lifecycle_outcome,
)
from agent_artifacts.application.reconciliation import plan_repair
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import ConfigureHarness, RemoveOwnedPath, WriteFile
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.receipts import InstallationReceipt
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    ObservedComponent,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason

MOMENT = "2026-08-31T14:32:00+00:00"
ROOT = "/opt/agents/mcp/github"
DIRECT = OwnershipReason(OwnershipKind.DIRECT, "public/mcp/github@1.6.0")
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")
LAUNCHER = ComponentId(Component.LAUNCHER)
HARNESS = ComponentId(Component.HARNESS, "tabnine")


def coordinate(version: str = "1.6.0") -> ArtifactCoordinate:
    return ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), version)


def desired(version: str = "1.6.0", digest: str = "a" * 64) -> DesiredState:
    return DesiredState(
        coordinate(version),
        (
            DesiredComponent(LAUNCHER, (WriteFile(f"{ROOT}/launch.sh", f"sha256:{digest}", True),)),
            DesiredComponent(
                HARNESS,
                (ConfigureHarness("tabnine", "mcp/github", ".tabnine/agent/settings.json"),),
            ),
        ),
    )


def removal(version: str = "1.6.0") -> DesiredState:
    return DesiredState(
        coordinate(version),
        (DesiredComponent(LAUNCHER, (RemoveOwnedPath(ROOT, True),)),),
    )


def current(state: ComponentState, version: str = "1.6.0") -> CurrentState:
    return CurrentState(
        coordinate(version),
        (ObservedComponent(LAUNCHER, state), ObservedComponent(HARNESS, state)),
    )


def receipt() -> InstallationReceipt:
    return InstallationReceipt(
        "mcp/github",
        ROOT,
        f"{ROOT}/launch.sh",
        ObjectDigest("sha256", "a" * 64),
        f"{ROOT}/runtime/.venv/bin/python",
    )


class FakeStore:
    """A store that remembers what it was told, and can be told to refuse."""

    def __init__(self, *, failing: bool = False) -> None:
        self.installations: dict[str, InstallationReceipt] = {}
        self.ownership: dict[str, tuple[OwnershipReason, ...] | None] = {}
        self.forgotten: list[str] = []
        self.actions: list[object] = []
        self.failing = failing

    def record_installation(
        self,
        key: ArtifactCoordinate,
        value: InstallationReceipt,
        *,
        ownership: tuple[OwnershipReason, ...] | None = None,
    ):
        if self.failing:
            return Err((Diagnostic(DiagnosticCode("store-refused"), Severity.ERROR, "no"),))
        self.installations[str(key)] = value
        self.ownership[str(key)] = ownership
        return Ok(f"/store/{key}.json")

    def forget_installation(self, key: ArtifactCoordinate) -> Result[str]:
        self.forgotten.append(str(key))
        return Ok(f"/store/{key}.json")

    def record_action(self, value: object) -> Result[str]:
        self.actions.append(value)
        return Ok("/store/activity/one.json")


class RecordingTest(unittest.TestCase):
    def outcome(
        self,
        intent,
        *,
        statuses: tuple[StepStatus, ...] = (StepStatus.APPLIED,),
        state: ComponentState = ComponentState.DIVERGENT,
        converged: bool | None = True,
        restoration: ExecutionOutcome | None = None,
    ) -> LifecycleExecutionOutcome:
        planned = plan_repair(intent.desired, current(state), policy=EffectivePolicy())
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        plan = LifecyclePlan(intent, planned.value)
        steps = tuple(
            StepOutcome(step.component, step.effect, status, "")
            for step, status in zip(planned.value.steps, statuses, strict=False)
        )
        return LifecycleExecutionOutcome(
            plan, ExecutionOutcome(plan.review_digest, steps, converged), restoration
        )

    def record(self, outcome, *, store=None, **kwargs):
        store = FakeStore() if store is None else store
        recorded = record_lifecycle_outcome(outcome, recorded_at=MOMENT, store=store, **kwargs)
        return store, recorded

    def test_an_install_records_who_asked_for_the_artifact(self):
        outcome = self.outcome(install_intent(desired(), ownership=(KIT, DIRECT)))

        store, recorded = self.record(outcome, receipt=receipt())

        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        self.assertEqual(store.ownership[str(coordinate())], (KIT, DIRECT))

    def test_a_repair_says_nothing_about_who_owns_the_artifact_it_repaired(self):
        """A repair is about the machine, not about who wants the artifact.

        Passing the ownership it happens to know -- which for a repair is none -- would let fixing
        a launcher quietly release a Collection's claim, and the next uninstall would then delete
        an artifact something else still needs.
        """

        outcome = self.outcome(repair_intent(desired()))

        store, recorded = self.record(outcome, receipt=receipt())

        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        self.assertIsNone(store.ownership[str(coordinate())])

    def test_an_uninstall_that_retained_the_artifact_records_what_is_still_owed_on_it(self):
        intent = uninstall_intent(desired(), removal(), ownership=(KIT, DIRECT), release=(DIRECT,))

        store, recorded = self.record(
            self.outcome(intent, state=ComponentState.MATCHED, converged=True), receipt=receipt()
        )

        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        self.assertEqual(store.forgotten, [])
        self.assertEqual(store.ownership[str(coordinate())], (KIT,))

    def test_every_finished_action_reaches_the_timeline_including_the_ones_that_failed(self):
        outcome = self.outcome(
            install_intent(desired()),
            statuses=(StepStatus.FAILED,),
            converged=False,
        )

        store, recorded = self.record(outcome, receipt=receipt())

        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        self.assertIsInstance(recorded.value, RecordedOutcome)
        self.assertEqual(len(store.actions), 1)
        self.assertEqual(store.actions[0].recorded_at, MOMENT)
        self.assertEqual(store.actions[0].summary, "Installed public/mcp/github@1.6.0")

    def test_an_installation_that_took_effect_is_recorded_even_when_it_did_not_finish(self):
        outcome = self.outcome(
            install_intent(desired()),
            statuses=(StepStatus.APPLIED,),
            converged=False,
        )

        store, recorded = self.record(outcome, receipt=receipt())

        self.assertEqual(list(store.installations), ["public/mcp/github@1.6.0"])
        self.assertEqual(recorded.value.installation, "/store/public/mcp/github@1.6.0.json")

    def test_an_installation_that_took_no_effect_at_all_leaves_the_store_untouched(self):
        outcome = self.outcome(
            install_intent(desired()),
            statuses=(StepStatus.FAILED,),
            converged=False,
        )

        store, recorded = self.record(outcome, receipt=receipt())

        self.assertEqual(store.installations, {})
        self.assertEqual(store.forgotten, [])
        self.assertIsNone(recorded.value.installation)

    def test_a_repair_that_found_nothing_to_do_still_refreshes_what_is_installed(self):
        outcome = self.outcome(repair_intent(desired()), statuses=(), state=ComponentState.MATCHED)

        store, recorded = self.record(outcome, receipt=receipt())

        self.assertEqual(list(store.installations), ["public/mcp/github@1.6.0"])
        self.assertFalse(recorded.value.forgotten)

    def test_a_completed_uninstall_forgets_the_record_rather_than_rewriting_it(self):
        intent = uninstall_intent(desired(), removal())
        outcome = self.outcome(intent, statuses=(StepStatus.APPLIED,), state=ComponentState.MATCHED)

        store, recorded = self.record(outcome)

        self.assertEqual(store.forgotten, ["public/mcp/github@1.6.0"])
        self.assertEqual(store.installations, {})
        self.assertTrue(recorded.value.forgotten)

    def test_an_uninstall_that_left_residue_keeps_the_record_that_describes_it(self):
        intent = uninstall_intent(desired(), removal())
        outcome = self.outcome(
            intent,
            statuses=(StepStatus.INTERRUPTED,),
            state=ComponentState.MATCHED,
            converged=False,
        )

        store, recorded = self.record(outcome)

        self.assertEqual(store.forgotten, [])
        self.assertFalse(recorded.value.forgotten)

    def test_a_rolled_back_update_leaves_the_previous_record_standing(self):
        intent = update_intent(desired("1.5.0"), desired("1.6.0", "b" * 64))
        restoration = ExecutionOutcome(ObjectDigest("sha256", "c" * 64), (), True)
        outcome = self.outcome(
            intent,
            statuses=(StepStatus.APPLIED, StepStatus.FAILED),
            converged=False,
            restoration=restoration,
        )

        store, recorded = self.record(outcome, receipt=receipt())

        self.assertEqual(store.installations, {})
        self.assertEqual(store.forgotten, [])
        self.assertEqual(len(store.actions), 1)
        self.assertIsNone(recorded.value.installation)

    def test_recording_an_installation_without_the_receipt_it_describes_is_refused(self):
        outcome = self.outcome(install_intent(desired()), statuses=(StepStatus.APPLIED,))

        store, recorded = self.record(outcome)

        self.assertIsInstance(recorded, Err)
        self.assertEqual(recorded.diagnostics[0].code, RECORDING_INCOMPLETE)
        self.assertEqual(store.installations, {})

    def test_a_store_that_refuses_the_installation_is_reported_rather_than_swallowed(self):
        outcome = self.outcome(install_intent(desired()), statuses=(StepStatus.APPLIED,))

        _, recorded = self.record(outcome, store=FakeStore(failing=True), receipt=receipt())

        self.assertIsInstance(recorded, Err)


if __name__ == "__main__":
    unittest.main()
