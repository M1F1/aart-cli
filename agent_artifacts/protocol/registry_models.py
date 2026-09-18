"""Frozen values for the AART registry protocol v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_artifacts.domain.identifiers import ArtifactIdentity, ObjectDigest, SourceId

from .capabilities import Capability
from .json import JsonValue
from .native_models import ArtifactSelector, CompatibilitySpec, InstallSpec
from .paths import SafeRelativePath
from .semver import SemVer, VersionBounds

ReviewStatus = Literal["approved", "pending", "rejected"]


@dataclass(frozen=True, slots=True)
class ServiceAdvertisement:
    name: str
    kind: str
    repository: str | None = None


@dataclass(frozen=True, slots=True)
class RegistryManifest:
    schema_version: int
    protocol_version: int
    registry_id: SourceId
    display_name: str
    requires_aart: VersionBounds
    required_capabilities: tuple[Capability, ...]
    default_channel: str
    services: tuple[ServiceAdvertisement, ...] = ()
    extensions: tuple[tuple[str, JsonValue], ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    status: ReviewStatus
    policy: str


@dataclass(frozen=True, slots=True)
class IndexSetup:
    recipe: SafeRelativePath
    platforms: tuple[str, ...]
    capabilities: tuple[Capability, ...] = ()


@dataclass(frozen=True, slots=True)
class IndexProvenance:
    origin_url: str
    resolved_commit: str
    path: SafeRelativePath


@dataclass(frozen=True, slots=True)
class IndexArtifact:
    source_id: SourceId
    identity: ArtifactIdentity
    version: SemVer
    summary: str
    manifest_digest: ObjectDigest
    payload_digest: ObjectDigest
    object_digest: ObjectDigest
    compatibility: CompatibilitySpec
    install: InstallSpec
    setup: IndexSetup | None = None
    review: ReviewRecord | None = None
    provenance: IndexProvenance | None = None
    collections: tuple[str, ...] = ()
    requires_aart: VersionBounds = VersionBounds()
    requires: tuple[ArtifactSelector, ...] = ()
