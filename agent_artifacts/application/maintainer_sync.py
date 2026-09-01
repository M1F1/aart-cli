"""Reviewed Source Sync through one Source lease and explicit persistence ports.

Preparation is a pure observation: it binds configured Source identity, the current published
snapshot, durable Candidate history and one approved target-registry snapshot into a review digest.
Execution rechecks those observations before acquisition, then keeps Source publication, exact
manifest compilation, Candidate reconciliation, atomic history publication and readback inside the
configured Source instance lease. Registry state is read-only input throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_artifacts.application.candidate_history import serialize_source_scan
from agent_artifacts.application.maintainer import SourceScan, reconcile_source_scan
from agent_artifacts.application.sources import (
    SourceSyncPorts,
    SourceSyncRequest,
    sync_source_while_locked,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import (
    ObjectDigest,
    SourceAlias,
    SourceId,
    source_revision_kind,
)
from agent_artifacts.domain.registry import RegistryArtifactVersion
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.serialization import canonical_json_bytes
from agent_artifacts.protocol.authoring import CompiledAuthorArtifact
from agent_artifacts.protocol.hashing import sha256_bytes
from agent_artifacts.protocol.native_tree import SourceSnapshot
from agent_artifacts.sources.model import (
    CurrentSource,
    CurrentSourceRequest,
    SourceLockRequest,
    SourceStorePaths,
    SourceSyncOutcome,
    source_instance_id,
    source_store_paths,
)

ReadCandidateHistoryPort = Callable[[SourceStorePaths], Result[SourceScan | None]]
WriteCandidateHistoryPort = Callable[[SourceStorePaths, SourceScan], Result[None]]
ReadApprovedRegistryPort = Callable[[SourceAlias], Result["ApprovedRegistryState"]]
CompileAuthorSnapshotPort = Callable[
    [SourceSnapshot, SourceAlias, str, str], Result[tuple[CompiledAuthorArtifact, ...]]
]

SOURCE_SYNC_INVALID = DiagnosticCode("maintainer-source-sync-invalid")


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (
            Diagnostic(
                SOURCE_SYNC_INVALID,
                Severity.ERROR,
                redact_text(message),
                remediation=tuple(redact_text(item) for item in remediation),
            ),
        )
    )


def _valid_digest(value: ObjectDigest) -> bool:
    return (
        isinstance(value, ObjectDigest)
        and value.algorithm == "sha256"
        and len(value.value) == 64
        and all(character in "0123456789abcdef" for character in value.value)
    )


@dataclass(frozen=True, slots=True)
class ApprovedRegistryState:
    """Exact approved registry observation Source Sync may compare Candidates against."""

    alias: SourceAlias
    revision: str
    snapshot_digest: ObjectDigest
    versions: tuple[RegistryArtifactVersion, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.alias, SourceAlias)
            or not self.alias.value
            or source_revision_kind(self.revision) != "git"
            or not _valid_digest(self.snapshot_digest)
            or not isinstance(self.versions, tuple)
            or any(
                not isinstance(item, RegistryArtifactVersion)
                or item.coordinate.source != self.alias
                for item in self.versions
            )
            or len({item.coordinate for item in self.versions}) != len(self.versions)
        ):
            raise ValueError("approved registry state is invalid")
        object.__setattr__(
            self,
            "versions",
            tuple(sorted(self.versions, key=lambda item: str(item.coordinate))),
        )


@dataclass(frozen=True, slots=True)
class SourceSyncBaseline:
    """The Source/Candidate observation somebody reviewed before confirming acquisition."""

    revision: str | None
    snapshot_digest: ObjectDigest | None
    declared_source_id: SourceId | None
    history_digest: ObjectDigest | None
    candidate_count: int

    def __post_init__(self) -> None:
        current = (self.revision, self.snapshot_digest, self.declared_source_id)
        if (
            not (all(item is None for item in current) or all(item is not None for item in current))
            or (self.revision is not None and source_revision_kind(self.revision) is None)
            or not (
                self.declared_source_id is None or isinstance(self.declared_source_id, SourceId)
            )
            or not (self.snapshot_digest is None or _valid_digest(self.snapshot_digest))
            or not (self.history_digest is None or _valid_digest(self.history_digest))
            or not isinstance(self.candidate_count, int)
            or isinstance(self.candidate_count, bool)
            or self.candidate_count < 0
        ):
            raise ValueError("Source Sync baseline is invalid")


def _baseline(
    current: CurrentSource | None,
    history: SourceScan | None,
) -> Result[SourceSyncBaseline]:
    if history is not None and (
        current is None
        or history.source_alias != current.candidate.alias
        or history.revision != current.candidate.resolved_revision
    ):
        return _error("Candidate history does not bind the current configured Source snapshot")
    history_digest = None
    if history is not None:
        serialized = serialize_source_scan(history)
        if isinstance(serialized, Err):
            return serialized
        history_digest = sha256_bytes(serialized.value.index)
    return Ok(
        SourceSyncBaseline(
            None if current is None else current.candidate.resolved_revision,
            None if current is None else current.candidate.snapshot_digest,
            None if current is None else current.declared_source_id,
            history_digest,
            0 if history is None else len(history.active),
        )
    )


def _review_digest(
    request: SourceSyncRequest,
    baseline: SourceSyncBaseline,
    approved: ApprovedRegistryState,
) -> ObjectDigest:
    source = request.source
    return sha256_bytes(
        canonical_json_bytes(
            {
                "approved_registry": {
                    "alias": approved.alias.value,
                    "revision": approved.revision,
                    "snapshot_digest": str(approved.snapshot_digest),
                },
                "baseline": {
                    "candidate_count": baseline.candidate_count,
                    "declared_source_id": (
                        None
                        if baseline.declared_source_id is None
                        else baseline.declared_source_id.value
                    ),
                    "history_digest": (
                        None if baseline.history_digest is None else str(baseline.history_digest)
                    ),
                    "revision": baseline.revision,
                    "snapshot_digest": (
                        None if baseline.snapshot_digest is None else str(baseline.snapshot_digest)
                    ),
                },
                "operation": "source-sync",
                "runtime": {
                    "available_capabilities": sorted(
                        item.value for item in request.available_capabilities
                    ),
                    "data_root": request.data_root,
                    "executable_version": str(request.executable_version),
                    "fallback": request.fallback.value,
                    "limits": {
                        "max_depth": request.limits.max_depth,
                        "max_file_bytes": request.limits.max_file_bytes,
                        "max_files": request.limits.max_files,
                        "max_total_bytes": request.limits.max_total_bytes,
                    },
                    "offline": request.offline,
                },
                "source": {
                    "alias": source.alias.value,
                    "enabled": source.enabled,
                    "kind": source.kind.value,
                    "location": source.location,
                    "ref": source.ref,
                },
            }
        )
    )


@dataclass(frozen=True, slots=True)
class PreparedSourceSync:
    request: SourceSyncRequest
    baseline: SourceSyncBaseline
    approved: ApprovedRegistryState
    review_digest: ObjectDigest = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request, SourceSyncRequest)
            or self.request.source.kind is SourceKind.REGISTRY_GIT
            or not isinstance(self.baseline, SourceSyncBaseline)
            or not isinstance(self.approved, ApprovedRegistryState)
        ):
            raise ValueError("prepared Source Sync is invalid")
        object.__setattr__(
            self,
            "review_digest",
            _review_digest(self.request, self.baseline, self.approved),
        )

    @property
    def source_alias(self) -> SourceAlias:
        return self.request.source.alias

    @property
    def target_registry(self) -> SourceAlias:
        return self.approved.alias


@dataclass(frozen=True, slots=True)
class SourceSyncExecutionResult:
    review_digest: ObjectDigest
    source: SourceSyncOutcome
    scan: SourceScan

    def __post_init__(self) -> None:
        if (
            not _valid_digest(self.review_digest)
            or not isinstance(self.source, SourceSyncOutcome)
            or not isinstance(self.scan, SourceScan)
            or self.scan.registry_mutations
            or self.scan.source_alias != self.source.current.candidate.alias
            or self.scan.revision != self.source.current.candidate.resolved_revision
        ):
            raise ValueError("Source Sync execution result is inconsistent")


@dataclass(frozen=True, slots=True)
class MaintainerSourceSyncPorts:
    sync: SourceSyncPorts
    read_history: ReadCandidateHistoryPort
    write_history: WriteCandidateHistoryPort
    read_approved: ReadApprovedRegistryPort
    compile: CompileAuthorSnapshotPort


def prepare_source_sync(
    request: SourceSyncRequest,
    current: CurrentSource | None,
    history: SourceScan | None,
    approved: ApprovedRegistryState,
) -> Result[PreparedSourceSync]:
    """Bind read-only Source, Candidate and Registry state into one confirmable review."""

    if not isinstance(request, SourceSyncRequest) or not isinstance(
        approved, ApprovedRegistryState
    ):
        return _error("preparing Source Sync needs typed Source and registry observations")
    if request.source.kind is SourceKind.REGISTRY_GIT:
        return _error("Source Sync screens act on authoring Sources, not registries")
    if not request.source.enabled:
        return _error("disabled authoring Source cannot be synchronized")
    if current is not None and (
        current.candidate.alias != request.source.alias
        or current.candidate.instance_id != source_instance_id(request.source)
    ):
        return _error("current Source observation belongs to another configured Source instance")
    observed = _baseline(current, history)
    if isinstance(observed, Err):
        return observed
    try:
        return Ok(PreparedSourceSync(request, observed.value, approved))
    except ValueError as error:
        return _error(str(error))


def _release(
    outcome: Result[SourceSyncExecutionResult],
    ports: MaintainerSourceSyncPorts,
    lease,
) -> Result[SourceSyncExecutionResult]:
    released = ports.sync.release_lock(lease)
    if isinstance(released, Err):
        if isinstance(outcome, Err):
            return Err((*outcome.diagnostics, *released.diagnostics))
        return released
    return outcome


def execute_source_sync(
    prepared: PreparedSourceSync,
    reviewed_digest: ObjectDigest,
    ports: MaintainerSourceSyncPorts,
) -> Result[SourceSyncExecutionResult]:
    """Apply exactly one reviewed Source Sync and publish no registry mutation."""

    if (
        not isinstance(prepared, PreparedSourceSync)
        or not isinstance(reviewed_digest, ObjectDigest)
        or not isinstance(ports, MaintainerSourceSyncPorts)
    ):
        return _error("executing Source Sync needs a prepared review and typed ports")
    if reviewed_digest != prepared.review_digest:
        return _error("confirmed Source Sync review does not match the prepared review")

    current_registry = ports.read_approved(prepared.target_registry)
    if isinstance(current_registry, Err):
        return current_registry
    if current_registry.value != prepared.approved:
        return _error(
            "approved target registry changed after Source Sync review",
            "review Source Sync again against the current registry snapshot",
        )

    request = prepared.request
    paths = source_store_paths(request.data_root, source_instance_id(request.source))
    lease = ports.sync.acquire_lock(
        SourceLockRequest(
            paths.lock_directory,
            request.lock_timeout_seconds,
            request.lock_stale_after_seconds,
        )
    )
    if isinstance(lease, Err):
        return lease

    current = ports.sync.read_current(CurrentSourceRequest(paths, request.source.alias))
    if isinstance(current, Err):
        return _release(current, ports, lease.value)
    if current.value is not None and (
        current.value.candidate.alias != request.source.alias
        or current.value.candidate.instance_id != source_instance_id(request.source)
    ):
        return _release(
            _error("current Source observation belongs to another configured Source instance"),
            ports,
            lease.value,
        )
    history = ports.read_history(paths)
    if isinstance(history, Err):
        return _release(history, ports, lease.value)
    observed = _baseline(current.value, history.value)
    if isinstance(observed, Err):
        return _release(observed, ports, lease.value)
    if observed.value != prepared.baseline:
        return _release(
            _error(
                "configured Source or Candidate history changed after Source Sync review",
                "review Source Sync again against the current Source state",
            ),
            ports,
            lease.value,
        )

    synchronized = sync_source_while_locked(request, ports.sync, lease.value)
    if isinstance(synchronized, Err):
        return _release(synchronized, ports, lease.value)
    pinned = synchronized.value.current.candidate
    compiled = ports.compile(
        pinned.snapshot,
        request.source.alias,
        request.source.location,
        pinned.resolved_revision,
    )
    if isinstance(compiled, Err):
        return _release(compiled, ports, lease.value)
    reconciled = reconcile_source_scan(
        request.source.alias,
        pinned.resolved_revision,
        compiled.value,
        previous=() if history.value is None else history.value.history,
        approved=prepared.approved.versions,
        target_registry=prepared.target_registry,
    )
    if isinstance(reconciled, Err):
        return _release(reconciled, ports, lease.value)
    if reconciled.value.registry_mutations:
        return _release(
            _error("Source Sync attempted to produce registry mutations"), ports, lease.value
        )
    written = ports.write_history(paths, reconciled.value)
    if isinstance(written, Err):
        return _release(written, ports, lease.value)
    readback = ports.read_history(paths)
    if isinstance(readback, Err):
        return _release(readback, ports, lease.value)
    if readback.value != reconciled.value:
        return _release(
            _error("persisted Candidate history does not match Source Sync result"),
            ports,
            lease.value,
        )
    result = Ok(
        SourceSyncExecutionResult(
            prepared.review_digest,
            synchronized.value,
            reconciled.value,
        )
    )
    return _release(result, ports, lease.value)


__all__ = [
    "ApprovedRegistryState",
    "MaintainerSourceSyncPorts",
    "PreparedSourceSync",
    "SOURCE_SYNC_INVALID",
    "SourceSyncBaseline",
    "SourceSyncExecutionResult",
    "execute_source_sync",
    "prepare_source_sync",
]
