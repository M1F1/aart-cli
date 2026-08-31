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

from dataclasses import dataclass

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
from agent_artifacts.domain.receipts import InstallationReceipt
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
from .installed_state import desired_state_from_receipt
from .intents import LifecycleIntent, LifecyclePlan, install_intent, plan_lifecycle_intent
from .runtime_projection import RuntimeProjection

__all__ = [
    "PROPOSAL_INVALID",
    "InstallationProposal",
    "PlannedInstallation",
    "desired_state_for",
    "install_lifecycle_intent",
    "intended_receipt",
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
    installations: tuple[PlannedInstallation, ...],
    selection: ResolvedSelection,
    facts: EnvironmentFacts,
    policy: EffectivePolicy,
    *,
    observed: tuple[tuple[ArtifactCoordinate, CurrentState], ...] = (),
    selected_remediations: tuple[Remediation, ...] = (),
) -> Result[InstallationProposal]:
    """Lower a resolved Selection into the plan a person reviews and the plans that run it.

    `observed` is required for every artifact rather than defaulted, because "nobody looked" and
    "it is not there" call for different installs and a default would quietly pick one. Passing a
    state observed on a machine where nothing is installed is how a first install says so.
    """

    if any(not isinstance(item, PlannedInstallation) for item in installations):
        return _error("proposing an installation needs planned installations")
    if not isinstance(selection, ResolvedSelection) or not isinstance(policy, EffectivePolicy):
        return _error("proposing an installation needs a resolved selection and a policy")
    states = dict(observed)
    if len(states) != len(observed):
        return _error("an artifact was observed twice")
    missing = tuple(str(item.coordinate) for item in installations if item.coordinate not in states)
    if missing:
        return _error(
            "nothing was observed for " + ", ".join(sorted(missing)) + "; an installation is "
            "planned against what is there, not against an assumption that nothing is"
        )

    lifecycle: list[LifecyclePlan] = []
    intents: list[ArtifactInstallIntent] = []
    for planned in installations:
        try:
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
                    runtime=planned.runtime,
                    transport=planned.transport,
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
