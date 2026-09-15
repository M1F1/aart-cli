"""Candidate review state and pure lifecycle transitions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from enum import Enum

from .artifacts import ArtifactPackage
from .identifiers import ObjectDigest, SourceAlias
from .serialization import canonical_json_bytes

_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


class CandidateState(str, Enum):
    NEW = "new"
    CHANGED = "changed"
    READY = "ready"
    WARNING = "warning"
    INVALID = "invalid"
    APPROVAL_REQUIRED = "approval-required"
    PROMOTED = "promoted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    SOURCE_REMOVED = "source-removed"


class FindingSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True, order=True)
class CandidateId:
    value: str

    def __post_init__(self) -> None:
        if _HEX_64_RE.fullmatch(self.value) is None:
            raise ValueError("candidate ID must be a lowercase SHA-256 value")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class CandidateFinding:
    code: str
    severity: FindingSeverity
    message: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.code, str)
            or not self.code
            or self.code != self.code.strip()
            or not isinstance(self.severity, FindingSeverity)
            or not isinstance(self.message, str)
            or not self.message
            or self.message != self.message.strip()
            or any(character in self.code + self.message for character in "\r\n")
        ):
            raise ValueError("candidate finding must contain safe single-line metadata")


@dataclass(frozen=True, slots=True)
class Candidate:
    id: CandidateId
    artifact: ArtifactPackage
    canonical_digest: ObjectDigest
    target_registry: SourceAlias
    state: CandidateState
    previous: CandidateId | None = None
    successor: CandidateId | None = None
    findings: tuple[CandidateFinding, ...] = ()
    rejection_reason: str | None = None
    registry_snapshot: ObjectDigest | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, CandidateId)
            or not isinstance(self.artifact, ArtifactPackage)
            or not isinstance(self.canonical_digest, ObjectDigest)
            or not isinstance(self.target_registry, SourceAlias)
            or not self.target_registry.value
            or not isinstance(self.state, CandidateState)
            or (self.previous is not None and not isinstance(self.previous, CandidateId))
            or (self.successor is not None and not isinstance(self.successor, CandidateId))
            or any(not isinstance(item, CandidateFinding) for item in self.findings)
            or candidate_id_for(self.artifact, self.target_registry) != self.id
            or self.previous == self.id
            or self.successor == self.id
        ):
            raise ValueError("candidate is invalid")
        object.__setattr__(self, "findings", tuple(sorted(set(self.findings))))
        has_error = any(item.severity is FindingSeverity.ERROR for item in self.findings)
        has_warning = any(item.severity is FindingSeverity.WARNING for item in self.findings)
        if self.state is CandidateState.INVALID and not has_error:
            raise ValueError("invalid candidate requires an error finding")
        if self.state is CandidateState.WARNING and (has_error or not has_warning):
            raise ValueError("warning candidate requires warnings and no errors")
        if self.state is CandidateState.REJECTED:
            if (
                self.rejection_reason is None
                or not self.rejection_reason
                or self.rejection_reason != self.rejection_reason.strip()
                or any(character in self.rejection_reason for character in "\r\n")
            ):
                raise ValueError("rejected candidate requires one safe reason")
        elif self.rejection_reason is not None:
            raise ValueError("only rejected candidates carry a rejection reason")
        if (self.state is CandidateState.SUPERSEDED) != (self.successor is not None):
            raise ValueError("superseded candidate must bind its successor")
        if (self.state is CandidateState.PROMOTED) != (self.registry_snapshot is not None):
            raise ValueError("promoted candidate must bind its registry snapshot")


@dataclass(frozen=True, slots=True, order=True)
class CandidateChange:
    field: str
    before: str | None
    after: str | None


def candidate_id_for(artifact: ArtifactPackage, target_registry: SourceAlias) -> CandidateId:
    data = {
        "artifact_input_digest": str(artifact.provenance.input_digest),
        "manifest_path": artifact.provenance.manifest_path,
        "source": artifact.coordinate.source.value,
        "target_registry": target_registry.value,
    }
    return CandidateId(hashlib.sha256(canonical_json_bytes(data)).hexdigest())


def make_candidate(
    artifact: ArtifactPackage,
    canonical_digest: ObjectDigest,
    target_registry: SourceAlias,
    *,
    previous: CandidateId | None = None,
) -> Candidate:
    return Candidate(
        candidate_id_for(artifact, target_registry),
        artifact,
        canonical_digest,
        target_registry,
        CandidateState.NEW if previous is None else CandidateState.CHANGED,
        previous,
    )


def assess_candidate(
    candidate: Candidate,
    *,
    findings: tuple[CandidateFinding, ...] = (),
    manual_approval_required: bool = False,
) -> Candidate:
    if candidate.state in {
        CandidateState.PROMOTED,
        CandidateState.SUPERSEDED,
        CandidateState.SOURCE_REMOVED,
    }:
        raise ValueError("terminal candidate state cannot be reassessed")
    ordered = tuple(sorted(set(findings)))
    if any(item.severity is FindingSeverity.ERROR for item in ordered):
        state = CandidateState.INVALID
    elif manual_approval_required:
        state = CandidateState.APPROVAL_REQUIRED
    elif any(item.severity is FindingSeverity.WARNING for item in ordered):
        state = CandidateState.WARNING
    else:
        state = CandidateState.READY
    return replace(
        candidate,
        state=state,
        findings=ordered,
        successor=None,
        rejection_reason=None,
        registry_snapshot=None,
    )


def approve_candidate(candidate: Candidate) -> Candidate:
    if candidate.state is not CandidateState.APPROVAL_REQUIRED:
        raise ValueError("only an approval-required candidate can be approved")
    return replace(candidate, state=CandidateState.READY)


def reject_candidate(candidate: Candidate, reason: str) -> Candidate:
    if candidate.state in {CandidateState.PROMOTED, CandidateState.SUPERSEDED}:
        raise ValueError("promoted or superseded candidate cannot be rejected")
    return replace(
        candidate,
        state=CandidateState.REJECTED,
        successor=None,
        rejection_reason=reason,
        registry_snapshot=None,
    )


def supersede_candidate(candidate: Candidate, successor: CandidateId) -> Candidate:
    if candidate.state is CandidateState.PROMOTED:
        raise ValueError("published registry state, not its candidate history, owns promotion")
    return replace(
        candidate,
        state=CandidateState.SUPERSEDED,
        successor=successor,
        rejection_reason=None,
        registry_snapshot=None,
    )


def mark_source_removed(candidate: Candidate) -> Candidate:
    return replace(
        candidate,
        state=CandidateState.SOURCE_REMOVED,
        successor=None,
        rejection_reason=None,
        registry_snapshot=None,
    )


def mark_candidate_promoted(candidate: Candidate, registry_snapshot: ObjectDigest) -> Candidate:
    if candidate.state not in {CandidateState.READY, CandidateState.WARNING}:
        raise ValueError("only a validated candidate can be promoted")
    return replace(
        candidate,
        state=CandidateState.PROMOTED,
        successor=None,
        rejection_reason=None,
        registry_snapshot=registry_snapshot,
    )


def semantic_candidate_diff(
    before: Candidate,
    after: Candidate,
) -> tuple[CandidateChange, ...]:
    left = before.artifact
    right = after.artifact
    fields = {
        "artifact_input_digest": (
            str(left.provenance.input_digest),
            str(right.provenance.input_digest),
        ),
        "canonical_digest": (str(before.canonical_digest), str(after.canonical_digest)),
        "capabilities": (
            ",".join(item.value for item in left.capabilities),
            ",".join(item.value for item in right.capabilities),
        ),
        "format": (left.format.value, right.format.value),
        "harnesses": (
            ",".join(left.compatibility.harnesses),
            ",".join(right.compatibility.harnesses),
        ),
        "payload_digest": (str(left.payload_digest), str(right.payload_digest)),
        "platforms": (
            ",".join(left.compatibility.platforms),
            ",".join(right.compatibility.platforms),
        ),
        "protocol": (left.protocol, right.protocol),
        "python": (left.compatibility.python, right.compatibility.python),
        "version": (left.coordinate.version, right.coordinate.version),
    }
    return tuple(
        CandidateChange(field, old, new)
        for field, (old, new) in sorted(fields.items())
        if old != new
    )
