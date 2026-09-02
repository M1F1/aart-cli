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

from agent_artifacts.application.candidate_validation import (
    CandidateValidation,
    ValidationCheck,
    ValidationOutcome,
    validate_candidate,
)
from agent_artifacts.application.maintainer import CandidateBundle, SourceScan
from agent_artifacts.application.maintainer_promotion import (
    CandidatePromotionExecutionResult,
    PreparedCandidatePromotionTransaction,
    plan_candidate_promotion,
    prepare_candidate_promotion,
    promotion_commit_subject,
)
from agent_artifacts.application.maintainer_sync import (
    ApprovedRegistryState,
    PreparedSourceSync,
    SourceSyncExecutionResult,
)
from agent_artifacts.application.promotion import (
    PromotionAudit,
    load_registry_promotions,
    registry_state_digest,
)
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.candidates import CandidateState, semantic_candidate_diff
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.inputs import ConfigInput, RuntimeInput, SecretInput
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import (
    PyProjectSpec,
    RequirementsFile,
    spec_descriptor_path,
)
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err
from agent_artifacts.protocol.authoring import read_package_description
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SourceSnapshot,
)
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
    "MaintainerPolicyReviewView",
    "MaintainerPromotionReviewView",
    "MaintainerRegistryChangeView",
    "MaintainerRegistryCommitView",
    "MaintainerRegistryDiffView",
    "project_maintainer_registry",
    "MaintainerWorkingTreeView",
    "MaintainerWorkingTreeState",
    "MaintainerRegistryTransactionView",
    "MaintainerRegistryView",
    "MaintainerRegistryValidationView",
    "MaintainerValidationCheckView",
    "MaintainerValidationDetailView",
    "MaintainerValidationRowId",
    "MaintainerValidationView",
    "MaintainerViews",
    "filter_maintainer_candidates",
    "maintainer_navigation_targets",
    "parse_validation_row",
    "project_maintainer_dashboard",
    "project_maintainer_candidates",
    "project_maintainer_policy_review",
    "project_maintainer_promotion_review",
    "project_maintainer_registry_diff",
    "project_maintainer_registry_commit",
    "project_maintainer_registry_validation",
    "project_maintainer_source",
    "project_maintainer_validation",
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
    validations: tuple[MaintainerValidationView, ...] | None = None
    promotions: tuple[MaintainerPromotionReviewView, ...] | None = None
    registry_diffs: tuple[MaintainerRegistryDiffView, ...] | None = None
    registries: tuple[MaintainerRegistryView, ...] | None = None

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
                self.registries is not None
                and (
                    any(
                        not isinstance(registry, MaintainerRegistryView)
                        for registry in self.registries
                    )
                    or len({item.alias for item in self.registries}) != len(self.registries)
                )
            )
            or (
                self.registry_diffs is not None
                and (
                    any(
                        not isinstance(diff, MaintainerRegistryDiffView)
                        for diff in self.registry_diffs
                    )
                    or len({(item.candidate_id, item.mode) for item in self.registry_diffs})
                    != len(self.registry_diffs)
                )
            )
            or (
                self.promotions is not None
                and (
                    any(
                        not isinstance(promotion, MaintainerPromotionReviewView)
                        for promotion in self.promotions
                    )
                    # One review per Candidate *and mode*: both modes are composed here, so
                    # choosing one on screen 42 selects a projection rather than making one.
                    or len({(item.candidate_id, item.mode) for item in self.promotions})
                    != len(self.promotions)
                )
            )
            or (
                self.validations is not None
                and (
                    any(
                        not isinstance(validation, MaintainerValidationView)
                        for validation in self.validations
                    )
                    or len({item.candidate_id for item in self.validations})
                    != len(self.validations)
                )
            )
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

    def validation(self, candidate_id: str) -> MaintainerValidationView | None:
        """The validation run composed for one Candidate, or nothing if none was composed.

        Screens 38 to 40 refuse rather than validate on the spot: a run assembled while drawing
        would be a second, unrecorded judgement of the same Candidate.
        """

        if self.validations is None:
            return None
        return next((item for item in self.validations if item.candidate_id == candidate_id), None)

    def registry(self, alias: str) -> MaintainerRegistryView | None:
        """The registry composed for one alias, refusals included."""

        if self.registries is None:
            return None
        return next((item for item in self.registries if item.alias == alias), None)

    def registry_diff(
        self,
        candidate_id: str,
        mode: PromotionMode = PromotionMode.VENDORED,
    ) -> MaintainerRegistryDiffView | None:
        """The registry transaction composed for one Candidate in one mode, refusals included."""

        if self.registry_diffs is None:
            return None
        return next(
            (
                item
                for item in self.registry_diffs
                if item.candidate_id == candidate_id and item.mode == mode.value
            ),
            None,
        )

    def promotion(
        self,
        candidate_id: str,
        mode: PromotionMode = PromotionMode.VENDORED,
    ) -> MaintainerPromotionReviewView | None:
        """The promotion review composed for one Candidate in one mode, refusals included."""

        if self.promotions is None:
            return None
        return next(
            (
                item
                for item in self.promotions
                if item.candidate_id == candidate_id and item.mode == mode.value
            ),
            None,
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


#: What each named check is called on screen.  The check's own value stays the stable identity.
_VALIDATION_LABELS: dict[ValidationCheck, str] = {
    ValidationCheck.MANIFEST_SCHEMA: "Manifest schema",
    ValidationCheck.PAYLOAD_BOUNDARIES: "Payload boundaries",
    ValidationCheck.SPECIAL_FILES: "No symlinks / special files",
    ValidationCheck.RUNTIME_DESCRIPTOR: "Runtime descriptor",
    ValidationCheck.DEPENDENCY_DESCRIPTOR: "Dependency descriptor",
    ValidationCheck.INPUT_DEFINITIONS: "Input definitions",
    ValidationCheck.SECRET_METADATA: "Secret metadata",
    ValidationCheck.POLICY: "Policy",
    ValidationCheck.SECURITY: "Security checks",
    ValidationCheck.LIVE_ACCEPTANCE: "Live acceptance",
}

_CANDIDATE_ID_DIGITS = frozenset("0123456789abcdef")


@dataclass(frozen=True, slots=True)
class MaintainerValidationRowId:
    """What screen 39 is about: one named check of one Candidate, not either alone.

    A check name alone is ambiguous across Candidates and a Candidate ID alone cannot open one
    check, so the row identity is the pair.  Keeping it parsed and typed rather than splitting a
    string inside a renderer is what lets screens 39 and 40 be entered directly and still know what
    they are showing.
    """

    candidate_id: str
    check: ValidationCheck

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_id, str)
            or len(self.candidate_id) != 64
            or set(self.candidate_id) - _CANDIDATE_ID_DIGITS
            or not isinstance(self.check, ValidationCheck)
        ):
            raise ValueError("a validation row is a Candidate ID and a named check")

    def __str__(self) -> str:
        return f"{self.candidate_id}:{self.check.value}"


