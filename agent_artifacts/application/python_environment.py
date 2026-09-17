"""Pure Python installer selection and environment effect lowering.

Selection is an intersection, in one direction only: what the specification can be installed by,
what the platform can actually run, and what policy allows. A preference chooses within that set
and never widens it. Lowering is pure: it produces effects, and every path it writes is one the
artifact owns.
"""

from __future__ import annotations

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import (
    CreatePythonEnvironment,
    Effect,
    InstallPythonDependencies,
)
from agent_artifacts.domain.inspection import EnvironmentFacts, RemediationCapabilityKind
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import (
    ArtifactEnvironment,
    PyProjectSpec,
    PythonDependencySpec,
    PythonInstaller,
    chosen_installer,
    compatible_installers,
    spec_descriptor_path,
    spec_kind,
)
from agent_artifacts.domain.result import Err, Ok, Result

NO_COMPATIBLE_INSTALLER = DiagnosticCode("no-compatible-python-installer")
PYTHON_ENVIRONMENT_INVALID = DiagnosticCode("python-environment-invalid")


def _error(
    code: DiagnosticCode,
    message: str,
    *,
    details: tuple[tuple[str, str], ...] = (),
) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message, details=details),))


def _names(values: frozenset[PythonInstaller]) -> str:
    return ", ".join(sorted(item.value for item in values)) or "none"


def platform_installers(facts: EnvironmentFacts) -> frozenset[PythonInstaller]:
    """The backends this platform reports it can run, ignoring any it does not recognize."""

    known = {item.value: item for item in PythonInstaller}
    return frozenset(
        known[item.name]
        for item in facts.remediation_capabilities
        if item.kind is RemediationCapabilityKind.PYTHON_INSTALLER and item.name in known
    )


def _permitted_installers(
    compatible: frozenset[PythonInstaller], policy: EffectivePolicy
) -> frozenset[PythonInstaller]:
    if policy.allowed_python_installers is None:
        return compatible
    return frozenset(
        item for item in PythonInstaller if item.value in policy.allowed_python_installers
    )


def usable_python_installers(
    spec: PythonDependencySpec,
    facts: EnvironmentFacts,
    policy: EffectivePolicy,
) -> frozenset[PythonInstaller]:
    """Every backend that could install this specification here, before one of them is picked.

    `select_python_installer` takes exactly this set and narrows it to one. It is named separately
    because a screen offering a per-install choice has to offer what could run rather than what
    happened to win (issue #11b): an offer derived from anything else can disagree with the plan,
    and then a chosen backend comes back as a refusal the operator reads as their own mistake.
    """

    compatible = compatible_installers(spec)
    return compatible & platform_installers(facts) & _permitted_installers(compatible, policy)


def select_python_installer(
    spec: PythonDependencySpec,
    facts: EnvironmentFacts,
    policy: EffectivePolicy,
    *,
    preferred: PythonInstaller | None = None,
) -> Result[PythonInstaller]:
    """Choose one backend, or say precisely which of the three sets emptied the intersection."""

    compatible = compatible_installers(spec)
    available = platform_installers(facts)
    permitted = _permitted_installers(compatible, policy)
    candidates = usable_python_installers(spec, facts, policy)
    if not candidates:
        detail = (
            f"compatible: {_names(compatible)}; "
            f"available: {_names(available)}; "
            f"permitted: {_names(permitted)}"
        )
        return _error(
            NO_COMPATIBLE_INSTALLER,
            f"no Python installer satisfies the specification, the platform and policy ({detail})",
            details=(
                ("compatible", _names(compatible)),
                ("available", _names(available)),
                ("permitted", _names(permitted)),
            ),
        )
    selected = chosen_installer(candidates, preferred)
    assert selected is not None
    return Ok(selected)


def dependency_installation(
    environment: ArtifactEnvironment,
    spec: PythonDependencySpec,
    installer: PythonInstaller,
) -> tuple[str, str, str]:
    """The descriptor an installer reads, what kind it is, and the backend chosen for it.

    A locked project is a different kind from the project it locks: the installer is told to honour
    the lock rather than to resolve afresh, and approving one is not approving the other. One
    function decides that, because the effect that runs and the desired state a later repair keeps
    have to agree about it.
    """

    descriptor = environment.payload_path(spec_descriptor_path(spec))
    locked = isinstance(spec, PyProjectSpec) and spec.lock_format is not None
    return (descriptor, "locked-project" if locked else spec_kind(spec), installer.value)


def plan_python_environment(
    environment: ArtifactEnvironment,
    spec: PythonDependencySpec,
    installer: PythonInstaller,
    base_interpreter: str,
) -> Result[tuple[Effect, ...]]:
    """Lower one artifact's environment and dependencies into effects. Nothing runs here."""

    if (
        not isinstance(environment, ArtifactEnvironment)
        or not isinstance(installer, PythonInstaller)
        or not isinstance(base_interpreter, str)
        or not base_interpreter.strip()
    ):
        return _error(PYTHON_ENVIRONMENT_INVALID, "Python environment plan inputs are invalid")
    if environment.owns(base_interpreter):
        return _error(
            PYTHON_ENVIRONMENT_INVALID,
            "the base interpreter cannot be the environment being built from it",
        )
    if installer not in compatible_installers(spec):
        return _error(
            PYTHON_ENVIRONMENT_INVALID,
            f"installer {installer.value} cannot install the declared specification",
        )
    try:
        descriptor, kind, backend = dependency_installation(environment, spec, installer)
        return Ok(
            (
                CreatePythonEnvironment(
                    environment.artifact, environment.environment, base_interpreter
                ),
                InstallPythonDependencies(environment.environment, descriptor, kind, backend),
            )
        )
    except ValueError as error:
        return _error(PYTHON_ENVIRONMENT_INVALID, f"Python environment plan is invalid: {error}")
