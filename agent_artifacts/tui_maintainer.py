"""Pure text renderers for canonical Maintainer Mode projections."""

from __future__ import annotations

from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.application.maintainer_views import (
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
from agent_artifacts.tui_layout import (
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
    return separate(
        (f"Sources: {view.source_count}",),
        (f"Candidates: {view.candidate_count}",),
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
        f"Candidates: {source.candidate_count} — {source.ready_count} ready, "
        f"{source.invalid_count} invalid",
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
    rows = [("", *_CANDIDATE_HEADINGS)]
    rows.extend(
        (
            ">" if item.id == cursor else "",
            _human(item.state.value),
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
        ("Status", _human(focused.state.value)),
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
        f"{view.artifact}@{view.version} — {_human(view.state.value)}",
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
            if profile is PresentationProfile.VERBOSE:
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
    profile: PresentationProfile,
    *,
    cursor: str = "",
) -> tuple[str, ...]:
    """Screen 53: the facets, what is ticked, and what the narrowing currently leaves.

    The count beside each value is what choosing it would leave, not how many carry it, so a
    narrowing that selects nothing is legible before it is applied rather than after screen 35
    goes blank.
    """

    if (
        not isinstance(view, MaintainerCandidateFilterView)
        or not isinstance(profile, PresentationProfile)
        or not isinstance(cursor, str)
        or any(character in cursor for character in "\r\n")
    ):
        raise ValueError("Maintainer Candidate filter rendering needs a view and a profile")
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
            line = f"{pointer} {mark} {option.value}"
            if profile is PresentationProfile.VERBOSE:
                line += f"  — {option.matching} would match"
            lines.append(line)
    lines.append("")
    if view.query:
        lines.append(f"Search: {view.query}")
    lines.append("No filter is applied." if view.is_empty else "Filtered.")
    lines.append(f"Showing {view.matching} of {view.total} Candidates")
    return tuple(lines)


def render_maintainer_collection_candidates(
    candidates: tuple[MaintainerCollectionCandidateView, ...],
    *,
    cursor: str = "",
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 51: versioned Collection Candidates, never flattened to imperative steps."""

    if (
        any(not isinstance(item, MaintainerCollectionCandidateView) for item in candidates)
        or not isinstance(cursor, str)
        or any(character in cursor for character in "\r\n")
        or not isinstance(profile, PresentationProfile)
    ):
        raise ValueError("Maintainer Collection rendering needs Candidate views and a profile")
    if not candidates:
        return ("No Collection Candidates are available.",)
    lines = []
    for candidate in candidates:
        lines.append(
            f"{'>' if candidate.candidate_id == cursor else ' '} {candidate.coordinate} — "
            f"{_human(candidate.state.value)} · {_noun(len(candidate.members), 'member')}"
        )
        if profile is PresentationProfile.VERBOSE:
            lines.extend(
                (
                    f"    Source: {candidate.source_alias} · {candidate.source_location}",
                    f"    Manifest: {candidate.manifest_path}",
                    f"    Candidate: {candidate.candidate_id}",
                )
            )
            lines.extend(f"    - {item}" for item in candidate.members)
    return tuple(lines)


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
    *,
    show_files: bool = False,
) -> tuple[str, ...]:
    if (
        not isinstance(view, MaintainerCandidateView)
        or not isinstance(profile, PresentationProfile)
        or not isinstance(show_files, bool)
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
    if not show_files:
        lines.append("Press f to view bounded redacted file diffs; d returns to summary.")
        return tuple(lines)
    lines.extend(("", "Bounded redacted file diffs:"))
    for changed_file in view.file_changes:
        lines.append(f"[{changed_file.path}]")
        lines.extend(f"  {line}" for line in changed_file.diff)
        if not changed_file.diff:
            lines.append("  content omitted by the global diff bound")
    lines.append("Press f to hide file diffs.")
    return tuple(lines)


def _allowlist(values: tuple[str, ...] | None) -> str:
    """What a policy permits, keeping "unconstrained" distinct from "nothing is permitted"."""

    if values is None:
        return "unconstrained"
    return ", ".join(values) if values else "none permitted"


def render_maintainer_validation(
    view: MaintainerValidationView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerValidationView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer validation rendering needs a typed view and profile")
    lines = [
        f"{view.artifact}@{view.version} — {_human(view.state.value)}",
        f"{view.error_count} {_noun(view.error_count, 'error')}, "
        f"{view.warning_count} {_noun(view.warning_count, 'warning')}",
        "Checks:",
    ]
    for item in view.checks:
        marker = " · required" if item.required else ""
        lines.append(f"  {item.label} — {_human(item.outcome)}{marker}")
        if profile is PresentationProfile.VERBOSE:
            lines.extend(f"    - {detail.message}" for detail in item.details)
    if view.unmet_requirements:
        lines.append(f"Unmet requirements: {', '.join(view.unmet_requirements)}")
    return tuple(lines)


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


def render_maintainer_registry_commit(
    view: MaintainerRegistryCommitView,
    profile: PresentationProfile,
    *,
    publication_remote: str = "origin",
    publication_branch: str = "",
    cursor: str = "",
    configure_publication: bool = False,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerRegistryCommitView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Maintainer registry commit rendering needs a typed view and profile")
    if not isinstance(configure_publication, bool) or any(
        not isinstance(value, str) or any(character in value for character in "\r\n")
        for value in (publication_remote, publication_branch, cursor)
    ):
        raise ValueError("Maintainer registry publication rendering needs safe configuration")
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
        lines.append("Git push: separate explicit action after this commit")
        return action_prompt(lines, "Enter commits this exact local transaction.")
    lines.append(f"Local Git revision: {_short(view.commit_revision or '', profile)}")
    if view.publication_remote is not None:
        target = f"{view.publication_remote}/{view.publication_branch}"
        if view.publication_outcome is not None:
            moved = {
                "created": f"created {target}",
                "updated": f"updated {target}",
                "already-current": f"{target} already held this revision",
            }[view.publication_outcome]
            lines.extend(
                (
                    f"{view.target_registry}: {moved} at {(view.commit_revision or '')[:12]}",
                    "Nothing was merged. Open a pull request for the reviewer to merge it.",
                )
            )
            return tuple(lines)
        lines.extend(
            (
                # The reader recognises the target as one name, so the review says it as one.
                f"Ready to push the reviewed commit to {target}",
                f"Publication remote: {view.publication_remote}",
                f"Publication branch: {view.publication_branch}",
                "Nothing will be merged; the default branch is never a publication target.",
            )
        )
        return action_prompt(lines, "Enter pushes this exact revision.")
    if not configure_publication:
        lines.append("Git publication: not yet published; press p to choose a review branch.")
        return tuple(lines)
    values = {
        "publication-remote": publication_remote or "<type the Git remote>",
        "publication-branch": publication_branch or "<type a non-default branch>",
        "publish": "Review publication",
    }
    labels = {
        "publication-remote": "Publication remote",
        "publication-branch": "Publication branch",
        "publish": "Continue",
    }
    rows = ("publication-remote", "publication-branch", "publish")
    lines.extend(
        (
            "Configure where this reviewed commit is published:",
            *(f"{'>' if row == cursor else ' '} {labels[row]}: {values[row]}" for row in rows),
            "Nothing is pushed until this target is reviewed; nothing here can merge.",
        )
    )
    return tuple(lines)


_WORKING_TREE_LABELS = {
    MaintainerWorkingTreeState.MATCHES_SNAPSHOT: "matches the approved snapshot",
    MaintainerWorkingTreeState.DIVERGED: "differs from the approved snapshot",
    MaintainerWorkingTreeState.UNOBSERVED: "not observed",
}


def render_maintainer_registry(
    view: MaintainerRegistryView,
    profile: PresentationProfile,
    *,
    show_working_tree: bool = True,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerRegistryView) or not isinstance(profile, PresentationProfile):
        raise ValueError("Maintainer registry rendering needs a typed view and profile")
    lines = [
        f"{view.alias}  {'✓ Valid' if view.valid else '⚠ Attention'}",
    ]
    lines.extend(f"  - {item}" for item in view.diagnostics)
    if view.snapshot is None:
        return tuple(lines)
    lines.append(f"Revision: {_short(view.revision or '', profile)}")
    lines.append(f"Snapshot: {_short(view.snapshot, profile)}")
    lines.append(f"Approved versions: {view.version_count}")
    if view.artifact_counts:
        lines.append(
            "  " + "  ".join(f"{kind.value} {count}" for kind, count in view.artifact_counts)
        )
    if show_working_tree:
        tree = view.working_tree
        lines.append(f"Working tree: {_WORKING_TREE_LABELS[tree.state]}")
        if tree.digest is not None:
            lines.append(f"  observed {_short(tree.digest, profile)}")
        if tree.detail is not None:
            lines.append(f"  {tree.detail}")
    if not view.transactions:
        lines.append("No promotion has been recorded in this registry yet.")
        return tuple(lines)
    lines.append("Recent promotions (newest first):")
    for item in view.transactions:
        lines.append(
            f"  {_short(item.snapshot_after, profile)} ({item.mode}) "
            f"{len(item.candidate_ids)} {_noun(len(item.candidate_ids), 'candidate')}"
        )
        lines.extend(f"    {_short(candidate, profile)}" for candidate in item.candidate_ids)
    return tuple(lines)


def maintainer_registry_rows(
    views: tuple[MaintainerRegistryView, ...],
    profile: PresentationProfile,
    *,
    registry_workspace_present: bool = True,
) -> tuple[str, ...]:
    """The subscribed snapshots, and nothing that introduces them.

    `QA-092`: a row of a registry snapshot does not need a line above it saying that snapshots are
    what follows. What a subscribed snapshot *is for* is an explanation rather than a state, so it
    collapses under `[v]` with the rest of them (`QA-095`, `maintainer_registry_descriptor`).
    """

    if not isinstance(views, tuple) or not isinstance(profile, PresentationProfile):
        raise ValueError("Maintainer registries rendering needs typed views and a profile")
    lines: list[str] = []
    for view in views:
        if lines:
            lines.append("")
        lines.extend(
            render_maintainer_registry(view, profile, show_working_tree=registry_workspace_present)
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

#: The operator asked for this sentence by name -- *"dopisz ze zeby zmiany byly dostepne to nalezy
#: zpushowac zmiany na remote brancha, ale aart tego za Ciebie nie zrobi, musisz to zrobic sam"*.
#: It stands only while something is actually waiting, so it stays an instruction rather than
#: becoming decoration on a screen with nothing to do.
_NOBODY_PUSHES_FOR_YOU = (
    "Changes become available to subscribers once this branch is pushed. "
    "AART does not push it for you."
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
    where = [(f"Repository: {view.origin}",)] if view.origin else []
    if view.branch:
        where.append((f"Branch: {view.branch}",))
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
    if view.state in {MaintainerPublicationState.UNPUBLISHED, MaintainerPublicationState.AHEAD}:
        where.append((_NOBODY_PUSHES_FOR_YOU,))
    if view.branch:
        where.append((_WHO_SUBSCRIBES,))
    return separate(*where)


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
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 46d: exact manifests from one pinned read, with adoption eligibility visible."""

    if (
        not isinstance(view, MaintainerRepositoryScanView)
        or not isinstance(selection, tuple)
        or not isinstance(cursor, str)
        or not isinstance(profile, PresentationProfile)
    ):
        raise ValueError("repository scan rendering needs a view, selection, cursor and profile")
    lines = [
        f"Repository scan: {view.url}",
        f"Resolved commit: {view.commit}",
        f"{view.manifest_count} explicit manifest(s) found; this repository was not saved as a Source.",
        "",
    ]
    selected = frozenset(selection)
    for item in view.artifacts:
        mark = "x" if item.coordinate in selected else (" " if item.adoptable else "-")
        lines.append(
            f"{'>' if item.coordinate == cursor else ' '} [{mark}] {item.coordinate}  {item.state}"
        )
        lines.append(f"    {item.summary}")
        lines.append(f"    manifest: {item.manifest_path}")
        lines.append("    declared payload:")
        lines.extend(f"      {path}" for path in item.payload_paths)
        if not item.adoptable:
            lines.append("    cannot be adopted until its manifest passes validation")
        if profile is PresentationProfile.VERBOSE:
            lines.append(f"    kind: {item.kind}; name: {item.name}; version: {item.version}")
    lines.extend(("", "Space selects an adoptable artifact; a reviews the selected copies."))
    return tuple(lines)


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
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 46f: packages with enough immutable provenance for an on-demand check."""

    if (
        any(not isinstance(item, MaintainerAdoptedArtifactView) for item in artifacts)
        or not isinstance(cursor, str)
        or not isinstance(profile, PresentationProfile)
    ):
        raise ValueError("adopted artifact rendering needs typed views, cursor and profile")
    if not artifacts:
        return (
            "No repository-adopted artifacts are in this Registry yet.",
            "Scan a repository first, then adopt one of its explicit manifests.",
        )
    lines = ["Repository-adopted artifacts", ""]
    for item in artifacts:
        lines.append(f"{'>' if item.coordinate == cursor else ' '} {item.coordinate}")
        lines.append(f"    {item.url} at {item.ref}")
        lines.append(f"    adopted commit: {_short(item.recorded_commit, profile)}")
        if profile is PresentationProfile.VERBOSE:
            lines.append(f"    manifest: {item.manifest_path}")
            lines.append(f"    recorded input: {item.input_digest}")
    lines.extend(("", "Enter checks the focused artifact's upstream now."))
    return tuple(lines)


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
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 47: what one registry transaction may carry, and what it may not.

    A Candidate the run refused is named here with its reason rather than being silently absent:
    "it is not in the list" and "it does not exist" look identical on screen otherwise.
    """

    if (
        not isinstance(views, tuple)
        or not isinstance(selection, tuple)
        or not isinstance(profile, PresentationProfile)
    ):
        raise ValueError("Maintainer bulk promotion rendering needs typed views and a profile")
    if not views:
        return ("Bulk promotion has nothing composed yet.",)
    lines: list[str] = []
    chosen = 0
    for index, view in enumerate(views):
        if index:
            lines.append("")
        lines.append(f"{view.target_registry}")
        lines.extend(f"  - {item}" for item in view.refusals)
        # `QA-030` again: these rows are a table without a header, and were ragged for the same
        # reason. Two spaces of indent are spent on the nesting, so the grid gets what is left.
        selectable: list[tuple[str, ...]] = []
        for item in view.candidates:
            mark = "[x]" if item.candidate_id in selection else "[ ]"
            chosen += 1 if item.candidate_id in selection else 0
            selectable.append((mark, item.artifact, item.version, _human(item.state.value)))
        lines.extend(
            f"  {line}" for line in columns(selectable, width=CONTENT_MEASURE - _BULK_INDENT)
        )
        if not view.candidates and not view.refusals:
            lines.append("  No Candidate of this registry can be promoted right now.")
        for blocked in view.excluded:
            lines.append(f"  Not promotable: {blocked.artifact} — {blocked.reason}")
    lines.append("")
    lines.append(f"{chosen} selected")
    return tuple(lines)
