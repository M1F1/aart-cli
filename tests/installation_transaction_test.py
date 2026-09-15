"""A bulk Selection executes as one reviewed installation transaction."""

from __future__ import annotations

import unittest

from agent_artifacts.application.execution import (
    EXECUTION_REVIEW_STALE,
    InstallationExecutionStatus,
    LifecycleExecutionStatus,
    execute_installation,
    installation_execution_to_data,
)
from agent_artifacts.application.installation_proposal import (
    PlannedInstallation,
    desired_state_for,
    propose_installation,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import Effect
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.plans import install_plan_to_data
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.reconciliation import ComponentState, CurrentState, ObservedComponent
from agent_artifacts.domain.result import Err, Ok
from tests.installation_proposal_test import (
    COORDINATE,
    _launcher,
    _nothing_installed,
    _planned,
    _resolved,
    _selection,
)


class _Lock:
    def __init__(self) -> None:
        self.acquired = 0
        self.released = 0

    def acquire(self):
        self.acquired += 1
        return Ok("one-transaction")

    def release(self, token: str):
        self.released += 1
        self.token = token
        return Ok(None)


class _Interpreter:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.effects: list[Effect] = []
        self.fail_first = fail_first

    def supports(self, _effect: Effect) -> bool:
        return True

    def apply(self, effect: Effect):
        self.effects.append(effect)
        if self.fail_first:
            self.fail_first = False
            return Err(
                (
                    Diagnostic(
                        DiagnosticCode("transaction-effect-failed"),
                        Severity.ERROR,
                        "the first artifact failed",
                    ),
                )
            )
        return Ok("applied")


def _matched(planned: PlannedInstallation) -> CurrentState:
    desired = desired_state_for(planned)
    return CurrentState(
        planned.coordinate,
        tuple(
            ObservedComponent(component.id, ComponentState.MATCHED)
            for component in desired.components
        ),
    )


def _proposal():
    first = _planned()
    second_artifact = _resolved("jira", version="2.0.0")
    environment = ArtifactEnvironment("mcp/jira", "/owned/aart/mcp/jira")
    second = _planned(
        second_artifact,
        environment=environment,
        launcher=_launcher(f"{environment.root}/launch"),
        registrations=(),
        dependencies=(f"{environment.payload}/requirements.txt", "requirements", "pip"),
    )
    proposed = propose_installation(
        (first, second),
        _selection(first.artifact, second.artifact),
        facts=EnvironmentFacts("darwin", ()),
        policy=EffectivePolicy(),
        observed=(
            (COORDINATE, _nothing_installed(first)),
            (second.coordinate, _nothing_installed(second)),
        ),
    )
    assert isinstance(proposed, Ok), getattr(proposed, "diagnostics", ())
    return proposed.value, (first, second)


class InstallationTransactionTest(unittest.TestCase):
    def test_every_artifact_executes_under_one_scope_lease_and_one_review(self) -> None:
        proposal, planned = _proposal()
        before = {item.coordinate: _nothing_installed(item) for item in planned}
        after = {item.coordinate: _matched(item) for item in planned}
        calls = {item.coordinate: 0 for item in planned}

        def inspect(desired):
            coordinate = desired.artifact
            calls[coordinate] += 1
            # Preflight and the per-artifact compare-under-lock both see the reviewed state;
            # reinspection after effects sees convergence.
            return before[coordinate] if calls[coordinate] < 3 else after[coordinate]

        lock = _Lock()
        result = execute_installation(
            proposal,
            policy=EffectivePolicy(),
            interpreters=(_Interpreter(),),
            inspect=inspect,
            lock=lock,
        )

        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        self.assertIs(result.value.status, InstallationExecutionStatus.COMPLETED)
        self.assertEqual((lock.acquired, lock.released), (1, 1))
        self.assertEqual(
            [item.plan for item in result.value.artifacts],
            list(proposal.lifecycle),
        )
        self.assertTrue(
            all(
                item.outcome is not None
                and item.outcome.status is LifecycleExecutionStatus.COMPLETED
                for item in result.value.artifacts
            )
        )
        projected = installation_execution_to_data(result.value)
        self.assertEqual(projected["review_digest"], str(proposal.review_digest))
        self.assertEqual(len(projected["artifacts"]), 2)
        self.assertEqual(projected["selection"], install_plan_to_data(proposal.plan)["selection"])

    def test_every_precondition_is_checked_before_the_first_effect(self) -> None:
        proposal, planned = _proposal()
        interpreter = _Interpreter()
        stale = _matched(planned[1])

        result = execute_installation(
            proposal,
            policy=EffectivePolicy(),
            interpreters=(interpreter,),
            inspect=lambda desired: (
                stale
                if desired.artifact == planned[1].coordinate
                else _nothing_installed(planned[0])
            ),
            lock=_Lock(),
        )

        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, EXECUTION_REVIEW_STALE)
        self.assertEqual(interpreter.effects, [])

    def test_a_failure_stops_later_artifacts_but_keeps_each_final_state_explicit(self) -> None:
        proposal, planned = _proposal()
        before = {item.coordinate: _nothing_installed(item) for item in planned}
        calls = {item.coordinate: 0 for item in planned}

        def inspect(desired):
            calls[desired.artifact] += 1
            return before[desired.artifact]

        result = execute_installation(
            proposal,
            policy=EffectivePolicy(),
            interpreters=(_Interpreter(fail_first=True),),
            inspect=inspect,
            lock=_Lock(),
        )

        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        self.assertIs(result.value.status, InstallationExecutionStatus.FAILED)
        first, second = result.value.artifacts
        self.assertEqual(first.status, LifecycleExecutionStatus.FAILED.value)
        self.assertEqual(second.status, "not-attempted")
        self.assertIsNone(second.outcome)
        self.assertIn("earlier artifact", second.detail)
        self.assertEqual(calls[planned[1].coordinate], 1, "second artifact was preflight only")


if __name__ == "__main__":
    unittest.main()
