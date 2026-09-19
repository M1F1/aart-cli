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

from aart_cli.application.consumer_views import (
    RUNNING,
    RunningInstallationView,
    project_running_installation,
)
from aart_cli.application.execution import (
    StepProgress,
    StepStatus,
    execute_installation,
    execute_lifecycle,
    execute_repair,
)
from aart_cli.application.intents import plan_lifecycle_intent, repair_intent
from aart_cli.domain.effects import ConfigureHarness, WriteFile
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.reconciliation import Component, ComponentId, ComponentState
from aart_cli.domain.result import Ok
from tests.execution_test import DESIRED, _Inspector, _Interpreter, observed, plan
from tests.installation_proposal_test import _nothing_installed
from tests.installation_transaction_test import _Interpreter as _TransactionInterpreter
from tests.installation_transaction_test import _Lock, _matched, _proposal
from tests.lifecycle_execution_test import V1, V2, current, desired
from tests.lifecycle_execution_test import _Lock as _LifecycleLock

# `differing_executors` is suppressed for the reason `doctor_properties_test` records: the scoped
# `make mutants` run re-runs the same test method object from a fresh runner per mutant.
MUTATION_SETTINGS = settings(suppress_health_check=(HealthCheck.differing_executors,))

_DIVERGENT = ("environment", "token", "launcher", "harness")


def _broken(*names: str):
    return observed(**{name: ComponentState.DIVERGENT for name in names})


class _Raising:
    """An interpreter that throws instead of returning, for the endings nothing hands back."""

    def __init__(self, error: BaseException, *, on: type) -> None:
        self._error = error
        self._on = on

    def supports(self, effect) -> bool:
        return True

    def apply(self, effect):
        if isinstance(effect, self._on):
            raise self._error
        return Ok("applied")


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

    def test_a_finished_step_is_numbered_and_named_exactly_as_its_start_was(self) -> None:
        """Found by scoped mutants: the outcome half of each announcement was barely held.

        A report that says a step is over has to be about the step that started, or a reader
        watching the list cannot tell which line to change. That is one claim for all three
        endings -- applied, failed, and never attempted.
        """

        current = _broken(*_DIVERGENT)
        steps = plan(current).steps
        reported = _run(current, interpreter=_Interpreter(fail=WriteFile))

        finished = [item for item in reported if item.status is not None]
        # A step nobody attempted is numbered too, and its number is its place in the plan.
        self.assertEqual([item.index for item in finished], list(range(1, len(steps) + 1)))
        for item in finished:
            step = steps[item.index - 1]
            self.assertEqual(item.component, step.component)
            self.assertEqual(item.effect, step.effect)

    def test_a_step_whose_interpreter_threw_is_still_named_where_it_stood(self) -> None:
        """The three endings a step can have that nothing returned: raised, interrupted, unhandled.

        Each is the ending a reader most needs placed, and each records its own outcome, so each is
        its own chance to lose the step's place in the plan.
        """

        current = _broken(*_DIVERGENT)
        steps = plan(current).steps
        third = steps[2]

        for interpreter in (
            _Raising(RuntimeError("it broke"), on=type(third.effect)),
            _Raising(KeyboardInterrupt(), on=type(third.effect)),
            _Interpreter(refuse=type(third.effect)),
        ):
            with self.subTest(interpreter=type(interpreter).__name__):
                reported = _run(current, interpreter=interpreter)

                (ended,) = [
                    item
                    for item in reported
                    if item.status is not None and item.status is not StepStatus.NOT_ATTEMPTED
                ][2:]
                self.assertEqual(ended.index, 3)
                self.assertEqual(ended.component, third.component)
                self.assertEqual(ended.effect, third.effect)

    def test_an_applied_step_reports_what_the_interpreter_said_about_it(self) -> None:
        reported = _run(_broken("launcher"))

        (finished,) = [item for item in reported if item.status is StepStatus.APPLIED]
        self.assertEqual(finished.detail, "applied")

    def test_every_member_of_a_transaction_says_which_artifact_it_is_about(self) -> None:
        """One Selection is several artifacts, and two of them have the same components.

        Without the artifact on each report, `launcher` twice is indistinguishable from `launcher`
        retried, so the reader cannot tell whose installation they are watching.
        """

        proposal, planned = _proposal()
        before = {item.coordinate: _nothing_installed(item) for item in planned}
        after = {item.coordinate: _matched(item) for item in planned}
        calls = {item.coordinate: 0 for item in planned}

        def inspect(desired):
            calls[desired.artifact] += 1
            return (
                before[desired.artifact] if calls[desired.artifact] < 3 else after[desired.artifact]
            )

        reported: list[StepProgress] = []
        outcome = execute_installation(
            proposal,
            policy=EffectivePolicy(),
            interpreters=(_TransactionInterpreter(),),
            inspect=inspect,
            lock=_Lock(),
            observe=reported.append,
        )

        self.assertIsInstance(outcome, Ok, getattr(outcome, "diagnostics", ()))
        self.assertTrue(reported)
        self.assertTrue(all(item.artifact is not None for item in reported))
        self.assertEqual(
            {item.artifact for item in reported}, {item.coordinate for item in planned}
        )

    def test_a_lifecycle_run_announces_its_steps_the_way_an_installation_does(self) -> None:
        wanted = desired(V1, "a")
        before = current(V1, ComponentState.DIVERGENT, ComponentState.MATCHED)
        reviewed = plan_lifecycle_intent(repair_intent(wanted), before, policy=EffectivePolicy())
        assert isinstance(reviewed, Ok), getattr(reviewed, "diagnostics", ())
        states = [before, current(V1, ComponentState.MATCHED, ComponentState.MATCHED)]
        reported: list[StepProgress] = []

        result = execute_lifecycle(
            reviewed.value,
            policy=EffectivePolicy(),
            interpreters=(_Interpreter(),),
            inspect=lambda _desired: states.pop(0),
            lock=_LifecycleLock(),
            observe=reported.append,
        )

        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        self.assertEqual([item.status for item in reported], [None, StepStatus.APPLIED])
        self.assertTrue(all(item.artifact == V1 for item in reported))

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