def parse_validation_row(value: str) -> MaintainerValidationRowId | None:
    """One row identity read back from the focus string, or nothing if it is not one.

    Returning nothing rather than raising is deliberate: the focus is whatever the previous screen
    put there, and a screen that cannot recognise it must refuse in the frame rather than crash.
    """

    if not isinstance(value, str):
        return None
    candidate_id, separator, check = value.partition(":")
    if not separator:
        return None
    try:
        return MaintainerValidationRowId(candidate_id, ValidationCheck(check))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class MaintainerValidationDetailView:
    """One actionable thing a check found, with what was declared against what was expected."""

    message: str
    path: str | None
    declared: str | None
    expected: str | None


@dataclass(frozen=True, slots=True)
class MaintainerValidationCheckView:
    """One named check as screen 38 lists it and screen 39 details it."""

    candidate_id: str
    check: str
    label: str
    outcome: str
    required: bool
    details: tuple[MaintainerValidationDetailView, ...]

    @property
    def row(self) -> str:
        return f"{self.candidate_id}:{self.check}"


@dataclass(frozen=True, slots=True)
class MaintainerValidationView:
    """One complete validation run, projected for screens 38 and 39.

    Warnings and errors are counted separately rather than totalled, because an error refuses
    promotion outright while a warning is something policy may or may not treat as blocking.
    """

    candidate_id: str
    artifact: str
    version: str
    state: CandidateState
    checks: tuple[MaintainerValidationCheckView, ...]
    unmet_requirements: tuple[str, ...]
    #: The policy judgement of this same run.  Screen 40 reads it rather than re-deciding, because
    #: a second judgement composed while drawing could disagree with the one screen 38 showed.
    review: MaintainerPolicyReviewView

    def check(self, name: str) -> MaintainerValidationCheckView:
        matched = next((item for item in self.checks if item.check == name), None)
        if matched is None:
            raise ValueError(f"no validation check named {name!r}")
        return matched

    def _counted(self, outcome: ValidationOutcome) -> int:
        return sum(1 for item in self.checks if item.outcome == outcome.value)

    @property
    def error_count(self) -> int:
        return self._counted(ValidationOutcome.ERROR)

    @property
    def warning_count(self) -> int:
        return self._counted(ValidationOutcome.WARNING)


