"""Read-only composition of offline readiness from configured durable state."""

from __future__ import annotations

from agent_artifacts.application.offline_readiness import (
    OfflineCapabilityState,
    OfflineReadiness,
    OfflineSourceReadiness,
    artifact_readiness,
)
from agent_artifacts.application.promotion import load_registry_versions
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.configuration.policy import EffectiveConfiguration
from agent_artifacts.domain.registry import PublicationStage, RegistryLifecycle
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.authoring import read_package_description
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)

from .configured_installation import object_candidate_from_registry_snapshot
from .source_store import read_current_source


def read_offline_readiness(
    effective: EffectiveConfiguration,
    *,
    data_root: str,
) -> Result[OfflineReadiness]:
    """Observe each enabled source once; never fetch, publish or invoke a package manager."""

    sources: list[OfflineSourceReadiness] = []
    for configured in effective.configuration.sources:
        if not configured.enabled:
            continue
        paths = source_store_paths(data_root, source_instance_id(configured))
        current = read_current_source(CurrentSourceRequest(paths, configured.alias))
        if isinstance(current, Err):
            return current
        if current.value is None:
            sources.append(
                OfflineSourceReadiness(
                    configured.alias,
                    OfflineCapabilityState.MISSING,
                )
            )
            continue
        if configured.kind is not SourceKind.REGISTRY_GIT:
            sources.append(
                OfflineSourceReadiness(
                    configured.alias,
                    OfflineCapabilityState.CACHED,
                )
            )
            continue

        snapshot = current.value.candidate.snapshot
        loaded = load_registry_versions(snapshot)
        if isinstance(loaded, Err):
            return loaded
        artifacts = []
        for version in loaded.value:
            if (
                version.publication is not PublicationStage.PUBLISHED
                or version.lifecycle is not RegistryLifecycle.PUBLISHED
                or version.coordinate.artifact.kind == "collection"
            ):
                continue
            candidate = object_candidate_from_registry_snapshot(snapshot, version)
            if isinstance(candidate, Err):
                artifacts.append(
                    artifact_readiness(
                        version.coordinate,
                        canonical_payload_cached=False,
                        declares_runtime_dependencies=None,
                    )
                )
                continue
            description = read_package_description(candidate.value.entries)
            if isinstance(description, Err):
                return description
            artifacts.append(
                artifact_readiness(
                    version.coordinate,
                    canonical_payload_cached=True,
                    declares_runtime_dependencies=description.value.dependencies is not None,
                )
            )
        sources.append(
            OfflineSourceReadiness(
                configured.alias,
                OfflineCapabilityState.CACHED,
                tuple(artifacts),
            )
        )
    return Ok(OfflineReadiness(tuple(sources)))


__all__ = ["read_offline_readiness"]