class RunningInstallationProjectionTest(unittest.TestCase):
    """`project_running_installation` is the only thing between the reports and the screen.

    The screen tests read drawn lines, which is the wrong place to state what the fold itself
    promises: one line per step at the latest thing said about it, counted, named and attributed.
    """

    def _reports(self, *, artifact=None):
        launcher = ComponentId(Component.LAUNCHER)
        write = WriteFile("/opt/agents/mcp/github/launch", "sha256:" + "a" * 64, True)
        harness = ComponentId(Component.HARNESS, "tabnine")
        configure = ConfigureHarness("tabnine", "mcp/github", ".tabnine/agent/settings.json")
        return (
            StepProgress(launcher, write, 1, 2, artifact=artifact),
            StepProgress(launcher, write, 1, 2, StepStatus.APPLIED, "written", artifact=artifact),
            StepProgress(harness, configure, 2, 2, artifact=artifact),
        )

    def test_a_step_said_twice_is_one_line_at_the_latest_thing_said_about_it(self) -> None:
        view = project_running_installation(self._reports())

        self.assertEqual([item.component for item in view.steps], ["launcher", "harness:tabnine"])
        self.assertEqual([item.status for item in view.steps], ["applied", RUNNING])
        self.assertEqual([item.detail for item in view.steps], ["written", ""])
        self.assertEqual([item.effect for item in view.steps], ["write-file", "configure-harness"])

    def test_the_count_is_the_steps_that_are_over_out_of_the_steps_there_are(self) -> None:
        view = project_running_installation(self._reports())

        self.assertEqual((view.done, view.total), (1, 2))
        self.assertFalse(view.finished)
        self.assertEqual(project_running_installation(()), RunningInstallationView("", (), 0, 0))

    def test_the_artifact_is_named_only_when_every_report_is_about_the_same_one(self) -> None:
        one = project_running_installation(self._reports(artifact=V1))
        self.assertEqual(one.artifact, str(V1))

        both = project_running_installation(self._reports(artifact=V1) + self._reports(artifact=V2))
        self.assertEqual(both.artifact, "")

    def test_only_progress_reports_can_be_projected(self) -> None:
        with self.assertRaises(ValueError):
            project_running_installation(("launcher is running",))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
