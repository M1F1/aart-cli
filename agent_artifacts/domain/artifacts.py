"""The canonical Artifact algebra: package intent without installation effects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .identifiers import ArtifactCoordinate, ObjectDigest, is_pinned_source_revision

_TOKEN_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._/-][a-z0-9]+)*$")


class ArtifactKind(str, Enum):
    SKILL = "skill"
    MCP = "mcp"
    GUIDELINE = "guideline"
    HOOK = "hook"
    MEMORY = "memory"


@dataclass(frozen=True, slots=True, order=True)
class ArtifactFormat:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _TOKEN_RE.fullmatch(self.value) is None:
            raise ValueError("artifact format must be a canonical lowercase identifier")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class Capability:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _TOKEN_RE.fullmatch(self.value) is None:
            raise ValueError("capability must be a canonical lowercase identifier")

    def __str__(self) -> str:
        return self.value


def _canonical_strings(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
        for value in values
    ):
        raise ValueError(f"{label} must contain non-empty single-line values")
    return tuple(sorted(set(values)))


@dataclass(frozen=True, slots=True)
class Compatibility:
    platforms: tuple[str, ...] = ()
    harnesses: tuple[str, ...] = ()
    python: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "platforms", _canonical_strings(self.platforms, "platforms"))
        object.__setattr__(self, "harnesses", _canonical_strings(self.harnesses, "harnesses"))
        if self.python is not None and (
            not isinstance(self.python, str)
            or not self.python
            or self.python != self.python.strip()
            or "\n" in self.python
            or "\r" in self.python
        ):
            raise ValueError("Python compatibility must be one non-empty constraint")


@dataclass(frozen=True, slots=True)
class Provenance:
    source: str
    revision: str
    manifest_path: str
    input_digest: ObjectDigest
    compiler: str

    def __post_init__(self) -> None:
        path_parts = self.manifest_path.split("/")
        if (
            not isinstance(self.source, str)
            or not self.source
            or self.source != self.source.strip()
            or any(character in self.source for character in "\r\n")
            or not is_pinned_source_revision(self.revision)
            or not self.manifest_path
            or self.manifest_path.startswith("/")
            or any(part in {"", ".", ".."} for part in path_parts)
            or not isinstance(self.input_digest, ObjectDigest)
            or not isinstance(self.compiler, str)
            or not self.compiler
            or any(character in self.compiler for character in "\r\n")
        ):
            raise ValueError("artifact provenance is invalid")


@dataclass(frozen=True, slots=True)
class ArtifactPackage:
    coordinate: ArtifactCoordinate
    kind: ArtifactKind
    format: ArtifactFormat
    payload_digest: ObjectDigest
    provenance: Provenance
    compatibility: Compatibility = Compatibility()
    capabilities: tuple[Capability, ...] = ()
    protocol: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coordinate, ArtifactCoordinate)
            or not isinstance(self.kind, ArtifactKind)
            or self.coordinate.artifact.kind != self.kind.value
            or not isinstance(self.format, ArtifactFormat)
            or not isinstance(self.payload_digest, ObjectDigest)
            or not isinstance(self.provenance, Provenance)
            or not isinstance(self.compatibility, Compatibility)
            or any(not isinstance(item, Capability) for item in self.capabilities)
            or (
                self.protocol is not None
                and (
                    not isinstance(self.protocol, str) or _TOKEN_RE.fullmatch(self.protocol) is None
                )
            )
        ):
            raise ValueError("artifact package is invalid")
        object.__setattr__(self, "capabilities", tuple(sorted(set(self.capabilities))))


def artifact_to_data(artifact: ArtifactPackage) -> dict[str, object]:
    return {
        "capabilities": [item.value for item in artifact.capabilities],
        "compatibility": {
            "harnesses": list(artifact.compatibility.harnesses),
            "platforms": list(artifact.compatibility.platforms),
            "python": artifact.compatibility.python,
        },
        "coordinate": str(artifact.coordinate),
        "format": artifact.format.value,
        "kind": artifact.kind.value,
        "payload_digest": str(artifact.payload_digest),
        "protocol": artifact.protocol,
        "provenance": {
            "compiler": artifact.provenance.compiler,
            "input_digest": str(artifact.provenance.input_digest),
            "manifest_path": artifact.provenance.manifest_path,
            "revision": artifact.provenance.revision,
            "source": artifact.provenance.source,
        },
    }
