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
from agent_artifacts.domain.receipts import InstallationReceipt
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import OwnershipReason

from .consumer_views import ActivityRecord, ReceiptDetailView, project_receipt_detail
from .execution import ExecutionStatus, LifecycleExecutionOutcome, LifecycleExecutionStatus
from .intents import LifecycleIntentKind

__all__ = [
    "RECORDING_INCOMPLETE",
    "ReceiptStorePort",
    "RecordedOutcome",
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
        receipt: InstallationReceipt,
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
    receipt: InstallationReceipt | None = None,
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
    installed = receipt if keeping and isinstance(receipt, InstallationReceipt) else None
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
