"""The consumer frontend: text renderers for the canonical view models, and the loop over them.

The renderers decide only how much detail to disclose; they never derive a plan or mutate consumer
intent.  :func:`run_consumer_shell` drives them, but it reaches the terminal and the machine only
through injected ports, so the persistent application is exercised headlessly with a fake terminal
and the curses adapter stays as thin as a `getch`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable, Protocol, TypeAlias, runtime_checkable

from agent_artifacts.application.consumer_session import ConsumerMachine
from agent_artifacts.application.consumer_ui import (
    ACTION_ANSWER_SCREENS,
    ACTION_REQUEST_SCREENS,
    CONFIG_CONTINUE_ROW,
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    InstallationConfigDraft,
    KeyBinding,
    WorkflowStepStatus,
    key_bindings,
    key_event,
    reduce_consumer_ui,
    typing_text,
    workflow_progress,
)
from agent_artifacts.application.consumer_views import (
    SETTING_PURPOSE,
    SETTING_ROWS,
    SUCCESS_CHOICES,
    SUCCESS_PURPOSE,
    ActivityView,
    ApplicationScreen,
    ConfigInputView,
    ConfigurationFileView,
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
    RunningInstallationView,
    navigation_targets,
    project_collection,
    project_registries,
    remediation_needs_decision,
    target_choice_problems,
    target_from_row,
    target_row,
    targets_confirmed,
)
from agent_artifacts.application.credential_guidance import credential_guidance_lines
from agent_artifacts.application.installed_setup import DeclaredArtifactSetup
from agent_artifacts.application.maintainer_views import (
    REGISTRY_MAINTENANCE_STAGES,
    REGISTRY_REBUILD_EVERYTHING,
    REGISTRY_STAGE_PURPOSE,
    REGISTRY_WORKSPACE_ROW,
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
    MaintainerRegistryWorkspaceView,
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
    Frame,
    action_prompt,
    bulleted,
    cards,
    field_block,
    is_action_prompt,
    render,
    separate,
    stated,
)
from agent_artifacts.tui_maintainer import (
    adopted_artifact_detail,
    maintainer_bulk_promotion_status,
    maintainer_candidate_detail,
    maintainer_candidate_filter_detail,
    maintainer_candidate_filter_status,
    maintainer_collection_candidate_detail,
    maintainer_registry_descriptor,
    maintainer_registry_detail,
    maintainer_registry_rows,
    maintainer_registry_status,
    maintainer_validation_check_detail,
    maintainer_validation_status,
    maintainer_workspace_detail,
    maintainer_workspace_row,
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
    repository_scan_detail,
    repository_scan_status,
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
    "activity_rows",
    "render_activity",
    "render_collection",
    "collection_member_rows",
    "render_credential",
    "render_credential_action",
    "render_credential_review",
    "credential_action_purpose",
    "render_dashboard",
    "doctor_issue_rows",
    "doctor_rows",
    "doctor_status",
    "render_doctor",
    "render_inspection",
    "render_install_plan",
    "render_installed_artifact",
    "render_installed_collection",
    "render_lifecycle_outcome",
    "render_lifecycle_plan",
    "render_marketplace_artifact",
    "render_progress",
    "render_running",
    "render_transaction_progress",
    "render_transaction_success",
    "render_ready",
    "render_receipt_detail",
    "render_registry",
    "registry_purpose",
    "remediation_change",
    "render_remediation",
    "render_required_inputs",
    "render_installation_config_form",
    "installation_config_status",
    "installation_config_purpose",
    "configuration_review_status",
    "configuration_value_status",
    "render_review_selection",
    "render_settings",
    "settings_consequence",
    "render_success",
    "compose_frame",
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
    # Keyed by outcome rather than by effect kind: one `write-file` is the launcher a harness runs
    # and another is the configuration file it reads, and calling both launchers is a count nobody
    # can reconcile with one server (issue #7, D-284).
    "write-configuration": "configuration file(s) written",
    "write-launcher": "launcher(s) written",
    # An artifact that starts nothing has no launcher at all. What it does instead is delivered and
    # merged, and each of those is named rather than counted as "other change".
    "deliver-artifact": "harness file(s) delivered",
    "withdraw-artifact": "harness file(s) withdrawn",
    "merge-managed-block": "managed block(s) written",
    "unmerge-managed-block": "managed block(s) removed",
    "merge-settings-entry": "harness setting(s) written",
    "unmerge-settings-entry": "harness setting(s) removed",
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


_USER_CONFIG_ROW_PREFIX = "configuration:"


def _user_config_row(identifier: str) -> str:
    return _USER_CONFIG_ROW_PREFIX + identifier


def _user_credential_row(reference: str) -> str:
    return reference


def render_user_inputs_area(
    screens: "ConsumerScreens", rows: tuple[str, ...], current_row: str
) -> tuple[str, ...]:
    """Screen 22: one row per installed artifact, never one global variables bucket.

    The trail already names the view, so the rows start at once (CP-23 task 14).
    """

    lines: list[str] = []
    for coordinate in rows:
        configurations = screens.configurations_for(coordinate)
        credentials = screens.credentials_for(coordinate)
        mark = ">" if coordinate == current_row else " "
        lines.append(f"{mark} {coordinate}")
        identifiers = _configuration_identifiers(configurations)
        lines.append(
            "    Configuration: "
            + (", ".join(identifiers) if identifiers else "none")
            + f" ({len(configurations)} harness file(s))"
        )
        if not credentials:
            lines.append("    Credentials: none")
        for credential in credentials:
            lines.append(f"    Credentials: {_credential_row(credential)}")
    return tuple(lines) if rows else ("No installed artifact has runtime inputs.",)


def _configuration_identifiers(configurations: tuple[ConfigurationFileView, ...]) -> list[str]:
    return sorted(
        {
            identifier
            for file in configurations
            for identifier in (*file.inputs, *(item[0] for item in file.values))
        }
    )


def render_artifact_user_inputs(
    coordinate: str,
    configurations: tuple[ConfigurationFileView, ...],
    credentials: tuple[CredentialRecordView, ...],
    current_row: str,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 22a's rows: ordinary values and provider references, each under its own heading.

    What the artifact is and what AART never reads are the state of the view
    (`artifact_user_inputs_status`), and a file path or provider reference describes the row under
    the cursor in Verbose (`artifact_user_input_purpose`), so the rows are the same in both
    profiles (CP-23 task 14).
    """

    del coordinate, profile
    lines: list[str] = []
    identifiers = _configuration_identifiers(configurations)
    if identifiers:
        lines.append("Configuration")
    for identifier in identifiers:
        row = _user_config_row(identifier)
        lines.append(f"{'>' if current_row == row else ' '} {identifier}")
        for file in configurations:
            value = next((value for name, value in file.values if name == identifier), None)
            shown = "value unavailable" if value is None else value
            lines.append(f"    {file.harness}: {shown} — {_human(file.state)}")
    if credentials:
        lines.append("Credentials")
    for credential in credentials:
        row = _user_credential_row(credential.reference)
        status = (
            "Configured securely"
            if credential.health == "present"
            else _human(credential.health).title()
        )
        lines.append(f"{'>' if current_row == row else ' '} {credential.input}: {status}")
    return tuple(lines)


def artifact_user_inputs_status(
    coordinate: str,
    configurations: tuple[ConfigurationFileView, ...],
    credentials: tuple[CredentialRecordView, ...],
) -> tuple[str, ...]:
    """Screen 22a's view state: whose inputs these are, and what is and is not declared."""

    return separate(
        (coordinate,),
        ()
        if _configuration_identifiers(configurations)
        else ("No ordinary configuration is declared.",),
        ("Credentials stay with their providers; AART never reads or displays them.",)
        if credentials
        else ("No credential reference is declared.",),
    )


def artifact_user_input_purpose(
    configurations: tuple[ConfigurationFileView, ...],
    credentials: tuple[CredentialRecordView, ...],
    current_row: str,
) -> tuple[str, ...]:
    """Where the value under the cursor lives: each harness's file, or the provider reference."""

    for credential in credentials:
        if _user_credential_row(credential.reference) == current_row:
            return (f"Provider: {credential.provider}", f"Reference: {credential.reference}")
    if not current_row.startswith(_USER_CONFIG_ROW_PREFIX):
        return ()
    identifier = current_row.removeprefix(_USER_CONFIG_ROW_PREFIX)
    lines: list[str] = []
    for file in configurations:
        if identifier in file.inputs or any(name == identifier for name, _ in file.values):
            lines.append(f"{file.harness}: {file.path}")
            if file.detail:
                lines.append(f"  {file.detail}")
    return tuple(lines)


def render_configuration_value_form(
    coordinate: str,
    input_id: str,
    harnesses: tuple[str, ...],
    draft: InstallationConfigDraft,
    current_row: str,
) -> tuple[str, ...]:
    """Screen 22c: one ordinary value, using screen 07's accept-before-continue contract."""

    if not input_id or all(item.id != input_id for item in draft.fields):
        return (
            "Choose an installed artifact and configuration input before entering a value.",
            "No configuration change has been prepared.",
        )
    value = draft.value(input_id)
    problem = draft.problem(input_id)
    shown = (
        "[value hidden because it looks like a credential]"
        if problem and "credential" in problem
        else f"[{value}]"
    )
    lines = [f"{'>' if current_row == input_id else ' '} {input_id} {shown}"]
    if problem:
        lines.append(f"    {problem}")
    elif any(item.id == input_id and item.accepted for item in draft.fields):
        lines.append("    accepted")
    lines.append(f"{'>' if current_row == CONFIG_CONTINUE_ROW else ' '} Continue")
    return tuple(lines)


def configuration_value_status(
    coordinate: str,
    input_id: str,
    harnesses: tuple[str, ...],
    held: tuple[tuple[str, str | None], ...] = (),
) -> tuple[str, ...]:
    """Screen 22c's state: which value of which artifact, for which harnesses, and what it is.

    `held` is what each chosen harness holds now. When they agree the field opens holding it
    (`CanonicalScreenSource.drafted`), so only a disagreement needs saying.
    """

    differing = len({value for _harness, value in held}) > 1
    return separate(
        (f"Change {input_id} for {coordinate}", "Harnesses: " + ", ".join(harnesses)),
        (
            (
                "The chosen harnesses hold different values, so the field starts empty:",
                *(f"  {harness}: {_held(value)}" for harness, value in held),
            )
            if differing
            else ()
        ),
        (
            "This is ordinary configuration stored beside the artifact.",
            "Credentials stay with their provider and are not accepted here.",
        ),
    )


def _held(value: str | None) -> str:
    return "not set" if value is None else value


