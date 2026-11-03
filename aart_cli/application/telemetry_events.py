"""The telemetry events one finished action amounts to (§213).

An install, update, downgrade or uninstall reports each artifact it changed and completed, and
each skill a plugin among them carries (§214); a repair, a failure and a member never attempted
report nothing, because nothing about what is installed changed for the organisation to count.
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
    """Each artifact `receipt` changed and completed, as one event, followed by one for each skill
    it carries when it is a plugin; `new_id` draws event ids."""

    if not isinstance(receipt, ReceiptDetailView):
        raise ValueError("telemetry events come from a finished action's receipt")
    moment = contract_moment(receipt.moment)
    changed: tuple[tuple[str, tuple[str, ...], str | None, str | None], ...]
    if receipt.artifacts:
        changed = tuple(
            (item.coordinate, item.members, item.harness, item.scope)
            for item in receipt.artifacts
            if item.status in _COMPLETED_MEMBER
        )
    else:
        changed = (
            ((receipt.artifact, (), None, None),) if receipt.outcome in _COMPLETED_ACTION else ()
        )
    events = (
        lifecycle_event(
            new_id(),
            moment,
            receipt.intent,
            coordinate,
            member=member,
            harness=harness,
            scope=scope,
        )
        for coordinate, members, harness, scope in changed
        for member in (None, *members)
    )
    return tuple(event for event in events if event is not None)