@dataclass(frozen=True, slots=True)
class MaintainerPolicyReviewView:
    """Screen 40: which policy decided what, separated from what the artifact declared.

    An allowlist that is `None` is not an empty allowlist.  A policy that does not constrain
    runtimes at all permits every runtime; one that constrains them to nothing permits none, and a
    Maintainer reading the screen has to be able to tell those two apart.
    """

    candidate_id: str
    artifact: str
    version: str
    decision: CandidateState
    required_checks: tuple[str, ...]
    unmet_requirements: tuple[str, ...]
    allowed_runtimes: tuple[str, ...] | None
    allowed_transports: tuple[str, ...] | None
    allowed_network_hosts: tuple[str, ...] | None
    allowed_secret_bindings: tuple[str, ...] | None
    forbidden_effects: tuple[str, ...]
    risk_ceiling: str
    blocking_findings: tuple[str, ...]


def _allowed(values: frozenset[str] | None) -> tuple[str, ...] | None:
    return None if values is None else tuple(sorted(values))


def project_maintainer_validation(
    bundle: CandidateBundle,
    *,
    policy: EffectivePolicy,
) -> MaintainerValidationView:
    """Run the named pipeline over one Candidate and project it for screens 38 and 39."""

    if not isinstance(bundle, CandidateBundle) or not isinstance(policy, EffectivePolicy):
        raise ValueError("Maintainer validation projection needs a Candidate and a policy")
    validation = validate_candidate(bundle, policy=policy)
    candidate = bundle.candidate
    candidate_id = candidate.id.value
    checks = tuple(
        MaintainerValidationCheckView(
            candidate_id,
            result.check.value,
            _VALIDATION_LABELS[result.check],
            result.outcome.value,
            result.check.value in policy.required_checks,
            tuple(
                MaintainerValidationDetailView(
                    detail.message, detail.path, detail.declared, detail.expected
                )
                for detail in result.details
            ),
        )
        for result in validation.results
    )
    return MaintainerValidationView(
        candidate_id,
        str(candidate.artifact.coordinate.artifact),
        str(candidate.artifact.coordinate.version),
        validation.state,
        checks,
        tuple(item.value for item in validation.unmet_requirements),
        project_maintainer_policy_review(validation, bundle, policy=policy),
    )


