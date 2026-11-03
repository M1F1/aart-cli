"""The telemetry events one finished action amounts to (§213).

An install, update, downgrade or uninstall reports each artifact it changed and completed, and
each skill a plugin among them carries (§214); a repair, a failure and a member never attempted
report nothing, because nothing about what is installed changed for the organisation to count.

Each event says where and how it happened, as far as the receipt knows it (D-518, D-519): the
harness and scope, the TUI or the command line, how long the action took, the version an update
replaced, the package, how many inputs it asked for, and whether it came directly or with a
Collection. What an event type does not hold is left to the domain to drop.
"""

from __future__ import annotations

from collections.abc import Callable

from aart_cli.domain.telemetry import TelemetryEvent, contract_moment, lifecycle_event

from .consumer_views import ActivityOutcome, ReceiptArtifactView, ReceiptDetailView, SelectionView

__all__ = ["lifecycle_events"]

_COMPLETED_MEMBER = frozenset({"completed", "completed-with-attention"})
_COMPLETED_ACTION = frozenset({ActivityOutcome.SUCCEEDED, ActivityOutcome.ATTENTION})


def _came(item: ReceiptArtifactView, selection: SelectionView | None) -> dict[str, object]:
    """How `item` came to be in this action: with a Collection the Selection named, directly, or
    neither when it is only somebody's dependency or no Selection was reviewed.

    The Collection is the one the Selection asked for, not any Collection that also owns it, so
    an artifact a person picked by hand is never counted as a Collection's.
    """

    if selection is None:
        return {}
    for owner in item.ownership:
        if owner.kind == "collection" and owner.owner in selection.collections:
            body, _, version = owner.owner.partition("@")
            return {
                "via": "collection",
                "collection": body.rpartition("/")[2],
                "collection_version": version or None,
            }
    if any(owner.kind == "direct" for owner in item.ownership):
        return {"via": "direct"}
    return {}


def _said(item: ReceiptArtifactView, receipt: ReceiptDetailView) -> dict[str, object]:
    """Where and how `item` was installed, updated or removed, by the context's field names."""

    return {
        "harness": item.harness,
        "scope": item.scope,
        "interface": receipt.interface,
        "duration_ms": receipt.duration_ms,
        "previous_version": item.previous_version,
        "package_digest": item.package_digest,
        "configuration_inputs": item.configuration_inputs,
        "credential_inputs": item.credential_inputs,
        **_came(item, receipt.selection),
    }


def lifecycle_events(
    receipt: ReceiptDetailView, new_id: Callable[[], str]
) -> tuple[TelemetryEvent, ...]:
    """Each artifact `receipt` changed and completed, as one event, followed by one for each skill
    it carries when it is a plugin; `new_id` draws event ids."""

    if not isinstance(receipt, ReceiptDetailView):
        raise ValueError("telemetry events come from a finished action's receipt")
    moment = contract_moment(receipt.moment)
    changed: tuple[tuple[str, tuple[str, ...], dict[str, object]], ...]
    if receipt.artifacts:
        changed = tuple(
            (item.coordinate, item.members, _said(item, receipt))
            for item in receipt.artifacts
            if item.status in _COMPLETED_MEMBER
        )
    elif receipt.outcome in _COMPLETED_ACTION:
        how: dict[str, object] = {
            "interface": receipt.interface,
            "duration_ms": receipt.duration_ms,
        }
        changed = ((receipt.artifact, (), how),)
    else:
        changed = ()
    events = (
        lifecycle_event(new_id(), moment, receipt.intent, coordinate, member=member, **said)
        for coordinate, members, said in changed
        for member in (None, *members)
    )
    return tuple(event for event in events if event is not None)
