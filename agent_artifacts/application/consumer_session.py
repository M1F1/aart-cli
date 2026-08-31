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

A flow is the other half. The machine is what is true; a flow is what somebody started and has not
finished, and screens 05 to 11 draw it rather than the machine. It is built once from a proposal
and rebuilt after an action, for the same reason assembly is: a review re-derived while somebody
scrolled would not be the review they confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from agent_artifacts.domain.credentials import CredentialObservation, CredentialState
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactCoordinate, InputId
from agent_artifacts.domain.inputs import BoundInput, BoundInputs, RuntimeInput
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.receipts import InstalledRecord
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState
from agent_artifacts.domain.remediations import Remediation
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ResolvedSelection

from .consumer_views import (
    ActivityView,
    ConsumerPlanView,
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
    project_install_plan,
    project_installation_receipt,
    project_installed_artifact,
    project_installed_collection,
    project_unadopted_installation,
)
from .execution import InstallationExecutionOutcome
from .installation_proposal import (
    InstallationProposal,
    PlannedInstallation,
    propose_installation,
)
from .intents import InstalledHealth, MemberHealth

__all__ = [
    "FLOW_INVALID",
    "ConsumerFlow",
    "ConsumerMachine",
    "InstalledInspection",
    "UnadoptedInstallation",
    "assemble_consumer_machine",
    "begin_installation",
    "record_installation",
]

FLOW_INVALID = DiagnosticCode("consumer-flow-invalid")

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
class UnadoptedInstallation:
    """One installation recorded in the project or user manifest and nowhere canonical.

    This is the strangler boundary, and it is deliberately thin: a coordinate and the scope it was
    installed into, which is everything the canonical model can honestly carry about a record it
    does not yet own. Nothing here is a receipt, a desired state or an observation, and it must not
    grow into one by inference -- the moment this can be projected from a kind-neutral canonical
    receipt instead, the record stops being unadopted and this type stops being needed.
    """

    coordinate: str
    scope: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coordinate, str)
            or not self.coordinate
            or any(character in self.coordinate for character in "\r\n")
            or self.scope not in {"project", "user"}
        ):
            raise ValueError("an unadopted installation is invalid")


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
        item.coordinate for item in inspections if reference in item.record.credential_references
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
    unadopted: tuple[UnadoptedInstallation, ...] = (),
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
    if any(not isinstance(item, UnadoptedInstallation) for item in unadopted):
        raise ValueError("consumer assembly needs unadopted installations")
    inspected = {item.coordinate for item in inspections}
    if len({item.coordinate for item in unadopted} & inspected):
        raise ValueError(
            "an installation cannot be both canonically receipted and unadopted; the caller "
            "decides which record answers for it before assembly, not the screens"
        )

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
                for reference in item.record.credential_references
                if str(reference) in by_reference
            ),
        )
        for item in inspections
    )
    # Drawn in the same list, because two lists would let the canonical one answer "not installed"
    # about something that is. Ordered after the measured ones and marked unknown, so nothing reads
    # an unmeasured installation as a healthy one.
    views += tuple(
        project_unadopted_installation(item.coordinate)
        for item in sorted(unadopted, key=lambda item: (item.coordinate, item.scope))
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


@dataclass(frozen=True, slots=True)
class ConsumerFlow:
    """One action somebody started, and everything the screens for it are drawn from.

    The proposal is the authority; the plan is its projection. They are held together rather than
    separately because the guarantee `InstallationProposal` makes -- that what was reviewed is what
    runs -- is only worth anything if the review a person read was projected from that proposal and
    not from some other plan built alongside it.
    """

    proposal: InstallationProposal
    plan: ConsumerPlanView
    outcome: ReceiptDetailView | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, InstallationProposal) or not isinstance(
            self.plan, ConsumerPlanView
        ):
            raise ValueError("a consumer flow needs a proposal and the review projected from it")
        if self.plan.review_digest != str(self.proposal.review_digest):
            raise ValueError("a consumer flow would show a review of a different plan")
        if self.outcome is not None and not isinstance(self.outcome, ReceiptDetailView):
            raise ValueError("a consumer flow outcome is invalid")

    @property
    def converged(self) -> bool:
        """Whether this flow would change nothing, because everything is already true."""

        return self.proposal.converged

    @property
    def artifacts(self) -> tuple[ArtifactCoordinate, ...]:
        return tuple(item.intent.desired.artifact for item in self.proposal.lifecycle)


