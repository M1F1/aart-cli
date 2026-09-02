"""Candidate validation as a pipeline of named checks, over one compiled artifact.

164.6 presents validation as an explicit list of checks rather than as a verdict, and makes three
separations load-bearing. Warnings and errors are distinct: an error is not a severe warning, and
collapsing them into one severity column would let a broken Candidate look like a noisy one. Policy
decides whether a warning blocks promotion, so the same Candidate can be ready in one organisation
and blocked in another without either answer being a bug. And policy-required manual approval is an
explicit Candidate state, not a warning a renderer happens to treat specially -- because "a person
must look at this" and "this looks slightly odd" are different instructions.

Every check here reads the compiled artifact the Candidate already carries. Nothing touches a
filesystem, a clock, a network or a registry. Most of what a manifest can get wrong is refused by
`compile_author_snapshot` long before a Candidate exists, so several checks are re-verifications:
they pass for anything that compiled, and they are what notices a Candidate history that was
tampered with or corrupted after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent_artifacts.application.maintainer import CandidateBundle
from agent_artifacts.domain.candidates import (
    CandidateFinding,
    CandidateId,
    CandidateState,
    FindingSeverity,
    assess_candidate,
)
from agent_artifacts.domain.inputs import BindingExposure, SecretInput, binding_kind
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import spec_descriptor_path
from agent_artifacts.domain.result import Err
from agent_artifacts.protocol.authoring import (
    PACKAGE_MANIFEST_FILENAME,
    read_package_description,
)
from agent_artifacts.protocol.native_tree import SnapshotEntry, SnapshotEntryKind
from agent_artifacts.redaction import redact_text

__all__ = [
    "VALIDATION_PIPELINE",
    "CandidateValidation",
    "ValidationCheck",
    "ValidationCheckResult",
    "ValidationDetail",
    "ValidationOutcome",
    "validate_candidate",
    "validated_candidate",
]

#: The two canonical files that sit beside the payload rather than inside it.
_PROVENANCE_FILENAME = "provenance.json"
_PAYLOAD_PREFIX = "payload/"
#: Where a secret may be delivered. Anything weaker is observable to other processes.
_SAFE_SECRET_EXPOSURE = BindingExposure.INHERITED_ENVIRONMENT


class ValidationCheck(str, Enum):
    """The named checks 164.6 presents, in the order it presents them."""

    MANIFEST_SCHEMA = "manifest-schema"
    PAYLOAD_BOUNDARIES = "payload-boundaries"
    SPECIAL_FILES = "special-files"
    RUNTIME_DESCRIPTOR = "runtime-descriptor"
    DEPENDENCY_DESCRIPTOR = "dependency-descriptor"
    INPUT_DEFINITIONS = "input-definitions"
    SECRET_METADATA = "secret-metadata"
    POLICY = "policy"
    SECURITY = "security-checks"
    LIVE_ACCEPTANCE = "live-acceptance"


VALIDATION_PIPELINE: tuple[ValidationCheck, ...] = tuple(ValidationCheck)


class ValidationOutcome(str, Enum):
    """How one check stands.

    `NOT_RUN` is deliberately not a pass. A check that could not run has produced no evidence, and
    a policy that requires it is entitled to say so rather than to be told everything is fine.
    """

    PASSED = "passed"
    WARNING = "warning"
    ERROR = "error"
    NOT_RUN = "not-run"


def _line(value: str) -> str:
    return redact_text(" ".join(value.split()))


@dataclass(frozen=True, slots=True, order=True)
class ValidationDetail:
    """One actionable thing a check found: where it is, what was declared, what was expected."""

    message: str
    path: str | None = None
    declared: str | None = None
    expected: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("a validation detail needs a message")
        object.__setattr__(self, "message", _line(self.message))
        for name in ("path", "declared", "expected"):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str) or not value:
                raise ValueError(f"validation detail {name} must be a non-empty line or nothing")
            object.__setattr__(self, name, _line(value))


@dataclass(frozen=True, slots=True)
class ValidationCheckResult:
    check: ValidationCheck
    outcome: ValidationOutcome
    details: tuple[ValidationDetail, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.check, ValidationCheck)
            or not isinstance(self.outcome, ValidationOutcome)
            or not isinstance(self.details, tuple)
            or any(not isinstance(item, ValidationDetail) for item in self.details)
        ):
            raise ValueError("a validation check result is invalid")
        if (
            self.outcome in (ValidationOutcome.WARNING, ValidationOutcome.ERROR)
            and not self.details
        ):
            raise ValueError("a failing check has to say what it found")

    @property
    def findings(self) -> tuple[CandidateFinding, ...]:
        """What this check contributes to the Candidate. A pass contributes nothing.

        `NOT_RUN` contributes nothing either: it is not a defect in the Candidate, it is missing
        evidence, and policy -- not severity -- is what decides whether that matters.
        """

        severity = {
            ValidationOutcome.WARNING: FindingSeverity.WARNING,
            ValidationOutcome.ERROR: FindingSeverity.ERROR,
        }.get(self.outcome)
        if severity is None:
            return ()
        return tuple(
            CandidateFinding(self.check.value, severity, item.message) for item in self.details
        )


@dataclass(frozen=True, slots=True)
class CandidateValidation:
    """One complete run of the pipeline over one Candidate, under one policy."""

    candidate_id: CandidateId
    results: tuple[ValidationCheckResult, ...]
    required_checks: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_id, CandidateId)
            or not isinstance(self.results, tuple)
            or any(not isinstance(item, ValidationCheckResult) for item in self.results)
            or tuple(item.check for item in self.results) != VALIDATION_PIPELINE
            or not isinstance(self.required_checks, frozenset)
            or any(not isinstance(item, str) or not item for item in self.required_checks)
        ):
            raise ValueError("a Candidate validation runs every named check exactly once, in order")

    def result(self, check: ValidationCheck) -> ValidationCheckResult:
        if not isinstance(check, ValidationCheck):
            raise ValueError("a validation result is looked up by a named check")
        return next(item for item in self.results if item.check is check)

    @property
    def findings(self) -> tuple[CandidateFinding, ...]:
        return tuple(item for result in self.results for item in result.findings)

    @property
    def unmet_requirements(self) -> tuple[ValidationCheck, ...]:
        """The checks this policy requires that did not pass, whether warned or never run."""

        return tuple(
            item.check
            for item in self.results
            if item.check.value in self.required_checks
            and item.outcome is not ValidationOutcome.PASSED
        )

    @property
    def manual_approval_required(self) -> bool:
        return bool(self.unmet_requirements)

    @property
    def state(self) -> CandidateState:
        """The state this run implies, decided the same way `assess_candidate` decides it."""

        if any(item.outcome is ValidationOutcome.ERROR for item in self.results):
            return CandidateState.INVALID
        if self.manual_approval_required:
            return CandidateState.APPROVAL_REQUIRED
        if any(item.outcome is ValidationOutcome.WARNING for item in self.results):
            return CandidateState.WARNING
        return CandidateState.READY


def _result(
    check: ValidationCheck,
    errors: tuple[ValidationDetail, ...],
    warnings: tuple[ValidationDetail, ...] = (),
) -> ValidationCheckResult:
    """An error outranks a warning inside one check: the worst thing found is what it reports."""

    if errors:
        return ValidationCheckResult(check, ValidationOutcome.ERROR, errors)
    if warnings:
        return ValidationCheckResult(check, ValidationOutcome.WARNING, warnings)
    return ValidationCheckResult(check, ValidationOutcome.PASSED)


def _manifest_schema(
    entries: tuple[SnapshotEntry, ...],
) -> tuple[ValidationCheckResult, InstallDescription | None]:
    described = read_package_description(entries)
    if isinstance(described, Err):
        detail = ValidationDetail(
            described.diagnostics[0].message,
            path=PACKAGE_MANIFEST_FILENAME,
        )
        return ValidationCheckResult(
            ValidationCheck.MANIFEST_SCHEMA, ValidationOutcome.ERROR, (detail,)
        ), None
    return ValidationCheckResult(
        ValidationCheck.MANIFEST_SCHEMA, ValidationOutcome.PASSED
    ), described.value


def _payload_boundaries(entries: tuple[SnapshotEntry, ...]) -> ValidationCheckResult:
    errors = tuple(
        ValidationDetail(
            "canonical tree carries a path outside the package boundary",
            path=str(entry.path),
            declared=str(entry.path),
            expected=f"{PACKAGE_MANIFEST_FILENAME}, {_PROVENANCE_FILENAME} or {_PAYLOAD_PREFIX}…",
        )
        for entry in entries
        if str(entry.path) not in (PACKAGE_MANIFEST_FILENAME, _PROVENANCE_FILENAME)
        and not str(entry.path).startswith(_PAYLOAD_PREFIX)
    )
    return _result(ValidationCheck.PAYLOAD_BOUNDARIES, errors)


def _special_files(entries: tuple[SnapshotEntry, ...]) -> ValidationCheckResult:
    errors = tuple(
        ValidationDetail(
            "a canonical package holds regular files only",
            path=str(entry.path),
            declared=entry.kind.value,
            expected=SnapshotEntryKind.FILE.value,
        )
        for entry in entries
        if entry.kind is not SnapshotEntryKind.FILE
    )
    return _result(ValidationCheck.SPECIAL_FILES, errors)


def _runtime_descriptor(description: InstallDescription | None) -> ValidationCheckResult:
    if description is None:
        return ValidationCheckResult(ValidationCheck.RUNTIME_DESCRIPTOR, ValidationOutcome.NOT_RUN)
    if description.contract is not None and description.runtime is None:
        return _result(
            ValidationCheck.RUNTIME_DESCRIPTOR,
            (
                ValidationDetail(
                    "the artifact declares how it launches but not what it runs on",
                    declared="none",
                    expected="a declared runtime",
                ),
            ),
        )
    warnings = (
        ()
        if description.runtime is None or description.runtime_version is not None
        else (
            ValidationDetail(
                f"runtime {description.runtime} is declared without a version constraint",
                declared=description.runtime,
                expected="a version constraint",
            ),
        )
    )
    return _result(ValidationCheck.RUNTIME_DESCRIPTOR, (), warnings)


def _dependency_descriptor(
    description: InstallDescription | None, entries: tuple[SnapshotEntry, ...]
) -> ValidationCheckResult:
    if description is None:
        return ValidationCheckResult(
            ValidationCheck.DEPENDENCY_DESCRIPTOR, ValidationOutcome.NOT_RUN
        )
    if description.dependencies is None:
        # Declaring no dependencies is an answer, not an omission.
        return ValidationCheckResult(
            ValidationCheck.DEPENDENCY_DESCRIPTOR, ValidationOutcome.PASSED
        )
    expected = f"{_PAYLOAD_PREFIX}{spec_descriptor_path(description.dependencies)}"
    present = any(str(entry.path) == expected for entry in entries)
    errors = (
        ()
        if present
        else (
            ValidationDetail(
                "the dependency descriptor the manifest names is not in the payload",
                path=expected,
                declared=expected,
                expected="a payload file at that path",
            ),
        )
    )
    return _result(ValidationCheck.DEPENDENCY_DESCRIPTOR, errors)


def _input_definitions(description: InstallDescription | None) -> ValidationCheckResult:
    if description is None:
        return ValidationCheckResult(ValidationCheck.INPUT_DEFINITIONS, ValidationOutcome.NOT_RUN)
    warnings = tuple(
        ValidationDetail(
            f"input {item.id.value} is asked for without a label to ask with",
            declared=item.id.value,
            expected="a guidance label",
        )
        for item in description.inputs
        if item.guidance is None
    )
    return _result(ValidationCheck.INPUT_DEFINITIONS, (), warnings)


def _secret_metadata(description: InstallDescription | None) -> ValidationCheckResult:
    if description is None:
        return ValidationCheckResult(ValidationCheck.SECRET_METADATA, ValidationOutcome.NOT_RUN)
    secrets = tuple(item for item in description.inputs if isinstance(item, SecretInput))
    errors = tuple(
        ValidationDetail(
            f"secret input {item.id.value} is delivered where other processes can read it",
            declared=binding_kind(item.binding),
            expected="environment, file or stdin",
        )
        for item in secrets
        if item.binding.exposure > _SAFE_SECRET_EXPOSURE
    )
    warnings = tuple(
        ValidationDetail(
            f"secret input {item.id.value} says nothing about where its value is obtained",
            declared=item.id.value,
            expected="acquisition guidance",
        )
        for item in secrets
        if item.guidance is None or item.guidance.obtain_from is None
    )
    return _result(ValidationCheck.SECRET_METADATA, errors, warnings)


def _policy(
    description: InstallDescription | None, policy: EffectivePolicy
) -> ValidationCheckResult:
    if description is None:
        return ValidationCheckResult(ValidationCheck.POLICY, ValidationOutcome.NOT_RUN)
    errors: list[ValidationDetail] = []
    runtime = description.runtime
    if policy.allowed_runtimes is not None and runtime is not None:
        if runtime not in policy.allowed_runtimes:
            errors.append(
                ValidationDetail(
                    f"policy does not allow the {runtime} runtime",
                    declared=runtime,
                    expected=", ".join(sorted(policy.allowed_runtimes)),
                )
            )
    transport = None if description.contract is None else description.contract.transport.value
    if policy.allowed_transports is not None and transport is not None:
        if transport not in policy.allowed_transports:
            errors.append(
                ValidationDetail(
                    f"policy does not allow the {transport} transport",
                    declared=transport,
                    expected=", ".join(sorted(policy.allowed_transports)),
                )
            )
    if policy.allowed_secret_bindings is not None:
        for item in description.inputs:
            if not isinstance(item, SecretInput):
                continue
            kind = binding_kind(item.binding)
            if kind not in policy.allowed_secret_bindings:
                errors.append(
                    ValidationDetail(
                        f"policy does not allow secret {item.id.value} to be bound by {kind}",
                        declared=kind,
                        expected=", ".join(sorted(policy.allowed_secret_bindings)),
                    )
                )
    return _result(ValidationCheck.POLICY, tuple(errors))


def _security(
    description: InstallDescription | None,
    entries: tuple[SnapshotEntry, ...],
    policy: EffectivePolicy,
) -> ValidationCheckResult:
    warnings = tuple(
        ValidationDetail(
            "payload file is delivered executable",
            path=str(entry.path),
            declared="executable",
        )
        for entry in entries
        if entry.executable and str(entry.path).startswith(_PAYLOAD_PREFIX)
    )
    errors: list[ValidationDetail] = []
    if description is not None and policy.allowed_network_hosts is not None:
        for item in description.inputs:
            obtain = None if item.guidance is None else item.guidance.obtain_from
            if obtain is None:
                continue
            host = obtain.url.split("/")[2].split("@")[-1].split(":")[0].lower()
            if host not in policy.allowed_network_hosts:
                errors.append(
                    ValidationDetail(
                        f"input {item.id.value} sends people to a host policy does not allow",
                        declared=host,
                        expected=", ".join(sorted(policy.allowed_network_hosts)),
                    )
                )
    return _result(ValidationCheck.SECURITY, tuple(errors), warnings)


def validate_candidate(bundle: CandidateBundle, *, policy: EffectivePolicy) -> CandidateValidation:
    """Run every named check over one compiled Candidate. No IO, no clock, no registry."""

    if not isinstance(bundle, CandidateBundle) or not isinstance(policy, EffectivePolicy):
        raise ValueError("Candidate validation needs one Candidate bundle and one policy")
    entries = bundle.artifact.canonical_entries
    schema, description = _manifest_schema(entries)
    results = (
        schema,
        _payload_boundaries(entries),
        _special_files(entries),
        _runtime_descriptor(description),
        _dependency_descriptor(description, entries),
        _input_definitions(description),
        _secret_metadata(description),
        _policy(description, policy),
        _security(description, entries, policy),
        # Live acceptance is a real installation on a real machine, which CP-17 owns. Saying so is
        # the honest answer; ticking it here would claim evidence nothing produced.
        ValidationCheckResult(ValidationCheck.LIVE_ACCEPTANCE, ValidationOutcome.NOT_RUN),
    )
    return CandidateValidation(bundle.candidate.id, results, frozenset(policy.required_checks))


def validated_candidate(bundle: CandidateBundle, *, policy: EffectivePolicy) -> CandidateBundle:
    """The same Candidate carrying what the pipeline found, in the state that implies."""

    validation = validate_candidate(bundle, policy=policy)
    return CandidateBundle(
        assess_candidate(
            bundle.candidate,
            findings=validation.findings,
            manual_approval_required=validation.manual_approval_required,
        ),
        bundle.artifact,
    )
