"""CP-12 reviewed lifecycle execution, locking and supported update restoration."""

from __future__ import annotations

import tempfile
import unittest

from agent_artifacts.application.execution import (
    EXECUTION_REVIEW_STALE,
    LifecycleExecutionStatus,
    execute_lifecycle,
    lifecycle_execution_to_data,
)
from agent_artifacts.application.intents import plan_lifecycle_intent, repair_intent, update_intent
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CreatePythonEnvironment,
    Effect,
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
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.execution import LocalMutationLock

V1 = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.0.0")
V2 = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "2.0.0")
LAUNCHER = ComponentId(Component.LAUNCHER)
HARNESS = ComponentId(Component.HARNESS, "tabnine")


def desired(coordinate: ArtifactCoordinate, digest: str) -> DesiredState:
    return DesiredState(
        coordinate,
        (
            DesiredComponent(
                LAUNCHER,
                (WriteFile("/owned/launch.sh", "sha256:" + digest * 64, True),),
            ),
            DesiredComponent(
                HARNESS,
                (ConfigureHarness("tabnine", "mcp/github", "settings.json"),),
            ),
        ),
    )


def current(
    coordinate: ArtifactCoordinate,
    launcher: ComponentState,
    harness: ComponentState,
) -> CurrentState:
    return CurrentState(
        coordinate,
        (
            ObservedComponent(LAUNCHER, launcher),
            ObservedComponent(HARNESS, harness),
        ),
    )


class _Lock:
    def __init__(self, *, busy: bool = False) -> None:
        self.busy = busy
        self.acquired = 0
        self.released = 0

    def acquire(self):
        self.acquired += 1
        if self.busy:
            return Err(
                (
                    Diagnostic(
                        DiagnosticCode("mutation-lock-busy"),
                        Severity.ERROR,
                        "another mutation is running",
                    ),
                )
            )
        return Ok("lease")

    def release(self, token: str):
        self.assert_token = token
        self.released += 1
        return Ok(None)


class _Interpreter:
    def __init__(self, *, fail_harness_once: bool = False) -> None:
        self.effects: list[Effect] = []
        self.fail_harness_once = fail_harness_once

    def supports(self, effect: Effect) -> bool:
        return True

    def apply(self, effect: Effect):
        self.effects.append(effect)
        if self.fail_harness_once and isinstance(effect, ConfigureHarness):
            self.fail_harness_once = False
            return Err(
                (Diagnostic(DiagnosticCode("harness-failed"), Severity.ERROR, "harness broke"),)
            )
        return Ok("applied")


