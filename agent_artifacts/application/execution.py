"""Running a repair plan, and then finding out whether it worked.

The rule that shapes everything here is that convergence is measured, never inferred. Interpreters
report what they did; only a fresh inspection reports what is true. A repair whose every step
succeeded and whose re-inspection still shows drift is `UNCONVERGED` -- reported as a repair that
did not work, not as a success with a caveat.

Re-inspection therefore always runs. After a clean pass, after a failure part-way, after a step no
interpreter would take: the machine is in some state, and saying which one matters more than
recounting the plan. An inspection that cannot run at all is `UNVERIFIED`, which is again a
different answer from "fine".

Ordering is the plan's, and the plan's is dependency order. A failure stops the run, because a step
that comes later is there because it needed the one that just failed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Protocol

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import Effect, effect_to_data
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import (
    ComponentId,
    CurrentState,
    DesiredState,
    Drift,
    compare_states,
    drift_to_data,
)
from agent_artifacts.domain.result import Err, Ok, Result

from .intents import LifecycleIntentKind, LifecyclePlan, plan_lifecycle_intent
from .reconciliation import RepairPlan, plan_repair

EXECUTION_INCOMPLETE = DiagnosticCode("execution-incomplete")
EXECUTION_INVALID = DiagnosticCode("execution-invalid")
EXECUTION_REVIEW_STALE = DiagnosticCode("execution-review-stale")

__all__ = [
    "EXECUTION_INCOMPLETE",
    "EXECUTION_INVALID",
    "EXECUTION_REVIEW_STALE",
    "EffectInterpreter",
    "ExecutionOutcome",
    "ExecutionStatus",
    "LifecycleExecutionOutcome",
    "LifecycleExecutionStatus",
    "MutationLockPort",
    "StepOutcome",
    "StepStatus",
    "execute_repair",
    "execute_lifecycle",
    "execution_outcome_to_data",
    "lifecycle_execution_to_data",
]


class StepStatus(str, Enum):
    APPLIED = "applied"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    NOT_ATTEMPTED = "not-attempted"


class ExecutionStatus(str, Enum):
    """What a run amounts to, once the machine has been looked at again."""

    CONVERGED = "converged"
    UNCONVERGED = "unconverged"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    UNVERIFIED = "unverified"


class LifecycleExecutionStatus(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ATTENTION = "completed-with-attention"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    PARTIALLY_APPLIED = "partially-applied"
    RESTORED = "restored"
    RESTORATION_FAILED = "restoration-failed"


class EffectInterpreter(Protocol):
    """An adapter that can carry out some effects and says which."""

    def supports(self, effect: Effect) -> bool: ...

    def apply(self, effect: Effect) -> Result[str]: ...


class MutationLockPort(Protocol):
    """One already-scoped mutation lease; read-only inspection does not need it."""

    def acquire(self) -> Result[str]: ...

    def release(self, token: str) -> Result[None]: ...


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class StepOutcome:
    component: ComponentId
    effect: Effect
    status: StepStatus
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.component, ComponentId) or not isinstance(self.status, StepStatus):
            raise ValueError("step outcome is invalid")
        if not isinstance(self.detail, str):
            raise ValueError("step outcome detail is invalid")
        object.__setattr__(self, "detail", " ".join(self.detail.split()))


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """What happened, and what is still true afterwards."""

    plan_digest: ObjectDigest
    steps: tuple[StepOutcome, ...]
    converged: bool | None
    residual_drift: tuple[Drift, ...] = ()
    detail: str = ""
    observed: CurrentState | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.plan_digest, ObjectDigest)
            or any(not isinstance(item, StepOutcome) for item in self.steps)
            or any(not isinstance(item, Drift) for item in self.residual_drift)
            or not (self.converged is None or isinstance(self.converged, bool))
            or not (self.observed is None or isinstance(self.observed, CurrentState))
            or not isinstance(self.detail, str)
        ):
            raise ValueError("execution outcome is invalid")
        if self.converged and self.residual_drift:
            raise ValueError("an outcome cannot have converged and still name drift")
        object.__setattr__(self, "detail", " ".join(self.detail.split()))

    @property
    def status(self) -> ExecutionStatus:
        if any(step.status is StepStatus.INTERRUPTED for step in self.steps):
            return ExecutionStatus.INTERRUPTED
        if any(step.status is StepStatus.FAILED for step in self.steps):
            return ExecutionStatus.FAILED
        if self.converged is None:
            return ExecutionStatus.UNVERIFIED
        return ExecutionStatus.CONVERGED if self.converged else ExecutionStatus.UNCONVERGED

    @property
    def applied(self) -> tuple[StepOutcome, ...]:
        return tuple(step for step in self.steps if step.status is StepStatus.APPLIED)


@dataclass(frozen=True, slots=True)
class LifecycleExecutionOutcome:
    """The auditable terminal result of one reviewed, scope-locked lifecycle intent."""

    plan: LifecyclePlan
    primary: ExecutionOutcome
    restoration: ExecutionOutcome | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.plan, LifecyclePlan)
            or not isinstance(self.primary, ExecutionOutcome)
            or not (self.restoration is None or isinstance(self.restoration, ExecutionOutcome))
            or not isinstance(self.detail, str)
            or self.primary.plan_digest != self.plan.review_digest
        ):
            raise ValueError("lifecycle execution outcome is invalid")
        object.__setattr__(self, "detail", " ".join(self.detail.split()))

    @property
    def status(self) -> LifecycleExecutionStatus:
        if self.restoration is not None:
            return (
                LifecycleExecutionStatus.RESTORED
                if self.restoration.status is ExecutionStatus.CONVERGED
                else LifecycleExecutionStatus.RESTORATION_FAILED
            )
        if self.primary.status is ExecutionStatus.CONVERGED:
            return LifecycleExecutionStatus.COMPLETED
        if self.primary.status in (ExecutionStatus.UNCONVERGED, ExecutionStatus.UNVERIFIED):
            return LifecycleExecutionStatus.COMPLETED_WITH_ATTENTION
        if self.primary.status is ExecutionStatus.INTERRUPTED:
            return (
                LifecycleExecutionStatus.PARTIALLY_APPLIED
                if self.primary.applied
                else LifecycleExecutionStatus.INTERRUPTED
            )
        return (
            LifecycleExecutionStatus.PARTIALLY_APPLIED
            if self.primary.applied
            else LifecycleExecutionStatus.FAILED
        )


def _dispatch(
    effect: Effect, interpreters: tuple[EffectInterpreter, ...]
) -> EffectInterpreter | None:
    for interpreter in interpreters:
        if interpreter.supports(effect):
            return interpreter
    return None


def execute_repair(
    plan: RepairPlan,
    desired: DesiredState,
    interpreters: tuple[EffectInterpreter, ...],
    *,
    inspect: Callable[[], CurrentState],
    allow_incomplete: bool = False,
) -> Result[ExecutionOutcome]:
    """Run `plan`, then inspect again and report what is actually true.

    `allow_incomplete` defaults to False. A plan that escalated something cannot converge by
    definition, so running it is a decision somebody makes rather than one this function makes
    quietly on their behalf.
    """

    if not isinstance(plan, RepairPlan) or not isinstance(desired, DesiredState):
        return _error(EXECUTION_INVALID, "execution needs a repair plan and a desired state")
    if plan.artifact != desired.artifact:
        return _error(
            EXECUTION_INVALID,
            f"plan for {plan.artifact} cannot be executed against a desired state for "
            f"{desired.artifact}",
        )
    if not plan.complete and not allow_incomplete:
        names = ", ".join(str(item) for item in plan.escalated)
        return _error(
            EXECUTION_INCOMPLETE,
            f"this plan cannot converge on its own: {names} need a wider action",
        )

    steps: list[StepOutcome] = []
    stopped = False
    for step in plan.steps:
        if stopped:
            steps.append(StepOutcome(step.component, step.effect, StepStatus.NOT_ATTEMPTED))
            continue
        interpreter = _dispatch(step.effect, interpreters)
        if interpreter is None:
            steps.append(
                StepOutcome(
                    step.component,
                    step.effect,
                    StepStatus.FAILED,
                    f"no interpreter here carries out {type(step.effect).__name__}",
                )
            )
            stopped = True
            continue
        try:
            applied = interpreter.apply(step.effect)
        except KeyboardInterrupt:
            steps.append(
                StepOutcome(
                    step.component,
                    step.effect,
                    StepStatus.INTERRUPTED,
                    "execution was interrupted; current state will be inspected",
                )
            )
            stopped = True
            continue
        except (OSError, RuntimeError, ValueError) as error:
            steps.append(StepOutcome(step.component, step.effect, StepStatus.FAILED, str(error)))
            stopped = True
            continue
        if isinstance(applied, Err):
            detail = "; ".join(diagnostic.message for diagnostic in applied.diagnostics)
            steps.append(StepOutcome(step.component, step.effect, StepStatus.FAILED, detail))
            stopped = True
            continue
        steps.append(StepOutcome(step.component, step.effect, StepStatus.APPLIED, applied.value))

    try:
        current = inspect()
        drift = compare_states(desired, current)
        converged: bool | None = not drift
        detail = ""
    except (OSError, RuntimeError, ValueError) as error:
        current = None
        drift = ()
        converged = None
        detail = f"re-inspection could not run: {error}"

    return Ok(
        ExecutionOutcome(
            plan.review_digest,
            tuple(steps),
            converged,
            drift,
            detail,
            current,
        )
    )


def execution_outcome_to_data(outcome: ExecutionOutcome) -> dict[str, object]:
    return {
        "converged": outcome.converged,
        "detail": outcome.detail,
        "plan_digest": str(outcome.plan_digest),
        "residual_drift": [drift_to_data(item) for item in outcome.residual_drift],
        "status": outcome.status.value,
        "steps": [
            {
                "component": str(step.component),
                "detail": step.detail,
                "effect": effect_to_data(step.effect),
                "status": step.status.value,
            }
            for step in outcome.steps
        ],
    }


def _execute_lifecycle_locked(
    reviewed: LifecyclePlan,
    *,
    policy: EffectivePolicy,
    interpreters: tuple[EffectInterpreter, ...],
    inspect: Callable[[DesiredState], CurrentState],
) -> Result[LifecycleExecutionOutcome]:
    try:
        current = inspect(reviewed.intent.desired)
    except (OSError, RuntimeError, ValueError) as error:
        return _error(EXECUTION_INVALID, f"lifecycle precondition inspection failed: {error}")
    fresh = plan_lifecycle_intent(reviewed.intent, current, policy=policy)
    if isinstance(fresh, Err):
        return fresh
    if fresh.value.review_digest != reviewed.review_digest:
        return _error(
            EXECUTION_REVIEW_STALE,
            "installed state changed after Review; inspect and review a fresh plan",
        )

    primary = execute_repair(
        reviewed.repair,
        reviewed.intent.desired,
        interpreters,
        inspect=lambda: inspect(reviewed.intent.desired),
    )
    if isinstance(primary, Err):
        return primary

    restoration: ExecutionOutcome | None = None
    detail = ""
    should_restore = (
        reviewed.intent.kind is LifecycleIntentKind.UPDATE
        and reviewed.intent.previous is not None
        and primary.value.status is not ExecutionStatus.CONVERGED
        and bool(primary.value.applied)
        and all(step.effect.capabilities.reversible for step in primary.value.applied)
    )
    if should_restore:
        assert reviewed.intent.previous is not None
        previous = reviewed.intent.previous
        try:
            previous_current = inspect(previous)
        except (OSError, RuntimeError, ValueError) as error:
            detail = f"previous state could not be inspected for restoration: {error}"
        else:
            restoration_plan = plan_repair(previous, previous_current, policy=policy)
            if isinstance(restoration_plan, Err):
                detail = "; ".join(item.message for item in restoration_plan.diagnostics)
            else:
                restored = execute_repair(
                    restoration_plan.value,
                    previous,
                    interpreters,
                    inspect=lambda: inspect(previous),
                )
                if isinstance(restored, Err):
                    detail = "; ".join(item.message for item in restored.diagnostics)
                else:
                    restoration = restored.value

    return Ok(LifecycleExecutionOutcome(reviewed, primary.value, restoration, detail))


def execute_lifecycle(
    reviewed: LifecyclePlan,
    *,
    policy: EffectivePolicy,
    interpreters: tuple[EffectInterpreter, ...],
    inspect: Callable[[DesiredState], CurrentState],
    lock: MutationLockPort,
) -> Result[LifecycleExecutionOutcome]:
    """Execute one reviewed intent under its scope lease.

    The current state is inspected again inside the lease and must produce the same review digest.
    This is the compare-under-lock boundary that keeps a second process from applying a plan whose
    precondition it invalidated. Every later resume repeats this function and therefore reconciles
    from fresh state rather than continuing at an imperative instruction number.
    """

    if not isinstance(reviewed, LifecyclePlan):
        return _error(EXECUTION_INVALID, "lifecycle execution needs a reviewed lifecycle plan")
    acquired = lock.acquire()
    if isinstance(acquired, Err):
        return acquired
    try:
        result = _execute_lifecycle_locked(
            reviewed,
            policy=policy,
            interpreters=interpreters,
            inspect=inspect,
        )
    finally:
        released = lock.release(acquired.value)
    if isinstance(released, Err):
        warning = "; ".join(item.message for item in released.diagnostics)
        if isinstance(result, Err):
            return Err((*result.diagnostics, *released.diagnostics))
        return Ok(
            replace(result.value, detail="; ".join(filter(None, (result.value.detail, warning))))
        )
    return result


def lifecycle_execution_to_data(outcome: LifecycleExecutionOutcome) -> dict[str, object]:
    return {
        "detail": outcome.detail,
        "intent": outcome.plan.intent.kind.value,
        "ownership_retained": [
            {"kind": item.kind.value, "owner": item.owner}
            for item in outcome.plan.intent.retained_ownership
        ],
        "primary": execution_outcome_to_data(outcome.primary),
        "restoration": (
            None if outcome.restoration is None else execution_outcome_to_data(outcome.restoration)
        ),
        "status": outcome.status.value,
    }
