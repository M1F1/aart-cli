"""Pure CP-07 environment assessment, remediation filtering and install planning."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol, cast

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import Effect, RiskClass, effect_to_data
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ObjectDigest
from agent_artifacts.domain.inspection import (
    EnvironmentFact,
    EnvironmentFacts,
    FactState,
    RemediationCapabilityKind,
)
from agent_artifacts.domain.plans import (
    InstallPlan,
    MutationPlan,
    OwnedAssessment,
    OwnedRequirement,
    PlannedEffect,
    PlannedRemediation,
)
from agent_artifacts.domain.policies import EffectivePolicy, policy_to_data
from agent_artifacts.domain.python_runtime import installers_for_lock
from agent_artifacts.domain.remediations import (
    ConfigureCredential,
    ConfigureHarness,
    ConfigureNetwork,
    InstallExecutable,
    InstallPythonPackages,
    InstallRuntime,
    Remediation,
    remediation_to_data,
)
from agent_artifacts.domain.requirements import (
    CredentialRequirement,
    ExecutableRequirement,
    FilesystemRequirement,
    HarnessRequirement,
    NetworkRequirement,
    PythonPackageRequirement,
    Requirement,
    RequirementId,
    RequirementState,
    RuntimeRequirement,
    requirement_to_data,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import (
    ResolvedArtifact,
    ResolvedSelection,
    artifact_coordinate_sort_key,
)
from agent_artifacts.domain.serialization import CanonicalValue, canonical_json_bytes
from agent_artifacts.protocol.semver import SemVer, parse_semver

PLANNING_INVALID = DiagnosticCode("installation-planning-invalid")
REQUIREMENT_CONFLICT = DiagnosticCode("requirement-conflict")
NO_ALLOWED_REMEDIATION = DiagnosticCode("no-allowed-remediation")
POLICY_VIOLATION = DiagnosticCode("policy-violation")
INSPECTION_INVALID = DiagnosticCode("environment-inspection-invalid")
_PARTIAL_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?(?:\.(0|[1-9][0-9]*))?$")


def _error(
    code: DiagnosticCode,
    message: str,
    *,
    details: tuple[tuple[str, str], ...] = (),
) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message, details=details),))


def _canonical(value: object) -> bytes:
    return canonical_json_bytes(cast(CanonicalValue, value))


def _requirement_key(requirement: Requirement) -> bytes:
    return _canonical(requirement_to_data(requirement))


def _remediation_key(remediation: Remediation) -> bytes:
    return _canonical(remediation_to_data(remediation))


def _effect_key(effect: Effect) -> bytes:
    return _canonical(effect_to_data(effect))


@dataclass(frozen=True, slots=True)
class ArtifactInstallIntent:
    artifact: ResolvedArtifact
    requirements: tuple[Requirement, ...]
    effects: tuple[Effect, ...]
    runtime: str | None = None
    transport: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ResolvedArtifact):
            raise ValueError("artifact install intent requires an exact resolved artifact")
        for label, value in (("runtime", self.runtime), ("transport", self.transport)):
            if value is not None and (
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or any(character in value for character in "\r\n")
            ):
                raise ValueError(f"install intent {label} is invalid")
        object.__setattr__(
            self,
            "requirements",
            tuple(sorted(set(self.requirements), key=_requirement_key)),
        )
        object.__setattr__(self, "effects", tuple(sorted(set(self.effects), key=_effect_key)))

    @property
    def coordinate(self) -> ArtifactCoordinate:
        return self.artifact.version.coordinate


class EnvironmentInspectionPort(Protocol):
    def inspect(self, requirements: tuple[Requirement, ...]) -> Result[EnvironmentFacts]: ...


def inspect_requirements(
    requirements: tuple[Requirement, ...],
    inspector: EnvironmentInspectionPort,
) -> Result[EnvironmentFacts]:
    """Cross the read-only inspection port once and make absent observations explicit unknowns."""

    ordered = tuple(sorted(set(requirements), key=_requirement_key))
    identifiers = tuple(item.id for item in ordered)
    if len(set(identifiers)) != len(identifiers):
        return _error(
            INSPECTION_INVALID,
            "environment inspection requires unique requirement IDs",
        )
    inspected = inspector.inspect(ordered)
    if isinstance(inspected, Err):
        return inspected
    expected = set(identifiers)
    actual = {item.requirement for item in inspected.value.facts}
    if actual - expected:
        return _error(
            INSPECTION_INVALID,
            "environment inspector returned facts outside the requested boundary",
        )
    missing = tuple(
        EnvironmentFact(identifier, FactState.UNKNOWN) for identifier in sorted(expected - actual)
    )
    return Ok(
        EnvironmentFacts(
            inspected.value.platform,
            (*inspected.value.facts, *missing),
            inspected.value.remediation_capabilities,
        )
    )


def aggregate_requirements(
    artifact_requirements: tuple[tuple[ArtifactCoordinate, tuple[Requirement, ...]], ...],
) -> Result[tuple[OwnedRequirement, ...]]:
    """Deduplicate equivalent bulk requirements while preserving every dependant."""

    by_id: dict[RequirementId, tuple[Requirement, set[ArtifactCoordinate]]] = {}
    for owner, requirements in artifact_requirements:
        for requirement in requirements:
            existing = by_id.get(requirement.id)
            if existing is not None and existing[0] != requirement:
                return _error(
                    REQUIREMENT_CONFLICT,
                    f"requirement {requirement.id} has conflicting declarations",
                    details=(("requirement", requirement.id.value),),
                )
            if existing is None:
                by_id[requirement.id] = (requirement, {owner})
            else:
                existing[1].add(owner)
    return Ok(
        tuple(
            sorted(
                (
                    OwnedRequirement(requirement, tuple(owners))
                    for requirement, owners in by_id.values()
                ),
                key=lambda item: item.sort_key,
            )
        )
    )


def _partial_semver(raw: str) -> SemVer | None:
    match = _PARTIAL_VERSION_RE.fullmatch(raw)
    if match is None:
        return None
    values = tuple(0 if value is None else int(value) for value in match.groups())
    if any(value > 2**63 - 1 for value in values):
        return None
    return SemVer(values[0], values[1], values[2])


def _runtime_constraint_allows(constraint: str, observed: str) -> bool | None:
    actual = parse_semver(observed)
    if isinstance(actual, Err):
        return None
    if constraint.startswith("^"):
        minimum = _partial_semver(constraint[1:])
        if minimum is None:
            return None
        maximum = (
            SemVer(minimum.major + 1, 0, 0)
            if minimum.major
            else SemVer(0, minimum.minor + 1, 0)
            if minimum.minor
            else SemVer(0, 0, minimum.patch + 1)
        )
        return minimum <= actual.value < maximum
    comparisons = []
    for part in constraint.split(","):
        match = re.fullmatch(r"(>=|<=|>|<|=)?(.+)", part)
        if match is None:
            return None
        expected = _partial_semver(match.group(2))
        if expected is None:
            exact = parse_semver(match.group(2))
            if isinstance(exact, Err):
                return None
            expected = exact.value
        comparisons.append((match.group(1) or "=", expected))
    return all(
        {
            ">=": actual.value >= expected,
            ">": actual.value > expected,
            "<=": actual.value <= expected,
            "<": actual.value < expected,
            "=": actual.value == expected,
        }[operator]
        for operator, expected in comparisons
    )


def assess_requirements(
    requirements: tuple[OwnedRequirement, ...],
    facts: EnvironmentFacts,
) -> tuple[OwnedAssessment, ...]:
    """Pure three-state comparison; facts are inputs, never inspected here."""

    by_id = {item.requirement: item for item in facts.facts}
    assessments = []
    for owned in requirements:
        requirement = owned.requirement
        fact = by_id.get(requirement.id)
        if fact is None or fact.state is FactState.UNKNOWN:
            state = RequirementState.UNKNOWN
            detail = "environment has no conclusive observation"
        elif fact.state is FactState.UNAVAILABLE:
            state = RequirementState.UNSATISFIED
            detail = "required capability is unavailable"
        elif isinstance(requirement, RuntimeRequirement):
            if fact.observed_version is None:
                state = RequirementState.UNKNOWN
                detail = "runtime is available but its version is unknown"
            else:
                allowed = _runtime_constraint_allows(requirement.constraint, fact.observed_version)
                if allowed is None:
                    state = RequirementState.UNKNOWN
                    detail = "runtime version evidence or constraint is invalid"
                else:
                    state = RequirementState.SATISFIED if allowed else RequirementState.UNSATISFIED
                    detail = f"observed {fact.observed_version}; expected {requirement.constraint}"
        else:
            state = RequirementState.SATISFIED
            detail = "required capability is available"
        assessments.append(OwnedAssessment(owned, state, detail))
    return tuple(sorted(assessments, key=lambda item: item.sort_key))


def _capability_names(
    facts: EnvironmentFacts,
    kind: RemediationCapabilityKind,
) -> frozenset[str]:
    return frozenset(item.name for item in facts.remediation_capabilities if item.kind is kind)


def _remediation_risk(remediation: Remediation) -> RiskClass:
    if isinstance(remediation, ConfigureCredential):
        return RiskClass.CREDENTIAL_MUTATION
    if isinstance(remediation, (InstallRuntime, InstallExecutable, InstallPythonPackages)):
        return RiskClass.EXECUTABLE_INSTALL
    if isinstance(remediation, ConfigureNetwork):
        return RiskClass.NETWORK_MUTATION
    return RiskClass.CONFIGURATION_MUTATION


def _remediation_policy_key(remediation: Remediation) -> str:
    if isinstance(remediation, ConfigureCredential):
        return "store-credential"
    if isinstance(remediation, InstallRuntime):
        return "install-runtime"
    if isinstance(remediation, InstallExecutable):
        return "install-executable"
    if isinstance(remediation, InstallPythonPackages):
        return "install-python-packages"
    if isinstance(remediation, ConfigureNetwork):
        return "configure-network"
    return "configure-harness"


def _possible_remediations(
    assessment: OwnedAssessment,
    facts: EnvironmentFacts,
) -> tuple[Remediation, ...]:
    requirement = assessment.requirement.requirement
    if assessment.state is RequirementState.SATISFIED:
        return ()
    if isinstance(requirement, CredentialRequirement):
        if not requirement.required:
            return ()
        providers = _capability_names(facts, RemediationCapabilityKind.CREDENTIAL_PROVIDER)
        if requirement.provider is not None:
            providers &= {requirement.provider}
        return tuple(
            ConfigureCredential(requirement.id, provider) for provider in sorted(providers)
        )
    if isinstance(requirement, RuntimeRequirement):
        available = _capability_names(facts, RemediationCapabilityKind.RUNTIME_INSTALLER)
        return (
            (InstallRuntime(requirement.id, requirement.runtime, requirement.constraint),)
            if requirement.runtime in available
            else ()
        )
    if isinstance(requirement, ExecutableRequirement):
        available = _capability_names(facts, RemediationCapabilityKind.EXECUTABLE_INSTALLER)
        return (
            (InstallExecutable(requirement.id, requirement.executable),)
            if requirement.executable in available
            else ()
        )
    if isinstance(requirement, NetworkRequirement):
        available = _capability_names(facts, RemediationCapabilityKind.NETWORK_CONFIGURATION)
        return (
            (ConfigureNetwork(requirement.id, requirement.host),)
            if requirement.host in available or "*" in available
            else ()
        )
    if isinstance(requirement, HarnessRequirement):
        available = _capability_names(facts, RemediationCapabilityKind.HARNESS_CONFIGURATION)
        return (
            (ConfigureHarness(requirement.id, requirement.harness),)
            if requirement.harness in available
            else ()
        )
    if isinstance(requirement, PythonPackageRequirement):
        # Which backends could read this contract, intersected with what the platform runs. A
        # backend the artifact's lock was not written by is never offered.
        readable = {item.value for item in installers_for_lock(requirement.lock_format)}
        available = _capability_names(facts, RemediationCapabilityKind.PYTHON_INSTALLER)
        return tuple(
            InstallPythonPackages(requirement.id, installer)
            for installer in sorted(readable & available)
        )
    assert isinstance(requirement, FilesystemRequirement)
    return ()


def allowed_remediations(
    assessments: tuple[OwnedAssessment, ...],
    facts: EnvironmentFacts,
    policy: EffectivePolicy,
) -> tuple[PlannedRemediation, ...]:
    if not policy.interactive_remediation:
        return ()
    options = []
    for assessment in assessments:
        for remediation in _possible_remediations(assessment, facts):
            risk = _remediation_risk(remediation)
            if risk > policy.risk_ceiling:
                continue
            if _remediation_policy_key(remediation) in policy.forbidden_effects:
                continue
            if isinstance(remediation, ConfigureCredential) and (
                policy.allowed_credential_providers is not None
                and remediation.provider not in policy.allowed_credential_providers
            ):
                continue
            if isinstance(remediation, InstallRuntime) and (
                policy.allowed_runtimes is not None
                and remediation.runtime not in policy.allowed_runtimes
            ):
                continue
            if isinstance(remediation, InstallPythonPackages) and (
                policy.allowed_python_installers is not None
                and remediation.installer not in policy.allowed_python_installers
            ):
                continue
            if isinstance(remediation, ConfigureNetwork) and (
                policy.allowed_network_hosts is not None
                and remediation.host not in policy.allowed_network_hosts
            ):
                continue
            options.append(PlannedRemediation(remediation, assessment.requirement.owners, risk))
    return tuple(sorted(options, key=lambda item: item.sort_key))


def _policy_failure(message: str) -> Err:
    return _error(POLICY_VIOLATION, message)


def _validate_intents(
    selection: ResolvedSelection,
    intents: tuple[ArtifactInstallIntent, ...],
) -> Result[tuple[ArtifactInstallIntent, ...]]:
    expected = {item.version.coordinate: item for item in selection.artifacts}
    actual = {item.coordinate: item for item in intents}
    if (
        len(actual) != len(intents)
        or set(actual) != set(expected)
        or any(actual[coordinate].artifact != artifact for coordinate, artifact in expected.items())
    ):
        return _error(
            PLANNING_INVALID,
            "install intents must bind every exact resolved artifact exactly once",
        )
    return Ok(
        tuple(sorted(intents, key=lambda item: artifact_coordinate_sort_key(item.coordinate)))
    )


def _policy_digest(policy: EffectivePolicy) -> ObjectDigest:
    digest = hashlib.sha256(_canonical(policy_to_data(policy)))
    return ObjectDigest("sha256", digest.hexdigest())


def _required(assessment: OwnedAssessment) -> bool:
    requirement = assessment.requirement.requirement
    return not isinstance(requirement, CredentialRequirement) or requirement.required


def prepare_install_plan(
    selection: ResolvedSelection,
    intents: tuple[ArtifactInstallIntent, ...],
    facts: EnvironmentFacts,
    policy: EffectivePolicy,
    *,
    selected_remediations: tuple[Remediation, ...] = (),
) -> Result[InstallPlan]:
    """Produce one exact review plan; this function has no inspection or mutation port."""

    checked = _validate_intents(selection, intents)
    if isinstance(checked, Err):
        return checked
    for intent in checked.value:
        registry = intent.coordinate.source.value
        if policy.allowed_registries is not None and registry not in policy.allowed_registries:
            return _policy_failure(f"registry {registry} is forbidden by effective policy")
        if (
            intent.runtime is not None
            and policy.allowed_runtimes is not None
            and intent.runtime not in policy.allowed_runtimes
        ):
            return _policy_failure(f"runtime {intent.runtime} is forbidden by effective policy")
        if (
            intent.transport is not None
            and policy.allowed_transports is not None
            and intent.transport not in policy.allowed_transports
        ):
            return _policy_failure(f"transport {intent.transport} is forbidden by effective policy")
        for effect in intent.effects:
            if not policy.permits_effect(effect):
                return _policy_failure(
                    f"effect {type(effect).__name__} is forbidden by effective policy"
                )

    aggregated = aggregate_requirements(
        tuple((intent.coordinate, intent.requirements) for intent in checked.value)
    )
    if isinstance(aggregated, Err):
        return aggregated
    assessments = assess_requirements(aggregated.value, facts)
    options = allowed_remediations(assessments, facts, policy)
    option_by_value = {item.remediation: item for item in options}
    selected = tuple(sorted(set(selected_remediations), key=_remediation_key))
    if any(item not in option_by_value for item in selected):
        return _policy_failure(
            "selected remediation is unavailable, unsupported or forbidden by effective policy"
        )
    selected_ids = {item.requirement for item in selected}
    unresolved = tuple(
        item
        for item in assessments
        if item.state is not RequirementState.SATISFIED
        and _required(item)
        and item.requirement.requirement.id not in selected_ids
    )
    if unresolved:
        identifiers = ", ".join(item.requirement.requirement.id.value for item in unresolved)
        mode = (
            "non-interactive policy permits no wizard; "
            if not policy.interactive_remediation
            else ""
        )
        return _error(
            NO_ALLOWED_REMEDIATION,
            f"{mode}unresolved requirements need an explicit allowed remediation: {identifiers}",
            details=(("requirements", identifiers),),
        )

    effect_owners: dict[Effect, set[ArtifactCoordinate]] = {}
    for intent in checked.value:
        for effect in intent.effects:
            effect_owners.setdefault(effect, set()).add(intent.coordinate)
    planned_effects = tuple(
        PlannedEffect(effect, tuple(owners)) for effect, owners in effect_owners.items()
    )
    chosen = tuple(option_by_value[item] for item in selected)
    risks = tuple(
        sorted(
            {
                *(item.effect.risk for item in planned_effects),
                *(item.risk for item in chosen),
            }
        )
    )
    try:
        return Ok(
            InstallPlan(
                selection,
                facts.platform,
                assessments,
                chosen,
                MutationPlan(planned_effects, risks),
                _policy_digest(policy),
            )
        )
    except ValueError as error:
        return _error(PLANNING_INVALID, f"canonical install plan is invalid: {error}")
