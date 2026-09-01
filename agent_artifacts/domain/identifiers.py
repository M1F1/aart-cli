"""Nominal identity values shared by AART bounded contexts.

Validation and parsing rules are introduced by the protocol context. These frozen values keep
source aliases, declared IDs, origins, artifact identities, and object digests distinct meanwhile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ArtifactKind = Literal["skill", "guideline", "mcp", "hook", "memory", "collection"]
SourceRevisionKind = Literal["git", "local"]

_GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_LOCAL_REVISION_RE = re.compile(r"^local:[0-9a-f]{64}$")


def source_revision_kind(value: str) -> SourceRevisionKind | None:
    """Classify one canonical immutable Source revision without conflating origins."""

    if not isinstance(value, str):
        return None
    if _GIT_REVISION_RE.fullmatch(value) is not None:
        return "git"
    if _LOCAL_REVISION_RE.fullmatch(value) is not None:
        return "local"
    return None


def is_pinned_source_revision(value: str) -> bool:
    return source_revision_kind(value) is not None


@dataclass(frozen=True, slots=True, order=True)
class SourceAlias:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class SourceId:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class SourceOrigin:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class InputId:
    """Identity of one declared runtime input, independent of its kind and of any value."""

    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class ArtifactIdentity:
    kind: ArtifactKind
    name: str

    def __str__(self) -> str:
        return f"{self.kind}/{self.name}"


@dataclass(frozen=True, slots=True)
class ArtifactCoordinate:
    source: SourceAlias
    artifact: ArtifactIdentity
    version: str | None = None

    def __str__(self) -> str:
        version = "" if self.version is None else f"@{self.version}"
        return f"{self.source}/{self.artifact}{version}"


@dataclass(frozen=True, slots=True, order=True)
class ObjectDigest:
    algorithm: str
    value: str

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.value}"
