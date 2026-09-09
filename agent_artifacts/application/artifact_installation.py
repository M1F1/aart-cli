"""What an artifact declares, met with what this machine offers.

`installation_proposal` lowers a :class:`PlannedInstallation` into the plan somebody reviews and the
effects that run. This is the step before it, and it is where the two halves of an install meet.
The package declares a runtime, a dependency descriptor and the inputs it is started with, and
knows nothing about any machine. The machine offers a root, an interpreter, values for the inputs
and harnesses to register with, and knows nothing about any artifact. Neither half can produce an
installation alone, and keeping the join in one place is what stops each half from guessing at the
other.

Two things are deliberately not decided here. Which backend installs the dependencies is
`select_python_installer`'s intersection of specification, platform and policy. What a launcher may
deliver is `generate_launcher`'s, which refuses a binding it cannot render rather than rendering
something that looks close. Both are asked, not restated.

Nothing here touches a filesystem, starts a process or reads a secret value. Inputs arrive as
references, and the launcher is derived rather than written.
"""

from __future__ import annotations

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import McpRegistration, McpTarget
from agent_artifacts.domain.inputs import InputValueSource, SecretInput
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.launch import launcher_path
from agent_artifacts.domain.plans import PlannedRemediation
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import (
    ArtifactEnvironment,
    PyProjectSpec,
    PythonInstaller,
    spec_descriptor_path,
    spec_kind,
)
from agent_artifacts.domain.requirements import (
    CredentialRequirement,
    HarnessRequirement,
    PythonPackageRequirement,
    Requirement,
    RequirementId,
    RuntimeRequirement,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ResolvedArtifact

from .input_binding import bind_runtime_inputs
from .installation_planning import (
    aggregate_requirements,
    allowed_remediations,
    assess_requirements,
)
from .installation_proposal import PlannedArtifact, PlannedInstallation
from .python_environment import dependency_installation, select_python_installer
from .runtime_projection import CredentialResolutionPort, generate_launcher

__all__ = [
    "INSTALLATION_NOT_DESCRIBED",
    "INSTALLATION_NOT_PLANNABLE",
    "installation_remediations",
    "plan_artifact_installation",
    "requirements_for",
]

INSTALLATION_NOT_DESCRIBED = DiagnosticCode("installation-not-described")
INSTALLATION_NOT_PLANNABLE = DiagnosticCode("installation-not-plannable")

#: An artifact that names a runtime without pinning it is asking for any version of it, which is
#: what the repository already spells `*` for a version constraint. Inventing a floor here would
#: make an install refuse machines the author never excluded.
UNCONSTRAINED = "*"


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def requirements_for(
    description: InstallDescription,
    *,
    targets: tuple[McpTarget, ...] = (),
) -> tuple[Requirement, ...]:
    """What has to be true of a machine before this artifact can be installed on it.

    §107 keeps these three apart because they fail apart: a missing interpreter, an unresolvable
    dependency and an unanswered credential are three different conversations with the person
    installing. The harnesses come from the request rather than the package -- an artifact declares
    what it is compatible with, and a person chooses where it goes.
    """

    if not isinstance(description, InstallDescription):
        raise ValueError("requirements are derived from an install description")
    requirements: list[Requirement] = []
    if description.runtime is not None:
        requirements.append(
            RuntimeRequirement(
                RequirementId(f"{description.runtime}-runtime"),
                description.runtime,
                description.runtime_version or UNCONSTRAINED,
            )
        )
    spec = description.dependencies
    if spec is not None:
        requirements.append(
            PythonPackageRequirement(
                RequirementId("python-packages"),
                spec_kind(spec),
                spec_descriptor_path(spec),
                spec.lock_format if isinstance(spec, PyProjectSpec) else None,
            )
        )
    requirements.extend(
        CredentialRequirement(RequirementId(str(item.id)), required=item.required)
        for item in description.inputs
        if isinstance(item, SecretInput)
    )
    requirements.extend(
        HarnessRequirement(RequirementId(f"harness-{target.harness}"), target.harness)
        for target in targets
    )
    return tuple(requirements)


def plan_artifact_installation(
    artifact: ResolvedArtifact,
    description: InstallDescription,
    *,
    root: str,
    payload_source: str,
    sources: tuple[InputValueSource, ...],
    policy: EffectivePolicy,
    facts: EnvironmentFacts,
    base_interpreter: str | None = None,
    targets: tuple[McpTarget, ...] = (),
    resolvers: tuple[CredentialResolutionPort, ...] = (),
    preferred_installer: PythonInstaller | None = None,
) -> Result[PlannedInstallation]:
    """Everything decided about installing `artifact` here, before anything is touched."""

    if not isinstance(artifact, ResolvedArtifact) or not isinstance(
        description, InstallDescription
    ):
        return _error(
            INSTALLATION_NOT_PLANNABLE,
            "planning an installation needs a resolved artifact and its install description",
        )
    contract = description.contract
    if contract is None:
        return _error(
            INSTALLATION_NOT_DESCRIBED,
            f"{artifact.version.coordinate} does not declare how it starts, so there is no "
            "launcher to generate and nothing for a harness to run",
        )

    identity = artifact.version.coordinate.artifact
    try:
        environment = ArtifactEnvironment(str(identity), root)
    except ValueError as error:
        return _error(INSTALLATION_NOT_PLANNABLE, f"installation root is invalid: {error}")

    bound = bind_runtime_inputs(description.inputs, sources, policy)
    if isinstance(bound, Err):
        return bound

    launcher = generate_launcher(environment, contract, bound.value, resolvers=resolvers)
    if isinstance(launcher, Err):
        return launcher
    if launcher.value.path != launcher_path(environment):
        return _error(
            INSTALLATION_NOT_PLANNABLE,
            "the generated launcher is not the one this artifact's harness entries would name",
        )

    dependencies: tuple[str, str, str] | None = None
    if description.dependencies is not None:
        if base_interpreter is None:
            return _error(
                INSTALLATION_NOT_PLANNABLE,
                f"{artifact.version.coordinate} declares dependencies, which need an interpreter "
                "to build the environment that holds them",
            )
        installer = select_python_installer(
            description.dependencies, facts, policy, preferred=preferred_installer
        )
        if isinstance(installer, Err):
            return installer
        dependencies = dependency_installation(
            environment, description.dependencies, installer.value
        )

    try:
        registrations = tuple(
            McpRegistration(
                target,
                identity.name,
                launcher.value.command,
                transport=contract.transport,
            )
            for target in targets
        )
        return Ok(
            PlannedInstallation(
                artifact,
                environment,
                contract,
                launcher.value,
                bound.value,
                registrations,
                payload_source,
                base_interpreter,
                dependencies,
                requirements_for(description, targets=targets),
                description.runtime,
                description.inputs,
            )
        )
    except ValueError as error:
        return _error(INSTALLATION_NOT_PLANNABLE, f"the installation is not plannable: {error}")


def installation_remediations(
    installations: tuple[PlannedArtifact, ...],
    facts: EnvironmentFacts,
    policy: EffectivePolicy,
) -> Result[tuple[PlannedRemediation, ...]]:
    """What this installation would need somebody to agree to, before it is proposed.

    Screens 07 and 08 offer these, and `prepare_install_plan` will refuse anything not among them,
    so the offer and the acceptance are computed by the same three functions. A person choosing
    from a list assembled some other way could pick something the plan then rejects, or -- worse --
    never be offered the one thing that would have made the install possible.

    Either shape of plan answers, because what is read here -- a coordinate and the requirements it
    carries -- is what the two have in common. A placement's requirements are only the harnesses
    that read it, so it contributes to the aggregate without ever asking for a runtime.
    """

    aggregated = aggregate_requirements(
        tuple((item.coordinate, item.requirements) for item in installations)
    )
    if isinstance(aggregated, Err):
        return aggregated
    return Ok(allowed_remediations(assess_requirements(aggregated.value, facts), facts, policy))
