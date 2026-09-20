"""Read-only composition of offline readiness from configured durable state."""

from __future__ import annotations

from aart_cli.application.offline_readiness import (
    OfflineCapabilityState,
    OfflineReadiness,
    OfflineSourceReadiness,
    artifact_readiness,
)
from aart_cli.application.promotion import load_configured_registry_versions
from aart_cli.configuration.policy import EffectiveConfiguration
from aart_cli.domain.registry import RegistryLifecycle
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.authoring import read_package_description
from aart_cli.sources.model import (
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
        if not configured.is_registry:
            sources.append(
                OfflineSourceReadiness(
                    configured.alias,
                    OfflineCapabilityState.CACHED,
                )
            )
            continue

        snapshot = current.value.candidate.snapshot
        loaded = load_configured_registry_versions(snapshot, configured.alias)
        if isinstance(loaded, Err):
            return loaded
        artifacts = []
        for version in loaded.value:
            # Everything read here is on the branch this consumer configured, which is what
            # published means (INV-242, D-207); what a registry withdrew still has to be skipped.
            if (
                version.lifecycle is not RegistryLifecycle.PUBLISHED
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
