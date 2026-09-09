"""Approved registry-version lifecycle, distinct from Candidate review state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .candidates import Candidate, CandidateId, CandidateState
from .identifiers import ArtifactCoordinate, ObjectDigest


class PromotionMode(str, Enum):
    VENDORED = "vendored"
    REFERENCED = "referenced"


class PublicationStage(str, Enum):
    PROMOTED_LOCAL = "promoted-local"
    PUBLISHED = "published"


class RegistryLifecycle(str, Enum):
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class RegistryArtifactVersion:
    coordinate: ArtifactCoordinate
    candidate_id: CandidateId
    input_digest: ObjectDigest
    payload_digest: ObjectDigest
    canonical_digest: ObjectDigest
    object_digest: ObjectDigest
    registry_snapshot: ObjectDigest
    mode: PromotionMode
    publication: PublicationStage = PublicationStage.PROMOTED_LOCAL
    lifecycle: RegistryLifecycle = RegistryLifecycle.PUBLISHED
    lifecycle_reason: str | None = None
    replacement: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coordinate, ArtifactCoordinate)
            or self.coordinate.version is None
            or not isinstance(self.candidate_id, CandidateId)
            or any(
                not isinstance(value, ObjectDigest)
                for value in (
                    self.input_digest,
                    self.payload_digest,
                    self.canonical_digest,
                    self.object_digest,
                    self.registry_snapshot,
                )
            )
            or not isinstance(self.mode, PromotionMode)
            or not isinstance(self.publication, PublicationStage)
            or not isinstance(self.lifecycle, RegistryLifecycle)
        ):
            raise ValueError("registry artifact version is invalid")
        for label, value in (
            ("lifecycle reason", self.lifecycle_reason),
            ("replacement", self.replacement),
        ):
            if value is not None and (
                not value
                or value != value.strip()
                or any(character in value for character in "\r\n")
            ):
                raise ValueError(f"registry {label} must be one safe line")
        if self.lifecycle is RegistryLifecycle.PUBLISHED and (
            self.lifecycle_reason is not None or self.replacement is not None
        ):
            raise ValueError("ordinary published lifecycle has no warning metadata")
        if self.lifecycle is not RegistryLifecycle.PUBLISHED and self.lifecycle_reason is None:
            raise ValueError("deprecated/revoked lifecycle requires a reason")


def registry_version_from_candidate(
    candidate: Candidate,
    *,
    object_digest: ObjectDigest,
    registry_snapshot: ObjectDigest,
    mode: PromotionMode,
) -> RegistryArtifactVersion:
    if candidate.state not in {
        CandidateState.READY,
        CandidateState.WARNING,
        CandidateState.PROMOTED,
    }:
        raise ValueError("registry version requires a validated candidate")
    artifact = candidate.artifact
    coordinate = ArtifactCoordinate(
        candidate.target_registry,
        artifact.coordinate.artifact,
        artifact.coordinate.version,
    )
    return RegistryArtifactVersion(
        coordinate,
        candidate.id,
        artifact.provenance.input_digest,
        artifact.payload_digest,
        candidate.canonical_digest,
        object_digest,
        registry_snapshot,
        mode,
    )


def publish_registry_version(
    version: RegistryArtifactVersion,
    registry_snapshot: ObjectDigest,
) -> RegistryArtifactVersion:
    return replace(
        version,
        registry_snapshot=registry_snapshot,
        publication=PublicationStage.PUBLISHED,
    )


def deprecate_registry_version(
    version: RegistryArtifactVersion,
    *,
    reason: str,
    replacement: str | None = None,
) -> RegistryArtifactVersion:
    return replace(
        version,
        lifecycle=RegistryLifecycle.DEPRECATED,
        lifecycle_reason=reason,
        replacement=replacement,
    )


def revoke_registry_version(
    version: RegistryArtifactVersion,
    *,
    reason: str,
    replacement: str | None = None,
) -> RegistryArtifactVersion:
    return replace(
        version,
        lifecycle=RegistryLifecycle.REVOKED,
        lifecycle_reason=reason,
        replacement=replacement,
    )
