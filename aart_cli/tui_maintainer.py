"""Pure text renderers for canonical Maintainer Mode projections."""

from __future__ import annotations

from aart_cli.application.consumer_views import PresentationProfile
from aart_cli.application.maintainer_promotion import CandidatePromotionRecord
from aart_cli.application.maintainer_views import (
    MaintainerAdoptedArtifactView,
    MaintainerAdoptionReviewView,
    MaintainerAdoptionUpstreamView,
    MaintainerBulkPromotionView,
    MaintainerCandidateFilterView,
    MaintainerCandidateLifecycleView,
    MaintainerCandidateView,
    MaintainerCollectionCandidateView,
    MaintainerCollectionValidationView,
    MaintainerDashboardView,
    MaintainerPolicyReviewView,
    MaintainerPromotionReviewView,
    MaintainerProvenanceView,
    MaintainerPublicationState,
    MaintainerRegistryCommitView,
    MaintainerRegistryDiffView,
    MaintainerRegistryValidationView,
    MaintainerRegistryView,
    MaintainerRegistryWorkspaceView,
    MaintainerRepositoryScanView,
    MaintainerSourceSyncResultView,
    MaintainerSourceSyncReviewView,
    MaintainerSourceView,
    MaintainerTransactionCandidateView,
    MaintainerValidationCheckView,
    MaintainerValidationView,
    MaintainerVersionConflictView,
    MaintainerWorkingTreeState,
)
from aart_cli.domain.candidates import CandidateState
from aart_cli.tui_layout import (
    CONTENT_MEASURE,
    action_prompt,
    columns,
    field_block,
    separate,
)

#: Screen 35's column headings. They are part of the grid rather than a hand-spaced string, so the
#: header cannot drift away from the rows it names (`QA-030`).
_CANDIDATE_HEADINGS = ("STATUS", "ARTIFACT", "VERSION", "SOURCE")

#: Screen 47 nests its selectable rows under a registry, and the grid gets the remaining measure.
_BULK_INDENT = 2

__all__ = [
    "maintainer_registry_detail",
    "maintainer_bulk_promotion_status",
    "maintainer_collection_candidate_detail",
    "maintainer_validation_check_detail",
    "maintainer_validation_status",
    "maintainer_candidate_filter_detail",
    "maintainer_candidate_filter_status",
    "adopted_artifact_detail",
    "repository_scan_detail",
    "repository_scan_status",
    "render_maintainer_dashboard",
    "render_maintainer_candidate",
    "render_maintainer_candidate_filters",
    "render_maintainer_candidate_lifecycle",
    "render_maintainer_candidate_diff",
    "render_maintainer_candidates",
    "maintainer_candidate_detail",
    "render_maintainer_collection_candidates",
    "render_maintainer_collection_validation",
    "render_maintainer_source",
    "render_source_sync_result",
    "render_source_sync_review",
    "render_maintainer_sources",
    "render_maintainer_policy_review",
    "render_maintainer_promotion_review",
    "render_maintainer_provenance",
    "render_maintainer_version_conflict",
    "render_maintainer_bulk_promotion",
    "maintainer_registry_descriptor",
    "maintainer_workspace_detail",
    "maintainer_workspace_row",
    "maintainer_registry_rows",
    "maintainer_registry_status",
    "render_maintainer_registry",
    "render_maintainer_registry_diff",
    "render_maintainer_registry_commit",
    "render_maintainer_registry_push",
    "maintainer_registry_push_status",
    "render_maintainer_registry_validation",
    "render_repository_adoption_review",
    "render_adopted_artifacts",
    "render_adoption_upstream_check",
    "render_repository_scan",
    "render_maintainer_validation",
    "render_maintainer_validation_check",
]


def _human(value: str) -> str:
    return value.replace("-", " ").capitalize()


def _noun(count: int, singular: str) -> str:
    return singular if count == 1 else f"{singular}s"


def _candidate_summary(active: int, settled: int) -> str:
    """Lead with what is waiting, and mention the audit trail only when there is one.

    A registry that has never promoted anything reads exactly as it did before, so the distinction
    costs nothing on the screens that never had the problem (issue #9).
    """

    if not settled:
        return f"Candidates: {active}"
    return f"Candidates: {active} awaiting action, {settled} settled"


def _lifecycle(counts: tuple[tuple[CandidateState, int], ...]) -> str:
    return ", ".join(f"{state.value}={count}" for state, count in counts)


