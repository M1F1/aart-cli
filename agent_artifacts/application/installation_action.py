"""One install action, preserving the reviewed identity from offer through durable recording.

The public command and the persistent shell are two adapters over one application operation.  This
module is that operation: preparation composes the offer and the proposal a person reviews, while
completion verifies that exact review, executes the whole Selection under one lease, and records
the transaction plus each installed member.

Resolution, placement, effect interpreters, inspection, locking, persistence and the clock stay at
explicit boundaries.  In particular this module never reads a secret value and never chooses an
interactive remediation: callers pass the subset somebody accepted.  ``None`` is reserved for a
non-interactive caller that explicitly accepts the whole offer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState
from agent_artifacts.domain.remediations import Remediation
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ResolvedSelection

from .consumer_session import ConsumerFlow, begin_installation, record_installation
from .execution import (
    EffectInterpreter,
    InstallationExecutionOutcome,
    MutationLockPort,
    execute_installation,
)
from .installation_offer import ArtifactPlacement, InstallationOffer, offer_installation
from .installation_planning import EnvironmentInspectionPort
from .installation_proposal import PlannedInstallation, intended_receipt
from .receipt_recording import (
    ReceiptStorePort,
    RecordedTransaction,
    record_installation_transaction,
)
from .runtime_projection import CredentialResolutionPort

__all__ = [
    "ACTION_INVALID",
    "ACTION_REVIEW_MISMATCH",
    "CompletedInstallationAction",
    "PreparedInstallationAction",
    "complete_installation_action",
    "prepare_installation_action",
]

ACTION_INVALID = DiagnosticCode("installation-action-invalid")
ACTION_REVIEW_MISMATCH = DiagnosticCode("installation-action-review-mismatch")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class PreparedInstallationAction:
    """The one immutable offer and flow an install confirmation is allowed to execute."""

    selection: ResolvedSelection
    offer: InstallationOffer
    flow: ConsumerFlow

    def __post_init__(self) -> None:
        if (
            not isinstance(self.selection, ResolvedSelection)
            or not isinstance(self.offer, InstallationOffer)
            or not isinstance(self.flow, ConsumerFlow)
            or self.flow.proposal.plan.selection != self.selection
            or self.flow.artifacts != tuple(item.coordinate for item in self.offer.installations)
        ):
            raise ValueError("a prepared installation action is inconsistent")

    @property
    def installations(self) -> tuple[PlannedInstallation, ...]:
        return self.offer.installations

    @property
    def review_digest(self) -> ObjectDigest:
        return self.flow.proposal.review_digest


@dataclass(frozen=True, slots=True)
class CompletedInstallationAction:
    """What ran, what was durably recorded, and the flow the result screen draws."""

    prepared: PreparedInstallationAction
    execution: InstallationExecutionOutcome
    recorded: RecordedTransaction
    flow: ConsumerFlow

    def __post_init__(self) -> None:
        if not isinstance(self.prepared, PreparedInstallationAction):
            raise ValueError("a completed installation action is inconsistent")
        digest = self.prepared.review_digest
        if (
            not isinstance(self.execution, InstallationExecutionOutcome)
            or not isinstance(self.recorded, RecordedTransaction)
            or not isinstance(self.flow, ConsumerFlow)
            or self.execution.proposal.review_digest != digest
            or self.flow.proposal.review_digest != digest
            or self.flow.outcome != self.recorded.receipt
            or self.recorded.receipt.review_digest != str(digest)
        ):
            raise ValueError("a completed installation action is inconsistent")


def prepare_installation_action(
    selection: ResolvedSelection,
    placements: tuple[ArtifactPlacement, ...],
    *,
    policy: EffectivePolicy,
    facts: EnvironmentFacts,
    inspect: EnvironmentInspectionPort,
    observe: Callable[[PlannedInstallation], CurrentState],
    selected_remediations: tuple[Remediation, ...] | None,
    base_interpreter: str | None = None,
    resolvers: tuple[CredentialResolutionPort, ...] = (),
) -> Result[PreparedInstallationAction]:
    """Offer and begin one action without mutating the machine.

    ``selected_remediations`` is explicit for an interactive caller.  ``None`` means the caller is
    non-interactive and has already authorized the whole offer (the command's ``--yes`` path); an
    empty tuple means somebody selected no remediation.
    """

    if not isinstance(selection, ResolvedSelection):
        return _error(ACTION_INVALID, "preparing an installation action needs a resolved Selection")
    offered = offer_installation(
        placements,
        policy=policy,
        facts=facts,
        inspect=inspect,
        observe=observe,
        base_interpreter=base_interpreter,
        resolvers=resolvers,
    )
    if isinstance(offered, Err):
        return offered
    chosen = offered.value.selected() if selected_remediations is None else selected_remediations
    begun = begin_installation(
        offered.value.installations,
        selection,
        offered.value.facts,
        policy,
        observed=offered.value.observed,
        selected_remediations=chosen,
    )
    if isinstance(begun, Err):
        return begun
    try:
        return Ok(PreparedInstallationAction(selection, offered.value, begun.value))
    except ValueError as error:
        return _error(ACTION_INVALID, f"this installation action cannot be prepared: {error}")


def complete_installation_action(
    prepared: PreparedInstallationAction,
    *,
    expected_review_digest: ObjectDigest,
    policy: EffectivePolicy,
    interpreters: tuple[EffectInterpreter, ...],
    inspect: Callable[[DesiredState], CurrentState],
    lock: MutationLockPort,
    store: ReceiptStorePort,
    recorded_at: str,
) -> Result[CompletedInstallationAction]:
    """Execute and record only the exact prepared review the caller confirmed."""

    if not isinstance(prepared, PreparedInstallationAction) or not isinstance(
        expected_review_digest, ObjectDigest
    ):
        return _error(ACTION_INVALID, "completing an installation needs a prepared action")
    if expected_review_digest != prepared.review_digest:
        return _error(
            ACTION_REVIEW_MISMATCH,
            f"the confirmed review {expected_review_digest} is not the prepared review "
            f"{prepared.review_digest}",
        )
    executed = execute_installation(
        prepared.flow.proposal,
        policy=policy,
        interpreters=interpreters,
        inspect=inspect,
        lock=lock,
    )
    if isinstance(executed, Err):
        return executed
    presented = record_installation(prepared.flow, executed.value, recorded_at=recorded_at)
    if isinstance(presented, Err):
        return presented
    persisted = record_installation_transaction(
        executed.value,
        recorded_at=recorded_at,
        store=store,
        receipts=tuple(
            (installation.coordinate, intended_receipt(installation))
            for installation in prepared.installations
        ),
    )
    if isinstance(persisted, Err):
        return persisted
    try:
        return Ok(
            CompletedInstallationAction(
                prepared,
                executed.value,
                persisted.value,
                presented.value,
            )
        )
    except ValueError as error:
        return _error(ACTION_INVALID, f"this installation action cannot be completed: {error}")
