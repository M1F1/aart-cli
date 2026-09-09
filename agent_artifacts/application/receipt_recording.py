"""What a finished lifecycle action leaves behind in the store.

Recording is a decision rather than a consequence of succeeding, and the decisions are the ones a
later reconciliation depends on.

An action that took effect is recorded even when it did not finish: its leftovers are on the
machine either way, and a record is what makes them somebody's -- drift a repair can find rather
than files nothing knows about.  An action that took no effect leaves the store exactly as it was.
A rolled-back update leaves the record it already had standing, because the previous installation
is the one that is still true.  An uninstall that retained the artifact removed nothing, so it
narrows who owns the record rather than forgetting it.

The store is a port. This module decides; the adapter writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.receipts import (
    ArtifactReceipt,
    InstallationReceipt,
    PlacedArtifactReceipt,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import OwnershipReason

from .consumer_views import (
    ActivityRecord,
    ReceiptDetailView,
    project_installation_receipt,
    project_receipt_detail,
)
from .execution import (
    ExecutionStatus,
    InstallationExecutionOutcome,
    LifecycleExecutionOutcome,
    LifecycleExecutionStatus,
)
from .intents import LifecycleIntentKind

__all__ = [
    "RECORDING_INCOMPLETE",
    "ReceiptStorePort",
    "RecordedOutcome",
    "RecordedTransaction",
    "record_installation_transaction",
    "record_lifecycle_outcome",
]

RECORDING_INCOMPLETE = DiagnosticCode("recording-incomplete")

_ROLLED_BACK = (
    LifecycleExecutionStatus.RESTORED,
    LifecycleExecutionStatus.RESTORATION_FAILED,
)


class ReceiptStorePort(Protocol):
    """Somewhere a receipt outlives this process."""

    def record_installation(
        self,
        coordinate: ArtifactCoordinate,
        receipt: ArtifactReceipt,
        *,
        ownership: tuple[OwnershipReason, ...] | None = None,
    ) -> Result[str]: ...

    def forget_installation(self, coordinate: ArtifactCoordinate) -> Result[str]: ...

    def record_action(self, receipt: ReceiptDetailView) -> Result[str]: ...


@dataclass(frozen=True, slots=True)
class RecordedOutcome:
    """What the store now holds because of this action."""

    receipt: ReceiptDetailView
    action: str
    installation: str | None = None
    forgotten: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, ReceiptDetailView) or not isinstance(self.action, str):
            raise ValueError("a recorded outcome needs the receipt it recorded")
        if self.installation is not None and self.forgotten:
            raise ValueError("one action cannot both record and forget an installation")


def _error(message: str) -> Err:
    return Err((Diagnostic(RECORDING_INCOMPLETE, Severity.ERROR, message),))


def _keeps_installation(outcome: LifecycleExecutionOutcome) -> bool:
    if outcome.status in _ROLLED_BACK:
        return False
    return bool(outcome.primary.applied) or outcome.primary.status is ExecutionStatus.CONVERGED


def record_lifecycle_outcome(
    outcome: LifecycleExecutionOutcome,
    *,
    recorded_at: str,
    store: ReceiptStorePort,
    receipt: ArtifactReceipt | None = None,
) -> Result[RecordedOutcome]:
    """Record one finished action, and whatever it changed about what is installed.

    `recorded_at` is supplied rather than read: this layer has no clock, and a receipt that dated
    itself when somebody recorded it would be a record of the writing, not of the action.

    The action always reaches the timeline -- a failure is something that happened -- and reaches it
    first, so a store that then refuses the installation still leaves the attempt visible.
    """

    if not isinstance(outcome, LifecycleExecutionOutcome):
        return _error("recording needs a lifecycle execution outcome")
    coordinate = outcome.plan.repair.artifact
    intent = outcome.plan.intent
    # An uninstall that retained the artifact removed nothing: something else still owns it, so
    # the record stays and only who owns it narrows.
    releasing = intent.kind is LifecycleIntentKind.UNINSTALL and not intent.retained
    keeping = not releasing and _keeps_installation(outcome)
    installed = (
        receipt
        if keeping and isinstance(receipt, (InstallationReceipt, PlacedArtifactReceipt))
        else None
    )
    if keeping and installed is None:
        return _error(
            f"recording {coordinate} needs the installation receipt the action applied, "
            "because the action took effect"
        )
    try:
        detail = project_receipt_detail(ActivityRecord(recorded_at, outcome))
    except ValueError as error:
        return _error(str(error))
    action = store.record_action(detail)
    if isinstance(action, Err):
        return action

    if releasing and outcome.primary.status is ExecutionStatus.CONVERGED:
        forgotten = store.forget_installation(coordinate)
        if isinstance(forgotten, Err):
            return forgotten
        return Ok(RecordedOutcome(detail, action.value, forgotten=True))
    if installed is not None:
        # The intent is the authority on who wants this. An action with no opinion about
        # ownership says so, rather than recording the nothing it happens to carry.
        recorded = store.record_installation(
            coordinate,
            installed,
            ownership=intent.resulting_ownership if intent.establishes_ownership else None,
        )
        if isinstance(recorded, Err):
            return recorded
        return Ok(RecordedOutcome(detail, action.value, recorded.value))
    return Ok(RecordedOutcome(detail, action.value))


@dataclass(frozen=True, slots=True)
class RecordedTransaction:
    """What the store now holds because of one whole reviewed Selection."""

    receipt: ReceiptDetailView
    action: str
    installations: tuple[tuple[ArtifactCoordinate, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, ReceiptDetailView) or not isinstance(self.action, str):
            raise ValueError("a recorded transaction needs the receipt it recorded")
        if len({coordinate for coordinate, _ in self.installations}) != len(self.installations):
            raise ValueError("a transaction records each installation once")


def record_installation_transaction(
    outcome: InstallationExecutionOutcome,
    *,
    recorded_at: str,
    store: ReceiptStorePort,
    receipts: tuple[tuple[ArtifactCoordinate, ArtifactReceipt], ...] = (),
) -> Result[RecordedTransaction]:
    """Record one transaction as one action, and each member it left installed.

    The Selection is what somebody reviewed, so it is what reaches the timeline: one entry, naming
    every member. What is installed is still per-artifact, because that is the unit a later repair
    reconciles -- a member that applied is recorded even when a later member failed, since its
    leftovers are on the machine either way and a record is what makes them somebody's.
    """

    if not isinstance(outcome, InstallationExecutionOutcome):
        return _error("recording needs an installation execution outcome")
    available = dict(receipts)
    if len(available) != len(receipts):
        return _error("a transaction was given the same artifact's receipt twice")

    keeping: list[tuple[ArtifactCoordinate, ArtifactReceipt, LifecycleExecutionOutcome]] = []
    releasing: list[ArtifactCoordinate] = []
    for member in outcome.artifacts:
        if member.outcome is None:
            continue
        coordinate = member.plan.repair.artifact
        intent = member.plan.intent
        # The same rule one action follows, applied per member. A member that gave up the last
        # claim on an artifact and converged is forgotten; one that retained a claim removed
        # nothing and keeps its record; anything that took effect is recorded, because its
        # leftovers are on the machine either way.
        if intent.kind is LifecycleIntentKind.UNINSTALL and not intent.retained:
            if member.outcome.primary.status is ExecutionStatus.CONVERGED:
                releasing.append(coordinate)
            continue
        if not _keeps_installation(member.outcome):
            continue
        installed = available.get(coordinate)
        if installed is None:
            return _error(
                f"recording {coordinate} needs the installation receipt the action applied, "
                "because the action took effect"
            )
        keeping.append((coordinate, installed, member.outcome))

    try:
        detail = project_installation_receipt(outcome, recorded_at=recorded_at)
    except ValueError as error:
        return _error(str(error))
    # The action reaches the timeline first, so a store that then refuses an installation still
    # leaves the attempt visible rather than losing the whole transaction.
    action = store.record_action(detail)
    if isinstance(action, Err):
        return action

    recorded: list[tuple[ArtifactCoordinate, str]] = []
    for coordinate, installed, applied in keeping:
        intent = applied.plan.intent
        written = store.record_installation(
            coordinate,
            installed,
            ownership=intent.resulting_ownership if intent.establishes_ownership else None,
        )
        if isinstance(written, Err):
            return written
        recorded.append((coordinate, written.value))
        # A record is per version, and an artifact is installed at one version at a time. The
        # version an update left is therefore forgotten as part of recording the one that replaced
        # it -- keeping both would report one artifact as two installations, and a later repair
        # would try to converge a version that is no longer anywhere on the disk. This happens
        # after the new record is written, so a store that fails half-way leaves the artifact
        # recorded twice rather than not at all.
        superseded = intent.previous
        if superseded is not None and superseded.artifact != coordinate:
            forgotten = store.forget_installation(superseded.artifact)
            if isinstance(forgotten, Err):
                return forgotten
    for coordinate in releasing:
        dropped = store.forget_installation(coordinate)
        if isinstance(dropped, Err):
            return dropped
    return Ok(RecordedTransaction(detail, action.value, tuple(recorded)))
