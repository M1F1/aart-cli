"""Canonical consumer Selection, versioned Collection and ownership values.

Selection records user intent.  It deliberately contains constraints rather than selected registry
versions; exact approved versions appear only in :class:`ResolvedSelection` after application
resolution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from .registry import RegistryArtifactVersion

_SAFE_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


def _safe_line(value: object, label: str, *, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(character in value for character in "\r\n")
    ):
        raise ValueError(f"{label} must be one safe non-empty line")
    return value


def artifact_request_sort_key(request: ArtifactRequest) -> tuple[str, str, str, str]:
    return (
        "" if request.source is None else request.source.value,
        request.identity.kind,
        request.identity.name,
        request.version.value,
    )


def artifact_coordinate_sort_key(
    coordinate: ArtifactCoordinate,
) -> tuple[str, str, str, str]:
    return (
        coordinate.source.value,
        coordinate.artifact.kind,
        coordinate.artifact.name,
        coordinate.version or "",
    )


@dataclass(frozen=True, slots=True, order=True)
class VersionConstraint:
    """Nominal constraint text; the application layer owns SemVer interpretation."""

    value: str

    def __post_init__(self) -> None:
        _safe_line(self.value, "version constraint", maximum=128)
        if any(character.isspace() for character in self.value):
            raise ValueError("version constraint cannot contain whitespace")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ArtifactRequest:
    identity: ArtifactIdentity
    version: VersionConstraint
    source: SourceAlias | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, ArtifactIdentity)
            or not self.identity.name
            or not isinstance(self.version, VersionConstraint)
            or (self.source is not None and not self.source.value)
        ):
            raise ValueError("artifact request is invalid")

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return artifact_request_sort_key(self)

    def __str__(self) -> str:
        prefix = "" if self.source is None else f"{self.source}/"
        constraint = "" if self.version.value == "*" else f"@{self.version}"
        return f"{prefix}{self.identity}{constraint}"


@dataclass(frozen=True, slots=True, order=True)
class CollectionCoordinate:
    source: SourceAlias
    name: str
    version: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source, SourceAlias)
            or not self.source.value
            or not isinstance(self.name, str)
            or _SAFE_NAME_RE.fullmatch(self.name) is None
        ):
            raise ValueError("Collection coordinate must have a qualified safe name")
        _safe_line(self.version, "Collection version", maximum=128)

    def __str__(self) -> str:
        return f"{self.source}/collection/{self.name}@{self.version}"


@dataclass(frozen=True, slots=True)
class CollectionMember:
    request: ArtifactRequest

    def __post_init__(self) -> None:
        if not isinstance(self.request, ArtifactRequest):
            raise ValueError("Collection member must contain an artifact request")

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return self.request.sort_key


@dataclass(frozen=True, slots=True)
class Collection:
    coordinate: CollectionCoordinate
    summary: str
    members: tuple[CollectionMember, ...]
    registry_snapshot: ObjectDigest

    def __post_init__(self) -> None:
        if not isinstance(self.coordinate, CollectionCoordinate):
            raise ValueError("Collection coordinate is invalid")
        _safe_line(self.summary, "Collection summary", maximum=1_024)
        if (
            not isinstance(self.registry_snapshot, ObjectDigest)
            or self.registry_snapshot.algorithm != "sha256"
            or _HEX_64_RE.fullmatch(self.registry_snapshot.value) is None
            or any(not isinstance(member, CollectionMember) for member in self.members)
        ):
            raise ValueError("Collection registry identity or members are invalid")
        object.__setattr__(
            self,
            "members",
            tuple(sorted(set(self.members), key=lambda member: member.sort_key)),
        )


@dataclass(frozen=True, slots=True)
class ArtifactSelection:
    artifacts: tuple[ArtifactRequest, ...] = ()
    collections: tuple[CollectionCoordinate, ...] = ()
    derived_from: tuple[CollectionCoordinate, ...] = ()

    def __post_init__(self) -> None:
        if (
            any(not isinstance(item, ArtifactRequest) for item in self.artifacts)
            or any(not isinstance(item, CollectionCoordinate) for item in self.collections)
            or any(not isinstance(item, CollectionCoordinate) for item in self.derived_from)
        ):
            raise ValueError("Selection contains invalid intent")
        artifacts = tuple(sorted(set(self.artifacts), key=artifact_request_sort_key))
        collections = tuple(sorted(set(self.collections)))
        derived = tuple(sorted(set(self.derived_from)))
        if set(collections) & set(derived):
            raise ValueError("an exact Collection cannot simultaneously be only a derivation")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "collections", collections)
        object.__setattr__(self, "derived_from", derived)

    @property
    def represents_exact_collections(self) -> bool:
        return bool(self.collections)


class OwnershipKind(str, Enum):
    COLLECTION = "collection"
    DEPENDENCY = "dependency"
    DIRECT = "direct"


@dataclass(frozen=True, slots=True)
class OwnershipReason:
    kind: OwnershipKind
    owner: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OwnershipKind):
            raise ValueError("ownership kind is invalid")
        _safe_line(self.owner, "ownership owner", maximum=1_024)

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.kind.value, self.owner)


@dataclass(frozen=True, slots=True)
class ResolvedArtifact:
    version: RegistryArtifactVersion
    ownership: tuple[OwnershipReason, ...]
    dependencies: tuple[ArtifactCoordinate, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.version, RegistryArtifactVersion)
            or not self.ownership
            or any(not isinstance(item, OwnershipReason) for item in self.ownership)
            or any(not isinstance(item, ArtifactCoordinate) for item in self.dependencies)
        ):
            raise ValueError("resolved artifact is invalid")
        object.__setattr__(
            self,
            "ownership",
            tuple(sorted(set(self.ownership), key=lambda item: item.sort_key)),
        )
        object.__setattr__(
            self,
            "dependencies",
            tuple(sorted(set(self.dependencies), key=artifact_coordinate_sort_key)),
        )


@dataclass(frozen=True, slots=True)
class ResolvedSelection:
    selection: ArtifactSelection
    artifacts: tuple[ResolvedArtifact, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.selection, ArtifactSelection) or any(
            not isinstance(item, ResolvedArtifact) for item in self.artifacts
        ):
            raise ValueError("resolved Selection is invalid")
        artifacts = tuple(
            sorted(
                self.artifacts,
                key=lambda item: artifact_coordinate_sort_key(item.version.coordinate),
            )
        )
        identities = tuple(item.version.coordinate.artifact for item in artifacts)
        if len(set(identities)) != len(identities):
            raise ValueError("resolved Selection permits one active version per artifact identity")
        object.__setattr__(self, "artifacts", artifacts)
