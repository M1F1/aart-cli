"""Pure Maintainer Mode screen identities and forward navigation.

The catalog is separate from the consumer catalog because the product makes visibility of the
whole maintainer surface an explicit preference boundary.  Both catalogs still travel through the
same application session and reducer; this module introduces no second UI state machine.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from difflib import unified_diff
from enum import Enum

from agent_artifacts.application.maintainer import CandidateBundle, SourceScan
from agent_artifacts.application.maintainer_sync import (
    PreparedSourceSync,
    SourceSyncExecutionResult,
)
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.candidates import CandidateState, semantic_candidate_diff
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.inputs import ConfigInput, RuntimeInput, SecretInput
from agent_artifacts.domain.python_runtime import (
    PyProjectSpec,
    RequirementsFile,
    spec_descriptor_path,
)
from agent_artifacts.domain.result import Err
from agent_artifacts.protocol.authoring import read_package_description
from agent_artifacts.protocol.native_tree import SnapshotEntry, SnapshotEntryKind
from agent_artifacts.sources.model import HealthStatus, SourceHealth

__all__ = [
    "MAINTAINER_SCREENS",
    "MaintainerDashboardView",
    "MaintainerCandidateFileChangeView",
    "MaintainerCandidateFilter",
    "MaintainerCandidateInputView",
    "MaintainerCandidateSemanticChangeView",
    "MaintainerCandidateView",
    "MaintainerScreen",
    "MaintainerSourceStatus",
    "MaintainerSourceSyncResultView",
    "MaintainerSourceSyncReviewView",
    "MaintainerSourceView",
    "MaintainerViews",
    "filter_maintainer_candidates",
    "maintainer_navigation_targets",
    "project_maintainer_dashboard",
    "project_maintainer_candidates",
    "project_maintainer_source",
    "project_source_sync_result",
    "project_source_sync_review",
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
class MaintainerSourceSyncReviewView:
    alias: str
    kind: str
    location: str
    branch: str | None
    target_registry: str
    current_revision: str | None
    candidate_count: int
    approved_revision: str
    approved_snapshot: str
    review_digest: str

    def __post_init__(self) -> None:
        values = (
            self.alias,
            self.kind,
            self.location,
            self.target_registry,
            self.approved_revision,
            self.approved_snapshot,
            self.review_digest,
        )
        if (
            any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in values
            )
            or (
                self.branch is not None
                and (not self.branch or any(character in self.branch for character in "\r\n"))
            )
            or (
                self.current_revision is not None
                and (
                    not self.current_revision
                    or any(character in self.current_revision for character in "\r\n")
                )
            )
            or not isinstance(self.candidate_count, int)
            or isinstance(self.candidate_count, bool)
            or self.candidate_count < 0
        ):
            raise ValueError("Maintainer Source Sync review view is invalid")


@dataclass(frozen=True, slots=True)
class MaintainerSourceSyncResultView:
    alias: str
    target_registry: str
    disposition: str
    revision: str
    manifest_count: int
    candidate_states: tuple[tuple[CandidateState, int], ...]
    review_digest: str

    def __post_init__(self) -> None:
        if (
            any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in (
                    self.alias,
                    self.target_registry,
                    self.disposition,
                    self.revision,
                    self.review_digest,
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
            or sum(count for _, count in self.candidate_states) != self.manifest_count
        ):
            raise ValueError("Maintainer Source Sync result view is invalid")

    @property
    def candidate_count(self) -> int:
        return sum(count for _, count in self.candidate_states)


@dataclass(frozen=True, slots=True)
class MaintainerCandidateInputView:
    id: str
    kind: str
    label: str
    required: bool
    example: str | None = None
    format_hint: str | None = None
    obtain_from: str | None = None
    obtain_from_url: str | None = None

    def __post_init__(self) -> None:
        required = (self.id, self.kind, self.label)
        optional = (self.example, self.format_hint, self.obtain_from, self.obtain_from_url)
        if (
            any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in required
            )
            or self.kind not in {"CONFIG", "SECRET"}
            or not isinstance(self.required, bool)
            or any(
                item is not None
                and (
                    not isinstance(item, str)
                    or not item
                    or any(character in item for character in "\r\n")
                )
                for item in optional
            )
            or (self.obtain_from is None) != (self.obtain_from_url is None)
            or (self.kind == "SECRET" and self.example is not None)
        ):
            raise ValueError("Maintainer Candidate input view is invalid")


@dataclass(frozen=True, slots=True, order=True)
class MaintainerCandidateSemanticChangeView:
    field: str
    before: str | None
    after: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.field, str)
            or not self.field
            or any(character in self.field for character in "\r\n")
            or any(
                item is not None
                and (not isinstance(item, str) or any(character in item for character in "\r\n"))
                for item in (self.before, self.after)
            )
        ):
            raise ValueError("Maintainer Candidate semantic change is invalid")


@dataclass(frozen=True, slots=True)
class MaintainerCandidateFileChangeView:
    path: str
    status: str
    diff: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, str)
            or not self.path
            or any(character in self.path for character in "\r\n")
            or self.status not in {"added", "modified", "removed"}
            or any(
                not isinstance(line, str) or any(character in line for character in "\r")
                for line in self.diff
            )
            or len(self.diff) > 200
        ):
            raise ValueError("Maintainer Candidate file change is invalid")


@dataclass(frozen=True, slots=True)
class MaintainerCandidateView:
    id: str
    state: CandidateState
    coordinate: str
    artifact: str
    version: str
    kind: str
    source_alias: str
    source_location: str
    source_revision: str
    manifest_path: str
    input_digest: str
    payload_digest: str
    canonical_digest: str
    target_registry: str
    runtime: str | None
    transport: str | None
    inputs: tuple[MaintainerCandidateInputView, ...]
    dependency_descriptor: str | None
    findings: tuple[str, ...]
    previous: str | None
    successor: str | None
    rejection_reason: str | None
    baseline: str
    semantic_changes: tuple[MaintainerCandidateSemanticChangeView, ...]
    file_changes: tuple[MaintainerCandidateFileChangeView, ...]

    def __post_init__(self) -> None:
        required = (
            self.id,
            self.coordinate,
            self.artifact,
            self.version,
            self.kind,
            self.source_alias,
            self.source_location,
            self.source_revision,
            self.manifest_path,
            self.input_digest,
            self.payload_digest,
            self.canonical_digest,
            self.target_registry,
            self.baseline,
        )
        optional = (
            self.runtime,
            self.transport,
            self.dependency_descriptor,
            self.previous,
            self.successor,
            self.rejection_reason,
        )
        if (
            any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in required
            )
            or not isinstance(self.state, CandidateState)
            or any(
                item is not None
                and (
                    not isinstance(item, str)
                    or not item
                    or any(character in item for character in "\r\n")
                )
                for item in optional
            )
            or any(not isinstance(item, MaintainerCandidateInputView) for item in self.inputs)
            or any(not isinstance(item, str) or not item for item in self.findings)
            or any(
                not isinstance(item, MaintainerCandidateSemanticChangeView)
                for item in self.semantic_changes
            )
            or any(
                not isinstance(item, MaintainerCandidateFileChangeView)
                for item in self.file_changes
            )
        ):
            raise ValueError("Maintainer Candidate view is invalid")


_MAX_FILE_DIFF_BYTES = 256 * 1024
_MAX_FILE_DIFF_LINES = 200
_MAX_FILE_DIFF_LINE = 512


def _input_view(item: RuntimeInput) -> MaintainerCandidateInputView:
    guidance = item.guidance
    obtain = None if guidance is None else guidance.obtain_from
    return MaintainerCandidateInputView(
        item.id.value,
        "SECRET" if isinstance(item, SecretInput) else "CONFIG",
        item.id.value if guidance is None else guidance.label,
        item.required,
        None if guidance is None or isinstance(item, SecretInput) else guidance.example,
        None if guidance is None else guidance.format_hint,
        None if obtain is None else obtain.label,
        None if obtain is None else obtain.url,
    )


def _dependency_label(bundle: CandidateBundle) -> str | None:
    described = read_package_description(bundle.artifact.canonical_entries)
    if isinstance(described, Err):
        raise ValueError(described.diagnostics[0].message)
    dependency = described.value.dependencies
    if dependency is None:
        return None
    if isinstance(dependency, RequirementsFile):
        return f"requirements: {dependency.path}"
    assert isinstance(dependency, PyProjectSpec)
    suffix = (
        "" if dependency.lock is None else f"; {dependency.lock_format} lock: {dependency.lock}"
    )
    return f"pyproject: {dependency.pyproject}{suffix}"


def _description(bundle: CandidateBundle):
    described = read_package_description(bundle.artifact.canonical_entries)
    if isinstance(described, Err):
        raise ValueError(described.diagnostics[0].message)
    return described.value


def _entry_map(bundle: CandidateBundle) -> dict[str, SnapshotEntry]:
    return {
        str(entry.path): entry
        for entry in bundle.artifact.canonical_entries
        if entry.kind is SnapshotEntryKind.FILE
    }


def _safe_file_text(content: bytes) -> list[str] | None:
    if len(content) > _MAX_FILE_DIFF_BYTES:
        return None
    try:
        return content.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None


def _file_changes(
    before: CandidateBundle | None,
    after: CandidateBundle,
) -> tuple[MaintainerCandidateFileChangeView, ...]:
    left = {} if before is None else _entry_map(before)
    right = _entry_map(after)
    changes = []
    remaining = _MAX_FILE_DIFF_LINES
    for path in sorted(set(left) | set(right)):
        old = left.get(path)
        new = right.get(path)
        if (
            old is not None
            and new is not None
            and (old.content == new.content and old.executable == new.executable)
        ):
            continue
        status = "added" if old is None else "removed" if new is None else "modified"
        old_lines = [] if old is None else _safe_file_text(old.content)
        new_lines = [] if new is None else _safe_file_text(new.content)
        diff: tuple[str, ...]
        if remaining <= 0:
            diff = ()
        elif old_lines is None or new_lines is None:
            diff = ("binary or oversized content differs",)
        else:
            raw = unified_diff(
                old_lines,
                new_lines,
                fromfile=f"before/{path}",
                tofile=f"after/{path}",
                lineterm="",
            )
            diff = tuple(
                redact_text(line[:_MAX_FILE_DIFF_LINE]) for line in raw if "\r" not in line
            )[:remaining]
        remaining -= len(diff)
        changes.append(MaintainerCandidateFileChangeView(path, status, diff))
    return tuple(changes)


def _descriptor_content(bundle: CandidateBundle) -> tuple[str, str] | None:
    description = _description(bundle)
    dependency = description.dependencies
    if dependency is None:
        return None
    path = spec_descriptor_path(dependency)
    entry = _entry_map(bundle).get(f"payload/{path}")
    if entry is None or len(entry.content) > _MAX_FILE_DIFF_BYTES:
        return (path, "binary or oversized descriptor")
    try:
        content = " | ".join(entry.content.decode("utf-8").splitlines())
    except UnicodeDecodeError:
        content = "binary or oversized descriptor"
    return (path, redact_text(content[:_MAX_FILE_DIFF_LINE]))


def _input_summary(item: RuntimeInput) -> str:
    kind = "SECRET" if isinstance(item, SecretInput) else "CONFIG"
    guidance = item.guidance
    details = [kind, item.id.value]
    if guidance is not None:
        if guidance.example is not None and isinstance(item, ConfigInput):
            details.append(f"example: {guidance.example}")
        if guidance.obtain_from is not None:
            details.append(f"obtain from: {guidance.obtain_from.label}")
    return " · ".join(details)


def _semantic_changes(
    before: CandidateBundle | None,
    after: CandidateBundle,
) -> tuple[MaintainerCandidateSemanticChangeView, ...]:
    if before is None:
        return (
            MaintainerCandidateSemanticChangeView(
                "candidate", None, str(after.candidate.artifact.coordinate)
            ),
        )
    changes = [
        MaintainerCandidateSemanticChangeView(item.field.replace("_", " "), item.before, item.after)
        for item in semantic_candidate_diff(before.candidate, after.candidate)
    ]
    if (
        before.candidate.artifact.provenance.revision
        != after.candidate.artifact.provenance.revision
    ):
        changes.append(
            MaintainerCandidateSemanticChangeView(
                "source revision",
                before.candidate.artifact.provenance.revision,
                after.candidate.artifact.provenance.revision,
            )
        )
    left_description, right_description = _description(before), _description(after)
    left_inputs = {item.id.value: item for item in left_description.inputs}
    right_inputs = {item.id.value: item for item in right_description.inputs}
    for input_id in sorted(set(left_inputs) | set(right_inputs)):
        left = left_inputs.get(input_id)
        right = right_inputs.get(input_id)
        before_summary = None if left is None else _input_summary(left)
        after_summary = None if right is None else _input_summary(right)
        if before_summary != after_summary:
            changes.append(
                MaintainerCandidateSemanticChangeView(
                    f"runtime input {input_id}", before_summary, after_summary
                )
            )
    left_dependency = _descriptor_content(before)
    right_dependency = _descriptor_content(after)
    if left_dependency != right_dependency:
        path = (
            right_dependency[0] if right_dependency is not None else left_dependency[0]  # type: ignore[index]
        )
        changes.append(
            MaintainerCandidateSemanticChangeView(
                f"dependency {path}",
                None if left_dependency is None else left_dependency[1],
                None if right_dependency is None else right_dependency[1],
            )
        )
    return tuple(sorted(set(changes)))


def _candidate_view(bundle: CandidateBundle, history: dict) -> MaintainerCandidateView:
    candidate = bundle.candidate
    previous = None if candidate.previous is None else history.get(candidate.previous)
    description = _description(bundle)
    runtime = description.runtime
    if runtime is not None and description.runtime_version is not None:
        runtime = f"{runtime} {description.runtime_version}"
    transport = None if description.contract is None else description.contract.transport.value
    baseline = (
        "None"
        if previous is None
        else f"Candidate {previous.candidate.artifact.coordinate.version}"
    )
    return MaintainerCandidateView(
        candidate.id.value,
        candidate.state,
        str(candidate.artifact.coordinate),
        str(candidate.artifact.coordinate.artifact),
        str(candidate.artifact.coordinate.version),
        candidate.artifact.kind.value,
        candidate.artifact.coordinate.source.value,
        redact_text(candidate.artifact.provenance.source),
        candidate.artifact.provenance.revision,
        candidate.artifact.provenance.manifest_path,
        str(candidate.artifact.provenance.input_digest),
        str(candidate.artifact.payload_digest),
        str(candidate.canonical_digest),
        candidate.target_registry.value,
        runtime,
        transport,
        tuple(_input_view(item) for item in description.inputs),
        _dependency_label(bundle),
        tuple(
            redact_text(f"{item.severity.value}: {item.code} — {item.message}")
            for item in candidate.findings
        ),
        None if candidate.previous is None else candidate.previous.value,
        None if candidate.successor is None else candidate.successor.value,
        None if candidate.rejection_reason is None else redact_text(candidate.rejection_reason),
        baseline,
        _semantic_changes(previous, bundle),
        _file_changes(previous, bundle),
    )


def project_maintainer_candidates(
    scans: tuple[SourceScan, ...],
) -> tuple[MaintainerCandidateView, ...]:
    if not isinstance(scans, tuple) or any(not isinstance(scan, SourceScan) for scan in scans):
        raise ValueError("Maintainer Candidate projection needs Source Scans")
    all_history = {bundle.candidate.id: bundle for scan in scans for bundle in scan.history}
    if sum(len(scan.history) for scan in scans) != len(all_history):
        raise ValueError("Maintainer Candidate history contains duplicate Candidate IDs")
    projected = tuple(
        _candidate_view(bundle, all_history) for scan in scans for bundle in scan.active
    )
    return tuple(
        sorted(
            projected,
            key=lambda item: (
                item.state.value,
                item.source_alias,
                item.artifact,
                item.version,
                item.id,
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class MaintainerCandidateFilter:
    """What the Candidate list is currently narrowed to, held as state rather than as text.

    Screen 53 edits this value and screen 35 obeys it.  The predicate lives here rather than in a
    renderer because a filtered review has to be reproducible: the same filter over the same
    composed Candidates selects the same rows on any terminal and at either presentation profile.
    """

    states: tuple[CandidateState, ...] = ()
    sources: tuple[str, ...] = ()
    query: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.states, tuple)
            or any(not isinstance(item, CandidateState) for item in self.states)
            or len(set(self.states)) != len(self.states)
            or not isinstance(self.sources, tuple)
            or any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in self.sources
            )
            or len(set(self.sources)) != len(self.sources)
            or not isinstance(self.query, str)
            or any(character in self.query for character in "\r\n")
        ):
            raise ValueError("Maintainer Candidate filter is invalid")
        object.__setattr__(self, "states", tuple(sorted(self.states, key=lambda item: item.value)))
        object.__setattr__(self, "sources", tuple(sorted(self.sources)))

    @property
    def is_empty(self) -> bool:
        return not (self.states or self.sources or self.query)

    def matches(self, candidate: MaintainerCandidateView) -> bool:
        """Whether one projected Candidate survives this filter."""

        if not isinstance(candidate, MaintainerCandidateView):
            raise ValueError("a Maintainer Candidate filter matches projected Candidate views")
        if self.states and candidate.state not in self.states:
            return False
        if self.sources and candidate.source_alias not in self.sources:
            return False
        if not self.query:
            return True
        needle = self.query.casefold()
        return any(
            needle in field.casefold()
            for field in (
                candidate.artifact,
                candidate.version,
                candidate.source_alias,
                candidate.state.value,
                candidate.target_registry,
            )
        )

    def with_query(self, text: str) -> MaintainerCandidateFilter:
        return replace(self, query=text)

    def toggled_state(self, state: CandidateState) -> MaintainerCandidateFilter:
        if not isinstance(state, CandidateState):
            raise ValueError("toggling a Candidate filter needs a Candidate state")
        remaining = tuple(item for item in self.states if item is not state)
        return replace(
            self,
            states=remaining if len(remaining) != len(self.states) else (*self.states, state),
        )

    def toggled_source(self, alias: str) -> MaintainerCandidateFilter:
        if not isinstance(alias, str) or not alias:
            raise ValueError("toggling a Candidate filter needs a Source alias")
        remaining = tuple(item for item in self.sources if item != alias)
        return replace(
            self,
            sources=remaining if len(remaining) != len(self.sources) else (*self.sources, alias),
        )


def filter_maintainer_candidates(
    candidates: tuple[MaintainerCandidateView, ...],
    candidate_filter: MaintainerCandidateFilter,
) -> tuple[MaintainerCandidateView, ...]:
    """The Candidate rows one filter selects, in the order they were composed in."""

    if not isinstance(candidates, tuple) or any(
        not isinstance(item, MaintainerCandidateView) for item in candidates
    ):
        raise ValueError("filtering Maintainer Candidates needs projected Candidate views")
    if not isinstance(candidate_filter, MaintainerCandidateFilter):
        raise ValueError("filtering Maintainer Candidates needs typed filter state")
    return tuple(item for item in candidates if candidate_filter.matches(item))


@dataclass(frozen=True, slots=True)
class MaintainerViews:
    """The Maintainer projections composed once and read by the shared screen source."""

    dashboard: MaintainerDashboardView
    sources: tuple[MaintainerSourceView, ...]
    candidates: tuple[MaintainerCandidateView, ...] | None = None

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
            or (
                self.candidates is not None
                and (
                    any(
                        not isinstance(candidate, MaintainerCandidateView)
                        for candidate in self.candidates
                    )
                    or len({candidate.id for candidate in self.candidates}) != len(self.candidates)
                    or self.dashboard.candidate_count != len(self.candidates)
                )
            )
        ):
            raise ValueError("composed Maintainer views disagree")
        object.__setattr__(
            self, "sources", tuple(sorted(self.sources, key=lambda item: item.alias))
        )
        if self.candidates is not None:
            object.__setattr__(
                self,
                "candidates",
                tuple(
                    sorted(
                        self.candidates,
                        key=lambda item: (
                            item.state.value,
                            item.source_alias,
                            item.artifact,
                            item.version,
                            item.id,
                        ),
                    )
                ),
            )

    def source(self, alias: str) -> MaintainerSourceView | None:
        return next((source for source in self.sources if source.alias == alias), None)

    def candidate(self, candidate_id: str) -> MaintainerCandidateView | None:
        if self.candidates is None:
            return None
        return next(
            (candidate for candidate in self.candidates if candidate.id == candidate_id), None
        )


def project_source_sync_review(prepared: PreparedSourceSync) -> MaintainerSourceSyncReviewView:
    if not isinstance(prepared, PreparedSourceSync):
        raise ValueError("Source Sync review projection needs a prepared Source Sync")
    source = prepared.request.source
    return MaintainerSourceSyncReviewView(
        source.alias.value,
        source.kind.value,
        source.location,
        source.ref,
        prepared.target_registry.value,
        prepared.baseline.revision,
        prepared.baseline.candidate_count,
        prepared.approved.revision,
        str(prepared.approved.snapshot_digest),
        str(prepared.review_digest),
    )


def project_source_sync_result(
    result: SourceSyncExecutionResult,
    *,
    target_registry: SourceAlias,
) -> MaintainerSourceSyncResultView:
    if not isinstance(result, SourceSyncExecutionResult) or not isinstance(
        target_registry, SourceAlias
    ):
        raise ValueError("Source Sync result projection needs a persisted result and target")
    counts = Counter(bundle.candidate.state for bundle in result.scan.active)
    return MaintainerSourceSyncResultView(
        result.scan.source_alias.value,
        target_registry.value,
        result.source.disposition.value,
        result.scan.revision,
        result.scan.manifest_count,
        tuple((state, counts[state]) for state in CandidateState if counts[state]),
        str(result.review_digest),
    )


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