def render_maintainer_dashboard(
    view: MaintainerDashboardView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerDashboardView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer Dashboard rendering needs a view and profile")
    # `QA-092`: no heading. Four counts and a list of activity are an overview already, and a line
    # that says so is the fault `QA-067` removed from `Navigation:` wearing another name.
    # `QA-096`: each count is a separate statement, so each is separated -- the blank line is what
    # the status block reads to tell one list item from the next.
    activity = [f"  - {item}" for item in view.recent_activity] or ["  - none yet"]
    candidates = [_candidate_summary(view.active_candidate_count, view.settled_candidate_count)]
    if profile is PresentationProfile.VERBOSE and view.lifecycle_counts:
        candidates.append(f"Candidate lifecycle: {_lifecycle(view.lifecycle_counts)}")
    return separate(
        (f"Sources: {view.source_count}",),
        tuple(candidates),
        (f"Validation failures: {view.validation_failure_count}",),
        (f"Ready for promotion: {view.ready_count}",),
        ("Recent maintainer activity:", *activity),
    )


def render_maintainer_sources(
    sources: tuple[MaintainerSourceView, ...],
    *,
    cursor: str = "",
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if (
        any(not isinstance(source, MaintainerSourceView) for source in sources)
        or not isinstance(cursor, str)
        or any(character in cursor for character in "\r\n")
        or not isinstance(profile, PresentationProfile)
    ):
        raise ValueError("Maintainer Sources rendering needs Source views, cursor and profile")
    if not sources:
        return ("No authoring Sources are configured.",)
    lines: list[str] = []
    for source in sources:
        lines.extend(
            (
                f"{'>' if source.alias == cursor else ' '} {source.alias} — "
                f"{_human(source.status.value)}",
                f"    {source.location}",
                f"    branch: {source.branch or 'local'} · {source.manifest_count} "
                f"{_noun(source.manifest_count, 'manifest')}"
                + (f" · {source.invalid_count} invalid" if source.invalid_count else ""),
            )
        )
    return tuple(lines)


def render_maintainer_source(
    source: MaintainerSourceView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(source, MaintainerSourceView) or not isinstance(profile, PresentationProfile):
        raise ValueError("Maintainer Source rendering needs a Source view and profile")
    revision = source.revision or "never synchronized"
    if profile is PresentationProfile.FAST and source.revision is not None:
        revision = source.revision[:12]
    lines = [
        f"{source.alias} — {_human(source.status.value)}",
        f"URL: {source.location}",
        f"branch: {source.branch or 'local'}",
        f"Last successful revision: {revision}",
        f"Manifests: {source.manifest_count}",
        f"{_candidate_summary(source.active_count, source.settled_count)}"
        f" — {source.ready_count} ready, {source.invalid_count} invalid",
    ]
    if profile is PresentationProfile.VERBOSE:
        lines.extend(
            (
                f"Kind: {_human(source.kind)}",
                "Target registries: " + (", ".join(source.target_registries) or "none"),
                "Candidate states: "
                + (
                    ", ".join(f"{state.value}={count}" for state, count in source.candidate_states)
                    or "none"
                ),
            )
        )
        if source.last_successful_sync is not None:
            lines.append(f"Last synchronized epoch: {source.last_successful_sync}")
        lines.extend(f"Attention: {diagnostic}" for diagnostic in source.diagnostics)
    return tuple(lines)


def render_source_sync_review(
    view: MaintainerSourceSyncReviewView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerSourceSyncReviewView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Source Sync review rendering needs a typed view and profile")
    revision = view.current_revision or "never synchronized"
    registry_revision = view.approved_revision
    if profile is PresentationProfile.FAST:
        if view.current_revision is not None:
            revision = view.current_revision[:12]
        registry_revision = registry_revision[:12]
    # `QA-029`: what it is, where it stands, what it will do, and the evidence, as four groups a
    # reader can skip between rather than as one block they have to read to the end.
    identity = [
        f"Sync authoring Source {view.alias}",
        f"Location: {view.location}",
        f"Branch: {view.branch or 'local'}",
    ]
    if profile is PresentationProfile.VERBOSE:
        identity.append(f"Source kind: {_human(view.kind)}")
    standing = [
        f"Current revision: {revision}",
        f"Current Candidates: {view.candidate_count}",
        f"Compare with approved registry: {view.target_registry}@{registry_revision}",
    ]
    effects = [
        "Effects: fetch/read, exact manifest discovery, compile, Candidate reconciliation",
        "Registry mutations: none",
    ]
    evidence = []
    if profile is PresentationProfile.VERBOSE:
        evidence.append(f"Approved snapshot: {view.approved_snapshot}")
    evidence.append(f"Review identity: {view.review_digest}")
    return action_prompt(
        separate(identity, standing, effects, evidence), "Press Enter to synchronize."
    )


def render_source_sync_result(
    view: MaintainerSourceSyncResultView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerSourceSyncResultView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Source Sync result rendering needs a typed view and profile")
    revision = view.revision if profile is PresentationProfile.VERBOSE else view.revision[:12]
    # `QA-029` again, on the screen the run lands on: the outcome, what it found, what it left
    # alone, and the evidence.
    outcome = [f"Source Sync {view.disposition}: {view.alias}", f"Pinned revision: {revision}"]
    found = [
        f"Discovered manifests: {view.manifest_count}",
        f"Candidates: {view.candidate_count}",
    ]
    if profile is PresentationProfile.VERBOSE:
        found.append(
            "Candidate states: "
            + (
                ", ".join(f"{state.value}={count}" for state, count in view.candidate_states)
                or "none"
            )
        )
    untouched = [f"Target registry observed: {view.target_registry}", "Registry mutations: none"]
    # `QA-063`: a manifest that would not compile is named here, with the file to open. Only when
    # there is one -- a Source with nothing wrong has nothing to say, and an always-drawn empty
    # section is the fault `QA-068` is about.
    refused = (
        [f"Could not read {len(view.refusals)} manifest:"]
        if len(view.refusals) == 1
        else [f"Could not read {len(view.refusals)} manifests:"]
    )
    refused.extend(f"  {path} — {reason}" for path, reason in view.refusals)
    sections = [outcome, found, *([refused] if view.refusals else []), untouched]
    return separate(*sections, [f"Review identity: {view.review_digest}"])


def candidate_status(view: MaintainerCandidateView) -> str:
    """A Candidate's status as the Registry trees record it, before its stored state (D-259).

    A local commit is not a sync, so until Source Sync observes a synchronized Registry the stored
    state still reads New or Ready. The record is what is true now; nothing here says Published.
    """

    if view.state is not CandidateState.PROMOTED:
        if view.promotion is CandidatePromotionRecord.PROMOTED_LOCALLY:
            return "Promoted locally"
        if view.promotion is CandidatePromotionRecord.PROMOTED:
            return "Promoted"
    return _human(view.state.value)


def render_maintainer_candidates(
    candidates: tuple[MaintainerCandidateView, ...],
    *,
    cursor: str = "",
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if (
        any(not isinstance(candidate, MaintainerCandidateView) for candidate in candidates)
        or not isinstance(cursor, str)
        or not isinstance(profile, PresentationProfile)
    ):
        raise ValueError("Maintainer Candidates rendering needs typed views, cursor and profile")
    if not candidates:
        return ("No active Candidates have been discovered.",)
    # `QA-030`: the header and every row are laid out on one shared grid, so a name longer than its
    # column is cut there instead of pushing the columns after it out of line. The row under the
    # cursor is spelt out in full by `maintainer_candidate_detail`, which is the screen's cursor
    # description rather than a second block inside the table (CP-23 task 02, D-252).
    # CP-23 task 14: the cursor is the same `> ` gutter every other list draws, carried inside the
    # first cell so the later columns stay on one grid; the header is the table's heading, flush
    # left like every heading over rows.
    rows = [_CANDIDATE_HEADINGS]
    rows.extend(
        (
            f"{'>' if item.id == cursor else ' '} {candidate_status(item)}",
            item.artifact,
            item.version,
            item.source_alias,
        )
        for item in candidates
    )
    return columns(rows, width=CONTENT_MEASURE)


def maintainer_candidate_detail(
    candidates: tuple[MaintainerCandidateView, ...],
    *,
    cursor: str,
) -> tuple[str, ...]:
    """The Candidate under the cursor, in full, or nothing when the cursor is on no Candidate.

    It is a cursor description, so the frame draws it below the table's rule and only in Verbose
    (D-250). No heading: the block's position already says what it describes.
    """

    if any(not isinstance(candidate, MaintainerCandidateView) for candidate in candidates) or (
        not isinstance(cursor, str)
    ):
        raise ValueError("Maintainer Candidate detail needs typed views and a cursor")
    focused = next((item for item in candidates if item.id == cursor), None)
    if focused is None:
        return ()
    fields = (
        ("Artifact", focused.artifact),
        ("Version", focused.version),
        ("Source", focused.source_alias),
        ("Status", candidate_status(focused)),
        ("Candidate", focused.id),
        ("Target registry", focused.target_registry),
    )
    return field_block(fields, indent=2, width=CONTENT_MEASURE)


def _short(value: str, profile: PresentationProfile) -> str:
    return value if profile is PresentationProfile.VERBOSE else value[:19]


def render_maintainer_candidate(
    view: MaintainerCandidateView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerCandidateView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer Candidate rendering needs a typed view and profile")
    lines = [
        f"{view.artifact}@{view.version} — {candidate_status(view)}",
        f"Kind: {view.kind}",
        f"Source: {view.source_alias} · {view.source_location}",
        f"Source revision: {_short(view.source_revision, profile)}",
        f"Manifest: {view.manifest_path}",
        f"Artifact input digest: {_short(view.input_digest, profile)}",
        f"Payload digest: {_short(view.payload_digest, profile)}",
        f"Canonical digest: {_short(view.canonical_digest, profile)}",
        f"Target registry: {view.target_registry}",
        f"Runtime: {view.runtime or 'none'}",
        f"Transport: {view.transport or 'none'}",
        f"Dependency descriptor: {view.dependency_descriptor or 'none'}",
        "Inputs:",
    ]
    if not view.inputs:
        lines.append("  - none")
    for item in view.inputs:
        lines.append(f"  {item.kind} {item.id} — {item.label}")
        if item.example is not None:
            lines.append(f"    example: {item.example}")
        if item.format_hint is not None:
            lines.append(f"    format: {item.format_hint}")
        if item.obtain_from is not None:
            lines.append(f"    obtain from: {item.obtain_from}")
            if profile is PresentationProfile.VERBOSE and item.obtain_from_url is not None:
                lines.append(f"    guidance URL: {item.obtain_from_url}")
    lines.append("Validation findings:")
    lines.extend(f"  - {item}" for item in view.findings)
    if not view.findings:
        lines.append("  - none recorded")
    if view.rejection_reason is not None:
        lines.append(f"Rejection: {view.rejection_reason}")
    lines.append("Press d for semantic diff.")
    return tuple(lines)


def render_maintainer_candidate_lifecycle(
    view: MaintainerCandidateLifecycleView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 48: Source/Candidate history joined to exact registry approval evidence."""

    if not isinstance(view, MaintainerCandidateLifecycleView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer Candidate lifecycle rendering needs a typed view and profile")
    lines = [f"{view.artifact}@{view.version} — Candidate lifecycle"]
    for stage in view.stages:
        lines.append(f"{_human(stage.phase.value)} — {_human(stage.outcome)}")
        lines.append(f"  {stage.detail}")
        if stage.evidence is not None:
            lines.append(f"  {_short(stage.evidence, profile)}")
        if profile is PresentationProfile.VERBOSE:
            lines.append(f"  Candidate {stage.candidate_id}")
    lines.append("Promotion is shown only when both registry version and audit evidence match.")
    return tuple(lines)


def render_maintainer_provenance(
    view: MaintainerProvenanceView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 49: exact Source, importer and payload provenance."""

    if not isinstance(view, MaintainerProvenanceView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer provenance rendering needs a typed view and profile")
    if view.git_revision is not None:
        pin = f"Pinned Git revision: {_short(view.git_revision, profile)}"
    else:
        pin = f"Pinned local snapshot: {_short(view.local_snapshot_digest or '', profile)}"
    lines = [
        f"{view.coordinate} — Provenance",
        f"Source: {view.source_url}",
        f"Source kind: {_human(view.source_kind.value)}",
        pin,
        f"Manifest: {view.manifest_path}",
        f"Artifact input digest: {_short(view.input_digest, profile)}",
        f"Importer: {view.importer_id} {view.importer_version}",
        "Payload paths:",
    ]
    lines.extend(f"  - {item}" for item in view.payload_paths)
    if not view.payload_paths:
        lines.append("  - none")
    lines.append("Warnings:")
    lines.extend(f"  - {item}" for item in view.warnings)
    if not view.warnings:
        lines.append("  - none")
    if profile is PresentationProfile.VERBOSE:
        lines.append(f"Candidate: {view.candidate_id}")
    return tuple(lines)


def render_maintainer_version_conflict(
    view: MaintainerVersionConflictView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 50: the immutable published value and the refused Candidate side by side."""

    if not isinstance(view, MaintainerVersionConflictView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer version conflict rendering needs a typed view and profile")
    lines = [
        f"{view.coordinate} — Version conflict",
        "Blocked: this coordinate/version is already published and immutable.",
        "Candidate content:",
        f"  input: {_short(view.candidate_input_digest, profile)}",
        f"  payload: {_short(view.candidate_payload_digest, profile)}",
        f"  canonical: {_short(view.candidate_canonical_digest, profile)}",
        "Published content:",
    ]
    if view.exact_evidence:
        lines.extend(
            (
                f"  input: {_short(view.published_input_digest or '', profile)}",
                f"  payload: {_short(view.published_payload_digest or '', profile)}",
                f"  canonical: {_short(view.published_canonical_digest or '', profile)}",
            )
        )
    else:
        lines.append("  exact digest evidence unavailable")
    lines.extend((view.evidence_detail, f"Required action: {view.required_action}"))
    if profile is PresentationProfile.VERBOSE:
        lines.append(f"Candidate: {view.candidate_id}")
        if view.published_candidate_id is not None:
            lines.append(f"Published Candidate: {view.published_candidate_id}")
    return tuple(lines)


def render_maintainer_candidate_filters(
    view: MaintainerCandidateFilterView,
    *,
    cursor: str = "",
) -> tuple[str, ...]:
    """Screen 53's rows: the facets and which of their values are ticked.

    What the narrowing currently leaves is the view's status
    (:func:`maintainer_candidate_filter_status`). What ticking the value under the cursor would
    leave is Verbose's description of it (:func:`maintainer_candidate_filter_detail`), so a
    narrowing that selects nothing is legible before it is applied.
    """

    if (
        not isinstance(view, MaintainerCandidateFilterView)
        or not isinstance(cursor, str)
        or any(character in cursor for character in "\r\n")
    ):
        raise ValueError("Maintainer Candidate filter rendering needs a view and a cursor")
    if not view.groups:
        return ("No Candidates are composed, so there is nothing to narrow.",)
    lines: list[str] = []
    for group in view.groups:
        if lines:
            lines.append("")
        lines.append(group.label)
        for option in group.options:
            mark = "[x]" if option.active else "[ ]"
            pointer = ">" if option.row == cursor else " "
            lines.append(f"{pointer} {mark} {option.value}")
    return tuple(lines)


def maintainer_candidate_filter_status(view: MaintainerCandidateFilterView) -> tuple[str, ...]:
    """Screen 53's state: the search, whether anything narrows, and what that leaves."""

    if not isinstance(view, MaintainerCandidateFilterView):
        raise ValueError("Maintainer Candidate filter status needs a view")
    return separate(
        (f"Search: {view.query}",) if view.query else (),
        ("No filter is applied." if view.is_empty else "Filtered.",),
        (f"Showing {view.matching} of {view.total} Candidates",),
    )


def maintainer_candidate_filter_detail(
    view: MaintainerCandidateFilterView, cursor: str
) -> tuple[str, ...]:
    """What the value under the cursor would leave: the count, not how many carry the value."""

    option = next(
        (item for group in view.groups for item in group.options if item.row == cursor), None
    )
    if option is None:
        return ()
    return (f"{option.value}: {option.matching} Candidate(s) would match",)


def render_maintainer_collection_candidates(
    candidates: tuple[MaintainerCollectionCandidateView, ...],
    *,
    cursor: str = "",
) -> tuple[str, ...]:
    """Screen 51: versioned Collection Candidates, never flattened to imperative steps.

    Where the Candidate under the cursor came from and what it holds is Verbose's description of it
    (:func:`maintainer_collection_candidate_detail`), so `v` never grows the rows.
    """

    if (
        any(not isinstance(item, MaintainerCollectionCandidateView) for item in candidates)
        or not isinstance(cursor, str)
        or any(character in cursor for character in "\r\n")
    ):
        raise ValueError("Maintainer Collection rendering needs Candidate views and a cursor")
    if not candidates:
        return ("No Collection Candidates are available.",)
    return tuple(
        f"{'>' if candidate.candidate_id == cursor else ' '} {candidate.coordinate} — "
        f"{_human(candidate.state.value)} · {_noun(len(candidate.members), 'member')}"
        for candidate in candidates
    )


def maintainer_collection_candidate_detail(
    candidates: tuple[MaintainerCollectionCandidateView, ...], cursor: str
) -> tuple[str, ...]:
    """The Collection Candidate under the cursor: its source, manifest, identity and members."""

    candidate = next((item for item in candidates if item.candidate_id == cursor), None)
    if candidate is None:
        return ()
    return (
        f"Source: {candidate.source_alias} · {candidate.source_location}",
        f"Manifest: {candidate.manifest_path}",
        f"Candidate: {candidate.candidate_id}",
        "Members:",
        *(f"  - {item}" for item in candidate.members),
    )


def render_maintainer_collection_validation(
    view: MaintainerCollectionValidationView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 52: every declaration beside the approved exact version satisfying it."""

    if not isinstance(view, MaintainerCollectionValidationView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer Collection validation rendering needs a typed view")
    lines = [
        f"{view.coordinate} — Collection validation: {_human(view.outcome)}",
        "Approved target registry snapshot: "
        + (
            "unavailable"
            if view.registry_snapshot is None
            else _short(view.registry_snapshot, profile)
        ),
        "Members:",
    ]
    for member in view.members:
        resolved = member.resolved_coordinate or "not resolved"
        lines.append(f"  {_human(member.outcome)}  {member.request} → {resolved}")
        if profile is PresentationProfile.VERBOSE or member.outcome != "approved":
            lines.append(f"    {member.detail}")
    lines.extend(f"Attention: {item}" for item in view.diagnostics)
    if profile is PresentationProfile.VERBOSE:
        lines.append(f"Candidate: {view.candidate_id}")
    return tuple(lines)


def render_maintainer_candidate_diff(
    view: MaintainerCandidateView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 37: the semantic summary in Fast, with the bounded file diffs added in Verbose.

    CP-23 task 03 (D-253): `v` is the one presentation toggle, so the raw file evidence is the
    Verbose projection of the same Candidate rather than a second, screen-specific `f` switch.
    The hint is its own statement after everything it is about.
    """

    if not isinstance(view, MaintainerCandidateView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer Candidate diff rendering needs a typed view and profile")
    lines = [
        view.artifact,
        f"Baseline: {view.baseline}",
        f"Candidate: {view.version}",
        "",
        "Semantic changes:",
    ]
    if not view.semantic_changes:
        lines.append("  no semantic changes")
    for change in view.semantic_changes:
        marker = "+" if change.before is None else "-" if change.after is None else "~"
        lines.append(f"{marker} {change.field}")
        lines.append(f"    {change.before or 'none'} → {change.after or 'none'}")
    if not any(change.field.startswith("runtime input") for change in view.semantic_changes):
        lines.append("No credential semantics changed.")
    lines.extend(("", "File changes (secondary):"))
    if not view.file_changes:
        lines.append("  none")
    for changed_file in view.file_changes:
        marker = {"added": "+", "removed": "-", "modified": "~"}[changed_file.status]
        lines.append(f"{marker} {changed_file.path} — {changed_file.status}")
    if profile is not PresentationProfile.VERBOSE:
        lines.extend(("", "Press v to view bounded redacted file diffs."))
        return tuple(lines)
    lines.extend(("", "Bounded redacted file diffs:"))
    for changed_file in view.file_changes:
        lines.append(f"[{changed_file.path}]")
        lines.extend(f"  {line}" for line in changed_file.diff)
        if not changed_file.diff:
            lines.append("  content omitted by the global diff bound")
    lines.extend(("", "Press v to hide the bounded redacted file diffs."))
    return tuple(lines)


def _allowlist(values: tuple[str, ...] | None) -> str:
    """What a policy permits, keeping "unconstrained" distinct from "nothing is permitted"."""

    if values is None:
        return "unconstrained"
    return ", ".join(values) if values else "none permitted"


def render_maintainer_validation(
    view: MaintainerValidationView,
    *,
    cursor: str = "",
) -> tuple[str, ...]:
    """Screen 38's rows: one per check, marked where policy requires it.

    The verdict and the counts are the view's status (:func:`maintainer_validation_status`); what a
    check found is Verbose's description of the row under the cursor
    (:func:`maintainer_validation_check_detail`).
    """

    if not isinstance(view, MaintainerValidationView) or not isinstance(cursor, str):
        raise ValueError("Maintainer validation rendering needs a typed view and a cursor")
    lines = ["Checks"]
    for item in view.checks:
        marker = " · required" if item.required else ""
        pointer = ">" if item.row == cursor else " "
        lines.append(f"{pointer} {item.label} — {_human(item.outcome)}{marker}")
    return tuple(lines)


def maintainer_validation_status(view: MaintainerValidationView) -> tuple[str, ...]:
    """Screen 38's state: which Candidate, its verdict, and what policy still requires."""

    if not isinstance(view, MaintainerValidationView):
        raise ValueError("Maintainer validation status needs a typed view")
    return separate(
        (f"{view.artifact}@{view.version} — {_human(view.state.value)}",),
        (
            f"{view.error_count} {_noun(view.error_count, 'error')}, "
            f"{view.warning_count} {_noun(view.warning_count, 'warning')}",
        ),
        (f"Unmet requirements: {', '.join(view.unmet_requirements)}",)
        if view.unmet_requirements
        else (),
    )


def maintainer_validation_check_detail(
    view: MaintainerValidationView, cursor: str
) -> tuple[str, ...]:
    """What the check under the cursor found, one line per finding."""

    check = next((item for item in view.checks if item.row == cursor), None)
    if check is None:
        return ()
    if not check.details:
        return (f"{check.label}: nothing to report",)
    return (f"{check.label}:", *(f"  - {detail.message}" for detail in check.details))


def render_maintainer_validation_check(
    view: MaintainerValidationCheckView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerValidationCheckView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer validation check rendering needs a typed view and profile")
    lines = [
        f"{view.label} — {_human(view.outcome)}",
        f"Check: {view.check}",
        f"Required by policy: {'yes' if view.required else 'no'}",
        "Findings:",
    ]
    if not view.details:
        lines.append("  - nothing to report")
    for detail in view.details:
        lines.append(f"  - {detail.message}")
        if detail.path is not None:
            lines.append(f"    path: {detail.path}")
        if detail.declared is not None:
            lines.append(f"    declared: {detail.declared}")
        if detail.expected is not None:
            lines.append(f"    expected: {detail.expected}")
    return tuple(lines)


def render_maintainer_policy_review(
    view: MaintainerPolicyReviewView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerPolicyReviewView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer policy review rendering needs a typed view and profile")
    lines = [
        f"{view.artifact}@{view.version} — {_human(view.decision.value)}",
        "Policy allows:",
        f"  Runtimes: {_allowlist(view.allowed_runtimes)}",
        f"  Transports: {_allowlist(view.allowed_transports)}",
        f"  Network hosts: {_allowlist(view.allowed_network_hosts)}",
        f"  Secret bindings: {_allowlist(view.allowed_secret_bindings)}",
        f"  Risk ceiling: {view.risk_ceiling}",
        "Policy requires:",
    ]
    lines.extend(f"  - {item}" for item in view.required_checks)
    if not view.required_checks:
        lines.append("  - nothing beyond the pipeline itself")
    if view.forbidden_effects:
        lines.append(f"Forbidden effects: {', '.join(view.forbidden_effects)}")
    if view.unmet_requirements:
        lines.append(f"Unmet requirements: {', '.join(view.unmet_requirements)}")
    lines.append("Blocking findings:")
    lines.extend(f"  - {item}" for item in view.blocking_findings)
    if not view.blocking_findings:
        lines.append("  - none; nothing here refuses promotion")
    return tuple(lines)


def render_maintainer_promotion_review(
    view: MaintainerPromotionReviewView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerPromotionReviewView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer promotion review rendering needs a typed view and profile")
    lines = [
        f"{view.artifact}@{view.version} — {_human(view.state.value)}",
        f"Target registry: {view.target_registry}",
        f"Promotion mode: {view.mode}",
        "",
        "Promotion choices:",
    ]
    for choice in view.mode_choices:
        default = " (enterprise default)" if choice.enterprise_default else ""
        selected = " — selected" if choice.selected else ""
        lines.extend(
            (
                f"{'●' if choice.selected else '○'} {choice.label}{default}{selected}",
                f"  {choice.registry_ownership}",
                f"  {choice.payload_availability}",
                f"  {choice.upstream_relationship}",
            )
        )
    lines.extend(
        (
            "",
            f"Source revision: {_short(view.source_revision, profile)}",
            f"Canonical digest: {_short(view.canonical_digest, profile)}",
        )
    )
    if view.registry_revision is not None:
        lines.append(f"Registry baseline: {_short(view.registry_revision, profile)}")
    if not view.confirmable:
        # The refusal replaces the review rather than sitting beside it: a digest on screen is an
        # invitation to confirm, and there is nothing here to confirm.
        lines.append("This Candidate cannot be promoted:")
        lines.extend(f"  - {item}" for item in view.refusals)
        return tuple(lines)
    lines.append(f"Validation report: {_short(view.validation_report_digest or '', profile)}")
    lines.append(f"Effective policy: {_short(view.effective_policy_digest or '', profile)}")
    if view.warnings:
        lines.append("Warnings carried into the audit record:")
        lines.extend(f"  - {item}" for item in view.warnings)
    lines.append(f"Review digest: {_short(view.review_digest or '', profile)}")
    return tuple(lines)


def render_maintainer_registry_diff(
    view: MaintainerRegistryDiffView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerRegistryDiffView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer registry diff rendering needs a typed view and profile")
    lines = [
        f"{view.artifact}@{view.version} → {view.target_registry} ({view.mode})",
    ]
    if not view.plannable:
        lines.append("No registry transaction can be planned:")
        lines.extend(f"  - {item}" for item in view.refusals)
        return tuple(lines)
    lines.append(
        f"Registry snapshot before: {_short(view.expected_registry_snapshot or '', profile)}"
    )
    lines.append(f"Registry snapshot after: {_short(view.next_registry_snapshot or '', profile)}")
    lines.append(f"{view.changed_paths} {_noun(view.changed_paths, 'path')} would be written:")
    lines.extend(f"  {item.kind} {item.path}" for item in view.changes)
    remaining = view.changed_paths - len(view.changes)
    if remaining > 0:
        lines.append(f"  … and {remaining} more not listed")
    lines.append(f"Transaction digest: {_short(view.plan_digest or '', profile)}")
    return tuple(lines)


def _transaction_heading(
    candidates: tuple[MaintainerTransactionCandidateView, ...],
    target_registry: str,
    mode: str,
) -> str:
    """One transaction may carry several Candidates, so the heading names all of them."""

    named = ", ".join(f"{item.artifact}@{item.version}" for item in candidates)
    return f"{named} → {target_registry} ({mode})"


def render_maintainer_registry_validation(
    view: MaintainerRegistryValidationView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerRegistryValidationView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer registry validation rendering needs a typed view and profile")
    lines = [
        _transaction_heading(view.candidates, view.target_registry, view.mode),
        "Registry validation: Passed",
        f"Projected snapshot: {_short(view.registry_snapshot, profile)}",
        f"Approved versions: {view.approved_version_count}",
        "Checks:",
        *(f"  ✓ {item}" for item in view.checks),
    ]
    # Each Candidate carries the run and policy result that approved it, so the evidence is listed
    # per Candidate rather than summarized into one pair a transaction could not be traced through.
    for item in view.candidates:
        lines.append(f"{item.artifact}@{item.version}")
        lines.append(f"  Candidate validation: {_short(item.validation_report_digest, profile)}")
        lines.append(f"  Effective policy: {_short(item.effective_policy_digest, profile)}")
    lines.append(f"Transaction digest: {_short(view.transaction_digest, profile)}")
    lines.append("No approved registry state has been written.")
    return tuple(lines)


#: 164.7 as revised by the owner (D-249/D-255): the terminal surface stops at the local commit, and
#: what makes that commit visible to anyone else is Git work AART does not do. Each step is named in
#: the order it has to happen, because pushing alone is not approval: a review branch that has been
#: pushed is still invisible to a subscriber reading the Registry's default branch.
_AFTER_THE_LOCAL_COMMIT = (
    "Subscribers cannot see this commit yet, and AART does not push it. In Git, you:",
    "1. push this Registry branch to its remote;",
    "2. where the Registry is reviewed, open a pull request and merge it into the branch",
    "   subscribers read;",
    "3. update this local checkout to that merged branch;",
    "4. run Registry Sync to observe the approved state.",
)


def render_maintainer_registry_commit(
    view: MaintainerRegistryCommitView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerRegistryCommitView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer registry commit rendering needs a typed view and profile")
    lines = [
        _transaction_heading(view.candidates, view.target_registry, view.mode),
        (
            "Approved registry state written locally"
            if view.applied
            else "Ready to write approved registry state"
        ),
        f"Registry snapshot before: {_short(view.registry_snapshot_before, profile)}",
        f"Registry snapshot after: {_short(view.registry_snapshot_after, profile)}",
        f"Changed paths: {view.changed_paths}",
        f"Approved versions: {view.approved_version_count}",
        f"Transaction digest: {_short(view.transaction_digest, profile)}",
        f"Commit subject: {view.commit_subject}",
    ]
    if not view.applied:
        lines.append("Git push: AART does not push; this commit stays local until you push it")
        return action_prompt(lines, "Enter commits this exact local transaction.")
    lines.append(f"Local Git revision: {_short(view.commit_revision or '', profile)}")
    return (*lines, "", *_AFTER_THE_LOCAL_COMMIT)


_WORKING_TREE_LABELS = {
    MaintainerWorkingTreeState.MATCHES_SNAPSHOT: "matches the approved snapshot",
    MaintainerWorkingTreeState.DIVERGED: "differs from the approved snapshot",
    MaintainerWorkingTreeState.UNOBSERVED: "not observed",
}


def render_maintainer_registry(
    view: MaintainerRegistryView,
    *,
    selected: bool = False,
    show_working_tree: bool = True,
) -> tuple[str, ...]:
    """One subscribed registry as a row, with what it holds said under it.

    Digests are shortened in both profiles so `v` never redraws the row; they are spelt out in full
    by :func:`maintainer_registry_detail`, the description of the row under the cursor.
    """

    if not isinstance(view, MaintainerRegistryView) or not isinstance(selected, bool):
        raise ValueError("Maintainer registry rendering needs a typed view")
    fast = PresentationProfile.FAST
    lines = [
        f"{'>' if selected else ' '} {view.alias}  {'✓ Valid' if view.valid else '⚠ Attention'}",
    ]
    lines.extend(f"    - {item}" for item in view.diagnostics)
    if view.snapshot is None:
        return tuple(lines)
    lines.append(f"    Revision: {_short(view.revision or '', fast)}")
    lines.append(f"    Snapshot: {_short(view.snapshot, fast)}")
    lines.append(f"    Approved versions: {view.version_count}")
    if view.artifact_counts:
        lines.append(
            "      " + "  ".join(f"{kind.value} {count}" for kind, count in view.artifact_counts)
        )
    if show_working_tree:
        tree = view.working_tree
        lines.append(f"    Working tree: {_WORKING_TREE_LABELS[tree.state]}")
        if tree.digest is not None:
            lines.append(f"      observed {_short(tree.digest, fast)}")
        if tree.detail is not None:
            lines.append(f"      {tree.detail}")
    if not view.transactions:
        lines.append("    No promotion has been recorded in this registry yet.")
        return tuple(lines)
    lines.append("    Recent promotions (newest first):")
    for item in view.transactions:
        lines.append(
            f"      {_short(item.snapshot_after, fast)} ({item.mode}) "
            f"{len(item.candidate_ids)} {_noun(len(item.candidate_ids), 'candidate')}"
        )
        lines.extend(f"        {_short(candidate, fast)}" for candidate in item.candidate_ids)
    return tuple(lines)


def maintainer_registry_detail(view: MaintainerRegistryView) -> tuple[str, ...]:
    """The registry under the cursor with every digest in full (Verbose)."""

    if not isinstance(view, MaintainerRegistryView):
        raise ValueError("Maintainer registry detail needs a typed view")
    if view.snapshot is None:
        return ()
    lines = [f"Revision: {view.revision or 'none'}", f"Snapshot: {view.snapshot}"]
    if view.working_tree.digest is not None:
        lines.append(f"Working tree observed: {view.working_tree.digest}")
    for item in view.transactions:
        lines.append(f"Promotion {item.snapshot_after} ({item.mode})")
        lines.extend(f"  {candidate}" for candidate in item.candidate_ids)
    return tuple(lines)


def maintainer_registry_rows(
    views: tuple[MaintainerRegistryView, ...],
    *,
    cursor: str = "",
    registry_workspace_present: bool = True,
) -> tuple[str, ...]:
    """The subscribed snapshots, and nothing that introduces them.

    `QA-092`: a row of a registry snapshot does not need a line above it saying that snapshots are
    what follows. What a subscribed snapshot *is for* is an explanation rather than a state, so it
    collapses under `[v]` with the rest of them (`QA-095`, `maintainer_registry_descriptor`).
    """

    if not isinstance(views, tuple) or not isinstance(cursor, str):
        raise ValueError("Maintainer registries rendering needs typed views and a cursor")
    lines: list[str] = []
    for view in views:
        if lines:
            lines.append("")
        lines.extend(
            render_maintainer_registry(
                view,
                selected=view.alias == cursor,
                show_working_tree=registry_workspace_present,
            )
        )
    return tuple(lines)


def maintainer_workspace_row(
    view: MaintainerRegistryWorkspaceView,
    *,
    selected: bool = False,
) -> str:
    """The registry this project publishes, as one row a cursor can stand on (`QA-098`).

    The sha is part of the row rather than part of the description because it is what tells two
    checkouts of one name apart -- different branches, different remotes, the same registry id --
    and that is a distinction the reader needs while scanning, not after opening something.
    """

    if not isinstance(view, MaintainerRegistryWorkspaceView) or not isinstance(selected, bool):
        raise ValueError("a registry workspace row needs a workspace view")
    marker = "> " if selected else "  "
    return f"{marker}{view.name}" + (f"  {view.commit}" if view.commit else "")


#: 164.7 in the words the decision is made in: a maintainer may point a subscription at the branch
#: they publish to, and everybody else reads the repository's default. Saying it here is what stops
#: the branch on the row above from reading like something a consumer could subscribe to.
_WHO_SUBSCRIBES = (
    "A maintainer may subscribe to this branch; everyone else subscribes to the repository's main."
)


def maintainer_workspace_detail(view: MaintainerRegistryWorkspaceView) -> tuple[str, ...]:
    """Where this registry stands: its repository, its branch, and what is waiting (`QA-098`).

    Each statement is its own group, because the status and notice blocks read a blank line as the
    boundary between list items (`QA-096`). What the checkout knows of its remote is stated as
    knowledge rather than as fact: a frame does no I/O, so "there is no such branch" and "nobody has
    looked lately" are different sentences and never the same one.
    """

    if not isinstance(view, MaintainerRegistryWorkspaceView):
        raise ValueError("a registry workspace description needs a workspace view")
    where: list[tuple[str, ...]] = [(f"Workspace: {view.root}",)] if view.root else []
    if view.origin:
        where.append((f"Remote: {view.remote} ({view.origin})",))
    if view.branch:
        where.append((f"Branch: {view.branch}",))
    else:
        where.append(("Branch: detached HEAD — Push review requires a new branch name.",))
    if view.revision:
        where.append((f"Local HEAD: {view.revision}",))
    if view.content_digest:
        where.append((f"Local canonical content: {view.content_digest}",))
    if view.state is MaintainerPublicationState.UNPUBLISHED:
        where.append(("Remote branch: none — this branch has not been pushed yet.",))
    elif view.remote_branch:
        where.append((f"Remote branch: {view.remote_branch}",))
    if view.state is MaintainerPublicationState.AHEAD:
        count = view.unpushed or 0
        where.append(
            (
                f"{count} {_noun(count, 'commit')} here "
                f"{'is' if count == 1 else 'are'} not on {view.remote_branch} yet.",
            )
        )
    elif view.state is MaintainerPublicationState.PUBLISHED:
        where.append(("Nothing here is waiting to be pushed.",))
    elif view.remote_branch:
        where.append(
            (
                "Whether anything is waiting to be pushed was not established; "
                "press u to check upstream.",
            )
        )
    if view.push_ready:
        target = view.suggested_branch if view.needs_a_new_branch else view.branch
        where.append((f"Push: ready — review target {view.remote}/{target}.",))
    else:
        where.append(("Push unavailable:", *(f"- {item}" for item in view.push_blockers)))
    if view.branch:
        where.append((_WHO_SUBSCRIBES,))
    return separate(*where)


def render_maintainer_registry_push(
    view: MaintainerRegistryWorkspaceView,
    *,
    branch: str | None = None,
    selected: str = "",
) -> tuple[str, ...]:
    """What the cursor acts on before Push: which branch, and going on with it.

    What is being pushed -- the commit, the content digest, the remote -- is the state of the
    view and is drawn by `maintainer_registry_push_status`. §167 keeps the two apart: the actions
    block holds rows and only rows, and a labelled value is not one. Drawing the facts here put
    six lines of prose among the two rows, which is what the recorded frame matrix caught.

    A checkout already standing on a branch of its own has nothing left to choose, so the review
    is the facts plus the one line addressed to the reader, and there are no rows at all.
    """

    if not isinstance(view, MaintainerRegistryWorkspaceView):
        raise ValueError("Registry Push review needs a workspace view")
    if not view.needs_a_new_branch:
        return action_prompt(
            maintainer_registry_push_status(view, branch=branch),
            "Enter pushes this exact commit without force or merge.",
        )
    return (
        f"{'>' if selected == 'branch' else ' '} Review branch: {branch or view.suggested_branch}",
        f"{'>' if selected == 'continue' else ' '} Continue",
    )


def maintainer_registry_push_status(
    view: MaintainerRegistryWorkspaceView, *, branch: str | None = None
) -> tuple[str, ...]:
    """Screen 46j's state: what exactly would go where, and what stops it if anything does.

    The target is stated here rather than left to the branch row alone, because on a checkout that
    already stands on its own branch there is no row -- and "this exact commit" would then name a
    destination the reader was never told.
    """

    if not isinstance(view, MaintainerRegistryWorkspaceView):
        raise ValueError("Registry Push review needs a workspace view")
    target = branch or (
        view.suggested_branch if view.needs_a_new_branch else view.branch or view.suggested_branch
    )
    facts = (
        f"Registry: {view.name}",
        f"Workspace: {view.root or 'not established'}",
        f"Exact commit: {view.revision or 'not established'}",
        f"Canonical content: {view.content_digest or 'not established'}",
        f"Remote: {view.remote}",
        f"Target branch: {target}",
    )
    return separate(
        facts,
        (
            ("The current branch is the one subscribers read, so Push targets a new branch.",)
            if view.needs_a_new_branch
            else ()
        ),
        (
            ()
            if view.push_ready
            else ("Push unavailable:", *(f"- {item}" for item in view.push_blockers))
        ),
    )


def maintainer_registry_descriptor(
    views: tuple[MaintainerRegistryView, ...],
    *,
    registry_workspace_present: bool = True,
) -> tuple[str, ...]:
    """What a connected snapshot is for, which never changes and so is never news (`QA-095`).

    The operator found it drawn on every frame although it describes the idea of a registry
    snapshot rather than this project's -- *"powinno byc collapsed albo uncollapsed jak sie klika
    v"*. It is an explanation, so it obeys `[v]` like every other one (`QA-070`).
    """

    if not isinstance(views, tuple):
        raise ValueError("Maintainer registries rendering needs typed views")
    lines = [
        "Connected Registry snapshots",
        "These approved snapshots determine what Marketplace can offer.",
    ]
    if not views and registry_workspace_present:
        # `QA-075`/`QA-060`: a Registry created here is not a subscribed one until it has been
        # published to its branch and subscribed to (`D-228`).
        lines.extend(
            (
                "",
                "A Registry created here becomes connectable once it is published to its "
                "branch and subscribed to.",
            )
        )
    return tuple(lines)


def maintainer_registry_status(
    views: tuple[MaintainerRegistryView, ...],
    *,
    registry_workspace_present: bool = True,
) -> tuple[str, ...]:
    """The state of this project, said once each (`QA-094`).

    Two standing facts and no headings: what the local checkout is, and whether anything is
    subscribed here. `QA-075` is why the second is phrased about *subscribed* registries -- "No
    Registry is connected." had sat above an initialization that just succeeded, and read as that
    run having failed. What a snapshot is for moved to `maintainer_registry_descriptor`, and why a
    rebuild was refused is the notice's block rather than a second telling of the first line here.
    """

    if not isinstance(views, tuple):
        raise ValueError("Maintainer registries rendering needs typed views")
    local = (
        "Current project contains a Registry. Rebuild updates its generated files."
        if registry_workspace_present
        else "Current project is not a Registry. Initialize creates one here."
    )
    if views:
        return (local,)
    return separate((local,), ("No Registry is subscribed in this project yet.",))


def render_repository_scan(
    view: MaintainerRepositoryScanView,
    selection: tuple[str, ...],
    *,
    cursor: str = "",
) -> tuple[str, ...]:
    """Screen 46d's rows: the artifacts one pinned read found that can be adopted.

    An artifact that cannot be adopted is not a row Space could tick, so it is part of
    :func:`repository_scan_status` with the reason; what a row is, beyond its manifest and payload,
    is Verbose's description of it (:func:`repository_scan_detail`).
    """

    if (
        not isinstance(view, MaintainerRepositoryScanView)
        or not isinstance(selection, tuple)
        or not isinstance(cursor, str)
    ):
        raise ValueError("repository scan rendering needs a view, selection and cursor")
    lines: list[str] = []
    selected = frozenset(selection)
    for item in view.artifacts:
        if not item.adoptable:
            continue
        mark = "x" if item.coordinate in selected else " "
        lines.append(
            f"{'>' if item.coordinate == cursor else ' '} [{mark}] {item.coordinate}  {item.state}"
        )
        lines.append(f"    {item.summary}")
        lines.append(f"    manifest: {item.manifest_path}")
        lines.append("    declared payload:")
        lines.extend(f"      {path}" for path in item.payload_paths)
    return tuple(lines)


def repository_scan_status(view: MaintainerRepositoryScanView) -> tuple[str, ...]:
    """Screen 46d's state: what was read, and what it found that cannot be adopted, and why."""

    if not isinstance(view, MaintainerRepositoryScanView):
        raise ValueError("repository scan status needs a view")
    refused = tuple(
        (
            f"{item.coordinate}  {item.state}: cannot be adopted until its manifest passes"
            " validation",
            f"  {item.summary}",
            f"  manifest: {item.manifest_path}",
        )
        for item in view.artifacts
        if not item.adoptable
    )
    adoptable = any(item.adoptable for item in view.artifacts)
    return separate(
        (
            f"Repository scan: {view.url}",
            f"Resolved commit: {view.commit}",
            f"{view.manifest_count} explicit manifest(s) found; this repository was not saved as"
            " a Source.",
        ),
        *refused,
        () if adoptable else ("Nothing in this repository can be adopted.",),
    )


def repository_scan_detail(view: MaintainerRepositoryScanView, cursor: str) -> tuple[str, ...]:
    """The scanned artifact under the cursor, as its manifest declares it (Verbose)."""

    item = view.artifact(cursor)
    if item is None or not item.adoptable:
        return ()
    return (f"Kind: {item.kind}", f"Name: {item.name}", f"Version: {item.version}")


def render_repository_adoption_review(
    view: MaintainerAdoptionReviewView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 46e: the immutable copies and local paths one confirmation will write."""

    if not isinstance(view, MaintainerAdoptionReviewView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("repository adoption review rendering needs a view and profile")
    lines = [
        f"Adopt {len(view.selected)} artifact(s) from {view.url}",
        f"Resolved commit: {view.commit}",
        "Selected artifacts:",
        *(f"  {coordinate}" for coordinate in view.selected),
        "Registry paths that will change:",
        *(f"  {path}" for path in view.changed_paths),
        "",
        "The repository will not be saved as a Source. Nothing is pushed or merged.",
    ]
    if profile is PresentationProfile.VERBOSE:
        lines.append(f"Review identity: {view.review_digest}")
    return action_prompt(
        lines, "Press Enter to write this exact transaction into the local registry checkout."
    )


def render_adopted_artifacts(
    artifacts: tuple[MaintainerAdoptedArtifactView, ...],
    *,
    cursor: str = "",
) -> tuple[str, ...]:
    """Screen 46f: packages with enough immutable provenance for an on-demand check.

    What Enter does is the legend's; the full provenance of the row under the cursor is Verbose's
    description of it (:func:`adopted_artifact_detail`), so `v` never grows the rows.
    """

    if any(not isinstance(item, MaintainerAdoptedArtifactView) for item in artifacts) or (
        not isinstance(cursor, str)
    ):
        raise ValueError("adopted artifact rendering needs typed views and a cursor")
    if not artifacts:
        return (
            "No repository-adopted artifacts are in this Registry yet.",
            "Scan a repository first, then adopt one of its explicit manifests.",
        )
    lines = ["Repository-adopted artifacts", ""]
    for item in artifacts:
        lines.append(f"{'>' if item.coordinate == cursor else ' '} {item.coordinate}")
        lines.append(f"    {item.url} at {item.ref}")
        lines.append(
            f"    adopted commit: {_short(item.recorded_commit, PresentationProfile.FAST)}"
        )
    return tuple(lines)


def adopted_artifact_detail(
    artifacts: tuple[MaintainerAdoptedArtifactView, ...], cursor: str
) -> tuple[str, ...]:
    """The adopted artifact under the cursor, with the provenance its check compares against."""

    item = next((entry for entry in artifacts if entry.coordinate == cursor), None)
    if item is None:
        return ()
    return (
        f"Adopted commit: {item.recorded_commit}",
        f"Manifest: {item.manifest_path}",
        f"Recorded input: {item.input_digest}",
    )


def render_adoption_upstream_check(
    view: MaintainerAdoptionUpstreamView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 46g: one explicit comparison, never continuous monitoring."""

    if not isinstance(view, MaintainerAdoptionUpstreamView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("adoption upstream rendering needs a typed view and profile")
    artifact = view.artifact
    lines = [
        f"Upstream check: {artifact.coordinate}",
        f"Result: {_human(view.disposition)}",
        f"Upstream: {artifact.url} at {artifact.ref}",
        f"Adopted commit: {_short(artifact.recorded_commit, profile)}",
    ]
    if view.resolved_commit is not None:
        lines.append(f"Resolved now: {_short(view.resolved_commit, profile)}")
    if view.disposition == "unchanged":
        lines.append("The declared manifest and payload are unchanged.")
    elif view.disposition == "changed" and view.proposal_available:
        lines.extend(
            (
                f"New immutable version proposed: {view.observed_coordinate}",
                "Press a to review the exact local Registry transaction.",
            )
        )
    elif view.disposition == "changed" and view.new_version_required:
        lines.extend(
            (
                "The declared manifest or payload changed at the published version.",
                "The upstream author must declare a new version before AART can propose a copy.",
            )
        )
    elif view.disposition == "missing":
        lines.append("The recorded manifest is no longer present at this branch or tag.")
    elif view.disposition == "unreachable":
        lines.append("The upstream could not be read, so its current state is unknown.")
    else:
        lines.append("The upstream declaration is invalid and cannot become a proposal.")
    lines.extend(f"  {detail}" for detail in view.details)
    lines.append("This check saved no Source and changed no Registry files.")
    return tuple(lines)


def render_maintainer_bulk_promotion(
    views: tuple[MaintainerBulkPromotionView, ...],
    selection: tuple[str, ...],
    *,
    cursor: str = "",
) -> tuple[str, ...]:
    """Screen 47's rows: the Candidates one registry transaction may carry, under their registry.

    What it may not carry, and why, is not a row Space could tick, so it is the view's status
    (:func:`maintainer_bulk_promotion_status`): a refused Candidate is named with its reason rather
    than silently absent, because "it is not in the list" and "it does not exist" look identical
    on screen otherwise.
    """

    if (
        not isinstance(views, tuple)
        or not isinstance(selection, tuple)
        or not isinstance(cursor, str)
    ):
        raise ValueError("Maintainer bulk promotion rendering needs typed views and a cursor")
    lines: list[str] = []
    for view in views:
        if not view.candidates:
            continue
        if lines:
            lines.append("")
        lines.append(f"{view.target_registry}")
        # `QA-030` again: these rows are a table without a header, and were ragged for the same
        # reason. The cursor gutter is spent first, so the grid gets what is left.
        selectable = [
            (
                "[x]" if item.candidate_id in selection else "[ ]",
                item.artifact,
                item.version,
                _human(item.state.value),
            )
            for item in view.candidates
        ]
        grid = columns(selectable, width=CONTENT_MEASURE - _BULK_INDENT)
        lines.extend(
            f"{'>' if item.candidate_id == cursor else ' '} {line}"
            for item, line in zip(view.candidates, grid, strict=True)
        )
    return tuple(lines)


def maintainer_bulk_promotion_status(
    views: tuple[MaintainerBulkPromotionView, ...],
) -> tuple[str, ...]:
    """Screen 47's state: per registry, what it refuses and which Candidates it cannot carry."""

    if not isinstance(views, tuple):
        raise ValueError("Maintainer bulk promotion status needs typed views")
    if not views:
        return ("Bulk promotion has nothing composed yet.",)
    statements: list[tuple[str, ...]] = []
    for view in views:
        said = (
            *(f"  - {item}" for item in view.refusals),
            *(
                ("  No Candidate of this registry can be promoted right now.",)
                if not view.candidates and not view.refusals
                else ()
            ),
            *(
                f"  Not promotable: {blocked.artifact} — {blocked.reason}"
                for blocked in view.excluded
            ),
        )
        if said:
            statements.append((view.target_registry, *said))
    return separate(*statements)
