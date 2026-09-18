"""Local composition root for the canonical consumer marketplace and shared object store."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass

from agent_artifacts.application.configuration import (
    ConfigurationPorts,
    ConfigurationRequest,
    load_configuration,
)
from agent_artifacts.application.promotion import registry_state_digest
from agent_artifacts.application.sources import SourceStatusRequest, source_status
from agent_artifacts.compiler.graph import GraphSource, compile_marketplace_graph
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind, UserConfiguration
from agent_artifacts.configuration.paths import Platform, resolve_config_paths
from agent_artifacts.configuration.policy import (
    EffectiveConfiguration,
    RuntimeOverrides,
    apply_configuration,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactCoordinate, SourceAlias
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.installation.model import InstallLocation
from agent_artifacts.io.config_store import (
    read_configuration,
    recover_configuration,
    write_configuration,
)
from agent_artifacts.io.configured_offers import project_configured_registry
from agent_artifacts.io.object_store import publish_object
from agent_artifacts.io.source_store import (
    read_current_source,
)
from agent_artifacts.marketplace.catalog import build_marketplace
from agent_artifacts.marketplace.model import (
    MarketplaceCatalog,
    MarketplaceSourceState,
)
from agent_artifacts.profiles.builtin import builtin
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    load_native_source,
)
from agent_artifacts.protocol.paths import SafeRelativePath, parse_relative_path
from agent_artifacts.protocol.registry_index import index_artifact_from_package
from agent_artifacts.registry_maintenance.promoted import (
    is_promoted_registry,
    legacy_registry_paths,
)
from agent_artifacts.runtime_contract import EXECUTABLE_CAPABILITIES, EXECUTABLE_VERSION
from agent_artifacts.security.aggregation import ArtifactSecurityEvidence
from agent_artifacts.security.application import verify_security_index
from agent_artifacts.security.attestation_schema import parse_security_index
from agent_artifacts.security.attestations import (
    AttestationTrust,
    AttestationTrustContext,
    ResolvedAttestation,
    resolve_attestation,
)
from agent_artifacts.security.model import (
    AssessmentCoverage,
    AssessmentStatus,
    FindingSeverity,
    SecurityAssessment,
    risk_from_evidence,
)
from agent_artifacts.sources.model import (
    CurrentSource,
    CurrentSourceRequest,
    SourceHealth,
    source_instance_id,
    source_store_paths,
)
from agent_artifacts.sources.runtime import observe_configured_source, sync_configured_source
from agent_artifacts.sources.validation import declares_native_source
from agent_artifacts.store.model import (
    ObjectPublishCommand,
    ObjectStorePaths,
    make_object_candidate,
    object_store_paths,
)

from .application import ConsumerApplicationService
from .io import LocalConsumerAdapter
from .model import ConsumerContext

CONSUMER_RUNTIME_INVALID = DiagnosticCode("consumer-runtime-invalid")
# Compatibility aliases for existing internal callers.  New composition roots use the public
# executable contract instead of importing this module's private implementation details.
_VERSION = EXECUTABLE_VERSION
_CAPABILITIES = EXECUTABLE_CAPABILITIES
_ATTESTATION_TRUST_RANK = {
    AttestationTrust.UNVERIFIED: 0,
    AttestationTrust.LOCAL: 1,
    AttestationTrust.REGISTRY_REVIEWED: 2,
    AttestationTrust.COMPANY_REVIEWED: 3,
}


@dataclass(frozen=True, slots=True)
class _GraphProjection:
    graph: GraphSource


def _error(message: str) -> Err:
    return Err((Diagnostic(CONSUMER_RUNTIME_INVALID, Severity.ERROR, message),))


def _offline_object_missing(coordinate: ArtifactCoordinate) -> Err:
    return Err(
        (
            Diagnostic(
                DiagnosticCode("offline-object-missing"),
                Severity.ERROR,
                f"offline mode cannot fetch uncached registry content for {coordinate}",
                remediation=("retry without offline mode while the registry origin is reachable",),
            ),
        )
    )


def _entry(snapshot, path: str) -> SnapshotEntry | None:
    return next((item for item in snapshot.entries if str(item.path) == path), None)


def _package_entries(snapshot, root: SafeRelativePath) -> Result[tuple[SnapshotEntry, ...]]:
    prefix = f"{root}/"
    result = []
    for item in snapshot.entries:
        raw = str(item.path)
        if not raw.startswith(prefix):
            continue
        relative = parse_relative_path(raw.removeprefix(prefix))
        if isinstance(relative, Err):
            return relative
        result.append(SnapshotEntry(relative.value, item.kind, item.content, item.executable))
    if not result:
        return _error(f"canonical package is absent from its source snapshot: {root}")
    return Ok(tuple(result))


def _package_root(snapshot, native, identity) -> SafeRelativePath:
    matches = tuple(
        SafeRelativePath((*root.parts, identity.kind, identity.name))
        for root in native.manifest.artifact_roots
        if _entry(snapshot, f"{root}/{identity.kind}/{identity.name}/artifact.json") is not None
    )
    if len(matches) != 1:
        raise ValueError(f"canonical package root is ambiguous: {identity}")
    return matches[0]


def _index_native(
    snapshot,
    native,
    paths: ObjectStorePaths | None,
    expected_by_identity=None,
):
    """Validate native packages into graph index records, optionally publishing their objects."""

    indexed = []
    for package in native.artifacts:
        try:
            root = _package_root(snapshot, native, package.manifest.identity)
        except ValueError as error:
            return _error(str(error))
        entries = _package_entries(snapshot, root)
        if isinstance(entries, Err):
            return entries
        expected = (
            None
            if expected_by_identity is None
            else expected_by_identity.get(package.manifest.identity)
        )
        candidate = make_object_candidate(entries.value, expected_digest=expected)
        if isinstance(candidate, Err):
            return candidate
        if paths is not None:
            published = publish_object(ObjectPublishCommand(paths, candidate.value))
            if isinstance(published, Err):
                return published
        indexed.append(
            index_artifact_from_package(
                package,
                source_id=native.manifest.source_id,
                object_digest=candidate.value.digest,
            )
        )
    return Ok(tuple(indexed))


def _materialize_native(snapshot, native, paths, expected_by_identity=None):
    """Compatibility wrapper for the consumer service's object-materializing composition path."""

    return _index_native(snapshot, native, paths, expected_by_identity)


