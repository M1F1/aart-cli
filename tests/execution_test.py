"""CP-12 — executing a repair plan, and finding out whether it actually worked."""

from __future__ import annotations

import unittest

from agent_artifacts.application.execution import (
    EXECUTION_INCOMPLETE,
    EXECUTION_INVALID,
    ExecutionStatus,
    StepStatus,
    execute_repair,
    execution_outcome_to_data,
)
from agent_artifacts.application.reconciliation import plan_repair
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CreatePythonEnvironment,
    Effect,
    EffectCapabilities,
    ReplaceCredential,
    RiskClass,
    WriteFile,
)
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ArtifactIdentity, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    DriftKind,
    ObservedComponent,
)
from agent_artifacts.domain.result import Err, Ok

ARTIFACT = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.5.0")
ROOT = "/opt/agents/mcp/github"

ENVIRONMENT = ComponentId(Component.RUNTIME_ENVIRONMENT)
TOKEN = ComponentId(Component.CREDENTIAL, "github-token")
LAUNCHER = ComponentId(Component.LAUNCHER)
HARNESS = ComponentId(Component.HARNESS, "tabnine")

DESIRED = DesiredState(
    ARTIFACT,
    (
        DesiredComponent(
            ENVIRONMENT,
            (CreatePythonEnvironment("mcp/github", f"{ROOT}/runtime/.venv", "/usr/bin/python3"),),
        ),
        DesiredComponent(TOKEN, (ReplaceCredential("github-token", "macos-keychain"),)),
        DesiredComponent(LAUNCHER, (WriteFile(f"{ROOT}/launch.sh", "sha256:" + "a" * 64, True),)),
        DesiredComponent(
            HARNESS, (ConfigureHarness("tabnine", "mcp/github", ".tabnine/agent/settings.json"),)
        ),
    ),
)


def observed(**states: ComponentState) -> CurrentState:
    names = {"environment": ENVIRONMENT, "token": TOKEN, "launcher": LAUNCHER, "harness": HARNESS}
    return CurrentState(
        ARTIFACT,
        tuple(
            ObservedComponent(identifier, states.get(name, ComponentState.MATCHED))
            for name, identifier in names.items()
        ),
    )


class _Interpreter:
    """Records what it was asked to do, and fails whatever it was told to fail."""

    def __init__(self, *, refuse: type | None = None, fail: type | None = None) -> None:
        self.applied: list[Effect] = []
        self._refuse = refuse
        self._fail = fail

    def supports(self, effect: Effect) -> bool:
        return self._refuse is None or not isinstance(effect, self._refuse)

    def apply(self, effect: Effect):
        self.applied.append(effect)
        if self._fail is not None and isinstance(effect, self._fail):
            return Err(
                (Diagnostic(DiagnosticCode("interpreter-failed"), Severity.ERROR, "it broke"),)
            )
        return Ok("applied")


class _Inspector:
    """Returns each queued state in turn, so a test can say what a re-inspection finds."""

    def __init__(self, *states: CurrentState) -> None:
        self._states = list(states)
        self.calls = 0

    def __call__(self) -> CurrentState:
        self.calls += 1
        return self._states.pop(0) if len(self._states) > 1 else self._states[0]


def plan(current: CurrentState, *, desired: DesiredState = DESIRED):
    result = plan_repair(desired, current, policy=EffectivePolicy())
    assert isinstance(result, Ok), getattr(result, "diagnostics", ())
    return result.value