def project_maintainer_policy_review(
    validation: CandidateValidation,
    bundle: CandidateBundle,
    *,
    policy: EffectivePolicy,
) -> MaintainerPolicyReviewView:
    """Project screen 40 from a run that already happened, never by judging the Candidate again."""

    if (
        not isinstance(validation, CandidateValidation)
        or not isinstance(bundle, CandidateBundle)
        or not isinstance(policy, EffectivePolicy)
    ):
        raise ValueError(
            "Maintainer policy review needs a validation run, a Candidate and a policy"
        )
    candidate = bundle.candidate
    if validation.candidate_id != candidate.id:
        raise ValueError("Maintainer policy review needs the run of the Candidate it reviews")
    blocking = tuple(
        redact_text(f"{result.check.value}: {detail.message}")
        for result in validation.results
        if result.outcome is ValidationOutcome.ERROR
        for detail in result.details
    )
    return MaintainerPolicyReviewView(
        candidate.id.value,
        str(candidate.artifact.coordinate.artifact),
        str(candidate.artifact.coordinate.version),
        validation.state,
        tuple(sorted(policy.required_checks)),
        tuple(item.value for item in validation.unmet_requirements),
        _allowed(policy.allowed_runtimes),
        _allowed(policy.allowed_transports),
        _allowed(policy.allowed_network_hosts),
        _allowed(policy.allowed_secret_bindings),
        tuple(sorted(policy.forbidden_effects)),
        policy.risk_ceiling.name.lower().replace("_", "-"),
        blocking,
    )


@dataclass(frozen=True, slots=True)
class MaintainerPromotionReviewView:
    """Screen 41: what confirming a promotion would write, or why it cannot be confirmed.

    A refusal is a legitimate answer to "can this be promoted", so it is projected rather than
    raised.  The review digest is present only when there is something to confirm; a screen that
    showed a digest for an unconfirmable review would invite confirming it.
    """

    candidate_id: str
    artifact: str
    version: str
    target_registry: str
    state: CandidateState
    mode: str
    canonical_digest: str
    source_revision: str
    review_digest: str | None
    registry_revision: str | None
    registry_snapshot_digest: str | None
    validation_report_digest: str | None
    effective_policy_digest: str | None
    warnings: tuple[str, ...]
    refusals: tuple[str, ...]

    @property
    def confirmable(self) -> bool:
        return self.review_digest is not None


def project_maintainer_promotion_review(
    bundle: CandidateBundle,
    validation: CandidateValidation,
    policy: EffectivePolicy,
    approved: ApprovedRegistryState | None,
    *,
    mode: PromotionMode,
) -> MaintainerPromotionReviewView:
    """Project one Candidate's promotion review, including the reasons it may have none."""

    if (
        not isinstance(bundle, CandidateBundle)
        or not isinstance(validation, CandidateValidation)
        or not isinstance(policy, EffectivePolicy)
        or not isinstance(mode, PromotionMode)
        or not (approved is None or isinstance(approved, ApprovedRegistryState))
    ):
        raise ValueError("Maintainer promotion review projection needs a Candidate and a policy")
    candidate = bundle.candidate
    common = {
        "candidate_id": candidate.id.value,
        "artifact": str(candidate.artifact.coordinate.artifact),
        "version": str(candidate.artifact.coordinate.version),
        "target_registry": candidate.target_registry.value,
        "state": validation.state,
        "mode": mode.value,
        "canonical_digest": str(candidate.canonical_digest),
        "source_revision": candidate.artifact.provenance.revision,
    }
    if approved is None:
        return MaintainerPromotionReviewView(
            **common,  # type: ignore[arg-type]
            review_digest=None,
            registry_revision=None,
            registry_snapshot_digest=None,
            validation_report_digest=None,
            effective_policy_digest=None,
            warnings=(),
            refusals=(
                f"target registry {candidate.target_registry.value} has no synchronized "
                "approved snapshot to promote into",
            ),
        )
    prepared = prepare_candidate_promotion(bundle, validation, policy, approved, mode=mode)
    if isinstance(prepared, Err):
        return MaintainerPromotionReviewView(
            **common,  # type: ignore[arg-type]
            review_digest=None,
            registry_revision=approved.revision,
            registry_snapshot_digest=str(approved.snapshot_digest),
            validation_report_digest=None,
            effective_policy_digest=None,
            warnings=(),
            refusals=tuple(redact_text(item.message) for item in prepared.diagnostics),
        )
    evidence = prepared.value.evidence
    return MaintainerPromotionReviewView(
        **common,  # type: ignore[arg-type]
        review_digest=str(prepared.value.review_digest),
        registry_revision=approved.revision,
        registry_snapshot_digest=str(approved.snapshot_digest),
        validation_report_digest=str(evidence.validation_report_digest),
        effective_policy_digest=str(evidence.effective_policy_digest),
        warnings=tuple(redact_text(item) for item in evidence.warnings),
        refusals=(),
    )


