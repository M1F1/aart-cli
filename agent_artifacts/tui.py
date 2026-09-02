"""The terminal entry point, and what is left of the wizard it replaced.

``run()`` is what ``cli._run_bare`` calls on a bare TTY. It composes the canonical consumer
application once and runs it: over ``curses`` when the terminal can host it, and over a
line-oriented terminal when it cannot (D-115). Both are the same application -- one screen source,
one reducer, one action handler -- because ERR05 permits a text fallback for exactly one condition,
the terminal cannot host curses, and says nothing about the product changing.

The legacy wizard that used to own both routes is gone: its curses shell (D-113), its text shell
and the stages only that shell drove (D-116). What remains here are the curses widgets the
surviving wizard stages still compose, and the composition and failure-rendering helpers the
canonical route uses. Nothing in this module decides anything semantic; that lives in
``application/`` and is reached through the injected handler.
"""

from __future__ import annotations

import functools
import os
import shutil
import sys
import traceback
from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Literal, Mapping, Optional, Sequence, Tuple

from . import __version__
from .application.consumer_ui import ConsumerUiState, opening_state
from .application.sources import SourceAdoptionOutcome
from .configuration.model import (
    UserConfiguration,
)
from .consumer import (
    ConsumerApplicationService,
    ConsumerOutcome,
    ConsumerReview,
)
from .consumer.application import CONSUMER_REVIEW_MISMATCH
from .curation.runtime import CurationService
from .domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from .domain.harness import Scope
from .domain.identifiers import ArtifactCoordinate, SourceAlias
from .domain.result import Err as DomainErr
from .domain.result import Ok as DomainOk
from .domain.result import Result as DomainResult
from .io.configured_installation_action import InstallationHost
from .io.consumer_actions import ConsumerActionContext, LocalConsumerActions
from .io.consumer_machine import read_consumer_machine
from .io.consumer_settings import read_consumer_settings
from .io.credentials import MacOsKeychainProvider
from .io.maintainer_views import read_maintainer_views
from .marketplace.model import MarketplaceCatalog
from .marketplace.search import Document, search, summary_line
from .model import (
    ArtifactType,
    InstallMode,
    InstallScope,
    Request,
    Result,
)
from .profiles.loader import load_profiles
from .profiles.model import Profile
from .profiles.scope import profile_for_scope
from .reporting.application import ReportingApplicationService
from .reporting.model import ReportingPlan, UsageReport
from .reporting.projection import (
    RegistryUsageReport,
    SetupReportState,
    usage_report_from_consumer,
    usage_reports_by_registry_from_consumer,
)
from .setup import (
    SETUP_EFFECT_PROMPT,
    SETUP_QUEUE_PROMPT,
    advisory_messages,
    project_setup_review,
    recovery_messages,
    render_run_summary,
    render_setup_outcome,
    render_setup_review,
    run_reload_reminders,
    setup_banner,
    setup_queue_choice,
    setup_queue_question,
    setup_retry_command,
)
from .sources.model import SourceIdentityTransition, SourceSyncOutcome
from .tui_consumer import (
    CanonicalScreenSource,
    read_consumer_offers,
    run_consumer_shell,
)
from .tui_failures import (
    WizardOperation,
    WizardStageFailure,
    render_wizard_stage_failure,
)
from .tui_layout import (
    BOX_CHECKED,
    BOX_DISABLED,
    BOX_EMPTY,
    CHROME_ROWS,
    CONTENT_MEASURE,
    HINT_ORDER,
    READABLE_MEASURE,
    STAGE_CURRENT,
    columns,
    field_block,
    pane_budget,
    status_bar,
    wrap,
)
from .tui_marketplace import (
    MarketplaceArtifactRow,
    MarketplaceTarget,
    artifact_cells,
    render_artifact_detail,
    render_artifact_pane,
)
from .tui_sources import (
    SourceAdditionRequest,
    SourceManagementRequest,
    SourceRemovalRequest,
    SourceStageView,
)
from .wizard import (
    BasketItem,
    WizardInput,
    WizardSession,
    WizardStage,
    initial_session,
    onboarding_lines,
    render_header,
)

# The three write actions the selector can drive; these are the verbs that build and dispatch a
# Request.
ACTIONS: Tuple[str, ...] = ("install", "update", "uninstall", "status")

# `receipt` is offered from the same menu and is deliberately *not* a fifth wizard verb.  The four
# above choose artifacts from a catalog and end at the wizard's Review; a receipt reads — or
# reverses — the setup record of one artifact that is already installed, so it has no basket, no
# install mode, and a review of its own.  Adding it to `ACTIONS` would put a value into the wizard
# state machine that no stage after `action` knows what to do with.
RECEIPT_MENU_ACTION = "receipt"
RECEIPT_MENU_ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("show", "Print the record a setup run persisted for one installation"),
    ("verify", "Ask this machine whether what that record claims is still true"),
    ("undo", "Reverse what the record says the run did (review first)"),
)


@dataclass(frozen=True, slots=True)
class _RoleChoice:
    name: Literal["user", "maintainer"]
    label: str
    description: str


ROLES: Tuple[_RoleChoice, ...] = (
    _RoleChoice(
        "user",
        "User",
        "Install, update, or remove harness artifacts from configured registries.",
    ),
    _RoleChoice(
        "maintainer",
        "Maintainer",
        "Do the same, plus curate a canonical registry checkout.",
    ),
)

CANONICAL_MAINTAINER_ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("validate", "Validate canonical registry protocol and generated evidence"),
    ("scaffold", "Scaffold one native artifact package for review"),
    ("collection", "Compose a collection from artifacts this registry already holds"),
    ("promote-native", "Promote one reviewed native Git reference"),
    ("refresh-native", "Check and review one locked native reference update"),
    ("vendor", "Copy one foreign subtree in as a package this registry owns"),
    ("revendor", "Re-resolve one vendored copy's upstream and review what moved"),
    ("lock", "Resolve approved references into the registry lock"),
    ("build", "Build the payload-free marketplace index"),
    ("audit", "Audit review, provenance, setup, license, and security evidence"),
    ("diff", "Preview deterministic canonical-format diff without writing"),
    ("user", "Enter User workflows; AART never commits or pushes Maintainer changes"),
)

# Canonical artifact-type display order (matches commands.list / docs/design/DESIGN.md §4).
_TYPE_ORDER: Tuple[ArtifactType, ...] = ("skill", "guideline", "mcp", "hook", "memory")
_TYPE_ATTR = {
    "skill": "skills",
    "guideline": "guidelines",
    "mcp": "mcp",
    "hook": "hooks",
    "memory": "memory",
}

ReadFn = Callable[[str], str]
WriteFn = Callable[[str], None]
SourceFactory = Callable[[Request], Result]
DispatchFn = Callable[[Request], int]


SourceFinalizeFn = Callable[[SourceManagementRequest], DomainResult[object]]
SourceAdditionFinalizeFn = Callable[[SourceAdditionRequest], DomainResult[object]]
SourceRemovalFinalizeFn = Callable[[SourceRemovalRequest], DomainResult[object]]
SourceSyncRunFn = Callable[[SourceAlias], DomainResult[SourceSyncOutcome]]
# Review and finalize are one function with one optional argument: passing the reviewed transition
# is what turns a review into an adoption, so a front-end cannot finalize something it never showed.
SourceResubscribeRunFn = Callable[
    [SourceAlias, SourceIdentityTransition | None], DomainResult[SourceAdoptionOutcome]
]
ConsumerServiceFactory = Callable[[UserConfiguration], DomainResult[ConsumerApplicationService]]
ReportingServiceFactory = Callable[[UserConfiguration], DomainResult[ReportingApplicationService]]
CurationServiceFactory = Callable[[str], DomainResult[CurationService]]


@dataclass(frozen=True, slots=True)
class _RuntimeSourceStage:
    """The imperative source boundary injected into either human TUI frontend."""

    view: SourceStageView
    source_finalizer: SourceFinalizeFn | None
    source_addition_finalizer: SourceAdditionFinalizeFn | None
    source_removal_finalizer: SourceRemovalFinalizeFn | None = None
    source_sync_runner: SourceSyncRunFn | None = None
    source_resubscribe_runner: SourceResubscribeRunFn | None = None


SourceStageLoader = Callable[[], DomainResult[_RuntimeSourceStage]]


@dataclass(frozen=True, slots=True)
class InstallModeChoice:
    """One user-facing installation-mode choice."""

    mode: InstallMode
    label: str
    description: str