class ExecutionTest(unittest.TestCase):
    def test_a_plan_with_nothing_to_do_touches_no_interpreter_and_still_re_inspects(self):
        interpreter = _Interpreter()
        inspect = _Inspector(observed())
        outcome = execute_repair(plan(observed()), DESIRED, (interpreter,), inspect=inspect)
        self.assertIsInstance(outcome, Ok, getattr(outcome, "diagnostics", ()))
        self.assertEqual(interpreter.applied, [])
        self.assertEqual(inspect.calls, 1)
        self.assertTrue(outcome.value.converged)
        self.assertIs(outcome.value.status, ExecutionStatus.CONVERGED)

    def test_a_repair_that_works_applies_only_its_steps_and_converges(self):
        interpreter = _Interpreter()
        outcome = execute_repair(
            plan(observed(launcher=ComponentState.DIVERGENT)),
            DESIRED,
            (interpreter,),
            inspect=_Inspector(observed()),
        ).value
        self.assertEqual(len(interpreter.applied), 1)
        self.assertIsInstance(interpreter.applied[0], WriteFile)
        self.assertEqual([step.status for step in outcome.steps], [StepStatus.APPLIED])
        self.assertTrue(outcome.converged)

    def test_a_repair_that_ran_cleanly_and_changed_nothing_is_not_a_success(self):
        """The failure this whole slice exists to catch: convergence is measured, not assumed."""

        still_broken = observed(launcher=ComponentState.DIVERGENT)
        outcome = execute_repair(
            plan(still_broken),
            DESIRED,
            (_Interpreter(),),
            inspect=_Inspector(still_broken),
        ).value
        self.assertEqual([step.status for step in outcome.steps], [StepStatus.APPLIED])
        self.assertFalse(outcome.converged)
        self.assertIs(outcome.status, ExecutionStatus.UNCONVERGED)
        self.assertEqual(
            [item.component for item in outcome.residual_drift], [ComponentId(Component.LAUNCHER)]
        )

    def test_a_failure_part_way_leaves_the_rest_unattempted_and_still_re_inspects(self):
        interpreter = _Interpreter(fail=CreatePythonEnvironment)
        inspect = _Inspector(observed(environment=ComponentState.ABSENT))
        outcome = execute_repair(
            plan(observed(environment=ComponentState.ABSENT, harness=ComponentState.ABSENT)),
            DESIRED,
            (interpreter,),
            inspect=inspect,
        ).value
        self.assertEqual(
            [step.status for step in outcome.steps],
            [StepStatus.FAILED, StepStatus.NOT_ATTEMPTED],
        )
        self.assertEqual(len(interpreter.applied), 1)
        self.assertEqual(inspect.calls, 1)
        self.assertIs(outcome.status, ExecutionStatus.FAILED)
        self.assertIn("it broke", outcome.steps[0].detail)

    def test_an_effect_nobody_claims_fails_rather_than_being_skipped(self):
        interpreter = _Interpreter(refuse=WriteFile)
        outcome = execute_repair(
            plan(observed(launcher=ComponentState.ABSENT)),
            DESIRED,
            (interpreter,),
            inspect=_Inspector(observed()),
        ).value
        self.assertEqual([step.status for step in outcome.steps], [StepStatus.FAILED])
        self.assertEqual(interpreter.applied, [])
        self.assertIn("no interpreter", outcome.steps[0].detail)

    def test_the_first_interpreter_that_claims_an_effect_gets_it(self):
        first = _Interpreter(refuse=WriteFile)
        second = _Interpreter()
        execute_repair(
            plan(observed(launcher=ComponentState.ABSENT)),
            DESIRED,
            (first, second),
            inspect=_Inspector(observed()),
        )
        self.assertEqual(first.applied, [])
        self.assertEqual(len(second.applied), 1)

    def test_an_incomplete_plan_is_refused_unless_the_caller_accepts_it(self):
        weak = DesiredState(
            ARTIFACT,
            (
                DesiredComponent(LAUNCHER, (_WeakEffect(),)),  # type: ignore[arg-type]
                DesiredComponent(
                    HARNESS,
                    (ConfigureHarness("tabnine", "mcp/github", ".tabnine/agent/settings.json"),),
                ),
            ),
        )
        current = CurrentState(
            ARTIFACT,
            (
                ObservedComponent(LAUNCHER, ComponentState.DIVERGENT),
                ObservedComponent(HARNESS, ComponentState.DIVERGENT),
            ),
        )
        incomplete = plan(current, desired=weak)
        refused = execute_repair(incomplete, weak, (_Interpreter(),), inspect=_Inspector(current))
        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.diagnostics[0].code, EXECUTION_INCOMPLETE)

        accepted = execute_repair(
            incomplete,
            weak,
            (_Interpreter(),),
            inspect=_Inspector(current),
            allow_incomplete=True,
        )
        self.assertIsInstance(accepted, Ok)
        self.assertIs(accepted.value.status, ExecutionStatus.UNCONVERGED)

    def test_a_plan_and_a_desired_state_that_disagree_are_refused(self):
        other = DesiredState(
            ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "gitlab"), "1.0.0"),
            (DesiredComponent(LAUNCHER, (WriteFile("/x/launch.sh", "sha256:" + "a" * 64),)),),
        )
        result = execute_repair(
            plan(observed(launcher=ComponentState.ABSENT)),
            other,
            (_Interpreter(),),
            inspect=_Inspector(observed()),
        )
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, EXECUTION_INVALID)

    def test_an_inspection_that_cannot_run_is_reported_rather_than_assumed(self):
        def broken() -> CurrentState:
            raise OSError("the disk went away")

        outcome = execute_repair(
            plan(observed(launcher=ComponentState.ABSENT)),
            DESIRED,
            (_Interpreter(),),
            inspect=broken,
        ).value
        self.assertIsNone(outcome.converged)
        self.assertIs(outcome.status, ExecutionStatus.UNVERIFIED)
        self.assertIn("the disk went away", outcome.detail)

    def test_the_outcome_names_components_and_carries_no_value(self):
        outcome = execute_repair(
            plan(observed(token=ComponentState.DIVERGENT)),
            DESIRED,
            (_Interpreter(),),
            inspect=_Inspector(observed()),
        ).value
        projected = execution_outcome_to_data(outcome)
        self.assertEqual(projected["status"], "converged")
        self.assertEqual(projected["steps"][0]["component"], "credential:github-token")
        self.assertEqual(projected["steps"][0]["status"], "applied")
        self.assertEqual(projected["residual_drift"], [])

    def test_residual_drift_after_a_partial_run_names_what_is_still_wrong(self):
        outcome = execute_repair(
            plan(observed(environment=ComponentState.ABSENT, harness=ComponentState.ABSENT)),
            DESIRED,
            (_Interpreter(fail=CreatePythonEnvironment),),
            inspect=_Inspector(
                observed(environment=ComponentState.ABSENT, harness=ComponentState.ABSENT)
            ),
        ).value
        self.assertEqual(
            [(item.component, item.kind) for item in outcome.residual_drift],
            [(ENVIRONMENT, DriftKind.MISSING), (HARNESS, DriftKind.MISSING)],
        )

    def test_an_interruption_stops_execution_and_still_re_inspects(self):
        class Interrupting(_Interpreter):
            def apply(self, effect: Effect):
                raise KeyboardInterrupt

        inspect = _Inspector(observed(launcher=ComponentState.ABSENT))
        outcome = execute_repair(
            plan(observed(launcher=ComponentState.ABSENT)),
            DESIRED,
            (Interrupting(),),
            inspect=inspect,
        ).value
        self.assertIs(outcome.status, ExecutionStatus.INTERRUPTED)
        self.assertEqual(outcome.steps[0].status, StepStatus.INTERRUPTED)
        self.assertEqual(inspect.calls, 1)

    def test_an_adapter_exception_is_a_failed_step_not_a_skipped_reinspection(self):
        class Broken(_Interpreter):
            def apply(self, effect: Effect):
                raise RuntimeError("adapter broke")

        inspect = _Inspector(observed(launcher=ComponentState.ABSENT))
        outcome = execute_repair(
            plan(observed(launcher=ComponentState.ABSENT)),
            DESIRED,
            (Broken(),),
            inspect=inspect,
        ).value
        self.assertIs(outcome.status, ExecutionStatus.FAILED)
        self.assertIn("adapter broke", outcome.steps[0].detail)
        self.assertEqual(inspect.calls, 1)


class _WeakEffect:
    risk = RiskClass.HIGH_RISK_EXECUTION
    capabilities = EffectCapabilities(True, False, False, False)


if __name__ == "__main__":
    unittest.main()
