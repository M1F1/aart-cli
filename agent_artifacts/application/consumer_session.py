"""One machine, assembled once into everything the consumer application can say about it.

The screens are projections. This is what decides *what* they are projections of, and the decisions
here are the ones no single projection can make: which Collection an installed artifact belongs to,
which installations would stop working without a credential, and what the Dashboard is counting.

Assembly happens once before the shell starts and again after an action changes the machine, never
inside a draw. Drawing the same screen twice must not be able to produce two different answers, and
a screen that re-derived health while somebody scrolled would do exactly that.

Nothing here reaches the machine. Inspection is an argument: each installed record arrives paired
with the desired state it describes and the current state something else measured, which is why the
same assembly serves a real installation, a fixture and a test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agent_artifacts.domain.credentials import CredentialObservation, CredentialState
from agent_artifacts.domain.receipts import InstalledRecord
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState

from .consumer_views import (
    ActivityView,
    CredentialRecordView,
    DashboardView,
    DoctorView,
    InstalledArtifactView,
    InstalledCollectionView,
    ReceiptDetailView,
    RegistryView,
    activity_from_receipts,
    project_credential_record,
    project_dashboard,
    project_doctor,
    project_installed_artifact,
    project_installed_collection,
)
from .intents import InstalledHealth, MemberHealth

__all__ = [
    "ConsumerMachine",
    "InstalledInspection",
    "assemble_consumer_machine",
]

#: How many finished actions the Dashboard opens with. Enough to see what just happened; the
#: timeline is where somebody goes to see more.
_RECENT = 3


@dataclass(frozen=True, slots=True)
class InstalledInspection:
    """One installed artifact, as this machine currently answers for it."""

    record: InstalledRecord
    desired: DesiredState
    current: CurrentState
    update_available: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record, InstalledRecord)
            or not isinstance(self.desired, DesiredState)
            or not isinstance(self.current, CurrentState)
            or not isinstance(self.update_available, bool)
        ):
            raise ValueError("an installed inspection is invalid")

    @property
    def coordinate(self) -> str:
        return str(self.record.coordinate)


@dataclass(frozen=True, slots=True)
class ConsumerMachine:
    """What the consumer application can say about this machine right now."""

    dashboard: DashboardView
    installed: tuple[InstalledArtifactView, ...] = ()
    collections: tuple[InstalledCollectionView, ...] = ()
    credentials: tuple[CredentialRecordView, ...] = ()
    activity: ActivityView = ActivityView(())
    receipts: tuple[ReceiptDetailView, ...] = ()
    registries: tuple[RegistryView, ...] = ()
    doctor: DoctorView | None = None


def _dependants(
    observation: CredentialObservation, inspections: tuple[InstalledInspection, ...]
) -> tuple[str, ...]:
    """The installations that would stop working without this credential.

    A reference, not a provider account: two artifacts sharing an account but binding different
    inputs are not dependants of each other's credential.
    """

    reference = observation.reference
    return tuple(
        item.coordinate for item in inspections if reference in item.record.receipt.credentials
    )


def _collections(
    inspections: tuple[InstalledInspection, ...], views: tuple[InstalledArtifactView, ...]
) -> tuple[InstalledCollectionView, ...]:
    """Group the installed artifacts by the Collections that want them.

    Membership comes from recorded ownership rather than from the Collection's own manifest: what
    is installed here is what somebody's Selection actually resolved to, and a Collection that has
    since published a new member has not thereby installed it.
    """

    health = {view.coordinate: view.health for view in views}
    members: dict[str, list[MemberHealth]] = {}
    for item in inspections:
        for collection in item.record.collections:
            members.setdefault(collection, []).append(
                MemberHealth(item.coordinate, InstalledHealth(health[item.coordinate]))
            )
    return tuple(
        project_installed_collection(name, tuple(group)) for name, group in sorted(members.items())
    )


def assemble_consumer_machine(
    inspections: tuple[InstalledInspection, ...],
    *,
    credentials: tuple[CredentialObservation, ...] = (),
    actions: tuple[ReceiptDetailView, ...] = (),
    registries: tuple[RegistryView, ...] = (),
    today: date,
) -> ConsumerMachine:
    """Assemble everything the consumer screens draw from, from what was read of this machine.

    `today` is supplied rather than read for the same reason it is everywhere else in this layer:
    which day a record belongs to is a question about a calendar somebody is looking at, and this
    layer has no clock.
    """

    if any(not isinstance(item, InstalledInspection) for item in inspections) or any(
        not isinstance(item, CredentialObservation) for item in credentials
    ):
        raise ValueError("consumer assembly needs inspections and credential observations")
    if any(not isinstance(item, ReceiptDetailView) for item in actions) or any(
        not isinstance(item, RegistryView) for item in registries
    ):
        raise ValueError("consumer assembly needs recorded actions and registry views")

    records = tuple(
        project_credential_record(item, dependants=_dependants(item, inspections))
        for item in credentials
    )
    by_reference = {item.reference: item for item in records}
    views = tuple(
        project_installed_artifact(
            item.desired,
            item.current,
            ownership=item.record.ownership,
            update_available=item.update_available,
            credentials=tuple(
                by_reference[str(reference)]
                for reference in item.record.receipt.credentials
                if str(reference) in by_reference
            ),
        )
        for item in inspections
    )
    timeline = activity_from_receipts(actions, today=today)
    recent = tuple(entry.summary for day in timeline.days for entry in day.entries)[:_RECENT]
    attention = sum(
        item.health in (CredentialState.ABSENT.value, CredentialState.INVALID.value)
        for item in records
    )
    return ConsumerMachine(
        project_dashboard(
            views,
            registry_count=len(registries),
            credential_attention_count=attention,
            recent_activity=recent,
        ),
        views,
        _collections(inspections, views),
        records,
        timeline,
        actions,
        registries,
        project_doctor(views),
    )
