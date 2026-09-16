"""`QA-082`: while a reviewed plan runs, say which step is running and which are done.

Requested in issue #7 against the released `v0.1.1`: the Ready screen lists what will happen, and
then the installation runs silently until it is over. The execution loop is the only place that
knows where it has got to, so it is the place that says so -- to a callback it is given, never to a
terminal it reaches for. What is announced is the plan's own steps, in the order they run, so the
progress report and the review cannot disagree.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_artifacts.application.execution import StepProgress, StepStatus, execute_repair
from agent_artifacts.domain.effects import ConfigureHarness, WriteFile
from agent_artifacts.domain.reconciliation import ComponentState
from agent_artifacts.domain.result import Ok
from tests.execution_test import DESIRED, _Inspector, _Interpreter, observed, plan

# `differing_executors` is suppressed for the reason `doctor_properties_test` records: the scoped
# `make mutants` run re-runs the same test method object from a fresh runner per mutant.
MUTATION_SETTINGS = settings(suppress_health_check=(HealthCheck.differing_executors,))

_DIVERGENT = ("environment", "token", "launcher", "harness")


def _broken(*names: str):
    return observed(**{name: ComponentState.DIVERGENT for name in names})


def _run(current, *, interpreter=None) -> list[StepProgress]:
    reported: list[StepProgress] = []
    outcome = execute_repair(
        plan(current),
        DESIRED,
        (interpreter or _Interpreter(),),
        inspect=_Inspector(observed()),
        observe=reported.append,
    )
    assert isinstance(outcome, Ok), getattr(outcome, "diagnostics", ())
    return reported


class InstallationProgressTest(unittest.TestCase):
    def test_each_step_is_announced_when_it_starts_and_again_when_it_is_done(self) -> None:
        reported = _run(_broken("launcher"))

        self.assertEqual([item.status for item in reported], [None, StepStatus.APPLIED])
        self.assertEqual([item.index for item in reported], [1, 1])
        self.assertEqual([item.total for item in reported], [1, 1])
        self.assertTrue(all(isinstance(item.effect, WriteFile) for item in reported))

    def test_a_plan_with_nothing_to_do_announces_nothing(self) -> None:
        self.assertEqual(_run(observed()), [])

    def test_the_step_that_failed_is_the_one_named_and_the_rest_are_not_attempted(self) -> None:
        reported = _run(_broken(*_DIVERGENT), interpreter=_Interpreter(fail=WriteFile))

        finished = [item for item in reported if item.status is not None]
        failed = [item for item in finished if item.status is StepStatus.FAILED]
        self.assertEqual(len(failed), 1)
        self.assertIsInstance(failed[0].effect, WriteFile)
        self.assertTrue(
            all(
                item.status is StepStatus.NOT_ATTEMPTED
                for item in finished[finished.index(failed[0]) + 1 :]
            )
        )
        # A step nobody attempted never claimed to start.
        started = [item for item in reported if item.status is None]
        self.assertEqual(len(started), finished.index(failed[0]) + 1)

    def test_an_announcement_says_which_effect_and_which_component_it_is(self) -> None:
        reported = _run(_broken("harness"))

        self.assertTrue(all(str(item.component) == "harness:tabnine" for item in reported))
        self.assertTrue(all(isinstance(item.effect, ConfigureHarness) for item in reported))

    @MUTATION_SETTINGS
    @given(st.lists(st.sampled_from(_DIVERGENT), min_size=1, max_size=4, unique=True))
    def test_what_is_announced_is_the_reviewed_plan_in_the_order_it_runs(
        self, divergent: list[str]
    ) -> None:
        current = _broken(*divergent)
        steps = plan(current).steps

        reported = _run(current)

        self.assertEqual(
            [(item.component, item.effect) for item in reported if item.status is None],
            [(step.component, step.effect) for step in steps],
        )
        self.assertEqual([item.total for item in reported], [len(steps)] * len(reported))
        self.assertEqual(
            [item.index for item in reported if item.status is None],
            list(range(1, len(steps) + 1)),
        )


if __name__ == "__main__":
    unittest.main()
