"""Pure Maintainer Mode screen identities and forward navigation.

The catalog is separate from the consumer catalog because the product makes visibility of the
whole maintainer surface an explicit preference boundary.  Both catalogs still travel through the
same application session and reducer; this module introduces no second UI state machine.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from agent_artifacts.application.maintainer import SourceScan
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.sources.model import HealthStatus, SourceHealth

__all__ = [
    "MAINTAINER_SCREENS",
    "MaintainerDashboardView",
    "MaintainerScreen",
    "MaintainerSourceStatus",
    "MaintainerSourceView",
    "MaintainerViews",
    "maintainer_navigation_targets",
    "project_maintainer_dashboard",
    "project_maintainer_source",
]


class MaintainerScreen(str, Enum):
    """The accepted Maintainer Mode screen catalog, numbered 30 through 53."""

    DASHBOARD = "30-maintainer-dashboard"
    SOURCES = "31-sources"
    SOURCE_DETAILS = "32-source-details"
    SOURCE_SYNC = "33-source-sync"
    SOURCE_SYNC_RESULT = "34-source-sync-result"
    CANDIDATES = "35-candidates"
    CANDIDATE_DETAILS = "36-candidate-details"
    CANDIDATE_DIFF = "37-candidate-diff"
    VALIDATION = "38-validation"
    VALIDATION_DETAILS = "39-validation-details"
    POLICY_REVIEW = "40-policy-review"
    PROMOTION_REVIEW = "41-promotion-review"
    PROMOTION_MODE = "42-promotion-mode"
    REGISTRY_DIFF = "43-registry-diff"
    REGISTRY_VALIDATION = "44-registry-validation"
    REGISTRY_COMMIT = "45-registry-commit"
    REGISTRY = "46-registry-maintainer"
    BULK_PROMOTION = "47-bulk-promotion"
    CANDIDATE_LIFECYCLE = "48-candidate-lifecycle"
    PROVENANCE = "49-provenance"
    VERSION_CONFLICT = "50-version-conflict"
    COLLECTION_CANDIDATES = "51-collection-candidates"
    COLLECTION_VALIDATION = "52-collection-validation"
    CANDIDATE_FILTERS = "53-candidate-filters"


MAINTAINER_SCREENS: tuple[MaintainerScreen, ...] = tuple(MaintainerScreen)


class MaintainerSourceStatus(str, Enum):
    DISABLED = "disabled"
    SYNCED = "synced"
    STALE = "stale"
    NOT_SYNCHRONIZED = "not-synchronized"
    ATTENTION = "attention"


@dataclass(frozen=True, slots=True)
class MaintainerSourceView:
    """One authoring Source and the Candidate observation made from its pinned snapshot."""

    alias: str
    kind: str
    location: str
    branch: str | None
    enabled: bool
    status: MaintainerSourceStatus
    revision: str | None
    last_successful_sync: int | None
    manifest_count: int
    candidate_states: tuple[tuple[CandidateState, int], ...]
    target_registries: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        lines = (
            self.alias,
            self.kind,
            self.location,
            *(self.target_registries),
            *(self.diagnostics),
        )
        if (
            not self.alias
            or not self.kind
            or not self.location
            or any(
                not isinstance(item, str) or any(char in item for char in "\r\n") for item in lines
            )
            or (
                self.branch is not None
                and (not self.branch or any(char in self.branch for char in "\r\n"))
            )
            or not isinstance(self.enabled, bool)
            or not isinstance(self.status, MaintainerSourceStatus)
            or (
                self.revision is not None
                and (not self.revision or any(char in self.revision for char in "\r\n"))
            )
            or (
                self.last_successful_sync is not None
                and (
                    not isinstance(self.last_successful_sync, int)
                    or isinstance(self.last_successful_sync, bool)
                    or self.last_successful_sync < 0
                )
            )
            or not isinstance(self.manifest_count, int)
            or isinstance(self.manifest_count, bool)
            or self.manifest_count < 0
            or any(
                not isinstance(state, CandidateState)
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count <= 0
                for state, count in self.candidate_states
            )
            or len({state for state, _ in self.candidate_states}) != len(self.candidate_states)
            or len(set(self.target_registries)) != len(self.target_registries)
        ):
            raise ValueError("maintainer Source view is invalid")
        if self.manifest_count != self.candidate_count:
            raise ValueError("maintainer Source manifest and active Candidate counts disagree")

    @property
    def candidate_count(self) -> int:
        return sum(count for _, count in self.candidate_states)

    def count(self, state: CandidateState) -> int:
        return next((count for found, count in self.candidate_states if found is state), 0)

    @property
    def ready_count(self) -> int:
        return self.count(CandidateState.READY)

    @property
    def invalid_count(self) -> int:
        return self.count(CandidateState.INVALID)


@dataclass(frozen=True, slots=True)
class MaintainerDashboardView:
    source_count: int
    candidate_count: int
    validation_failure_count: int
    ready_count: int
    recent_activity: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        counts = (
            self.source_count,
            self.candidate_count,
            self.validation_failure_count,
            self.ready_count,
        )
        if (
            any(
                not isinstance(count, int) or isinstance(count, bool) or count < 0
                for count in counts
            )
            or self.validation_failure_count > self.candidate_count
            or self.ready_count > self.candidate_count
            or any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in self.recent_activity
            )
        ):
            raise ValueError("maintainer Dashboard view is invalid")


@dataclass(frozen=True, slots=True)
class MaintainerViews:
    """The Maintainer projections composed once and read by the shared screen source."""

    dashboard: MaintainerDashboardView
    sources: tuple[MaintainerSourceView, ...]

    def __post_init__(self) -> None:
        aliases = tuple(source.alias for source in self.sources)
        if (
            not isinstance(self.dashboard, MaintainerDashboardView)
            or any(not isinstance(source, MaintainerSourceView) for source in self.sources)
            or len(set(aliases)) != len(aliases)
            or self.dashboard.source_count != len(self.sources)
            or self.dashboard.candidate_count
            != sum(source.candidate_count for source in self.sources)
            or self.dashboard.validation_failure_count
            != sum(source.invalid_count for source in self.sources)
            or self.dashboard.ready_count != sum(source.ready_count for source in self.sources)
        ):
            raise ValueError("composed Maintainer views disagree")
        object.__setattr__(
            self, "sources", tuple(sorted(self.sources, key=lambda item: item.alias))
        )

    def source(self, alias: str) -> MaintainerSourceView | None:
        return next((source for source in self.sources if source.alias == alias), None)


def _source_status(configured: ConfiguredSource, health: SourceHealth) -> MaintainerSourceStatus:
    if not configured.enabled:
        return MaintainerSourceStatus.DISABLED
    if health.status is HealthStatus.HEALTHY:
        return MaintainerSourceStatus.SYNCED
    if health.status is HealthStatus.STALE:
        return MaintainerSourceStatus.STALE
    if health.status in {HealthStatus.MISSING, HealthStatus.NOT_SYNCHRONIZED}:
        return MaintainerSourceStatus.NOT_SYNCHRONIZED
    return MaintainerSourceStatus.ATTENTION


def project_maintainer_source(
    configured: ConfiguredSource,
    health: SourceHealth,
    scan: SourceScan | None = None,
) -> MaintainerSourceView:
    """Bind configuration, durable Source health and one matching non-mutating Source Scan."""

    if (
        not isinstance(configured, ConfiguredSource)
        or configured.kind is SourceKind.REGISTRY_GIT
        or not isinstance(health, SourceHealth)
        or not (scan is None or isinstance(scan, SourceScan))
    ):
        raise ValueError("maintainer Source projection needs an authoring Source")
    current = health.current
    if current is not None and current.candidate.alias != configured.alias:
        raise ValueError("maintainer Source health belongs to another configured Source")
    if scan is not None:
        if (
            scan.source_alias != configured.alias
            or current is None
            or scan.revision != current.candidate.resolved_revision
        ):
            raise ValueError("maintainer Source scan does not bind the current pinned Source")
    counts = Counter(bundle.candidate.state for bundle in (() if scan is None else scan.active))
    candidate_states = tuple((state, counts[state]) for state in CandidateState if counts[state])
    registries = tuple(
        sorted(
            {
                bundle.candidate.target_registry.value
                for bundle in (() if scan is None else scan.active)
            }
        )
    )
    return MaintainerSourceView(
        configured.alias.value,
        configured.kind.value,
        configured.location,
        configured.ref,
        configured.enabled,
        _source_status(configured, health),
        None if current is None else current.candidate.resolved_revision,
        None if current is None else current.published_at_epoch_seconds,
        0 if scan is None else scan.manifest_count,
        candidate_states,
        registries,
        tuple(redact_text(item.message) for item in health.diagnostics),
    )


def project_maintainer_dashboard(
    sources: tuple[MaintainerSourceView, ...],
    *,
    recent_activity: tuple[str, ...] = (),
) -> MaintainerDashboardView:
    if any(not isinstance(source, MaintainerSourceView) for source in sources) or len(
        {source.alias for source in sources}
    ) != len(sources):
        raise ValueError("maintainer Dashboard needs unique Source views")
    return MaintainerDashboardView(
        len(sources),
        sum(source.candidate_count for source in sources),
        sum(source.invalid_count for source in sources),
        sum(source.ready_count for source in sources),
        recent_activity,
    )


_NAVIGATION: dict[MaintainerScreen, tuple[MaintainerScreen, ...]] = {
    MaintainerScreen.DASHBOARD: (
        MaintainerScreen.SOURCES,
        MaintainerScreen.CANDIDATES,
        MaintainerScreen.REGISTRY,
    ),
    MaintainerScreen.SOURCES: (
        MaintainerScreen.SOURCE_DETAILS,
        MaintainerScreen.SOURCE_SYNC,
    ),
    MaintainerScreen.SOURCE_DETAILS: (MaintainerScreen.SOURCE_SYNC,),
    MaintainerScreen.SOURCE_SYNC: (MaintainerScreen.SOURCE_SYNC_RESULT,),
    MaintainerScreen.SOURCE_SYNC_RESULT: (MaintainerScreen.CANDIDATES,),
    MaintainerScreen.CANDIDATES: (
        MaintainerScreen.CANDIDATE_DETAILS,
        MaintainerScreen.BULK_PROMOTION,
        MaintainerScreen.COLLECTION_CANDIDATES,
        MaintainerScreen.CANDIDATE_FILTERS,
    ),
    MaintainerScreen.CANDIDATE_DETAILS: (
        MaintainerScreen.CANDIDATE_DIFF,
        MaintainerScreen.VALIDATION,
        MaintainerScreen.CANDIDATE_LIFECYCLE,
        MaintainerScreen.PROVENANCE,
        MaintainerScreen.VERSION_CONFLICT,
    ),
    MaintainerScreen.CANDIDATE_DIFF: (MaintainerScreen.VALIDATION,),
    MaintainerScreen.VALIDATION: (
        MaintainerScreen.VALIDATION_DETAILS,
        MaintainerScreen.POLICY_REVIEW,
    ),
    MaintainerScreen.VALIDATION_DETAILS: (MaintainerScreen.POLICY_REVIEW,),
    MaintainerScreen.POLICY_REVIEW: (MaintainerScreen.PROMOTION_REVIEW,),
    MaintainerScreen.PROMOTION_REVIEW: (MaintainerScreen.PROMOTION_MODE,),
    MaintainerScreen.PROMOTION_MODE: (MaintainerScreen.REGISTRY_DIFF,),
    MaintainerScreen.REGISTRY_DIFF: (MaintainerScreen.REGISTRY_VALIDATION,),
    MaintainerScreen.REGISTRY_VALIDATION: (MaintainerScreen.REGISTRY_COMMIT,),
    MaintainerScreen.REGISTRY_COMMIT: (MaintainerScreen.REGISTRY,),
    MaintainerScreen.REGISTRY: (),
    MaintainerScreen.BULK_PROMOTION: (MaintainerScreen.REGISTRY_DIFF,),
    MaintainerScreen.CANDIDATE_LIFECYCLE: (MaintainerScreen.PROVENANCE,),
    MaintainerScreen.PROVENANCE: (),
    MaintainerScreen.VERSION_CONFLICT: (),
    MaintainerScreen.COLLECTION_CANDIDATES: (MaintainerScreen.COLLECTION_VALIDATION,),
    MaintainerScreen.COLLECTION_VALIDATION: (MaintainerScreen.VALIDATION,),
    MaintainerScreen.CANDIDATE_FILTERS: (MaintainerScreen.CANDIDATES,),
}


def maintainer_navigation_targets(screen: MaintainerScreen) -> tuple[MaintainerScreen, ...]:
    """Accepted Maintainer forward routes, independent of terminal and machine state."""

    if not isinstance(screen, MaintainerScreen):
        raise ValueError("maintainer navigation needs a maintainer screen")
    return _NAVIGATION[screen]
