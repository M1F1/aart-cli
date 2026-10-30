"""The telemetry events one finished action amounts to (§213).

An install, update, downgrade or uninstall reports each artifact it changed and completed; a
repair, a failure and a member never attempted report nothing, because nothing about what is
installed changed for the organisation to count.
"""

from __future__ import annotations

from collections.abc import Callable

from aart_cli.domain.telemetry import TelemetryEvent, contract_moment, lifecycle_event

from .consumer_views import ActivityOutcome, ReceiptDetailView

__all__ = ["lifecycle_events"]

_COMPLETED_MEMBER = frozenset({"completed", "completed-with-attention"})
_COMPLETED_ACTION = frozenset({ActivityOutcome.SUCCEEDED, ActivityOutcome.ATTENTION})


def lifecycle_events(
    receipt: ReceiptDetailView, new_id: Callable[[], str]
) -> tuple[TelemetryEvent, ...]:
    """Each artifact `receipt` changed and completed, as one event; `new_id` draws event ids."""

    if not isinstance(receipt, ReceiptDetailView):
        raise ValueError("telemetry events come from a finished action's receipt")
    moment = contract_moment(receipt.moment)
    if receipt.artifacts:
        changed = tuple(
            item.coordinate for item in receipt.artifacts if item.status in _COMPLETED_MEMBER
        )
    else:
        changed = (receipt.artifact,) if receipt.outcome in _COMPLETED_ACTION else ()
    events = (lifecycle_event(new_id(), moment, receipt.intent, item) for item in changed)
    return tuple(event for event in events if event is not None)
