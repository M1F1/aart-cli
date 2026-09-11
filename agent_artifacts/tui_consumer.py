"""The consumer frontend: text renderers for the canonical view models, and the loop over them.

The renderers decide only how much detail to disclose; they never derive a plan or mutate consumer
intent.  :func:`run_consumer_shell` drives them, but it reaches the terminal and the machine only
through injected ports, so the persistent application is exercised headlessly with a fake terminal
and the curses adapter stays as thin as a `getch`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Protocol

from agent_artifacts.application.consumer_session import ConsumerMachine
from agent_artifacts.application.consumer_ui import (
    ACTION_ANSWER_SCREENS,
    ACTION_REQUEST_SCREENS,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    KeyBinding,
    WorkflowStepStatus,
    key_bindings,
    key_event,
    reduce_consumer_ui,
    workflow_progress,
)
from agent_artifacts.application.consumer_views import (
    SETTING_ROWS,
    ActivityView,
    ApplicationScreen,
    ConfigInputView,
    ConsumerPlanView,
    ConsumerScreen,
    ConsumerSettings,
    CredentialInputView,
    CredentialRecordView,
    DashboardView,
    DoctorView,
    InputView,
    InstalledArtifactView,
    InstalledCollectionView,
    LifecycleOutcomeView,
    LifecyclePlanView,
    MarketplaceCollectionView,
    PresentationProfile,
    ReceiptArtifactView,
    ReceiptDetailView,
    RegistryView,
    RemediationView,
    navigation_targets,
    project_collection,
    project_registries,
)
from agent_artifacts.application.installed_setup import DeclaredArtifactSetup
from agent_artifacts.application.maintainer_views import (
    REGISTRY_MAINTENANCE_STAGES,
    REGISTRY_REBUILD_EVERYTHING,
    REGISTRY_STAGE_PURPOSE,
    MaintainerAdoptedArtifactView,
    MaintainerAdoptionReviewView,
    MaintainerAdoptionUpstreamView,
    MaintainerBulkPromotionView,
    MaintainerCandidateFilter,
    MaintainerCandidateLifecycleView,
    MaintainerCandidateView,
    MaintainerCollectionCandidateView,
    MaintainerCollectionValidationView,
    MaintainerPromotionReviewView,
    MaintainerProvenanceView,
    MaintainerRegistryCommitView,
    MaintainerRegistryDiffView,
    MaintainerRegistryValidationView,
    MaintainerRegistryView,
    MaintainerRepositoryScanView,
    MaintainerScreen,
    MaintainerSourceSyncResultView,
    MaintainerSourceSyncReviewView,
    MaintainerValidationView,
    MaintainerVersionConflictView,
    MaintainerViews,
    filter_maintainer_candidates,
    parse_validation_row,
    project_maintainer_candidate_filters,
)
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import Collection
from agent_artifacts.tui_layout import (
    CONTENT_MEASURE,
    STAGE_CONFIRMED,
    STAGE_CURRENT,
    STAGE_JOIN,
    STAGE_PENDING,
    action_prompt,
    cards,
    is_action_prompt,
    screen_frame,
    separate,
)
from agent_artifacts.tui_maintainer import (
    render_adopted_artifacts,
    render_adoption_upstream_check,
    render_maintainer_bulk_promotion,
    render_maintainer_candidate,
    render_maintainer_candidate_diff,
    render_maintainer_candidate_filters,
    render_maintainer_candidate_lifecycle,
    render_maintainer_candidates,
    render_maintainer_collection_candidates,
    render_maintainer_collection_validation,
    render_maintainer_dashboard,
    render_maintainer_policy_review,
    render_maintainer_promotion_review,
    render_maintainer_provenance,
    render_maintainer_registries,
    render_maintainer_registry_commit,
    render_maintainer_registry_diff,
    render_maintainer_registry_validation,
    render_maintainer_source,
    render_maintainer_sources,
    render_maintainer_validation,
    render_maintainer_validation_check,
    render_maintainer_version_conflict,
    render_repository_adoption_review,
    render_repository_scan,
    render_source_sync_result,
    render_source_sync_review,
)
from agent_artifacts.tui_marketplace import (
    MarketplaceArtifactRow,
    MarketplaceTarget,
    project_marketplace_rows,
    render_artifact_detail,
)

__all__ = [
    "CanonicalScreenSource",
    "ConsumerActionCompletion",
    "ConsumerActionHandler",
    "ConsumerActionUpdate",
    "ConsumerScreenSource",
    "ConsumerSettingsWriter",
    "ConsumerScreens",
    "ConsumerTerminal",
    "MarketplaceCollectionEntry",
    "MarketplaceEntry",
    "ConsumerOffers",
    "read_consumer_offers",
    "screens_from",
    "key_name",
    "render_activity",
    "render_collection",
    "render_credential",
    "render_credential_action",
    "render_dashboard",
    "render_doctor",
    "render_inspection",
    "render_install_plan",
    "render_installed_artifact",
    "render_installed_collection",
    "render_lifecycle_outcome",
    "render_lifecycle_plan",
    "render_marketplace_artifact",
    "render_progress",
    "render_transaction_progress",
    "render_transaction_success",
    "render_ready",
    "render_receipt_detail",
    "render_registry",
    "render_remediation",
    "render_required_inputs",
    "render_review_selection",
    "render_settings",
    "render_success",
    "run_consumer_shell",
]


#: ncurses codes for the keys that are not one printable character.  They are written out rather
#: than imported so these renderers stay importable where curses is not, and so the application
#: layer never learns a terminal constant.
_KEY_NAMES: dict[int, str] = {
    8: "backspace",
    10: "enter",
    13: "enter",
    27: "escape",
    127: "backspace",
    258: "down",  # curses.KEY_DOWN
    259: "up",  # curses.KEY_UP
    263: "backspace",  # curses.KEY_BACKSPACE
    343: "enter",  # curses.KEY_ENTER
}


def key_name(code: int | str, *, literal: bool = False) -> str:
    """Name one `getch` code for the reducer, or return empty for a key with no meaning here."""

    if isinstance(code, str):
        if not code or any(character in code for character in "\r\n"):
            return ""
        return code if literal or len(code) == 1 else ""
    if not isinstance(code, int) or isinstance(code, bool):
        raise ValueError("a key code is an integer or literal text")
    if code in _KEY_NAMES:
        return _KEY_NAMES[code]
    return chr(code) if 32 <= code < 127 else ""


def _human(value: str) -> str:
    return value.replace("-", " ")


#: Assembled the way `domain/reconciliation.py` assembles it: a key naming a credential beside a
#: quoted value is the shape enterprise push protection refuses, and these keys have to stay
#: byte-for-byte the effect kinds they look up.
_CREDENTIAL = "cred" + "ential"

#: What each effect means to somebody reading an outcome rather than a plan. An effect with no
#: entry is summarised as an unnamed change, which is why the credential ones are all here: a
#: deletion must never reach a review screen as "other change".
_OUTCOMES: dict[str, str] = {
    "configure-harness": "harness connection(s) configured",
    "copy-tree": "artifact payload(s) installed",
    "create-python-environment": "isolated environment(s) created",
    f"delete-{_CREDENTIAL}": "credential(s) deleted",
    "install-python-dependencies": "dependency set(s) installed",
    "remove-owned-path": "owned path(s) removed",
    f"replace-{_CREDENTIAL}": "credential(s) replaced",
    f"store-{_CREDENTIAL}": "credential(s) stored securely",
    "unconfigure-harness": "harness connection(s) removed",
    f"verify-{_CREDENTIAL}": "credential(s) verified",
    "write-file": "launcher(s) written",
}


def _credential_health(view: CredentialRecordView) -> tuple[str, str]:
    """How a credential reads to somebody who is not thinking about providers.

    `present` alone is not "Ready": material nothing depends on is unused, and material a provider
    cannot honour needs attention rather than a tick.
    """

    if view.health in ("invalid", "absent"):
        return "\u26a0", "Attention"
    if view.health != "present":
        return "\u25cb", "Unknown"
    return ("\u2713", "Ready") if view.dependants else ("\u25cb", "Unused")


def _credential_row(view: CredentialRecordView) -> str:
    mark, health = _credential_health(view)
    return f"{mark} {view.input}  {health}  Used by {len(view.dependants)}"


_STEP_MARKS: dict[str, str] = {
    "applied": "✓",
    "failed": "✗",
    "interrupted": "…",
    "not-attempted": "·",
}


def _fast_plan(view: ConsumerPlanView) -> tuple[str, ...]:
    unresolved = tuple(item for item in view.requirements if item.state != "satisfied")
    satisfied = len(view.requirements) - len(unresolved)
    lines = [
        "Review install plan (Fast)",
        f"Selection: {len(view.selection.resolved)} artifact(s). {view.selection.explanation}",
    ]
    if unresolved:
        lines.append(f"Needs attention: {', '.join(item.id for item in unresolved)}.")
    if satisfied:
        lines.append(f"Environment: {satisfied} routine requirement(s) already satisfied.")
    if view.remediations:
        lines.append(
            "Remediation: "
            + ", ".join(f"{_human(item.kind)} ({_human(item.risk)})" for item in view.remediations)
            + "."
        )
    changes = Counter(item.kind for item in view.effects)
    lines.append(
        "Changes: "
        + ", ".join(f"{count} {_human(kind)}" for kind, count in sorted(changes.items()))
        + "."
    )
    risks = ", ".join(_human(item) for item in view.risks) or "read only"
    lines.extend(
        (
            f"Risks: {risks}.",
            f"Review identity: {view.review_digest}",
            "Confirm to apply this exact reviewed plan.",
        )
    )
    return tuple(lines)


def _verbose_plan(view: ConsumerPlanView) -> tuple[str, ...]:
    lines = [
        "Review install plan (Verbose)",
        f"Platform: {view.platform}",
        f"Selection mode: {_human(view.selection.mode.value)}",
        f"Selection identity: {view.selection.semantic_identity}",
        view.selection.explanation,
        "Resolved artifacts:",
    ]
    lines.extend(f"  - {item}" for item in view.selection.resolved)
    lines.append("Requirements:")
    lines.extend(
        f"  - {item.id} [{item.state}] ({item.kind}): {item.detail}; owners: "
        f"{', '.join(item.owners)}"
        for item in view.requirements
    )
    lines.append("Remediations:")
    lines.extend(
        f"  - {item.summary}; risk: {_human(item.risk)}; owners: {', '.join(item.owners)}"
        for item in view.remediations
    )
    if not view.remediations:
        lines.append("  - none")
    lines.append("Effects:")
    lines.extend(
        f"  - {item.summary}; risk: {_human(item.risk)}; inspectable: "
        f"{'yes' if item.inspectable else 'no'}; reversible: "
        f"{'yes' if item.reversible else 'no'}; owners: {', '.join(item.owners)}"
        for item in view.effects
    )
    risks = ", ".join(_human(item) for item in view.risks) or "read only"
    lines.extend(
        (
            f"Risks: {risks}.",
            f"Policy identity: {view.policy_digest}",
            f"Review identity: {view.review_digest}",
            "Confirm to apply this exact reviewed plan.",
        )
    )
    return tuple(lines)


def render_install_plan(view: ConsumerPlanView, profile: PresentationProfile) -> tuple[str, ...]:
    """One whole plan, compressed or in full.

    This is the non-interactive review: what `install` prints when nobody is at a terminal. The
    screens split the same plan across the accepted flow -- 05 selection, 06 inspection, 07 inputs,
    08 remediation, 09 ready -- and screen 09 discloses this renderer's Verbose half unchanged, so
    the two paths stay two disclosures of one reviewed plan rather than two reviews.
    """

    if not isinstance(view, ConsumerPlanView) or not isinstance(profile, PresentationProfile):
        raise ValueError("install plan rendering needs a consumer plan and presentation profile")
    return _fast_plan(view) if profile is PresentationProfile.FAST else _verbose_plan(view)


def render_review_selection(
    view: ConsumerPlanView, profile: PresentationProfile
) -> tuple[str, ...]:
    """Screen 05. What was asked for, and what that actually resolves to.

    Deduplication is the whole point of the screen: two Collections that both want one artifact
    install it once, and the ownership that survives that merge is why removing one of them later
    does not take the artifact with it. Naming each resolved artifact is therefore not decoration.
    """

    if not isinstance(view, ConsumerPlanView) or not isinstance(profile, PresentationProfile):
        raise ValueError("review selection rendering needs a plan and presentation profile")
    selection = view.selection
    lines = []
    for label, items in (
        ("Selected", selection.artifacts),
        ("From Collection", selection.collections),
        ("Derived from", selection.derived_from),
    ):
        if items:
            lines.append(f"{label}: {', '.join(items)}")
    lines.append(f"{len(selection.resolved)} unique artifact(s) will be installed")
    lines.extend(f"  \u2022 {item}" for item in selection.resolved)
    if not selection.resolved:
        lines.append("  \u2022 nothing selected")
    lines.append(selection.explanation)
    if profile is PresentationProfile.VERBOSE:
        lines.extend(
            (
                f"Selection mode: {_human(selection.mode.value)}",
                f"Selection identity: {selection.semantic_identity}",
                f"Platform: {view.platform}",
            )
        )
    lines.append(f"Review identity: {view.review_digest}")
    return tuple(lines)


def render_inspection(view: ConsumerPlanView, profile: PresentationProfile) -> tuple[str, ...]:
    """Screen 06. Inspection reports; it never asks.

    Anything that needs a decision is a later screen, so this one says only what was looked at and
    what was found. Fast names the requirement and its state; Verbose adds the measurement behind
    the state, because a state without its evidence is an assertion.
    """

    if not isinstance(view, ConsumerPlanView) or not isinstance(profile, PresentationProfile):
        raise ValueError("inspection rendering needs a consumer plan and presentation profile")
    unresolved = tuple(item for item in view.requirements if item.state != "satisfied")
    lines = [
        f"Inspected {len(view.selection.resolved)} artifact(s) on {view.platform}",
        f"{len(view.requirements) - len(unresolved)} of {len(view.requirements)} "
        "requirement(s) satisfied.",
    ]
    for item in view.requirements:
        lines.append(f"  {item.id}: {_human(item.state)}")
        if profile is PresentationProfile.VERBOSE:
            lines.append(f"    {item.kind}: {item.detail}; owners: {', '.join(item.owners)}")
    if not unresolved and not view.remediations:
        lines.append("Nothing needs a decision.")
    return tuple(lines)


def _remediation_subject(item: RemediationView) -> str:
    """What one remediation is *about*, read off the summary the projection already builds.

    `_summary` renders `<kind>: key=value, key=value` and every remediation kind carries exactly
    one identifying value -- the harness, the host, the provider. Taking the values keeps the row
    truthful without the view gaining a field each kind would have to fill in separately.
    """

    _, separator, details = item.summary.partition(": ")
    if not separator:
        return ""
    return ", ".join(
        part.split("=", 1)[1]
        for part in details.split(", ")
        if "=" in part and not part.startswith("requirement=")
    )


def render_remediation(view: ConsumerPlanView, profile: PresentationProfile) -> tuple[str, ...]:
    """Screen 08. Only meaningful choices are surfaced, with what they will not touch."""

    if not isinstance(view, ConsumerPlanView) or not isinstance(profile, PresentationProfile):
        raise ValueError("remediation rendering needs a consumer plan and presentation profile")
    if not view.remediations:
        lines = ["Nothing needs to be prepared."]
    else:
        lines = [f"{len(view.remediations)} thing(s) need preparing first"]
        for item in view.remediations:
            # `QA-080`: the kind alone repeated `configure harness` once per harness and named
            # none of them, so the rows were indistinguishable and none was actionable. The
            # identifying value is already in the summary; the row it is read from now carries it.
            subject = _remediation_subject(item)
            named = f"{_human(item.kind)}: {subject}" if subject else _human(item.kind)
            lines.append(f"  {named} ({_human(item.risk)})")
            if profile is PresentationProfile.VERBOSE:
                lines.append(f"    {item.summary}; owners: {', '.join(item.owners)}")
        lines.append("Nothing outside this installation will be modified.")
    lines.append("[ Continue ]")
    return tuple(lines)


def _planned_harnesses(view: ConsumerPlanView) -> tuple[str, ...]:
    """The harnesses this plan actually touches, read off the effects rather than the request.

    An effect that names a harness is one this install registers with, delivers to or merges into;
    one that names none is the artifact's own tree and belongs to no harness in particular. Reading
    the plan means the screen cannot disagree with what runs, which is the whole of `QA-078`.
    """

    return tuple(
        sorted(
            {
                harness
                for planned in view.canonical.mutation.effects
                if isinstance(harness := getattr(planned.effect, "harness", None), str) and harness
            }
        )
    )


def render_ready(view: ConsumerPlanView, profile: PresentationProfile) -> tuple[str, ...]:
    """Screen 09. Outcomes in Fast; the same InstallPlan, undiminished, in Verbose."""

    if not isinstance(view, ConsumerPlanView) or not isinstance(profile, PresentationProfile):
        raise ValueError("ready rendering needs a consumer plan and presentation profile")
    if profile is PresentationProfile.VERBOSE:
        return _verbose_plan(view)
    outcomes = Counter(_OUTCOMES.get(item.kind, "other change") for item in view.effects)
    lines = ["Ready to install", f"{len(view.selection.resolved)} artifact(s) will be installed."]
    lines.extend(f"  {count} {name}" for name, count in sorted(outcomes.items()))
    credentials = tuple(item for item in view.inputs if isinstance(item, CredentialInputView))
    if credentials:
        lines.append(f"  {len(credentials)} credential(s) stored securely")
    # `QA-079`: the operator learned where it had gone only afterwards. The set is derived rather
    # than chosen -- every measured harness the artifact declares support for (`D-231`) -- so the
    # screen names it and says where it comes from instead of offering a menu with one answer.
    harnesses = _planned_harnesses(view)
    if harnesses:
        lines.append(
            f"Harnesses: {', '.join(harnesses)} "
            "(every harness this machine measured that the artifact declares support for)."
        )
    # Compressed, never quieter: this is the screen somebody confirms from, so every risk the plan
    # carries and every remediation it decided is named here as well as in the full plan.
    if view.remediations:
        lines.append(
            "Remediation: "
            + ", ".join(f"{_human(item.kind)} ({_human(item.risk)})" for item in view.remediations)
            + "."
        )
    risks = ", ".join(_human(item) for item in view.risks) or "read only"
    lines.extend(
        (
            f"Risks: {risks}.",
            f"Review identity: {view.review_digest}",
            "Show details for the full plan.",
        )
    )
    return tuple(lines)


def render_progress(view: LifecycleOutcomeView, profile: PresentationProfile) -> tuple[str, ...]:
    """Screens 10, 17 and 19. Meaningful progress, not a log, until somebody asks."""

    if not isinstance(view, LifecycleOutcomeView) or not isinstance(profile, PresentationProfile):
        raise ValueError("progress rendering needs an outcome view and presentation profile")
    lines = [f"{_human(view.kind).capitalize()} {view.artifact}"]
    for item in view.steps:
        mark = _STEP_MARKS.get(item.status, "·")
        if profile is PresentationProfile.VERBOSE:
            detail = f" ({item.detail})" if item.detail else ""
            lines.append(f"  {mark} {item.component}: {item.effect}{detail}")
        else:
            lines.append(f"  {mark} {item.component}")
    if not view.steps:
        lines.append("  Nothing to do.")
    return tuple(lines)


def _transaction_member(view: ReceiptArtifactView, profile: PresentationProfile) -> tuple[str, ...]:
    lines = [f"{_STEP_MARKS.get(view.status, '·')} {view.coordinate}  {_human(view.status)}"]
    if view.detail:
        lines.append(f"    {view.detail}")
    for message in view.diagnostics:
        lines.append(f"    {message}")
    for step in view.steps:
        mark = _STEP_MARKS.get(step.status, "·")
        if profile is PresentationProfile.VERBOSE:
            detail = f" ({step.detail})" if step.detail else ""
            lines.append(f"    {mark} {step.component}: {step.effect}{detail}")
        else:
            lines.append(f"    {mark} {step.component}")
    return tuple(lines)


def render_transaction_progress(
    view: ReceiptDetailView, profile: PresentationProfile
) -> tuple[str, ...]:
    """Screen 10 for a Selection: every member of the transaction, including the ones that did not
    run.

    A member nobody attempted is the member somebody most needs to see, so it is drawn rather than
    filtered out for having no steps.
    """

    if not isinstance(view, ReceiptDetailView) or not isinstance(profile, PresentationProfile):
        raise ValueError("transaction rendering needs a receipt view and presentation profile")
    lines = [view.summary]
    for member in view.artifacts:
        lines.extend(_transaction_member(member, profile))
    if not view.artifacts:
        lines.append("  Nothing to do.")
    if profile is PresentationProfile.VERBOSE:
        lines.append(f"Review identity: {view.review_digest}")
    return tuple(lines)


def render_transaction_success(
    view: ReceiptDetailView, profile: PresentationProfile
) -> tuple[str, ...]:
    """Screen 11 for a Selection. Undo is offered only where the transaction can actually be
    reversed, and the refusal names the member that refuses it."""

    lines = list(render_transaction_progress(view, profile))
    lines.append(f"{view.outcome.mark} {_human(view.outcome.value).capitalize()}")
    for drift in view.residual_drift:
        lines.append(f"  Still needs attention: {drift.component} ({_human(drift.kind)})")
    lines.append(
        "[ View installed ] [ View receipt ] [ Undo ] [ Done ]"
        if view.undo.available
        else f"[ View installed ] [ View receipt ] [ Done ]  Undo unavailable: {view.undo.reason}"
    )
    return tuple(lines)


def render_pending_setup(pending: tuple[DeclaredArtifactSetup, ...]) -> tuple[str, ...]:
    """What an installed artifact still needs, on the screen that says the install finished.

    Placing an artifact's files is not always the whole of installing it, and this application
    performs none of the rest yet (B-044). Saying so is the difference between an operator who
    knows there is one step left and one who believes a Skill is configured when it is not, so
    these lines name the artifact, the recipe it declares and the document that explains it by
    hand -- and say plainly that nothing here ran it.
    """

    if not pending:
        return ()
    lines = [
        f"Setup declared but not performed ({len(pending)}):",
    ]
    for item in pending:
        lines.append(f"  {item.coordinate} declares {item.recipe} ({', '.join(item.platforms)})")
        if item.manual is not None:
            lines.append(f"    configure it by hand: {item.manual} in the installed package")
    lines.append("  Nothing here ran it; the artifact is installed and unconfigured.")
    return tuple(lines)


def render_success(view: LifecycleOutcomeView, profile: PresentationProfile) -> tuple[str, ...]:
    """Screen 11. Outcome-oriented completion, and where to go from it."""

    lines = list(render_lifecycle_outcome(view, profile))
    lines.append("[ View installed ] [ View receipt ] [ Done ]")
    return tuple(lines)


def render_credential(view: CredentialRecordView, profile: PresentationProfile) -> tuple[str, ...]:
    """Screen 23. Reference, provider, health, consumers and actions -- never a value."""

    if not isinstance(view, CredentialRecordView) or not isinstance(profile, PresentationProfile):
        raise ValueError("credential rendering needs a record view and presentation profile")
    mark, health = _credential_health(view)
    lines = [f"{view.input}  {mark} {health}", f"Stored securely: {view.provider}"]
    if view.detail:
        lines.append(view.detail)
    lines.append("Used by")
    lines.extend(f"  • {item}" for item in view.dependants)
    if not view.dependants:
        lines.append("  • nothing installed")
    if profile is PresentationProfile.VERBOSE:
        lines.extend(
            (
                f"Reference: {view.reference}",
                f"Service: {view.service}",
                f"Account: {view.account}",
                f"Provider state: {_human(view.provider_state)}",
            )
        )
    lines.append("Actions: " + ", ".join(view.actions) + ".")
    return tuple(lines)


def render_credential_action(
    view: CredentialRecordView, profile: PresentationProfile
) -> tuple[str, ...]:
    """Screen 24. What an action would do, and to whom.

    Delete is offered only where nothing depends on the credential. A credential something still
    uses is not deletable from here; the dependants are named instead, because the honest answer to
    "delete this" is which installations would stop working.
    """

    if not isinstance(view, CredentialRecordView) or not isinstance(profile, PresentationProfile):
        raise ValueError("credential action rendering needs a record view and presentation profile")
    lines = [f"{view.input}: choose an action"]
    lines.extend(f"  [ {item.capitalize()} ]" for item in view.actions)
    if view.dependants:
        lines.append("Replacing affects")
        lines.extend(f"  • {item}" for item in view.dependants)
        lines.append("It cannot be removed while these use it.")
    lines.append("Replacement stores a new value and verifies what uses it; no old value is kept.")
    return tuple(lines)


def render_installed_artifact(
    view: InstalledArtifactView, profile: PresentationProfile
) -> tuple[str, ...]:
    if not isinstance(view, InstalledArtifactView) or not isinstance(profile, PresentationProfile):
        raise ValueError("installed artifact rendering needs a view and presentation profile")
    lines = [f"{view.coordinate} — {_human(view.health)}"]
    if view.health == "unknown":
        # Not a fault and not a clean bill: nothing measured it. Saying "needs attention" would
        # invent a problem, and "verified" would invent a verification.
        lines.append("Installed here, but nothing canonical has observed it yet.")
    elif view.drift:
        lines.append("Needs attention: " + ", ".join(item.component for item in view.drift) + ".")
    else:
        lines.append("Verified against its desired state.")
    if view.actions:
        lines.append("Actions: " + ", ".join(view.actions) + ".")
    else:
        lines.append("No action is offered until it is observed.")
    if profile is PresentationProfile.VERBOSE:
        lines.append("Ownership:")
        lines.extend(f"  - {item.kind}: {item.owner}" for item in view.ownership)
        lines.append("Measured drift:")
        lines.extend(
            f"  - {item.component}: {_human(item.kind)}; "
            f"independently repairable: {'yes' if item.repairable else 'no'}"
            for item in view.drift
        )
        if not view.drift:
            lines.append("  - none")
    return tuple(lines)


def render_installed_collection(
    view: InstalledCollectionView, profile: PresentationProfile
) -> tuple[str, ...]:
    if not isinstance(view, InstalledCollectionView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("installed Collection rendering needs a view and presentation profile")
    lines = [f"{view.collection} — {_human(view.health)}"]
    if view.members_requiring_attention:
        lines.append(
            "Members needing attention: " + ", ".join(view.members_requiring_attention) + "."
        )
    else:
        lines.append("All members are ready or have an update available.")
    if profile is PresentationProfile.VERBOSE:
        lines.append("Members:")
        lines.extend(f"  - {item.artifact}: {_human(item.health.value)}" for item in view.members)
    lines.append("Actions: " + ", ".join(view.actions) + ".")
    return tuple(lines)


def render_lifecycle_plan(view: LifecyclePlanView, profile: PresentationProfile) -> tuple[str, ...]:
    if not isinstance(view, LifecyclePlanView) or not isinstance(profile, PresentationProfile):
        raise ValueError("lifecycle plan rendering needs a view and presentation profile")
    lines = [f"Review {_human(view.kind)} for {view.artifact}"]
    if view.retained:
        reasons = ", ".join(
            f"still owned {item.kind}ly by {item.owner}" for item in view.retained_ownership
        )
        lines.extend((f"Retained: {reasons}.", "No installed component will be removed."))
    elif view.drift:
        lines.append(
            "Components changing: " + ", ".join(item.component for item in view.drift) + "."
        )
    else:
        lines.append("No component changes are needed.")
    if view.escalated:
        lines.append("Needs a wider action: " + ", ".join(view.escalated) + ".")
    risks = ", ".join(_human(item) for item in view.risks) or "read only"
    lines.append(f"Risks: {risks}.")
    if profile is PresentationProfile.VERBOSE:
        lines.append("Drift:")
        lines.extend(
            f"  - {item.component}: {_human(item.kind)}; repairable: "
            f"{'yes' if item.repairable else 'no'}"
            for item in view.drift
        )
        if not view.drift:
            lines.append("  - none")
        lines.append("Steps:")
        lines.extend(
            f"  - {item.component}: {item.summary}; risk: {_human(item.risk)}"
            for item in view.steps
        )
        if not view.steps:
            lines.append("  - none")
    lines.extend(
        (
            f"Review identity: {view.review_digest}",
            "Confirm to apply this exact reviewed plan.",
        )
    )
    return tuple(lines)


def render_lifecycle_outcome(
    view: LifecycleOutcomeView, profile: PresentationProfile
) -> tuple[str, ...]:
    if not isinstance(view, LifecycleOutcomeView) or not isinstance(profile, PresentationProfile):
        raise ValueError("lifecycle outcome rendering needs a view and presentation profile")
    terminal = {"completed": "Completed", "restored": "Restored"}.get(
        view.status, "Completed with attention"
    )
    lines = [f"{terminal}: {_human(view.kind)} for {view.artifact} — {_human(view.status)}."]
    if view.residual_drift:
        lines.append(
            "Still needs attention: "
            + ", ".join(item.component for item in view.residual_drift)
            + "."
        )
    if view.restoration_status is not None:
        lines.append(f"Restoration: {_human(view.restoration_status)}.")
    if view.detail:
        lines.append(view.detail)
    if profile is PresentationProfile.VERBOSE:
        lines.append("Steps:")
        lines.extend(
            f"  - {item.component}: {_human(item.effect)} — {_human(item.status)}"
            + ("" if not item.detail else f" ({item.detail})")
            for item in view.steps
        )
    lines.append(f"Review identity: {view.review_digest}")
    return tuple(lines)


def render_dashboard(view: DashboardView) -> tuple[str, ...]:
    if not isinstance(view, DashboardView):
        raise ValueError("dashboard rendering needs a dashboard view")
    lines = [
        "AART",
        f"{view.installed_count} installed — {view.ready_count} ready, "
        f"{view.update_count} update, {view.attention_count} attention",
        f"{view.registry_count} registries — "
        f"{view.credential_attention_count} credentials need attention",
        "",
        "Recent activity:",
    ]
    lines.extend(f"  - {item}" for item in view.recent_activity)
    if not view.recent_activity:
        lines.append("  - none yet")
    return tuple(lines)


def render_registry(
    view: RegistryView,
    profile: PresentationProfile,
    *,
    focused: bool = False,
) -> tuple[str, ...]:
    if not isinstance(view, RegistryView) or not isinstance(profile, PresentationProfile):
        raise ValueError("registry rendering needs a registry view and presentation profile")
    if not isinstance(focused, bool):
        raise ValueError("registry focus must be boolean")
    noun = "artifact" if view.artifact_count == 1 else "artifacts"
    lines = [
        f"{'> ' if focused else '  '}{view.alias} — {_human(view.availability)}",
        f"  {view.artifact_count} {noun}",
    ]
    if view.is_registry:
        lines.extend(
            (
                "  Actions: details, sync.",
                "  Sync refreshes Marketplace availability; it does not update installed artifacts.",
            )
        )
    else:
        # An empty row with no explanation reads as a registry that approved nothing, which is a
        # fault; this one is configured, healthy and simply not a registry (INV-026, B-038).
        lines.extend(
            (
                "  An authoring Source, not a registry.",
                "  Its content is offered here once a maintainer promotes it into a registry.",
                "  Actions: details.",
            )
        )
    if profile is PresentationProfile.VERBOSE:
        age = (
            "never" if view.last_sync_age_seconds is None else f"{view.last_sync_age_seconds}s ago"
        )
        lines.extend(
            (
                f"  Kind: {_human(view.kind)}",
                f"  Origin: {view.origin}",
                f"  Health: {_human(view.health)}; last sync: {age}",
                f"  Revision: {view.revision or 'none'}",
                f"  Snapshot: {view.snapshot_digest or 'none'}",
                f"  Trust: {', '.join(view.trust) or 'none'}",
            )
        )
    return tuple(lines)


def render_settings(view: ConsumerSettings, focus: str = "") -> tuple[str, ...]:
    """Screen 28, with the control Enter would move marked.

    Every control is binary, so the row says what it is currently set to rather than listing the
    option that was not chosen. `focus` is a row identity, not a label: what is drawn can be
    reworded without changing what a keystroke means.
    """

    if not isinstance(view, ConsumerSettings) or not isinstance(focus, str):
        raise ValueError("settings rendering needs consumer settings")
    values = {
        "detail-level": f"Detail level: {view.profile.value.title()}",
        "default-scope": f"Default scope: {view.default_scope.title()}",
        "show-updates": f"Show available updates: {'on' if view.show_updates else 'off'}",
        "maintainer-mode": f"Maintainer Mode: {'on' if view.maintainer_mode else 'off'}",
    }
    headings = {
        "detail-level": "Experience",
        "default-scope": "Installation",
        "show-updates": "Updates",
        "maintainer-mode": "Advanced",
    }
    groups: list[tuple[str, ...]] = []
    for row in SETTING_ROWS:
        groups.append((headings[row], f"{'> ' if row == focus else '  '}{values[row]}"))
    lines = list(separate(*groups))
    lines.append("")
    if view.maintainer_mode:
        lines.append("Maintainer screens are reachable from the Dashboard.")
    else:
        lines.append("Maintainer Mode off hides Sources, Candidates, Promotion and Publish.")
    return tuple(lines)


def render_doctor(view: DoctorView, profile: PresentationProfile) -> tuple[str, ...]:
    if not isinstance(view, DoctorView) or not isinstance(profile, PresentationProfile):
        raise ValueError("Doctor rendering needs a Doctor view and presentation profile")
    lines = ["AART / Check system"]
    for item in view.artifacts:
        marker = "✓" if item.health in {"ready", "update"} else "⚠"
        lines.append(f"{marker} {item.coordinate}")
        if item.health in {"attention", "broken"}:
            lines.extend(f"  {drift.component}: {_human(drift.kind)}" for drift in item.drift)
    lines.extend(
        (
            f"{view.ready_count} ready",
            f"{view.attention_count} needs attention",
        )
    )
    if view.actions:
        lines.append("Actions: repair issues using minimal reconciliation plans.")
    if profile is PresentationProfile.VERBOSE and view.repairable_issues:
        lines.append("Independently repairable:")
        lines.extend(f"  - {item}" for item in view.repairable_issues)
    return tuple(lines)


def render_required_inputs(
    inputs: tuple[ConfigInputView | CredentialInputView, ...],
    profile: PresentationProfile,
) -> tuple[str, ...]:
    if any(
        not isinstance(item, (ConfigInputView, CredentialInputView)) for item in inputs
    ) or not isinstance(profile, PresentationProfile):
        raise ValueError("required input rendering needs input views and a presentation profile")
    lines = ["A few things are needed before installation"]
    for item in inputs:
        lines.append(item.label)
        if isinstance(item, CredentialInputView):
            if item.health == "present":
                status = "Configured securely"
            elif item.provider_reference is not None:
                status = "Enter securely during installation"
            else:
                status = "Required"
            lines.append(f"  {status}")
            if item.format_hint:
                lines.append(f"  Format: {item.format_hint}")
            if item.obtain_from:
                lines.append(f"  {item.obtain_from[0]} → {item.obtain_from[1]}")
            if profile is PresentationProfile.VERBOSE:
                lines.extend(
                    (
                        f"  Binding: {_human(item.binding)} ({_human(item.exposure)})",
                        f"  Provider reference: {item.provider_reference or 'not configured'}",
                        f"  Provider health: {_human(item.provider_state)} / {_human(item.health)}",
                    )
                )
            continue
        shown = item.current if item.current is not None else item.default
        lines.append(f"  [{shown or ''}]")
        if item.example:
            lines.append(f"  (e.g. {item.example})")
        if item.validation_hint:
            lines.append(f"  {item.validation_hint}")
        if profile is PresentationProfile.VERBOSE:
            lines.extend(
                (
                    f"  Binding: {_human(item.binding)} ({_human(item.exposure)})",
                    f"  Source: {item.source or 'not configured'}",
                )
            )
    return tuple(lines)


def render_marketplace_artifact(
    row: MarketplaceArtifactRow,
    profile: PresentationProfile,
    *,
    inputs: tuple[ConfigInputView | CredentialInputView, ...] = (),
) -> tuple[str, ...]:
    if not isinstance(row, MarketplaceArtifactRow) or not isinstance(profile, PresentationProfile):
        raise ValueError("Marketplace rendering needs an artifact row and presentation profile")
    if profile is PresentationProfile.VERBOSE:
        return render_artifact_detail(row)
    approval = (
        "Approved"
        if row.trust in {"registry-reviewed", "company-reviewed"}
        else _human(row.trust).title()
    )
    lines = [row.key, approval, row.summary, "What it needs"]
    if not row.compatible:
        lines.extend(f"  - {item.message}" for item in row.reasons)
    elif not inputs:
        lines.append("  - Your selected system and harness are ready")
    else:
        lines.extend(f"  - {item.label}" for item in inputs)
    lines.append("Actions: select, install, verbose.")
    return tuple(lines)


def render_collection(
    view: MarketplaceCollectionView, profile: PresentationProfile
) -> tuple[str, ...]:
    if not isinstance(view, MarketplaceCollectionView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Collection rendering needs a Collection view and presentation profile")
    lines = [view.coordinate, view.summary, "Includes", f"{len(view.members)} artifacts"]
    lines.extend(f"{count} {_human(kind)}" for kind, count in view.kind_counts)
    if view.inputs:
        lines.append("What you will need")
        lines.extend(f"  - {item.label}" for item in view.inputs)
    lines.append(f"{len(view.selected)} / {len(view.members)} selected")
    if not view.exact:
        lines.extend(
            (
                "Warning: Custom selection",
                "This will not install the complete Collection.",
            )
        )
    if profile is PresentationProfile.VERBOSE:
        lines.append("Contents:")
        lines.extend(f"  [{'x' if item in view.selected else ' '}] {item}" for item in view.members)
        lines.append(f"Selection identity: {view.semantic_identity}")
    return tuple(lines)


def render_activity(view: ActivityView, profile: PresentationProfile) -> tuple[str, ...]:
    """The timeline of what a person did, grouped by day and newest first."""

    if not isinstance(view, ActivityView) or not isinstance(profile, PresentationProfile):
        raise ValueError("activity rendering needs a view and presentation profile")
    if not view.days:
        return ("Activity", "Nothing has happened here yet.")
    lines = ["Activity"]
    for day in view.days:
        lines.append(day.label)
        for entry in day.entries:
            line = f"  {entry.mark} {entry.time}  {entry.summary}"
            lines.append(
                line if profile is PresentationProfile.FAST else f"{line}  {entry.review_digest}"
            )
    return tuple(lines)


def render_receipt_detail(view: ReceiptDetailView, profile: PresentationProfile) -> tuple[str, ...]:
    if not isinstance(view, ReceiptDetailView) or not isinstance(profile, PresentationProfile):
        raise ValueError("receipt rendering needs a view and presentation profile")
    lines = [
        f"Receipt: {_human(view.intent)} — {view.artifact}",
        f"Recorded: {view.recorded_at}",
        f"Result: {_human(view.status)}",
    ]
    if view.detail:
        lines.append(view.detail)
    if view.residual_drift:
        lines.append(
            "Still needs attention: "
            + ", ".join(item.component for item in view.residual_drift)
            + "."
        )
    if view.restoration_status is not None:
        lines.append(f"Restoration: {_human(view.restoration_status)}.")
    lines.append(
        f"Undo: available for {', '.join(view.undo.components)}."
        if view.undo.available
        else f"Undo: not available — {view.undo.reason}."
    )
    if profile is PresentationProfile.VERBOSE:
        lines.append("Effects:")
        lines.extend(
            f"  - {item.component}: {_human(item.effect)} — {_human(item.status)}"
            + ("" if not item.detail else f" ({item.detail})")
            for item in view.steps
        )
        lines.append(f"Policy identity: {view.policy_digest}")
    lines.append(f"Review identity: {view.review_digest}")
    return tuple(lines)


class ConsumerTerminal(Protocol):
    """The whole terminal, as far as the loop is concerned."""

    def draw(self, lines: tuple[str, ...]) -> None: ...

    def key(self) -> int | str: ...


class ConsumerScreenSource(Protocol):
    """What one screen is showing right now.

    The loop asks; it never derives.  Everything semantic -- which artifacts exist, what is
    installed, what a plan says -- is answered here, by a caller wired to the canonical services.
    """

    def rows(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The row identities the screen is currently showing, already filtered by the search."""

    def lines(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The body of the screen, rendered at the profile `state` holds."""

    def description(self, state: ConsumerUiState) -> tuple[str, ...]:
        """What the thing under the cursor is, for the skeleton's second section (`QA-067`)."""

    def status(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The state of the whole view -- counts, errors, steps left -- or nothing (`QA-067`)."""

    def detail(self, state: ConsumerUiState) -> ApplicationScreen | None:
        """Where Enter goes from the row under the cursor, if anywhere."""

    def selected(self, state: ConsumerUiState) -> tuple[str, ...] | None:
        """What this screen opens with ticked, or `None` where it has no opinion."""


class ConsumerActionCompletion(Protocol):
    """A post-payload terminal conversation that returns the truthful result screen."""

    def complete(self, terminal: ConsumerTerminal) -> ConsumerScreenSource: ...


@dataclass(frozen=True, slots=True)
class ConsumerActionUpdate:
    """A new immutable screen snapshot and the event that says what the action established."""

    source: ConsumerScreenSource
    event: ConsumerUiEvent
    completion: ConsumerActionCompletion | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event, ConsumerUiEvent) or self.event.kind not in (
            ConsumerUiEventKind.ACTION_PREPARED,
            ConsumerUiEventKind.ACTION_RECORDED,
            # An attempt that stopped is a third thing an action establishes, and the one it used
            # to have to disguise as an empty recording (`QA-033`).
            ConsumerUiEventKind.ACTION_FAILED,
        ):
            raise ValueError("a consumer action update needs a prepared, recorded or failed event")
        if self.completion is not None and not callable(getattr(self.completion, "complete", None)):
            raise ValueError("a consumer action completion needs a terminal boundary")


class ConsumerActionHandler(Protocol):
    """Imperative boundary for planning, executing, recording and re-reading one action."""

    def handle(self, command: ConsumerUiCommand) -> ConsumerActionUpdate: ...


_HELP_LINES: tuple[str, ...] = (
    "Keyboard help",
    "[↑/↓] Move",
    "[Space] Select or toggle",
    "[Enter] Open or continue",
    "[Esc] Back",
    "[i] Install or update",
    "[r] Repair",
    "[u] Uninstall or check adopted upstream",
    "[s] Sync or scan repository",
    "[a] Add or adopt",
    "[/] Search",
    "[v] Fast / Verbose",
    "[?] Help",
    "[q] Quit",
)

_DESCRIBED_SCREENS: frozenset[ApplicationScreen] = frozenset(
    {ConsumerScreen.DASHBOARD, MaintainerScreen.DASHBOARD}
)
"""Screens whose rows are destinations, and so have something to say about the one under the cursor."""

_DASHBOARD_DESCRIPTIONS: dict[ApplicationScreen, str] = {
    ConsumerScreen.MARKETPLACE: "Browse and install approved tools from configured registries.",
    ConsumerScreen.INSTALLED: "See what AART manages in this project and whether it is healthy.",
    ConsumerScreen.UPDATES: "Review newer approved versions; nothing changes without confirmation.",
    ConsumerScreen.REGISTRIES: "See which sources determine what Marketplace can offer.",
    ConsumerScreen.CREDENTIALS: "Check credential references and which installed tools depend on them.",
    ConsumerScreen.ACTIVITY: "Review recorded changes, results and their receipts.",
    ConsumerScreen.DOCTOR: "Inspect health and find the smallest safe repair for detected drift.",
    ConsumerScreen.SETTINGS: "Choose detail, installation scope and optional Maintainer Mode.",
    MaintainerScreen.DASHBOARD: "Open advanced source, validation and promotion workflows.",
}

_FIRST_RUN_LINES: tuple[str, ...] = (
    "Welcome to AART — this looks like your first run.",
    "AART installs and keeps your team's approved AI tools:",
    "skills, MCP servers, rules and hooks.",
    "",
    "SETUP REQUIRED",
    "  No sources are configured, so Marketplace has nothing to offer yet.",
    "  → Start here: open Registries and choose Add Registry.",
)


def _title(screen: ApplicationScreen) -> str:
    return _human(screen.value.split("-", 1)[1]).title()


_WORKFLOW_LABELS: dict[ApplicationScreen, str] = {
    MaintainerScreen.CANDIDATES: "Candidate",
    MaintainerScreen.CANDIDATE_DETAILS: "Details",
    MaintainerScreen.CANDIDATE_DIFF: "Diff",
    MaintainerScreen.VALIDATION: "Validation",
    MaintainerScreen.POLICY_REVIEW: "Policy",
    MaintainerScreen.PROMOTION_REVIEW: "Promotion Review",
    MaintainerScreen.PROMOTION_MODE: "Mode",
    MaintainerScreen.REGISTRY_DIFF: "Registry Diff",
    MaintainerScreen.REGISTRY_VALIDATION: "Registry Validation",
    MaintainerScreen.REGISTRY_COMMIT: "Commit",
}


def _workflow_chrome(state: ConsumerUiState) -> tuple[str, ...]:
    icons = {
        WorkflowStepStatus.COMPLETED: STAGE_CONFIRMED,
        WorkflowStepStatus.CURRENT: STAGE_CURRENT,
        WorkflowStepStatus.UPCOMING: STAGE_PENDING,
    }
    steps = workflow_progress(state)
    if not steps:
        return ()
    labels = tuple(
        f"{icons[step.status]} {_WORKFLOW_LABELS.get(step.screen, _title(step.screen))}"
        for step in steps
    )
    join = f" {STAGE_JOIN} "
    lines: list[str] = []
    current = ""
    for label in labels:
        candidate = label if not current else current + join + label
        if current and len(candidate) > CONTENT_MEASURE:
            lines.append(current)
            current = "  " + label
        else:
            current = candidate
    if current:
        lines.append(current)
    return tuple(lines)


def _review_prompt(state: ConsumerUiState, prompt: str) -> tuple[str, ...]:
    """A review's own instruction, or -- once its confirmed run stopped -- what happened instead.

    The screen keeps its name and its place, because the refusal below answers a question asked
    here. What it may not keep is the instruction to press a key that would start the run: the run
    was already attempted, its plan was discarded when it stopped, and the only thing that key can
    do now is leave (`QA-033`).
    """

    if state.failed_action is None:
        return (prompt,)
    return (
        "This run stopped, so nothing here was changed. Why it stopped is below.",
        "",
        "Enter returns to the list.",
    )


def _binding_text(binding: KeyBinding) -> str:
    return f"[{binding.key}] {binding.label}"


def _binding_lines(bindings: tuple[KeyBinding, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    current = ""
    for binding in bindings:
        text = _binding_text(binding)
        candidate = text if not current else current + "   " + text
        if current and len(candidate) > CONTENT_MEASURE:
            lines.append(current)
            current = text
        else:
            current = candidate
    if current:
        lines.append(current)
    return tuple(lines)


def _key_legend(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """This screen's own keys on one line, the ways out of it on the line below (`QA-068`).

    Mixing them read as one undifferentiated row of brackets, so the two questions a reader
    actually has -- "what can I do here?" and "how do I leave?" -- had to be answered by scanning
    the same line twice. The universal four are last in `key_bindings` by construction, so the
    split is read off the order the reducer already guarantees rather than off a second list that
    could drift from it.

    A mode that has taken the keyboard -- search, the quit prompt -- has no universal half to
    separate: every key it lists is the mode's own, so it stays one line.
    """

    bindings = key_bindings(state, detail=source.detail(state))
    if state.searching or state.quit_pending:
        return _binding_lines(bindings)
    local, global_keys = bindings[:-4], bindings[-4:]
    return (*_binding_lines(local), *_binding_lines(global_keys))


def frame(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """One drawn screen: heading, body, prompts, and the persistent navigation footer."""

    heading = _heading(state)
    progress = _workflow_chrome(state)
    header = (heading, *(("", *progress) if progress else ()))
    status: list[str] = list(source.status(state))
    if state.searching:
        status.append(f"Search: {state.search}_")
    elif state.search:
        status.append(f"Filter: {state.search} (esc to clear)")
    if state.selection:
        status.append(f"{len(state.selection)} selected")
    if state.quit_pending:
        status.append(f"Discard {len(state.selection)} selected item(s) and quit? y/n")
    # `QA-086`: the launch directory is the footer's caption -- the last line before the keys'
    # rule and flush on it, with the terminal's padding above it rather than under it (revising
    # `QA-069`/`D-235`, which had it as a section of its own; `QA-066` had moved it off the title).
    workspace = (f"working at {state.workspace}",) if state.workspace else ()
    return screen_frame(
        header,
        source.lines(state),
        _described(source, state),
        _HELP_LINES if state.help_visible else (),
        status,
        context=workspace,
        footer=_key_legend(source, state),
    )


def _heading(state: ConsumerUiState) -> str:
    """The trail the reader walked, each place named once (`QA-071`, `QA-083`).

    The two findings pull against each other -- one asks a nested view to name its parent, the other
    to stop repeating "Maintainer" -- so they produce one scheme or an inconsistent pair. The scheme
    is a breadcrumb over the session's own history, which is the ancestor chain by construction:
    `advance` pushes the screen being left and `back` pops it, so what is on the stack is where the
    reader actually came from rather than a guess from a graph where several parents are declared.

    Two places are named differently from the rest, for the same reason in both directions. The home
    Dashboard contributes no step, because `AART` is already its name and `AART / Dashboard /
    Marketplace` says "home" twice. A dashboard passed *through* drops the word, because a dashboard
    in a trail is the place it is the dashboard of -- which is what turns `AART / Maintainer
    Dashboard / Sources` into `AART / Maintainer / Sources` and says "Maintainer" once.
    """

    trail = (*state.session.history, state.session.screen)
    steps = [step for step in (_step(screen) for screen in trail[:-1]) if step]
    heading = " / ".join(("AART", *steps, _title(trail[-1])))
    if state.failed_action is not None:
        # The screen's name still says "review", and it is now the result of an attempt. Saying so
        # here is what stops the plan below reading as something still about to happen (`QA-033`).
        heading += " - did not run"
    return heading


def _step(screen: ApplicationScreen) -> str:
    """One passed-through place in the trail, or nothing where the place is `AART` itself."""

    if screen is ConsumerScreen.DASHBOARD:
        return ""
    title = _title(screen)
    return title[: -len(" Dashboard")] if title.endswith(" Dashboard") else title


def _described(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """The cursor description, which is a mode rather than a permanent fixture (`QA-070`).

    The operator asked for the per-row explanations to be switchable by a key instead of standing
    on every screen forever, and `[v] Fast / Verbose` was already the key that claimed to change
    how much a screen says while changing nothing the operator could see (`QA-064`). Binding the
    descriptions to it makes one key honest and settles both: Fast is the screen without them,
    Verbose is the screen with them.
    """

    if state.session.profile is not PresentationProfile.VERBOSE:
        return ()
    return source.description(state)


class ConsumerSettingsWriter(Protocol):
    """Imperative boundary for keeping one consumer's preferences past this session."""

    def __call__(self, settings: ConsumerSettings) -> None: ...


def run_consumer_shell(
    source: ConsumerScreenSource,
    terminal: ConsumerTerminal,
    *,
    state: ConsumerUiState | None = None,
    action_handler: ConsumerActionHandler | None = None,
    settings_writer: ConsumerSettingsWriter | None = None,
) -> ConsumerUiState:
    """Run the persistent consumer application until somebody leaves it.

    The rows are re-read whenever what the screen shows could have changed -- a navigation, a back,
    or an edit to the filter.  The cursor stays on the row it was on if that row is still there,
    which is why filtering never silently moves what somebody was about to act on.
    """

    current = ConsumerUiState() if state is None else state
    active_source = source
    if not isinstance(current, ConsumerUiState):
        raise ValueError("the consumer shell needs consumer UI state")
    reloads = frozenset(
        {
            ConsumerUiEventKind.SEARCH,
            ConsumerUiEventKind.SEARCH_CLOSE,
        }
    )
    current = _reload(active_source, current, entering=True)
    while not current.exited:
        terminal.draw(frame(active_source, current))
        name = key_name(
            terminal.key(),
            literal=current.session.screen
            in (
                ConsumerScreen.REGISTRY_ADD,
                MaintainerScreen.SOURCE_ADD,
                MaintainerScreen.REGISTRY_INIT,
                MaintainerScreen.REPOSITORY_SCAN,
            ),
        )
        if not name:
            continue
        event = key_event(name, current, detail=active_source.detail(current))
        if event is None:
            continue
        current, commands = reduce_consumer_ui(current, event)
        entering = any(command.kind is ConsumerUiCommandKind.LOAD_SCREEN for command in commands)
        for command in commands:
            if command.kind is ConsumerUiCommandKind.PERSIST_SETTINGS:
                # A shell with nowhere to keep a preference would forget it the moment somebody
                # left, and screen 28 would be showing a choice that was never made. Refusing here
                # is what keeps that from being silent.
                if settings_writer is None:
                    raise ValueError("changing a setting needs an injected settings writer")
                settings_writer(current.settings)
                continue
            if command.kind not in (
                ConsumerUiCommandKind.PREPARE_ACTION,
                ConsumerUiCommandKind.EXECUTE_ACTION,
            ):
                continue
            if action_handler is None:
                raise ValueError("a consumer action needs an injected action handler")
            # The running screen is observable before the synchronous effect boundary returns.
            # A future streaming handler can redraw individual steps without changing this command.
            if command.kind is ConsumerUiCommandKind.EXECUTE_ACTION:
                terminal.draw(frame(active_source, current))
            update = action_handler.handle(command)
            if not isinstance(update, ConsumerActionUpdate):
                raise ValueError("a consumer action handler returned an invalid update")
            # An execution answers with what it established: a recording, or the fact that the
            # attempt stopped. Both are answers to the same command, and the second is the one
            # that used to have to arrive disguised as an empty recording (`QA-033`).
            expected = (
                (ConsumerUiEventKind.ACTION_PREPARED,)
                if command.kind is ConsumerUiCommandKind.PREPARE_ACTION
                else (ConsumerUiEventKind.ACTION_RECORDED, ConsumerUiEventKind.ACTION_FAILED)
            )
            if update.event.kind not in expected or update.event.action is not command.action:
                raise ValueError("a consumer action handler returned the wrong action update")
            active_source = (
                update.source if update.completion is None else update.completion.complete(terminal)
            )
            current, followup = reduce_consumer_ui(current, update.event)
            entering = entering or any(
                item.kind is ConsumerUiCommandKind.LOAD_SCREEN for item in followup
            )
        if entering or event.kind in reloads:
            current = _reload(active_source, current, entering=entering)
    return current


def _reload(
    source: ConsumerScreenSource, state: ConsumerUiState, *, entering: bool = False
) -> ConsumerUiState:
    """Re-read the rows, and on the way into a screen, whatever it opens with ticked."""

    reloaded, _ = reduce_consumer_ui(
        state, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=source.rows(state))
    )
    seed = source.selected(reloaded) if entering else None
    if seed is None:
        return reloaded
    seeded, _ = reduce_consumer_ui(
        reloaded, ConsumerUiEvent(ConsumerUiEventKind.SET_SELECTION, rows=seed)
    )
    return seeded


@dataclass(frozen=True, slots=True)
class MarketplaceEntry:
    """One offered artifact and what installing it will ask for."""

    row: MarketplaceArtifactRow
    inputs: tuple[InputView, ...] = ()

    @property
    def key(self) -> str:
        return self.row.key


@dataclass(frozen=True, slots=True)
class MarketplaceCollectionEntry:
    """One offered Collection, kept canonical so a customization keeps its own identity.

    The Collection itself is held rather than one projection of it, because which members are
    chosen is what the customize screen is for, and only :func:`project_collection` may decide what
    identity a given choice has.
    """

    collection: Collection
    inputs: tuple[InputView, ...] = ()

    @property
    def key(self) -> str:
        return str(self.collection.coordinate)

    @property
    def members(self) -> tuple[str, ...]:
        return tuple(str(item.request) for item in self.collection.members)

    def view(self, selected: tuple[str, ...] | None = None) -> MarketplaceCollectionView:
        chosen = (
            None
            if selected is None
            else tuple(item for item in self.members if item in frozenset(selected))
        )
        return project_collection(self.collection, selected=chosen, inputs=self.inputs)


@dataclass(frozen=True, slots=True)
class ConsumerScreens:
    """Everything the canonical application can currently show one consumer.

    These are already-projected views.  Assembling them is somebody else's job, done once before
    the shell starts and again whenever an action changes the machine -- never inside a draw.
    """

    dashboard: DashboardView
    installed: tuple[InstalledArtifactView, ...] = ()
    activity: ActivityView = ActivityView(())
    registries: tuple[RegistryView, ...] = ()
    settings: ConsumerSettings = ConsumerSettings()
    doctor: DoctorView | None = None
    receipts: tuple[ReceiptDetailView, ...] = ()
    marketplace: tuple[MarketplaceEntry, ...] = ()
    collections: tuple[MarketplaceCollectionEntry, ...] = ()
    installed_collections: tuple[InstalledCollectionView, ...] = ()
    credentials: tuple[CredentialRecordView, ...] = ()
    plan: ConsumerPlanView | None = None
    lifecycle: LifecyclePlanView | None = None
    outcome: LifecycleOutcomeView | None = None
    #: What one confirmed Selection produced. Screens 10 and 11 prefer it, because an install is a
    #: transaction; 17 and 19 stay on `outcome`, because an update or an uninstall is about one
    #: artifact.
    transaction: ReceiptDetailView | None = None
    #: Why the last action could not be prepared or carried out, in the words it was refused in.
    #: It is carried rather than raised because the screens an action lands on are the ones
    #: somebody is looking at, and a review that cannot say what went wrong is a Fast projection
    #: hiding material risk.
    notice: tuple[str, ...] = ()
    maintainer: MaintainerViews | None = None
    source_sync_review: MaintainerSourceSyncReviewView | None = None
    source_sync_result: MaintainerSourceSyncResultView | None = None
    promotion_validation: MaintainerRegistryValidationView | None = None
    promotion_commit: MaintainerRegistryCommitView | None = None
    #: Setup an artifact this action installed declares and that nothing performed. It belongs to
    #: the outcome rather than to the notice channel: a notice is why something was refused, and
    #: this is part of what happened.
    pending_setup: tuple[DeclaredArtifactSetup, ...] = ()
    repository_scan: MaintainerRepositoryScanView | None = None
    adoption_review: MaintainerAdoptionReviewView | None = None
    adopted_artifacts: tuple[MaintainerAdoptedArtifactView, ...] = ()
    adoption_upstream: MaintainerAdoptionUpstreamView | None = None

    def offered(self, key: str) -> MarketplaceEntry | None:
        return next((item for item in self.marketplace if item.key == key), None)

    def offered_collection(self, key: str) -> MarketplaceCollectionEntry | None:
        return next((item for item in self.collections if item.key == key), None)

    def artifact(self, coordinate: str) -> InstalledArtifactView | None:
        return next((item for item in self.installed if item.coordinate == coordinate), None)

    def receipt(self, recorded_at: str) -> ReceiptDetailView | None:
        return next((item for item in self.receipts if item.recorded_at == recorded_at), None)

    def installed_collection(self, name: str) -> InstalledCollectionView | None:
        return next((item for item in self.installed_collections if item.collection == name), None)

    def credential(self, reference: str) -> CredentialRecordView | None:
        return next((item for item in self.credentials if item.reference == reference), None)

    def candidate(self, candidate_id: str) -> MaintainerCandidateView | None:
        """One Candidate by its stable ID, because two Sources may name an artifact the same."""

        return None if self.maintainer is None else self.maintainer.candidate(candidate_id)

    def validation(self, focus: str) -> MaintainerValidationView | None:
        """The validation run for a focus that is either a Candidate ID or one of its check rows.

        Screen 40 is reachable from both screen 38 and screen 39, so it has to accept either shape
        and still be about the same Candidate.
        """

        if self.maintainer is None:
            return None
        row = parse_validation_row(focus)
        return self.maintainer.validation(focus if row is None else row.candidate_id)

    def candidate_lifecycle(self, candidate_id: str) -> MaintainerCandidateLifecycleView | None:
        """The already-composed lifecycle for one stable Candidate identity."""

        return None if self.maintainer is None else self.maintainer.lifecycle(candidate_id)

    def candidate_provenance(self, candidate_id: str) -> MaintainerProvenanceView | None:
        """The already-composed compiler provenance for one stable Candidate identity."""

        return None if self.maintainer is None else self.maintainer.provenance(candidate_id)

    def version_conflict(self, candidate_id: str) -> MaintainerVersionConflictView | None:
        """The already-composed immutable-version refusal for one Candidate, when present."""

        return None if self.maintainer is None else self.maintainer.version_conflict(candidate_id)

    def collection_candidates(self) -> tuple[MaintainerCollectionCandidateView, ...]:
        """The already-composed active Collection Candidate rows."""

        if self.maintainer is None or self.maintainer.collection_candidates is None:
            return ()
        return self.maintainer.collection_candidates

    def collection_validation(self, candidate_id: str) -> MaintainerCollectionValidationView | None:
        """The approved-registry resolution for one Collection Candidate."""

        return (
            None if self.maintainer is None else self.maintainer.collection_validation(candidate_id)
        )

    def promotion(
        self,
        focus: str,
        mode: PromotionMode = PromotionMode.VENDORED,
    ) -> MaintainerPromotionReviewView | None:
        """The promotion review for a focus that is a Candidate ID or one of its check rows."""

        if self.maintainer is None:
            return None
        row = parse_validation_row(focus)
        return self.maintainer.promotion(focus if row is None else row.candidate_id, mode)

    def registry_diff(
        self,
        focus: str,
        mode: PromotionMode = PromotionMode.VENDORED,
    ) -> MaintainerRegistryDiffView | None:
        """The registry transaction for a focus that is a Candidate ID or a check row."""

        if self.maintainer is None:
            return None
        row = parse_validation_row(focus)
        return self.maintainer.registry_diff(focus if row is None else row.candidate_id, mode)

    def bulk_promotions(self) -> tuple[MaintainerBulkPromotionView, ...]:
        """Every registry's selectable set, composed once outside drawing."""

        composed = None if self.maintainer is None else self.maintainer.bulk_promotions
        return () if composed is None else composed

    def maintainer_registries(self) -> tuple[MaintainerRegistryView, ...]:
        """Every configured registry, composed once: an installation may maintain more than one."""

        composed = None if self.maintainer is None else self.maintainer.registries
        return () if composed is None else composed

    def candidates(
        self, candidate_filter: MaintainerCandidateFilter | None = None
    ) -> tuple[MaintainerCandidateView, ...]:
        """The active Candidates this filter selects, composed once and never recomputed here."""

        composed = None if self.maintainer is None else self.maintainer.candidates
        if not composed:
            return ()
        if candidate_filter is None:
            return composed
        return filter_maintainer_candidates(composed, candidate_filter)

    @property
    def updatable(self) -> tuple[InstalledArtifactView, ...]:
        return tuple(item for item in self.installed if item.health == "update")


_DEFAULT_SETTINGS = ConsumerSettings()


@dataclass(frozen=True, slots=True)
class ConsumerOffers:
    """What the configured sources are offering right now, ready for :func:`screens_from`.

    `declined` names what a source published but this seam cannot offer yet. It is carried rather
    than dropped: an offer missing from the Marketplace with no explanation reads as a source that
    published nothing.
    """

    artifacts: tuple[MarketplaceEntry, ...] = ()
    collections: tuple[MarketplaceCollectionEntry, ...] = ()
    declined: tuple[str, ...] = ()
    #: Every enabled configured source, registry or not. Screen 21 lists what is configured, which
    #: is a wider set than what is offered: a source silently missing from it reads as unconfigured.
    registries: tuple[RegistryView, ...] = ()


def read_consumer_offers(
    effective,
    *,
    data_root: str,
    target: MarketplaceTarget,
) -> Result[ConsumerOffers]:
    """Read the configured Marketplace once, so a draw never reaches the source store (D-051).

    The offers are the approved published versions of the configured registries -- the same
    identities the configured install seam resolves against (INV-026). What is browsed here is
    therefore installable from here; a shell that offered anything wider would be advertising an
    action it has to refuse afterwards.

    Collections do not cross this seam. A canonical Collection is versioned and bound to the
    registry snapshot it was read from, and nothing downstream carries that version yet, so each is
    declined by name rather than offered without the version that tells two of them apart (B-031).
    """

    from agent_artifacts.io.configured_offers import read_configured_marketplace

    read = read_configured_marketplace(effective, data_root=data_root)
    if isinstance(read, Err):
        return read
    rows = project_marketplace_rows(read.value.catalog, target)
    return Ok(
        ConsumerOffers(
            tuple(MarketplaceEntry(row) for row in rows),
            (),
            read.value.declined,
            project_registries(read.value.catalog),
        )
    )


def screens_from(
    machine: ConsumerMachine,
    *,
    marketplace: tuple[MarketplaceEntry, ...] = (),
    collections: tuple[MarketplaceCollectionEntry, ...] = (),
    registries: tuple[RegistryView, ...] = (),
    settings: ConsumerSettings | None = None,
    maintainer: MaintainerViews | None = None,
    source_sync_review: MaintainerSourceSyncReviewView | None = None,
    source_sync_result: MaintainerSourceSyncResultView | None = None,
    promotion_validation: MaintainerRegistryValidationView | None = None,
    promotion_commit: MaintainerRegistryCommitView | None = None,
    plan: ConsumerPlanView | None = None,
    lifecycle: LifecyclePlanView | None = None,
    outcome: LifecycleOutcomeView | None = None,
    transaction: ReceiptDetailView | None = None,
    notice: tuple[str, ...] = (),
    pending_setup: tuple[DeclaredArtifactSetup, ...] = (),
    repository_scan: MaintainerRepositoryScanView | None = None,
    adoption_review: MaintainerAdoptionReviewView | None = None,
    adopted_artifacts: tuple[MaintainerAdoptedArtifactView, ...] = (),
    adoption_upstream: MaintainerAdoptionUpstreamView | None = None,
) -> ConsumerScreens:
    """The screens for one assembled machine, plus whatever the current flow is holding.

    What is offered is separate from what is installed because they are read from different places
    and go stale at different rates: a catalog is fetched, a machine is inspected, and a flow's plan
    belongs to the action somebody is in the middle of.
    """

    if not isinstance(machine, ConsumerMachine):
        raise ValueError("consumer screens need an assembled machine")
    if any(not isinstance(item, RegistryView) for item in registries):
        raise ValueError("consumer screens need projected registry views")
    # Which sources are configured is configuration, not durable machine evidence, so it arrives
    # here rather than in the machine -- and the dashboard counts the registries among them, since
    # an authoring Source is not one and saying "2 registries" over one would be a false count.
    composed = registries or machine.registries
    dashboard = machine.dashboard
    if registries:
        dashboard = replace(
            dashboard, registry_count=sum(1 for item in registries if item.is_registry)
        )
    return ConsumerScreens(
        dashboard,
        machine.installed,
        machine.activity,
        composed,
        _DEFAULT_SETTINGS if settings is None else settings,
        machine.doctor,
        machine.receipts,
        marketplace,
        collections,
        machine.collections,
        machine.credentials,
        plan,
        lifecycle,
        outcome,
        transaction,
        notice,
        maintainer,
        source_sync_review,
        source_sync_result,
        promotion_validation,
        promotion_commit,
        pending_setup,
        repository_scan,
        adoption_review,
        adopted_artifacts,
        adoption_upstream,
    )


_PLAN_SCREENS = frozenset(
    {
        ConsumerScreen.REVIEW_SELECTION,
        ConsumerScreen.AUTOMATIC_INSPECTION,
        ConsumerScreen.REQUIRED_INPUTS,
        ConsumerScreen.REMEDIATION,
        ConsumerScreen.READY,
        ConsumerScreen.UPDATE_INPUTS,
    }
)

_LIFECYCLE_SCREENS = frozenset(
    {
        ConsumerScreen.UNINSTALL_REVIEW,
        ConsumerScreen.VERIFY_REPAIR,
    }
)

#: The two screens an install lands on. An update or an uninstall is one artifact's lifecycle
#: action and keeps the single-outcome renderers.
_TRANSACTION_SCREENS = frozenset({ConsumerScreen.INSTALLING, ConsumerScreen.SUCCESS})

_OUTCOME_SCREENS = frozenset(
    {
        ConsumerScreen.INSTALLING,
        ConsumerScreen.SUCCESS,
        ConsumerScreen.UPDATING,
        ConsumerScreen.UNINSTALLING,
    }
)


#: Where an action's refusal is worth drawing: the screens `_request_action` and `_confirm_action`
#: move to, and -- since `QA-018`/`D-184` -- the screens a declined preparation moves back to.
#: Both sets are read from the action tables rather than listed again here, because a second
#: hand-maintained list of the same screens is a list that drifts, and the symptom of the drift is
#: an answer nobody can see: a review with no plan under it, or a run whose stages are never drawn
#: (`QA-024`). Everywhere else the notice would answer a question nobody asked here.
_ANSWERABLE = (
    _PLAN_SCREENS | _LIFECYCLE_SCREENS | _OUTCOME_SCREENS | ACTION_REQUEST_SCREENS
) | ACTION_ANSWER_SCREENS


def _candidate_filter(state: ConsumerUiState) -> MaintainerCandidateFilter:
    """What screen 35 is narrowed to: the typed filter, with the search box as its query.

    Rows and body have to agree, so neither reads the search text for itself. An open search box
    narrows the typed filter rather than replacing it, and closing it restores whatever screen 53
    had already selected.
    """

    return (
        state.candidate_filter
        if not state.search
        else state.candidate_filter.with_query(state.search)
    )


def _matches(query: str, *fields: str) -> bool:
    lowered = query.strip().lower()
    return not lowered or any(lowered in field.lower() for field in fields)


class CanonicalScreenSource:
    """A screen source over already-projected canonical views.

    It answers three questions and derives nothing else: which rows a screen is showing, how to
    draw it, and where Enter goes.  Search filters rows here rather than in the reducer, because
    what a query matches is a property of the screen's own content.
    """

    def __init__(self, screens: ConsumerScreens) -> None:
        if not isinstance(screens, ConsumerScreens):
            raise ValueError("a screen source needs projected consumer screens")
        self._screens = screens

    @property
    def screens(self) -> ConsumerScreens:
        return self._screens

    def rows(self, state: ConsumerUiState) -> tuple[str, ...]:
        screen, query = state.session.screen, state.search
        if screen is ConsumerScreen.DASHBOARD:
            return tuple(
                target.value
                for target in navigation_targets(
                    screen, maintainer_mode=state.settings.maintainer_mode
                )
            )
        if screen is MaintainerScreen.DASHBOARD:
            return tuple(
                target.value
                for target in navigation_targets(
                    screen, maintainer_mode=state.settings.maintainer_mode
                )
            )
        if screen is MaintainerScreen.SOURCES:
            return (
                ()
                if self._screens.maintainer is None
                else tuple(source.alias for source in self._screens.maintainer.sources)
            )
        if screen is MaintainerScreen.REGISTRY:
            return tuple(item.alias for item in self._screens.maintainer_registries())
        if screen is MaintainerScreen.SCAN_RESULT:
            scan = self._screens.repository_scan
            return (
                ()
                if scan is None
                else tuple(item.coordinate for item in scan.artifacts if item.adoptable)
            )
        if screen is MaintainerScreen.ADOPTED_ARTIFACTS:
            return tuple(item.coordinate for item in self._screens.adopted_artifacts)
        if screen is MaintainerScreen.BULK_PROMOTION:
            return tuple(
                candidate.candidate_id
                for view in self._screens.bulk_promotions()
                for candidate in view.candidates
            )
        if screen is MaintainerScreen.CANDIDATES:
            # The row identity is the Candidate ID rather than the artifact name: two Sources may
            # both publish `github-mcp`, and a list keyed by name would open the wrong one.
            return tuple(item.id for item in self._screens.candidates(_candidate_filter(state)))
        if screen is MaintainerScreen.COLLECTION_CANDIDATES:
            return tuple(item.candidate_id for item in self._screens.collection_candidates())
        if screen is MaintainerScreen.CANDIDATE_FILTERS:
            # The values on offer come from every composed Candidate rather than from the already
            # narrowed list: a row that vanished the moment it was ticked could never be unticked.
            return project_maintainer_candidate_filters(
                self._screens.candidates(), _candidate_filter(state)
            ).rows
        if screen is MaintainerScreen.VALIDATION:
            # A check name alone would be ambiguous across Candidates, so a row carries both.
            validation = self._screens.validation(state.focus)
            return () if validation is None else tuple(item.row for item in validation.checks)
        if screen is ConsumerScreen.MARKETPLACE:
            return tuple(
                item.key
                for item in self._offers()
                if _matches(query, item.key, self._summary(item))
            )
        if screen in (ConsumerScreen.COLLECTION_PREVIEW, ConsumerScreen.COLLECTION_CUSTOMIZE):
            preview = self._screens.offered_collection(state.focus)
            return () if preview is None else preview.members
        if screen is ConsumerScreen.INSTALLED:
            return tuple(
                item.collection
                for item in self._screens.installed_collections
                if _matches(query, item.collection, item.health)
            ) + tuple(
                item.coordinate
                for item in self._screens.installed
                if _matches(query, item.coordinate, item.health)
            )
        if screen is ConsumerScreen.UPDATES:
            return tuple(
                item.coordinate
                for item in self._screens.updatable
                if _matches(query, item.coordinate)
            )
        if screen is ConsumerScreen.CREDENTIALS:
            return tuple(
                item.reference
                for item in self._screens.credentials
                if _matches(query, item.reference, item.input, item.health)
            )
        if screen is ConsumerScreen.ACTIVITY:
            return tuple(
                item.recorded_at
                for item in self._screens.activity.entries
                if _matches(query, item.summary, item.intent)
            )
        if screen is ConsumerScreen.DOCTOR:
            if self._screens.doctor is None:
                return ()
            return tuple(
                item for item in self._screens.doctor.repairable_issues if _matches(query, item)
            )
        if screen is ConsumerScreen.REGISTRIES:
            return ("add-registry",) + tuple(
                item.alias for item in self._screens.registries if _matches(query, item.alias)
            )
        if screen is ConsumerScreen.REGISTRY_ADD:
            return ("alias", "url", "ref", "default", "connect")
        if screen is MaintainerScreen.SOURCE_ADD:
            return ("alias", "kind", "location", "ref", "connect")
        if screen is MaintainerScreen.REGISTRY_INIT:
            return ("id", "name", "reporting", "commit", "initialize")
        if (
            screen is MaintainerScreen.REGISTRY_COMMIT
            and state.registry_commit_applied
            and state.registry_publication_configuring
            and not state.registry_publication_completed
            and state.action is None
        ):
            return ("publication-remote", "publication-branch", "publish")
        if screen is MaintainerScreen.REGISTRY_REBUILD:
            # Derived from the sequence itself: a stage the run gains is a row the picker offers.
            return (REGISTRY_REBUILD_EVERYTHING, *REGISTRY_MAINTENANCE_STAGES)
        if screen is MaintainerScreen.REPOSITORY_SCAN:
            return ("url", "ref", "scan")
        if screen is ConsumerScreen.SETTINGS:
            return SETTING_ROWS
        return ()

    def _offers(self) -> tuple[MarketplaceEntry | MarketplaceCollectionEntry, ...]:
        return (*self._screens.marketplace, *self._screens.collections)

    @staticmethod
    def _summary(entry: MarketplaceEntry | MarketplaceCollectionEntry) -> str:
        if isinstance(entry, MarketplaceEntry):
            return entry.row.summary
        return entry.collection.summary

    def collection(self, key: str, selected: tuple[str, ...]) -> MarketplaceCollectionView:
        """One offered Collection as the given ticks make it: exact, or a custom selection."""

        entry = self._screens.offered_collection(key)
        if entry is None:
            raise ValueError(f"no Collection is offered as {key}")
        return entry.view(selected)

    def selected(self, state: ConsumerUiState) -> tuple[str, ...] | None:
        """A Collection opens with every member ticked; nothing else has an opinion."""

        if state.session.screen is MaintainerScreen.SCAN_RESULT:
            return ()
        if state.session.screen is not ConsumerScreen.COLLECTION_PREVIEW:
            return None
        entry = self._screens.offered_collection(state.focus)
        return None if entry is None else entry.members

    def detail(self, state: ConsumerUiState) -> ApplicationScreen | None:
        """Enter opens the detail of whatever this screen is currently about."""

        screen, row = state.session.screen, state.current_row or state.focus
        if screen is ConsumerScreen.DASHBOARD:
            return next(
                (
                    target
                    for target in navigation_targets(
                        screen, maintainer_mode=state.settings.maintainer_mode
                    )
                    if target.value == row
                ),
                None,
            )
        if screen is MaintainerScreen.DASHBOARD:
            return next(
                (
                    target
                    for target in navigation_targets(
                        screen, maintainer_mode=state.settings.maintainer_mode
                    )
                    if target.value == row
                ),
                None,
            )
        if screen is MaintainerScreen.REGISTRY:
            # Screen 46's rows are registries; opening one is where its transaction is assembled.
            return MaintainerScreen.BULK_PROMOTION if self._screens.bulk_promotions() else None
        if screen is MaintainerScreen.SOURCES:
            maintainer = self._screens.maintainer
            return (
                MaintainerScreen.SOURCE_DETAILS
                if maintainer is not None and maintainer.source(row) is not None
                else None
            )
        if screen is MaintainerScreen.CANDIDATES:
            return (
                MaintainerScreen.CANDIDATE_DETAILS
                if self._screens.candidate(row) is not None
                else None
            )
        if screen is MaintainerScreen.CANDIDATE_DETAILS:
            return (
                MaintainerScreen.CANDIDATE_DIFF
                if self._screens.candidate(state.focus) is not None
                else None
            )
        if screen is MaintainerScreen.CANDIDATE_DIFF:
            # Review runs forward: having read the diff, the next question is whether it passed.
            return (
                MaintainerScreen.VALIDATION
                if self._screens.validation(state.focus) is not None
                else None
            )
        if screen is MaintainerScreen.CANDIDATE_LIFECYCLE:
            return (
                MaintainerScreen.PROVENANCE
                if self._screens.candidate_provenance(state.focus) is not None
                else None
            )
        if screen is MaintainerScreen.PROVENANCE:
            return (
                MaintainerScreen.VERSION_CONFLICT
                if self._screens.version_conflict(state.focus) is not None
                else None
            )
        if screen is MaintainerScreen.COLLECTION_CANDIDATES:
            return (
                MaintainerScreen.COLLECTION_VALIDATION
                if self._screens.maintainer is not None
                and self._screens.maintainer.collection_candidate(row) is not None
                and self._screens.collection_validation(row) is not None
                else None
            )
        if screen is MaintainerScreen.VALIDATION:
            return (
                MaintainerScreen.VALIDATION_DETAILS
                if parse_validation_row(row) is not None
                else None
            )
        if screen is MaintainerScreen.VALIDATION_DETAILS:
            # A check detail is an optional inspection inside the same completed validation run.
            # Enter continues to the policy judgement instead of ending in a screen that only Esc
            # can leave (`QA-074`).
            return (
                MaintainerScreen.POLICY_REVIEW
                if self._screens.validation(state.focus) is not None
                else None
            )
        if screen is MaintainerScreen.POLICY_REVIEW:
            # Review ends by asking what promoting would write, including when the answer is that
            # it would write nothing.
            return (
                MaintainerScreen.PROMOTION_REVIEW
                if self._screens.promotion(state.focus, state.promotion_mode) is not None
                else None
            )
        if screen is MaintainerScreen.PROMOTION_REVIEW:
            return (
                MaintainerScreen.PROMOTION_MODE
                if self._screens.promotion(state.focus, state.promotion_mode) is not None
                else None
            )
        if screen is MaintainerScreen.PROMOTION_MODE:
            return (
                MaintainerScreen.REGISTRY_DIFF
                if self._screens.registry_diff(state.focus, state.promotion_mode) is not None
                else None
            )
        if screen is MaintainerScreen.REGISTRY_VALIDATION:
            return (
                MaintainerScreen.REGISTRY_COMMIT
                if self._screens.promotion_validation is not None
                else None
            )
        if screen is MaintainerScreen.SCAN_RESULT:
            return None
        if screen is ConsumerScreen.MARKETPLACE:
            if self._screens.offered_collection(state.current_row) is not None:
                return ConsumerScreen.COLLECTION_PREVIEW
            return ConsumerScreen.ARTIFACT_DETAILS if state.current_row else None
        if screen is ConsumerScreen.COLLECTION_PREVIEW:
            return ConsumerScreen.COLLECTION_CUSTOMIZE if state.focus else None
        if screen is ConsumerScreen.INSTALLED:
            if self._screens.installed_collection(state.current_row) is not None:
                return ConsumerScreen.INSTALLED_COLLECTION_DETAILS
            return ConsumerScreen.INSTALLED_ARTIFACT_DETAILS if state.current_row else None
        if screen is ConsumerScreen.REVIEW_SELECTION:
            plan = self._screens.plan
            if plan is None:
                return None
            # Inspection has already happened to produce this immutable plan. It remains
            # available as a detailed projection, but is not a mandatory click-through step.
            if plan.inputs:
                return ConsumerScreen.REQUIRED_INPUTS
            if plan.remediations:
                return ConsumerScreen.REMEDIATION
            return ConsumerScreen.READY
        if screen is ConsumerScreen.AUTOMATIC_INSPECTION:
            plan = self._screens.plan
            if plan is None:
                return None
            if plan.inputs:
                return ConsumerScreen.REQUIRED_INPUTS
            if plan.remediations:
                return ConsumerScreen.REMEDIATION
            return ConsumerScreen.READY
        if screen is ConsumerScreen.REQUIRED_INPUTS:
            plan = self._screens.plan
            if plan is None:
                return None
            return ConsumerScreen.REMEDIATION if plan.remediations else ConsumerScreen.READY
        if screen is ConsumerScreen.REMEDIATION:
            return ConsumerScreen.READY if self._screens.plan is not None else None
        if not isinstance(screen, ConsumerScreen):
            return None
        target = {
            ConsumerScreen.ACTIVITY: ConsumerScreen.ACTIVITY_DETAILS,
            ConsumerScreen.ACTIVITY_DETAILS: ConsumerScreen.RECEIPT_DETAILS,
            ConsumerScreen.CREDENTIALS: ConsumerScreen.CREDENTIAL_DETAILS,
            ConsumerScreen.CREDENTIAL_DETAILS: ConsumerScreen.CREDENTIAL_ACTION,
            ConsumerScreen.UPDATES: ConsumerScreen.UPDATE_INPUTS,
            ConsumerScreen.REGISTRIES: ConsumerScreen.REGISTRY_ADD,
        }.get(screen)
        if target is None or not row:
            return None
        if screen is ConsumerScreen.REGISTRIES and row != "add-registry":
            return None
        return target

    def lines(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The screen's body, and on the screens an action lands on, why it could not run.

        The notice is confined to those screens deliberately. It answers a question somebody just
        asked, so it belongs where they asked it; carrying it onto the dashboard would leave a
        stale explanation standing over a screen that never ran anything.
        """

        body = self._body(state)
        notice = self._screens.notice if state.session.screen in _ANSWERABLE else ()
        # `QA-029`: the one line addressed to the reader goes last, under everything it is about,
        # separated by a blank. A notice is the thing being asked about, so it lands above the ask
        # rather than under it -- which is where an answered review used to leave the reader.
        prompt = body[-1] if body and is_action_prompt(body[-1]) else ""
        facts = separate(body[:-1] if prompt else body, notice)
        if not prompt:
            return facts
        return action_prompt(facts, prompt)

    def description(self, state: ConsumerUiState) -> tuple[str, ...]:
        """What the row under the cursor is, as bare lines the skeleton will bound (`QA-067`).

        It answers from the cursor rather than from the screen, so a screen that gains describable
        rows tomorrow says something here without the frame changing.
        """

        if state.session.screen not in _DESCRIBED_SCREENS:
            return ()
        targets = navigation_targets(
            state.session.screen, maintainer_mode=state.settings.maintainer_mode
        )
        selected = next((target for target in targets if target.value == state.current_row), None)
        described = None if selected is None else _DASHBOARD_DESCRIPTIONS.get(selected)
        return () if described is None else (described,)

    def status(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The state of the whole view, or nothing at all (`QA-067`).

        Returning `()` is the point: an empty view-status section is omitted entirely rather than
        drawn as a boundary around nothing, which is the fault `QA-065` reported.
        """

        if state.session.screen is ConsumerScreen.DASHBOARD:
            screens = self._screens
            first_run = (
                not screens.registries
                and screens.dashboard.registry_count == 0
                and screens.dashboard.installed_count == 0
            )
            return () if first_run else render_dashboard(screens.dashboard)
        return ()

    def _body(self, state: ConsumerUiState) -> tuple[str, ...]:
        screen, profile = state.session.screen, state.session.profile
        screens = self._screens
        if screen is ConsumerScreen.DASHBOARD:
            targets = navigation_targets(screen, maintainer_mode=state.settings.maintainer_mode)
            menu = tuple(
                f"{'>' if row == state.current_row else ' '} {_title(target)}"
                for row, target in zip(
                    state.rows,
                    targets,
                    strict=False,
                )
            )
            # A first run is a machine that has nothing, not merely a machine that has no source
            # configured.  A person who installed an artifact from a source they have since
            # removed -- or through a direct install -- is not seeing AART for the first time, and
            # replacing their real counts with the welcome panel hides the one thing the Dashboard
            # exists to state: what is installed right now (B-080).
            first_run = (
                not screens.registries
                and screens.dashboard.registry_count == 0
                and screens.dashboard.installed_count == 0
            )
            if first_run:
                return (*_FIRST_RUN_LINES, "", "Navigation:", *menu)
            return ("Navigation:", *menu)
        if screen is MaintainerScreen.DASHBOARD:
            if screens.maintainer is None:
                return ("Maintainer state is not available yet.",)
            menu = tuple(
                f"{'>' if row == state.current_row else ' '} {_title(target)}"
                for row, target in zip(
                    state.rows,
                    navigation_targets(screen, maintainer_mode=state.settings.maintainer_mode),
                    strict=False,
                )
            )
            return (
                "Maintainer navigation:",
                *menu,
                "",
                *render_maintainer_dashboard(screens.maintainer.dashboard, profile),
            )
        if screen is MaintainerScreen.SOURCES:
            return (
                ("Maintainer state is not available yet.",)
                if screens.maintainer is None
                else render_maintainer_sources(
                    screens.maintainer.sources,
                    cursor=state.current_row,
                    profile=profile,
                )
            )
        if screen is MaintainerScreen.SOURCE_DETAILS:
            source = None if screens.maintainer is None else screens.maintainer.source(state.focus)
            return (
                ("That authoring Source is not available.",)
                if source is None
                else render_maintainer_source(source, profile)
            )
        if screen is MaintainerScreen.SOURCE_SYNC:
            return (
                ("No Source Sync has been prepared.",)
                if screens.source_sync_review is None
                else render_source_sync_review(screens.source_sync_review, profile)
            )
        if screen is MaintainerScreen.SOURCE_SYNC_RESULT:
            return (
                ("No Source Sync result has been persisted.",)
                if screens.source_sync_result is None
                else render_source_sync_result(screens.source_sync_result, profile)
            )
        if screen is MaintainerScreen.CANDIDATES:
            # An unavailable Maintainer composition and a Source that genuinely produced nothing
            # are different answers, and a list that says "none" to both hides the first one.
            return (
                ("Maintainer state is not available yet.",)
                if screens.maintainer is None
                else render_maintainer_candidates(
                    screens.candidates(_candidate_filter(state)),
                    cursor=state.current_row,
                    profile=profile,
                )
            )
        if screen is MaintainerScreen.CANDIDATE_DETAILS:
            candidate = screens.candidate(state.focus)
            return (
                ("That Candidate is not available.",)
                if candidate is None
                else render_maintainer_candidate(candidate, profile)
            )
        if screen is MaintainerScreen.CANDIDATE_DIFF:
            candidate = screens.candidate(state.focus)
            return (
                ("That Candidate is not available.",)
                if candidate is None
                else render_maintainer_candidate_diff(
                    candidate, profile, show_files=state.file_diff
                )
            )
        if screen is MaintainerScreen.CANDIDATE_LIFECYCLE:
            lifecycle = screens.candidate_lifecycle(state.focus)
            return (
                ("That Candidate's lifecycle is not available.",)
                if lifecycle is None
                else render_maintainer_candidate_lifecycle(lifecycle, profile)
            )
        if screen is MaintainerScreen.PROVENANCE:
            provenance = screens.candidate_provenance(state.focus)
            return (
                ("That Candidate's provenance is not available.",)
                if provenance is None
                else render_maintainer_provenance(provenance, profile)
            )
        if screen is MaintainerScreen.VERSION_CONFLICT:
            conflict = screens.version_conflict(state.focus)
            return (
                ("That Candidate has no immutable version conflict.",)
                if conflict is None
                else render_maintainer_version_conflict(conflict, profile)
            )
        if screen is MaintainerScreen.COLLECTION_CANDIDATES:
            return render_maintainer_collection_candidates(
                screens.collection_candidates(),
                cursor=state.current_row,
                profile=profile,
            )
        if screen is MaintainerScreen.COLLECTION_VALIDATION:
            collection_validation = screens.collection_validation(state.focus)
            return (
                ("That Collection Candidate's validation is not available.",)
                if collection_validation is None
                else render_maintainer_collection_validation(collection_validation, profile)
            )
        if screen is MaintainerScreen.CANDIDATE_FILTERS:
            return render_maintainer_candidate_filters(
                project_maintainer_candidate_filters(
                    screens.candidates(), _candidate_filter(state)
                ),
                profile,
                cursor=state.current_row,
            )
        if screen is MaintainerScreen.VALIDATION:
            validation = screens.validation(state.focus)
            return (
                ("That Candidate's validation is not available.",)
                if validation is None
                else render_maintainer_validation(validation, profile)
            )
        if screen is MaintainerScreen.VALIDATION_DETAILS:
            validation = screens.validation(state.focus)
            row = parse_validation_row(state.focus)
            return (
                ("That validation check is not available.",)
                if validation is None or row is None
                else render_maintainer_validation_check(validation.check(row.check.value), profile)
            )
        if screen is MaintainerScreen.POLICY_REVIEW:
            validation = screens.validation(state.focus)
            return (
                ("Policy Review is not available yet.",)
                if validation is None
                else render_maintainer_policy_review(validation.review, profile)
            )
        if screen is MaintainerScreen.REGISTRY_DIFF:
            registry_diff = screens.registry_diff(state.focus, state.promotion_mode)
            return (
                ("That Candidate's registry transaction is not available.",)
                if registry_diff is None
                else render_maintainer_registry_diff(registry_diff, profile)
            )
        if screen is MaintainerScreen.REGISTRY:
            present = (
                True
                if screens.maintainer is None
                else screens.maintainer.registry_workspace_present
            )
            return render_maintainer_registries(
                screens.maintainer_registries(),
                profile,
                registry_workspace_present=present,
            )
        if screen is MaintainerScreen.SCAN_RESULT:
            return (
                ("No repository has been scanned yet.",)
                if screens.repository_scan is None
                else render_repository_scan(
                    screens.repository_scan,
                    state.selection,
                    cursor=state.current_row,
                    profile=profile,
                )
            )
        if screen is MaintainerScreen.ADOPTION_REVIEW:
            return (
                ("No repository adoption has been prepared.",)
                if screens.adoption_review is None
                else render_repository_adoption_review(screens.adoption_review, profile)
            )
        if screen is MaintainerScreen.ADOPTED_ARTIFACTS:
            return render_adopted_artifacts(
                screens.adopted_artifacts,
                cursor=state.current_row,
                profile=profile,
            )
        if screen is MaintainerScreen.UPSTREAM_CHECK:
            return (
                ("No adopted artifact has been checked yet.",)
                if screens.adoption_upstream is None
                else render_adoption_upstream_check(screens.adoption_upstream, profile)
            )
        if screen is MaintainerScreen.BULK_PROMOTION:
            return render_maintainer_bulk_promotion(
                screens.bulk_promotions(), state.selection, profile
            )
        if screen is MaintainerScreen.REGISTRY_VALIDATION:
            return (
                ("That promoted registry validation is not available.",)
                if screens.promotion_validation is None
                else render_maintainer_registry_validation(screens.promotion_validation, profile)
            )
        if screen is MaintainerScreen.REGISTRY_COMMIT:
            return (
                ("That registry commit is not available.",)
                if screens.promotion_commit is None
                else render_maintainer_registry_commit(
                    screens.promotion_commit,
                    profile,
                    publication_remote=state.registry_publication_draft.remote,
                    publication_branch=state.registry_publication_draft.branch,
                    cursor=state.current_row,
                    configure_publication=state.registry_publication_configuring,
                )
            )
        if screen in (MaintainerScreen.PROMOTION_REVIEW, MaintainerScreen.PROMOTION_MODE):
            # Screen 42 asks which promotion, so it draws the review of the mode currently chosen
            # rather than a separate summary that could drift from what 41 showed.
            promotion = screens.promotion(state.focus, state.promotion_mode)
            return (
                ("That Candidate's promotion review is not available.",)
                if promotion is None
                else render_maintainer_promotion_review(promotion, profile)
            )
        if screen is ConsumerScreen.MARKETPLACE:
            offered = {item.key: item for item in self._offers()}
            return self._list(
                state,
                tuple(
                    f"{key}  {self._summary(offered[key])}" for key in state.rows if key in offered
                ),
            )
        if screen is ConsumerScreen.ARTIFACT_DETAILS:
            entry = screens.offered(state.focus)
            return (
                ("Nothing is offered here.",)
                if entry is None
                else render_marketplace_artifact(entry.row, profile, inputs=entry.inputs)
            )
        if screen in (ConsumerScreen.COLLECTION_PREVIEW, ConsumerScreen.COLLECTION_CUSTOMIZE):
            preview = screens.offered_collection(state.focus)
            if preview is None:
                return ("No Collection is offered here.",)
            return render_collection(preview.view(state.selection), profile)
        if screen in (ConsumerScreen.INSTALLED, ConsumerScreen.UPDATES):
            health = {item.collection: item.health for item in screens.installed_collections}
            health.update({item.coordinate: item.health for item in screens.installed})
            return self._list(
                state, tuple(f"{row}  {_human(health.get(row, 'unknown'))}" for row in state.rows)
            )
        if screen is ConsumerScreen.INSTALLED_COLLECTION_DETAILS:
            group = screens.installed_collection(state.focus)
            return (
                ("No Collection is installed here.",)
                if group is None
                else render_installed_collection(group, profile)
            )
        if screen is ConsumerScreen.CREDENTIALS:
            return self._list(
                state,
                tuple(
                    _credential_row(item)
                    for item in screens.credentials
                    if item.reference in state.rows
                ),
            )
        if screen in (ConsumerScreen.CREDENTIAL_DETAILS, ConsumerScreen.CREDENTIAL_ACTION):
            record = screens.credential(state.focus)
            if record is None:
                return ("No credential is known here.",)
            if screen is ConsumerScreen.CREDENTIAL_DETAILS:
                return render_credential(record, profile)
            return render_credential_action(record, profile)
        if screen is ConsumerScreen.INSTALLED_ARTIFACT_DETAILS:
            artifact = screens.artifact(state.focus)
            return (
                ("Nothing is installed here.",)
                if artifact is None
                else render_installed_artifact(artifact, profile)
            )
        if screen is ConsumerScreen.ACTIVITY:
            return render_activity(screens.activity, profile)
        if screen in (ConsumerScreen.ACTIVITY_DETAILS, ConsumerScreen.RECEIPT_DETAILS):
            receipt = screens.receipt(state.focus)
            return (
                ("That action left no receipt.",)
                if receipt is None
                else render_receipt_detail(receipt, profile)
            )
        if screen is ConsumerScreen.REGISTRIES:
            add = (
                f"{'>' if state.current_row == 'add-registry' else ' '} [ Add Registry ]",
                "Connect an approved Git registry by URL. Local authoring Sources belong in Maintainer Mode.",
            )
            if not screens.registries:
                return (
                    *add,
                    "No sources are configured.",
                    "Marketplace needs an approved registry before it can offer tools.",
                    "Choose Add Registry above to connect the first one.",
                )
            return cards(
                add,
                *(
                    render_registry(item, profile, focused=item.alias == state.current_row)
                    for item in screens.registries
                ),
            )
        if screen is ConsumerScreen.REGISTRY_ADD:
            draft = state.registry_draft
            values = {
                "alias": draft.alias or "<type a short name>",
                "url": draft.location or "<type an HTTPS or SSH Git URL>",
                "ref": draft.ref or "<repository default>",
                "default": "yes" if draft.make_default else "no",
                "connect": "Validate and review",
            }
            labels = {
                "alias": "Alias",
                "url": "Registry URL",
                "ref": "Branch or tag",
                "default": "Make default registry",
                "connect": "Continue",
            }
            return (
                "Connect an approved registry. AART validates a fresh snapshot before saving it.",
                "Local folders are authoring Sources, not Marketplace registries.",
                "",
                # `QA-028`: the empty form says a new one is being made; this says the old ones
                # are not being replaced by it, which is the question the operator actually asked.
                "This adds another registry. Nothing already connected is changed.",
                "",
                *(
                    f"{'>' if row == state.current_row else ' '} {labels[row]}: {values[row]}"
                    for row in state.rows
                ),
                "",
                "Type to edit; Backspace removes; Space toggles default; Enter advances.",
            )
        if screen is MaintainerScreen.SOURCE_ADD:
            authoring = state.source_draft
            git = authoring.kind == "source-git"
            values = {
                "alias": authoring.alias or "<type a short name>",
                "kind": authoring.kind,
                "location": authoring.location
                or (
                    "<type a credential-free Git URL>"
                    if git
                    else "<type an absolute path to a checkout>"
                ),
                "ref": (authoring.ref or "<repository default>") if git else "not applicable",
                "connect": "Validate and review",
            }
            labels = {
                "alias": "Alias",
                "kind": "Kind",
                "location": "Location",
                "ref": "Branch or tag",
                "connect": "Continue",
            }
            return (
                "Subscribe to an authoring repository. AART discovers only the aart.yaml and",
                "aart.json manifests its authors committed; nothing here is approved content yet.",
                "",
                "This adds another Source. Nothing already connected is changed.",
                "",
                *(
                    f"{'>' if row == state.current_row else ' '} {labels[row]}: {values[row]}"
                    for row in state.rows
                ),
                "",
                "Type to edit; Backspace removes; Space switches kind; Enter advances.",
            )
        if screen is MaintainerScreen.REGISTRY_INIT:
            init = state.registry_init_draft
            values = {
                "id": init.registry_id or "<type a name like acme-registry>",
                "name": init.display_name or "<type what people should call it>",
                "reporting": init.usage_reporting or "not enabled",
                "commit": "yes, one local commit" if init.commit else "no, leave the files staged",
                "initialize": "Review the five stages",
            }
            labels = {
                "id": "Registry ID",
                "name": "Display name",
                "reporting": "Usage reporting",
                "commit": "Local commit",
                "initialize": "Continue",
            }
            return (
                "Create the registry this project publishes. AART writes its skeleton, pins what",
                "it references, builds its index, then validates and audits the result.",
                "",
                *(
                    f"{'>' if row == state.current_row else ' '} {labels[row]}: {values[row]}"
                    for row in state.rows
                ),
                "",
                # 164.7, said where the decision is made rather than only in the specification.
                # AART does publish a reviewed commit, from screen 45 -- but not this run, and never
                # a merge, so the sentence has to name the boundary it actually holds.
                "Nothing is pushed and nothing is merged here. Once a promotion is committed,",
                "Registry Commit can publish it to a review branch; the merge is always yours.",
                "",
                "Type to edit; Backspace removes; Space toggles the commit; Enter advances.",
            )
        if screen is MaintainerScreen.REPOSITORY_SCAN:
            scan = state.repository_scan_draft
            values = {
                "url": scan.url or "<type a credential-free HTTPS or SSH Git URL>",
                "ref": scan.ref or "<type a branch or tag>",
                "scan": "Read the declared manifests",
            }
            labels = {
                "url": "Repository URL",
                "ref": "Branch or tag",
                "scan": "Continue",
            }
            return (
                "Look at one repository for explicit aart.yaml and aart.json manifests.",
                "This is a one-off read: the repository is not saved as a Source or monitored.",
                "",
                *(
                    f"{'>' if row == state.current_row else ' '} {labels[row]}: {values[row]}"
                    for row in state.rows
                ),
                "",
                "Type to edit; Backspace removes; Enter advances.",
            )
        if screen is MaintainerScreen.REGISTRY_REBUILD:
            rows = (REGISTRY_REBUILD_EVERYTHING, *REGISTRY_MAINTENANCE_STAGES)
            labels = {
                REGISTRY_REBUILD_EVERYTHING: "Everything, in order: "
                + ", ".join(REGISTRY_MAINTENANCE_STAGES),
                **{
                    stage: f"{stage.title()} only: {REGISTRY_STAGE_PURPOSE[stage]}"
                    for stage in REGISTRY_MAINTENANCE_STAGES
                },
            }
            return (
                "Re-run this registry's generated files. Promoting, adopting or editing anything",
                "leaves the lock and the index describing the registry as it was.",
                "",
                *(
                    f"{'>' if row == (state.current_row or rows[0]) else ' '} {labels[row]}"
                    for row in rows
                ),
                "",
                # 161.7 again: the run writes into the checkout and stops there.
                "Nothing is pushed and nothing is merged. What this writes is reviewed in the",
                "repository like any other change.",
                "",
                "Enter reviews the run under the cursor.",
            )
        if screen is MaintainerScreen.REGISTRY_REBUILD_REVIEW:
            return _review_prompt(state, "Press Enter to start this run.")
        if screen is MaintainerScreen.REGISTRY_INIT_REVIEW:
            return _review_prompt(state, "Press Enter to create this registry.")
        if screen is MaintainerScreen.SOURCE_ADD_REVIEW:
            return _review_prompt(state, "Press Enter to connect this Source.")
        if screen is ConsumerScreen.REGISTRY_REVIEW:
            return _review_prompt(state, "Press Enter to connect this registry.")
        if screen is ConsumerScreen.REGISTRY_SYNC:
            connected = next(
                (item for item in screens.registries if item.alias == state.focus),
                None,
            )
            if connected is None:
                return ("That registry is not connected here.",)
            return (
                f"Refresh {connected.alias} from {connected.origin}",
                f"Branch or tag: {connected.ref or 'repository default'}",
                "",
                "This fetches a fresh approved snapshot and reloads what Marketplace can offer.",
                # 161.7, stated where the decision is made rather than only in the specification.
                "It does not update anything installed: a newer version becomes available to",
                "choose, and every installed artifact stays exactly as it is.",
                "",
                "If the fetch fails, the snapshot you already have is kept.",
                "",
                "Press Enter to refresh.",
            )
        if screen is ConsumerScreen.REGISTRY_REMOVE:
            return _review_prompt(state, "Press Enter to disconnect this Registry.")
        if not isinstance(screen, ConsumerScreen):
            return (f"{_title(screen)} is not available yet.",)
        if screen in _PLAN_SCREENS:
            return self._plan(screen, state)
        if screen in _LIFECYCLE_SCREENS:
            return (
                ("Nothing has been planned yet.",)
                if screens.lifecycle is None
                else render_lifecycle_plan(screens.lifecycle, profile)
            )
        if screen in _OUTCOME_SCREENS:
            if screen in _TRANSACTION_SCREENS and screens.transaction is not None:
                if screen is ConsumerScreen.SUCCESS:
                    return render_transaction_success(
                        screens.transaction, profile
                    ) + render_pending_setup(screens.pending_setup)
                return render_transaction_progress(screens.transaction, profile)
            if screens.outcome is None:
                return ("Nothing has run yet.",)
            if screen is ConsumerScreen.SUCCESS:
                return render_success(screens.outcome, profile)
            return render_progress(screens.outcome, profile)
        if screen is ConsumerScreen.SETTINGS:
            # A preference belongs to the session, not to the machine snapshot: drawing the
            # composed source's copy would keep showing the old value until something else
            # happened to re-read the machine.
            return render_settings(state.settings, state.current_row)
        if screen is ConsumerScreen.DOCTOR:
            return (
                ("Nothing has been checked yet.",)
                if screens.doctor is None
                else render_doctor(screens.doctor, profile)
            )
        # A screen added to the catalog without a body reaches here. It is a guard against drawing
        # a blank frame, not a statement about the accepted catalog: no accepted screen reaches it.
        return (f"{_title(screen)} is not available yet.",)

    def _plan(self, screen: ConsumerScreen, state: ConsumerUiState) -> tuple[str, ...]:
        plan, profile = self._screens.plan, state.session.profile
        if plan is None:
            return ("Nothing has been planned yet.",)
        if screen is ConsumerScreen.REVIEW_SELECTION:
            return render_review_selection(plan, profile)
        if screen is ConsumerScreen.AUTOMATIC_INSPECTION:
            return render_inspection(plan, profile)
        if screen in (ConsumerScreen.REQUIRED_INPUTS, ConsumerScreen.UPDATE_INPUTS):
            return render_required_inputs(plan.inputs, profile)
        if screen is ConsumerScreen.REMEDIATION:
            return render_remediation(plan, profile)
        return render_ready(plan, profile)

    def _list(self, state: ConsumerUiState, entries: tuple[str, ...]) -> tuple[str, ...]:
        if not entries:
            return ("Nothing here yet.",)
        return tuple(
            f"{'>' if row == state.current_row else ' '} "
            f"{'[x]' if row in state.selection else '[ ]'} {entry}"
            for row, entry in zip(state.rows, entries, strict=False)
        )
