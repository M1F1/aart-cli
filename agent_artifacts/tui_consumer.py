"""The consumer frontend: text renderers for the canonical view models, and the loop over them.

The renderers decide only how much detail to disclose; they never derive a plan or mutate consumer
intent.  :func:`run_consumer_shell` drives them, but it reaches the terminal and the machine only
through injected ports, so the persistent application is exercised headlessly with a fake terminal
and the curses adapter stays as thin as a `getch`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from agent_artifacts.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ActivityView,
    ConfigInputView,
    ConsumerPlanView,
    ConsumerScreen,
    ConsumerSettings,
    CredentialInputView,
    DashboardView,
    DoctorView,
    InstalledArtifactView,
    InstalledCollectionView,
    LifecycleOutcomeView,
    LifecyclePlanView,
    MarketplaceCollectionView,
    PresentationProfile,
    ReceiptDetailView,
    RegistryView,
)
from agent_artifacts.tui_marketplace import MarketplaceArtifactRow, render_artifact_detail

__all__ = [
    "CanonicalScreenSource",
    "ConsumerScreenSource",
    "ConsumerScreens",
    "ConsumerTerminal",
    "key_name",
    "run_consumer_shell",
    "render_activity",
    "render_install_plan",
    "render_collection",
    "render_dashboard",
    "render_doctor",
    "render_installed_artifact",
    "render_installed_collection",
    "render_lifecycle_outcome",
    "render_lifecycle_plan",
    "render_marketplace_artifact",
    "render_receipt_detail",
    "render_required_inputs",
    "render_registry",
    "render_settings",
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


def key_name(code: int) -> str:
    """Name one `getch` code for the reducer, or return empty for a key with no meaning here."""

    if not isinstance(code, int) or isinstance(code, bool):
        raise ValueError("a key code is an integer")
    if code in _KEY_NAMES:
        return _KEY_NAMES[code]
    return chr(code) if 32 <= code < 127 else ""


def _human(value: str) -> str:
    return value.replace("-", " ")


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
    if not isinstance(view, ConsumerPlanView) or not isinstance(profile, PresentationProfile):
        raise ValueError("install plan rendering needs a consumer plan and presentation profile")
    return _fast_plan(view) if profile is PresentationProfile.FAST else _verbose_plan(view)


def render_installed_artifact(
    view: InstalledArtifactView, profile: PresentationProfile
) -> tuple[str, ...]:
    if not isinstance(view, InstalledArtifactView) or not isinstance(profile, PresentationProfile):
        raise ValueError("installed artifact rendering needs a view and presentation profile")
    lines = [f"{view.coordinate} — {_human(view.health)}"]
    if view.drift:
        lines.append("Needs attention: " + ", ".join(item.component for item in view.drift) + ".")
    else:
        lines.append("Verified against its desired state.")
    lines.append("Actions: " + ", ".join(view.actions) + ".")
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
        "Recent activity:",
    ]
    lines.extend(f"  - {item}" for item in view.recent_activity)
    if not view.recent_activity:
        lines.append("  - none yet")
    return tuple(lines)


def render_registry(view: RegistryView, profile: PresentationProfile) -> tuple[str, ...]:
    if not isinstance(view, RegistryView) or not isinstance(profile, PresentationProfile):
        raise ValueError("registry rendering needs a registry view and presentation profile")
    noun = "artifact" if view.artifact_count == 1 else "artifacts"
    lines = [
        f"{view.alias} — {_human(view.availability)}",
        f"{view.artifact_count} {noun}",
        "Actions: details, sync.",
        "Sync refreshes Marketplace availability; it does not update installed artifacts.",
    ]
    if profile is PresentationProfile.VERBOSE:
        age = (
            "never" if view.last_sync_age_seconds is None else f"{view.last_sync_age_seconds}s ago"
        )
        lines.extend(
            (
                f"Kind: {_human(view.kind)}",
                f"Origin: {view.origin}",
                f"Health: {_human(view.health)}; last sync: {age}",
                f"Revision: {view.revision or 'none'}",
                f"Snapshot: {view.snapshot_digest or 'none'}",
                f"Trust: {', '.join(view.trust) or 'none'}",
            )
        )
    return tuple(lines)


def render_settings(view: ConsumerSettings) -> tuple[str, ...]:
    if not isinstance(view, ConsumerSettings):
        raise ValueError("settings rendering needs consumer settings")
    return (
        "Experience",
        f"Detail level: {view.profile.value.title()}",
        "Installation",
        f"Default scope: {view.default_scope.title()}",
        "Updates",
        f"Show available updates: {'on' if view.show_updates else 'off'}",
        "Advanced",
        f"Maintainer Mode: {'on' if view.maintainer_mode else 'off'}",
    )


def render_doctor(view: DoctorView, profile: PresentationProfile) -> tuple[str, ...]:
    if not isinstance(view, DoctorView) or not isinstance(profile, PresentationProfile):
        raise ValueError("Doctor rendering needs a Doctor view and presentation profile")
    lines = [
        "AART / Check system",
        f"{view.ready_count} ready",
        f"{view.attention_count} needs attention",
    ]
    lines.extend(f"  - {item}" for item in view.issues)
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
            status = "Configured securely" if item.provider_reference is not None else "Required"
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

    def key(self) -> int: ...


class ConsumerScreenSource(Protocol):
    """What one screen is showing right now.

    The loop asks; it never derives.  Everything semantic -- which artifacts exist, what is
    installed, what a plan says -- is answered here, by a caller wired to the canonical services.
    """

    def rows(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The row identities the screen is currently showing, already filtered by the search."""

    def lines(self, state: ConsumerUiState) -> tuple[str, ...]:
        """The body of the screen, rendered at the profile `state` holds."""

    def detail(self, state: ConsumerUiState) -> ConsumerScreen | None:
        """Where Enter goes from the row under the cursor, if anywhere."""