INSTALL_MODE_CHOICES: Tuple[InstallModeChoice, ...] = (
    InstallModeChoice(
        "copy",
        "Copy (recommended)",
        "Install an independent snapshot into the target harness.",
    ),
    InstallModeChoice(
        "symlink",
        "Symlink",
        (
            "Live-link supported skills and hooks to a local catalog; file and merged "
            "artifacts selected through collections use copy semantics."
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class InstallScopeChoice:
    """One explicit consumer configuration/state boundary."""

    scope: InstallScope
    label: str
    description: str


INSTALL_SCOPE_CHOICES: Tuple[InstallScopeChoice, ...] = (
    InstallScopeChoice(
        "project",
        "Project (recommended)",
        "Configure only the current repository.",
    ),
    InstallScopeChoice(
        "user",
        "User",
        "Configure the selected harnesses for the current user across projects.",
    ),
)


@dataclass(frozen=True, slots=True)
class _Choice:
    """One selectable catalog row: either a single artifact or a whole collection.

    ``kind`` is ``"artifact"`` or ``"collection"``. ``label`` is the human row text. ``key`` is
    ``(type, name)`` for an artifact (so we can build ``Request.names`` + ``type_filter``-free
    selection) or the qualified collection coordinate.
    """

    kind: Literal["artifact", "collection", "profile"]
    name: str
    type: Optional[ArtifactType]
    label: str
    description: str = ""
    hidden_count: int = 0
    complete: bool = True
    enabled: bool = True
    reason: str = ""
    linked_count: int = 0
    copied_count: int = 0
    qualified_key: str = ""
    cells: Tuple[str, ...] = ()
    row: Optional[MarketplaceArtifactRow] = None


def _choice_label(
    kind: Literal["artifact", "collection", "profile"],
    name: str,
    art_type: Optional[ArtifactType],
    description: str,
    status: str = "",
) -> str:
    """Render a one-line choice label from structured choice data."""
    if kind == "artifact" and art_type is not None:
        label = f"[{art_type}] {name}"
    elif kind == "collection":
        label = f"[collection] {name}"
    else:
        label = name
    if description:
        label += f" — {description}"
    if status:
        label += f" ({status})"
    return label


def _dispatch(request: Request) -> int:
    """Route *request* through the same handlers the flag-mode CLI uses.

    Prefers ``cli.DISPATCH`` (WP-19) when it exists; otherwise imports the command module
    for ``request.command`` directly. Both paths call the identical ``run`` function — this
    module duplicates **no** command logic.
    """
    try:
        from . import cli

        dispatch = getattr(cli, "DISPATCH", None)
    except Exception:  # pragma: no cover - cli import is trivial
        dispatch = None

    if isinstance(dispatch, Mapping) and request.command in dispatch:
        return int(dispatch[request.command](request))

    # Fallback: import the specific command module on demand (avoids importing all of them
    # and keeps this independent of WP-19's merge state).
    from importlib import import_module

    module = import_module(f".commands.{request.command}", package=__package__)
    return int(module.run(request))


_ORIGINAL_DISPATCH = _dispatch


@dataclass(frozen=True, slots=True)
class _CanonicalSetupRun:
    exit_code: int
    reporting: Tuple[SetupReportState, ...]


def _setup_reporting_failure(status: str) -> Tuple[str, str] | None:
    if status in {"configured", "already-configured", "not-required"}:
        return None
    if status == "verification-failed":
        return ("verification", "setup-verification-failed")
    if status in {"rollback-incomplete", "rolled-back"}:
        return ("rollback", f"setup-{status}")
    if status in {"queue-declined", "planning-failed"}:
        return ("queue", f"setup-{status}")
    return ("setup-installer", f"setup-{status}")


def _setup_reporting_key(
    review: ConsumerReview,
    coordinate: ArtifactCoordinate,
    profile: str,
    scope: str,
) -> str:
    """Bind an unversioned setup identity back to its exact consumer Review item."""

    matches = tuple(
        item.key
        for item in review.items
        if item.coordinate.source == coordinate.source
        and item.coordinate.artifact == coordinate.artifact
        and item.profile == profile
        and item.scope == scope
    )
    if len(matches) == 1:
        return matches[0]
    return f"{coordinate}#{profile}/{scope}"


def _canonical_setup_run(
    service: ConsumerApplicationService,
    review: ConsumerReview,
    outcome: ConsumerOutcome,
    *,
    read: ReadFn,
    write: WriteFn,
) -> _CanonicalSetupRun:
    """Prepare, separately review, and sequentially execute canonical post-payload setup."""

    if not any(item.setup_status == "pending" for item in outcome.items):
        return _CanonicalSetupRun(0, ())
    queue = service.setup_queue(review, outcome)
    if queue.failures and all("authoriz" in item.detail.casefold() for item in queue.failures):
        write("Setup needs explicit permission for untrusted/custom source capabilities.")
        answer = _read_line(read, "Authorize these reviewed setup capabilities? [y/N]: ")
        if answer is not None and answer.strip().lower() in ("y", "yes"):
            queue = service.setup_queue(
                review,
                outcome,
                authorize_untrusted_source=True,
                authorize_custom_entrypoint=True,
            )
    if queue.failures:
        write("Payload outcome: installed; setup planning did not change installed payloads.")
    for failure in queue.failures:
        key, _separator, selector = failure.key.partition("#")
        profile, _separator, scope = selector.partition("/")
        for line in render_setup_outcome(
            artifact=key,
            profile=profile or "selected profile",
            scope=scope or "selected scope",
            status="planning-failed",
            detail=failure.detail,
            # `aart setup` was removed in 2.0.0; the canonical verb re-runs the recipe. Planning
            # failed here, so no effect was applied and the profile/scope may not be known: the
            # coordinate alone is the most this failure can honestly say.
            retry_command=f"aart marketplace setup {key}",
            manual=failure.manual,
        ):
            write(line)
    if not queue.plans:
        plan_failures = tuple(
            SetupReportState(
                failure.key,
                "planning-failed",
                failure_phase="queue",
                failure_code="setup-planning-failed",
            )
            for failure in queue.failures
        )
        return _CanonicalSetupRun(1 if queue.failures else 0, plan_failures)
    # Keyed by identity because one ``step_id`` is only unique inside its own plan, and every
    # plan stays referenced by ``queue.plans`` for the whole run.
    safe_effects = {}
    for plan in queue.plans:
        safe_effects.update(
            {
                id(effect): rendered
                for effect, rendered in zip(
                    plan.legacy_plan.effects,
                    project_setup_review(plan.legacy_plan).effects,
                    strict=True,
                )
            }
        )
    for line in setup_queue_question(
        artifacts=len(queue.plans),
        steps=sum(len(plan.legacy_plan.effects) for plan in queue.plans),
    ):
        write(line)
    answer = _read_line(read, SETUP_QUEUE_PROMPT)
    choice = setup_queue_choice(answer)
    if choice == "show":
        write("Review setup queue (runs sequentially after installed payloads):")
        for plan in queue.plans:
            for line in render_setup_review(plan.legacy_plan):
                write(line)
    if choice == "stop":
        write("Payload outcome: installed; installed payloads were not rolled back.")
        write("Setup remains pending.")
        for plan in queue.plans:
            for line in render_setup_outcome(
                artifact=str(plan.request.coordinate),
                profile=plan.request.profile,
                scope=plan.request.scope,
                status="declined",
                detail="setup was declined before any effect ran",
                manual=project_setup_review(plan.legacy_plan).manual,
            ):
                write(line)
        declined = tuple(
            SetupReportState(
                _setup_reporting_key(
                    review,
                    plan.request.coordinate,
                    plan.request.profile,
                    plan.request.scope,
                ),
                "queue-declined",
                plan.recipe_digest,
                "queue",
                "setup-queue-declined",
            )
            for plan in queue.plans
        )
        planning = tuple(
            SetupReportState(
                failure.key,
                "planning-failed",
                failure_phase="queue",
                failure_code="setup-planning-failed",
            )
            for failure in queue.failures
        )
        return _CanonicalSetupRun(1, (*declined, *planning))

    def consent(effect) -> bool:
        """Report each step, and ask about it only when the operator asked to be asked.

        The two are different things, and treating them as one is what made this screen
        frightening (`#113`): a person who has chosen to install an artifact has already decided
        that its steps may run, so asking again per effect asks a question whose answer was
        settled. It stays available -- `s` at the question above -- because the answer can
        genuinely be no when a step touches something the operator owns.

        Quiet or not, a step that needs a value still asks for it: that prompt comes from the
        runtime, and nothing here can or should answer it.
        """

        reviewed = safe_effects.get(id(effect))
        if choice == "run":
            write(f"  {reviewed.index}. {reviewed.identity}" if reviewed else "  running a step")
            return True
        if reviewed is None:
            write("Approve this reviewed setup effect.")
        else:
            write(f"Approve {reviewed.index}. {reviewed.identity}. {reviewed.recovery}.")
        decision = _read_line(read, SETUP_EFFECT_PROMPT)
        return decision is not None and decision.strip().lower() in ("y", "yes")

    def announce(position: int, total: int, plan) -> None:
        """Say whose setup is starting, before anything asks the operator for anything.

        Everything between here and the item's own summary — approval prompts, and `security`
        taking the terminal to ask for a password twice while naming nothing — carries no
        artifact identity at all, and effect numbering restarts at 1 for each item, which reads
        as a glitch rather than as a boundary (`AD-40`).
        """

        write("")
        for line in setup_banner(
            artifact=str(plan.request.coordinate),
            profile=plan.request.profile,
            scope=plan.request.scope,
            phase="START",
            position=position,
            total=total,
        ):
            write(line)

    setup_outcome = service.finalize_setup_queue(queue, consent=consent, on_item_start=announce)
    plan_by_key = {
        f"{plan.request.coordinate}#{plan.request.profile}/{plan.request.scope}": plan
        for plan in queue.plans
    }
    for position, item in enumerate(setup_outcome.items, start=1):
        setup_plan = plan_by_key.get(f"{item.coordinate}#{item.profile}/{item.scope}")
        for line in render_setup_outcome(
            artifact=str(item.coordinate),
            profile=item.profile,
            scope=item.scope,
            status=item.setup_status.value,
            detail=item.detail,
            retry_command=(
                ""
                if item.successful
                else setup_retry_command(
                    coordinate=str(item.coordinate), profile=item.profile, scope=item.scope
                )
            ),
            recovery=() if item.record is None else recovery_messages(item.record),
            # The wizard is how setup is normally run, and it read no advisory at all: the
            # measurement happened, the receipt carried it, and this surface printed nothing
            # (`AD-36`).
            advisories=() if item.record is None else advisory_messages(item.record),
            # The reload reminder is not here any more: it is a fact about the machine, not about
            # this artifact, and one per item is how it stopped being read (`AD-39`).
            manual=None
            if setup_plan is None
            else project_setup_review(setup_plan.legacy_plan).manual,
            position=position,
            total=len(setup_outcome.items),
        ):
            write(line)
    for line in render_run_summary(
        tuple(
            {
                "artifact": str(item.coordinate),
                "profile": item.profile,
                "scope": item.scope,
                "status": item.setup_status.value,
                "detail": item.detail,
                "successful": item.successful,
                "retry_command": (
                    ""
                    if item.successful
                    else setup_retry_command(
                        coordinate=str(item.coordinate), profile=item.profile, scope=item.scope
                    )
                ),
            }
            for item in setup_outcome.items
        ),
        reminders=run_reload_reminders(tuple(item.record for item in setup_outcome.items)),
    ):
        write(line)
    reported_states: List[SetupReportState] = []
    for item in setup_outcome.items:
        key = f"{item.coordinate}#{item.profile}/{item.scope}"
        reporting_key = _setup_reporting_key(
            review,
            item.coordinate,
            item.profile,
            item.scope,
        )
        status = item.setup_status.value
        failure_spec = _setup_reporting_failure(status)
        setup_plan = plan_by_key.get(key)
        reported_states.append(
            SetupReportState(
                reporting_key,
                status,
                None if setup_plan is None else setup_plan.recipe_digest,
                None if failure_spec is None else failure_spec[0],
                None if failure_spec is None else failure_spec[1],
            )
        )
    reported_states.extend(
        SetupReportState(
            queue_failure.key,
            "planning-failed",
            failure_phase="queue",
            failure_code="setup-planning-failed",
        )
        for queue_failure in queue.failures
    )
    return _CanonicalSetupRun(
        0 if setup_outcome.incomplete == 0 and not queue.failures else 1,
        tuple(reported_states),
    )


def _offer_prepared_usage_report(
    service: ReportingApplicationService,
    plan: ReportingPlan,
    *,
    read: ReadFn,
    write: WriteFn,
) -> None:
    target = f"{plan.destination.host}/{plan.destination.repository}"
    if plan.destination.mode.value == "prompt":
        answer = _read_line(read, f"Share this redacted usage report with {target}? [y/N]: ")
        if answer is None or answer.strip().lower() not in ("y", "yes"):
            write("Usage report was not submitted.")
            return
    write("Exact redacted usage report payload:")
    write(plan.payload.decode("utf-8").strip())
    if plan.destination.mode.value == "prompt":
        answer = _read_line(read, "Open the prefilled GitHub issue? [y/N]: ")
        if answer is None or answer.strip().lower() not in ("y", "yes"):
            write("Usage report was not submitted.")
            return
    submitted = service.submit(plan)
    if isinstance(submitted, DomainErr):
        write("warning: usage report submission failed; the artifact outcome is unchanged")
        return
    write(
        "Usage report opened in the browser."
        if submitted.value.status == "browser-opened"
        else "Usage report submitted."
    )


def _offer_routed_usage_reports(
    service: ReportingApplicationService | None,
    combined: UsageReport,
    routed: Tuple[RegistryUsageReport, ...],
    *,
    read: ReadFn,
    write: WriteFn,
) -> None:
    if service is None:
        return
    selected_aliases = {report.source_alias for report in routed}
    for notice in service.notices:
        if notice.source_alias in selected_aliases:
            write(f"Usage report not offered for registry {notice.source_alias}: {notice.reason}.")
    prepared = service.prepare_routed(combined, routed)
    if isinstance(prepared, DomainErr):
        write("warning: usage reports could not be prepared; the artifact outcome is unchanged")
        return
    if prepared.value:
        write("Optional redacted usage reports are available for these artifact registries:")
        for plan in prepared.value:
            write(f"  - {plan.destination.host}/{plan.destination.repository}")
    for plan in prepared.value:
        _offer_prepared_usage_report(service, plan, read=read, write=write)


def _complete_canonical_consumer_action(
    consumer: ConsumerApplicationService,
    review: ConsumerReview,
    outcome: ConsumerOutcome,
    reporting: ReportingApplicationService | None,
    *,
    read: ReadFn,
    write: WriteFn,
    failure_context: InternalFailureContext | None = None,
) -> int:
    if failure_context is not None:
        failure_context.capture_operation("setup")
    setup = _canonical_setup_run(consumer, review, outcome, read=read, write=write)
    if failure_context is not None:
        failure_context.capture_operation("reporting")
    try:
        event = usage_report_from_consumer(
            review,
            outcome,
            setup.reporting,
            aart_version=__version__,
            interface="tui",
        )
        routed = usage_reports_by_registry_from_consumer(
            review,
            outcome,
            setup.reporting,
            aart_version=__version__,
            interface="tui",
        )
    except ValueError:
        write("warning: usage report projection failed; the artifact outcome is unchanged")
        return setup.exit_code
    _offer_routed_usage_reports(reporting, event, routed, read=read, write=write)
    return setup.exit_code


# --------------------------------------------------------------------------- #
# Text / fallback flow — fully injectable, headless-testable.                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _UserWizardReadModel:
    choices: Tuple[_Choice, ...]
    profiles_map: Mapping[str, Profile]
    source_label: str = ""
    source_root: str = ""
    marketplace_rows: Tuple[MarketplaceArtifactRow, ...] = ()


def _basket_key(choice: _Choice) -> str:
    if choice.qualified_key:
        return choice.qualified_key
    return (
        f"{choice.type}/{choice.name}"
        if choice.kind == "artifact" and choice.type is not None
        else f"{choice.kind}/{choice.name}"
    )


def _basket_item(choice: _Choice) -> BasketItem:
    return BasketItem(
        "collection" if choice.kind == "collection" else "artifact",
        _basket_key(choice),
        choice.label,
        choice.description,
    )


def _canonical_choice(row: MarketplaceArtifactRow) -> _Choice:
    """One list row. Identity and summary here; every evidence field lives in the record (D6)."""

    return _Choice(
        "artifact",
        row.identity.name,
        row.identity.kind,  # type: ignore[arg-type]
        f"{row.key} — {row.summary}",
        description=row.summary,
        enabled=row.compatible,
        reason="; ".join(reason.message for reason in row.reasons),
        linked_count=sum(mode == "symlink" for mode in row.actual_modes),
        copied_count=sum(mode == "copy" for mode in row.actual_modes),
        qualified_key=row.key,
        cells=artifact_cells(row),
        row=row,
    )


def _canonical_collection_choices(
    catalog: MarketplaceCatalog,
    rows: Tuple[MarketplaceArtifactRow, ...],
    *,
    sources: Tuple[SourceAlias, ...] = (),
) -> Tuple[_Choice, ...]:
    by_coordinate = {row.coordinate: row for row in rows}
    selected_sources = frozenset(sources)
    choices = []
    for collection in catalog.collections:
        if selected_sources and collection.coordinate.source not in selected_sources:
            continue
        member_rows = tuple(by_coordinate.get(member) for member in collection.members)
        missing = sum(row is None for row in member_rows)
        available = tuple(row for row in member_rows if row is not None)
        reasons = tuple(sorted({reason.message for row in available for reason in row.reasons}))
        enabled = missing == 0 and all(row.compatible for row in available)
        reason_parts = []
        if missing:
            reason_parts.append(f"{missing} member(s) unavailable")
        reason_parts.extend(reasons)
        reason = "; ".join(reason_parts)
        status = "" if enabled else f" — unavailable: {reason}"
        members = ", ".join(str(member) for member in collection.members)
        choices.append(
            _Choice(
                "collection",
                collection.coordinate.name,
                None,
                f"[collection] {collection.coordinate} — {collection.summary} "
                f"({len(collection.members)} members){status}",
                description=f"{collection.summary} Members: {members}.",
                enabled=enabled,
                reason=reason,
                linked_count=sum("symlink" in row.actual_modes for row in available),
                copied_count=sum("copy" in row.actual_modes for row in available),
                qualified_key=str(collection.coordinate),
                cells=(
                    f"[collection] {collection.coordinate}",
                    "available" if enabled else "unavailable",
                    f"{len(collection.members)} members",
                ),
            )
        )
    return tuple(choices)


_NOTHING_SELECTED = (
    "Nothing is selected yet. Enter number(s) between 1 and {count}, or 'q' to quit."
)

_KEEPS_ITS_NUMBER = (
    "Each row keeps the number it has in the full list, so type the numbers shown. "
    "'/' on its own lists everything again."
)


def _choice_documents(choices: Sequence[_Choice]) -> Tuple[Document, ...]:
    """Each row as the text a person would type at it.

    The name is what they half remember, the qualified key is what they paste, and the summary is
    what they describe. The type goes in as well, so `/skill` is a way to see only skills without
    a filter flag existing anywhere.
    """

    return tuple(
        Document(
            choice.name,
            choice.qualified_key or choice.label,
            choice.description,
            (("type", choice.type),) if choice.type else (),
        )
        for choice in choices
    )


def _matching_rows(choices: Sequence[_Choice], query: str) -> Tuple[int, ...]:
    """The rows matching ``query``, best first, named by their place in ``choices``.

    Positions, never a renumbered list. The caller's indices address the basket, the availability
    map and the install plan; a filtered view that renumbered its rows would let a person select
    the artifact that happens to sit at the number they read.
    """

    return tuple(hit.index for hit in search(_choice_documents(choices), query))


def _write_search(write: WriteFn, choices: Sequence[_Choice], query: str) -> None:
    """Answer a ``/`` line: the matching rows, at their own numbers, and how many there were."""

    matches = _matching_rows(choices, query)
    width = shutil.get_terminal_size(fallback=(100, 24)).columns
    for index in matches:
        write(_text_choice_line(index + 1, choices[index], width))
    write(summary_line(query, len(matches), len(choices)))
    if matches and len(matches) < len(choices):
        write(_KEEPS_ITS_NUMBER)


def _prompt_wizard_indices(
    read: ReadFn,
    write: WriteFn,
    prompt: str,
    choices: Sequence[_Choice],
    *,
    selected: Sequence[int] = (),
    allow_add: bool = False,
    allow_source_maintenance: bool = False,
) -> WizardInput:
    selected_tuple = tuple(dict.fromkeys(selected))
    while True:
        line = _read_line(read, prompt)
        if line is None:
            return WizardInput("quit")
        answer = line.strip()
        low = answer.lower()
        if low in ("q", "quit"):
            return WizardInput("quit")
        if low in ("b", "back"):
            return WizardInput("back")
        if allow_add and low in ("a", "add"):
            return WizardInput("add")
        if allow_source_maintenance and low in ("s", "sync"):
            return WizardInput("sync")
        if allow_source_maintenance and low in ("r", "remove"):
            return WizardInput("remove")
        if allow_source_maintenance and low in ("i", "resubscribe"):
            return WizardInput("resubscribe")
        if not answer:
            if selected_tuple:
                return WizardInput("confirm", selected_tuple)
            # D5 has no cursor to fall back on here, so an empty confirm says why it did nothing
            # rather than ending the wizard (design section 5).
            write(_NOTHING_SELECTED.format(count=len(choices)))
            continue
        if answer.startswith("?"):
            number = answer[1:].strip()
            if number.isdigit() and 1 <= int(number) <= len(choices):
                for line in _choice_detail(choices, int(number) - 1):
                    write(line)
                continue
            write(f"Enter ?N with a number between 1 and {len(choices)}.")
            continue
        if answer.startswith("/"):
            _write_search(write, choices, answer[1:])
            continue
        parsed = _parse_indices(answer, len(choices))
        if parsed:
            disabled = tuple(choices[index] for index in parsed if not choices[index].enabled)
            if disabled:
                for choice in disabled:
                    write(f"{choice.name}: {choice.reason or 'this item is unavailable'}.")
                continue
            return WizardInput("confirm", parsed)
        write(
            f"Please enter number(s) between 1 and {len(choices)}, 'b' to go back, or 'q' to quit."
        )


def _prompt_wizard_scope(read: ReadFn, write: WriteFn) -> WizardInput | InstallScope:
    while True:
        line = _read_line(read, "Installation scope [1] (b=back, q=quit): ")
        if line is None:
            return WizardInput("quit")
        answer = line.strip().lower()
        if answer in ("q", "quit"):
            return WizardInput("quit")
        if answer in ("b", "back"):
            return WizardInput("back")
        if answer in ("", "1", "project"):
            return "project"
        if answer in ("2", "user", "global"):
            return "user"
        write("Please enter 1 (Project), 2 (User), 'b' to go back, or 'q' to quit.")


def _load_user_wizard_read_model(
    session: WizardSession,
    *,
    source_factory: SourceFactory,
    source_dir: Optional[str],
    repo: Optional[str],
    project: Optional[str],
    user_home: Optional[str],
    consumer_service: Optional[ConsumerApplicationService] = None,
) -> DomainResult[_UserWizardReadModel]:
    del source_factory, source_dir, repo
    assert session.action is not None
    base_profiles = load_profiles(project)
    resolved_home = os.path.abspath(user_home or os.path.expanduser("~"))
    scope = session.scope
    profiles_map: Mapping[str, Profile] = (
        base_profiles
        if scope == "project"
        else {
            name: profile_for_scope(profile, "user", resolved_home)
            for name, profile in base_profiles.items()
        }
    )
    if consumer_service is None:
        return DomainErr(
            (
                Diagnostic(
                    DiagnosticCode("canonical-consumer-unavailable"),
                    Severity.ERROR,
                    "the canonical consumer service is unavailable",
                    remediation=("configure and synchronize a canonical registry source",),
                ),
            )
        )
    selected_sources = (
        () if session.source_selection is None else session.source_selection.enabled_aliases
    )
    setup_capabilities = getattr(
        getattr(getattr(consumer_service.context, "effective", None), "policy", None),
        "allowed_setup_capabilities",
        None,
    )
    # Test doubles and alternative service skins may expose no typed policy context. Absence has
    # the same semantics as an unset allowlist; an arbitrary mock value must not become a
    # capability set and mask the domain result returned by `browse`.
    if setup_capabilities is not None and not isinstance(setup_capabilities, tuple):
        setup_capabilities = None
    projected = consumer_service.browse(
        MarketplaceTarget(
            tuple(sorted(session.profiles)),
            "darwin" if sys.platform == "darwin" else "linux",
            scope,  # type: ignore[arg-type]
            session.install_mode,  # type: ignore[arg-type]
            setup_capabilities,
        ),
        sources=selected_sources,
    )
    if isinstance(projected, DomainErr):
        return projected
    rows = projected.value
    if session.action in ("update", "uninstall"):
        rows = tuple(row for row in rows if row.installed)
    choices = tuple(_canonical_choice(row) for row in rows)
    if session.action == "install":
        choices += _canonical_collection_choices(
            consumer_service.context.catalog,
            rows,
            sources=selected_sources,
        )
    return DomainOk(
        _UserWizardReadModel(
            choices,
            profiles_map,
            "federated configured marketplace",
            consumer_service.context.store_paths.root,
            rows,
        )
    )


def _receipt_data_root(user_home: Optional[str]) -> str:
    """The data root a receipt reads, resolved the way every other TUI path resolves it."""

    from .configuration.paths import Platform, resolve_config_paths

    platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
    paths = resolve_config_paths(
        platform,
        home=os.path.abspath(user_home or os.path.expanduser("~")),
        xdg_config_home=os.environ.get("XDG_CONFIG_HOME"),
        xdg_data_home=os.environ.get("XDG_DATA_HOME"),
        xdg_cache_home=os.environ.get("XDG_CACHE_HOME"),
    )
    return paths.data_root


def receipt_outcome(
    action: str,
    scope: str,
    selector: str,
    *,
    profiles: Sequence[str] = (),
    project: Optional[str] = None,
    user_home: Optional[str] = None,
    confirm: Callable[[Tuple[str, ...]], bool],
) -> DomainResult[Tuple[str, ...]]:
    """One receipt action, from a selector to the lines a front-end writes.

    Both skins call this, so neither owns any part of a receipt: the resolution, the three
    projections and the undo's consent gate all live here or in `receipt_service`, and what a
    skin supplies is `confirm` — how *it* shows a review and asks. That is the only thing a
    curses form and a line-oriented prompt genuinely do differently.
    """

    from .receipt_service import (
        apply_undo,
        load_receipt,
        resolved_paths,
        show_view,
        undo_view,
        verify_view,
    )
    from .setup_render import (
        render_receipt_payload,
        render_undo_payload,
        render_verification_payload,
    )

    data_root = _receipt_data_root(user_home)
    project_root, home = resolved_paths(data_root=data_root, project=project, user_home=user_home)
    loaded = load_receipt(
        data_root=data_root,
        project_root=project_root,
        user_home=home,
        scope=scope,  # type: ignore[arg-type]
        selector=selector,
        profiles=tuple(profiles),
    )
    if isinstance(loaded, DomainErr):
        return loaded

    if action == "show":
        return DomainOk(render_receipt_payload(show_view(loaded.value)))
    if action == "verify":
        return DomainOk(render_verification_payload(verify_view(loaded.value)))

    payload, digest = undo_view(loaded.value)
    review = render_undo_payload(payload)
    if not confirm(review):
        return DomainOk(review + ("Undo not applied; nothing was changed.",))

    # `SI-1` over an interactive consent: the flag-mode path binds the decision with
    # `--expect <digest>`, and the equivalent here is to recompute the undo after the answer and
    # refuse if it is no longer the one that was read. Re-reading from disk, not from `loaded`,
    # because what may have moved is the record itself.
    reloaded = load_receipt(
        data_root=data_root,
        project_root=project_root,
        user_home=home,
        scope=scope,  # type: ignore[arg-type]
        selector=selector,
        profiles=tuple(profiles),
    )
    if isinstance(reloaded, DomainErr):
        return reloaded
    recomputed_payload, recomputed = undo_view(reloaded.value)
    if recomputed != digest:
        return DomainErr(
            (
                Diagnostic(
                    CONSUMER_REVIEW_MISMATCH,
                    Severity.ERROR,
                    f"the undo changed since it was reviewed: read {digest}, "
                    f"recomputed {recomputed}",
                    remediation=("read the undo again and re-answer it",),
                ),
            )
        )
    del recomputed_payload

    rolled = apply_undo(reloaded.value)
    return DomainOk(
        render_undo_payload(payload, applied=True)
        + (f"Undo outcome: {rolled.status} — {rolled.detail}",)
    )


def _prompt_receipt_action(read: ReadFn, write: WriteFn) -> WizardInput | str:
    write("Receipt action:")
    for index, (name, description) in enumerate(RECEIPT_MENU_ACTIONS, start=1):
        write(f"  {index:>2}. {name:<8} {description}")
    names = tuple(name for name, _ in RECEIPT_MENU_ACTIONS)
    while True:
        line = _read_line(read, "Receipt action (b=back, q=quit): ")
        if line is None:
            return WizardInput("quit")
        answer = line.strip().lower()
        if answer in ("q", "quit"):
            return WizardInput("quit")
        if answer in ("b", "back", ""):
            return WizardInput("back")
        if answer in names:
            return answer
        if answer.isdigit() and 1 <= int(answer) <= len(names):
            return names[int(answer) - 1]
        write(f"Please enter 1-{len(names)}, an action name, 'b', or 'q'.")


def _run_receipt_text(
    read: ReadFn,
    write: WriteFn,
    *,
    project: Optional[str] = None,
    user_home: Optional[str] = None,
    profiles: Sequence[str] = (),
) -> None:
    """Walk the three receipt actions at a line-oriented terminal, then return to the menu."""

    action = _prompt_receipt_action(read, write)
    if isinstance(action, WizardInput):
        return
    scope = _prompt_wizard_scope(read, write)
    if isinstance(scope, WizardInput):
        return
    selector = _read_line(read, "Installed artifact (kind/name, b=back, q=quit): ")
    if selector is None:
        return
    wanted = selector.strip()
    if wanted.lower() in ("", "b", "back", "q", "quit"):
        return

    def confirm(review: Tuple[str, ...]) -> bool:
        for line in review:
            write(line)
        write("Applying reverses the effects marked `reverses` above; nothing else is touched.")
        answer = _read_line(read, "Apply this undo? [y/N]: ")
        return answer is not None and answer.strip().lower() in ("y", "yes")

    outcome = receipt_outcome(
        action,
        scope,
        wanted,
        profiles=profiles,
        project=project,
        user_home=user_home,
        confirm=confirm,
    )
    if isinstance(outcome, DomainErr):
        _write_domain_diagnostics(outcome, write)
        return
    for line in outcome.value:
        write(line)


def _write_domain_diagnostics(result: DomainErr, write: WriteFn) -> None:
    for diagnostic in result.diagnostics:
        for line in wrap(
            f"{diagnostic.severity.value} [{diagnostic.code.value}]: {diagnostic.message}",
            width=CONTENT_MEASURE,
        ):
            write(line)
        for remediation in diagnostic.remediation:
            prefix = "  remediation: "
            lines = wrap(remediation, width=CONTENT_MEASURE - len(prefix))
            write(prefix + lines[0])
            for line in lines[1:]:
                write(" " * len(prefix) + line)


def _read_line(read: ReadFn, prompt: str) -> Optional[str]:
    """Read one line; map EOF (``input`` raising ``EOFError``) to ``None`` (= quit)."""
    try:
        return read(prompt)
    except EOFError:
        return None


def _parse_indices(line: str, choice_count: int) -> Tuple[int, ...]:
    """Pure 1-based comma/space selection parser used by both text menus."""
    tokens = [token for token in line.replace(",", " ").split() if token]
    out: List[int] = []
    seen = set()
    for token in tokens:
        if not token.isdigit():
            return ()
        number = int(token)
        if not (1 <= number <= choice_count):
            return ()
        index = number - 1
        if index not in seen:
            seen.add(index)
            out.append(index)
    return tuple(out)


def _text_choice_line(index: int, choice: _Choice, width: int) -> str:
    """Render one numbered text-frontend row within the terminal width."""
    prefix = f"  {index:>2}. "
    if width <= len(prefix):
        return _ellipsize(prefix, width)
    return prefix + _ellipsize(choice.label, max(width - len(prefix), 0))


# --------------------------------------------------------------------------- #
# curses front-end — gather an immutable session, dispatch only after teardown. #
# --------------------------------------------------------------------------- #
def _curses_header(stdscr, session: WizardSession) -> Tuple[str, ...]:
    width = _width(stdscr) if hasattr(stdscr, "getmaxyx") else 80
    return render_header(session, width=max(width - 1, 1), frontend="curses")


def _position(session: WizardSession, stage: str) -> Tuple[int, int]:
    for position in session.positions:
        if position.stage == stage:
            return position.cursor, position.scroll
    return 0, 0


def _curses_single_event(curses, stdscr, title, labels, session: WizardSession) -> WizardInput:
    cursor, scroll = _position(session, session.current)
    try:
        result = _curses_singleselect(
            curses,
            stdscr,
            title,
            labels,
            wizard=True,
            initial_cursor=cursor,
            initial_scroll=scroll,
            header=_curses_header(stdscr, session),
        )
    except TypeError as error:
        if "unexpected keyword argument" not in str(error):
            raise
        result = _curses_singleselect(curses, stdscr, title, labels)
    if isinstance(result, WizardInput):
        return result
    if result is None:
        return WizardInput("quit", cursor=cursor, scroll=scroll)
    selected = int(result)
    return WizardInput("confirm", (selected,), selected, scroll)


def _curses_text_input(
    curses,
    stdscr,
    session: WizardSession,
    prompt: str,
    *,
    default: str | None = None,
    maximum_length: int = 512,
) -> str | WizardInput:
    """Collect one bounded printable source field without leaving the full-screen wizard."""

    required = ("clear", "addstr", "refresh", "getch")
    if not all(hasattr(stdscr, name) for name in required):
        return WizardInput("quit")
    buffer = ""
    backspace = {getattr(curses, "KEY_BACKSPACE", -1), 127, 8}
    enter = {getattr(curses, "KEY_ENTER", -1), 10, 13}
    while True:
        stdscr.clear()
        available = max(_width(stdscr) - 1, 1)
        lines = _curses_header(stdscr, session) + (prompt,)
        for row, line in enumerate(lines):
            if row >= max(_height(stdscr) - 2, 0):
                break
            stdscr.addstr(row, 0, _ellipsize(line, available))
        input_row = min(len(lines) + 1, max(_height(stdscr) - 2, 0))
        shown = buffer or ("" if default is None else f"[{default}]")
        stdscr.addstr(input_row, 0, _ellipsize(f"> {shown}", available))
        if _height(stdscr) > 0:
            stdscr.addstr(
                _height(stdscr) - 1,
                0,
                status_bar(
                    (
                        ("enter", "continue"),
                        ("backspace", "back when empty"),
                        ("q", "quit when empty"),
                    ),
                    width=available,
                ),
            )
        stdscr.refresh()
        key = stdscr.getch()
        if key in enter:
            return buffer or (default or "")
        if key in backspace:
            if buffer:
                buffer = buffer[:-1]
            else:
                return WizardInput("back")
            continue
        if key in (27,) or (key in (ord("q"), ord("Q")) and not buffer):
            return WizardInput("quit")
        if 32 <= key <= 126 and len(buffer) < maximum_length:
            buffer += chr(key)


def _curses_notice(
    stdscr,
    session: WizardSession,
    title: str,
    lines: Sequence[str],
) -> None:
    """Show one bounded source-flow outcome before returning to the Sources stage.

    Curses has no scrollback after a form closes.  A short acknowledgement keeps parser,
    policy, sync, and success outcomes observable instead of silently dropping the user back at
    the checkbox list.
    """

    required = ("clear", "addstr", "refresh", "getch")
    if not all(hasattr(stdscr, name) for name in required):
        return
    content = _curses_header(stdscr, session) + (title, *lines)
    available = max(_width(stdscr) - 1, 1)
    content_width = min(available, CONTENT_MEASURE)
    stdscr.clear()
    for row, line in enumerate(content[: max(_height(stdscr) - 1, 0)]):
        stdscr.addstr(row, 0, _ellipsize(line, content_width))
    if _height(stdscr) > 0:
        stdscr.addstr(_height(stdscr) - 1, 0, _ellipsize("Press any key to continue.", available))
    stdscr.refresh()
    stdscr.getch()


def _source_flow_diagnostics(result: DomainErr) -> tuple[str, ...]:
    """Render a refused source operation, remediation included.

    Curses has no scrollback, so a notice that drops remediation leaves the user looking at a
    refusal with no stated way out — which is the whole failure this stage exists to end. Lines
    are wrapped rather than ellipsized, because the way out is usually the longest line.
    """

    lines: tuple[str, ...] = ()
    for diagnostic in result.diagnostics:
        lines += tuple(
            wrap(
                f"{diagnostic.severity.value} [{diagnostic.code.value}]: {diagnostic.message}",
                width=CONTENT_MEASURE,
            )
        )
        for remediation in diagnostic.remediation:
            prefix = "  next: "
            wrapped = wrap(remediation, width=CONTENT_MEASURE - len(prefix))
            lines += (prefix + wrapped[0],)
            lines += tuple(" " * len(prefix) + line for line in wrapped[1:])
    return lines


def _curses_review(curses, stdscr, session: WizardSession, lines: Sequence[str]):
    if not all(hasattr(stdscr, name) for name in ("clear", "addstr", "refresh", "getch")):
        return False
    content = _curses_header(stdscr, session) + tuple(lines)
    offset = 0
    while True:
        stdscr.clear()
        available = max(_width(stdscr) - 1, 0)
        height = _height(stdscr)
        body_height = max(height - 1, 1)
        max_offset = max(len(content) - body_height, 0)
        offset = min(offset, max_offset)
        for row, line in enumerate(content[offset : offset + body_height]):
            stdscr.addstr(row, 0, _ellipsize(line, available))
        if height:
            stdscr.addstr(
                height - 1,
                0,
                status_bar(
                    (("enter", "finalize"), ("b", "back"), ("q", "quit")),
                    width=available,
                ),
            )
        stdscr.refresh()
        key = stdscr.getch()
        if key in (curses.KEY_ENTER, 10, 13, ord("y"), ord("Y")):
            return True
        if key in (getattr(curses, "KEY_BACKSPACE", -1), 127, 8, ord("b")):
            return "back"
        if key in (ord("q"), 27):
            return "quit"
        if key in (ord("n"), ord("N")):
            return False
        if key in (curses.KEY_DOWN, ord("j")) and offset < max_offset:
            offset += 1
        elif key in (curses.KEY_UP, ord("k")) and offset > 0:
            offset -= 1
        elif key == getattr(curses, "KEY_NPAGE", -1) and offset < max_offset:
            offset = min(offset + body_height, max_offset)
        elif key == getattr(curses, "KEY_PPAGE", -1) and offset > 0:
            offset = max(offset - body_height, 0)


def _run_receipt_curses(
    curses,
    stdscr,
    session: WizardSession,
    *,
    project: Optional[str],
    user_home: Optional[str],
) -> None:
    """The same three receipt actions inside the full-screen wizard.

    Every decision is `receipt_outcome`'s; this function only asks the three questions with
    curses widgets and shows what comes back. The undo's consent is `_curses_review`, which is
    the same gate the wizard's own Review uses, so an undo is approved the way everything else
    in this skin is.
    """

    labels = tuple(f"{name} — {description}" for name, description in RECEIPT_MENU_ACTIONS)
    event = _curses_single_event(curses, stdscr, "Receipt action", labels, session)
    if event.kind != "confirm" or not event.selected:
        return
    action = RECEIPT_MENU_ACTIONS[event.selected[0]][0]

    chosen = _curses_install_scope_event(curses, stdscr, header=_curses_header(stdscr, session))
    if chosen.kind != "confirm" or not chosen.selected:
        return
    scope = INSTALL_SCOPE_CHOICES[chosen.selected[0]].scope

    typed = _curses_text_input(
        curses, stdscr, session, "Installed artifact to read (kind/name):", maximum_length=200
    )
    if isinstance(typed, WizardInput) or not typed.strip():
        return

    def confirm(review: Tuple[str, ...]) -> bool:
        return (
            _curses_review(
                curses,
                stdscr,
                session,
                tuple(review)
                + ("", "Enter applies this undo; n, b or q leaves everything as it is."),
            )
            is True
        )

    outcome = receipt_outcome(
        action,
        scope,
        typed.strip(),
        profiles=session.profiles,
        project=project,
        user_home=user_home,
        confirm=confirm,
    )
    if isinstance(outcome, DomainErr):
        _curses_notice(
            stdscr,
            session,
            f"Receipt {action} failed",
            tuple(
                line
                for diagnostic in outcome.diagnostics
                for line in (
                    f"{diagnostic.severity.value} [{diagnostic.code.value}]: {diagnostic.message}",
                    *(f"  remediation: {item}" for item in diagnostic.remediation),
                )
            ),
        )
        return
    _curses_notice(stdscr, session, f"Receipt {action}", outcome.value)


class CursesUnavailable(Exception):
    """The terminal cannot host the curses wizard.

    Raised only for import, TTY, or curses initialisation failure detected **before** the wizard
    interacts with the user. It is the sole condition under which the text wizard may start as a
    fallback. Any failure after interaction begins propagates instead, so a defect is never
    mistaken for a missing terminal and never silently restarts the wizard at onboarding with the
    user's selections discarded.
    """


INTERNAL_FAILURE_CODE = "tui-stage-internal"


#: The boundaries ``run`` itself can name. A canonical failure has no ``WizardStage`` to report --
#: the stages are gone -- and reporting one anyway would send somebody looking for a screen that no
#: longer exists. What ``run`` does know is whether it was still composing the application or had
#: handed it to a terminal, and which terminal that was.
CanonicalBoundary = Literal["compose", "curses", "text"]


@dataclass(slots=True)
class InternalFailureContext:
    """The last safe frontend boundary, kept outside any session it describes."""

    stage: WizardStage | CanonicalBoundary = "compose"
    operation: WizardOperation = "load"

    def capture_operation(self, operation: WizardOperation) -> None:
        """Mark a shell operation while retaining the stage captured at its boundary."""

        self.operation = operation


def internal_failure_lines(
    error: BaseException,
    context: InternalFailureContext | None = None,
) -> Tuple[str, ...]:
    """Project a defect into stable, redacted terminal lines.

    Only the exception *type* is disclosed. Messages can carry filesystem paths, subprocess
    output, or setup input, so they are withheld by default. Context contains only the last safe
    stage and operation; it never owns terminal, service, or domain-state objects.
    """

    failure_context = context or InternalFailureContext()
    return (
        f"internal error: {INTERNAL_FAILURE_CODE}",
        f"  stage: {failure_context.stage}",
        f"  operation: {failure_context.operation}",
        f"  type: {type(error).__name__}",
        "next: rerun the command; if it repeats, report it with the steps that reached this screen.",
    )


def _debug_traceback_enabled() -> bool:
    """Enable an explicitly local traceback channel without changing normal terminal output."""

    return os.environ.get("AART_DEBUG") == "1"


def _render_internal_failure(
    error: BaseException,
    context: InternalFailureContext | None = None,
) -> int:
    for line in internal_failure_lines(error, context):
        print(line)
    if _debug_traceback_enabled():
        traceback.print_exception(error, file=sys.stderr)
    return 2


def _curses_multiselect(
    curses,
    stdscr,
    title: str,
    labels: Sequence[str],
    details: Optional[Sequence[str]] = None,
    disabled: Optional[Sequence[bool]] = None,
    *,
    wizard: bool = False,
    allow_add: bool = False,
    allow_source_maintenance: bool = False,
    initial_checked: Sequence[int] = (),
    initial_cursor: int = 0,
    initial_scroll: int = 0,
    header: Sequence[str] = (),
    cells: Optional[Sequence[Sequence[str]]] = None,
    pane_for: Optional[Callable[[int, int], Sequence[str]]] = None,
    reasons: Optional[Sequence[str]] = None,
    detail_for: Optional[Callable[[int], Sequence[str]]] = None,
    notice: str = "",
    documents: Optional[Sequence[Document]] = None,
):
    """A checkbox list, optionally returning explicit wizard navigation and position.

    Enter confirms the ticked rows. With nothing ticked it confirms the row under the cursor,
    because moving the cursor onto a row and pressing Enter is the most natural gesture on a list
    and it used to end the session silently (D5). A disabled cursor row refuses and says why
    instead of leaving; only a list with no selectable row at all still returns nothing.

    ``/`` starts a filter and every printable key after it narrows the list live; Enter keeps the
    filter and hands the arrows back, Escape drops it. A filter hides rows, and hiding a row is
    all it does: what was ticked stays ticked, and every index this function reports is a position
    in the caller's own ``labels``, never in the filtered view. ``documents`` says what each row
    is *about* -- name, coordinate, summary -- so a filter ranks the way `marketplace search` does;
    without it the row's printed label is the text searched, which still matches but ranks flatly.
    """
    if not labels:
        return WizardInput("confirm") if wizard else ()
    cursor = min(max(initial_cursor, 0), len(labels) - 1)
    scroll = max(initial_scroll, 0)
    checked = [False] * len(labels)
    for index in initial_checked:
        if 0 <= index < len(checked) and (disabled is None or not disabled[index]):
            checked[index] = True
    back_keys = {getattr(curses, "KEY_BACKSPACE", -1), 127, 8, ord("b")}
    erase_keys = {getattr(curses, "KEY_BACKSPACE", -1), 127, 8}
    hints = _list_hints(
        toggle=True,
        back=wizard,
        details=details is not None,
        add=wizard and allow_add,
        maintain=wizard and allow_source_maintenance,
        search=True,
    )
    selectable = disabled is None or not all(disabled)
    corpus = (
        tuple(documents)
        if documents is not None
        else tuple(Document(label, label) for label in labels)
    )
    query = ""
    searching = False
    # True while the query has just changed: the cursor then rides the best match, so typing one
    # more letter and pressing Enter takes the row the filter was narrowing towards. Dropping the
    # filter does not set it, because the row someone was looking at is still the row they were
    # looking at.
    snap = False
    while True:
        view = _search_view(corpus, query)
        if view and (snap or cursor not in view):
            cursor = view[0]
        snap = False
        position = view.index(cursor) if view else 0
        scroll = _draw_list(
            curses,
            stdscr,
            title,
            tuple(labels[index] for index in view),
            position,
            [checked[index] for index in view],
            disabled=None if disabled is None else [disabled[index] for index in view],
            header=header,
            scroll=scroll,
            hints=_SEARCH_HINTS if searching else hints,
            cells=None if cells is None else tuple(cells[index] for index in view),
            pane_for=(
                None
                if pane_for is None or not view
                else functools.partial(_filtered_pane, pane_for, view)
            ),
            notice=notice or _search_notice(query, len(view), len(labels), searching),
        )
        notice = ""
        ch = stdscr.getch()
        if searching:
            # Every printable key is a letter of the query while the filter is open, so nothing
            # here may fall through to the bindings below: `q` types a q, `b` types a b.
            if ch == 27:  # ESC drops the filter and the search together
                query, searching, scroll = "", False, 0
            elif ch in (curses.KEY_ENTER, 10, 13):
                searching = False  # keep what is on screen, hand the arrows back
            elif ch in erase_keys:
                query, scroll, snap = query[:-1], 0, True
            elif 32 <= ch < 127:
                query, scroll, snap = query + chr(ch), 0, True
            continue
        if ch in (ord("q"), 27):  # q / ESC
            return WizardInput("quit", cursor=cursor, scroll=scroll) if wizard else None
        elif ch == ord("/"):
            searching, scroll = True, 0
        elif wizard and ch in back_keys:
            return WizardInput("back", cursor=cursor, scroll=scroll)
        elif wizard and allow_add and ch in (ord("a"), ord("A")):
            return WizardInput("add", cursor=cursor, scroll=scroll)
        elif wizard and allow_source_maintenance and ch in (ord("s"), ord("S")):
            # The cursor row, not the ticked rows: maintenance acts on exactly one source.
            return WizardInput("sync", (cursor,), cursor=cursor, scroll=scroll)
        elif wizard and allow_source_maintenance and ch in (ord("i"), ord("I")):
            return WizardInput("resubscribe", (cursor,), cursor=cursor, scroll=scroll)
        elif wizard and allow_source_maintenance and ch in (ord("r"), ord("R")):
            return WizardInput("remove", (cursor,), cursor=cursor, scroll=scroll)
        elif ch in (curses.KEY_UP, ord("k")) and view:
            cursor = view[(position - 1) % len(view)]
        elif ch in (curses.KEY_DOWN, ord("j")) and view:
            cursor = view[(position + 1) % len(view)]
        elif ch == ord(" ") and view:
            if disabled is None or not disabled[cursor]:
                checked[cursor] = not checked[cursor]
        elif ch == ord("?") and detail_for is not None and view:
            _draw_detail(curses, stdscr, labels[cursor], record=tuple(detail_for(cursor)))
        elif ch == ord("?") and details is not None and view and cursor < len(details):
            _draw_detail(curses, stdscr, labels[cursor], details[cursor])
        elif ch in (curses.KEY_ENTER, 10, 13):
            # Over every row, not the filtered ones: a filter hides rows, it never unticks them.
            selected = tuple(i for i, on in enumerate(checked) if on)
            if not selected and selectable:
                if not view:
                    notice = _NOTHING_MATCHES.format(query=query)
                    continue
                if disabled is not None and disabled[cursor]:
                    notice = _refusal(reasons, cursor)
                    continue
                selected = (cursor,)
            return (
                WizardInput("confirm", selected, cursor=cursor, scroll=0 if query else scroll)
                if wizard
                else selected
            )


def _curses_singleselect(
    curses,
    stdscr,
    title: str,
    labels: Sequence[str],
    *,
    wizard: bool = False,
    initial_cursor: int = 0,
    initial_scroll: int = 0,
    header: Sequence[str] = (),
):
    """A single-choice list, optionally returning explicit wizard navigation."""
    cursor = min(max(initial_cursor, 0), max(len(labels) - 1, 0))
    scroll = max(initial_scroll, 0)
    back_keys = {getattr(curses, "KEY_BACKSPACE", -1), 127, 8, ord("b")}
    hints = _list_hints(toggle=False, back=wizard, details=False, add=False)
    while True:
        scroll = _draw_list(
            curses,
            stdscr,
            title,
            labels,
            cursor,
            None,
            header=header,
            scroll=scroll,
            hints=hints,
        )
        ch = stdscr.getch()
        if ch in (ord("q"), 27):
            return WizardInput("quit", cursor=cursor, scroll=scroll) if wizard else None
        elif wizard and ch in back_keys:
            return WizardInput("back", cursor=cursor, scroll=scroll)
        elif ch in (curses.KEY_UP, ord("k")):
            cursor = (cursor - 1) % len(labels)
        elif ch in (curses.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % len(labels)
        elif ch in (curses.KEY_ENTER, 10, 13):
            return WizardInput("confirm", (cursor,), cursor, scroll) if wizard else cursor


PANE_ROWS = 8
"""Rows the artifact pane asks for: one rule, identity, a summary line, and the field block."""


def _fitting_cells(cells: Sequence[Sequence[str]], width: int) -> Tuple[Tuple[str, ...], ...]:
    """Keep the leading columns that still fit, and drop the rest whole.

    ``columns`` shrinks a column toward one character rather than dropping it, which turns
    ``registry-reviewed`` into ``regist…`` — the same width, none of the meaning. The projections
    order their cells by importance precisely so this can cut from the right instead.
    """

    if not cells:
        return ()
    count = max(len(row) for row in cells)
    widths = [
        max((len(row[index]) for row in cells if index < len(row)), default=0)
        for index in range(count)
    ]
    keep = 1
    while keep < count and sum(widths[: keep + 1]) + 2 * keep <= width:
        keep += 1
    return tuple(tuple(row[:keep]) for row in cells)


def _choice_detail(choices: Sequence[_Choice], index: int) -> Tuple[str, ...]:
    """The complete record behind ``?``, in whichever frontend asked for it (D8)."""

    choice = choices[index]
    if choice.row is not None:
        return render_artifact_detail(choice.row)
    identity = _choice_label(choice.kind, choice.name, choice.type, "")
    description = choice.description or "No catalog description is available."
    return (identity, *wrap(description, width=READABLE_MEASURE))


def _choice_pane(choices: Sequence[_Choice], index: int, width: int) -> Tuple[str, ...]:
    """The pane body for the cursor row, whatever kind of row it is.

    An artifact has a projection of its own; a collection has no security record, so it gets the
    same shape assembled from what the choice already knows. Both keep the pane the same height,
    which is what stops the list from moving under the cursor.
    """

    choice = choices[index]
    if choice.row is not None:
        return render_artifact_pane(choice.row, width=width)
    status = "available" if choice.enabled else f"unavailable: {choice.reason}"
    return (
        f"  {choice.cells[0] if choice.cells else choice.label}",
        *(f"  {line}" for line in wrap(choice.description, width=max(width - 2, 1))),
        *field_block((("status", status),), indent=4, width=width),
    )


def _refusal(reasons: Optional[Sequence[str]], cursor: int) -> str:
    """What to say when Enter lands on a row that cannot be chosen."""

    reason = reasons[cursor] if reasons is not None and cursor < len(reasons) else ""
    return f"cannot select this row: {reason}" if reason else "this row cannot be selected"


_NOTHING_MATCHES = "Nothing matches {query!r}. Press / to change the filter."

_SEARCH_HINTS: Tuple[Tuple[str, str], ...] = (
    ("enter", "keep"),
    ("esc", "clear"),
    ("bksp", "erase"),
)
"""The bar while a filter is being typed. Every other key is a letter, so no other key is offered."""


def _filtered_pane(pane_for, view: Sequence[int], position: int, width: int) -> Sequence[str]:
    """The pane for the row at ``position`` of a filtered view, asked for by its real index."""

    return pane_for(view[position], width)


def _search_view(corpus: Sequence[Document], query: str) -> Tuple[int, ...]:
    """Which rows a filter leaves, best first; every row when nothing is typed."""

    return tuple(hit.index for hit in search(corpus, query))


def _search_notice(query: str, matches: int, total: int, searching: bool) -> str:
    """The one line under the title while a filter is being typed or is being held."""

    if searching:
        return f"/{query}   {summary_line(query, matches, total)}"
    if query:
        return f"filter {query!r}   {summary_line(query, matches, total)}   /=change"
    return ""


def _list_hints(
    *,
    toggle: bool,
    back: bool,
    details: bool,
    add: bool,
    maintain: bool = False,
    search: bool = False,
) -> Tuple[Tuple[str, str], ...]:
    """The canonical hint table filtered down to the keys this screen actually accepts (D2)."""

    enabled = {
        "space": toggle,
        "enter": True,
        "b": back,
        "?": details,
        "/": search,
        "a": add,
        "s": maintain,
        "i": maintain,
        "r": maintain,
        "q": True,
    }
    return tuple(hint for hint in HINT_ORDER if enabled[hint[0]])


def _draw_list(
    curses,
    stdscr,
    title: str,
    labels,
    cursor: int,
    checked,
    *,
    disabled: Optional[Sequence[bool]] = None,
    header: Sequence[str] = (),
    scroll: int = 0,
    hints: Sequence[Tuple[str, str]] = (),
    cells: Optional[Sequence[Sequence[str]]] = None,
    pane_for: Optional[Callable[[int, int], Sequence[str]]] = None,
    notice: str = "",
) -> int:
    """Render *title* + the labels, marking the cursor row and any checked rows.

    The last row belongs to the status bar and to nothing else (D2). Everything above it — header,
    title and the list viewport — is laid out inside ``height - 1``, the same reservation
    ``_curses_onboarding`` already makes for its footer.

    ``cells`` replaces the flat label with a shared column grid computed across every row at once,
    so a column starts at the same offset on all of them. ``pane_for`` supplies the detail pane for
    the cursor row; it is reserved out of the viewport at a height fixed for the whole frame, which
    is what keeps the list from reflowing under a moving cursor (D6). One item is still one row.
    """
    stdscr.clear()
    available = max(_width(stdscr) - 1, 0)
    height = _height(stdscr)
    body_height = max(height - 1, 1)
    header_budget = max(body_height - CHROME_ROWS, 1)
    if len(header) > header_budget:
        # Keep whatever says where the user is before anything else. These match the marker
        # vocabulary in tui_layout, not prose, so they survive wording changes.
        priorities = (
            lambda line: STAGE_CURRENT in line,
            lambda line: line.startswith("Basket:"),
            lambda line: line.startswith("Removed "),
        )
        picked: List[int] = []
        for predicate in priorities:
            picked.extend(
                index
                for index, line in enumerate(header)
                if predicate(line) and index not in picked
            )
        picked.extend(index for index in range(len(header)) if index not in picked)
        visible_indices = set(picked[:header_budget])
        header = tuple(line for index, line in enumerate(header) if index in visible_indices)
    row = 0
    for line in header:
        if row >= body_height:
            break
        stdscr.addstr(row, 0, _ellipsize(line, available))
        row += 1
    if row < body_height:
        stdscr.addstr(row, 0, _ellipsize(title, available))
    if notice and row + 1 < body_height:
        # The separator row is already reserved and already blank, so a notice costs no geometry.
        stdscr.addstr(row + 1, 0, _ellipsize(notice, available))
    list_start = row + 2
    pane_height = 0 if pane_for is None else pane_budget(height=height, requested=PANE_ROWS)
    visible_rows = max(body_height - list_start - pane_height, 1)
    max_scroll = max(len(labels) - visible_rows, 0)
    scroll = min(max(scroll, 0), max_scroll)
    if cursor < scroll:
        scroll = cursor
    elif cursor >= scroll + visible_rows:
        scroll = cursor - visible_rows + 1
    gutter = 2 + (4 if checked is not None else 0)
    row_width = max(min(available, CONTENT_MEASURE) - gutter, 1)
    texts = labels if cells is None else columns(_fitting_cells(cells, row_width), width=row_width)
    for display_row, i in enumerate(range(scroll, min(len(labels), scroll + visible_rows))):
        prefix = "> " if i == cursor else "  "
        box = ""
        if checked is not None:
            if disabled is not None and disabled[i]:
                box = f"{BOX_DISABLED} "
            else:
                box = f"{BOX_CHECKED} " if checked[i] else f"{BOX_EMPTY} "
        line = f"{prefix}{box}{texts[i]}"
        target_row = list_start + display_row
        if target_row < body_height:
            stdscr.addstr(target_row, 0, _ellipsize(line, available))
    if pane_height and pane_for is not None:
        # Directly under the last row when the list is short, otherwise just above the bar. Both
        # depend only on frame constants, so the pane never moves while the cursor does.
        pane_top = min(list_start + min(len(labels), visible_rows) + 1, body_height - pane_height)
        pane_lines = (
            "─" * min(available, CONTENT_MEASURE),
            *pane_for(cursor, min(available, CONTENT_MEASURE)),
        )
        for offset, line in enumerate(pane_lines[:pane_height]):
            stdscr.addstr(pane_top + offset, 0, _ellipsize(line, available))
    if height:
        stdscr.addstr(
            height - 1,
            0,
            status_bar(
                hints,
                counters=_list_counters(labels, checked, disabled, scroll, visible_rows),
                width=available,
            ),
        )
    stdscr.refresh()
    return scroll


def _list_counters(
    labels,
    checked,
    disabled: Optional[Sequence[bool]],
    scroll: int,
    visible_rows: int,
) -> Tuple[str, ...]:
    """The bar's right-hand counters, cheapest to lose last (D2)."""

    counters = []
    if checked is not None:
        selected = sum(
            1
            for index, value in enumerate(checked)
            if value and (disabled is None or not disabled[index])
        )
        counters.append(f"{selected} selected")
    if len(labels) > visible_rows:
        last = min(len(labels), scroll + visible_rows)
        counters.append(f"{scroll + 1}-{last} of {len(labels)}")
    return tuple(counters)


def _curses_onboarding(curses, stdscr) -> WizardInput:
    """Render the first-screen controls; test doubles without a screen auto-confirm."""

    if not all(hasattr(stdscr, name) for name in ("clear", "addstr", "refresh", "getch")):
        return WizardInput("confirm")
    session = initial_session()
    offset = 0
    while True:
        stdscr.clear()
        available = max(_width(stdscr) - 1, 0)
        lines = onboarding_lines("curses") + render_header(
            session, width=max(available, 1), frontend="curses"
        )
        height = _height(stdscr)
        body_height = max(height - 1, 1)
        max_offset = max(len(lines) - body_height, 0)
        offset = min(offset, max_offset)
        for row, line in enumerate(lines[offset : offset + body_height]):
            stdscr.addstr(row, 0, _ellipsize(line, available))
        if height:
            stdscr.addstr(
                height - 1,
                0,
                status_bar((("enter", "start"), ("q", "quit")), width=available),
            )
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            return WizardInput("confirm")
        if ch in (ord("q"), 27):
            return WizardInput("quit")
        if ch in (curses.KEY_DOWN, ord("j")) and offset < max_offset:
            offset += 1
        elif ch in (curses.KEY_UP, ord("k")) and offset > 0:
            offset -= 1
        elif ch == getattr(curses, "KEY_NPAGE", -1) and offset < max_offset:
            offset = min(offset + body_height, max_offset)
        elif ch == getattr(curses, "KEY_PPAGE", -1) and offset > 0:
            offset = max(offset - body_height, 0)


def _curses_install_scope_event(
    curses,
    stdscr,
    *,
    initial_cursor: int = 0,
    initial_scroll: int = 0,
    header: Sequence[str] = (),
) -> WizardInput:
    """Scope selector with Project under the initial cursor. Always a `WizardInput`.

    `selected[0]` indexes `INSTALL_SCOPE_CHOICES`; `kind` is `confirm`, `back` or `quit`.

    `LAF-64`: this used to take `wizard=True` and answer with the `InstallScope` itself when the
    flag was absent — one function, two return types, and nothing in the signature saying which.
    A second caller written the obvious way (`if isinstance(result, WizardInput): return`) compiled,
    typechecked, and read every successful selection as a cancel. The flag is gone rather than
    documented, because a caller cannot misread a type it never receives. The scope-only shape went
    with it: its only reader was a fallback for a stubbed function, and nothing asks for it.
    """

    labels = [f"{choice.label} — {choice.description}" for choice in INSTALL_SCOPE_CHOICES]
    event = _curses_singleselect(
        curses,
        stdscr,
        "Installation scope",
        labels,
        wizard=True,
        initial_cursor=initial_cursor,
        initial_scroll=initial_scroll,
        header=header,
    )
    assert isinstance(event, WizardInput)
    return event


def _curses_install_mode(
    curses,
    stdscr,
    *,
    wizard: bool = False,
    initial_cursor: int = 0,
    initial_scroll: int = 0,
    header: Sequence[str] = (),
):
    """Install-only mode selector with Copy under the initial cursor."""

    labels = [f"{choice.label} — {choice.description}" for choice in INSTALL_MODE_CHOICES]
    cursor = min(max(initial_cursor, 0), len(labels) - 1)
    scroll = max(initial_scroll, 0)
    back_keys = {getattr(curses, "KEY_BACKSPACE", -1), 127, 8, ord("b")}
    hints = _list_hints(toggle=False, back=True, details=False, add=False)
    while True:
        scroll = _draw_list(
            curses,
            stdscr,
            "Installation mode",
            labels,
            cursor,
            None,
            header=header,
            scroll=scroll,
            hints=hints,
        )
        ch = stdscr.getch()
        if ch in (ord("q"), 27):
            return WizardInput("quit", cursor=cursor, scroll=scroll) if wizard else None
        if ch in back_keys:
            return WizardInput("back", cursor=cursor, scroll=scroll) if wizard else "back"
        if ch in (curses.KEY_UP, ord("k")):
            cursor = (cursor - 1) % len(labels)
        elif ch in (curses.KEY_DOWN, ord("j")):
            cursor = (cursor + 1) % len(labels)
        elif ch in (curses.KEY_ENTER, 10, 13):
            return (
                WizardInput("confirm", (cursor,), cursor, scroll)
                if wizard
                else INSTALL_MODE_CHOICES[cursor].mode
            )


def _ellipsize(text: str, width: int) -> str:
    """Return one visual line no wider than ``width``, marking truncation with ``…``."""
    one_line = text.replace("\r", " ").replace("\n", " ")
    if width <= 0:
        return ""
    if len(one_line) <= width:
        return one_line
    if width == 1:
        return "…"
    return one_line[: width - 1] + "…"


def _draw_detail(
    curses,
    stdscr,
    label: str,
    description: str = "",
    *,
    record: Sequence[str] = (),
) -> None:
    """Show the complete evidence in a scrollable curses detail view.

    A record is rendered as it comes: it is already bounded and its digest lines are deliberately
    exempt from the measure, because a wrapped hash can be neither read nor copied (D8). Plain
    prose is wrapped at the readable measure rather than at the terminal width (D7).
    """
    available = max(_width(stdscr) - 1, 1)
    height = _height(stdscr)
    # A record leads with its own identity line, so repeating the label above it would state the
    # same fact twice on adjacent rows.
    titles = ("Artifact details",) if record else ("Artifact details", label)
    content_top = len(titles) + 1
    content_height = max(height - content_top - 1, 1)
    wrapped = list(record) or list(
        wrap(description or "No catalog description is available.", width=available)
    )
    max_offset = max(len(wrapped) - content_height, 0)
    offset = 0

    while True:
        stdscr.clear()
        for index, title in enumerate(titles):
            if index < height:
                stdscr.addstr(index, 0, _ellipsize(title, available))
        for relative_row, line in enumerate(wrapped[offset : offset + content_height]):
            row = content_top + relative_row
            if row >= max(height - 1, 0):
                break
            stdscr.addstr(row, 0, _ellipsize(line, available))
        if height > 0:
            hints = (("↑/↓", "scroll"), ("q", "return")) if max_offset else (("q", "return"),)
            stdscr.addstr(height - 1, 0, status_bar(hints, width=available))
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (curses.KEY_DOWN, ord("j")) and offset < max_offset:
            offset += 1
        elif ch in (curses.KEY_UP, ord("k")) and offset > 0:
            offset -= 1
        elif ch == curses.KEY_NPAGE and offset < max_offset:
            offset = min(offset + content_height, max_offset)
        elif ch == curses.KEY_PPAGE and offset > 0:
            offset = max(offset - content_height, 0)
        else:
            return


def _curses_stage_failure_recovery(
    curses,
    stdscr,
    failure: WizardStageFailure,
) -> WizardInput:
    """Show a blocking stage record and accept only its declared recovery events."""

    required = ("clear", "addstr", "refresh", "getch", "getmaxyx")
    if not all(hasattr(stdscr, name) for name in required):
        return WizardInput("quit")
    shortcuts = {"retry": "r", "back": "b", "quit": "q"}
    available = max(_width(stdscr) - 1, 1)
    height = _height(stdscr)
    body_height = max(height - 1, 1)
    record = render_wizard_stage_failure(failure, width=available)
    max_offset = max(len(record) - body_height, 0)
    offset = 0
    hints = tuple((shortcuts[choice], choice) for choice in failure.choices)
    while True:
        stdscr.clear()
        for row, line in enumerate(record[offset : offset + body_height]):
            stdscr.addstr(row, 0, _ellipsize(line, available))
        if height > 0:
            stdscr.addstr(height - 1, 0, status_bar(hints, width=available))
        stdscr.refresh()
        key = stdscr.getch()
        for choice, shortcut in shortcuts.items():
            if choice in failure.choices and key in (ord(shortcut), ord(shortcut.upper())):
                return WizardInput(choice)
        if key in (getattr(curses, "KEY_DOWN", -1), ord("j")) and offset < max_offset:
            offset += 1
        elif key in (getattr(curses, "KEY_UP", -1), ord("k")) and offset > 0:
            offset -= 1
        elif key == getattr(curses, "KEY_NPAGE", -1) and offset < max_offset:
            offset = min(offset + body_height, max_offset)
        elif key == getattr(curses, "KEY_PPAGE", -1) and offset > 0:
            offset = max(offset - body_height, 0)


def _height(stdscr) -> int:
    return stdscr.getmaxyx()[0]


def _width(stdscr) -> int:
    return stdscr.getmaxyx()[1]


class _CursesTerminal:
    """The whole curses dependency of the canonical consumer application.

    Drawing and one blocking read: everything else about that application -- what a key means,
    what a screen shows, when to reload rows -- lives in code that never touches a terminal.
    """

    def __init__(self, stdscr) -> None:
        self._stdscr = stdscr

    def draw(self, lines: Tuple[str, ...]) -> None:
        self._stdscr.clear()
        height, width = self._stdscr.getmaxyx()
        for row, line in enumerate(lines[: max(height - 1, 0)]):
            self._stdscr.addstr(row, 0, line[: max(width - 1, 0)])
        self._stdscr.refresh()

    def key(self) -> int:
        return int(self._stdscr.getch())


#: The keys a line editor cannot send. A line has no arrows and no bare Escape, so those get a
#: word; everything else is the character somebody typed. An unknown word is worth nothing rather
#: than its first letter: taking the "d" out of "delete" would act on a key nobody pressed.
_TEXT_KEY_WORDS: dict[str, int] = {
    "": 10,
    "enter": 10,
    "return": 10,
    "up": 259,
    "down": 258,
    "esc": 27,
    "escape": 27,
    "back": 263,
    "backspace": 263,
    "space": 32,
}

_TEXT_KEY_HINT = "Keys: one character, or up / down / enter / esc / back. Blank line = enter."


class _TextTerminal:
    """The canonical consumer application in a terminal that cannot draw.

    The shell's terminal is two methods, so text is not a second application: it is the same one,
    written with ``print`` and driven by ``input()``. That is what ERR05's degradation means --
    the terminal cannot host curses, not that the product changes.
    """

    def __init__(self, read: ReadFn, write: WriteFn) -> None:
        self._read = read
        self._write = write
        self._ended = False

    def draw(self, lines: Tuple[str, ...]) -> None:
        for line in lines:
            self._write(line)
        self._write("")
        self._write(_TEXT_KEY_HINT)

    def key(self) -> int:
        try:
            raw = self._read("> ")
        except EOFError:
            # stdin ended. Quit, and answer the discard prompt quitting may raise -- nobody is
            # there to answer it, and redrawing it forever is the alternative.
            quitting = not self._ended
            self._ended = True
            return ord("q") if quitting else ord("y")
        if len(raw) == 1:
            return ord(raw)
        return _TEXT_KEY_WORDS.get(raw.strip().lower(), 0)


def run_consumer_text(
    actions: LocalConsumerActions,
    *,
    read: ReadFn = input,
    write: WriteFn = print,
) -> ConsumerUiState:
    """Run the canonical consumer application over a line-oriented terminal.

    The same screens, reducer and action handler the curses route runs. Only the terminal differs,
    which is the whole of what ERR05 permits a text fallback to change.
    """

    return run_consumer_shell(
        actions.source(),
        _TextTerminal(read, write),
        state=opening_state(actions.settings),
        action_handler=actions,
        settings_writer=actions.save_settings,
    )


def run_consumer(actions: LocalConsumerActions) -> ConsumerUiState:
    """Run the canonical consumer application over curses, or raise if there is no terminal.

    The handler is the argument rather than the screens, because the screens come from it: what is
    drawn after an action is what that action read back off the machine, and a caller holding its
    own snapshot beside the handler would be holding one that goes stale the first time somebody
    installs something.
    """

    try:
        import curses  # stdlib; imported lazily so the text path needs no terminal at all.
    except ImportError as error:
        raise CursesUnavailable("the curses application could not start") from error

    captured: dict = {}

    def _ui(stdscr) -> None:
        captured["state"] = run_consumer_shell(
            actions.source(),
            _CursesTerminal(stdscr),
            state=opening_state(actions.settings),
            action_handler=actions,
            settings_writer=actions.save_settings,
        )

    try:
        curses.wrapper(_ui)
    except CursesUnavailable:
        raise
    except Exception as error:  # pragma: no cover - terminal capability failure
        if "state" in captured:
            raise
        raise CursesUnavailable("the curses application could not start") from error
    state = captured.get("state")
    if not isinstance(state, ConsumerUiState):  # pragma: no cover - wrapper always runs _ui
        raise CursesUnavailable("the curses application did not run")
    return state


def _canonical_consumer_actions(
    *,
    project: str | None,
    user_home: str | None,
    today: date,
) -> DomainResult[LocalConsumerActions]:
    """Compose the canonical application from one durable read of the local machine.

    Everything an action needs is resolved here, once: where this machine keeps its state, what
    the configured sources offer, and which harnesses were actually measured. Composition is where
    an effect belongs, and a draw must never reach back into any of it (D-051).
    """

    from .configuration.paths import Platform, resolve_config_paths

    platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
    home = os.path.abspath(user_home or os.path.expanduser("~"))
    paths = resolve_config_paths(
        platform,
        home=home,
        xdg_config_home=os.environ.get("XDG_CONFIG_HOME"),
        xdg_data_home=os.environ.get("XDG_DATA_HOME"),
        xdg_cache_home=os.environ.get("XDG_CACHE_HOME"),
    )
    project_root = os.path.abspath(project or os.getcwd())
    # One set of adapters for the whole application. Measuring a credential through a provider the
    # actions could not act on would report an attention nothing here is able to close.
    providers = (MacOsKeychainProvider(),) if sys.platform == "darwin" else ()
    machine = read_consumer_machine(
        state_root=os.path.join(paths.data_root, "state"),
        harness_root=project_root,
        today=today,
        project_root=project_root,
        user_home=home,
        data_root=paths.data_root,
        credential_providers=providers,
    )
    if isinstance(machine, DomainErr):
        return machine
    loaded = _canonical_consumer_configuration(paths)
    if isinstance(loaded, DomainErr):
        return loaded
    target = _canonical_marketplace_target()
    offers = read_consumer_offers(loaded.value, data_root=paths.data_root, target=target)
    if isinstance(offers, DomainErr):
        return offers
    # Preferences somebody already chose, not the ones this build happens to default to. An
    # unreadable file refuses here rather than opening on a Fast/consumer view that quietly
    # contradicts what screen 28 was last told.
    settings = read_consumer_settings(paths.data_root)
    if isinstance(settings, DomainErr):
        return settings
    maintainer = read_maintainer_views(
        loaded.value, data_root=paths.data_root, registry_root=project_root
    )
    if isinstance(maintainer, DomainErr):
        return maintainer
    return DomainOk(
        LocalConsumerActions(
            ConsumerActionContext(
                InstallationHost(
                    paths.data_root, project_root, home, Scope.PROJECT, target.profiles
                ),
                loaded.value,
                machine.value,
                offers=offers.value,
                settings=settings.value,
                maintainer=maintainer.value,
                credential_providers=providers,
            ),
            data_root=paths.data_root,
        )
    )


def _canonical_consumer_source(
    *,
    project: str | None,
    user_home: str | None,
    today: date,
) -> DomainResult[CanonicalScreenSource]:
    """The screens the canonical shell opens on, which are the composed application's own."""

    composed = _canonical_consumer_actions(project=project, user_home=user_home, today=today)
    if isinstance(composed, DomainErr):
        return composed
    return DomainOk(composed.value.source())


def _canonical_consumer_configuration(paths) -> DomainResult:
    """The effective configuration this machine's Marketplace and installs are composed from."""

    from .application.configuration import (
        ConfigurationPorts,
        ConfigurationRequest,
        load_configuration,
    )
    from .configuration.policy import RuntimeOverrides
    from .io.config_cas import checked_config_writer
    from .io.config_store import read_configuration, recover_configuration, write_configuration

    loaded = load_configuration(
        ConfigurationRequest(paths, RuntimeOverrides(), content_required=False),
        ConfigurationPorts(
            read_configuration,
            write_configuration,
            recover_configuration,
            checked_config_writer,
        ),
    )
    if isinstance(loaded, DomainErr):
        return loaded
    return DomainOk(loaded.value.effective)


def _canonical_marketplace_target() -> MarketplaceTarget:
    """What this machine can actually accept.

    The harnesses come from the measured `MCP_TARGETS`, never from a list written beside them: an
    offer marked compatible with a harness nobody has measured is a compatibility claim AART cannot
    keep.
    """

    from .domain.harness import MCP_TARGETS

    return MarketplaceTarget(
        tuple(sorted({harness for harness, _ in MCP_TARGETS})),
        "darwin" if sys.platform == "darwin" else "linux",
        "project",
        "copy",
    )


def _render_consumer_startup_failure(failure: DomainErr) -> int:
    print("The local AART state could not be loaded.")
    for diagnostic in failure.diagnostics:
        print(f"{diagnostic.severity.value} [{diagnostic.code.value}]: {diagnostic.message}")
        for remediation in diagnostic.remediation:
            print(f"  fix: {remediation}")
    return 2


def _curses_supported() -> bool:
    """Return false only for expected pre-interaction terminal capability failures."""

    try:
        import curses  # noqa: F401  (presence check only)
    except ImportError:
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Entry point — chooses curses vs text and delegates.                           #
# --------------------------------------------------------------------------- #
def run(
    *,
    source_dir: Optional[str] = None,
    repo: Optional[str] = None,
    project: Optional[str] = None,
    user_home: Optional[str] = None,
) -> int:
    """Launch the interactive application; return a process exit code.

    Called by ``cli._run_bare`` on a bare TTY invocation. Both routes run the same canonical
    consumer application: over ``curses`` when the terminal can host it, and over a line-oriented
    terminal when it cannot (D-115). A clean quit returns 0. Sources are loaded only from canonical
    user configuration.

    The application is composed once, before either terminal starts. Composing again on the
    degradation path would read the same machine twice, and the reading is where the local state is
    opened -- so a failure would be reported by whichever half happened to open it first.
    """
    if source_dir is not None or repo is not None:
        print(
            "error: direct catalog directories and repository aliases are no longer supported; "
            "add a canonical registry in Sources instead."
        )
        return 2
    canonical_failures = InternalFailureContext()
    try:
        canonical_terminal = _curses_supported()
    except Exception as error:
        return _render_internal_failure(error, canonical_failures)
    # One composition for whichever terminal answers. Composing again on the degradation path
    # would open the same local state twice, and a failure would then be reported by whichever
    # half opened it first.
    try:
        composed = _canonical_consumer_actions(
            project=project, user_home=user_home, today=date.today()
        )
    except Exception as error:
        # Composition reads local state, so an unexpected defect here carries paths and file
        # contents in its message. A typed startup failure is rendered below; this is the untyped
        # one, and it goes through the same redaction as any other internal defect.
        return _render_internal_failure(error, canonical_failures)
    if isinstance(composed, DomainErr):
        return _render_consumer_startup_failure(composed)
    if canonical_terminal:
        # Past this point a defect is the running application's, not the composition's, and the
        # record has to say so -- including which terminal was hosting it, because the two answer
        # for different things and a person reproducing it needs to know which one to reach.
        canonical_failures.stage = "curses"
        try:
            run_consumer(composed.value)
        except CursesUnavailable:
            # The terminal claimed it could and could not. That is ERR05's one legitimate
            # degradation, and it lands on the same application in a line-oriented terminal
            # rather than on a second curses attempt or a different product.
            pass
        except Exception as error:
            # The outermost crash boundary for the canonical application. ``curses.wrapper`` has
            # already restored the terminal; broad catching is for rendering, never for starting
            # a second application over the same machine.
            return _render_internal_failure(error, canonical_failures)
        else:
            return 0
    canonical_failures.stage = "text"
    try:
        run_consumer_text(composed.value)
    except Exception as error:
        return _render_internal_failure(error, canonical_failures)
    return 0