def _project_graph_source(
    configured,
    current,
    paths: ObjectStorePaths,
    *,
    materialize_objects: bool = True,
) -> Result[_GraphProjection]:
    snapshot = current.candidate.snapshot
    if configured.kind is not SourceKind.REGISTRY_GIT:
        # An authoring Source holds Candidates, and a Candidate is by definition not approved
        # content (INV-199).  It contributes nothing to the consumer Marketplace -- and, because
        # the loop that calls this returns on the first Err, "nothing" has to mean an empty
        # projection rather than a refusal: a subscribed author repository must not be able to
        # take the whole Marketplace away from the consumer who subscribed to it (B-094).
        if not declares_native_source(snapshot):
            return Ok(
                _GraphProjection(GraphSource(configured.alias, current.declared_source_id, (), ()))
            )
        native = load_native_source(
            snapshot,
            executable_version=_VERSION,
            available_capabilities=_CAPABILITIES,
        )
        if isinstance(native, Err):
            return native
        indexed = _index_native(
            snapshot,
            native.value,
            paths if materialize_objects else None,
        )
        if isinstance(indexed, Err):
            return indexed
        return Ok(
            _GraphProjection(
                GraphSource(
                    configured.alias,
                    native.value.manifest.source_id,
                    native.value.manifest.required_capabilities,
                    indexed.value,
                    native.value.collections,
                )
            )
        )

    # The approved registry projection is the canonical consumer representation produced by
    # promotion, and the only one.  The retired maintainer workspace wrote `aart.lock.json`,
    # `aart.index.json` and `entries/`; no second compiler survives to read them, so a snapshot
    # still carrying that shape -- or carrying both -- is refused by name instead of being
    # interpreted by whichever branch happened to match first (CP-26.4, D-308).
    retired = legacy_registry_paths(snapshot)
    if retired:
        return _error(
            f"registry {configured.alias} carries the retired authoring-workspace "
            "representation: " + ", ".join(retired)
        )
    if not is_promoted_registry(snapshot):
        return _error(
            f"registry {configured.alias} is not a canonical approved Registry: its root must "
            "declare aart-registry.json and aart-source.json"
        )
    approved = project_configured_registry(configured, current)
    if isinstance(approved, Err):
        return approved
    return Ok(_GraphProjection(approved.value[0]))