def _flow_error(message: str) -> Err:
    return Err((Diagnostic(FLOW_INVALID, Severity.ERROR, message),))


def _declared(installations: tuple[PlannedInstallation, ...]) -> tuple[RuntimeInput, ...]:
    """The distinct inputs this selection declares, in the order they were declared.

    An input two artifacts both want is asked for once. They agree on what it is because the values
    for a selection are bound from one set of sources, so the first declaration is the declaration
    rather than a choice between rivals.
    """

    seen: dict[InputId, RuntimeInput] = {}
    for planned in installations:
        for item in planned.declared:
            seen.setdefault(item.id, item)
    return tuple(seen.values())


def _bound(installations: tuple[PlannedInstallation, ...]) -> BoundInputs:
    seen: dict[InputId, BoundInput] = {}
    for planned in installations:
        for item in planned.bound.inputs:
            seen.setdefault(item.input.id, item)
    return BoundInputs(tuple(seen.values()))


def begin_installation(
    installations: tuple[PlannedInstallation, ...],
    selection: ResolvedSelection,
    facts: EnvironmentFacts,
    policy: EffectivePolicy,
    *,
    observed: tuple[tuple[ArtifactCoordinate, CurrentState], ...] = (),
    selected_remediations: tuple[Remediation, ...] = (),
    credential_observations: tuple[CredentialObservation, ...] = (),
) -> Result[ConsumerFlow]:
    """Begin the flow screens 05 to 09 draw, from what this machine would install.

    Everything an install needs was already decided by the time this is called. What it adds is the
    one thing a screen cannot do for itself: hold the proposal and its projection together so the
    next screen and the one after it are looking at the same install.
    """

    proposed = propose_installation(
        installations,
        selection,
        facts,
        policy,
        observed=observed,
        selected_remediations=selected_remediations,
    )
    if isinstance(proposed, Err):
        return proposed
    try:
        plan = project_install_plan(
            proposed.value.plan,
            inputs=_declared(installations),
            bound_inputs=_bound(installations),
            credential_observations=credential_observations,
        )
        return Ok(ConsumerFlow(proposed.value, plan))
    except ValueError as error:
        return _flow_error(f"this installation cannot be reviewed: {error}")


def record_installation(
    flow: ConsumerFlow,
    outcome: InstallationExecutionOutcome,
    *,
    recorded_at: str,
) -> Result[ConsumerFlow]:
    """Carry what ran back onto the flow that reviewed it, for screens 10 and 11.

    A flow is always about one proposal, so what it records is always one transaction -- an install
    of a single artifact is a transaction with one member rather than a second kind of result
    (D-064). The outcome has to be of this flow's own proposal. Anything else would let one action's
    result be drawn under another's review, which is how somebody reads "installed" about an
    install that never happened.

    `recorded_at` is supplied rather than read: this layer has no clock, and a receipt that dated
    itself when somebody drew it would be a record of the drawing, not of the action.
    """

    if not isinstance(flow, ConsumerFlow) or not isinstance(outcome, InstallationExecutionOutcome):
        return _flow_error("recording an installation needs a flow and what running it produced")
    if outcome.proposal.review_digest != flow.proposal.review_digest:
        return _flow_error(
            "this outcome is from a proposal this flow never made; a result is only ever "
            "reported under the review it belongs to"
        )
    try:
        return Ok(
            replace(flow, outcome=project_installation_receipt(outcome, recorded_at=recorded_at))
        )
    except ValueError as error:
        return _flow_error(f"this outcome cannot be reported: {error}")
