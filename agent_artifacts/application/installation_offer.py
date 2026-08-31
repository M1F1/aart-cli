"""One Selection, planned and measured once, as the offer somebody is then asked to accept.

Four functions already answer the four questions an install asks. `plan_artifact_installation` says
what one artifact would do on this machine, `aggregate_requirements` says what the whole Selection
needs without asking for the same thing twice, `inspect_requirements` measures whether this machine
has it, and `installation_remediations` says what somebody would have to agree to where it does not.
What was missing was anything in production that called them in order. The only caller was a test
wiring them by hand, so neither the shell's action handler nor the public commands could reach the
canonical path without repeating that wiring -- and two copies of it disagree the first time one
changes.

An offer is not a decision. Nothing here mutates anything, selects a remediation, or reads a secret
value: inputs are bound to references, and the credential a launcher resolves at start is still only
a `CredentialReference` when this returns. Accepting is `begin_installation`, deliberately a second
call, because the thing between the two is a person.

The whole Selection succeeds or the offer refuses. Offering the half that planned would let somebody
confirm an install of two artifacts and receive one, which is the failure `execute_installation`
exists to prevent one layer down (D-064).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import McpTarget
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.inputs import InputValueSource
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.plans import PlannedRemediation
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import PythonInstaller
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState
from agent_artifacts.domain.remediations import Remediation
from agent_artifacts.domain.requirements import Requirement
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ResolvedArtifact

from .artifact_installation import (
    installation_remediations,
    plan_artifact_installation,
    requirements_for,
)
from .installation_planning import (
    EnvironmentInspectionPort,
    aggregate_requirements,
    inspect_requirements,
)
from .installation_proposal import PlannedInstallation, desired_state_for

__all__ = [
    "OFFER_NOT_PLANNABLE",
    "ArtifactPlacement",
    "InstallationOffer",
    "offer_installation",
]

#: An offer that could not be assembled at all -- nothing to install, or an artifact this machine
#: cannot plan. Distinct from a remediation being unavailable, which is an offer with work in it.
OFFER_NOT_PLANNABLE = DiagnosticCode("installation-offer-not-plannable")


@dataclass(frozen=True, slots=True)
class ArtifactPlacement:
    """One resolved artifact and where this machine would put it.

    The artifact says what it is; the placement says where. Keeping them in one value is what lets
    a caller answer for a whole Selection in one list rather than four parallel ones that can fall
    out of step with each other.
    """

    artifact: ResolvedArtifact
    description: InstallDescription
    root: str
    payload_source: str
    targets: tuple[McpTarget, ...] = ()
    sources: tuple[InputValueSource, ...] = ()
    preferred_installer: PythonInstaller | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact, ResolvedArtifact)
            or not isinstance(self.description, InstallDescription)
            or not isinstance(self.root, str)
            or not self.root
            or not isinstance(self.payload_source, str)
            or not self.payload_source
        ):
            raise ValueError("an artifact placement is invalid")

    @property
    def coordinate(self):
        return self.artifact.version.coordinate


@dataclass(frozen=True, slots=True)
class InstallationOffer:
    """What this machine would install, what it measured, and what it would need agreed to."""

    installations: tuple[PlannedInstallation, ...]
    facts: EnvironmentFacts
    remediations: tuple[PlannedRemediation, ...] = field(default=())
    #: What is on this machine right now for each artifact, one entry per installation. An artifact
    #: nothing is installed for is observed as an empty state rather than left out: "nobody looked"
    #: and "nothing is there" are different facts, and only the second one may plan a first install.
    observed: tuple[tuple[ArtifactCoordinate, CurrentState], ...] = field(default=())

    def __post_init__(self) -> None:
        if (
            not self.installations
            or any(not isinstance(item, PlannedInstallation) for item in self.installations)
            or not isinstance(self.facts, EnvironmentFacts)
            or any(not isinstance(item, PlannedRemediation) for item in self.remediations)
            or len(self.observed) != len(self.installations)
        ):
            raise ValueError("an installation offer is invalid")

    def selected(self) -> tuple[Remediation, ...]:
        """Everything offered, for a caller with nobody to ask.

        A non-interactive command has already been given its answer by the operator who typed it,
        so it accepts the whole offer or none of it. An interactive caller has screens 07 and 08
        instead and passes the subset somebody actually ticked, which is why this is a method to
        ignore rather than a field the offer already holds.
        """

        return tuple(item.remediation for item in self.remediations)


def _error(message: str) -> Err:
    return Err((Diagnostic(OFFER_NOT_PLANNABLE, Severity.ERROR, message),))


def offer_installation(
    placements: tuple[ArtifactPlacement, ...],
    *,
    policy: EffectivePolicy,
    facts: EnvironmentFacts,
    inspect: EnvironmentInspectionPort,
    observe: Callable[[DesiredState], CurrentState],
    base_interpreter: str | None = None,
    resolvers: tuple[object, ...] = (),
) -> Result[InstallationOffer]:
    """Plan the whole Selection, measure this machine once, and list what it would need agreed.

    `facts` going in is what this machine can be asked to do -- its remediation capabilities, which
    decide which installer a plan may choose. `facts` coming out is what it actually has, measured
    through the inspection port after planning knows what to ask about. They are deliberately not
    the same value: a capability is permission and a fact is an observation.
    """

    if not placements or any(not isinstance(item, ArtifactPlacement) for item in placements):
        return _error("an installation offer needs at least one artifact placement")
    if not isinstance(policy, EffectivePolicy) or not isinstance(facts, EnvironmentFacts):
        return _error("an installation offer needs a policy and this machine's capabilities")

    installations: list[PlannedInstallation] = []
    for placement in placements:
        planned = plan_artifact_installation(
            placement.artifact,
            placement.description,
            root=placement.root,
            payload_source=placement.payload_source,
            sources=placement.sources,
            policy=policy,
            facts=facts,
            base_interpreter=base_interpreter,
            targets=placement.targets,
            resolvers=resolvers,  # type: ignore[arg-type]
            preferred_installer=placement.preferred_installer,
        )
        if isinstance(planned, Err):
            # Returned as it came: the planner's diagnostic already names the artifact and why,
            # and rewrapping it here would replace a specific refusal with a vaguer one.
            return planned
        installations.append(planned.value)

    owned = aggregate_requirements(
        tuple(
            (
                placement.coordinate,
                requirements_for(placement.description, targets=placement.targets),
            )
            for placement in placements
        )
    )
    if isinstance(owned, Err):
        return owned
    requirements: tuple[Requirement, ...] = tuple(item.requirement for item in owned.value)

    measured = inspect_requirements(requirements, inspect)
    if isinstance(measured, Err):
        return measured

    offered = installation_remediations(tuple(installations), measured.value, policy)
    if isinstance(offered, Err):
        return offered

    observed: list[tuple[ArtifactCoordinate, CurrentState]] = []
    for installation in installations:
        try:
            observed.append((installation.coordinate, observe(desired_state_for(installation))))
        except Exception as error:  # noqa: BLE001 - the port is somebody else's code
            return _error(f"{installation.coordinate} could not be observed: {error}")

    try:
        return Ok(
            InstallationOffer(tuple(installations), measured.value, offered.value, tuple(observed))
        )
    except ValueError as error:
        return _error(f"this installation cannot be offered: {error}")
