"""What a Maintainer confirms when promoting one reviewed Candidate into an approved registry.

Promotion is the first Maintainer action that writes approved registry state, so what it records
has to be the review that actually happened.  The evidence it carries is a digest of the validation
run and of the policy that judged it, which is what lets an audit record answer "who approved this,
against which rules" rather than only "this was promoted".

Nothing here writes, reads or plans a registry transaction.  This module binds a Candidate, the run
that judged it and the approved baseline into one value a Maintainer can confirm, and refuses
anything the review already refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_artifacts.application.candidate_validation import (
    CandidateValidation,
    ValidationOutcome,
)
from agent_artifacts.application.maintainer import CandidateBundle
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.application.promotion import (
    PromotionEvidence,
    PromotionPlan,
    plan_bulk_promotion,
)
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.candidates import CandidateState, assess_candidate
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import SourceAlias, source_revision_kind
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.serialization import canonical_json_bytes
from agent_artifacts.protocol.hashing import sha256_bytes
from agent_artifacts.protocol.native_tree import SourceSnapshot
from agent_artifacts.store.model import ObjectDigest

__all__ = [
    "MAINTAINER_PROMOTION_INVALID",
    "PreparedCandidatePromotion",
    "plan_candidate_promotion",
    "effective_policy_digest",
    "prepare_candidate_promotion",
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
    validation: CandidateValidation
    policy: EffectivePolicy
    approved: ApprovedRegistryState
    mode: PromotionMode
    evidence: PromotionEvidence
    review_digest: ObjectDigest = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate, CandidateBundle)
            or not isinstance(self.validation, CandidateValidation)
            or not isinstance(self.policy, EffectivePolicy)
            or not isinstance(self.approved, ApprovedRegistryState)
            or not isinstance(self.mode, PromotionMode)
            or not isinstance(self.evidence, PromotionEvidence)
            or self.validation.candidate_id != self.candidate.candidate.id
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
            PreparedCandidatePromotion(reviewed, validation, policy, approved, mode, evidence.value)
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
