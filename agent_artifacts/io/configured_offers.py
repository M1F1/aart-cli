"""What the configured registries are offering right now, read from what they published.

INV-026 settles where a Marketplace comes from: it is a human-facing projection over *configured
registries*, and it does not redefine what a registry approved.  So the offers here are read from
``registry/versions/*`` -- the same approved identities :func:`resolve_configured_selection` will
resolve against -- and never from a source's own working content.  A shell that offered what its
install seam could not resolve would be advertising an action it has to refuse afterwards.

Nothing is re-derived.  Each offered version is compiled back into the canonical package the
registry published, so compatibility is decided by the one existing evaluator reading the one
existing manifest, and a setup recipe's capabilities are recomputed from its own steps rather than
taken on the author's word.

This module reads; it does not write.  No object is materialized, no snapshot is fetched, and the
source store is opened once per configured source.
"""

from __future__ import annotations

import dataclasses
import time

from agent_artifacts.application.promotion import (
    load_registry_promotions,
    load_registry_versions,
)
from agent_artifacts.application.sources import SourceStatusRequest, source_status
from agent_artifacts.compiler.graph import GraphSource, compile_marketplace_graph
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.configuration.policy import EffectiveConfiguration
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactIdentity
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
    RegistryLifecycle,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.marketplace.catalog import build_marketplace
from agent_artifacts.marketplace.model import MarketplaceCatalog, MarketplaceSourceState
from agent_artifacts.protocol.native_tree import SourceSnapshot, compile_native_package
from agent_artifacts.protocol.paths import SafeRelativePath
from agent_artifacts.protocol.registry_index import index_artifact_from_package
from agent_artifacts.protocol.registry_models import ReviewRecord
from agent_artifacts.protocol.semver import SemVer, parse_semver
from agent_artifacts.runtime_contract import EXECUTABLE_CAPABILITIES
from agent_artifacts.sources.model import (
    CurrentSource,
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)

from .source_store import read_current_source

__all__ = [
    "CONFIGURED_OFFERS_INVALID",
    "ConfiguredMarketplace",
    "project_configured_registry",
    "read_configured_marketplace",
]

#: A configured registry published something this seam cannot read as an offer.
CONFIGURED_OFFERS_INVALID = DiagnosticCode("configured-offers-invalid")


@dataclasses.dataclass(frozen=True, slots=True)
class ConfiguredMarketplace:
    """What the configured registries offer, beside what they approved and this seam did not.

    `declined` is carried rather than dropped: an approved version missing from the Marketplace
    with no explanation reads as a registry that never approved it.
    """

    catalog: MarketplaceCatalog
    declined: tuple[str, ...] = ()


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURED_OFFERS_INVALID, Severity.ERROR, message),))


def _declined(version: RegistryArtifactVersion) -> str | None:
    """Why this approved version is not something the Marketplace may put in front of somebody.

    A referenced version has no verified content in this snapshot; a revoked one was withdrawn; a
    deprecated one carries a warning the row has nowhere to render yet, and offering it silently
    would be the Fast projection hiding material risk (B-037).  Collections are versioned and
    nothing downstream carries that version yet (B-031).
    """

    coordinate = version.coordinate
    if coordinate.artifact.kind == "collection":
        return f"{coordinate}: a Collection is offered by version, and nothing here carries one yet"
    if version.publication is not PublicationStage.PUBLISHED:
        return f"{coordinate}: promoted in this registry but not published"
    if version.mode is not PromotionMode.VENDORED:
        return f"{coordinate}: referenced, so this registry snapshot holds no verified content"
    if version.lifecycle is RegistryLifecycle.REVOKED:
        return f"{coordinate}: revoked by the registry"
    if version.lifecycle is RegistryLifecycle.DEPRECATED:
        return f"{coordinate}: deprecated by the registry, and this view cannot say so on the row"
    return None


def _current_versions(
    alias: str,
    versions: tuple[RegistryArtifactVersion, ...],
) -> Result[tuple[tuple[RegistryArtifactVersion, ...], tuple[str, ...]]]:
    """The one version of each identity a Marketplace row can stand for, and what it left out.

    A row is an artifact, not a version list, and the graph keys artifacts by source and identity.
    The highest approved SemVer is offered: it is what an unconstrained request would resolve to, so
    what is browsed and what is installed agree.  An older approved version is superseded, not
    declined -- it is still there, under the same row.
    """

    current: dict[ArtifactIdentity, tuple[RegistryArtifactVersion, SemVer]] = {}
    declined: list[str] = []
    for version in versions:
        reason = _declined(version)
        if reason is not None:
            declined.append(reason)
            continue
        assert version.coordinate.version is not None
        parsed = parse_semver(version.coordinate.version)
        if isinstance(parsed, Err):
            return _error(
                f"registry {alias} approved a version that is not SemVer: {version.coordinate}"
            )
        identity = version.coordinate.artifact
        found = current.get(identity)
        if found is None or found[1] < parsed.value:
            current[identity] = (version, parsed.value)
    offered = tuple(
        current[identity][0] for identity in sorted(current, key=lambda item: str(item))
    )
    return Ok((offered, tuple(sorted(set(declined)))))


