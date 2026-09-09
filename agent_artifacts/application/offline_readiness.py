"""Pure projection of the three independent offline-installability capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent_artifacts.domain.identifiers import ArtifactCoordinate, SourceAlias


class OfflineCapabilityState(str, Enum):
    """What durable local evidence permits AART to say about one capability."""

    CACHED = "cached"
    MISSING = "missing"
    NOT_REQUIRED = "not-required"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class OfflineArtifactReadiness:
    coordinate: ArtifactCoordinate
    metadata: OfflineCapabilityState
    canonical_payload: OfflineCapabilityState
    runtime_dependencies: OfflineCapabilityState

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coordinate, ArtifactCoordinate)
            or self.metadata is not OfflineCapabilityState.CACHED
            or self.canonical_payload
            not in {OfflineCapabilityState.CACHED, OfflineCapabilityState.MISSING}
            or self.runtime_dependencies
            not in {OfflineCapabilityState.NOT_REQUIRED, OfflineCapabilityState.UNVERIFIED}
            or (
                self.canonical_payload is OfflineCapabilityState.MISSING
                and self.runtime_dependencies is OfflineCapabilityState.NOT_REQUIRED
            )
        ):
            raise ValueError("offline artifact readiness is inconsistent")


@dataclass(frozen=True, slots=True)
class OfflineSourceReadiness:
    alias: SourceAlias
    metadata: OfflineCapabilityState
    artifacts: tuple[OfflineArtifactReadiness, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.alias, SourceAlias)
            or self.metadata not in {OfflineCapabilityState.CACHED, OfflineCapabilityState.MISSING}
            or any(not isinstance(item, OfflineArtifactReadiness) for item in self.artifacts)
            or (self.metadata is OfflineCapabilityState.MISSING and self.artifacts)
            or any(item.coordinate.source != self.alias for item in self.artifacts)
        ):
            raise ValueError("offline source readiness is inconsistent")
        object.__setattr__(
            self,
            "artifacts",
            tuple(sorted(self.artifacts, key=lambda item: str(item.coordinate))),
        )


@dataclass(frozen=True, slots=True)
class OfflineReadiness:
    sources: tuple[OfflineSourceReadiness, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(item, OfflineSourceReadiness) for item in self.sources):
            raise ValueError("offline readiness needs source observations")
        aliases = tuple(item.alias for item in self.sources)
        if len(set(aliases)) != len(aliases):
            raise ValueError("offline readiness source aliases must be unique")
        object.__setattr__(
            self, "sources", tuple(sorted(self.sources, key=lambda item: item.alias))
        )


def artifact_readiness(
    coordinate: ArtifactCoordinate,
    *,
    canonical_payload_cached: bool,
    declares_runtime_dependencies: bool | None,
) -> OfflineArtifactReadiness:
    """Project only what the three observations independently establish."""

    payload = (
        OfflineCapabilityState.CACHED
        if canonical_payload_cached
        else OfflineCapabilityState.MISSING
    )
    dependencies = (
        OfflineCapabilityState.NOT_REQUIRED
        if canonical_payload_cached and declares_runtime_dependencies is False
        else OfflineCapabilityState.UNVERIFIED
    )
    return OfflineArtifactReadiness(
        coordinate,
        OfflineCapabilityState.CACHED,
        payload,
        dependencies,
    )


def offline_readiness_to_data(readiness: OfflineReadiness) -> dict[str, object]:
    return {
        "sources": [
            {
                "alias": source.alias.value,
                "metadata": source.metadata.value,
                "artifacts": [
                    {
                        "coordinate": str(artifact.coordinate),
                        "metadata": artifact.metadata.value,
                        "canonical_payload": artifact.canonical_payload.value,
                        "runtime_dependencies": artifact.runtime_dependencies.value,
                    }
                    for artifact in source.artifacts
                ],
            }
            for source in readiness.sources
        ]
    }


__all__ = [
    "OfflineArtifactReadiness",
    "OfflineCapabilityState",
    "OfflineReadiness",
    "OfflineSourceReadiness",
    "artifact_readiness",
    "offline_readiness_to_data",
]
