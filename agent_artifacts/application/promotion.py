"""Deterministic reviewed promotion of Candidates into an approved registry snapshot.

The application boundary plans one complete mutation over an inert registry snapshot.  Its output
port can apply that mutation once, but deliberately has no commit, push, merge or publication
operation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol, cast

from agent_artifacts.application.maintainer import CandidateBundle
from agent_artifacts.domain.candidates import (
    CandidateFinding,
    CandidateId,
    CandidateState,
    FindingSeverity,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ArtifactKind,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
    RegistryLifecycle,
    registry_version_from_candidate,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.hashing import (
    file_entry,
    json_digest,
    parse_sha256,
    sha256_bytes,
    tree_digest,
)
from agent_artifacts.protocol.json import JsonArray, JsonObject, canonical_json_bytes, parse_json
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import SafeRelativePath, parse_relative_path
from agent_artifacts.sources.model import source_snapshot_digest
from agent_artifacts.store.model import make_object_candidate

PROMOTION_INVALID = DiagnosticCode("promotion-invalid")
PROMOTION_IMMUTABLE_CONFLICT = DiagnosticCode("promotion-immutable-conflict")
PROMOTION_REVIEW_MISMATCH = DiagnosticCode("promotion-review-mismatch")
PROMOTION_STALE = DiagnosticCode("promotion-stale")
PROMOTION_APPLY_MISMATCH = DiagnosticCode("promotion-apply-mismatch")
_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, ObjectDigest)
        and value.algorithm == "sha256"
        and _HEX_64_RE.fullmatch(value.value) is not None
    )


def _safe_lines(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n")
        for value in values
    ):
        raise ValueError(f"{label} must contain safe non-empty lines")
    return tuple(sorted(set(values)))


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    validation_report_digest: ObjectDigest
    effective_policy_digest: ObjectDigest
    warnings: tuple[str, ...] = ()
    external_audit_reference: str | None = None

    def __post_init__(self) -> None:
        if not _valid_digest(self.validation_report_digest) or not _valid_digest(
            self.effective_policy_digest
        ):
            raise ValueError("promotion evidence requires canonical report digests")
        object.__setattr__(self, "warnings", _safe_lines(self.warnings, "promotion warnings"))
        if self.external_audit_reference is not None and (
            not self.external_audit_reference
            or self.external_audit_reference != self.external_audit_reference.strip()
            or any(character in self.external_audit_reference for character in "\r\n")
        ):
            raise ValueError("external audit reference must be one safe line")


@dataclass(frozen=True, slots=True, order=True)
class PromotionAudit:
    candidate_id: CandidateId
    candidate_digest: ObjectDigest
    source_revision: str
    validation_report_digest: ObjectDigest
    effective_policy_digest: ObjectDigest
    mode: PromotionMode
    registry_snapshot_before: ObjectDigest
    registry_snapshot_after: ObjectDigest
    warnings: tuple[str, ...] = ()
    external_audit_reference: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_id, CandidateId)
            or any(
                not _valid_digest(value)
                for value in (
                    self.candidate_digest,
                    self.validation_report_digest,
                    self.effective_policy_digest,
                    self.registry_snapshot_before,
                    self.registry_snapshot_after,
                )
            )
            or re.fullmatch(r"[0-9a-f]{40}", self.source_revision) is None
            or not isinstance(self.mode, PromotionMode)
        ):
            raise ValueError("promotion audit is invalid")
        object.__setattr__(self, "warnings", _safe_lines(self.warnings, "audit warnings"))
        if self.external_audit_reference is not None and (
            not self.external_audit_reference
            or self.external_audit_reference != self.external_audit_reference.strip()
            or any(character in self.external_audit_reference for character in "\r\n")
        ):
            raise ValueError("external audit reference must be one safe line")


class PromotionChangeKind(str, Enum):
    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True, order=True)
class PromotionFileChange:
    path: SafeRelativePath
    kind: PromotionChangeKind
    content: bytes
    executable: bool
    before_digest: ObjectDigest | None
    after_digest: ObjectDigest

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, SafeRelativePath)
            or not isinstance(self.kind, PromotionChangeKind)
            or not isinstance(self.content, bytes)
            or not isinstance(self.executable, bool)
            or not _valid_digest(self.after_digest)
            or sha256_bytes(self.content) != self.after_digest
            or (self.before_digest is not None and not _valid_digest(self.before_digest))
        ):
            raise ValueError("promotion file change is invalid")
        if self.kind is PromotionChangeKind.ADDED and self.before_digest is not None:
            raise ValueError("added promotion path cannot have prior content")
        if self.kind is PromotionChangeKind.CHANGED and (
            self.before_digest is None or self.before_digest == self.after_digest
        ):
            raise ValueError("changed promotion path requires distinct exact bytes")
        if self.kind is PromotionChangeKind.UNCHANGED and self.before_digest != self.after_digest:
            raise ValueError("unchanged promotion path must preserve exact bytes")


def _review_digest(
    expected_workspace_digest: ObjectDigest,
    next_workspace_digest: ObjectDigest,
    expected_registry_snapshot: ObjectDigest,
    next_registry_snapshot: ObjectDigest,
    mode: PromotionMode,
    changes: tuple[PromotionFileChange, ...],
) -> ObjectDigest:
    return json_digest(
        JsonObject(
            (
                (
                    "changes",
                    JsonArray(
                        tuple(
                            JsonObject(
                                (
                                    ("after_digest", str(change.after_digest)),
                                    (
                                        "before_digest",
                                        None
                                        if change.before_digest is None
                                        else str(change.before_digest),
                                    ),
                                    ("executable", change.executable),
                                    ("kind", change.kind.value),
                                    ("path", str(change.path)),
                                )
                            )
                            for change in changes
                        )
                    ),
                ),
                ("expected_registry_snapshot", str(expected_registry_snapshot)),
                ("expected_workspace_digest", str(expected_workspace_digest)),
                ("mode", mode.value),
                ("next_registry_snapshot", str(next_registry_snapshot)),
                ("next_workspace_digest", str(next_workspace_digest)),
            )
        )
    )


def _lifecycle_review_digest(
    expected_workspace_digest: ObjectDigest,
    next_workspace_digest: ObjectDigest,
    registry_snapshot: ObjectDigest,
    changes: tuple[PromotionFileChange, ...],
) -> ObjectDigest:
    return json_digest(
        JsonObject(
            (
                (
                    "changes",
                    JsonArray(
                        tuple(
                            JsonObject(
                                (
                                    ("after_digest", str(change.after_digest)),
                                    (
                                        "before_digest",
                                        None
                                        if change.before_digest is None
                                        else str(change.before_digest),
                                    ),
                                    ("kind", change.kind.value),
                                    ("path", str(change.path)),
                                )
                            )
                            for change in changes
                        )
                    ),
                ),
                ("expected_workspace_digest", str(expected_workspace_digest)),
                ("next_workspace_digest", str(next_workspace_digest)),
                ("registry_snapshot", str(registry_snapshot)),
            )
        )
    )


@dataclass(frozen=True, slots=True)
class PromotionPlan:
    expected_workspace_digest: ObjectDigest
    next_workspace_digest: ObjectDigest
    expected_registry_snapshot: ObjectDigest
    next_registry_snapshot: ObjectDigest
    mode: PromotionMode
    changes: tuple[PromotionFileChange, ...]
    versions: tuple[RegistryArtifactVersion, ...]
    audits: tuple[PromotionAudit, ...]
    review_digest: ObjectDigest

    def __post_init__(self) -> None:
        ordered_changes = tuple(sorted(self.changes, key=lambda item: str(item.path)))
        ordered_versions = tuple(sorted(self.versions, key=lambda item: str(item.coordinate)))
        ordered_audits = tuple(sorted(self.audits, key=lambda item: item.candidate_id.value))
        if (
            any(
                not _valid_digest(value)
                for value in (
                    self.expected_workspace_digest,
                    self.next_workspace_digest,
                    self.expected_registry_snapshot,
                    self.next_registry_snapshot,
                    self.review_digest,
                )
            )
            or not isinstance(self.mode, PromotionMode)
            or not ordered_changes
            or not ordered_versions
            or len({str(item.path) for item in ordered_changes}) != len(ordered_changes)
            or len({str(item.coordinate) for item in ordered_versions}) != len(ordered_versions)
            or len({item.candidate_id for item in ordered_audits}) != len(ordered_audits)
            or {item.candidate_id for item in ordered_versions}
            != {item.candidate_id for item in ordered_audits}
            or any(item.mode is not self.mode for item in ordered_versions)
            or any(item.mode is not self.mode for item in ordered_audits)
            or any(
                item.registry_snapshot != self.next_registry_snapshot for item in ordered_versions
            )
            or any(
                item.registry_snapshot_before != self.expected_registry_snapshot
                or item.registry_snapshot_after != self.next_registry_snapshot
                for item in ordered_audits
            )
            or self.review_digest
            != _review_digest(
                self.expected_workspace_digest,
                self.next_workspace_digest,
                self.expected_registry_snapshot,
                self.next_registry_snapshot,
                self.mode,
                ordered_changes,
            )
        ):
            raise ValueError("promotion plan is invalid")
        object.__setattr__(self, "changes", ordered_changes)
        object.__setattr__(self, "versions", ordered_versions)
        object.__setattr__(self, "audits", ordered_audits)

    @property
    def changed_paths(self) -> int:
        return sum(item.kind is not PromotionChangeKind.UNCHANGED for item in self.changes)


@dataclass(frozen=True, slots=True)
class PromotionApplyCommand:
    plan: PromotionPlan


@dataclass(frozen=True, slots=True)
class PromotionApplyReceipt:
    review_digest: ObjectDigest
    workspace_digest: ObjectDigest
    registry_snapshot: ObjectDigest
    changed_paths: int

    def __post_init__(self) -> None:
        if (
            not _valid_digest(self.review_digest)
            or not _valid_digest(self.workspace_digest)
            or not _valid_digest(self.registry_snapshot)
            or not isinstance(self.changed_paths, int)
            or isinstance(self.changed_paths, bool)
            or self.changed_paths < 0
        ):
            raise ValueError("promotion apply receipt is invalid")


@dataclass(frozen=True, slots=True)
class RegistryLifecyclePlan:
    expected_workspace_digest: ObjectDigest
    next_workspace_digest: ObjectDigest
    registry_snapshot: ObjectDigest
    changes: tuple[PromotionFileChange, ...]
    before: tuple[RegistryArtifactVersion, ...]
    after: tuple[RegistryArtifactVersion, ...]
    review_digest: ObjectDigest

    def __post_init__(self) -> None:
        ordered_changes = tuple(sorted(self.changes, key=lambda item: str(item.path)))
        ordered_before = tuple(sorted(self.before, key=lambda item: str(item.coordinate)))
        ordered_after = tuple(sorted(self.after, key=lambda item: str(item.coordinate)))
        if (
            any(
                not _valid_digest(value)
                for value in (
                    self.expected_workspace_digest,
                    self.next_workspace_digest,
                    self.registry_snapshot,
                    self.review_digest,
                )
            )
            or not ordered_changes
            or ordered_before == ordered_after
            or tuple(str(item.coordinate) for item in ordered_before)
            != tuple(str(item.coordinate) for item in ordered_after)
            or any(not str(item.path).startswith("registry/") for item in ordered_changes)
            or len({str(item.path) for item in ordered_changes}) != len(ordered_changes)
            or self.review_digest
            != _lifecycle_review_digest(
                self.expected_workspace_digest,
                self.next_workspace_digest,
                self.registry_snapshot,
                ordered_changes,
            )
        ):
            raise ValueError("registry lifecycle plan is invalid")
        object.__setattr__(self, "changes", ordered_changes)
        object.__setattr__(self, "before", ordered_before)
        object.__setattr__(self, "after", ordered_after)


class PromotionOutputPort(Protocol):
    def current(self) -> Result[SourceSnapshot]: ...

    def apply(self, command: PromotionApplyCommand) -> Result[PromotionApplyReceipt]: ...


def _error(message: str, *, code: DiagnosticCode = PROMOTION_INVALID) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _files(snapshot: SourceSnapshot) -> Result[dict[str, SnapshotEntry]]:
    validated = source_snapshot_digest(snapshot)
    if isinstance(validated, Err):
        return validated
    return Ok({str(entry.path): entry for entry in snapshot.entries})


def registry_state_digest(snapshot: SourceSnapshot) -> Result[ObjectDigest]:
    """Digest the published content of a registry snapshot, ignoring its metadata records.

    Published payload is what a registry *is* to a consumer; version and audit records describe it.
    Keeping the digest to `artifacts/` and `references/` is what lets a Maintainer be told that a
    local checkout still holds the approved content even while metadata is being rewritten.
    """

    entries = []
    for item in snapshot.entries:
        raw = str(item.path)
        if item.kind is not SnapshotEntryKind.FILE or not raw.startswith(
            ("artifacts/", "references/")
        ):
            continue
        entries.append(file_entry(item.path, item.content, executable=item.executable))
    return tree_digest(entries)


def _path(raw: str) -> Result[SafeRelativePath]:
    parsed = parse_relative_path(raw)
    if isinstance(parsed, Err):
        return _error(f"promotion produced an unsafe registry path: {raw}")
    return parsed


def _change(
    files: dict[str, SnapshotEntry],
    path: SafeRelativePath,
    content: bytes,
    *,
    executable: bool = False,
    mutable: bool = False,
) -> Result[PromotionFileChange]:
    current = files.get(str(path))
    after = sha256_bytes(content)
    if current is None:
        return Ok(
            PromotionFileChange(
                path,
                PromotionChangeKind.ADDED,
                content,
                executable,
                None,
                after,
            )
        )
    if current.kind is not SnapshotEntryKind.FILE:
        return _error(
            f"published coordinate/version path is immutable: {path}",
            code=PROMOTION_IMMUTABLE_CONFLICT,
        )
    if current.content != content or current.executable != executable:
        if mutable:
            return Ok(
                PromotionFileChange(
                    path,
                    PromotionChangeKind.CHANGED,
                    content,
                    executable,
                    sha256_bytes(current.content),
                    after,
                )
            )
        return _error(
            f"published coordinate/version path is immutable: {path}",
            code=PROMOTION_IMMUTABLE_CONFLICT,
        )
    return Ok(
        PromotionFileChange(
            path,
            PromotionChangeKind.UNCHANGED,
            content,
            executable,
            after,
            after,
        )
    )


def _project(
    snapshot: SourceSnapshot,
    changes: tuple[PromotionFileChange, ...],
) -> Result[SourceSnapshot]:
    files = _files(snapshot)
    if isinstance(files, Err):
        return files
    output = dict(files.value)
    for change in changes:
        raw = str(change.path)
        before = output.get(raw)
        if before is not None and before.kind is not SnapshotEntryKind.FILE:
            return _error(f"promotion target is not a file: {raw}")
        before_digest = None if before is None else sha256_bytes(before.content)
        if before_digest != change.before_digest:
            return _error(f"promotion path changed after review: {raw}", code=PROMOTION_STALE)
        output[raw] = SnapshotEntry(
            change.path,
            SnapshotEntryKind.FILE,
            change.content,
            change.executable,
        )
        for length in range(1, len(change.path.parts)):
            parent = SafeRelativePath(change.path.parts[:length])
            existing = output.get(str(parent))
            if existing is not None and existing.kind is not SnapshotEntryKind.DIRECTORY:
                return _error(f"promotion parent is not a directory: {parent}")
            output.setdefault(
                str(parent),
                SnapshotEntry(parent, SnapshotEntryKind.DIRECTORY),
            )
    return Ok(SourceSnapshot(snapshot.origin, tuple(output.values())))


def _reference_content(bundle: CandidateBundle, object_digest: ObjectDigest) -> bytes:
    candidate = bundle.candidate
    artifact = candidate.artifact
    return canonical_json_bytes(
        JsonObject(
            (
                ("candidate_digest", str(candidate.canonical_digest)),
                ("candidate_id", candidate.id.value),
                ("coordinate", str(artifact.coordinate)),
                ("input_digest", str(artifact.provenance.input_digest)),
                ("manifest_path", artifact.provenance.manifest_path),
                ("object_digest", str(object_digest)),
                ("payload_digest", str(artifact.payload_digest)),
                ("revision", artifact.provenance.revision),
                ("source", artifact.provenance.source),
                ("source_mode", PromotionMode.REFERENCED.value),
            )
        )
    )


def _audit_content(audit: PromotionAudit) -> bytes:
    return canonical_json_bytes(
        JsonObject(
            (
                ("candidate_digest", str(audit.candidate_digest)),
                ("candidate_id", audit.candidate_id.value),
                ("effective_policy_result", str(audit.effective_policy_digest)),
                ("external_audit_reference", audit.external_audit_reference),
                ("promotion_mode", audit.mode.value),
                ("registry_snapshot_after", str(audit.registry_snapshot_after)),
                ("registry_snapshot_before", str(audit.registry_snapshot_before)),
                ("source_revision", audit.source_revision),
                ("validation_report_digest", str(audit.validation_report_digest)),
                ("warnings", JsonArray(audit.warnings)),
            )
        )
    )


def _version_content(version: RegistryArtifactVersion) -> bytes:
    identity = version.coordinate.artifact
    return canonical_json_bytes(
        JsonObject(
            (
                ("candidate_id", version.candidate_id.value),
                ("canonical_digest", str(version.canonical_digest)),
                ("input_digest", str(version.input_digest)),
                ("kind", identity.kind),
                ("lifecycle", version.lifecycle.value),
                ("lifecycle_reason", version.lifecycle_reason),
                ("name", identity.name),
                ("object_digest", str(version.object_digest)),
                ("payload_digest", str(version.payload_digest)),
                ("promotion_mode", version.mode.value),
                ("publication", version.publication.value),
                ("registry", version.coordinate.source.value),
                ("registry_snapshot", str(version.registry_snapshot)),
                ("replacement", version.replacement),
                ("schema", "aart.dev/registry-version/v1"),
                ("version", version.coordinate.version),
            )
        )
    )


def _registry_catalog_content(
    versions: tuple[RegistryArtifactVersion, ...],
    registry_snapshot: ObjectDigest,
    *,
    schema: str,
) -> bytes:
    ordered = tuple(sorted(versions, key=lambda item: str(item.coordinate)))
    return canonical_json_bytes(
        JsonObject(
            (
                (
                    "artifacts",
                    JsonArray(
                        tuple(
                            JsonObject(
                                (
                                    ("canonical_digest", str(item.canonical_digest)),
                                    ("coordinate", str(item.coordinate)),
                                    ("lifecycle", item.lifecycle.value),
                                    ("object_digest", str(item.object_digest)),
                                    ("promotion_mode", item.mode.value),
                                    ("publication", item.publication.value),
                                )
                            )
                            for item in ordered
                        )
                    ),
                ),
                ("registry_snapshot", str(registry_snapshot)),
                ("schema", schema),
            )
        )
    )


def _candidate_warnings(findings: tuple[CandidateFinding, ...]) -> tuple[str, ...]:
    return tuple(
        f"{item.code}: {item.message}"
        for item in findings
        if item.severity is FindingSeverity.WARNING
    )


def plan_bulk_promotion(
    snapshot: SourceSnapshot,
    selected: tuple[CandidateBundle, ...],
    *,
    evidence: tuple[tuple[CandidateId, PromotionEvidence], ...],
    approved: tuple[RegistryArtifactVersion, ...],
    mode: PromotionMode = PromotionMode.VENDORED,
) -> Result[PromotionPlan]:
    """Plan selected candidates as one deterministic registry transaction."""

    if not isinstance(mode, PromotionMode) or not selected:
        return _error("bulk promotion requires candidates and an explicit valid mode")
    ordered = tuple(sorted(selected, key=lambda item: item.candidate.id.value))
    candidate_ids = tuple(item.candidate.id for item in ordered)
    coordinates = tuple(str(item.candidate.artifact.coordinate) for item in ordered)
    registries = {item.candidate.target_registry for item in ordered}
    if (
        len(set(candidate_ids)) != len(candidate_ids)
        or len(set(coordinates)) != len(coordinates)
        or len(registries) != 1
        or any(
            item.candidate.state not in {CandidateState.READY, CandidateState.WARNING}
            for item in ordered
        )
    ):
        return _error("bulk promotion selection is duplicated, mixed or not ready")
    evidence_by_id = dict(evidence)
    if len(evidence_by_id) != len(evidence) or set(evidence_by_id) != set(candidate_ids):
        return _error("each selected candidate requires exactly one promotion evidence record")
    # Named `stored` rather than `candidate`: the later loops bind `candidate` to the promotion
    # candidate itself, and reusing the name here would make every one of them a Result.
    object_digests: dict[CandidateId, ObjectDigest] = {}
    for bundle in ordered:
        stored = make_object_candidate(bundle.artifact.canonical_entries)
        if isinstance(stored, Err):
            return _error(
                f"candidate {bundle.candidate.id} does not form one immutable store object"
            )
        object_digests[bundle.candidate.id] = stored.value.digest

    files = _files(snapshot)
    if isinstance(files, Err):
        return files
    workspace_before = source_snapshot_digest(snapshot)
    registry_before = registry_state_digest(snapshot)
    if isinstance(workspace_before, Err) or isinstance(registry_before, Err):
        return _error("registry snapshot is invalid")

    approved_by_coordinate = {str(item.coordinate): item for item in approved}
    if len(approved_by_coordinate) != len(approved):
        return _error("approved registry state contains duplicate coordinate versions")
    package_changes: list[PromotionFileChange] = []
    for bundle in ordered:
        candidate = bundle.candidate
        artifact = candidate.artifact
        approved_version = approved_by_coordinate.get(
            str(
                registry_version_from_candidate(
                    candidate,
                    object_digest=object_digests[candidate.id],
                    registry_snapshot=registry_before.value,
                    mode=mode,
                ).coordinate
            )
        )
        if approved_version is not None:
            suffix = (
                "already contains this exact candidate"
                if approved_version.canonical_digest == candidate.canonical_digest
                else "is immutable and contains different content"
            )
            return _error(
                f"published coordinate/version {approved_version.coordinate} {suffix}",
                code=PROMOTION_IMMUTABLE_CONFLICT,
            )
        identity = artifact.coordinate.artifact
        version = artifact.coordinate.version
        assert version is not None
        if mode is PromotionMode.VENDORED:
            prefix = f"artifacts/{identity.kind}/{identity.name}/{version}"
            expected_paths: set[str] = set()
            for entry in bundle.artifact.canonical_entries:
                if entry.kind is not SnapshotEntryKind.FILE:
                    return _error("canonical promotion packages may contain only regular files")
                path = _path(f"{prefix}/{entry.path}")
                if isinstance(path, Err):
                    return path
                expected_paths.add(str(path.value))
                change = _change(
                    files.value,
                    path.value,
                    entry.content,
                    executable=entry.executable,
                )
                if isinstance(change, Err):
                    return change
                package_changes.append(change.value)
            occupied = {
                raw
                for raw, item in files.value.items()
                if raw.startswith(f"{prefix}/") and item.kind is SnapshotEntryKind.FILE
            }
            if occupied - expected_paths:
                return _error(
                    f"published coordinate/version path is immutable: {prefix}",
                    code=PROMOTION_IMMUTABLE_CONFLICT,
                )
        else:
            path = _path(f"references/{identity.kind}/{identity.name}/{version}.json")
            if isinstance(path, Err):
                return path
            change = _change(
                files.value,
                path.value,
                _reference_content(bundle, object_digests[candidate.id]),
            )
            if isinstance(change, Err):
                return change
            package_changes.append(change.value)

    package_projection = _project(snapshot, tuple(package_changes))
    if isinstance(package_projection, Err):
        return package_projection
    registry_after = registry_state_digest(package_projection.value)
    if isinstance(registry_after, Err):
        return registry_after

    versions: list[RegistryArtifactVersion] = []
    audits: list[PromotionAudit] = []
    metadata_changes: list[PromotionFileChange] = []
    package_files = _files(package_projection.value)
    assert isinstance(package_files, Ok)
    for bundle in ordered:
        candidate = bundle.candidate
        item_evidence = evidence_by_id[candidate.id]
        audit = PromotionAudit(
            candidate.id,
            candidate.canonical_digest,
            candidate.artifact.provenance.revision,
            item_evidence.validation_report_digest,
            item_evidence.effective_policy_digest,
            mode,
            registry_before.value,
            registry_after.value,
            tuple(sorted(set((*_candidate_warnings(candidate.findings), *item_evidence.warnings)))),
            item_evidence.external_audit_reference,
        )
        audits.append(audit)
        versions.append(
            registry_version_from_candidate(
                candidate,
                object_digest=object_digests[candidate.id],
                registry_snapshot=registry_after.value,
                mode=mode,
            )
        )
        audit_path = _path(f"registry/promotions/{candidate.id.value}.json")
        if isinstance(audit_path, Err):
            return audit_path
        audit_change = _change(
            package_files.value,
            audit_path.value,
            _audit_content(audit),
        )
        if isinstance(audit_change, Err):
            return audit_change
        metadata_changes.append(audit_change.value)

    # Every approved version names the registry's approved content snapshot, and this promotion
    # changed that content, so every retained record is rebound to the new digest inside the same
    # reviewed transaction.  Leaving them on the old one would make the whole registry unreadable
    # to a consumer the moment it holds more than one promotion (`validate_promoted_registry`
    # requires one exact snapshot), which is a registry that can never carry a second version.
    # This rebinds registry metadata only: the package at a published coordinate does not move.
    retained = tuple(replace(item, registry_snapshot=registry_after.value) for item in approved)
    all_versions = tuple(sorted((*retained, *versions), key=lambda item: str(item.coordinate)))
    if len({str(item.coordinate) for item in all_versions}) != len(all_versions):
        return _error("promotion would duplicate an approved coordinate version")
    rebound = {str(item.coordinate) for item in retained}
    for registry_version in all_versions:
        identity = registry_version.coordinate.artifact
        version_path = _path(
            f"registry/versions/{identity.kind}/{identity.name}/"
            f"{registry_version.coordinate.version}.json"
        )
        if isinstance(version_path, Err):
            return version_path
        version_change = _change(
            package_files.value,
            version_path.value,
            _version_content(registry_version),
            mutable=str(registry_version.coordinate) in rebound,
        )
        if isinstance(version_change, Err):
            return version_change
        metadata_changes.append(version_change.value)
    for raw_path, schema in (
        ("registry/index.json", "aart.dev/registry-index/v1"),
        ("registry/snapshot.json", "aart.dev/registry-snapshot/v1"),
    ):
        catalog_path = _path(raw_path)
        if isinstance(catalog_path, Err):
            return catalog_path
        catalog_change = _change(
            package_files.value,
            catalog_path.value,
            _registry_catalog_content(all_versions, registry_after.value, schema=schema),
            mutable=True,
        )
        if isinstance(catalog_change, Err):
            return catalog_change
        metadata_changes.append(catalog_change.value)

    changes = tuple(sorted((*package_changes, *metadata_changes), key=lambda item: str(item.path)))
    projected = _project(snapshot, changes)
    if isinstance(projected, Err):
        return projected
    workspace_after = source_snapshot_digest(projected.value)
    if isinstance(workspace_after, Err):
        return workspace_after
    review = _review_digest(
        workspace_before.value,
        workspace_after.value,
        registry_before.value,
        registry_after.value,
        mode,
        changes,
    )
    return Ok(
        PromotionPlan(
            workspace_before.value,
            workspace_after.value,
            registry_before.value,
            registry_after.value,
            mode,
            changes,
            tuple(versions),
            tuple(audits),
            review,
        )
    )


def project_promotion(snapshot: SourceSnapshot, plan: PromotionPlan) -> Result[SourceSnapshot]:
    current = source_snapshot_digest(snapshot)
    if isinstance(current, Err):
        return current
    if current.value != plan.expected_workspace_digest:
        return _error("registry workspace changed after promotion review", code=PROMOTION_STALE)
    projected = _project(snapshot, plan.changes)
    if isinstance(projected, Err):
        return projected
    workspace = source_snapshot_digest(projected.value)
    registry = registry_state_digest(projected.value)
    if (
        isinstance(workspace, Err)
        or isinstance(registry, Err)
        or workspace.value != plan.next_workspace_digest
        or registry.value != plan.next_registry_snapshot
    ):
        return _error("promotion projection no longer matches review", code=PROMOTION_STALE)
    return projected


def finalize_promotion(
    plan: PromotionPlan,
    reviewed_digest: ObjectDigest,
    *,
    output: PromotionOutputPort,
) -> Result[PromotionApplyReceipt]:
    """Apply one exact review through one local atomic port; publication remains external."""

    if reviewed_digest != plan.review_digest:
        return _error(
            "reviewed promotion digest does not match the prepared transaction",
            code=PROMOTION_REVIEW_MISMATCH,
        )
    current = output.current()
    if isinstance(current, Err):
        return current
    verified = project_promotion(current.value, plan)
    if isinstance(verified, Err):
        return verified
    applied = output.apply(PromotionApplyCommand(plan))
    if isinstance(applied, Err):
        return applied
    receipt = applied.value
    if (
        receipt.review_digest != plan.review_digest
        or receipt.workspace_digest != plan.next_workspace_digest
        or receipt.registry_snapshot != plan.next_registry_snapshot
        or receipt.changed_paths != plan.changed_paths
    ):
        return _error(
            "promotion output receipt does not match the reviewed transaction",
            code=PROMOTION_APPLY_MISMATCH,
        )
    return applied


def _immutable_version_fields(version: RegistryArtifactVersion) -> tuple[object, ...]:
    return (
        version.coordinate,
        version.candidate_id,
        version.input_digest,
        version.payload_digest,
        version.canonical_digest,
        version.object_digest,
        version.registry_snapshot,
        version.mode,
    )


def plan_registry_lifecycle(
    snapshot: SourceSnapshot,
    before: tuple[RegistryArtifactVersion, ...],
    after: tuple[RegistryArtifactVersion, ...],
) -> Result[RegistryLifecyclePlan]:
    """Review publication/deprecation/revocation metadata without touching payload state."""

    ordered_before = tuple(sorted(before, key=lambda item: str(item.coordinate)))
    ordered_after = tuple(sorted(after, key=lambda item: str(item.coordinate)))
    if (
        not ordered_before
        or len({str(item.coordinate) for item in ordered_before}) != len(ordered_before)
        or len({str(item.coordinate) for item in ordered_after}) != len(ordered_after)
        or tuple(str(item.coordinate) for item in ordered_before)
        != tuple(str(item.coordinate) for item in ordered_after)
        or ordered_before == ordered_after
        or any(
            _immutable_version_fields(left) != _immutable_version_fields(right)
            for left, right in zip(ordered_before, ordered_after, strict=True)
        )
    ):
        return _error(
            "registry lifecycle updates may change metadata only; immutable versions must match"
        )
    workspace_before = source_snapshot_digest(snapshot)
    registry_snapshot = registry_state_digest(snapshot)
    if isinstance(workspace_before, Err) or isinstance(registry_snapshot, Err):
        return _error("registry lifecycle input snapshot is invalid")
    if any(item.registry_snapshot != registry_snapshot.value for item in ordered_before):
        return _error("registry versions do not bind the current approved content snapshot")
    files = _files(snapshot)
    if isinstance(files, Err):
        return files
    changes: list[PromotionFileChange] = []
    for version in ordered_after:
        identity = version.coordinate.artifact
        version_path = _path(
            f"registry/versions/{identity.kind}/{identity.name}/{version.coordinate.version}.json"
        )
        if isinstance(version_path, Err):
            return version_path
        version_change = _change(
            files.value,
            version_path.value,
            _version_content(version),
            mutable=True,
        )
        if isinstance(version_change, Err):
            return version_change
        changes.append(version_change.value)
    for raw_path, schema in (
        ("registry/index.json", "aart.dev/registry-index/v1"),
        ("registry/snapshot.json", "aart.dev/registry-snapshot/v1"),
    ):
        catalog_path = _path(raw_path)
        if isinstance(catalog_path, Err):
            return catalog_path
        catalog_change = _change(
            files.value,
            catalog_path.value,
            _registry_catalog_content(ordered_after, registry_snapshot.value, schema=schema),
            mutable=True,
        )
        if isinstance(catalog_change, Err):
            return catalog_change
        changes.append(catalog_change.value)
    ordered_changes = tuple(sorted(changes, key=lambda item: str(item.path)))
    projected = _project(snapshot, ordered_changes)
    if isinstance(projected, Err):
        return projected
    workspace_after = source_snapshot_digest(projected.value)
    projected_registry = registry_state_digest(projected.value)
    if (
        isinstance(workspace_after, Err)
        or isinstance(projected_registry, Err)
        or projected_registry.value != registry_snapshot.value
    ):
        return _error("lifecycle metadata attempted to mutate approved payload state")
    review = _lifecycle_review_digest(
        workspace_before.value,
        workspace_after.value,
        registry_snapshot.value,
        ordered_changes,
    )
    return Ok(
        RegistryLifecyclePlan(
            workspace_before.value,
            workspace_after.value,
            registry_snapshot.value,
            ordered_changes,
            ordered_before,
            ordered_after,
            review,
        )
    )


def project_lifecycle_update(
    snapshot: SourceSnapshot,
    plan: RegistryLifecyclePlan,
) -> Result[SourceSnapshot]:
    current_workspace = source_snapshot_digest(snapshot)
    current_registry = registry_state_digest(snapshot)
    if (
        isinstance(current_workspace, Err)
        or isinstance(current_registry, Err)
        or current_workspace.value != plan.expected_workspace_digest
        or current_registry.value != plan.registry_snapshot
    ):
        return _error("registry changed after lifecycle review", code=PROMOTION_STALE)
    projected = _project(snapshot, plan.changes)
    if isinstance(projected, Err):
        return projected
    next_workspace = source_snapshot_digest(projected.value)
    next_registry = registry_state_digest(projected.value)
    if (
        isinstance(next_workspace, Err)
        or isinstance(next_registry, Err)
        or next_workspace.value != plan.next_workspace_digest
        or next_registry.value != plan.registry_snapshot
    ):
        return _error("lifecycle projection no longer matches review", code=PROMOTION_STALE)
    return projected


def validate_promoted_registry(
    snapshot: SourceSnapshot,
    versions: tuple[RegistryArtifactVersion, ...],
) -> Result[ObjectDigest]:
    """Validate durable version records, catalogs and vendored canonical package digests."""

    files = _files(snapshot)
    registry_snapshot = registry_state_digest(snapshot)
    if isinstance(files, Err) or isinstance(registry_snapshot, Err):
        return _error("approved registry snapshot is invalid")
    ordered = tuple(sorted(versions, key=lambda item: str(item.coordinate)))
    if len({str(item.coordinate) for item in ordered}) != len(ordered) or any(
        item.registry_snapshot != registry_snapshot.value for item in ordered
    ):
        return _error("registry versions do not bind one exact approved content snapshot")
    expected_version_paths: set[str] = set()
    for version in ordered:
        identity = version.coordinate.artifact
        version_path = (
            f"registry/versions/{identity.kind}/{identity.name}/{version.coordinate.version}.json"
        )
        expected_version_paths.add(version_path)
        version_entry = files.value.get(version_path)
        if (
            version_entry is None
            or version_entry.kind is not SnapshotEntryKind.FILE
            or version_entry.content != _version_content(version)
        ):
            return _error(f"registry version record is missing or stale: {version.coordinate}")
        if version.mode is PromotionMode.VENDORED:
            prefix = f"artifacts/{identity.kind}/{identity.name}/{version.coordinate.version}/"
            canonical_entries = []
            object_entries = []
            raw_paths = {
                raw
                for raw, entry in files.value.items()
                if raw.startswith(prefix) and entry.kind is SnapshotEntryKind.FILE
            }
            if (
                f"{prefix}artifact.json" not in raw_paths
                or f"{prefix}provenance.json" not in raw_paths
            ):
                return _error(f"vendored registry package is incomplete: {version.coordinate}")
            for raw in sorted(raw_paths):
                relative = raw.removeprefix(prefix)
                parsed = parse_relative_path(relative)
                entry = files.value[raw]
                if isinstance(parsed, Err):
                    return _error(f"vendored registry path is invalid: {raw}")
                object_entries.append(
                    SnapshotEntry(
                        parsed.value,
                        SnapshotEntryKind.FILE,
                        entry.content,
                        entry.executable,
                    )
                )
                if relative == "provenance.json":
                    continue
                canonical_entries.append(
                    file_entry(parsed.value, entry.content, executable=entry.executable)
                )
            digest = tree_digest(canonical_entries)
            if isinstance(digest, Err) or digest.value != version.canonical_digest:
                return _error(f"vendored registry package digest is invalid: {version.coordinate}")
            stored = make_object_candidate(
                object_entries,
                expected_digest=version.object_digest,
            )
            if isinstance(stored, Err):
                return _error(f"vendored registry object digest is invalid: {version.coordinate}")
        else:
            reference_path = (
                f"references/{identity.kind}/{identity.name}/{version.coordinate.version}.json"
            )
            reference = files.value.get(reference_path)
            if reference is None or reference.kind is not SnapshotEntryKind.FILE:
                return _error(f"referenced registry record is missing: {version.coordinate}")
            parsed_reference = parse_json(reference.content)
            if (
                not isinstance(parsed_reference, Ok)
                or not isinstance(parsed_reference.value, JsonObject)
                or parsed_reference.value.get("candidate_digest") != str(version.canonical_digest)
                or parsed_reference.value.get("object_digest") != str(version.object_digest)
            ):
                return _error(f"referenced registry record is invalid: {version.coordinate}")
    actual_version_paths = {
        raw
        for raw, entry in files.value.items()
        if raw.startswith("registry/versions/") and entry.kind is SnapshotEntryKind.FILE
    }
    if actual_version_paths != expected_version_paths:
        return _error("registry version record set does not match approved versions")
    for raw_path, schema in (
        ("registry/index.json", "aart.dev/registry-index/v1"),
        ("registry/snapshot.json", "aart.dev/registry-snapshot/v1"),
    ):
        catalog_entry = files.value.get(raw_path)
        if (
            catalog_entry is None
            or catalog_entry.kind is not SnapshotEntryKind.FILE
            or catalog_entry.content
            != _registry_catalog_content(ordered, registry_snapshot.value, schema=schema)
        ):
            return _error(f"registry catalog is missing or stale: {raw_path}")
    return Ok(registry_snapshot.value)


def _required_text(value: JsonObject, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"registry version requires {key}")
    return item


def _optional_text(value: JsonObject, key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise ValueError(f"registry version {key} must be text or null")
    return item


def _required_digest(value: JsonObject, key: str) -> ObjectDigest:
    parsed = parse_sha256(_required_text(value, key))
    if isinstance(parsed, Err):
        raise ValueError(f"registry version {key} must be canonical SHA-256")
    return parsed.value


def _parse_version_record(content: bytes, path: str) -> Result[RegistryArtifactVersion]:
    parsed = parse_json(content)
    if isinstance(parsed, Err) or not isinstance(parsed.value, JsonObject):
        return _error(f"registry version record is invalid JSON: {path}")
    value = parsed.value
    try:
        if value.get("schema") != "aart.dev/registry-version/v1":
            raise ValueError("registry version schema is unsupported")
        kind = _required_text(value, "kind")
        if kind not in {"skill", "guideline", "mcp", "hook", "memory", "collection"}:
            raise ValueError("registry version kind is invalid")
        version = RegistryArtifactVersion(
            ArtifactCoordinate(
                SourceAlias(_required_text(value, "registry")),
                ArtifactIdentity(cast(ArtifactKind, kind), _required_text(value, "name")),
                _required_text(value, "version"),
            ),
            CandidateId(_required_text(value, "candidate_id")),
            _required_digest(value, "input_digest"),
            _required_digest(value, "payload_digest"),
            _required_digest(value, "canonical_digest"),
            _required_digest(value, "object_digest"),
            _required_digest(value, "registry_snapshot"),
            PromotionMode(_required_text(value, "promotion_mode")),
            PublicationStage(_required_text(value, "publication")),
            RegistryLifecycle(_required_text(value, "lifecycle")),
            _optional_text(value, "lifecycle_reason"),
            _optional_text(value, "replacement"),
        )
    except ValueError as error:
        return _error(f"registry version record is invalid at {path}: {error}")
    identity = version.coordinate.artifact
    expected_path = (
        f"registry/versions/{identity.kind}/{identity.name}/{version.coordinate.version}.json"
    )
    if path != expected_path:
        return _error(f"registry version identity does not match its path: {path}")
    return Ok(version)


def _parse_audit_record(content: bytes, path: str) -> Result[PromotionAudit]:
    parsed = parse_json(content)
    if isinstance(parsed, Err) or not isinstance(parsed.value, JsonObject):
        return _error(f"registry promotion record is invalid JSON: {path}")
    value = parsed.value
    try:
        warnings = value.get("warnings")
        if not isinstance(warnings, JsonArray) or any(
            not isinstance(item, str) for item in warnings.items
        ):
            raise ValueError("promotion warnings must be a list of text")
        audit = PromotionAudit(
            CandidateId(_required_text(value, "candidate_id")),
            _required_digest(value, "candidate_digest"),
            _required_text(value, "source_revision"),
            _required_digest(value, "validation_report_digest"),
            _required_digest(value, "effective_policy_result"),
            PromotionMode(_required_text(value, "promotion_mode")),
            _required_digest(value, "registry_snapshot_before"),
            _required_digest(value, "registry_snapshot_after"),
            cast(tuple[str, ...], warnings.items),
            _optional_text(value, "external_audit_reference"),
        )
    except ValueError as error:
        return _error(f"registry promotion record is invalid at {path}: {error}")
    if path != f"registry/promotions/{audit.candidate_id.value}.json":
        return _error(f"registry promotion identity does not match its path: {path}")
    return Ok(audit)


def load_registry_promotions(snapshot: SourceSnapshot) -> Result[tuple[PromotionAudit, ...]]:
    """Read the durable approval evidence a registry wrote when it promoted each version.

    This is the counterpart of the writer above, and the only supported way to read it back: a
    consumer asking why a version is trusted is asking about the promotion that approved it, not
    about a flag somebody could restate elsewhere.
    """

    files = _files(snapshot)
    if isinstance(files, Err):
        return files
    audits: list[PromotionAudit] = []
    for path, entry in sorted(files.value.items()):
        if not path.startswith("registry/promotions/"):
            continue
        if entry.kind is SnapshotEntryKind.DIRECTORY:
            continue
        if entry.kind is not SnapshotEntryKind.FILE or not path.endswith(".json"):
            return _error(f"registry promotion path must be a JSON file: {path}")
        parsed = _parse_audit_record(entry.content, path)
        if isinstance(parsed, Err):
            return parsed
        if entry.content != _audit_content(parsed.value):
            return _error(f"registry promotion record is not canonical: {path}")
        audits.append(parsed.value)
    ordered = tuple(sorted(audits))
    if len({item.candidate_id for item in ordered}) != len(ordered):
        return _error("registry contains duplicate promotion records")
    return Ok(ordered)


def load_registry_versions(
    snapshot: SourceSnapshot,
) -> Result[tuple[RegistryArtifactVersion, ...]]:
    """Load and validate the approved version projection from one inert registry snapshot."""

    files = _files(snapshot)
    if isinstance(files, Err):
        return files
    versions: list[RegistryArtifactVersion] = []
    for path, entry in sorted(files.value.items()):
        if not path.startswith("registry/versions/"):
            continue
        if entry.kind is SnapshotEntryKind.DIRECTORY:
            continue
        if entry.kind is not SnapshotEntryKind.FILE or not path.endswith(".json"):
            return _error(f"registry version path must be a JSON file: {path}")
        parsed = _parse_version_record(entry.content, path)
        if isinstance(parsed, Err):
            return parsed
        versions.append(parsed.value)
    ordered = tuple(sorted(versions, key=lambda item: str(item.coordinate)))
    if len({str(item.coordinate) for item in ordered}) != len(ordered):
        return _error("registry contains duplicate approved coordinate versions")
    if ordered:
        validated = validate_promoted_registry(snapshot, ordered)
        if isinstance(validated, Err):
            return validated
    return Ok(ordered)