def _package_entries(snapshot: SourceSnapshot, prefix: tuple[str, ...]):
    """The published package re-rooted at its own manifest, so it compiles as what it is."""

    return tuple(
        dataclasses.replace(entry, path=SafeRelativePath(entry.path.parts[len(prefix) :]))
        for entry in snapshot.entries
        if entry.path.parts[: len(prefix)] == prefix and len(entry.path.parts) > len(prefix)
    )


def project_configured_registry(
    configured: ConfiguredSource,
    current: CurrentSource,
) -> Result[tuple[GraphSource, tuple[str, ...]]]:
    """Every artifact this registry currently offers, compiled from what it published."""

    snapshot = current.candidate.snapshot
    loaded = load_registry_versions(snapshot)
    if isinstance(loaded, Err):
        return loaded
    promotions = load_registry_promotions(snapshot)
    if isinstance(promotions, Err):
        return promotions
    approvals = {audit.candidate_id: audit for audit in promotions.value}
    selected = _current_versions(str(configured.alias), loaded.value)
    if isinstance(selected, Err):
        return selected
    offered, declined = selected.value
    artifacts = []
    for version in offered:
        identity = version.coordinate.artifact
        prefix = ("artifacts", identity.kind, identity.name, str(version.coordinate.version))
        entries = _package_entries(snapshot, prefix)
        if not any(str(entry.path) == "artifact.json" for entry in entries):
            return _error(
                f"registry {configured.alias} approved {version.coordinate} without publishing "
                f"its content at {'/'.join(prefix)}"
            )
        package = compile_native_package(entries, expected_identity=identity)
        if isinstance(package, Err):
            return package
        if str(package.value.manifest.version) != version.coordinate.version:
            return _error(
                f"registry {configured.alias} published {version.coordinate} as version "
                f"{package.value.manifest.version}"
            )
        if package.value.payload_digest != version.payload_digest:
            # The approval names a payload; the published bytes must be that payload, or the row
            # would carry a digest nobody reviewed.
            return _error(
                f"registry {configured.alias} published content for {version.coordinate} that "
                "does not match its approved payload"
            )
        audit = approvals.get(version.candidate_id)
        if audit is None:
            # The version record says it was approved; the promotion that approved it says why.
            # Without that record the row would claim a review nothing in this snapshot evidences.
            return _error(
                f"registry {configured.alias} approved {version.coordinate} without keeping the "
                "promotion record that approved it"
            )
        artifacts.append(
            index_artifact_from_package(
                package.value,
                source_id=current.declared_source_id,
                object_digest=version.object_digest,
                review=ReviewRecord("approved", str(audit.effective_policy_digest)),
            )
        )
    return Ok(
        (
            GraphSource(configured.alias, current.declared_source_id, (), tuple(artifacts)),
            declined,
        )
    )


def read_configured_marketplace(
    effective: EffectiveConfiguration,
    *,
    data_root: str,
    observed_at_epoch_seconds: int | None = None,
) -> Result[ConfiguredMarketplace]:
    """Aggregate every enabled configured registry into one catalog, without mutating anything.

    Enabled sources that are not registries still appear, with their health and nothing offered:
    a source is where content comes from, and a registry is what approves it (INV-026).  Saying so
    is the point -- a configured source silently missing from the list would read as unconfigured.
    """

    if not isinstance(effective, EffectiveConfiguration) or not isinstance(data_root, str):
        return _error("reading configured offers needs effective configuration and a data root")
    now = int(time.time()) if observed_at_epoch_seconds is None else observed_at_epoch_seconds
    states: list[MarketplaceSourceState] = []
    graph_sources: list[GraphSource] = []
    declined: list[str] = []
    for order, configured in enumerate(
        source for source in effective.configuration.sources if source.enabled
    ):
        paths = source_store_paths(data_root, source_instance_id(configured))
        health = source_status(
            SourceStatusRequest(
                CurrentSourceRequest(paths, configured.alias),
                now,
                effective.configuration.sync.max_age_seconds,
            ),
            read_current_source,
        )
        states.append(MarketplaceSourceState(configured, health, order))
        if configured.kind is not SourceKind.REGISTRY_GIT or health.current is None:
            continue
        projected = project_configured_registry(configured, health.current)
        if isinstance(projected, Err):
            return projected
        graph_sources.append(projected.value[0])
        declined.extend(projected.value[1])
    graph = compile_marketplace_graph(
        tuple(graph_sources), available_capabilities=EXECUTABLE_CAPABILITIES
    )
    if isinstance(graph, Err):
        return graph
    catalog = build_marketplace(graph.value, effective, tuple(states))
    if isinstance(catalog, Err):
        return catalog
    return Ok(ConfiguredMarketplace(catalog.value, tuple(sorted(set(declined)))))
