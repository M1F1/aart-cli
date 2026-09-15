"""Versioned Collection declarations under the same review lifecycle as artifact Candidates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .candidates import CandidateFinding, CandidateId, CandidateState
from .identifiers import ObjectDigest, SourceAlias, is_pinned_source_revision
from .selection import ArtifactRequest, artifact_request_sort_key
from .serialization import canonical_json_bytes


def _safe_line(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n")
    ):
        raise ValueError(f"{label} must be one safe non-empty line")
    return value


@dataclass(frozen=True, slots=True)
class CollectionCandidate:
    """One authored, versioned Collection awaiting approval into a target registry."""

    id: CandidateId
    source_alias: SourceAlias
    source_location: str
    source_revision: str
    manifest_path: str
    input_digest: ObjectDigest
    canonical_digest: ObjectDigest
    target_registry: SourceAlias
    name: str
    version: str
    summary: str
    members: tuple[ArtifactRequest, ...]
    state: CandidateState
    previous: CandidateId | None = None
    successor: CandidateId | None = None
    findings: tuple[CandidateFinding, ...] = ()

    def __post_init__(self) -> None:
        for value, label in (
            (self.source_location, "Collection Candidate Source location"),
            (self.manifest_path, "Collection Candidate manifest path"),
            (self.name, "Collection Candidate name"),
            (self.version, "Collection Candidate version"),
            (self.summary, "Collection Candidate summary"),
        ):
            _safe_line(value, label)
        if (
            not isinstance(self.id, CandidateId)
            or not isinstance(self.source_alias, SourceAlias)
            or not self.source_alias.value
            or not is_pinned_source_revision(self.source_revision)
            or self.manifest_path.startswith("/")
            or any(part in {"", ".", ".."} for part in self.manifest_path.split("/"))
            or not isinstance(self.input_digest, ObjectDigest)
            or not isinstance(self.canonical_digest, ObjectDigest)
            or not isinstance(self.target_registry, SourceAlias)
            or not self.target_registry.value
            or not isinstance(self.state, CandidateState)
            or any(not isinstance(item, ArtifactRequest) for item in self.members)
            or not self.members
            or any(not isinstance(item, CandidateFinding) for item in self.findings)
            or (self.previous is not None and not isinstance(self.previous, CandidateId))
            or (self.successor is not None and not isinstance(self.successor, CandidateId))
            or self.previous == self.id
            or self.successor == self.id
            or collection_candidate_id_for(
                self.source_alias,
                self.manifest_path,
                self.input_digest,
                self.target_registry,
            )
            != self.id
        ):
            raise ValueError("Collection Candidate is invalid")
        object.__setattr__(
            self,
            "members",
            tuple(sorted(set(self.members), key=artifact_request_sort_key)),
        )
        object.__setattr__(self, "findings", tuple(sorted(set(self.findings))))
        if (self.state is CandidateState.SUPERSEDED) != (self.successor is not None):
            raise ValueError("superseded Collection Candidate must bind its successor")


def collection_candidate_id_for(
    source_alias: SourceAlias,
    manifest_path: str,
    input_digest: ObjectDigest,
    target_registry: SourceAlias,
) -> CandidateId:
    """Stable identity for authored input plus target, distinct from an artifact Candidate ID."""

    return CandidateId(
        hashlib.sha256(
            canonical_json_bytes(
                {
                    "candidate_kind": "collection",
                    "input_digest": str(input_digest),
                    "manifest_path": manifest_path,
                    "source": source_alias.value,
                    "target_registry": target_registry.value,
                }
            )
        ).hexdigest()
    )
