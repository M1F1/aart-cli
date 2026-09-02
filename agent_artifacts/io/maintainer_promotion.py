"""Concrete configured composition for reviewed Candidate promotion."""

from __future__ import annotations

import os
from dataclasses import dataclass

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.maintainer import CandidateBundle
from agent_artifacts.application.maintainer_promotion import (
    CandidatePromotionCommitCommand,
    CandidatePromotionCommitReceipt,
    CandidatePromotionExecutionResult,
    MaintainerCandidatePromotionPorts,
    PreparedCandidatePromotionTransaction,
    execute_candidate_promotion,
    prepare_candidate_promotion_transaction,
)
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.configuration.policy import EffectiveConfiguration, redact_text
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.git import GitProcessRequest, run_git_process
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)

from .candidate_store import candidate_history_paths, read_candidate_history
from .maintainer_sync import read_approved_registry_state
from .registry_promotion import FilesystemPromotionOutput
from .source_store import read_current_source

MAINTAINER_PROMOTION_CONFIGURATION_INVALID = DiagnosticCode(
    "maintainer-promotion-configuration-invalid"
)


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (
            Diagnostic(
                MAINTAINER_PROMOTION_CONFIGURATION_INVALID,
                Severity.ERROR,
                redact_text(message),
                remediation=tuple(redact_text(item) for item in remediation),
            ),
        )
    )


def _configured_registry(
    effective: EffectiveConfiguration,
    alias: SourceAlias,
) -> ConfiguredSource | None:
    return next(
        (
            item
            for item in effective.configuration.sources
            if item.enabled and item.kind is SourceKind.REGISTRY_GIT and item.alias == alias
        ),
        None,
    )


def _registry_root(root: str, registry: ConfiguredSource) -> Result[str]:
    if not os.path.isabs(root) or os.path.normpath(root) != root:
        return _error(
            f"registry {registry.alias} promotion needs a local checkout as the project root",
            "launch AART from the normalized absolute registry Git checkout",
        )
    return Ok(root)


def _git(root: str, *arguments: str, max_output_bytes: int = 1024 * 1024):
    return run_git_process(
        GitProcessRequest(
            ("git", "-c", "core.hooksPath=/dev/null", "-C", root, *arguments),
            root,
            30,
            max_output_bytes=max_output_bytes,
        )
    )


def _staged_paths(root: str) -> Result[tuple[str, ...]]:
    pending = _git(root, "diff", "--cached", "--name-only", "-z")
    if isinstance(pending, Err):
        return pending
    try:
        return Ok(
            tuple(
                sorted(
                    item.decode("utf-8", errors="strict")
                    for item in pending.value.stdout.split(b"\x00")
                    if item
                )
            )
        )
    except UnicodeDecodeError as error:
        return _error(f"Git index contains an invalid path: {error}")


def commit_candidate_promotion(
    root: str,
    command: CandidatePromotionCommitCommand,
) -> Result[CandidatePromotionCommitReceipt]:
    """Stage only reviewed registry paths, create one local commit and never push."""

    if (
        not isinstance(root, str)
        or not os.path.isabs(root)
        or os.path.normpath(root) != root
        or not isinstance(command, CandidatePromotionCommitCommand)
    ):
        return _error("committing promotion needs a local root and reviewed command")
    paths = tuple(str(item) for item in command.paths)
    existing = _staged_paths(root)
    if isinstance(existing, Err):
        return existing
    if existing.value:
        return _error(
            "Git index already contains changes outside this promotion commit",
            "commit, restore or unstage existing changes, then review promotion again",
        )
    for offset in range(0, len(paths), 256):
        staged = _git(root, "add", "-A", "--", *paths[offset : offset + 256])
        if isinstance(staged, Err):
            return staged
    staged_paths = _staged_paths(root)
    if isinstance(staged_paths, Err):
        return staged_paths
    if staged_paths.value != tuple(sorted(paths)):
        return _error(
            "Git index contains changes outside the reviewed promotion",
            "commit, restore or unstage unrelated changes, then review promotion again",
        )
    committed = _git(root, "commit", "-m", command.subject)
    if isinstance(committed, Err):
        return committed
    revision = _git(root, "rev-parse", "--verify", "HEAD", max_output_bytes=128)
    if isinstance(revision, Err):
        return revision
    try:
        return Ok(
            CandidatePromotionCommitReceipt(
                command.review_digest,
                revision.value.stdout.decode("ascii", errors="strict").strip(),
                command.subject,
                command.paths,
            )
        )
    except (UnicodeDecodeError, ValueError) as error:
        return _error(f"local promotion commit is invalid: {error}")