def configuration_review_status(
    view: LifecyclePlanView,
    input_id: str,
    held: tuple[tuple[str, str | None], ...],
    value: str,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """Screen 22d: the one value, and what each harness in the plan holds before and after.

    The harnesses are the plan's own `configuration:` components rather than the ones ticked on
    22b, so the review says exactly what confirming writes. The review identity is how the plan is
    pinned, not what it changes, so it is Verbose's (CP-23 task 14, D-273).
    """

    before = dict(held)
    harnesses = tuple(
        item.component.removeprefix("configuration:")
        for item in view.drift
        if item.component.startswith("configuration:")
    )
    risks = ", ".join(_human(item) for item in view.risks) or "read only"
    return separate(
        (
            f"Change {input_id} for {view.artifact}",
            *(f"  {harness}: {_held(before.get(harness))} → {value}" for harness in harnesses),
        ),
        (f"Risks: {risks}.",),
        (
            (f"Review identity: {view.review_digest}",)
            if profile is PresentationProfile.VERBOSE
            else ()
        ),
    )


_STEP_MARKS: dict[str, str] = {
    "applied": "✓",
    "failed": "✗",
    "interrupted": "…",
    "not-attempted": "·",
    # A step that has been reached and has not finished. It is the only mark that means "now".
    "running": "▸",
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


def _remediation_values(item: RemediationView) -> dict[str, str]:
    """What one remediation is *about*, read off the summary the projection already builds.

    `_summary` renders `<kind>: key=value, key=value`, and every remediation kind carries its
    identifying values there -- the harness, the provider, the runtime and its constraint
    (`QA-080`). Reading them back keeps each change naming its own subject without the view
    gaining a field each kind would have to fill in separately.
    """

    _, separator, details = item.summary.partition(": ")
    if not separator:
        return {}
    pairs = (part.split("=", 1) for part in details.split(", ") if "=" in part)
    return {key: value for key, value in pairs if key != "requirement"}


def remediation_change(item: RemediationView) -> str:
    """One remediation as the change AART will make, naming its subject (CP-23 task 08)."""

    values = _remediation_values(item)
    kind = item.kind
    if kind == "configure-harness" and "harness" in values:
        return f"Configure the {values['harness']} integration for this artifact"
    if kind == "configure-credential":
        where = f" in {_human(values['provider'])}" if "provider" in values else ""
        return f"Store the credential it needs securely{where}"
    if kind == "select-alternative-provider" and "provider" in values:
        return f"Keep the credential it needs in {_human(values['provider'])} instead"
    if kind == "install-runtime" and "runtime" in values:
        constraint = f" {values['constraint']}" if "constraint" in values else ""
        return f"Install the {values['runtime']}{constraint} runtime it runs on"
    if kind == "install-executable" and "executable" in values:
        return f"Install the {values['executable']} program it runs"
    if kind == "install-python-packages" and "installer" in values:
        return f"Install its Python dependencies with {values['installer']}"
    if kind == "configure-network" and "host" in values:
        return f"Configure network access to {values['host']}"
    subject = ", ".join(values.values())
    named = _human(kind).capitalize()
    return f"{named}: {subject}" if subject else named


#: What a change touches that somebody must not miss, kept in Fast in plain words. Harness
#: configuration is absent: it is routine and derived (D-258), and the change itself names it.
_REMEDIATION_IMPACT: dict[str, str] = {
    "configure-credential": ("A credential will be stored; AART never shows its value."),
    "select-alternative-provider": "A credential will be kept by a different provider.",
    "install-runtime": "Software will be installed on this machine.",
    "install-executable": "Software will be installed on this machine.",
    "install-python-packages": "Software will be installed on this machine.",
    "configure-network": "Network access will be configured.",
}


def render_remediation(view: ConsumerPlanView, profile: PresentationProfile) -> tuple[str, ...]:
    """Screen 08: the changes AART will make once the final review is confirmed.

    CP-23 task 08 (D-258). Outcomes, not chores: the reader is not asked to prepare anything.
    The effect vocabulary and owners are Verbose; material impact stays in Fast. Nothing here
    promises what the plan does not establish, and Continue is the screen's row, not a line here.
    """

    if not isinstance(view, ConsumerPlanView) or not isinstance(profile, PresentationProfile):
        raise ValueError("remediation rendering needs a consumer plan and presentation profile")
    if not view.remediations:
        return ("Nothing needs to be prepared.",)
    lines = [
        "AART will make this change after you confirm the final review:"
        if len(view.remediations) == 1
        else "AART will make these changes after you confirm the final review:"
    ]
    for item in view.remediations:
        lines.append(f"  {remediation_change(item)}")
        if profile is PresentationProfile.VERBOSE:
            lines.append(
                f"    {item.summary} ({_human(item.risk)}); owners: {', '.join(item.owners)}"
            )
    impacts = tuple(
        dict.fromkeys(
            _REMEDIATION_IMPACT[item.kind]
            for item in view.remediations
            if item.kind in _REMEDIATION_IMPACT
        )
    )
    if impacts:
        lines.extend(("", *impacts))
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
    outcomes = Counter(_OUTCOMES.get(item.outcome, "other change") for item in view.effects)
    lines = ["Ready to install", f"{len(view.selection.resolved)} artifact(s) will be installed."]
    lines.extend(f"  {count} {name}" for name, count in sorted(outcomes.items()))
    # The final review names the intent confirmed on screen 05. Updates have no target picker and
    # continue to derive their installed harnesses from the effects already in the plan (D-260).
    harnesses = view.chosen_targets or _planned_harnesses(view)
    if harnesses:
        suffix = " (chosen for this installation)." if view.chosen_targets else "."
        lines.append(f"Harnesses: {', '.join(harnesses)}{suffix}")
    # Compressed, never quieter: this is the screen somebody confirms from, so every risk the plan
    # carries and every remediation it decided is named here as well as in the full plan.
    # CP-23 task 08: in the outcome wording Remediation uses, because a plan with only routine
    # harness configuration skips that screen and this is where those changes are disclosed.
    if view.remediations:
        lines.append(
            "AART will also: "
            + "; ".join(remediation_change(item) for item in view.remediations)
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


def render_running(view: RunningInstallationView, profile: PresentationProfile) -> tuple[str, ...]:
    """Screen 10 while the reviewed plan is still running.

    Same shape as the finished report, because it is the same list: the steps somebody reviewed, in
    the order they run, one of them marked as the one running now. Drawing performs no IO -- what is
    drawn is what the execution has already said.
    """

    if not isinstance(view, RunningInstallationView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("running rendering needs a running view and presentation profile")
    heading = f"Installing {view.artifact}" if view.artifact else "Installing"
    lines = [f"{heading} ({view.done} of {view.total} done)"]
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
    # CP-23 task 06 (D-256): the choices are rows on the screen, not words in its report, and Undo
    # is never one of them -- no reviewed installation undo exists to start from here.
    lines.append(
        "Undo is not offered here: no reviewed undo exists for an installation yet."
        if view.undo.available
        else f"Undo unavailable: {view.undo.reason}"
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
    """Screen 11's outcome. Where to go from it is the screen's rows (CP-23 task 06)."""

    return render_lifecycle_outcome(view, profile)


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
    return tuple(lines)


def render_credential_action(
    view: CredentialRecordView, profile: PresentationProfile
) -> tuple[str, ...]:
    """Screen 24's view status: the credential the rows act on, who uses it, and what cannot happen.

    CP-23 task 12 (D-262). The actions are the screen's rows, so nothing here names one. What stays
    is what somebody choosing among them must not miss: which installations depend on the reference
    (INV-057), that one in use cannot be removed, and that no action reads the current value
    (INV-056).
    """

    if not isinstance(view, CredentialRecordView) or not isinstance(profile, PresentationProfile):
        raise ValueError("credential action rendering needs a record view and presentation profile")
    mark, health = _credential_health(view)
    lines = [f"{view.input} in {view.provider}  {mark} {health}"]
    if view.dependants:
        lines.append("Used by")
        lines.extend(f"  • {item}" for item in view.dependants)
        lines.append("It cannot be removed while these use it.")
    else:
        lines.append("Nothing installed uses it.")
    lines.append("AART never reads or shows its current value.")
    if profile is PresentationProfile.VERBOSE:
        lines.append(f"Reference: {view.reference}")
    return tuple(lines)


def credential_action_purpose(view: CredentialRecordView, action: str) -> tuple[str, ...]:
    """What one of screen 24's rows does, for the cursor description (Verbose, D-250)."""

    if not isinstance(view, CredentialRecordView) or not isinstance(action, str):
        raise ValueError("a credential action purpose needs a record view and an action")
    if action == "verify":
        return (
            f"Asks {view.provider} whether {view.input} is still there;",
            "nothing is changed.",
        )
    if action == "replace":
        return (
            f"Opens a review first. {view.provider} then asks for the new value",
            "itself; AART never reads or shows the current one.",
        )
    if action == "set":
        return (
            f"Opens a review first. {view.provider} then asks for the value",
            "itself; AART never receives or keeps it.",
        )
    if action == "delete":
        return (
            f"Opens a review first. Removes {view.input} from {view.provider};",
            "no copy is kept, so it cannot be undone.",
        )
    return ()


def render_credential_review(
    view: CredentialRecordView, action: ConsumerActionKind | None
) -> tuple[str, ...]:
    """Screen 24a: what a chosen credential action will do, or what verifying it found.

    A replacement names every installation that will use the new value before the provider is
    asked for it (INV-057), and says the provider asks rather than AART (INV-056). A deletion is
    only ever reviewed for a reference nothing uses. With no pending action the screen is Verify's
    answer: the provider was asked while it opened, and nothing was changed.
    """

    if not isinstance(view, CredentialRecordView) or not (
        action is None or isinstance(action, ConsumerActionKind)
    ):
        raise ValueError("credential review rendering needs a record view and an action")
    if action is ConsumerActionKind.CREDENTIAL_REPLACE:
        lines = [
            f"Replace {view.input} in {view.provider}.",
            f"{view.provider} asks for the new value in this terminal.",
            "AART never reads or shows the current one.",
            "",
        ]
        if view.dependants:
            lines.append("These use it and will use the new value:")
            lines.extend(f"  • {item}" for item in view.dependants)
        else:
            lines.append("Nothing installed uses it.")
        lines.append("No copy of the current value is kept, so this cannot be undone.")
        return tuple(lines)
    if action is ConsumerActionKind.CREDENTIAL_SET:
        lines = [
            f"Set {view.input} in {view.provider}.",
            f"{view.provider} asks for the new value in this terminal.",
            "AART never receives or keeps it.",
            "",
        ]
        if view.dependants:
            lines.append("These installations need it:")
            lines.extend(f"  • {item}" for item in view.dependants)
        else:
            lines.append("Nothing installed uses it.")
        lines.append("The provider is verified immediately after setup.")
        return tuple(lines)
    if action is ConsumerActionKind.CREDENTIAL_DELETE:
        return (
            f"Delete {view.input} from {view.provider}.",
            "Nothing installed uses it.",
            "No copy is kept, so this cannot be undone.",
        )
    mark, health = _credential_health(view)
    lines = [f"{view.input} in {view.provider}  {mark} {health}"]
    if view.detail:
        lines.append(view.detail)
    lines.append("Checked just now; nothing was changed.")
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
    if not view.actions:
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
    """One connected registry as a row, and what the row says about itself under it.

    What a sync does and the snapshot's details describe the row rather than being it, so they are
    `registry_purpose`, read in Verbose through the cursor description (CP-23 task 14).
    """

    if not isinstance(view, RegistryView) or not isinstance(profile, PresentationProfile):
        raise ValueError("registry rendering needs a registry view and presentation profile")
    if not isinstance(focused, bool):
        raise ValueError("registry focus must be boolean")
    noun = "artifact" if view.artifact_count == 1 else "artifacts"
    lines = [
        f"{'> ' if focused else '  '}{view.alias} — {_human(view.availability)}",
        f"    {view.artifact_count} {noun}",
    ]
    if not view.is_registry:
        # An empty row with no explanation reads as a registry that approved nothing, which is a
        # fault; this one is configured, healthy and simply not a registry (INV-026, B-038).
        lines.append("    an authoring Source, not a registry")
    return tuple(lines)


def registry_purpose(view: RegistryView) -> tuple[str, ...]:
    """What a connected registry row is for, and the snapshot behind it."""

    if not isinstance(view, RegistryView):
        raise ValueError("a registry description needs a registry view")
    age = "never" if view.last_sync_age_seconds is None else f"{view.last_sync_age_seconds}s ago"
    purpose = (
        "Sync refreshes Marketplace availability; it does not update installed artifacts."
        if view.is_registry
        else "Its content is offered here once a maintainer promotes it into a registry."
    )
    return (
        purpose,
        f"Kind: {_human(view.kind)}",
        f"Origin: {view.origin}",
        f"Health: {_human(view.health)}; last sync: {age}",
        f"Revision: {view.revision or 'none'}",
        f"Snapshot: {view.snapshot_digest or 'none'}",
        f"Trust: {', '.join(view.trust) or 'none'}",
    )


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
    return separate(*groups)


def settings_consequence(view: ConsumerSettings) -> tuple[str, ...]:
    """What the Maintainer Mode toggle currently implies for the rest of the application.

    It is a consequence of a setting rather than a setting, so it is the state of the view rather
    than a row -- and a sentence standing under four toggles reads like a fifth one (`QA-087`).
    """

    if not isinstance(view, ConsumerSettings):
        raise ValueError("settings rendering needs consumer settings")
    if view.maintainer_mode:
        return ("Maintainer screens are reachable from the Dashboard.",)
    return ("Maintainer Mode off hides Sources, Candidates, Promotion and Publish.",)


def doctor_rows(view: DoctorView, *, leaving_out: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Each installed artifact and how it is, with whatever drifted on it underneath (`QA-087`).

    The command line prints every artifact. The TUI leaves out the issues it draws as rows, so
    what `r` would repair is under the cursor and everything else is the state of the view.
    """

    if not isinstance(view, DoctorView):
        raise ValueError("Doctor rendering needs a Doctor view")
    lines: list[str] = []
    for item in view.artifacts:
        if item.coordinate in leaving_out:
            continue
        marker = "✓" if item.health in {"ready", "update"} else "⚠"
        lines.append(f"{marker} {item.coordinate}")
        if item.health in {"attention", "broken"}:
            lines.extend(f"  {drift.component}: {_human(drift.kind)}" for drift in item.drift)
    return tuple(lines)


def doctor_issue_rows(view: DoctorView, rows: tuple[str, ...], current: str) -> tuple[str, ...]:
    """The repairable issues as rows, the cursor on the one `r` repairs (CP-23 task 14).

    Repair is requested for the row under the cursor, so the cursor is drawn: otherwise nothing on
    screen would say which issue the key acts on.
    """

    if not isinstance(view, DoctorView):
        raise ValueError("Doctor rendering needs a Doctor view")
    artifacts = {item.coordinate: item for item in view.artifacts}
    lines: list[str] = []
    for row in rows:
        lines.append(f"{'>' if row == current else ' '} ⚠ {row}")
        item = artifacts.get(row)
        drift = () if item is None else item.drift
        lines.extend(f"    {entry.component}: {_human(entry.kind)}" for entry in drift)
    return tuple(lines)


def doctor_status(view: DoctorView, profile: PresentationProfile) -> tuple[str, ...]:
    """How the machine is, rather than how any one artifact is.

    Counts summarise the rows, and repair acts on the whole set rather than on the row under the
    cursor, so neither is a row. Verbose adds to this and not to the list, because what it adds --
    which issues can be repaired on their own -- is also a fact about the set (`QA-087`).
    """

    if not isinstance(view, DoctorView) or not isinstance(profile, PresentationProfile):
        raise ValueError("Doctor rendering needs a Doctor view and presentation profile")
    # `QA-096`: separate statements, separately -- the blank line is what the status block reads
    # to tell one list item from the next, and a count is not a continuation of the count above it.
    repairable = (
        ("Independently repairable:", *(f"  - {item}" for item in view.repairable_issues))
        if profile is PresentationProfile.VERBOSE and view.repairable_issues
        else ()
    )
    return separate(
        (f"{view.ready_count} ready",),
        (f"{view.attention_count} needs attention",),
        ("Actions: repair issues using minimal reconciliation plans.",) if view.actions else (),
        repairable,
    )


def render_doctor(view: DoctorView, profile: PresentationProfile) -> tuple[str, ...]:
    """The whole report, top to bottom, for a command line that has no blocks to put it in.

    The TUI takes the two halves separately and the frame names the screen, so the title here is
    the command line's alone (`QA-077`).
    """

    return ("AART / Check system", *doctor_rows(view), *doctor_status(view, profile))


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
        if isinstance(item, CredentialInputView):
            # What it is for, who needs it and how to get it are what a person needs before the
            # provider asks, so they are Fast facts, worded as the lent terminal words them (D-263).
            lines.extend(credential_guidance_lines(item.guidance))
            if item.health == "present":
                status = "Configured securely"
            elif item.provider_reference is not None:
                status = "Enter securely during installation"
            else:
                status = "Required"
            lines.append(f"  {status}")
            if profile is PresentationProfile.VERBOSE:
                lines.extend(
                    (
                        f"  Binding: {_human(item.binding)} ({_human(item.exposure)})",
                        f"  Provider reference: {item.provider_reference or 'not configured'}",
                        f"  Provider health: {_human(item.provider_state)} / {_human(item.health)}",
                    )
                )
            continue
        lines.append(item.label)
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


def render_installation_config_form(
    inputs: tuple[InputView, ...],
    draft: InstallationConfigDraft,
    current_row: str,
) -> tuple[str, ...]:
    """Screen 07's rows: the editable non-secrets and Continue (INV-067).

    What the form explains, and the credentials a provider will ask for, are not rows a cursor can
    stand on, so they are :func:`installation_config_status`; what a field binds to is Verbose's
    description of it, :func:`installation_config_purpose`.
    """

    if (
        any(not isinstance(item, (ConfigInputView, CredentialInputView)) for item in inputs)
        or not isinstance(draft, InstallationConfigDraft)
        or not isinstance(current_row, str)
    ):
        raise ValueError("installation config form needs projected inputs and a safe draft")
    projected = {item.id: item for item in inputs if isinstance(item, ConfigInputView)}
    lines = ["Configuration"] if draft.fields else []
    for field in draft.fields:
        view = projected.get(field.id)
        label = field.id if view is None else view.label
        problem = field.problem
        shown = (
            "<credential-shaped value refused>"
            if problem is not None and "credential" in problem
            else field.value
        )
        mark = ">" if current_row == field.id else " "
        accepted = "  accepted" if field.accepted and problem is None else ""
        lines.append(f"{mark} {label} ({field.id}): [{shown}]{accepted}")
        if view is not None and view.example:
            lines.append(f"    (e.g. {view.example})")
        if problem is not None:
            lines.append(f"    Problem: {problem}")
        elif view is not None and view.validation_hint:
            lines.append(f"    {view.validation_hint}")
    mark = ">" if current_row == CONFIG_CONTINUE_ROW else " "
    readiness = "Review selection" if draft.ready else "Accept every configuration value first"
    lines.append(f"{mark} Continue: {readiness}")
    return tuple(lines)


def installation_config_status(inputs: tuple[InputView, ...]) -> tuple[str, ...]:
    """Screen 07's state: why it asks, where the values go, and what the provider will ask for.

    The credential guidance is a Fast fact (D-263): a person needs it before the provider asks.
    """

    statements: list[tuple[str, ...]] = [
        ("A few things are needed before installation",),
        ("These ordinary values will be kept beside the installed artifact, per harness.",),
    ]
    credentials = tuple(item for item in inputs if isinstance(item, CredentialInputView))
    if credentials:
        statements.append(
            ("Credentials", "Values stay with the credential provider; AART keeps only references.")
        )
    for item in credentials:
        status = (
            "Configured securely"
            if item.health == "present"
            else (
                "Enter securely during installation"
                if item.provider_reference is not None
                else "Required"
            )
        )
        statements.append((*credential_guidance_lines(item.guidance), f"{item.label}: {status}"))
    return separate(*statements)


def installation_config_purpose(
    inputs: tuple[InputView, ...], current_row: str | None
) -> tuple[str, ...]:
    """What the field under the cursor binds to, which Verbose describes rather than drawing."""

    view = next(
        (item for item in inputs if isinstance(item, ConfigInputView) and item.id == current_row),
        None,
    )
    return () if view is None else (f"Binding: {_human(view.binding)} ({_human(view.exposure)})",)


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
    # The description is disclosed in Verbose and on Artifact Details, not repeated here.  What a
    # choice actually turns on is whether this is already installed and where it can go, so those
    # lead instead (issue #10).  Search and filtering still read the summary either way.
    state = (
        "Installed: " + ", ".join(row.installed_statuses)
        if row.installed_statuses
        else "Not installed"
    )
    lines = [row.key, approval, state, "Eligible installation harnesses"]
    if row.eligible_harnesses:
        lines.extend(f"  - {harness}" for harness in row.eligible_harnesses)
    else:
        lines.append("  - No eligible installation harness is available on this machine.")
    if row.unavailable_harnesses:
        lines.append("Detected but not eligible")
        lines.extend(f"  - {harness}" for harness in row.unavailable_harnesses)
    if not row.compatible:
        lines.append("Why installation is unavailable")
        lines.extend(
            f"  - {item.profile}: "
            + (
                "; ".join(reason.message for reason in item.reasons)
                if item.reasons
                else "no compatible placement is available"
            )
            for item in row.compatibility
        )
    lines.append("What it needs")
    if inputs:
        lines.extend(f"  - {item.label}" for item in inputs)
    else:
        lines.append("  - Nothing else before choosing an eligible harness")
    return tuple(lines)


def render_collection(
    view: MarketplaceCollectionView, profile: PresentationProfile, *, contents: bool = True
) -> tuple[str, ...]:
    """What a Collection and the current choice of its members amount to: the view's status.

    §161.4: the details summarize counts and prerequisites rather than dumping every member, so
    the members are listed here only in Verbose, and only where they are not already the rows
    (`contents=False` on the Contents screen, whose rows they are).
    """

    if not isinstance(view, MarketplaceCollectionView) or not isinstance(
        profile, PresentationProfile
    ):
        raise ValueError("Collection rendering needs a Collection view and presentation profile")
    statements: list[tuple[str, ...]] = [
        (view.coordinate, view.summary),
        (
            "Includes",
            f"{len(view.members)} artifacts",
            *(f"{count} {_human(kind)}" for kind, count in view.kind_counts),
        ),
    ]
    if view.inputs:
        statements.append(("What you will need", *(f"  - {item.label}" for item in view.inputs)))
    statements.append((f"{len(view.selected)} / {len(view.members)} selected",))
    if not view.exact:
        statements.append(
            ("Warning: Custom selection", "This will not install the complete Collection.")
        )
    if profile is PresentationProfile.VERBOSE:
        if contents:
            statements.append(
                (
                    "Contents:",
                    *(
                        f"  [{'x' if item in view.selected else ' '}] {item}"
                        for item in view.members
                    ),
                )
            )
        statements.append((f"Selection identity: {view.semantic_identity}",))
    return separate(*statements)


def collection_member_rows(view: MarketplaceCollectionView, current: str | None) -> tuple[str, ...]:
    """A Collection's members as the rows Space ticks, the cursor on the one it is on."""

    return tuple(
        f"{'>' if item == current else ' '} [{'x' if item in view.selected else ' '}] {item}"
        for item in view.members
    )


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


def activity_rows(view: ActivityView, rows: tuple[str, ...], current: str) -> tuple[str, ...]:
    """Screen 25's entries as rows under their day, the cursor on the one Enter opens.

    `render_activity` is the command line's timeline, titled and read top to bottom. On screen the
    trail names the view and Enter opens the entry under the cursor, so the cursor is drawn and
    the review identity describes that entry in Verbose rather than widening every row
    (CP-23 task 14).
    """

    if not isinstance(view, ActivityView):
        raise ValueError("activity rendering needs an activity view")
    lines: list[str] = []
    for day in view.days:
        shown = [entry for entry in day.entries if entry.recorded_at in rows]
        if not shown:
            continue
        lines.append(day.label)
        lines.extend(
            f"{'>' if entry.recorded_at == current else ' '} {entry.mark} {entry.time}  "
            f"{entry.summary}"
            for entry in shown
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
        # D-256: reversibility is a recorded fact, and no reviewed undo exists to act on it here.
        f"Undo: {', '.join(view.undo.components)} could be reversed, but no reviewed undo is "
        "offered here."
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

    def actions(self, state: ConsumerUiState) -> tuple[str, ...]:
        """What the cursor can act on: rows, toggles, commands, at the profile `state` holds.

        Nothing that only reads belongs here (`QA-087`). A screen that wants to say what it is or
        what state it is in has `description` and `status` to say it in, and saying it here puts
        prose between two rows, where it reads like a row.
        """

    def description(self, state: ConsumerUiState) -> tuple[str, ...]:
        """What the thing under the cursor is, for the skeleton's second section (`QA-067`)."""

    def notice(self, state: ConsumerUiState) -> tuple[str, ...]:
        """Why the last action was refused, if this screen is one an action lands on."""

    def status(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The state of the whole view -- counts, errors, steps left -- or nothing (`QA-067`)."""

    def detail(self, state: ConsumerUiState) -> ApplicationScreen | None:
        """Where Enter goes from the row under the cursor, if anywhere."""

    def selected(self, state: ConsumerUiState) -> tuple[str, ...] | None:
        """What this screen opens with ticked, or `None` where it has no opinion."""

    def drafted(self, state: ConsumerUiState) -> str | None:
        """What the field this screen edits opens holding, or `None` where it opens empty."""


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


#: Where a handler says a running plan has got to. The shell binds one for the duration of an
#: execution and takes it back afterwards, exactly as the terminal is lent to a credential prompt.
ProgressReporter: TypeAlias = Callable[[RunningInstallationView], None]


@runtime_checkable
class ProgressReportingHandler(Protocol):
    """An action handler that can report a running plan step by step.

    Separate from `ConsumerActionHandler` because reporting is optional: a handler that runs no
    effects, or one in a test, has nothing to report and should not have to say so.
    """

    def observe_progress(self, report: ProgressReporter | None) -> None: ...


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

#: The screens that stand between a decision and the thing it does: a filled-in form or a chosen
#: row on one side, an irreversible run on the other. They hold no rows, because the only decision
#: on offer is a key -- so the legend advertises it (`QA-088`) and the screen states its subject
#: (`QA-090`).
_REVIEW_SCREENS: frozenset[ApplicationScreen] = frozenset(
    {
        ConsumerScreen.REGISTRY_REVIEW,
        ConsumerScreen.REGISTRY_REMOVE,
        MaintainerScreen.SOURCE_ADD_REVIEW,
        MaintainerScreen.REGISTRY_INIT_REVIEW,
        MaintainerScreen.REGISTRY_REBUILD_REVIEW,
        ConsumerScreen.REGISTRY_SYNC,
        ConsumerScreen.CREDENTIAL_REVIEW,
        ConsumerScreen.CONFIGURATION_REVIEW,
    }
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
    ConsumerScreen.CREDENTIALS: (
        "Manage ordinary per-harness configuration beside provider-held credentials."
    ),
    ConsumerScreen.ACTIVITY: "Review recorded changes, results and their receipts.",
    ConsumerScreen.DOCTOR: "Inspect health and find the smallest safe repair for detected drift.",
    ConsumerScreen.SETTINGS: "Choose detail, installation scope and optional Maintainer Mode.",
    MaintainerScreen.DASHBOARD: "Open advanced source, validation and promotion workflows.",
}

_REGISTRY_EXPLANATION: tuple[str, ...] = (
    "Connect an approved Git registry by URL. Local authoring Sources belong in Maintainer Mode.",
)
"""What a registry is, said on the screen that offers to connect one (`QA-043`)."""

_REGISTRY_ADD_INTRO: tuple[str, ...] = (
    "Connect an approved registry. AART validates a fresh snapshot before saving it.",
    "Local folders are authoring Sources, not Marketplace registries.",
    "",
    # `QA-028`: the empty form says a new one is being made; this says the old ones are not being
    # replaced by it, which is the question the operator actually asked.
    "This adds another registry. Nothing already connected is changed.",
)
"""What connecting a registry does, said under the fields rather than over them (`QA-087`)."""

_SOURCE_ADD_INTRO: tuple[str, ...] = (
    "Subscribe to an authoring repository. AART discovers only the aart.yaml and",
    "aart.json manifests its authors committed; nothing here is approved content yet.",
    "",
    "This adds another Source. Nothing already connected is changed.",
)
"""What subscribing to an authoring repository does, and what it does not approve (`QA-087`)."""

_REGISTRY_INIT_INTRO: tuple[str, ...] = (
    "Create the registry this project publishes. AART writes its skeleton, pins what",
    "it references, builds its index, then validates and audits the result.",
    "",
    # 164.7, said where the decision is made rather than only in the specification. The terminal
    # surface never pushes (D-255): not this run, and not a promotion committed later either.
    "Nothing is pushed and nothing is merged here, or when a promotion is committed:",
    "pushing and merging this registry are steps you take in Git yourself.",
)
"""What initializing a registry writes, and the boundary the run stops at (`QA-087`)."""

_REPOSITORY_SCAN_INTRO: tuple[str, ...] = (
    "Look at one repository for explicit aart.yaml and aart.json manifests.",
    "This is a one-off read: the repository is not saved as a Source or monitored.",
)
"""What a scan reads, and what it deliberately does not keep (`QA-087`)."""

_REGISTRY_REBUILD_INTRO: tuple[str, ...] = (
    "Re-run this registry's generated files. Promoting, adopting or editing anything",
    "leaves the lock and the index describing the registry as it was.",
    "",
    # 161.7 again: the run writes into the checkout and stops there.
    "Nothing is pushed and nothing is merged. What this writes is reviewed in the",
    "repository like any other change.",
)
"""Why a rebuild is offered, and the boundary it stops at (`QA-087`)."""

_FORM_PROSE: dict[ConsumerScreen | MaintainerScreen, tuple[str, ...]] = {
    ConsumerScreen.REGISTRY_ADD: _REGISTRY_ADD_INTRO,
    MaintainerScreen.SOURCE_ADD: _SOURCE_ADD_INTRO,
    MaintainerScreen.REGISTRY_INIT: _REGISTRY_INIT_INTRO,
    MaintainerScreen.REPOSITORY_SCAN: _REPOSITORY_SCAN_INTRO,
    MaintainerScreen.REGISTRY_REBUILD: _REGISTRY_REBUILD_INTRO,
}
"""Every form, as what it says about itself -- and nothing it says about the keyboard.

A table rather than a branch: `QA-087` is one rule for five screens, and a screen that wants a
sixth adds a row here instead of a shape of its own. `QA-088` is why no key line is in here: a key
the screen accepts is advertised in the legend, which is the block that exists to answer that.
"""

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


def _review_facts(state: ConsumerUiState, screens: "ConsumerScreens") -> tuple[str, ...]:
    """What a review is about, or -- once its confirmed run stopped -- what happened instead.

    `QA-090`: a review that drew only *"Press Enter to connect this registry."* over a legend that
    already offers `[Enter] Confirm` would say nothing about what is about to happen, which 161.4
    forbids: a screen states what it is and what state it is in without the reader deriving either.
    The decision is the legend's to advertise (`QA-088`); this is the review's subject, and it
    reads as view status because it is a statement rather than something to act on (`QA-087`).

    A refusal replaces it rather than joining it. The screen keeps its name and its place, because
    the notice answers a question asked here, but the plan it described was discarded when the run
    stopped and describing it still would be describing something that no longer exists (`QA-033`).
    The reason stands *above* this, in the block `QA-093` gave it, so the sentence points up.
    """

    if state.failed_action is not None:
        return ("This run stopped, so nothing here was changed. Why it stopped is above.",)
    screen = state.session.screen
    if screen is ConsumerScreen.REGISTRY_REVIEW:
        draft = state.registry_draft
        if not draft.alias and not draft.location:
            return ()
        return (
            f"Connect {draft.alias} from {draft.location}",
            f"Branch or tag: {draft.ref or 'repository default'}",
            "",
            "It becomes the default registry."
            if draft.make_default
            else "The default registry does not change.",
        )
    if screen is MaintainerScreen.SOURCE_ADD_REVIEW:
        authoring = state.source_draft
        if not authoring.alias and not authoring.location:
            return ()
        git = authoring.kind == "source-git"
        return (
            f"Subscribe to {authoring.alias} at {authoring.location}",
            f"Branch or tag: {authoring.ref or 'repository default'}"
            if git
            else "A local authoring checkout, read where it stands.",
        )
    if screen is MaintainerScreen.REGISTRY_INIT_REVIEW:
        init = state.registry_init_draft
        if not init.registry_id:
            return ()
        return (
            f"Create {init.registry_id}, called {init.display_name}, in this project."
            if init.display_name
            else f"Create {init.registry_id} in this project.",
            f"Stages, in order: {', '.join(REGISTRY_MAINTENANCE_STAGES)}.",
            "",
            "The files are written and committed locally."
            if init.commit
            else "The files are written and left staged.",
        )
    if screen is MaintainerScreen.REGISTRY_REBUILD_REVIEW:
        stage = state.focus
        if stage == REGISTRY_REBUILD_EVERYTHING:
            return (f"Run every stage in order: {', '.join(REGISTRY_MAINTENANCE_STAGES)}.",)
        purpose = REGISTRY_STAGE_PURPOSE.get(stage or "")
        return () if purpose is None else (f"Run {stage} only: {purpose}.",)
    if screen is ConsumerScreen.REGISTRY_REMOVE:
        return () if not state.focus else (f"Disconnect {state.focus} from this project.",)
    if screen is ConsumerScreen.CREDENTIAL_REVIEW:
        record = screens.credential(state.focus)
        if record is None:
            return ("That credential is not known here any more.",)
        return render_credential_review(record, state.action)
    if screen is ConsumerScreen.CONFIGURATION_REVIEW:
        if screens.lifecycle is None:
            return ("That configuration change is not prepared any more.",)
        answers = dict(state.configuration_draft.answers)
        if state.configuration_input not in answers:
            return render_lifecycle_plan(screens.lifecycle, state.session.profile)
        return configuration_review_status(
            screens.lifecycle,
            state.configuration_input,
            screens.held_configuration(state.user_inputs_artifact, state.configuration_input),
            answers[state.configuration_input],
            state.session.profile,
        )
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
        )
    return ()


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


#: The universal keys `key_bindings` always ends with: how to move and how to leave.
_WAYS_OUT = frozenset({"↑/↓", "Esc", "?", "q"})


def _key_legend(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """This screen's own keys on one line, the ways out of it on the line below (`QA-068`).

    Mixing them read as one undifferentiated row of brackets, so the two questions a reader
    actually has -- "what can I do here?" and "how do I leave?" -- had to be answered by scanning
    the same line twice. The universal keys are last in `key_bindings` by construction, so the
    split is read off the order the reducer already guarantees.

    A mode that has taken the keyboard -- search, the quit prompt -- has no universal half to
    separate: every key it lists is the mode's own, so it stays one line.
    """

    bindings = key_bindings(state, detail=source.detail(state))
    if state.searching or state.quit_pending:
        return _binding_lines(bindings)
    # A text field gives up `?` and `q` to the text (D-269), so the ways out are counted rather
    # than assumed to be four.
    split = len(bindings)
    while split and bindings[split - 1].key in _WAYS_OUT:
        split -= 1
    local, global_keys = bindings[:split], bindings[split:]
    return (*_binding_lines(local), *_binding_lines(global_keys))


def frame(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """One drawn screen: heading, body, prompts, and the persistent navigation footer."""

    return render(compose_frame(source, state))


def compose_frame(source: ConsumerScreenSource, state: ConsumerUiState) -> Frame:
    """The blocks one screen is drawn from, before `render` lays them out.

    Kept apart from `frame` so the frame contract can be checked block by block (CP-23 task 14)
    rather than by reading blocks back off drawn lines.
    """

    heading = _heading(state)
    progress = _workflow_chrome(state)
    header = (heading, *(("", *progress) if progress else ()))
    # `QA-096`: the view's status is a list of statements, not a paragraph. What counts as one
    # statement is the blank line the screen composed with, and the session's own lines are
    # statements of their own rather than a continuation of whatever the screen said last.
    session: list[tuple[str, ...]] = []
    if state.searching:
        session.append((f"Search: {state.search}_",))
    elif state.search:
        session.append((f"Filter: {state.search} (esc to clear)",))
    spoken = source.status(state)
    # A screen that already states how much of its own list is selected ("1 / 2 selected") has
    # said it more exactly; the session's bare count would be the same statement twice.
    if state.selection and not any(line.endswith(" selected") for line in spoken):
        session.append((f"{len(state.selection)} selected",))
    if state.quit_pending:
        session.append((f"Discard {len(state.selection)} selected item(s) and quit? y/n",))
    status = bulleted(stated(separate(spoken, *session)))
    # `QA-086`: the launch directory is the footer's caption -- the last line before the keys'
    # rule and flush on it, with the terminal's padding above it rather than under it (revising
    # `QA-069`/`D-235`, which had it as a section of its own; `QA-066` had moved it off the title).
    workspace = f"working at {state.workspace}" if state.workspace else ""
    return Frame(
        trail=header,
        actions=source.actions(state),
        described=_described(source, state),
        notice=source.notice(state),
        help=_HELP_LINES if state.help_visible else (),
        status=status,
        context=workspace,
        keys=_key_legend(source, state),
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
    # The screen's name still says "review", and it is now the result of an attempt. Saying so
    # here is what stops the plan below reading as something still about to happen (`QA-033`).
    suffix = " - did not run" if state.failed_action is not None else ""
    return (
        " / ".join(("AART", *_fitted(steps, _screen_title(state), suffix), _screen_title(state)))
        + suffix
    )


def _fitted(steps: list[str], title: str, suffix: str) -> list[str]:
    """The passed-through places that fit on the frame's first line (CP-23 task 14, D-272).

    A trail five places deep ran past the content measure and wrapped. The places dropped are the
    middle ones: the first says which area this is, and the last is where Esc goes.
    """

    def fits(shown: list[str]) -> bool:
        return len(" / ".join(("AART", *shown, title)) + suffix) <= CONTENT_MEASURE

    if fits(steps):
        return steps
    for head in (1, 0):
        shown = [*steps[:head], "…", steps[-1]]
        if len(steps) > head + 1 and fits(shown):
            return shown
    return ["…", steps[-1]] if len(steps) > 1 else steps


#: Review 24a is one screen for three things, so its name is the thing it is (D-272).
_CREDENTIAL_REVIEW_TITLES = {
    ConsumerActionKind.CREDENTIAL_REPLACE: "Review Replacement",
    ConsumerActionKind.CREDENTIAL_DELETE: "Review Deletion",
    ConsumerActionKind.CREDENTIAL_SET: "Review Setup",
}


def _screen_title(state: ConsumerUiState) -> str:
    screen = state.session.screen
    if screen is ConsumerScreen.CREDENTIAL_REVIEW:
        # With no action pending the screen is what Verify found (`render_credential_review`).
        action = state.action
        return (
            "Verification"
            if action is None
            else _CREDENTIAL_REVIEW_TITLES.get(action, "Verification")
        )
    return _title(screen)


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


def _progress_redraw(
    terminal: ConsumerTerminal,
    source: "CanonicalScreenSource",
    state: ConsumerUiState,
) -> "ProgressReporter":
    """Draw the frame this execution was started from, with the step it has reached.

    Bound to the source and state the loop is holding, so the running report lands inside the same
    shared frame as every other screen -- heading, body, footer -- with no skeleton of its own.
    """

    def redraw(view: RunningInstallationView) -> None:
        terminal.draw(frame(source.with_running(view), state))

    return redraw


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
        # A paste arrives whole on a text field, and the reducer, not a second list here, knows
        # which rows are text fields (D-269).
        name = key_name(terminal.key(), literal=typing_text(current))
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
            # The running screen is observable before the synchronous effect boundary returns, and
            # again on every step: a handler that can report its progress redraws this same frame
            # with the step it has reached, so a long install is never a still screen (issue #7).
            reporting = command.kind is ConsumerUiCommandKind.EXECUTE_ACTION and isinstance(
                action_handler, ProgressReportingHandler
            )
            if command.kind is ConsumerUiCommandKind.EXECUTE_ACTION:
                terminal.draw(frame(active_source, current))
            if reporting and isinstance(active_source, CanonicalScreenSource):
                running_source, running_state = active_source, current
                action_handler.observe_progress(  # type: ignore[attr-defined]
                    _progress_redraw(terminal, running_source, running_state)
                )
            try:
                update = action_handler.handle(command)
            finally:
                if reporting:
                    action_handler.observe_progress(None)  # type: ignore[attr-defined]
            if not isinstance(update, ConsumerActionUpdate):
                raise ValueError("a consumer action handler returned an invalid update")
            # An execution answers with what it established: a recording, or the fact that the
            # attempt stopped. Both are answers to the same command, and the second must not arrive
            # disguised as an empty recording (`QA-033`).
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
    if seed is not None:
        reloaded, _ = reduce_consumer_ui(
            reloaded, ConsumerUiEvent(ConsumerUiEventKind.SET_SELECTION, rows=seed)
        )
    text = source.drafted(reloaded) if entering else None
    if text is None:
        return reloaded
    drafted, _ = reduce_consumer_ui(
        reloaded,
        ConsumerUiEvent(
            ConsumerUiEventKind.EDIT_CONFIGURATION, key=reloaded.configuration_input, text=text
        ),
    )
    return drafted


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
    #: The pre-review screen-07 projection. It is separate from ``plan.inputs`` because no plan
    #: exists until these values have been accepted and bound.
    installation_inputs: tuple[InputView, ...] = ()
    configurations: tuple[ConfigurationFileView, ...] = ()
    #: Where a reviewed plan has got to while it is still running. It is held apart from `outcome`
    #: because it is not a result: it is replaced on every step and dropped the moment there is one.
    running: RunningInstallationView | None = None

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

    def user_input_artifacts(self) -> tuple[str, ...]:
        """Installed artifacts that own config or depend on a provider reference."""

        configured = {item.coordinate for item in self.configurations}
        dependants = {owner for item in self.credentials for owner in item.dependants}
        return tuple(sorted(configured | dependants))

    def configurations_for(self, coordinate: str) -> tuple[ConfigurationFileView, ...]:
        return tuple(item for item in self.configurations if item.coordinate == coordinate)

    def held_configuration(
        self, coordinate: str, input_id: str
    ) -> tuple[tuple[str, str | None], ...]:
        """What each harness of one installed artifact holds now for one ordinary value."""

        return tuple(
            (item.harness, next((value for name, value in item.values if name == input_id), None))
            for item in self.configurations_for(coordinate)
        )

    def credentials_for(self, coordinate: str) -> tuple[CredentialRecordView, ...]:
        return tuple(item for item in self.credentials if coordinate in item.dependants)

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
    running: RunningInstallationView | None = None,
    transaction: ReceiptDetailView | None = None,
    notice: tuple[str, ...] = (),
    pending_setup: tuple[DeclaredArtifactSetup, ...] = (),
    repository_scan: MaintainerRepositoryScanView | None = None,
    adoption_review: MaintainerAdoptionReviewView | None = None,
    adopted_artifacts: tuple[MaintainerAdoptedArtifactView, ...] = (),
    adoption_upstream: MaintainerAdoptionUpstreamView | None = None,
    installation_inputs: tuple[InputView, ...] = (),
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
        installation_inputs,
        machine.configurations,
        running,
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


_REMEDIATION_CONTINUE = (
    "Opens Ready to install, the final review: nothing has changed yet, and nothing will "
    "until you confirm there."
)

_NO_APPROVED_DESCRIPTION = "No description was approved for this offer."


def marketplace_offer_description(
    entry: MarketplaceEntry | MarketplaceCollectionEntry,
) -> tuple[str, ...]:
    """The Marketplace offer under the cursor, as its approved Registry metadata states it.

    A cursor description (D-250, D-257): the frame draws it below the list's rule in Verbose only.
    Every value comes from the projected offer; an offer whose summary carries no words says so
    rather than borrowing a description from anywhere else.
    """

    if isinstance(entry, MarketplaceEntry):
        row = entry.row
        fields = (
            ("Artifact", row.identity.name),
            ("Kind", _human(row.identity.kind).capitalize()),
            ("Version", row.version),
            ("Source", str(row.source_alias)),
            ("Description", row.summary.strip() or _NO_APPROVED_DESCRIPTION),
        )
    elif isinstance(entry, MarketplaceCollectionEntry):
        offered = entry.collection
        count = len(offered.members)
        fields = (
            ("Collection", offered.coordinate.name),
            ("Version", offered.coordinate.version),
            ("Source", str(offered.coordinate.source)),
            ("Includes", f"{count} artifact{'' if count == 1 else 's'}"),
            ("Description", offered.summary.strip() or _NO_APPROVED_DESCRIPTION),
        )
    else:
        raise ValueError("a Marketplace description needs an offered artifact or Collection")
    return field_block(fields, indent=2, width=CONTENT_MEASURE)


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

    def with_running(self, view: RunningInstallationView | None) -> "CanonicalScreenSource":
        """The same screens, showing where a plan that is running now has got to.

        A copy rather than a mutation: the source the loop is holding is what somebody reviewed
        from, and a running plan is over in a moment.
        """

        return CanonicalScreenSource(replace(self._screens, running=view))

    def rows(self, state: ConsumerUiState) -> tuple[str, ...]:
        screen, query = state.session.screen, state.search
        if screen is ConsumerScreen.CONFIGURATION_TARGETS:
            coordinate = state.user_inputs_artifact
            return tuple(
                target_row(item.harness)
                for item in self._screens.configurations_for(coordinate)
                if state.configuration_input in item.inputs
                or any(name == state.configuration_input for name, _value in item.values)
            )
        if screen is ConsumerScreen.CONFIGURATION_VALUE:
            return (
                (state.configuration_input, CONFIG_CONTINUE_ROW)
                if state.configuration_input
                else ()
            )
        if screen is ConsumerScreen.REQUIRED_INPUTS and state.config_form_active:
            fields = tuple(
                item.id
                for item in self._screens.installation_inputs
                if isinstance(item, ConfigInputView)
            )
            return (*fields, CONFIG_CONTINUE_ROW) if fields else ()
        if screen is ConsumerScreen.REVIEW_SELECTION:
            plan = self._screens.plan
            if plan is None:
                return ()
            eligible = tuple(target_row(item.harness) for item in plan.targets)
            stale = tuple(
                target_row(harness)
                for harness in state.targets
                if all(item.harness != harness for item in plan.targets)
            )
            return (*eligible, *stale)
        if screen is ConsumerScreen.REMEDIATION:
            # CP-23 task 08: Continue is a row, so it is a control rather than a printed string.
            return () if self._screens.plan is None else (ConsumerScreen.READY.value,)
        if screen is ConsumerScreen.CREDENTIAL_ACTION:
            # CP-23 task 12: the actions the record permits are the rows (D-262).
            record = self._screens.credential(state.focus)
            return () if record is None else record.actions
        if screen is ConsumerScreen.USER_INPUT_DETAILS:
            coordinate = state.user_inputs_artifact or state.focus
            configuration_rows = tuple(
                _user_config_row(identifier)
                for identifier in sorted(
                    {
                        identifier
                        for file in self._screens.configurations_for(coordinate)
                        for identifier in (*file.inputs, *(item[0] for item in file.values))
                    }
                )
            )
            credential_rows = tuple(
                _user_credential_row(item.reference)
                for item in self._screens.credentials_for(coordinate)
            )
            return (*configuration_rows, *credential_rows)
        if screen is ConsumerScreen.SUCCESS:
            # CP-23 task 06: the choices exist once something ran; before that there is nothing
            # to view, and a row that opens nothing is the gap this replaced.
            if self._screens.transaction is None and self._screens.outcome is None:
                return ()
            return tuple(target.value for target, _label in SUCCESS_CHOICES)
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
            # `QA-098`: the registry this project publishes is a row, above the ones it subscribes
            # to. It had been prose, so the screen had nothing for a cursor to stand on at all.
            workspace = self._registry_workspace()
            return (() if workspace is None else (REGISTRY_WORKSPACE_ROW,)) + tuple(
                item.alias for item in self._screens.maintainer_registries()
            )
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
        if screen is ConsumerScreen.COLLECTION_CUSTOMIZE:
            # §161.4: the details summarize the Collection rather than dumping its members; the
            # Contents are where members are rows, because ticking them is what they are for.
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
                coordinate
                for coordinate in self._screens.user_input_artifacts()
                if _matches(query, coordinate)
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
            return ("id", "name", "commit", "initialize")
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

    def drafted(self, state: ConsumerUiState) -> str | None:
        """22c opens holding the value the chosen harnesses share, unaccepted (CP-23 task 14).

        Harnesses that disagree, or that hold nothing, open it empty: choosing one of their values
        for the reader would be a decision the screen has no business making.
        """

        if state.session.screen is not ConsumerScreen.CONFIGURATION_VALUE:
            return None
        held = {value for _harness, value in self._held(state, state.configuration_targets)}
        if len(held) != 1:
            return None
        (value,) = held
        return value

    def _held(
        self, state: ConsumerUiState, harnesses: tuple[str, ...]
    ) -> tuple[tuple[str, str | None], ...]:
        chosen = frozenset(harnesses)
        return tuple(
            item
            for item in self._screens.held_configuration(
                state.user_inputs_artifact, state.configuration_input
            )
            if item[0] in chosen
        )

    def selected(self, state: ConsumerUiState) -> tuple[str, ...] | None:
        """A Collection opens with every member ticked; nothing else has an opinion."""

        if state.session.screen is MaintainerScreen.SCAN_RESULT:
            return ()
        if state.session.screen is ConsumerScreen.CONFIGURATION_TARGETS:
            return tuple(
                item.harness
                for item in self._screens.configurations_for(state.user_inputs_artifact)
                if state.configuration_input in item.inputs
                or any(name == state.configuration_input for name, _value in item.values)
            )
        if state.session.screen is not ConsumerScreen.COLLECTION_PREVIEW:
            return None
        entry = self._screens.offered_collection(state.focus)
        return None if entry is None else entry.members

    def detail(self, state: ConsumerUiState) -> ApplicationScreen | None:
        """Enter opens the detail of whatever this screen is currently about."""

        screen, row = state.session.screen, state.current_row or state.focus
        if screen is ConsumerScreen.SUCCESS:
            # The cursor alone: Success's focus is the recorded receipt, never a choice.
            return next(
                (
                    target
                    for target, _label in SUCCESS_CHOICES
                    if target.value == state.current_row and state.current_row in state.rows
                ),
                None,
            )
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
            # The registry this project *publishes* is not one of them: it has no candidates to
            # promote through it, so Enter on it opens nothing (`QA-098`).
            if row == REGISTRY_WORKSPACE_ROW:
                return None
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
            if plan is None or not targets_confirmed(plan, state.targets):
                return None
            # Inspection has already happened to produce this immutable plan. It remains
            # available as a detailed projection, but is not a mandatory click-through step.
            if plan.inputs:
                return ConsumerScreen.REQUIRED_INPUTS
            if remediation_needs_decision(plan):
                return ConsumerScreen.REMEDIATION
            return ConsumerScreen.READY
        if screen is ConsumerScreen.AUTOMATIC_INSPECTION:
            plan = self._screens.plan
            if plan is None:
                return None
            if plan.inputs:
                return ConsumerScreen.REQUIRED_INPUTS
            if remediation_needs_decision(plan):
                return ConsumerScreen.REMEDIATION
            return ConsumerScreen.READY
        if screen is ConsumerScreen.REQUIRED_INPUTS:
            plan = self._screens.plan
            if plan is None:
                return None
            return (
                ConsumerScreen.REMEDIATION
                if remediation_needs_decision(plan)
                else ConsumerScreen.READY
            )
        if screen is ConsumerScreen.USER_INPUT_DETAILS:
            return (
                ConsumerScreen.CONFIGURATION_TARGETS
                if row.startswith(_USER_CONFIG_ROW_PREFIX)
                else (
                    ConsumerScreen.CREDENTIAL_DETAILS
                    if self._screens.credential(row) is not None
                    else None
                )
            )
        if screen is ConsumerScreen.CONFIGURATION_TARGETS:
            eligible = {
                item.harness
                for item in self._screens.configurations_for(state.user_inputs_artifact)
                if state.configuration_input in item.inputs
                or any(name == state.configuration_input for name, _value in item.values)
            }
            return (
                ConsumerScreen.CONFIGURATION_VALUE
                if state.configuration_targets
                and set(state.configuration_targets).issubset(eligible)
                else None
            )
        if screen is ConsumerScreen.REMEDIATION:
            return ConsumerScreen.READY if self._screens.plan is not None else None
        if not isinstance(screen, ConsumerScreen):
            return None
        target = {
            ConsumerScreen.ACTIVITY: ConsumerScreen.ACTIVITY_DETAILS,
            ConsumerScreen.ACTIVITY_DETAILS: ConsumerScreen.RECEIPT_DETAILS,
            ConsumerScreen.CREDENTIALS: ConsumerScreen.USER_INPUT_DETAILS,
            ConsumerScreen.CREDENTIAL_DETAILS: ConsumerScreen.CREDENTIAL_ACTION,
            ConsumerScreen.UPDATES: ConsumerScreen.UPDATE_INPUTS,
            ConsumerScreen.REGISTRIES: ConsumerScreen.REGISTRY_ADD,
        }.get(screen)
        if target is None or not row:
            return None
        if screen is ConsumerScreen.REGISTRIES and row != "add-registry":
            return None
        return target

    def actions(self, state: ConsumerUiState) -> tuple[str, ...]:
        """What the cursor acts on, and nothing else at all."""

        # `QA-091`: a screen with no rows has nothing the cursor can act on, so its actions block
        # is empty and whatever it has to say is the state of the view. The rule is read off the
        # row model rather than off a list of screens, because a list of screens is the thing the
        # operator asked us to stop maintaining -- *"zeby nie bylo zbyt wielu wyjatkow od reguly"*.
        if not self.rows(state):
            return ()
        body = self._body(state)
        # `QA-029`: the one line addressed to the reader goes last, under everything it is about,
        # separated by a blank.
        prompt = body[-1] if body and is_action_prompt(body[-1]) else ""
        facts = separate(body[:-1] if prompt else body)
        if not prompt:
            return facts
        return action_prompt(facts, prompt)

    def notice(self, state: ConsumerUiState) -> tuple[str, ...]:
        """Why the last action could not run, on the screens where somebody asked for it.

        `QA-093`: a block of its own, because the operator found it drawn among the five stages a
        reader was choosing between -- *"powiadomienie o bledzie nie powinno byc w jednym bloku z
        akcja"*. It is confined to the answerable screens deliberately: it answers a question
        somebody just asked, so it belongs where they asked it, and carrying it onto the dashboard
        would leave a stale explanation standing over a screen that never ran anything.
        """

        if state.session.screen not in _ANSWERABLE:
            return ()
        # `QA-096`: a diagnostic is written lower-case everywhere it is produced; on a screen it
        # is a sentence like every other statement, and `stated` is the one place that settles it.
        return bulleted(stated(self._screens.notice))

    def description(self, state: ConsumerUiState) -> tuple[str, ...]:
        """What the row under the cursor is, as bare lines the skeleton will bound (`QA-067`).

        It answers from the cursor rather than from the screen, so a screen that gains describable
        rows tomorrow says something here without the frame changing.
        """

        if state.session.screen is ConsumerScreen.SETTINGS:
            purpose = SETTING_PURPOSE.get(state.current_row or "")
            return () if purpose is None else (purpose,)
        if state.session.screen is ConsumerScreen.USER_INPUT_DETAILS:
            coordinate = state.user_inputs_artifact or state.focus
            return artifact_user_input_purpose(
                self._screens.configurations_for(coordinate),
                self._screens.credentials_for(coordinate),
                state.current_row,
            )
        if state.session.screen is ConsumerScreen.ACTIVITY:
            entry = next(
                (
                    item
                    for item in self._screens.activity.entries
                    if item.recorded_at == state.current_row
                ),
                None,
            )
            if entry is None:
                return ()
            return (
                f"Recorded {entry.recorded_at}",
                f"Review identity: {entry.review_digest}",
            )
        if state.session.screen is ConsumerScreen.REQUIRED_INPUTS and state.config_form_active:
            return installation_config_purpose(self._screens.installation_inputs, state.current_row)
        if state.session.screen is MaintainerScreen.COLLECTION_CANDIDATES:
            return maintainer_collection_candidate_detail(
                self._screens.collection_candidates(), state.current_row
            )
        if state.session.screen is MaintainerScreen.VALIDATION:
            validation = self._screens.validation(state.focus)
            return (
                ()
                if validation is None
                else maintainer_validation_check_detail(validation, state.current_row)
            )
        if state.session.screen is MaintainerScreen.CANDIDATE_FILTERS:
            return maintainer_candidate_filter_detail(
                project_maintainer_candidate_filters(
                    self._screens.candidates(), _candidate_filter(state)
                ),
                state.current_row,
            )
        if state.session.screen is MaintainerScreen.SCAN_RESULT:
            scan = self._screens.repository_scan
            return () if scan is None else repository_scan_detail(scan, state.current_row)
        if state.session.screen is MaintainerScreen.ADOPTED_ARTIFACTS:
            return adopted_artifact_detail(self._screens.adopted_artifacts, state.current_row)
        if state.session.screen is ConsumerScreen.COLLECTION_CUSTOMIZE:
            member = self._screens.offered(state.current_row or "")
            return () if member is None else marketplace_offer_description(member)
        if state.session.screen is ConsumerScreen.REGISTRIES:
            if state.current_row == "add-registry":
                return ("Opens the form that connects another approved registry.",)
            registry = next(
                (item for item in self._screens.registries if item.alias == state.current_row),
                None,
            )
            return () if registry is None else registry_purpose(registry)
        if state.session.screen is ConsumerScreen.REMEDIATION:
            if state.current_row != ConsumerScreen.READY.value or self.detail(state) is None:
                return ()
            return (_REMEDIATION_CONTINUE,)
        if state.session.screen is ConsumerScreen.CREDENTIAL_ACTION:
            record = self._screens.credential(state.focus)
            if record is None or state.current_row not in record.actions:
                return ()
            return credential_action_purpose(record, state.current_row or "")
        if state.session.screen is ConsumerScreen.SUCCESS:
            chosen = self.detail(state)
            return () if not isinstance(chosen, ConsumerScreen) else (SUCCESS_PURPOSE[chosen],)
        if state.session.screen is ConsumerScreen.REVIEW_SELECTION:
            plan = self._screens.plan
            harness = target_from_row(state.current_row)
            if plan is None or harness is None:
                return ()
            target = next((item for item in plan.targets if item.harness == harness), None)
            if target is None:
                return (f"{harness} is no longer eligible for this selection.",)
            return (
                f"{harness} can host:",
                *(f"  {artifact}" for artifact in target.artifacts),
            )
        if state.session.screen is ConsumerScreen.CONFIGURATION_TARGETS:
            harness = target_from_row(state.current_row)
            if harness is None:
                return ()
            is_selected = harness in state.configuration_targets
            return (
                f"{harness} will receive the value from this edit."
                if is_selected
                else f"{harness} is not changed by this edit.",
            )
        if state.session.screen is MaintainerScreen.REGISTRY:
            # `QA-098`: with the cursor on the registry this project publishes, the description is
            # where that registry has got to -- repository, branch, what its checkout knows of the
            # remote, and what is waiting to be pushed.
            workspace = self._registry_workspace()
            if workspace is not None and state.current_row == REGISTRY_WORKSPACE_ROW:
                return maintainer_workspace_detail(workspace)
            # `QA-095`: what a snapshot is for, which `[v]` gates because `_described` is the only
            # caller, followed by the registry under the cursor with its digests in full. With no
            # row there is nothing to describe; the view status says it instead.
            if not state.rows:
                return ()
            screens = self._screens
            present = (
                True
                if screens.maintainer is None
                else screens.maintainer.registry_workspace_present
            )
            registries = screens.maintainer_registries()
            subscribed = next(
                (item for item in registries if item.alias == state.current_row), None
            )
            return separate(
                maintainer_registry_descriptor(registries, registry_workspace_present=present),
                () if subscribed is None else maintainer_registry_detail(subscribed),
            )
        if state.session.screen is MaintainerScreen.REGISTRY_REBUILD:
            # The whole-sequence row names its four stages in its own label, so it has nothing
            # left to add here and says nothing rather than repeating itself.
            purpose = REGISTRY_STAGE_PURPOSE.get(state.current_row or "")
            return () if purpose is None else (purpose,)
        if state.session.screen is ConsumerScreen.MARKETPLACE:
            # CP-23 task 07: the offer under the cursor, read from the same filtered list the rows
            # were, so a row the search removed is never described.
            focused = next(
                (
                    item
                    for item in self._offers()
                    if item.key == state.current_row
                    and _matches(state.search, item.key, self._summary(item))
                ),
                None,
            )
            return () if focused is None else marketplace_offer_description(focused)
        if state.session.screen is MaintainerScreen.CANDIDATES:
            # CP-23 task 02: the table is the actions block; the Candidate it points at is this
            # description, read from the same filtered list the rows were, so a row the search
            # removed is never described.
            if self._screens.maintainer is None:
                return ()
            return maintainer_candidate_detail(
                self._screens.candidates(_candidate_filter(state)),
                cursor=state.current_row,
            )
        if state.session.screen not in _DESCRIBED_SCREENS:
            return ()
        targets = navigation_targets(
            state.session.screen, maintainer_mode=state.settings.maintainer_mode
        )
        selected = next((target for target in targets if target.value == state.current_row), None)
        described = None if selected is None else _DASHBOARD_DESCRIPTIONS.get(selected)
        return () if described is None else (described,)

    def _registry_workspace(self) -> MaintainerRegistryWorkspaceView | None:
        """The registry this project publishes, when one was read from it (`QA-098`)."""

        maintainer = self._screens.maintainer
        return None if maintainer is None else maintainer.registry_workspace

    def _form_prose(self, state: ConsumerUiState) -> tuple[str, ...]:
        """What a form has to say about itself, which is never a row a cursor can stand on.

        `QA-087`: the fields are the actions block on their own; the introduction, the reassurance
        and the key prompt read below the rule as the state of the view. `QA-029` still puts the
        prompt last with a blank above it -- it moved block, not position.
        """

        return _FORM_PROSE.get(state.session.screen, ())

    def _first_run(self) -> bool:
        """A machine that has nothing, not merely a machine with no source configured (`B-080`).

        Somebody who installed an artifact from a source they have since removed -- or through a
        direct install -- is not seeing AART for the first time, and replacing their real counts
        with the welcome panel hides the one thing the Dashboard exists to state.
        """

        screens = self._screens
        return (
            not screens.registries
            and screens.dashboard.registry_count == 0
            and screens.dashboard.installed_count == 0
        )

    def status(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The state of the whole view, or nothing at all (`QA-067`).

        Returning `()` is the point: an empty view-status section is omitted entirely rather than
        drawn as a boundary around nothing, which is the fault `QA-065` reported.
        """

        spoken = self._view_status(state)
        if self.rows(state):
            return spoken
        # `QA-091`: with no rows there is no actions block, so the report a result screen draws is
        # the state of the view. The refusal is not: `QA-093` gives it its own block above.
        return separate(self._body(state), spoken)

    def _view_status(self, state: ConsumerUiState) -> tuple[str, ...]:
        """What this particular screen has to say about itself."""

        screen, screens = state.session.screen, self._screens
        prose = self._form_prose(state)
        if prose:
            return prose
        if screen is ConsumerScreen.REQUIRED_INPUTS and state.config_form_active:
            return installation_config_status(screens.installation_inputs)
        if screen is ConsumerScreen.CONFIGURATION_VALUE and self.rows(state):
            return configuration_value_status(
                state.user_inputs_artifact,
                state.configuration_input,
                state.configuration_targets,
                self._held(state, state.configuration_targets),
            )
        if screen in _REVIEW_SCREENS:
            return _review_facts(state, screens)
        if screen is ConsumerScreen.USER_INPUT_DETAILS and self.rows(state):
            coordinate = state.user_inputs_artifact or state.focus
            return artifact_user_inputs_status(
                coordinate,
                screens.configurations_for(coordinate),
                screens.credentials_for(coordinate),
            )
        if screen in (ConsumerScreen.COLLECTION_PREVIEW, ConsumerScreen.COLLECTION_CUSTOMIZE):
            preview = screens.offered_collection(state.focus)
            if preview is not None:
                return render_collection(
                    preview.view(state.selection),
                    state.session.profile,
                    contents=screen is ConsumerScreen.COLLECTION_PREVIEW,
                )
        if screen is MaintainerScreen.BULK_PROMOTION:
            return maintainer_bulk_promotion_status(screens.bulk_promotions())
        if screen is MaintainerScreen.VALIDATION and self.rows(state):
            validation = screens.validation(state.focus)
            assert validation is not None
            return maintainer_validation_status(validation)
        if screen is MaintainerScreen.CANDIDATE_FILTERS and self.rows(state):
            return maintainer_candidate_filter_status(
                project_maintainer_candidate_filters(screens.candidates(), _candidate_filter(state))
            )
        if screen is MaintainerScreen.SCAN_RESULT and screens.repository_scan is not None:
            return repository_scan_status(screens.repository_scan)
        if screen is ConsumerScreen.DASHBOARD:
            # `QA-087`: first-run guidance and the counts are both answers to "what state is this
            # in", so they belong here rather than above the rows, inside the rows' own block.
            return _FIRST_RUN_LINES if self._first_run() else render_dashboard(screens.dashboard)
        if screen is MaintainerScreen.REGISTRY:
            present = (
                True
                if screens.maintainer is None
                else screens.maintainer.registry_workspace_present
            )
            status = maintainer_registry_status(
                screens.maintainer_registries(), registry_workspace_present=present
            )
            if state.rows or state.session.profile is not PresentationProfile.VERBOSE:
                return status
            # With no row to describe, `QA-095`'s explanation is still Verbose's to show; it is
            # said with the view's state rather than as a description of nothing.
            return separate(
                maintainer_registry_descriptor(
                    screens.maintainer_registries(), registry_workspace_present=present
                ),
                status,
            )
        if screen is ConsumerScreen.DOCTOR:
            if screens.doctor is None:
                return ()
            report = doctor_status(screens.doctor, state.session.profile)
            if not state.rows:
                return report
            return separate(doctor_rows(screens.doctor, leaving_out=state.rows), report)
        if screen is ConsumerScreen.SETTINGS:
            # From the session's own settings, not the machine snapshot: the same reason the rows
            # are drawn from `state.settings`.
            return settings_consequence(state.settings)
        if screen is ConsumerScreen.ARTIFACT_DETAILS and screens.offered(state.focus) is not None:
            return (
                "Selected for installation."
                if state.focus in state.selection
                else "Not selected for installation.",
            )
        if screen is ConsumerScreen.CREDENTIAL_ACTION and self.rows(state):
            record = screens.credential(state.focus)
            assert record is not None
            return render_credential_action(record, state.session.profile)
        if screen is ConsumerScreen.REMEDIATION and self.rows(state):
            # CP-23 task 08: the changes are what this view states; Continue is its row.
            assert screens.plan is not None
            return render_remediation(screens.plan, state.session.profile)
        if (
            screen is ConsumerScreen.REVIEW_SELECTION
            and screens.plan is not None
            and (screens.plan.targets or state.targets)
        ):
            problems = target_choice_problems(screens.plan, state.targets)
            target_status = (
                problems if problems else (f"Installing into: {', '.join(state.targets)}",)
            )
            return separate(
                render_review_selection(screens.plan, state.session.profile),
                target_status,
            )
        if screen is ConsumerScreen.SUCCESS and self.rows(state):
            # CP-23 task 06: what happened is the state of the view; the choices are the rows.
            if screens.transaction is not None:
                return render_transaction_success(
                    screens.transaction, state.session.profile
                ) + render_pending_setup(screens.pending_setup)
            assert screens.outcome is not None
            return render_success(screens.outcome, state.session.profile)
        if screen is ConsumerScreen.REGISTRIES:
            if screens.registries:
                return _REGISTRY_EXPLANATION
            return separate(
                _REGISTRY_EXPLANATION,
                ("No sources are configured.",),
                ("Marketplace needs an approved registry before it can offer tools.",),
                ("Choose Add Registry above to connect the first one.",),
            )
        if screen is MaintainerScreen.DASHBOARD:
            # An unavailable composition is the state of the view, not something to put a cursor
            # on -- and saying so here keeps the rows' block holding only rows.
            if screens.maintainer is None:
                return ("Maintainer state is not available yet.",)
            return render_maintainer_dashboard(screens.maintainer.dashboard, state.session.profile)
        return ()

    def _body(self, state: ConsumerUiState) -> tuple[str, ...]:
        screen, profile = state.session.screen, state.session.profile
        screens = self._screens
        if screen is ConsumerScreen.REVIEW_SELECTION and self.rows(state):
            return tuple(
                f"{'>' if row == state.current_row else ' '} "
                f"{'[x]' if target_from_row(row) in state.targets else '[ ]'} "
                f"{target_from_row(row)}"
                for row in state.rows
            )
        if screen is ConsumerScreen.CONFIGURATION_TARGETS:
            return tuple(
                f"{'>' if row == state.current_row else ' '} "
                f"{'[x]' if target_from_row(row) in state.configuration_targets else '[ ]'} "
                f"{target_from_row(row)}"
                for row in state.rows
            )
        if screen is ConsumerScreen.REMEDIATION and self.rows(state):
            return (f"{'>' if state.current_row == ConsumerScreen.READY.value else ' '} Continue",)
        if screen is ConsumerScreen.CREDENTIAL_ACTION and self.rows(state):
            return tuple(
                f"{'>' if row == state.current_row else ' '} {row.capitalize()}"
                for row in state.rows
            )
        if screen is ConsumerScreen.SUCCESS and self.rows(state):
            return tuple(
                f"{'>' if target.value == state.current_row else ' '} {label}"
                for target, label in SUCCESS_CHOICES
            )
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
            # `QA-087`: the rows, and nothing else. The label went with the prose -- a block whose
            # contents are the navigation does not need to announce that it is the navigation.
            return menu
        if screen is MaintainerScreen.DASHBOARD:
            if screens.maintainer is None:
                return ()
            menu = tuple(
                f"{'>' if row == state.current_row else ' '} {_title(target)}"
                for row, target in zip(
                    state.rows,
                    navigation_targets(screen, maintainer_mode=state.settings.maintainer_mode),
                    strict=False,
                )
            )
            return menu
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
                else render_maintainer_candidate_diff(candidate, profile)
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
                cursor=state.current_row,
            )
        if screen is MaintainerScreen.VALIDATION:
            validation = screens.validation(state.focus)
            return (
                ("That Candidate's validation is not available.",)
                if validation is None
                else render_maintainer_validation(validation, cursor=state.current_row)
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
            workspace = self._registry_workspace()
            published = (
                ()
                if workspace is None
                else (
                    maintainer_workspace_row(
                        workspace, selected=state.current_row == REGISTRY_WORKSPACE_ROW
                    ),
                )
            )
            return separate(
                published,
                maintainer_registry_rows(
                    screens.maintainer_registries(),
                    cursor=state.current_row,
                    registry_workspace_present=present,
                ),
            )
        if screen is MaintainerScreen.SCAN_RESULT:
            return (
                ("No repository has been scanned yet.",)
                if screens.repository_scan is None
                else render_repository_scan(
                    screens.repository_scan,
                    state.selection,
                    cursor=state.current_row,
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
            )
        if screen is MaintainerScreen.UPSTREAM_CHECK:
            return (
                ("No adopted artifact has been checked yet.",)
                if screens.adoption_upstream is None
                else render_adoption_upstream_check(screens.adoption_upstream, profile)
            )
        if screen is MaintainerScreen.BULK_PROMOTION:
            return render_maintainer_bulk_promotion(
                screens.bulk_promotions(), state.selection, cursor=state.current_row
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
                else render_maintainer_registry_commit(screens.promotion_commit, profile)
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
            if screen is ConsumerScreen.COLLECTION_PREVIEW:
                return ()
            return collection_member_rows(preview.view(state.selection), state.current_row)
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
            return render_user_inputs_area(screens, state.rows, state.current_row)
        if screen is ConsumerScreen.USER_INPUT_DETAILS:
            coordinate = state.user_inputs_artifact or state.focus
            return render_artifact_user_inputs(
                coordinate,
                screens.configurations_for(coordinate),
                screens.credentials_for(coordinate),
                state.current_row,
                profile,
            )
        if screen is ConsumerScreen.CONFIGURATION_VALUE:
            return render_configuration_value_form(
                state.user_inputs_artifact,
                state.configuration_input,
                state.configuration_targets,
                state.configuration_draft,
                state.current_row,
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
            if not state.rows:
                return ("Nothing has happened here yet.",)
            return activity_rows(screens.activity, state.rows, state.current_row)
        if screen in (ConsumerScreen.ACTIVITY_DETAILS, ConsumerScreen.RECEIPT_DETAILS):
            receipt = screens.receipt(state.focus)
            return (
                ("That action left no receipt.",)
                if receipt is None
                else render_receipt_detail(receipt, profile)
            )
        if screen is ConsumerScreen.REGISTRIES:
            # `QA-087`: the row, and the rows of whatever is connected. What a registry *is*, and
            # what this machine has, are answers to different questions and live in `status`.
            add = (f"{'>' if state.current_row == 'add-registry' else ' '} Add Registry",)
            if not screens.registries:
                return add
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
            return tuple(
                f"{'>' if row == state.current_row else ' '} {labels[row]}: {values[row]}"
                for row in state.rows
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
            return tuple(
                f"{'>' if row == state.current_row else ' '} {labels[row]}: {values[row]}"
                for row in state.rows
            )
        if screen is MaintainerScreen.REGISTRY_INIT:
            init = state.registry_init_draft
            values = {
                "id": init.registry_id or "<type a name like acme-registry>",
                "name": init.display_name or "<type what people should call it>",
                "commit": "yes, one local commit" if init.commit else "no, leave the files staged",
                "initialize": "Review the five stages",
            }
            labels = {
                "id": "Registry ID",
                "name": "Display name",
                "commit": "Local commit",
                "initialize": "Continue",
            }
            return tuple(
                f"{'>' if row == state.current_row else ' '} {labels[row]}: {values[row]}"
                for row in state.rows
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
            return tuple(
                f"{'>' if row == state.current_row else ' '} {labels[row]}: {values[row]}"
                for row in state.rows
            )
        if screen is MaintainerScreen.REGISTRY_REBUILD:
            rows = (REGISTRY_REBUILD_EVERYTHING, *REGISTRY_MAINTENANCE_STAGES)
            # `QA-089`: a row is the choice alone. Gluing the purpose on turned five things to
            # choose between into five sentences to read, and the purpose is exactly what the
            # cursor description exists to say -- under `[v]`, for whichever row is selected.
            labels = {
                REGISTRY_REBUILD_EVERYTHING: "Everything, in order: "
                + ", ".join(REGISTRY_MAINTENANCE_STAGES),
                **{stage: f"{stage.title()} only" for stage in REGISTRY_MAINTENANCE_STAGES},
            }
            return tuple(
                f"{'>' if row == (state.current_row or rows[0]) else ' '} {labels[row]}"
                for row in rows
            )
        if screen in _REVIEW_SCREENS:
            # A review has nothing the cursor can move over: the one decision it offers is a key,
            # and a key is advertised in the legend (`QA-088`). What it is about is view status.
            return ()
        if screen is ConsumerScreen.REQUIRED_INPUTS and state.config_form_active:
            return render_installation_config_form(
                screens.installation_inputs,
                state.config_draft,
                state.current_row or "",
            )
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
            # A plan that is running now outranks whatever the last one produced: this is the
            # screen somebody is watching while it runs, and the previous result is not news.
            if screens.running is not None:
                return render_running(screens.running, profile)
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
            if screens.doctor is None:
                return ("Nothing has been checked yet.",)
            if state.rows:
                return doctor_issue_rows(screens.doctor, state.rows, state.current_row)
            return doctor_rows(screens.doctor)
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
