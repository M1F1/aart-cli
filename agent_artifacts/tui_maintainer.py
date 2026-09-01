"""Pure text renderers for canonical Maintainer Mode projections."""

from __future__ import annotations

from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.application.maintainer_views import (
    MaintainerCandidateView,
    MaintainerDashboardView,
    MaintainerSourceSyncResultView,
    MaintainerSourceSyncReviewView,
    MaintainerSourceView,
)

__all__ = [
    "render_maintainer_dashboard",
    "render_maintainer_candidate",
    "render_maintainer_candidate_diff",
    "render_maintainer_candidates",
    "render_maintainer_source",
    "render_source_sync_result",
    "render_source_sync_review",
    "render_maintainer_sources",
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
    lines = [
        "Maintainer overview",
        f"Sources: {view.source_count}",
        f"Candidates: {view.candidate_count}",
        f"Validation failures: {view.validation_failure_count}",
        f"Ready for promotion: {view.ready_count}",
        "Recent maintainer activity:",
    ]
    lines.extend(f"  - {item}" for item in view.recent_activity)
    if not view.recent_activity:
        lines.append("  - none yet")
    return tuple(lines)


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
    lines = [
        f"Sync authoring Source {view.alias}",
        f"Location: {view.location}",
        f"Branch: {view.branch or 'local'}",
        f"Current revision: {revision}",
        f"Current Candidates: {view.candidate_count}",
        f"Compare with approved registry: {view.target_registry}@{registry_revision}",
        "Effects: fetch/read, exact manifest discovery, compile, Candidate reconciliation",
        "Registry mutations: none",
    ]
    if profile is PresentationProfile.VERBOSE:
        lines.extend(
            (
                f"Source kind: {_human(view.kind)}",
                f"Approved snapshot: {view.approved_snapshot}",
            )
        )
    lines.extend((f"Review identity: {view.review_digest}", "Press Enter to synchronize."))
    return tuple(lines)


def render_source_sync_result(
    view: MaintainerSourceSyncResultView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if not isinstance(view, MaintainerSourceSyncResultView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Source Sync result rendering needs a typed view and profile")
    revision = view.revision if profile is PresentationProfile.VERBOSE else view.revision[:12]
    lines = [
        f"Source Sync {view.disposition}: {view.alias}",
        f"Pinned revision: {revision}",
        f"Discovered manifests: {view.manifest_count}",
        f"Candidates: {view.candidate_count}",
        f"Target registry observed: {view.target_registry}",
        "Registry mutations: none",
    ]
    if profile is PresentationProfile.VERBOSE:
        lines.append(
            "Candidate states: "
            + (
                ", ".join(f"{state.value}={count}" for state, count in view.candidate_states)
                or "none"
            )
        )
    lines.append(f"Review identity: {view.review_digest}")
    return tuple(lines)


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
    lines = ["STATUS               ARTIFACT                 VERSION       SOURCE"]
    for item in candidates:
        prefix = ">" if item.id == cursor else " "
        lines.append(
            f"{prefix} {_human(item.state.value):<18} {item.artifact:<24} "
            f"{item.version:<13} {item.source_alias}"
        )
        if profile is PresentationProfile.VERBOSE:
            lines.append(f"    Candidate {item.id} · target {item.target_registry}")
    return tuple(lines)


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