def read_configured_candidate(
    effective: EffectiveConfiguration,
    candidate_id: CandidateId,
    *,
    data_root: str,
) -> Result[CandidateBundle]:
    """Read one active Candidate from history that still binds its current Source revision."""

    if (
        not isinstance(effective, EffectiveConfiguration)
        or not isinstance(candidate_id, CandidateId)
        or not isinstance(data_root, str)
    ):
        return _error("reading a configured Candidate needs configuration, an ID and data root")
    found: list[CandidateBundle] = []
    for source in effective.configuration.sources:
        if not source.enabled or source.kind is SourceKind.REGISTRY_GIT:
            continue
        paths = source_store_paths(data_root, source_instance_id(source))
        current = read_current_source(CurrentSourceRequest(paths, source.alias))
        if isinstance(current, Err):
            return current
        history = read_candidate_history(candidate_history_paths(paths))
        if isinstance(history, Err):
            return history
        if history.value is None:
            continue
        if (
            current.value is None
            or history.value.source_alias != source.alias
            or history.value.revision != current.value.candidate.resolved_revision
        ):
            return _error(
                f"Candidate history for Source {source.alias} does not bind its current revision",
                "synchronize the Source and review the current Candidate again",
            )
        found.extend(item for item in history.value.active if item.candidate.id == candidate_id)
    if len(found) != 1:
        return _error(
            f"active Candidate {candidate_id} is not uniquely available",
            "open Candidates and review one active Candidate again",
        )
    return Ok(found[0])


@dataclass(frozen=True, slots=True)
class PreparedConfiguredCandidatePromotion:
    transaction: PreparedCandidatePromotionTransaction
    registry_root: str
    data_root: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.transaction, PreparedCandidatePromotionTransaction)
            or not os.path.isabs(self.registry_root)
            or os.path.normpath(self.registry_root) != self.registry_root
            or not os.path.isabs(self.data_root)
            or os.path.normpath(self.data_root) != self.data_root
        ):
            raise ValueError("configured Candidate promotion is invalid")

    @property
    def review_digest(self) -> ObjectDigest:
        return self.transaction.review_digest


def prepare_configured_candidate_promotion(
    effective: EffectiveConfiguration,
    candidate_id: CandidateId,
    *,
    data_root: str,
    registry_root: str,
    policy: EffectivePolicy,
    mode: PromotionMode,
) -> Result[PreparedConfiguredCandidatePromotion]:
    """Re-observe and pre-validate the exact local registry transaction to confirm."""

    if (
        not isinstance(effective, EffectiveConfiguration)
        or not isinstance(candidate_id, CandidateId)
        or not isinstance(policy, EffectivePolicy)
        or not isinstance(mode, PromotionMode)
        or not os.path.isabs(data_root)
        or os.path.normpath(data_root) != data_root
    ):
        return _error("preparing configured promotion needs typed configuration and local state")
    candidate = read_configured_candidate(effective, candidate_id, data_root=data_root)
    if isinstance(candidate, Err):
        return candidate
    target = candidate.value.candidate.target_registry
    registry = _configured_registry(effective, target)
    if registry is None:
        return _error(f"target registry {target} is not configured and enabled")
    root = _registry_root(registry_root, registry)
    if isinstance(root, Err):
        return root
    approved = read_approved_registry_state(effective, target, data_root=data_root)
    if isinstance(approved, Err):
        return approved
    output = FilesystemPromotionOutput(root.value)
    workspace = output.current()
    if isinstance(workspace, Err):
        return workspace
    validation = validate_candidate(candidate.value, policy=policy)
    transaction = prepare_candidate_promotion_transaction(
        candidate.value,
        validation,
        policy,
        approved.value,
        workspace.value,
        mode=mode,
    )
    if isinstance(transaction, Err):
        return transaction
    try:
        return Ok(PreparedConfiguredCandidatePromotion(transaction.value, root.value, data_root))
    except ValueError as error:
        return _error(str(error))


def complete_configured_candidate_promotion(
    effective: EffectiveConfiguration,
    prepared: PreparedConfiguredCandidatePromotion,
    *,
    reviewed_digest: ObjectDigest,
    registry_root: str,
) -> Result[CandidatePromotionExecutionResult]:
    """Execute a reviewed promotion against the same configured local registry checkout."""

    if not isinstance(effective, EffectiveConfiguration) or not isinstance(
        prepared, PreparedConfiguredCandidatePromotion
    ):
        return _error("completing configured promotion needs configuration and a prepared review")
    target = prepared.transaction.target_registry
    registry = _configured_registry(effective, target)
    if registry is None:
        return _error(f"target registry {target} is no longer configured and enabled")
    root = _registry_root(registry_root, registry)
    if isinstance(root, Err):
        return root
    if root.value != prepared.registry_root:
        return _error(
            "configured registry checkout changed after promotion review",
            "review promotion again against the current registry checkout",
        )

    def read_candidate(candidate_id: CandidateId) -> Result[CandidateBundle]:
        return read_configured_candidate(
            effective,
            candidate_id,
            data_root=prepared.data_root,
        )

    def read_approved(alias: SourceAlias):
        return read_approved_registry_state(
            effective,
            alias,
            data_root=prepared.data_root,
        )

    return execute_candidate_promotion(
        prepared.transaction,
        reviewed_digest,
        MaintainerCandidatePromotionPorts(
            read_candidate,
            read_approved,
            FilesystemPromotionOutput(prepared.registry_root),
            lambda command: commit_candidate_promotion(prepared.registry_root, command),
        ),
    )


__all__ = [
    "MAINTAINER_PROMOTION_CONFIGURATION_INVALID",
    "PreparedConfiguredCandidatePromotion",
    "complete_configured_candidate_promotion",
    "commit_candidate_promotion",
    "prepare_configured_candidate_promotion",
    "read_configured_candidate",
]
