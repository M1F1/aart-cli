"""Turning a comparison into the smallest plan that puts one installation right.

Minimality is the whole point. The effects in a repair plan come only from components that actually
drifted, so a wrong token produces a credential repair and not a reinstall. Everything else about
the plan follows from that: steps stay in dependency order rather than the canonical order used for
review digests, because this plan is meant to be executed; and a component whose effects cannot be
re-run on their own is escalated by name rather than quietly rebuilt.

Policy is applied to what would actually run. A forbidden repair fails the plan instead of being
dropped from it -- a plan that silently omits the one thing that was wrong would converge on paper
and never converge on the machine.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import cast

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import Effect, RiskClass, effect_to_data
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ObjectDigest
from agent_artifacts.domain.policies import EffectivePolicy, effect_to_policy_key, policy_to_data
from agent_artifacts.domain.reconciliation import (
    ComponentId,
    CurrentState,
    DesiredState,
    Drift,
    compare_states,
    drift_to_data,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.serialization import CanonicalValue, canonical_json_bytes

RECONCILE_INVALID = DiagnosticCode("reconcile-invalid")
RECONCILE_POLICY_VIOLATION = DiagnosticCode("reconcile-policy-violation")

__all__ = [
    "RECONCILE_INVALID",
    "RECONCILE_POLICY_VIOLATION",
    "RepairPlan",
    "RepairStep",
    "plan_repair",
    "repair_converged",
    "repair_plan_to_data",
]


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _canonical(value: object) -> bytes:
    return canonical_json_bytes(cast(CanonicalValue, value))


@dataclass(frozen=True, slots=True)
class RepairStep:
    """One effect, and the component it exists to put right."""

    component: ComponentId
    effect: Effect

    def __post_init__(self) -> None:
        if not isinstance(self.component, ComponentId):
            raise ValueError("a repair step names the component it repairs")


@dataclass(frozen=True, slots=True)
class RepairPlan:
    """What has to happen, and what this engine cannot do on its own."""

    artifact: ArtifactCoordinate
    drift: tuple[Drift, ...]
    steps: tuple[RepairStep, ...]
    escalated: tuple[ComponentId, ...]
    policy_digest: ObjectDigest
    review_digest: ObjectDigest = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact, ArtifactCoordinate)
            or any(not isinstance(item, Drift) for item in self.drift)
            or any(not isinstance(item, RepairStep) for item in self.steps)
            or any(not isinstance(item, ComponentId) for item in self.escalated)
            or not isinstance(self.policy_digest, ObjectDigest)
        ):
            raise ValueError("repair plan is invalid")
        object.__setattr__(
            self, "escalated", tuple(sorted(set(self.escalated), key=lambda item: item.sort_key))
        )
        digest = hashlib.sha256(_canonical(repair_plan_to_data(self, review=False)))
        object.__setattr__(self, "review_digest", ObjectDigest("sha256", digest.hexdigest()))

    @property
    def risks(self) -> tuple[RiskClass, ...]:
        return tuple(sorted({step.effect.risk for step in self.steps}))

    @property
    def complete(self) -> bool:
        """Whether running these steps would leave nothing drifted.

        False when something drifted that this engine will not repair alone -- the caller has to
        decide on a wider action rather than run the steps and assume convergence.
        """

        return not self.escalated


def plan_repair(
    desired: DesiredState,
    current: CurrentState,
    *,
    policy: EffectivePolicy,
) -> Result[RepairPlan]:
    """The smallest policy-permitted plan that repairs `current` into `desired`.

    `policy` has no default, for the same reason it has none in credential planning: a permissive
    policy that appears because nobody passed one is a restriction that stopped applying without
    anybody deciding it should.
    """

    if not isinstance(policy, EffectivePolicy):
        return _error(RECONCILE_INVALID, "repair planning needs an effective policy")
    try:
        drift = compare_states(desired, current)
    except ValueError as error:
        return _error(RECONCILE_INVALID, str(error))

    by_id = {component.id: component for component in desired.components}
    steps: list[RepairStep] = []
    escalated: list[ComponentId] = []

    def execution_order(item: Drift) -> tuple[int, int, str]:
        component = by_id.get(item.component)
        ordinal, name = item.sort_key
        # Establish dependencies from the bottom up. Tear them down in the opposite direction:
        # unregister the harness before deleting the launcher it names, and delete the root last.
        if component is not None and component.target.value == "absent":
            return (1, -ordinal, name)
        return (0, ordinal, name)

    for item in sorted(drift, key=execution_order):
        component = by_id.get(item.component)
        if component is None or not item.repairable:
            escalated.append(item.component)
            continue
        for effect in component.effects_for(item.kind):
            if effect.risk > policy.risk_ceiling:
                return _error(
                    RECONCILE_POLICY_VIOLATION,
                    f"repairing {item.component} needs {effect_to_policy_key(effect)}, which "
                    "exceeds the effective policy risk ceiling",
                )
            if not policy.permits_effect(effect):
                return _error(
                    RECONCILE_POLICY_VIOLATION,
                    f"repairing {item.component} needs {effect_to_policy_key(effect)}, which the "
                    "effective policy forbids",
                )
            steps.append(RepairStep(item.component, effect))

    digest = hashlib.sha256(_canonical(policy_to_data(policy)))
    try:
        return Ok(
            RepairPlan(
                desired.artifact,
                drift,
                tuple(steps),
                tuple(escalated),
                ObjectDigest("sha256", digest.hexdigest()),
            )
        )
    except ValueError as error:
        return _error(RECONCILE_INVALID, f"repair plan is invalid: {error}")


def repair_converged(desired: DesiredState, current: CurrentState) -> bool:
    """Whether a re-inspection shows the installation is now what was wanted.

    Called after effects run, never instead of running them. It compares a fresh observation, so a
    repair that reported success and changed nothing is caught here.
    """

    return not compare_states(desired, current)


def repair_plan_to_data(plan: RepairPlan, *, review: bool = True) -> dict[str, object]:
    data: dict[str, object] = {
        "artifact": str(plan.artifact),
        "complete": plan.complete,
        "drift": [drift_to_data(item) for item in plan.drift],
        "escalated": [str(item) for item in plan.escalated],
        "policy_digest": str(plan.policy_digest),
        "risks": [risk.name.lower().replace("_", "-") for risk in plan.risks],
        "steps": [
            {"component": str(step.component), "effect": effect_to_data(step.effect)}
            for step in plan.steps
        ],
    }
    if review:
        data["review_digest"] = str(plan.review_digest)
    return data