#: How many changed paths screen 43 lists.  A promotion writes one file per payload entry, and a
#: review that made somebody page through thousands of rows would not be read at all.
_MAX_REGISTRY_CHANGES = 200


@dataclass(frozen=True, slots=True)
class MaintainerRegistryChangeView:
    """One path a promotion transaction would write, and what it would do to it."""

    path: str
    kind: str


@dataclass(frozen=True, slots=True)
class MaintainerRegistryDiffView:
    """Screen 43: the registry transaction a confirmed promotion would apply.

    `changed_paths` counts the whole transaction while `changes` is bounded, so a truncated list
    never understates what would be written.
    """

    candidate_id: str
    artifact: str
    version: str
    mode: str
    target_registry: str
    changed_paths: int
    changes: tuple[MaintainerRegistryChangeView, ...]
    expected_registry_snapshot: str | None
    next_registry_snapshot: str | None
    plan_digest: str | None
    refusals: tuple[str, ...]

    @property
    def plannable(self) -> bool:
        return self.plan_digest is not None


def project_maintainer_registry_diff(
    bundle: CandidateBundle,
    validation: CandidateValidation,
    policy: EffectivePolicy,
    approved: ApprovedRegistryState | None,
    registry_snapshot: SourceSnapshot | None,
    *,
    mode: PromotionMode,
) -> MaintainerRegistryDiffView:
    """Project the transaction, or the reasons there is none to project."""

    if (
        not isinstance(bundle, CandidateBundle)
        or not isinstance(validation, CandidateValidation)
        or not isinstance(policy, EffectivePolicy)
        or not isinstance(mode, PromotionMode)
        or not (approved is None or isinstance(approved, ApprovedRegistryState))
        or not (registry_snapshot is None or isinstance(registry_snapshot, SourceSnapshot))
    ):
        raise ValueError("Maintainer registry diff projection needs a Candidate and a policy")
    candidate = bundle.candidate
    common: dict[str, object] = {
        "candidate_id": candidate.id.value,
        "artifact": str(candidate.artifact.coordinate.artifact),
        "version": str(candidate.artifact.coordinate.version),
        "mode": mode.value,
        "target_registry": candidate.target_registry.value,
    }

    def _refused(*reasons: str) -> MaintainerRegistryDiffView:
        return MaintainerRegistryDiffView(
            **common,  # type: ignore[arg-type]
            changed_paths=0,
            changes=(),
            expected_registry_snapshot=None,
            next_registry_snapshot=None,
            plan_digest=None,
            refusals=tuple(redact_text(item) for item in reasons),
        )

    if approved is None:
        return _refused(
            f"target registry {candidate.target_registry.value} has no synchronized "
            "approved snapshot to promote into"
        )
    if registry_snapshot is None:
        return _refused(
            f"registry {candidate.target_registry.value} workspace could not be read, "
            "so no transaction can be planned"
        )
    prepared = prepare_candidate_promotion(bundle, validation, policy, approved, mode=mode)
    if isinstance(prepared, Err):
        return _refused(*(item.message for item in prepared.diagnostics))
    try:
        planned = plan_candidate_promotion(prepared.value, registry_snapshot)
    except ValueError as error:
        # A planner that raises must still leave a readable screen: composing every other
        # Candidate's view depends on this one not aborting the whole read.
        return _refused(f"this transaction cannot be planned: {error}")
    if isinstance(planned, Err):
        return _refused(*(item.message for item in planned.diagnostics))
    plan = planned.value
    return MaintainerRegistryDiffView(
        **common,  # type: ignore[arg-type]
        changed_paths=len(plan.changes),
        changes=tuple(
            MaintainerRegistryChangeView(str(item.path), item.kind.value)
            for item in plan.changes[:_MAX_REGISTRY_CHANGES]
        ),
        expected_registry_snapshot=str(plan.expected_registry_snapshot),
        next_registry_snapshot=str(plan.next_registry_snapshot),
        plan_digest=str(plan.review_digest),
        refusals=(),
    )


