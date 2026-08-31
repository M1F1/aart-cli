"""One lowering behind the plan somebody reviews and the effects that actually run.

An install has to be described twice. A person confirms a review -- the Selection, the requirements,
the remediations, the risks and the mutations of §161.5 screens 05 to 09. A reconciler drives a
desired state -- the components of CP-11 that a later repair keeps true. Written separately those
two descriptions are free to disagree, and somebody then confirms one thing while another runs.

So they are not written separately. A :class:`PlannedInstallation` says what an installation is;
:func:`desired_state_for` lowers it into the state to converge on, and the effects the reconciler
selects against a real inspection are the effects the review names. An :class:`InstallationProposal`
refuses to exist when they differ, which makes "what you confirmed is what runs" a property of the
type rather than a discipline somebody has to remember.

Nothing here inspects, mutates or reads a secret value. Bound inputs reach this module as
references and rendered launcher content stays out of the plan: a review is written to disk,
printed and drawn in a terminal, so what it may carry about a launcher is the digest naming it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypeAlias

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import Effect
from agent_artifacts.domain.harness import McpRegistration
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ObjectDigest
from agent_artifacts.domain.inputs import BoundInputs, ConfigInput, RuntimeInput, SecretInput
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.launch import LaunchContract
from agent_artifacts.domain.plans import InstallPlan
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import (
    ArtifactDelivery,
    ArtifactMerge,
    ArtifactReceipt,
    InstallationReceipt,
    PlacedArtifactReceipt,
)
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState
from agent_artifacts.domain.remediations import Remediation
from agent_artifacts.domain.requirements import Requirement
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import (
    ResolvedArtifact,
    ResolvedSelection,
    artifact_coordinate_sort_key,
)

from .installation_planning import ArtifactInstallIntent, prepare_install_plan
from .installed_state import desired_state_from_placement, desired_state_from_receipt
from .intents import (
    LifecycleIntent,
    LifecyclePlan,
    install_intent,
    plan_lifecycle_intent,
    supersession_intent,
)
from .runtime_projection import RuntimeProjection

__all__ = [
    "PROPOSAL_INVALID",
    "InstallationProposal",
    "PlannedArtifact",
    "PlannedInstallation",
    "PlannedPlacement",
    "artifact_desired_state",
    "artifact_receipt_for",
    "desired_state_for",
    "install_lifecycle_intent",
    "intended_placement_receipt",
    "intended_receipt",
    "placement_desired_state",
    "placement_lifecycle_intent",
    "propose_installation",
]

PROPOSAL_INVALID = DiagnosticCode("installation-proposal-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(PROPOSAL_INVALID, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class PlannedInstallation:
    """Everything decided about one artifact's installation before anything is touched.

    The optional fields are the plan knowledge a receipt does not hold. Leaving one out leaves the
    component out rather than inventing it, which is what lets the same value describe a Skill with
    no runtime and an MCP server with an owned interpreter.
    """

    artifact: ResolvedArtifact
    environment: ArtifactEnvironment
    contract: LaunchContract
    launcher: RuntimeProjection
    bound: BoundInputs = BoundInputs()
    registrations: tuple[McpRegistration, ...] = ()
    payload_source: str | None = None
    base_interpreter: str | None = None
    dependencies: tuple[str, str, str] | None = None
    requirements: tuple[Requirement, ...] = ()
    runtime: str | None = None
    declared: tuple[RuntimeInput, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact, ResolvedArtifact)
            or not isinstance(self.environment, ArtifactEnvironment)
            or not isinstance(self.contract, LaunchContract)
            or not isinstance(self.launcher, RuntimeProjection)
            or not isinstance(self.bound, BoundInputs)
        ):
            raise ValueError("a planned installation is invalid")
        if not self.launcher.path.startswith(f"{self.environment.root}/"):
            raise ValueError("a planned launcher belongs to the artifact root it is generated for")
        if any(not isinstance(item, McpRegistration) for item in self.registrations):
            raise ValueError("planned harness registrations are invalid")
        for registration in self.registrations:
            # A harness entry that names anything else would start something this plan never
            # reviewed, and no later inspection of the launcher would notice.
            if registration.command != self.launcher.command:
                raise ValueError(
                    f"harness {registration.target.harness} would start "
                    "something other than the planned launcher"
                )
        for value, label in (
            (self.payload_source, "payload source"),
            (self.base_interpreter, "base interpreter"),
            (self.runtime, "runtime"),
        ):
            if value is not None and (
                not isinstance(value, str)
                or not value.strip()
                or any(character in value for character in "\r\n")
            ):
                raise ValueError(f"a planned installation {label} must be one non-empty line")
        if self.dependencies is not None:
            if (
                not isinstance(self.dependencies, tuple)
                or len(self.dependencies) != 3
                or any(not isinstance(item, str) or not item.strip() for item in self.dependencies)
            ):
                raise ValueError("planned dependencies are a descriptor, a kind and an installer")
            if self.base_interpreter is None:
                raise ValueError(
                    "dependencies need the base interpreter the environment holding them is "
                    "built from"
                )
        if any(not isinstance(item, Requirement) for item in self.requirements):
            raise ValueError("planned requirements are invalid")
        if any(not isinstance(item, (SecretInput, ConfigInput)) for item in self.declared):
            raise ValueError("planned declared inputs are invalid")
        if self.declared:
            # A value bound to an input the artifact never declared would be delivered to the
            # process without appearing on the screen that asked for it.
            declared = {item.id for item in self.declared}
            undeclared = sorted(
                str(item.input.id) for item in self.bound.inputs if item.input.id not in declared
            )
            if undeclared:
                raise ValueError(
                    "an installation binds inputs this artifact does not declare: "
                    + ", ".join(undeclared)
                )
        object.__setattr__(
            self,
            "registrations",
            tuple(sorted(self.registrations, key=lambda item: (item.target.harness, item.server))),
        )

    @property
    def coordinate(self) -> ArtifactCoordinate:
        return self.artifact.version.coordinate

    @property
    def transport(self) -> str:
        return self.contract.transport.value


def intended_receipt(planned: PlannedInstallation) -> InstallationReceipt:
    """The receipt this installation means to leave behind.

    Written before the install rather than after it, so the state to converge on and the state a
    later repair reads back are built by one function from one description.
    """

    if not isinstance(planned, PlannedInstallation):
        raise ValueError("an intended receipt needs a planned installation")
    return InstallationReceipt(
        planned.environment.artifact,
        planned.environment.root,
        planned.launcher.path,
        planned.launcher.digest,
        planned.environment.interpreter,
        planned.contract.transport,
        planned.registrations,
        planned.bound.credential_references,
        base_interpreter=planned.base_interpreter,
    )


def desired_state_for(planned: PlannedInstallation) -> DesiredState:
    """The component-level state this installation converges on."""

    return desired_state_from_receipt(
        planned.coordinate,
        intended_receipt(planned),
        base_interpreter=planned.base_interpreter,
        dependencies=planned.dependencies,
        payload_source=planned.payload_source,
    )


def install_lifecycle_intent(planned: PlannedInstallation) -> LifecycleIntent:
    """The install intent, carrying who asked for the artifact through to the record."""

    return install_intent(desired_state_for(planned), ownership=planned.artifact.ownership)


@dataclass(frozen=True, slots=True)
class PlannedPlacement:
    """Everything decided about placing one artifact a harness reads, before anything is touched.

    The counterpart of `PlannedInstallation` for the four kinds that start no process. There is no
    contract, no launcher and no environment to build, and those are absent rather than optional:
    INV-010 keeps semantic kind separate from runtime protocol, and a placement carrying an empty
    launcher would converge on a component nobody installed.
    """

    artifact: ResolvedArtifact
    environment: ArtifactEnvironment
    payload_digest: ObjectDigest
    deliveries: tuple[ArtifactDelivery, ...] = ()
    payload_source: str | None = None
    requirements: tuple[Requirement, ...] = ()
    #: The regions of files this machine's user owns that this artifact writes into. A memory
    #: artifact has these and no deliveries; a Skill has deliveries and none of these.
    merges: tuple[ArtifactMerge, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact, ResolvedArtifact)
            or not isinstance(self.environment, ArtifactEnvironment)
            or not isinstance(self.payload_digest, ObjectDigest)
        ):
            raise ValueError("a planned placement is invalid")
        if any(not isinstance(item, ArtifactDelivery) for item in self.deliveries) or any(
            not isinstance(item, ArtifactMerge) for item in self.merges
        ):
            raise ValueError("planned placement deliveries or merges are invalid")
        if not self.deliveries and not self.merges:
            # Placed in its own tree and read by nobody is a download, not an installation.
            raise ValueError("a planned placement is read by at least one harness")
        if self.payload_source is not None and (
            not isinstance(self.payload_source, str)
            or not self.payload_source.strip()
            or any(character in self.payload_source for character in "\r\n")
        ):
            raise ValueError("a planned placement payload source must be one non-empty line")
        if any(not isinstance(item, Requirement) for item in self.requirements):
            raise ValueError("planned placement requirements are invalid")
        if not self.environment.root.startswith("/"):
            # The harness resolves nothing on this artifact's behalf: a relative root would be
            # read against whatever working directory the run that repaired it happened to have.
            raise ValueError("a planned placement root must be one absolute path")
        prefix = self.environment.root.rstrip("/") + "/"
        placed: tuple[ArtifactDelivery | ArtifactMerge, ...] = (*self.deliveries, *self.merges)
        for item in placed:
            if item.source != self.environment.root and not item.source.startswith(prefix):
                # A delivery is made from the artifact that owns it, so a repair copies from what
                # this installation placed rather than from somewhere nobody chose.
                raise ValueError(
                    f"a delivery to {item.harness} comes from outside {self.environment.artifact}"
                )
        for items, label in ((self.deliveries, "delivery"), (self.merges, "merge")):
            harnesses = [item.harness for item in items]
            if len(set(harnesses)) != len(harnesses):
                raise ValueError(f"one harness reads one {label} of an artifact")
        object.__setattr__(
            self, "deliveries", tuple(sorted(self.deliveries, key=lambda item: item.harness))
        )
        object.__setattr__(
            self, "merges", tuple(sorted(self.merges, key=lambda item: item.harness))
        )

    @property
    def coordinate(self) -> ArtifactCoordinate:
        return self.artifact.version.coordinate


#: One artifact's plan, whichever shape of installation it is. The two are separate types because
#: they converge on different components -- one has a launcher and the other has deliveries -- and
#: everything that treats them alike does so through what they share: a coordinate, requirements
#: and a lifecycle intent.
PlannedArtifact: TypeAlias = PlannedInstallation | PlannedPlacement


def intended_placement_receipt(planned: PlannedPlacement) -> PlacedArtifactReceipt:
    """The receipt this placement means to leave behind.

    Written before the delivery for the same reason `intended_receipt` is: the state to converge on
    and the state a later repair reads back are built by one function from one description.
    """

    if not isinstance(planned, PlannedPlacement):
        raise ValueError("an intended placement receipt needs a planned placement")
    return PlacedArtifactReceipt(
        planned.environment.artifact,
        planned.environment.root,
        planned.payload_digest,
        planned.deliveries,
        merges=planned.merges,
    )


def placement_desired_state(planned: PlannedPlacement) -> DesiredState:
    """The component-level state this placement converges on."""

    return desired_state_from_placement(
        planned.coordinate,
        intended_placement_receipt(planned),
        payload_source=planned.payload_source,
    )


def placement_lifecycle_intent(planned: PlannedPlacement) -> LifecycleIntent:
    """The install intent, carrying who asked for the artifact through to the record."""

    return install_intent(placement_desired_state(planned), ownership=planned.artifact.ownership)


def _unversioned(coordinate: ArtifactCoordinate) -> ArtifactCoordinate:
    """The artifact a coordinate names, without the version it happens to be at.

    Supersession is keyed by this. An update names the artifact, not the version -- the version
    being left is what the previous state records, and the version being taken is what resolution
    chose, so a key carrying either of them could only agree with one side.
    """

    return replace(coordinate, version=None)


def artifact_receipt_for(planned: PlannedArtifact) -> ArtifactReceipt:
    """What either shape of plan would leave behind, without the caller deciding which it is.

    The two receipts are different types because they record different things -- one a launcher and
    a transport, the other the paths harnesses read -- and this is the single place that branch is
    written down. A caller that made the choice for itself would be a second place for the two to
    fall out of step.
    """

    if isinstance(planned, PlannedPlacement):
        return intended_placement_receipt(planned)
    return intended_receipt(planned)


def artifact_desired_state(planned: PlannedArtifact) -> DesiredState:
    """The component-level state either shape of plan converges on."""

    if isinstance(planned, PlannedPlacement):
        return placement_desired_state(planned)
    return desired_state_for(planned)


@dataclass(frozen=True, slots=True)
class InstallationProposal:
    """One reviewed plan and the lifecycle plans that carry it out.

    The constructor is the guarantee: an effect that would run and is not in the reviewed plan
    makes the proposal invalid, so no execution path can be handed a plan somebody did not confirm.
    """

    plan: InstallPlan
    lifecycle: tuple[LifecyclePlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, InstallPlan) or any(
            not isinstance(item, LifecyclePlan) for item in self.lifecycle
        ):
            raise ValueError("an installation proposal is invalid")
        ordered = tuple(
            sorted(
                self.lifecycle,
                key=lambda item: artifact_coordinate_sort_key(item.intent.desired.artifact),
            )
        )
        if len({item.intent.desired.artifact for item in ordered}) != len(ordered):
            raise ValueError("an installation proposal plans the same artifact twice")
        reviewed = {item.effect for item in self.plan.mutation.effects}
        running = {step.effect for item in ordered for step in item.repair.steps}
        unreviewed = running - reviewed
        if unreviewed:
            names = ", ".join(sorted(type(effect).__name__ for effect in unreviewed))
            raise ValueError(f"the reviewed plan does not name what would run: {names}")
        object.__setattr__(self, "lifecycle", ordered)

    @property
    def review_digest(self) -> ObjectDigest:
        return self.plan.review_digest

    @property
    def effects(self) -> tuple[Effect, ...]:
        """Every effect that will run, in the order the reconciler chose to run it."""

        return tuple(step.effect for item in self.lifecycle for step in item.repair.steps)

    @property
    def converged(self) -> bool:
        """Whether this proposal would change nothing, because everything is already true."""

        return not self.effects

    def plan_for(self, coordinate: ArtifactCoordinate) -> LifecyclePlan | None:
        for item in self.lifecycle:
            if item.intent.desired.artifact == coordinate:
                return item
        return None


def propose_installation(
    installations: tuple[PlannedArtifact, ...],
    selection: ResolvedSelection,
    facts: EnvironmentFacts,
    policy: EffectivePolicy,
    *,
    observed: tuple[tuple[ArtifactCoordinate, CurrentState], ...] = (),
    previous: tuple[tuple[ArtifactCoordinate, DesiredState], ...] = (),
    selected_remediations: tuple[Remediation, ...] = (),
) -> Result[InstallationProposal]:
    """Lower a resolved Selection into the plan a person reviews and the plans that run it.

    `observed` is required for every artifact rather than defaulted, because "nobody looked" and
    "it is not there" call for different installs and a default would quietly pick one. Passing a
    state observed on a machine where nothing is installed is how a first install says so.

    `previous` names, for an artifact that already has one, the state the installed version
    converged on. It makes that artifact's plan a transition rather than a first install, which is
    what lets a review state what is being left as well as what is being taken. It is passed
    rather than inferred from `observed`, because an observation is what is on the disk and a
    transition is between two things somebody intended -- a drifted installation is still an update
    from the version it records, not from the damage. Which transition it is follows from the two
    versions (`supersession_intent`), including the refusal to call a move backwards an update.
    """

    if any(not isinstance(item, (PlannedInstallation, PlannedPlacement)) for item in installations):
        return _error("proposing an installation needs planned installations")
    if not isinstance(selection, ResolvedSelection) or not isinstance(policy, EffectivePolicy):
        return _error("proposing an installation needs a resolved selection and a policy")
    states = dict(observed)
    if len(states) != len(observed):
        return _error("an artifact was observed twice")
    superseded = dict(previous)
    if len(superseded) != len(previous):
        return _error("an artifact was superseded twice")
    if any(coordinate.version is not None for coordinate in superseded):
        return _error(
            "a superseded artifact is named without a version; the version being left is the one "
            "its previous state records"
        )
    planned_coordinates = {_unversioned(item.coordinate) for item in installations}
    unplanned = tuple(
        str(coordinate) for coordinate in superseded if coordinate not in planned_coordinates
    )
    if unplanned:
        return _error(
            "a previous version was named for "
            + ", ".join(sorted(unplanned))
            + ", which is not being installed"
        )
    missing = tuple(str(item.coordinate) for item in installations if item.coordinate not in states)
    if missing:
        return _error(
            "nothing was observed for " + ", ".join(sorted(missing)) + "; an installation is "
            "planned against what is there, not against an assumption that nothing is"
        )

    lifecycle: list[LifecyclePlan] = []
    intents: list[ArtifactInstallIntent] = []
    for planned in installations:
        # A placement names no runtime and no transport. Leaving both absent is the fact rather
        # than a default: nothing starts, so there is no interpreter it runs under and no channel
        # a harness would speak to it over.
        if isinstance(planned, PlannedPlacement):
            runtime, transport = None, None
        else:
            runtime, transport = planned.runtime, planned.transport
        replaced = superseded.get(_unversioned(planned.coordinate))
        try:
            if replaced is not None:
                intent = supersession_intent(
                    replaced,
                    artifact_desired_state(planned),
                    ownership=planned.artifact.ownership,
                )
            elif isinstance(planned, PlannedPlacement):
                intent = placement_lifecycle_intent(planned)
            else:
                intent = install_lifecycle_intent(planned)
        except ValueError as error:
            return _error(f"{planned.coordinate} cannot be installed: {error}")
        reconciled = plan_lifecycle_intent(intent, states[planned.coordinate], policy=policy)
        if isinstance(reconciled, Err):
            return reconciled
        lifecycle.append(reconciled.value)
        try:
            intents.append(
                ArtifactInstallIntent(
                    planned.artifact,
                    planned.requirements,
                    tuple(step.effect for step in reconciled.value.repair.steps),
                    runtime=runtime,
                    transport=transport,
                )
            )
        except ValueError as error:
            return _error(f"{planned.coordinate} cannot be reviewed: {error}")

    prepared = prepare_install_plan(
        selection,
        tuple(intents),
        facts,
        policy,
        selected_remediations=selected_remediations,
    )
    if isinstance(prepared, Err):
        return prepared
    try:
        return Ok(InstallationProposal(prepared.value, tuple(lifecycle)))
    except ValueError as error:
        return _error(f"installation proposal is invalid: {error}")