_HELP_LINES: tuple[str, ...] = (
    "↑ ↓  move        space  select",
    "enter  details   esc  back",
    "/  search        v  Fast/Verbose",
    "?  help          q  quit",
)


def _title(screen: ConsumerScreen) -> str:
    return _human(screen.value.split("-", 1)[1]).title()


def frame(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """One drawn screen: heading, body, and whichever prompt is currently open."""

    heading = f"AART / {_title(state.session.screen)}"
    lines = [heading, "", *source.lines(state)]
    if state.help_visible:
        lines.extend(("", *_HELP_LINES))
    if state.searching:
        lines.extend(("", f"Search: {state.search}_"))
    elif state.search:
        lines.extend(("", f"Filter: {state.search} (esc to clear)"))
    if state.selection:
        lines.append(f"{len(state.selection)} selected")
    if state.quit_pending:
        lines.append(f"Discard {len(state.selection)} selected item(s) and quit? y/n")
    return tuple(lines)


def run_consumer_shell(
    source: ConsumerScreenSource,
    terminal: ConsumerTerminal,
    *,
    state: ConsumerUiState | None = None,
) -> ConsumerUiState:
    """Run the persistent consumer application until somebody leaves it.

    The rows are re-read whenever what the screen shows could have changed -- a navigation, a back,
    or an edit to the filter.  The cursor stays on the row it was on if that row is still there,
    which is why filtering never silently moves what somebody was about to act on.
    """

    current = ConsumerUiState() if state is None else state
    if not isinstance(current, ConsumerUiState):
        raise ValueError("the consumer shell needs consumer UI state")
    reloads = frozenset(
        {
            ConsumerUiEventKind.SEARCH,
            ConsumerUiEventKind.SEARCH_CLOSE,
        }
    )
    current = _reload(source, current)
    while not current.exited:
        terminal.draw(frame(source, current))
        name = key_name(terminal.key())
        if not name:
            continue
        event = key_event(name, current, detail=source.detail(current))
        if event is None:
            continue
        current, commands = reduce_consumer_ui(current, event)
        if event.kind in reloads or any(
            command.kind is ConsumerUiCommandKind.LOAD_SCREEN for command in commands
        ):
            current = _reload(source, current)
    return current


def _reload(source: ConsumerScreenSource, state: ConsumerUiState) -> ConsumerUiState:
    reloaded, _ = reduce_consumer_ui(
        state, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=source.rows(state))
    )
    return reloaded


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

    def artifact(self, coordinate: str) -> InstalledArtifactView | None:
        return next((item for item in self.installed if item.coordinate == coordinate), None)

    def receipt(self, recorded_at: str) -> ReceiptDetailView | None:
        return next((item for item in self.receipts if item.recorded_at == recorded_at), None)


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
        if screen is ConsumerScreen.INSTALLED:
            return tuple(
                item.coordinate
                for item in self._screens.installed
                if _matches(query, item.coordinate, item.health)
            )
        if screen is ConsumerScreen.ACTIVITY:
            return tuple(
                item.recorded_at
                for item in self._screens.activity.entries
                if _matches(query, item.summary, item.intent)
            )
        if screen is ConsumerScreen.REGISTRIES:
            return tuple(
                item.alias for item in self._screens.registries if _matches(query, item.alias)
            )
        return ()

    def detail(self, state: ConsumerUiState) -> ConsumerScreen | None:
        """Enter opens the detail of whatever this screen is currently about."""

        target = {
            ConsumerScreen.INSTALLED: ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
            ConsumerScreen.ACTIVITY: ConsumerScreen.ACTIVITY_DETAILS,
            ConsumerScreen.ACTIVITY_DETAILS: ConsumerScreen.RECEIPT_DETAILS,
        }.get(state.session.screen)
        if target is None or not (state.current_row or state.focus):
            return None
        return target

    def lines(self, state: ConsumerUiState) -> tuple[str, ...]:
        screen, profile = state.session.screen, state.session.profile
        screens = self._screens
        if screen is ConsumerScreen.DASHBOARD:
            return render_dashboard(screens.dashboard)
        if screen is ConsumerScreen.INSTALLED:
            return self._list(
                state,
                tuple(
                    f"{item.coordinate}  {_human(item.health)}"
                    for item in screens.installed
                    if item.coordinate in state.rows
                ),
            )
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
            return tuple(
                line for item in screens.registries for line in render_registry(item, profile)
            )
        if screen is ConsumerScreen.SETTINGS:
            return render_settings(screens.settings)
        if screen is ConsumerScreen.DOCTOR:
            return (
                ("Nothing has been checked yet.",)
                if screens.doctor is None
                else render_doctor(screens.doctor, profile)
            )
        return (f"{_title(screen)} is not available yet.",)

    def _list(self, state: ConsumerUiState, entries: tuple[str, ...]) -> tuple[str, ...]:
        if not entries:
            return ("Nothing here yet.",)
        return tuple(
            f"{'>' if row == state.current_row else ' '} "
            f"{'[x]' if row in state.selection else '[ ]'} {entry}"
            for row, entry in zip(state.rows, entries, strict=False)
        )