_PROMOTED_REGISTRY_CHECKS = (
    "Registry workspace projection",
    "Approved version identities",
    "Canonical package digests",
    "Registry catalogs",
    "Promotion provenance",
    "Snapshot reproducibility",
)


@dataclass(frozen=True, slots=True)
class MaintainerRegistryValidationView:
    """Screen 44: evidence that the projected promoted registry is internally valid."""

    candidate_id: str
    artifact: str
    version: str
    target_registry: str
    mode: str
    registry_snapshot: str
    transaction_digest: str
    validation_report_digest: str
    effective_policy_digest: str
    approved_version_count: int
    checks: tuple[str, ...]

    def __post_init__(self) -> None:
        lines = (
            self.candidate_id,
            self.artifact,
            self.version,
            self.target_registry,
            self.mode,
            self.registry_snapshot,
            self.transaction_digest,
            self.validation_report_digest,
            self.effective_policy_digest,
            *self.checks,
        )
        if (
            any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in lines
            )
            or not isinstance(self.approved_version_count, int)
            or isinstance(self.approved_version_count, bool)
            or self.approved_version_count < 1
            or len(set(self.checks)) != len(self.checks)
        ):
            raise ValueError("Maintainer registry validation view is invalid")


@dataclass(frozen=True, slots=True)
class MaintainerRegistryCommitView:
    """Screen 45 before or after the exact local approved-registry write."""

    candidate_id: str
    artifact: str
    version: str
    target_registry: str
    mode: str
    transaction_digest: str
    registry_snapshot_before: str
    registry_snapshot_after: str
    changed_paths: int
    approved_version_count: int
    applied: bool
    commit_subject: str
    commit_revision: str | None

    def __post_init__(self) -> None:
        lines = (
            self.candidate_id,
            self.artifact,
            self.version,
            self.target_registry,
            self.mode,
            self.transaction_digest,
            self.registry_snapshot_before,
            self.registry_snapshot_after,
            self.commit_subject,
        )
        if (
            any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in lines
            )
            or not isinstance(self.changed_paths, int)
            or isinstance(self.changed_paths, bool)
            or self.changed_paths < 0
            or not isinstance(self.approved_version_count, int)
            or isinstance(self.approved_version_count, bool)
            or self.approved_version_count < 1
            or not isinstance(self.applied, bool)
            or (
                self.commit_revision is not None
                and (
                    not self.commit_revision
                    or any(character in self.commit_revision for character in "\r\n")
                )
            )
            or (self.applied != (self.commit_revision is not None))
        ):
            raise ValueError("Maintainer registry commit view is invalid")


def project_maintainer_registry_validation(
    prepared: PreparedCandidatePromotionTransaction,
) -> MaintainerRegistryValidationView:
    """Project the successful pre-write validation already performed by the application."""

    if not isinstance(prepared, PreparedCandidatePromotionTransaction):
        raise ValueError("registry validation projection needs a prepared promotion transaction")
    promotion = prepared.promotion
    candidate = promotion.candidate.candidate
    return MaintainerRegistryValidationView(
        candidate.id.value,
        str(candidate.artifact.coordinate.artifact),
        str(candidate.artifact.coordinate.version),
        candidate.target_registry.value,
        promotion.mode.value,
        str(prepared.registry_snapshot),
        str(prepared.review_digest),
        str(promotion.evidence.validation_report_digest),
        str(promotion.evidence.effective_policy_digest),
        prepared.approved_version_count,
        _PROMOTED_REGISTRY_CHECKS,
    )


