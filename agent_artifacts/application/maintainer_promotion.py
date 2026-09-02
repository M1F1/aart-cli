"""What a Maintainer confirms when promoting one reviewed Candidate into an approved registry.

Promotion is the first Maintainer action that writes approved registry state, so what it records
has to be the review that actually happened.  The evidence it carries is a digest of the validation
run and of the policy that judged it, which is what lets an audit record answer "who approved this,
against which rules" rather than only "this was promoted".

Every transformation here remains pure until ``execute_candidate_promotion`` calls explicit read,
atomic workspace and local Git commit ports.  That execution re-observes every reviewed baseline,
replans, validates before writing, validates the persisted readback, commits only reviewed paths
and has no push capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_artifacts.application.candidate_validation import (
    CandidateValidation,
    ValidationOutcome,
    validate_candidate,
)
from agent_artifacts.application.maintainer import CandidateBundle
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.application.promotion import (
    PromotionApplyReceipt,
    PromotionEvidence,
    PromotionOutputPort,
    PromotionPlan,
    finalize_promotion,
    load_registry_promotions,
    load_registry_versions,
    plan_bulk_promotion,
    project_promotion,
    validate_promoted_registry,
)
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.candidates import CandidateId, CandidateState, assess_candidate
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import SourceAlias, source_revision_kind
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.serialization import canonical_json_bytes
from agent_artifacts.protocol.hashing import sha256_bytes
from agent_artifacts.protocol.native_tree import SourceSnapshot
from agent_artifacts.protocol.paths import SafeRelativePath
from agent_artifacts.sources.model import source_snapshot_digest
from agent_artifacts.store.model import ObjectDigest

__all__ = [
    "MAINTAINER_PROMOTION_INVALID",
    "CandidatePromotionExecutionResult",
    "CandidatePromotionCommitCommand",
    "CandidatePromotionCommitReceipt",
    "MaintainerCandidatePromotionPorts",
    "PreparedCandidatePromotion",
    "PreparedCandidatePromotionTransaction",
    "execute_candidate_promotion",
    "plan_candidate_promotion",
    "effective_policy_digest",
    "prepare_candidate_promotion",
    "prepare_candidate_promotion_transaction",
    "promotion_commit_subject",
    "promotion_evidence",
    "validation_report_digest",
]

MAINTAINER_PROMOTION_INVALID = DiagnosticCode("maintainer-promotion-invalid")

#: The Candidate states a promotion may act on.  A warning is not blocking by itself; policy says
#: whether it is, and it has already said so by the time a run reaches here.
_PROMOTABLE = frozenset({CandidateState.READY, CandidateState.WARNING})


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (
            Diagnostic(
                MAINTAINER_PROMOTION_INVALID,
                Severity.ERROR,
                redact_text(message),
                remediation=tuple(redact_text(item) for item in remediation),
            ),
        )
    )


def validation_report_digest(validation: CandidateValidation) -> ObjectDigest:
    """Digest the run itself, so an audit names the evidence rather than describing it.

    Every check appears, in pipeline order, with its outcome and its details.  A run that reached a
    different conclusion, or reached the same conclusion for different reasons, digests differently.
    """

    if not isinstance(validation, CandidateValidation):
        raise ValueError("a validation report digest needs a validation run")
    return sha256_bytes(
        canonical_json_bytes(
            {
                "candidate": validation.candidate_id.value,
                "checks": [
                    {
                        "check": result.check.value,
                        "details": [
                            {
                                "declared": detail.declared,
                                "expected": detail.expected,
                                "message": detail.message,
                                "path": detail.path,
                            }
                            for detail in result.details
                        ],
                        "outcome": result.outcome.value,
                    }
                    for result in validation.results
                ],
                "report": "candidate-validation",
                "required_checks": sorted(validation.required_checks),
                "state": validation.state.value,
            }
        )
    )


def effective_policy_digest(policy: EffectivePolicy) -> ObjectDigest:
    """Digest the rules a promotion was judged against, distinguishing unset from empty.

    A `None` allowlist and an empty one are different policies -- one permits everything, the other
    nothing -- so they must not collapse to the same digest.
    """

    if not isinstance(policy, EffectivePolicy):
        raise ValueError("an effective policy digest needs an effective policy")
    return sha256_bytes(
        canonical_json_bytes(
            {
                "allowed_credential_providers": _set(policy.allowed_credential_providers),
                "allowed_network_hosts": _set(policy.allowed_network_hosts),
                "allowed_python_installers": _set(policy.allowed_python_installers),
                "allowed_registries": _set(policy.allowed_registries),
                "allowed_runtimes": _set(policy.allowed_runtimes),
                "allowed_secret_bindings": _set(policy.allowed_secret_bindings),
                "allowed_transports": _set(policy.allowed_transports),
                "forbidden_effects": _set(policy.forbidden_effects),
                "forbidden_persisted_config": _set(policy.forbidden_persisted_config),
                "interactive_remediation": policy.interactive_remediation,
                "policy": "effective-policy",
                "required_checks": _set(policy.required_checks),
                "risk_ceiling": policy.risk_ceiling.name,
            }
        )
    )


def _set(values: frozenset[str] | None) -> list[str] | None:
    return None if values is None else sorted(values)


def promotion_evidence(
    validation: CandidateValidation,
    policy: EffectivePolicy,
) -> Result[PromotionEvidence]:
    """The evidence record a promotion audit keeps: which run, which policy, which warnings."""

    try:
        return Ok(
            PromotionEvidence(
                validation_report_digest(validation),
                effective_policy_digest(policy),
                tuple(
                    result.check.value + ": " + detail.message
                    for result in validation.results
                    if result.outcome is ValidationOutcome.WARNING
                    for detail in result.details
                ),
            )
        )
    except ValueError as error:
        return _error(f"promotion evidence is invalid: {error}")


@dataclass(frozen=True, slots=True)
class PreparedCandidatePromotion:
    """One Candidate, the run that judged it and the registry baseline, bound into one review."""

    candidate: CandidateBundle
    observed: CandidateBundle
    validation: CandidateValidation
    policy: EffectivePolicy
    approved: ApprovedRegistryState
    mode: PromotionMode
    evidence: PromotionEvidence
    review_digest: ObjectDigest = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate, CandidateBundle)
            or not isinstance(self.observed, CandidateBundle)
            or not isinstance(self.validation, CandidateValidation)
            or not isinstance(self.policy, EffectivePolicy)
            or not isinstance(self.approved, ApprovedRegistryState)
            or not isinstance(self.mode, PromotionMode)
            or not isinstance(self.evidence, PromotionEvidence)
            or self.validation.candidate_id != self.candidate.candidate.id
            or self.observed.candidate.id != self.candidate.candidate.id
            or self.observed.artifact != self.candidate.artifact
        ):
            raise ValueError("prepared Candidate promotion is invalid")
        object.__setattr__(self, "review_digest", _review_digest(self))

    @property
    def state(self) -> CandidateState:
        """What the run concluded, which is what promotion acts on."""

        return self.validation.state

    @property
    def target_registry(self) -> SourceAlias:
        return self.candidate.candidate.target_registry


def _review_digest(prepared: PreparedCandidatePromotion) -> ObjectDigest:
    candidate = prepared.candidate.candidate
    return sha256_bytes(
        canonical_json_bytes(
            {
                "approved_registry": {
                    "alias": prepared.approved.alias.value,
                    "revision": prepared.approved.revision,
                    "snapshot_digest": str(prepared.approved.snapshot_digest),
                    "versions": sorted(str(item.coordinate) for item in prepared.approved.versions),
                },
                "candidate": {
                    "canonical_digest": str(candidate.canonical_digest),
                    "coordinate": str(candidate.artifact.coordinate),
                    "id": candidate.id.value,
                    "payload_digest": str(candidate.artifact.payload_digest),
                    "source_revision": candidate.artifact.provenance.revision,
                    "state": prepared.state.value,
                    "observed_state": prepared.observed.candidate.state.value,
                },
                "evidence": {
                    "effective_policy_digest": str(prepared.evidence.effective_policy_digest),
                    "validation_report_digest": str(prepared.evidence.validation_report_digest),
                },
                "mode": prepared.mode.value,
                "operation": "candidate-promotion",
            }
        )
    )


def prepare_candidate_promotion(
    bundle: CandidateBundle,
    validation: CandidateValidation,
    policy: EffectivePolicy,
    approved: ApprovedRegistryState,
    *,
    mode: PromotionMode = PromotionMode.VENDORED,
) -> Result[PreparedCandidatePromotion]:
    """Bind one reviewed Candidate into a confirmable promotion, or say why it cannot be one."""

    if (
        not isinstance(bundle, CandidateBundle)
        or not isinstance(validation, CandidateValidation)
        or not isinstance(policy, EffectivePolicy)
        or not isinstance(approved, ApprovedRegistryState)
        or not isinstance(mode, PromotionMode)
    ):
        return _error("preparing a promotion needs a Candidate, its run, a policy and a baseline")
    candidate = bundle.candidate
    if validation.candidate_id != candidate.id:
        return _error("the validation run under review judged a different Candidate")
    if candidate.target_registry != approved.alias:
        return _error(
            f"Candidate targets registry {candidate.target_registry.value}, "
            f"not {approved.alias.value}",
            "Open the promotion from the registry the Candidate was scanned for.",
        )
    # The run decides, not the state the scan recorded: policy may have changed since, and the run
    # is what the Maintainer was actually shown on screens 38 to 40.
    if validation.state is CandidateState.INVALID:
        return _error(
            "Candidate is invalid under this policy and cannot be promoted",
            "Screen 39 names each failing check and what it expected.",
        )
    if validation.state is CandidateState.APPROVAL_REQUIRED:
        return _error(
            "policy requires manual approval before this Candidate can be promoted",
            "Screen 40 lists the required checks this run did not pass.",
        )
    if validation.state not in _PROMOTABLE or candidate.state is CandidateState.INVALID:
        return _error("Candidate is not in a promotable state")
    evidence = promotion_evidence(validation, policy)
    if isinstance(evidence, Err):
        return evidence
    # The Candidate a promotion acts on is the one the run leaves behind, not the one the scan
    # recorded before any policy had judged it: a scan writes `new`, and what makes a Candidate
    # promotable is the run screens 38 to 40 showed.
    reviewed = CandidateBundle(
        assess_candidate(
            candidate,
            findings=validation.findings,
            manual_approval_required=validation.manual_approval_required,
        ),
        bundle.artifact,
    )
    try:
        return Ok(
            PreparedCandidatePromotion(
                reviewed,
                bundle,
                validation,
                policy,
                approved,
                mode,
                evidence.value,
            )
        )
    except ValueError as error:
        return _error(f"prepared Candidate promotion is invalid: {error}")


def plan_candidate_promotion(
    prepared: PreparedCandidatePromotion,
    registry_snapshot: SourceSnapshot,
) -> Result[PromotionPlan]:
    """Plan the one transaction a confirmed review would apply, writing nothing.

    The evidence the review bound travels into the plan's audit records, so what the registry ends
    up recording names the run that approved it rather than a fresh one taken at write time.
    """

    if not isinstance(prepared, PreparedCandidatePromotion) or not isinstance(
        registry_snapshot, SourceSnapshot
    ):
        return _error("planning a promotion needs a reviewed promotion and a registry workspace")
    # A promotion audit records a Git revision, and a local Source carries `local:<snapshot>`
    # (D-096). Promoting one through the Git-only record would either fail deep inside the planner
    # or, worse, disguise a local origin as a commit, so it is refused here by name.
    revision = prepared.candidate.candidate.artifact.provenance.revision
    if source_revision_kind(revision) != "git":
        return _error(
            "a Candidate from a local Source cannot be promoted yet: the promotion audit record "
            "has no place for local provenance",
            "Promote from a Git-backed authoring Source, or wait for local promotion to land.",
        )
    return plan_bulk_promotion(
        registry_snapshot,
        (prepared.candidate,),
        evidence=((prepared.candidate.candidate.id, prepared.evidence),),
        approved=prepared.approved.versions,
        mode=prepared.mode,
    )


@dataclass(frozen=True, slots=True)
class PreparedCandidatePromotionTransaction:
    """The exact projected and validated registry transaction screens 43–45 review."""

    promotion: PreparedCandidatePromotion
    plan: PromotionPlan
    projected: SourceSnapshot
    registry_snapshot: ObjectDigest
    approved_version_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.promotion, PreparedCandidatePromotion)
            or not isinstance(self.plan, PromotionPlan)
            or not isinstance(self.projected, SourceSnapshot)
            or not isinstance(self.registry_snapshot, ObjectDigest)
            or not isinstance(self.approved_version_count, int)
            or isinstance(self.approved_version_count, bool)
            or self.approved_version_count < 1
            or self.plan.mode is not self.promotion.mode
            or self.plan.next_registry_snapshot != self.registry_snapshot
            or len(self.plan.audits) != 1
            or self.plan.audits[0].candidate_id != self.promotion.candidate.candidate.id
        ):
            raise ValueError("prepared Candidate promotion transaction is invalid")

    @property
    def review_digest(self) -> ObjectDigest:
        """The transaction digest screen 43 showed and screen 45 must confirm."""

        return self.plan.review_digest


def _project_and_validate(
    promotion: PreparedCandidatePromotion,
    plan: PromotionPlan,
    workspace: SourceSnapshot,
) -> Result[PreparedCandidatePromotionTransaction]:
    projected = project_promotion(workspace, plan)
    if isinstance(projected, Err):
        return projected
    versions = load_registry_versions(projected.value)
    if isinstance(versions, Err):
        return versions
    audits = load_registry_promotions(projected.value)
    if isinstance(audits, Err):
        return audits
    by_candidate = {item.candidate_id: item for item in audits.value}
    if any(by_candidate.get(item.candidate_id) != item for item in plan.audits):
        return _error("promoted registry provenance does not match the reviewed transaction")
    validated = validate_promoted_registry(projected.value, versions.value)
    if isinstance(validated, Err):
        return validated
    try:
        return Ok(
            PreparedCandidatePromotionTransaction(
                promotion,
                plan,
                projected.value,
                validated.value,
                len(versions.value),
            )
        )
    except ValueError as error:
        return _error(f"prepared promotion transaction is invalid: {error}")


def prepare_candidate_promotion_transaction(
    bundle: CandidateBundle,
    validation: CandidateValidation,
    policy: EffectivePolicy,
    approved: ApprovedRegistryState,
    registry_workspace: SourceSnapshot,
    *,
    mode: PromotionMode = PromotionMode.VENDORED,
) -> Result[PreparedCandidatePromotionTransaction]:
    """Plan and validate the exact inert registry state screens 43–45 will review."""

    if not isinstance(registry_workspace, SourceSnapshot):
        return _error("preparing a promotion transaction needs a registry workspace")
    workspace_digest = source_snapshot_digest(registry_workspace)
    if isinstance(workspace_digest, Err):
        return workspace_digest
    if workspace_digest.value != approved.snapshot_digest:
        return _error(
            "registry workspace does not match the synchronized approved baseline",
            "synchronize or restore the registry checkout, then review promotion again",
        )
    prepared = prepare_candidate_promotion(
        bundle,
        validation,
        policy,
        approved,
        mode=mode,
    )
    if isinstance(prepared, Err):
        return prepared
    planned = plan_candidate_promotion(prepared.value, registry_workspace)
    if isinstance(planned, Err):
        return planned
    return _project_and_validate(prepared.value, planned.value, registry_workspace)


ReadCandidatePort = Callable[[CandidateId], Result[CandidateBundle]]
ReadApprovedRegistryPort = Callable[[SourceAlias], Result[ApprovedRegistryState]]


@dataclass(frozen=True, slots=True)
class CandidatePromotionCommitCommand:
    """The reviewed paths and subject an explicit local Git commit may contain."""

    review_digest: ObjectDigest
    subject: str
    paths: tuple[SafeRelativePath, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.review_digest, ObjectDigest)
            or not isinstance(self.subject, str)
            or not self.subject
            or self.subject != self.subject.strip()
            or any(character in self.subject for character in "\r\n")
            or not isinstance(self.paths, tuple)
            or not self.paths
            or any(not isinstance(item, SafeRelativePath) for item in self.paths)
            or len(set(self.paths)) != len(self.paths)
        ):
            raise ValueError("Candidate promotion commit command is invalid")
        object.__setattr__(self, "paths", tuple(sorted(self.paths)))


@dataclass(frozen=True, slots=True)
class CandidatePromotionCommitReceipt:
    """The local Git revision created for an exact promotion; push is structurally absent."""

    review_digest: ObjectDigest
    revision: str
    subject: str
    paths: tuple[SafeRelativePath, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.review_digest, ObjectDigest)
            or source_revision_kind(self.revision) != "git"
            or not isinstance(self.subject, str)
            or not self.subject
            or self.subject != self.subject.strip()
            or any(character in self.subject for character in "\r\n")
            or not isinstance(self.paths, tuple)
            or not self.paths
            or any(not isinstance(item, SafeRelativePath) for item in self.paths)
            or len(set(self.paths)) != len(self.paths)
        ):
            raise ValueError("Candidate promotion commit receipt is invalid")
        object.__setattr__(self, "paths", tuple(sorted(self.paths)))


CommitPromotionPort = Callable[
    [CandidatePromotionCommitCommand], Result[CandidatePromotionCommitReceipt]
]


def promotion_commit_subject(prepared: PreparedCandidatePromotionTransaction) -> str:
    """The deterministic one-line subject screen 45 reviews and the Git port must use."""

    if not isinstance(prepared, PreparedCandidatePromotionTransaction):
        raise ValueError("promotion commit subject needs a prepared transaction")
    candidate = prepared.promotion.candidate.candidate
    return (
        f"Promote {candidate.artifact.coordinate.artifact}@"
        f"{candidate.artifact.coordinate.version} to {candidate.target_registry}"
    )


@dataclass(frozen=True, slots=True)
class MaintainerCandidatePromotionPorts:
    """Every observation and the one atomic output used by confirmed promotion."""

    read_candidate: ReadCandidatePort
    read_approved: ReadApprovedRegistryPort
    output: PromotionOutputPort
    commit: CommitPromotionPort


@dataclass(frozen=True, slots=True)
class CandidatePromotionExecutionResult:
    """Verified persisted registry evidence from one locally applied promotion."""

    review_digest: ObjectDigest
    registry_snapshot: ObjectDigest
    workspace_digest: ObjectDigest
    changed_paths: int
    approved_version_count: int
    commit_revision: str
    commit_subject: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.review_digest, ObjectDigest)
            or not isinstance(self.registry_snapshot, ObjectDigest)
            or not isinstance(self.workspace_digest, ObjectDigest)
            or not isinstance(self.changed_paths, int)
            or isinstance(self.changed_paths, bool)
            or self.changed_paths < 0
            or not isinstance(self.approved_version_count, int)
            or isinstance(self.approved_version_count, bool)
            or self.approved_version_count < 1
            or source_revision_kind(self.commit_revision) != "git"
            or not isinstance(self.commit_subject, str)
            or not self.commit_subject
            or self.commit_subject != self.commit_subject.strip()
            or any(character in self.commit_subject for character in "\r\n")
        ):
            raise ValueError("Candidate promotion execution result is invalid")


def execute_candidate_promotion(
    prepared: PreparedCandidatePromotionTransaction,
    reviewed_digest: ObjectDigest,
    ports: MaintainerCandidatePromotionPorts,
) -> Result[CandidatePromotionExecutionResult]:
    """Re-observe, replan and atomically apply exactly one reviewed promotion.

    Validation happens over the projected registry before the first write. The atomic output then
    performs its own locked current-state check, and the persisted tree is read and validated once
    more before success is reported. Publication and Git push remain outside this operation.
    """

    if (
        not isinstance(prepared, PreparedCandidatePromotionTransaction)
        or not isinstance(reviewed_digest, ObjectDigest)
        or not isinstance(ports, MaintainerCandidatePromotionPorts)
    ):
        return _error("executing promotion needs one prepared transaction and typed ports")
    if reviewed_digest != prepared.review_digest:
        return _error(
            "confirmed promotion digest does not match the reviewed registry transaction",
            "review the current registry transaction again",
        )

    candidate_id = prepared.promotion.observed.candidate.id
    current_candidate = ports.read_candidate(candidate_id)
    if isinstance(current_candidate, Err):
        return current_candidate
    if current_candidate.value != prepared.promotion.observed:
        return _error(
            "Candidate changed after promotion review",
            "validate and review the current Candidate again",
        )

    current_approved = ports.read_approved(prepared.promotion.target_registry)
    if isinstance(current_approved, Err):
        return current_approved
    if current_approved.value != prepared.promotion.approved:
        return _error(
            "approved registry baseline changed after promotion review",
            "review promotion again against the current approved registry",
        )

    current_workspace = ports.output.current()
    if isinstance(current_workspace, Err):
        return current_workspace
    validation = validate_candidate(
        current_candidate.value,
        policy=prepared.promotion.policy,
    )
    current_promotion = prepare_candidate_promotion(
        current_candidate.value,
        validation,
        prepared.promotion.policy,
        current_approved.value,
        mode=prepared.promotion.mode,
    )
    if isinstance(current_promotion, Err):
        return current_promotion
    if current_promotion.value.review_digest != prepared.promotion.review_digest:
        return _error(
            "Candidate validation or policy result changed after promotion review",
            "review the current Candidate and policy again",
        )
    replanned = plan_candidate_promotion(current_promotion.value, current_workspace.value)
    if isinstance(replanned, Err):
        return replanned
    if replanned.value.review_digest != prepared.plan.review_digest:
        return _error(
            "registry workspace changed after the transaction was reviewed",
            "review the current registry transaction again",
        )
    revalidated = _project_and_validate(
        current_promotion.value,
        replanned.value,
        current_workspace.value,
    )
    if isinstance(revalidated, Err):
        return revalidated
    if revalidated.value != prepared:
        return _error(
            "promoted registry validation changed after review",
            "review the current promoted registry again",
        )

    applied = finalize_promotion(replanned.value, reviewed_digest, output=ports.output)
    if isinstance(applied, Err):
        return applied
    persisted = ports.output.current()
    if isinstance(persisted, Err):
        return persisted
    persisted_workspace = source_snapshot_digest(persisted.value)
    if isinstance(persisted_workspace, Err):
        return persisted_workspace
    versions = load_registry_versions(persisted.value)
    if isinstance(versions, Err):
        return versions
    audits = load_registry_promotions(persisted.value)
    if isinstance(audits, Err):
        return audits
    persisted_audits = {item.candidate_id: item for item in audits.value}
    if any(persisted_audits.get(item.candidate_id) != item for item in replanned.value.audits):
        return _error("persisted registry provenance does not match the reviewed promotion")
    validated = validate_promoted_registry(persisted.value, versions.value)
    if isinstance(validated, Err):
        return validated
    receipt: PromotionApplyReceipt = applied.value
    if (
        persisted_workspace.value != receipt.workspace_digest
        or persisted_workspace.value != prepared.plan.next_workspace_digest
        or validated.value != receipt.registry_snapshot
        or len(versions.value) != prepared.approved_version_count
    ):
        return _error("persisted registry does not match the validated promotion result")
    commit_command = CandidatePromotionCommitCommand(
        prepared.review_digest,
        promotion_commit_subject(prepared),
        tuple(item.path for item in prepared.plan.changes if item.kind.value != "unchanged"),
    )
    committed = ports.commit(commit_command)
    if isinstance(committed, Err):
        return Err(
            (
                Diagnostic(
                    MAINTAINER_PROMOTION_INVALID,
                    Severity.ERROR,
                    "approved registry state was written and validated, but its local Git commit "
                    "failed; the reviewed changes remain in the checkout",
                    remediation=(
                        "inspect Git status, repair the commit failure, and commit the reviewed "
                        "paths without pushing",
                    ),
                ),
                *committed.diagnostics,
            )
        )
    if (
        committed.value.review_digest != commit_command.review_digest
        or committed.value.subject != commit_command.subject
        or committed.value.paths != commit_command.paths
    ):
        return _error("local Git commit does not match the reviewed registry transaction")
    try:
        return Ok(
            CandidatePromotionExecutionResult(
                receipt.review_digest,
                receipt.registry_snapshot,
                receipt.workspace_digest,
                receipt.changed_paths,
                len(versions.value),
                committed.value.revision,
                committed.value.subject,
            )
        )
    except ValueError as error:
        return _error(f"promotion result is invalid: {error}")
