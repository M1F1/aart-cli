"""Taking recorded installations back out, as one reviewed transaction.

Uninstall is planned from what is recorded, never from what a registry offers. That is not a
simplification -- it is the requirement. An installed artifact is on the disk whether or not the
subscription that delivered it is still configured, so an uninstall that had to resolve a
coordinate first would refuse exactly when somebody most needs it: after the source is gone.

What is removed therefore comes from the receipt, and how much is removed comes from ownership.
`uninstall_intent` already decides that: an artifact something else still wants is not removed, it
is narrowed, and the intent says so by keeping the previous state as the one to converge on. This
module does the rest -- one absent desired state per member, one plan against what is actually
there, and one review digest over all of them, so a person confirms the whole removal rather than
each step of it.

Nothing here reads a secret value. Credentials are retained by default: the last dependant
disappearing is not authority to delete somebody's token, so deleting one is a separate mutation a
caller asks for explicitly.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import Effect, RiskClass
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ObjectDigest
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.receipts import (
    InstallationReceipt,
    InstalledRecord,
    PlacedArtifactReceipt,
)
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import OwnershipReason
from agent_artifacts.domain.serialization import CanonicalValue, canonical_json_bytes

from .installed_state import (
    desired_state_from_placement,
    desired_state_from_receipt,
    removal_state_from_placement,
    removal_state_from_receipt,
)
from .intents import LifecyclePlan, plan_lifecycle_intent, uninstall_intent

__all__ = [
    "REMOVAL_INVALID",
    "PlannedRemoval",
    "RemovalProposal",
    "plan_removal",
    "propose_removal",
]

#: A removal was asked for that this machine cannot describe from what it recorded.
REMOVAL_INVALID = DiagnosticCode("removal-proposal-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(REMOVAL_INVALID, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class PlannedRemoval:
    """One recorded installation and the absent state taking it out converges on.

    Both states are derived from the same receipt, so what is removed is exactly what was
    installed. `release` is which of the reasons this artifact is installed for are being given
    up -- everything it has, for somebody uninstalling it directly; one Collection's claim, for a
    Collection being removed around it.
    """

    record: InstalledRecord
    previous: DesiredState
    removal: DesiredState
    release: tuple[OwnershipReason, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record, InstalledRecord)
            or not isinstance(self.previous, DesiredState)
            or not isinstance(self.removal, DesiredState)
        ):
            raise ValueError("a planned removal is invalid")
        if self.previous.artifact != self.record.coordinate:
            raise ValueError("a planned removal describes a different artifact than it records")
        if any(not isinstance(item, OwnershipReason) for item in self.release):
            raise ValueError("released ownership is invalid")

    @property
    def coordinate(self) -> ArtifactCoordinate:
        return self.record.coordinate


def plan_removal(
    record: InstalledRecord,
    *,
    release: tuple[OwnershipReason, ...] = (),
    delete_credentials: bool = False,
) -> Result[PlannedRemoval]:
    """Derive what removing one recorded installation would converge on.

    `delete_credentials` reaches only the launched shape, because a placed artifact has none. It
    defaults to False everywhere: a credential outliving its last dependant is the documented
    behaviour, not an oversight to be corrected by whoever calls this.
    """

    if not isinstance(record, InstalledRecord):
        return _error("planning a removal needs a recorded installation")
    receipt = record.receipt
    try:
        if isinstance(receipt, PlacedArtifactReceipt):
            previous = desired_state_from_placement(record.coordinate, receipt)
            removal = removal_state_from_placement(record.coordinate, receipt)
        elif isinstance(receipt, InstallationReceipt):
            previous = desired_state_from_receipt(
                record.coordinate, receipt, base_interpreter=receipt.base_interpreter
            )
            removal = removal_state_from_receipt(
                record.coordinate, receipt, delete_credentials=delete_credentials
            )
        else:
            return _error(f"{record.coordinate} is recorded as something this build cannot remove")
        return Ok(PlannedRemoval(record, previous, removal, release))
    except ValueError as error:
        return _error(f"{record.coordinate} cannot be removed: {error}")


@dataclass(frozen=True, slots=True)
class RemovalProposal:
    """One reviewed removal transaction: every member's plan, under one digest.

    The digest covers the members rather than each member covering itself, because what somebody
    confirms is the removal -- taking out three of four artifacts because the fourth's plan changed
    is not what they agreed to. `converged` is how a removal of something already gone reports
    itself: nothing to do is an answer, not a failure.
    """

    lifecycle: tuple[LifecyclePlan, ...]
    policy_digest: ObjectDigest
    review_digest: ObjectDigest = field(init=False)

    def __post_init__(self) -> None:
        if not self.lifecycle or any(
            not isinstance(item, LifecyclePlan) for item in self.lifecycle
        ):
            raise ValueError("a removal proposal plans at least one recorded installation")
        if not isinstance(self.policy_digest, ObjectDigest):
            raise ValueError("a removal proposal is invalid")
        ordered = tuple(sorted(self.lifecycle, key=lambda item: str(item.intent.desired.artifact)))
        if len({item.repair.artifact for item in ordered}) != len(ordered):
            raise ValueError("a removal proposal plans the same artifact twice")
        object.__setattr__(self, "lifecycle", ordered)
        data: CanonicalValue = {
            "members": [
                {
                    "artifact": str(item.repair.artifact),
                    "intent": item.intent.kind.value,
                    "review_digest": str(item.repair.review_digest),
                }
                for item in ordered
            ],
            "policy_digest": str(self.policy_digest),
        }
        digest = hashlib.sha256(canonical_json_bytes(data))
        object.__setattr__(self, "review_digest", ObjectDigest("sha256", digest.hexdigest()))

    @property
    def effects(self) -> tuple[Effect, ...]:
        return tuple(step.effect for item in self.lifecycle for step in item.repair.steps)

    @property
    def risks(self) -> tuple[RiskClass, ...]:
        return tuple(sorted({effect.risk for effect in self.effects}))

    @property
    def converged(self) -> bool:
        """Whether this removal would change nothing, because there is nothing left to remove."""

        return not self.effects

    def plan_for(self, coordinate: ArtifactCoordinate) -> LifecyclePlan | None:
        for item in self.lifecycle:
            if item.repair.artifact == coordinate:
                return item
        return None


def propose_removal(
    removals: tuple[PlannedRemoval, ...],
    *,
    observed: tuple[tuple[ArtifactCoordinate, CurrentState], ...],
    policy: EffectivePolicy,
) -> Result[RemovalProposal]:
    """Lower recorded installations into the removal a person reviews and the plans that run it.

    `observed` is required for every member for the same reason an install requires it: an artifact
    somebody already deleted by hand and one nobody looked at are different facts, and planning a
    removal against an assumption would report a machine cleaned that nobody measured.
    """

    if not removals or any(not isinstance(item, PlannedRemoval) for item in removals):
        return _error("proposing a removal needs at least one planned removal")
    if not isinstance(policy, EffectivePolicy):
        return _error("proposing a removal needs an effective policy")
    states = dict(observed)
    if len(states) != len(observed):
        return _error("an artifact was observed twice")
    missing = tuple(str(item.coordinate) for item in removals if item.coordinate not in states)
    if missing:
        return _error(
            "nothing was observed for " + ", ".join(sorted(missing)) + "; a removal is planned "
            "against what is there, not against an assumption that it still is"
        )

    lifecycle: list[LifecyclePlan] = []
    for removal in removals:
        try:
            intent = uninstall_intent(
                removal.previous,
                removal.removal,
                ownership=removal.record.ownership,
                release=removal.release,
            )
        except ValueError as error:
            return _error(f"{removal.coordinate} cannot be uninstalled: {error}")
        planned = plan_lifecycle_intent(intent, states[removal.coordinate], policy=policy)
        if isinstance(planned, Err):
            return planned
        lifecycle.append(planned.value)
    try:
        return Ok(RemovalProposal(tuple(lifecycle), lifecycle[0].repair.policy_digest))
    except ValueError as error:
        return _error(f"removal proposal is invalid: {error}")