class ReviewedLifecycleExecutionTest(unittest.TestCase):
    def test_the_scope_lock_wraps_precondition_check_effects_and_reinspection(self) -> None:
        wanted = desired(V1, "a")
        before = current(V1, ComponentState.DIVERGENT, ComponentState.MATCHED)
        reviewed = plan_lifecycle_intent(
            repair_intent(wanted), before, policy=EffectivePolicy()
        ).value
        states = [before, current(V1, ComponentState.MATCHED, ComponentState.MATCHED)]

        def inspect(_desired: DesiredState) -> CurrentState:
            return states.pop(0)

        lock = _Lock()
        interpreter = _Interpreter()
        result = execute_lifecycle(
            reviewed,
            policy=EffectivePolicy(),
            interpreters=(interpreter,),
            inspect=inspect,
            lock=lock,
        )
        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        self.assertIs(result.value.status, LifecycleExecutionStatus.COMPLETED)
        self.assertEqual((lock.acquired, lock.released), (1, 1))
        self.assertEqual(len(interpreter.effects), 1)

    def test_a_changed_precondition_invalidates_review_without_mutating(self) -> None:
        wanted = desired(V1, "a")
        reviewed = plan_lifecycle_intent(
            repair_intent(wanted),
            current(V1, ComponentState.DIVERGENT, ComponentState.MATCHED),
            policy=EffectivePolicy(),
        ).value
        lock = _Lock()
        interpreter = _Interpreter()
        result = execute_lifecycle(
            reviewed,
            policy=EffectivePolicy(),
            interpreters=(interpreter,),
            inspect=lambda _desired: current(V1, ComponentState.MATCHED, ComponentState.MATCHED),
            lock=lock,
        )
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, EXECUTION_REVIEW_STALE)
        self.assertEqual(interpreter.effects, [])
        self.assertEqual(lock.released, 1)

    def test_a_busy_scope_fails_before_inspection_or_effects(self) -> None:
        wanted = desired(V1, "a")
        before = current(V1, ComponentState.DIVERGENT, ComponentState.MATCHED)
        reviewed = plan_lifecycle_intent(
            repair_intent(wanted), before, policy=EffectivePolicy()
        ).value
        calls = 0

        def inspect(_desired: DesiredState) -> CurrentState:
            nonlocal calls
            calls += 1
            return before

        interpreter = _Interpreter()
        result = execute_lifecycle(
            reviewed,
            policy=EffectivePolicy(),
            interpreters=(interpreter,),
            inspect=inspect,
            lock=_Lock(busy=True),
        )
        self.assertIsInstance(result, Err)
        self.assertEqual(calls, 0)
        self.assertEqual(interpreter.effects, [])

    def test_failed_update_restores_verified_previous_state_when_effects_support_it(self) -> None:
        old, new = desired(V1, "a"), desired(V2, "b")
        target_before = current(V2, ComponentState.DIVERGENT, ComponentState.DIVERGENT)
        reviewed = plan_lifecycle_intent(
            update_intent(old, new), target_before, policy=EffectivePolicy()
        ).value
        target_after = current(V2, ComponentState.MATCHED, ComponentState.DIVERGENT)
        old_after_failure = current(V1, ComponentState.DIVERGENT, ComponentState.DIVERGENT)
        old_restored = current(V1, ComponentState.MATCHED, ComponentState.MATCHED)
        queues = {V2: [target_before, target_after], V1: [old_after_failure, old_restored]}

        def inspect(wanted: DesiredState) -> CurrentState:
            return queues[wanted.artifact].pop(0)

        interpreter = _Interpreter(fail_harness_once=True)
        result = execute_lifecycle(
            reviewed,
            policy=EffectivePolicy(),
            interpreters=(interpreter,),
            inspect=inspect,
            lock=_Lock(),
        )
        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        self.assertIs(result.value.status, LifecycleExecutionStatus.RESTORED)
        self.assertIsNotNone(result.value.restoration)
        self.assertTrue(result.value.restoration.converged)
        projected = lifecycle_execution_to_data(result.value)
        self.assertEqual(projected["status"], "restored")
        self.assertEqual(projected["intent"], "update")

    def test_a_non_reversible_partial_update_is_reported_not_called_atomic(self) -> None:
        old = desired(V1, "a")
        new = DesiredState(
            V2,
            (
                DesiredComponent(
                    ComponentId(Component.RUNTIME_ENVIRONMENT),
                    (
                        CreatePythonEnvironment(
                            "mcp/github", "/owned/runtime/.venv", "/usr/bin/python3"
                        ),
                    ),
                ),
                DesiredComponent(
                    HARNESS,
                    (ConfigureHarness("tabnine", "mcp/github", "settings.json"),),
                ),
            ),
        )
        before = CurrentState(
            V2,
            (
                ObservedComponent(
                    ComponentId(Component.RUNTIME_ENVIRONMENT), ComponentState.ABSENT
                ),
                ObservedComponent(HARNESS, ComponentState.DIVERGENT),
            ),
        )
        after = CurrentState(
            V2,
            (
                ObservedComponent(
                    ComponentId(Component.RUNTIME_ENVIRONMENT), ComponentState.MATCHED
                ),
                ObservedComponent(HARNESS, ComponentState.DIVERGENT),
            ),
        )
        reviewed = plan_lifecycle_intent(
            update_intent(old, new), before, policy=EffectivePolicy()
        ).value
        states = [before, after]
        result = execute_lifecycle(
            reviewed,
            policy=EffectivePolicy(),
            interpreters=(_Interpreter(fail_harness_once=True),),
            inspect=lambda _desired: states.pop(0),
            lock=_Lock(),
        )
        self.assertIsInstance(result, Ok)
        self.assertIs(result.value.status, LifecycleExecutionStatus.PARTIALLY_APPLIED)
        self.assertIsNone(result.value.restoration)


class LocalMutationLockTest(unittest.TestCase):
    def test_mutations_are_serialized_per_scope_but_not_globally(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            first = LocalMutationLock(root, "project:/workspace", timeout_seconds=0.01)
            same = LocalMutationLock(root, "project:/workspace", timeout_seconds=0.01)
            other = LocalMutationLock(root, "project:/other", timeout_seconds=0.01)
            lease = first.acquire()
            self.assertIsInstance(lease, Ok)
            self.assertIsInstance(same.acquire(), Err)
            other_lease = other.acquire()
            self.assertIsInstance(other_lease, Ok)
            self.assertEqual(other.release(other_lease.value), Ok(None))
            self.assertEqual(first.release(lease.value), Ok(None))


if __name__ == "__main__":
    unittest.main()