def _graph_source(configured, current, paths) -> Result[GraphSource]:
    projected = _project_graph_source(configured, current, paths)
    return projected if isinstance(projected, Err) else Ok(projected.value.graph)


def _merged_security_evidence(
    coordinate: ArtifactCoordinate,
    resolved: tuple[ResolvedAttestation, ...],
    *,
    age_seconds: int,
) -> ArtifactSecurityEvidence | None:
    """Merge one current attestation per provider into explainable artifact evidence."""

    by_provider: dict[str, ResolvedAttestation] = {}
    for item in resolved:
        provider = item.assessment.providers[0]
        existing = by_provider.get(provider.id)
        if existing is None or provider.version > existing.assessment.providers[0].version:
            by_provider[provider.id] = item
    selected = tuple(by_provider[key] for key in sorted(by_provider))
    if not selected:
        return None
    providers = tuple(item.assessment.providers[0] for item in selected)
    statuses = {provider.status for provider in providers}
    if AssessmentStatus.STALE in statuses:
        status = AssessmentStatus.STALE
    elif AssessmentStatus.FAILED in statuses:
        status = AssessmentStatus.FAILED
    elif statuses == {AssessmentStatus.COMPLETE}:
        status = AssessmentStatus.COMPLETE
    elif statuses == {AssessmentStatus.NOT_SCANNED}:
        status = AssessmentStatus.NOT_SCANNED
    else:
        status = AssessmentStatus.PARTIAL
    coverage = (
        providers[0].coverage
        if len(providers) == 1
        else AssessmentCoverage(
            sum(provider.coverage.completed for provider in providers),
            sum(provider.coverage.expected for provider in providers),
            tuple(
                f"{provider.id}:{reason}"
                for provider in providers
                for reason in provider.coverage.skipped
            ),
        )
    )
    findings_by_fingerprint = {
        finding.fingerprint: finding for item in selected for finding in item.assessment.findings
    }
    findings = tuple(findings_by_fingerprint.values())
    maximum = max(
        (finding.severity for finding in findings),
        key=lambda severity: severity.rank,
        default=FindingSeverity.UNKNOWN,
    )
    try:
        assessment = SecurityAssessment(
            1,
            selected[0].assessment.object_digest,
            status,
            risk_from_evidence(status, maximum),
            maximum,
            coverage,
            findings,
            providers,
        )
    except ValueError:
        return None
    trust = min(
        (item.trust for item in selected),
        key=lambda item: _ATTESTATION_TRUST_RANK[item],
    )
    return ArtifactSecurityEvidence(coordinate, assessment, trust, age_seconds)