def project_maintainer_registry_commit(
    prepared: PreparedCandidatePromotionTransaction,
    *,
    result: CandidatePromotionExecutionResult | None = None,
) -> MaintainerRegistryCommitView:
    """Project screen 45's exact local write before confirmation or after verified readback."""

    if not isinstance(prepared, PreparedCandidatePromotionTransaction) or not (
        result is None or isinstance(result, CandidatePromotionExecutionResult)
    ):
        raise ValueError("registry commit projection needs a prepared promotion transaction")
    plan = prepared.plan
    if result is not None and (
        result.review_digest != plan.review_digest
        or result.registry_snapshot != plan.next_registry_snapshot
        or result.workspace_digest != plan.next_workspace_digest
        or result.changed_paths != plan.changed_paths
        or result.approved_version_count != prepared.approved_version_count
    ):
        raise ValueError("registry commit result does not match the reviewed transaction")
    candidate = prepared.promotion.candidate.candidate
    return MaintainerRegistryCommitView(
        candidate.id.value,
        str(candidate.artifact.coordinate.artifact),
        str(candidate.artifact.coordinate.version),
        candidate.target_registry.value,
        prepared.promotion.mode.value,
        str(plan.review_digest),
        str(plan.expected_registry_snapshot),
        str(plan.next_registry_snapshot),
        plan.changed_paths,
        prepared.approved_version_count,
        result is not None,
        promotion_commit_subject(prepared),
        None if result is None else result.commit_revision,
    )


class MaintainerWorkingTreeState(str, Enum):
    """What a local registry checkout is, relative to the approved snapshot it should hold."""

    MATCHES_SNAPSHOT = "matches-snapshot"
    DIVERGED = "diverged"
    UNOBSERVED = "unobserved"


@dataclass(frozen=True, slots=True)
class MaintainerWorkingTreeView:
    """Screen 46: the local checkout, observed rather than inferred."""

    state: MaintainerWorkingTreeState
    digest: str | None
    detail: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.state, MaintainerWorkingTreeState)
            or not (self.digest is None or isinstance(self.digest, str))
            or (self.state is MaintainerWorkingTreeState.UNOBSERVED and self.digest is not None)
            or not (self.detail is None or isinstance(self.detail, str))
        ):
            raise ValueError("Maintainer working tree view is invalid")


@dataclass(frozen=True, slots=True)
class MaintainerRegistryTransactionView:
    """One promotion transaction as the registry recorded it, newest first in the chain."""

    snapshot_before: str
    snapshot_after: str
    mode: str
    candidate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.snapshot_before
            or not self.snapshot_after
            or not self.mode
            or not self.candidate_ids
            or any(not isinstance(item, str) or not item for item in self.candidate_ids)
        ):
            raise ValueError("Maintainer registry transaction view is invalid")
        object.__setattr__(self, "candidate_ids", tuple(sorted(self.candidate_ids)))


@dataclass(frozen=True, slots=True)
class MaintainerRegistryView:
    """Screen 46: registry validity, contents, checkout state and recent promotions."""

    alias: str
    valid: bool
    revision: str | None
    snapshot: str | None
    version_count: int
    artifact_counts: tuple[tuple[ArtifactKind, int], ...]
    working_tree: MaintainerWorkingTreeView
    transactions: tuple[MaintainerRegistryTransactionView, ...]
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.alias
            or not isinstance(self.valid, bool)
            or self.version_count < 0
            or not isinstance(self.working_tree, MaintainerWorkingTreeView)
            or any(
                not isinstance(item, MaintainerRegistryTransactionView)
                for item in self.transactions
            )
            or (self.valid and self.diagnostics)
        ):
            raise ValueError("Maintainer registry view is invalid")


_MAX_REGISTRY_TRANSACTIONS = 50


