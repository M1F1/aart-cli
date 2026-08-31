"""Resolve consumer Selection from configured, approved registry snapshots.

This is the effectful bridge between source-store state and the pure CP-06 resolver.  Approval
identity comes only from validated ``registry/versions/*`` records.  In particular, legacy
Marketplace rows are not sufficient evidence to manufacture a Candidate ID or registry snapshot.
"""

from __future__ import annotations

from agent_artifacts.application.marketplace_resolution import (
    ApprovedMarketplace,
    ApprovedMarketplaceArtifact,
    ApprovedRegistrySnapshot,
    RegistryTrust,
    ResolutionPolicy,
    aggregate_approved_marketplace,
    resolve_selection,
)
from agent_artifacts.application.promotion import load_registry_versions
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.configuration.policy import EffectiveConfiguration
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.registry import PromotionMode, PublicationStage, RegistryArtifactVersion
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    ResolvedSelection,
    VersionConstraint,
)
from agent_artifacts.protocol.native_models import ArtifactSelector
from agent_artifacts.protocol.native_schema import parse_artifact_manifest
from agent_artifacts.protocol.native_tree import SnapshotEntryKind, SourceSnapshot
from agent_artifacts.protocol.semver import VersionBounds, version_bounds_label
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)

from .source_store import read_current_source

__all__ = [
    "CONFIGURED_SELECTION_INVALID",
    "load_configured_approved_marketplace",
    "resolve_configured_selection",
]

CONFIGURED_SELECTION_INVALID = DiagnosticCode("configured-selection-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURED_SELECTION_INVALID, Severity.ERROR, message),))


def _constraint(bounds: VersionBounds | None) -> VersionConstraint:
    if bounds is None or (bounds.min_inclusive is None and bounds.max_exclusive is None):
        return VersionConstraint("*")
    return VersionConstraint(version_bounds_label(bounds))


def _dependency(
    selector: ArtifactSelector,
    version: RegistryArtifactVersion,
) -> ArtifactRequest:
    return ArtifactRequest(
        selector.identity, _constraint(selector.version), version.coordinate.source
    )


def _manifest_entry(snapshot: SourceSnapshot, version: RegistryArtifactVersion):
    identity = version.coordinate.artifact
    path = f"artifacts/{identity.kind}/{identity.name}/{version.coordinate.version}/artifact.json"
    return path, next((entry for entry in snapshot.entries if str(entry.path) == path), None)


def _approved_artifact(
    snapshot: SourceSnapshot,
    version: RegistryArtifactVersion,
) -> Result[ApprovedMarketplaceArtifact]:
    if version.mode is not PromotionMode.VENDORED:
        return _error(
            f"configured approved version {version.coordinate} is referenced; its verified "
            "dependency manifest is not available in this registry snapshot"
        )
    path, entry = _manifest_entry(snapshot, version)
    if entry is None or entry.kind is not SnapshotEntryKind.FILE:
        return _error(f"configured approved version manifest is missing: {path}")
    manifest = parse_artifact_manifest(entry.content, path=path)
    if isinstance(manifest, Err):
        return manifest
    if (
        manifest.value.identity != version.coordinate.artifact
        or str(manifest.value.version) != version.coordinate.version
    ):
        return _error(
            f"configured approved version does not match its manifest: {version.coordinate}"
        )
    try:
        return Ok(
            ApprovedMarketplaceArtifact(
                version,
                tuple(_dependency(item, version) for item in manifest.value.requires),
            )
        )
    except ValueError as error:
        return _error(f"configured approved version is invalid: {error}")


def _approved_snapshot(
    alias,
    snapshot: SourceSnapshot,
) -> Result[ApprovedRegistrySnapshot | None]:
    loaded = load_registry_versions(snapshot)
    if isinstance(loaded, Err):
        return loaded
    versions = loaded.value
    if not versions:
        return Ok(None)
    registry_snapshots = {item.registry_snapshot for item in versions}
    if len(registry_snapshots) != 1 or any(item.coordinate.source != alias for item in versions):
        return _error(f"configured registry {alias} has inconsistent approved version identity")
    artifacts: list[ApprovedMarketplaceArtifact] = []
    for version in versions:
        if (
            version.publication is not PublicationStage.PUBLISHED
            or version.coordinate.artifact.kind == "collection"
        ):
            continue
        artifact = _approved_artifact(snapshot, version)
        if isinstance(artifact, Err):
            return artifact
        artifacts.append(artifact.value)
    try:
        return Ok(
            ApprovedRegistrySnapshot(
                alias,
                next(iter(registry_snapshots)),
                RegistryTrust.REGISTRY_REVIEWED,
                tuple(artifacts),
            )
        )
    except ValueError as error:
        return _error(f"configured registry {alias} is not an approved snapshot: {error}")


def load_configured_approved_marketplace(
    effective: EffectiveConfiguration,
    *,
    data_root: str,
) -> Result[ApprovedMarketplace]:
    """Read every enabled configured registry once and aggregate its published versions."""

    if not isinstance(effective, EffectiveConfiguration) or not isinstance(data_root, str):
        return _error(
            "configured Selection resolution needs effective configuration and a data root"
        )
    snapshots: list[ApprovedRegistrySnapshot] = []
    for configured in effective.configuration.sources:
        if not configured.enabled or configured.kind is not SourceKind.REGISTRY_GIT:
            continue
        paths = source_store_paths(data_root, source_instance_id(configured))
        current = read_current_source(CurrentSourceRequest(paths, configured.alias))
        if isinstance(current, Err):
            return current
        if current.value is None:
            continue
        approved = _approved_snapshot(configured.alias, current.value.candidate.snapshot)
        if isinstance(approved, Err):
            return approved
        if approved.value is not None:
            snapshots.append(approved.value)
    return aggregate_approved_marketplace(tuple(snapshots))


def resolve_configured_selection(
    effective: EffectiveConfiguration,
    selection: ArtifactSelection,
    *,
    data_root: str,
    policy: ResolutionPolicy | None = None,
) -> Result[ResolvedSelection]:
    """Resolve intent only through the approved identities present in configured snapshots."""

    if not isinstance(selection, ArtifactSelection):
        return _error("configured Selection resolution needs an ArtifactSelection")
    marketplace = load_configured_approved_marketplace(effective, data_root=data_root)
    if isinstance(marketplace, Err):
        return marketplace
    return resolve_selection(marketplace.value, selection, policy=policy)