def _registry_security_evidence(
    catalog: MarketplaceCatalog,
    registry_sources: tuple[tuple[ConfiguredSource, CurrentSource], ...],
    *,
    now: int,
) -> tuple[ArtifactSecurityEvidence, ...]:
    """Verify optional committed registry attestations and bind them to exact coordinates."""

    evidence = []
    for configured, current in registry_sources:
        snapshot = current.candidate.snapshot
        security_entry = _entry(snapshot, "security/index.json")
        if security_entry is None:
            continue
        security_index = parse_security_index(security_entry.content)
        # The attestation set claims a registry identity and a registry content state.  Both are
        # recomputed from this snapshot rather than read out of a catalog the same commit could
        # have rewritten, so a tampered registry cannot assert the state its evidence was made
        # for (CP-26.4).
        registry_state = registry_state_digest(snapshot)
        if isinstance(security_index, Err) or isinstance(registry_state, Err):
            continue
        index = security_index.value
        if (
            index.registry_id != current.declared_source_id
            or index.registry_inputs_digest != registry_state.value
        ):
            continue
        documents = []
        for index_entry in index.entries:
            document = _entry(snapshot, str(index_entry.path))
            if document is None:
                break
            documents.append((index_entry.path, document.content))
        else:
            verified = verify_security_index(index, tuple(documents))
            if isinstance(verified, Err):
                continue
            age = max(now - current.published_at_epoch_seconds, 0)
            for item in catalog.items:
                if item.source.alias != configured.alias:
                    continue
                matching = tuple(
                    resolve_attestation(
                        attestation,
                        attestation.cache_key,
                        trust_context=AttestationTrustContext(
                            index.registry_id,
                            index.registry_inputs_digest,
                            item.trust.kind,
                        ),
                    )
                    for attestation in verified.value.attestations
                    if attestation.cache_key.object_digest == item.artifact.artifact.object_digest
                )
                merged = _merged_security_evidence(item.coordinate, matching, age_seconds=age)
                if merged is not None:
                    evidence.append(merged)
    return tuple(evidence)


def load_read_only_marketplace(
    effective: EffectiveConfiguration,
    *,
    data_root: str,
    observe_freshness: bool = False,
) -> Result[MarketplaceCatalog]:
    """Build the configured marketplace from durable snapshots without object-store mutation.

    This is intentionally narrower than :func:`load_local_consumer_service`: it receives the
    already-resolved effective configuration from its caller, never rereads configuration, and
    validates packages into graph/index values without materializing immutable objects.  Object
    publication remains an install/update concern owned by the consumer service.
    """

    now = int(time.time())
    states = []
    graph_sources = []
    paths = object_store_paths(data_root)
    for order, configured in enumerate(
        source for source in effective.configuration.sources if source.enabled
    ):
        source_paths = source_store_paths(data_root, source_instance_id(configured))
        health: SourceHealth
        if observe_freshness:
            health = observe_configured_source(
                configured,
                data_root=data_root,
                mode=effective.configuration.sync.mode,
                observed_at_epoch_seconds=now,
            )
        else:
            health = source_status(
                SourceStatusRequest(
                    CurrentSourceRequest(source_paths, configured.alias),
                    now,
                    effective.configuration.sync.max_age_seconds,
                ),
                read_current_source,
            )
        states.append(MarketplaceSourceState(configured, health, order))
        if health.current is None:
            continue
        projected = _project_graph_source(
            configured,
            health.current,
            paths,
            materialize_objects=False,
        )
        if isinstance(projected, Err):
            return projected
        graph_sources.append(projected.value.graph)
    graph = compile_marketplace_graph(
        tuple(graph_sources),
        available_capabilities=_CAPABILITIES,
    )
    if isinstance(graph, Err):
        return graph
    return build_marketplace(graph.value, effective, tuple(states))