def _registry_transactions(
    audits: tuple[PromotionAudit, ...],
    head: str,
) -> tuple[MaintainerRegistryTransactionView, ...]:
    """Order transactions newest first by walking the snapshot chain back from the head.

    No promotion record carries a clock, and inventing one at read time would make the order a
    property of when a Maintainer looked rather than of what happened.  Each audit names the
    snapshot its own transaction started from and produced, so the records group into transactions
    and the transactions chain -- which is derivable, reproducible evidence.
    """

    grouped: dict[tuple[str, str, str], list[str]] = {}
    for audit in audits:
        key = (
            str(audit.registry_snapshot_after),
            str(audit.registry_snapshot_before),
            audit.mode.value,
        )
        grouped.setdefault(key, []).append(audit.candidate_id.value)
    ordered: list[MaintainerRegistryTransactionView] = []
    seen: set[str] = set()
    cursor = head
    while len(ordered) < _MAX_REGISTRY_TRANSACTIONS and cursor not in seen:
        seen.add(cursor)
        step = next((key for key in grouped if key[0] == cursor), None)
        if step is None:
            break
        ordered.append(
            MaintainerRegistryTransactionView(step[1], step[0], step[2], tuple(grouped[step]))
        )
        cursor = step[1]
    return tuple(ordered)


def project_maintainer_registry(
    alias: SourceAlias,
    approved: ApprovedRegistryState | None,
    registry_snapshot: SourceSnapshot | None,
    checkout: SourceSnapshot | None,
) -> MaintainerRegistryView:
    """Project screen 46 from durable registry evidence and one observed local checkout.

    The checkout is a separate observation on purpose: synchronized source-store content is an
    immutable record of what the registry published, and answering "does my working tree still
    match" from it would answer a question nobody asked.
    """

    if (
        not isinstance(alias, SourceAlias)
        or not (approved is None or isinstance(approved, ApprovedRegistryState))
        or not (registry_snapshot is None or isinstance(registry_snapshot, SourceSnapshot))
        or not (checkout is None or isinstance(checkout, SourceSnapshot))
    ):
        raise ValueError("Maintainer registry projection needs an alias and typed observations")
    diagnostics: list[str] = []
    if approved is None:
        return MaintainerRegistryView(
            alias.value,
            False,
            None,
            None,
            0,
            (),
            MaintainerWorkingTreeView(MaintainerWorkingTreeState.UNOBSERVED, None),
            (),
            (f"registry {alias.value} has no synchronized approved state yet",),
        )
    snapshot = str(approved.snapshot_digest)
    # A durable record may hold the kind as its wire string; the view states the typed kind.
    counts = Counter(ArtifactKind(str(item.coordinate.artifact.kind)) for item in approved.versions)
    artifact_counts = tuple(sorted(counts.items(), key=lambda item: item[0].value))
    audits: tuple[PromotionAudit, ...] = ()
    if registry_snapshot is None:
        diagnostics.append(f"registry {alias.value} snapshot content was not read")
    else:
        loaded = load_registry_promotions(registry_snapshot)
        if isinstance(loaded, Err):
            diagnostics.append(f"registry {alias.value} promotion records are unreadable")
        else:
            audits = loaded.value
            approved_ids = {item.candidate_id for item in approved.versions}
            recorded = {item.candidate_id for item in audits}
            missing = sorted(item.value for item in approved_ids - recorded)
            if missing:
                # A published version nobody approved is the failure registry validity exists for.
                diagnostics.append(
                    f"{len(missing)} approved version(s) carry no promotion approval record: "
                    + ", ".join(missing[:5])
                )
    observed = None if checkout is None else registry_state_digest(checkout)
    if observed is None:
        working = MaintainerWorkingTreeView(MaintainerWorkingTreeState.UNOBSERVED, None)
    elif isinstance(observed, Err):
        working = MaintainerWorkingTreeView(
            MaintainerWorkingTreeState.UNOBSERVED, None, "the local checkout could not be digested"
        )
    elif str(observed.value) == snapshot:
        working = MaintainerWorkingTreeView(
            MaintainerWorkingTreeState.MATCHES_SNAPSHOT, str(observed.value)
        )
    else:
        working = MaintainerWorkingTreeView(
            MaintainerWorkingTreeState.DIVERGED,
            str(observed.value),
            "the local checkout holds different published content than the approved snapshot",
        )
    return MaintainerRegistryView(
        alias.value,
        not diagnostics,
        approved.revision,
        snapshot,
        len(approved.versions),
        artifact_counts,
        working,
        _registry_transactions(audits, snapshot),
        tuple(diagnostics),
    )