def load_local_consumer_service(
    *,
    project: str | None,
    user_home: str | None,
    configuration: UserConfiguration | None = None,
    refresh_sources: bool = False,
    observe_freshness: bool = False,
    offline: bool = False,
    content_required: bool = True,
) -> Result[ConsumerApplicationService]:
    """Load a consumer service, optionally refreshing every configured origin first.

    ``content_required`` is the canonical no-source contract: a content operation needs at least one
    enabled source, and every organization-required alias.  Uninstall is the one lifecycle operation
    that is not a content operation — it reads the manifest — so it passes ``False`` rather than
    refusing to remove what a project already has because the subscription it came from is gone.
    """

    platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
    home = os.path.abspath(user_home or os.path.expanduser("~"))
    config_paths = resolve_config_paths(
        platform,
        home=home,
        xdg_config_home=os.environ.get("XDG_CONFIG_HOME"),
        xdg_data_home=os.environ.get("XDG_DATA_HOME"),
        xdg_cache_home=os.environ.get("XDG_CACHE_HOME"),
    )
    loaded = load_configuration(
        ConfigurationRequest(
            config_paths,
            RuntimeOverrides(),
            content_required=content_required and configuration is None,
        ),
        ConfigurationPorts(
            read_configuration,
            write_configuration,
            recover_configuration,
        ),
    )
    if isinstance(loaded, Err):
        return loaded
    if configuration is None:
        effective = loaded.value.effective
    else:
        prospective = apply_configuration(
            configuration,
            RuntimeOverrides(),
            loaded.value.effective.policy,
        )
        if isinstance(prospective, Err):
            return prospective
        effective = prospective.value
    observed_health: Mapping[SourceAlias, SourceHealth] = {}
    if observe_freshness and not offline:
        observed_health = {
            source.alias: observe_configured_source(
                source,
                data_root=config_paths.data_root,
                mode=effective.configuration.sync.mode,
            )
            for source in effective.configuration.sources
            if source.enabled
        }
    elif refresh_sources and not offline:
        for source in effective.configuration.sources:
            if not source.enabled:
                continue
            refreshed = sync_configured_source(source, data_root=config_paths.data_root)
            if isinstance(refreshed, Err):
                return refreshed
    now = int(time.time())
    states = []
    graph_sources = []
    registry_sources = []
    store_paths = object_store_paths(config_paths.data_root)
    for order, configured in enumerate(
        source for source in effective.configuration.sources if source.enabled
    ):
        paths = source_store_paths(config_paths.data_root, source_instance_id(configured))
        health = observed_health.get(configured.alias)
        if health is None:
            health = source_status(
                SourceStatusRequest(
                    CurrentSourceRequest(paths, configured.alias),
                    now,
                    effective.configuration.sync.max_age_seconds,
                ),
                read_current_source,
            )
        states.append(MarketplaceSourceState(configured, health, order))
        if health.current is None:
            continue
        if configured.kind is SourceKind.REGISTRY_GIT:
            registry_sources.append((configured, health.current))
        projected = _project_graph_source(configured, health.current, store_paths)
        if isinstance(projected, Err):
            return projected
        graph_sources.append(projected.value.graph)
    graph = compile_marketplace_graph(
        tuple(graph_sources),
        available_capabilities=_CAPABILITIES,
    )
    if isinstance(graph, Err):
        return graph
    catalog = build_marketplace(graph.value, effective, tuple(states))
    if isinstance(catalog, Err):
        return catalog
    security = _registry_security_evidence(catalog.value, tuple(registry_sources), now=now)
    location = InstallLocation(
        os.path.abspath(project or os.getcwd()),
        home,
        config_paths.data_root,
    )
    context = ConsumerContext(
        catalog.value,
        effective,
        builtin(),
        location,
        store_paths,
        security,
    )
    # Approved content is vendored in the registry snapshot itself, so nothing has to be fetched
    # from a third repository before an install: `io.configured_installation` materializes the
    # exact approved object.  The default port is therefore the honest one.
    return Ok(ConsumerApplicationService(context, LocalConsumerAdapter()))


__all__ = [
    "CONSUMER_RUNTIME_INVALID",
    "load_local_consumer_service",
    "load_read_only_marketplace",
]
