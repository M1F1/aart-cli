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

import os
import sys
import traceback
from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, List, Literal, Mapping, Optional, Sequence, Tuple

from . import __version__
from .application.consumer_ui import (
    ConsumerUiEventKind,
    ConsumerUiState,
    RegistryDraft,
    RegistryInitDraft,
    RepositoryScanDraft,
    SourceDraft,
    key_event,
    opening_state,
)
from .application.consumer_views import ConsumerScreen, ConsumerSession
from .application.installed_setup import DeclaredArtifactSetup
from .consumer import (
    ConsumerApplicationService,
    ConsumerOutcome,
    ConsumerReview,
)
from .domain.harness import Scope
from .domain.identifiers import ArtifactCoordinate
from .domain.result import Err as DomainErr
from .domain.result import Ok as DomainOk
from .domain.result import Result as DomainResult
from .io.configured_installation_action import (
    CompletedConfiguredInstallation,
    InstallationHost,
)
from .io.configured_setup import ConfiguredSetupService, configured_consumer_completion
from .io.consumer_actions import (
    ConsumerActionContext,
    LocalConsumerActions,
    RegistryBootstrapCompletion,
    RegistryConnectionSnapshot,
)
from .io.consumer_machine import read_consumer_machine
from .io.consumer_settings import read_consumer_settings
from .io.credentials import MacOsKeychainProvider
from .io.maintainer_views import read_maintainer_views
from .model import (
    Request,
)
from .reporting.application import ReportingApplicationService
from .reporting.model import ReportingPlan, UsageReport
from .reporting.projection import (
    RegistryUsageReport,
    SetupReportState,
    usage_report_from_consumer,
    usage_reports_by_registry_from_consumer,
)
from .reporting.runtime import load_local_reporting_service
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
from .tui_consumer import (
    ConsumerActionCompletion,
    ConsumerScreenSource,
    ConsumerTerminal,
    key_name,
    read_consumer_offers,
    run_consumer_shell,
)
from .tui_failures import (
    WizardOperation,
)
from .tui_marketplace import (
    MarketplaceTarget,
)
from .wizard import (
    WizardStage,
)

_TYPE_ATTR = {
    "skill": "skills",
    "guideline": "guidelines",
    "mcp": "mcp",
    "hook": "hooks",
    "memory": "memory",
}

ReadFn = Callable[[str], str]
WriteFn = Callable[[str], None]


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


class _TerminalConversation:
    """Adapt the shell's draw/key port to the retained line-oriented completion boundary."""

    def __init__(self, terminal: ConsumerTerminal) -> None:
        self._terminal = terminal
        self._lines: list[str] = []

    def write(self, value: str) -> None:
        self._lines.extend(str(value).replace("\r", "\n").split("\n"))
        self._terminal.draw(tuple(self._lines))

    def read(self, prompt: str) -> str:
        value = ""
        state = ConsumerUiState(
            session=ConsumerSession(ConsumerScreen.MARKETPLACE),
            searching=True,
        )
        while True:
            self._terminal.draw((*self._lines, f"{prompt}{value}_"))
            name = key_name(self._terminal.key())
            if not name:
                continue
            event = key_event(name, state)
            if event is None:
                continue
            if event.kind is ConsumerUiEventKind.SEARCH:
                value = event.text
                # Shell confirmation prompts are one-key decisions, not line input disguised as
                # a screen.  The same adapter still supports ordinary setup text inputs below.
                if "[" in prompt and value in {"y", "Y", "n", "N", "s", "S", "v", "V"}:
                    return value
                state = replace(state, search=value)
                continue
            if event.kind is ConsumerUiEventKind.SEARCH_CLOSE:
                if event.accepted is not True:
                    raise EOFError
                return value


@dataclass(frozen=True, slots=True)
class _CanonicalTerminalCompletion:
    service: ConsumerApplicationService | ConfiguredSetupService
    review: ConsumerReview
    outcome: ConsumerOutcome
    reporting: ReportingApplicationService | None
    pending_setup: tuple[DeclaredArtifactSetup, ...]
    source: Callable[[tuple[DeclaredArtifactSetup, ...]], ConsumerScreenSource]

    def complete(self, terminal: ConsumerTerminal) -> ConsumerScreenSource:
        conversation = _TerminalConversation(terminal)
        exit_code = _complete_canonical_consumer_action(
            self.service,
            self.review,
            self.outcome,
            self.reporting,
            read=conversation.read,
            write=conversation.write,
        )
        return self.source(() if exit_code == 0 else self.pending_setup)


@dataclass(frozen=True, slots=True)
class _UnavailableTerminalCompletion:
    message: str
    pending_setup: tuple[DeclaredArtifactSetup, ...]
    source: Callable[[tuple[DeclaredArtifactSetup, ...]], ConsumerScreenSource]

    def complete(self, terminal: ConsumerTerminal) -> ConsumerScreenSource:
        terminal.draw((f"warning: {self.message}",))
        return self.source(self.pending_setup)


def _canonical_setup_run(
    service: ConsumerApplicationService | ConfiguredSetupService,
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
    consumer: ConsumerApplicationService | ConfiguredSetupService,
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


def _read_line(read: ReadFn, prompt: str) -> Optional[str]:
    """Read one line; map EOF (``input`` raising ``EOFError``) to ``None`` (= quit)."""
    try:
        return read(prompt)
    except EOFError:
        return None


# --------------------------------------------------------------------------- #
# curses front-end — gather an immutable session, dispatch only after teardown. #
# --------------------------------------------------------------------------- #


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


"""Rows the artifact pane asks for: one rule, identity, a summary line, and the field block."""


def _refusal(reasons: Optional[Sequence[str]], cursor: int) -> str:
    """What to say when Enter lands on a row that cannot be chosen."""

    reason = reasons[cursor] if reasons is not None and cursor < len(reasons) else ""
    return f"cannot select this row: {reason}" if reason else "this row cannot be selected"


"""The bar while a filter is being typed. Every other key is a letter, so no other key is offered."""


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
        drawable = max(height - 1, 0)
        if not lines or not drawable:
            self._stdscr.refresh()
            return

        # ``frame`` reserves its last line for global navigation. Keep that chrome visible when
        # a long report has more rows than the terminal: clipping help off screen would recreate
        # the first-run trap the footer exists to remove. The terminal only places and clips the
        # already-composed frame; key meaning remains in the pure shell.
        body = lines[:-1][: max(drawable - 1, 0)]
        for row, line in enumerate(body):
            self._stdscr.addstr(row, 0, line[: max(width - 1, 0)])
        self._stdscr.addstr(drawable - 1, 0, lines[-1][: max(width - 1, 0)])
        self._stdscr.refresh()

    def key(self) -> int | str:
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

    def key(self) -> int | str:
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
        named = _TEXT_KEY_WORDS.get(raw.strip().lower())
        return raw if named is None else named


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

    # ncurses otherwise waits around a second after a lone Escape byte in case it is the prefix of
    # a function-key sequence. Esc is the accepted global Back action, so that default makes the
    # application appear to hang on every return. Fifty milliseconds preserves terminal escape
    # sequences while keeping a local Back action immediate.
    curses.set_escdelay(50)

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

    def reread() -> DomainResult[RegistryConnectionSnapshot]:
        """Re-derive everything a changed subscription changes, in one place.

        Connecting a registry, connecting an authoring Source and refreshing a registry all move
        the same three derived things.  Reading them back separately in each closure is how two of
        them would come to disagree about what the third had already been told.
        """

        refreshed = _canonical_consumer_configuration(paths)
        if isinstance(refreshed, DomainErr):
            return refreshed
        refreshed_offers = read_consumer_offers(
            refreshed.value, data_root=paths.data_root, target=target
        )
        if isinstance(refreshed_offers, DomainErr):
            return refreshed_offers
        refreshed_maintainer = read_maintainer_views(
            refreshed.value, data_root=paths.data_root, registry_root=project_root
        )
        if isinstance(refreshed_maintainer, DomainErr):
            return refreshed_maintainer
        return DomainOk(
            RegistryConnectionSnapshot(
                refreshed.value,
                refreshed_offers.value,
                refreshed_maintainer.value,
            )
        )

    def registry_connection(draft: RegistryDraft) -> DomainResult[RegistryConnectionSnapshot]:
        # One authority for both front ends: the TUI supplies a typed draft, while the canonical
        # source-add transaction retains schema validation, snapshot validation, CAS and policy.
        from .commands.source import add_configured_source

        added = add_configured_source(
            Request(
                "source",
                project=project_root,
                user_home=home,
                source_action="add",
                source_alias=draft.alias,
                source_kind="registry-git",
                source_location=draft.location,
                source_make_default=draft.make_default,
                ref=draft.ref or None,
            )
        )
        if isinstance(added, DomainErr):
            return added
        return reread()

    def registry_refresh(alias: str) -> DomainResult[RegistryConnectionSnapshot]:
        # The same authority once more: `aart source sync` and screen 21c refresh a subscription
        # through one transaction (B-084).  It writes no configuration, so a consumer may run it
        # with none of the authority `add` needs, and a failed fetch leaves the last known good
        # snapshot exactly where it was.
        from .commands.source import sync_configured_sources

        synchronized = sync_configured_sources(
            Request(
                "source",
                project=project_root,
                user_home=home,
                source_action="sync",
                source_alias=alias,
            )
        )
        if isinstance(synchronized, DomainErr):
            return synchronized
        return reread()

    def source_connection(draft: SourceDraft) -> DomainResult[RegistryConnectionSnapshot]:
        # The same authority again, with the kind the Maintainer form chose rather than a
        # hardcoded `registry-git`: 164.2's authoring Sources and approved registries are two
        # subscriptions through one transaction, not two transactions (B-083).
        from .commands.source import add_configured_source

        added = add_configured_source(
            Request(
                "source",
                project=project_root,
                user_home=home,
                source_action="add",
                source_alias=draft.alias,
                source_kind=draft.kind,
                source_location=draft.location,
                # An authoring Source is never the default registry; that flag is screen 21a's.
                source_make_default=False,
                ref=draft.ref or None,
            )
        )
        if isinstance(added, DomainErr):
            return added
        return reread()

    def registry_bootstrap(
        draft: RegistryInitDraft,
    ) -> DomainResult[RegistryBootstrapCompletion]:
        # The five canonical stages in their one meaningful order, run against this project's own
        # checkout (B-090). The re-read afterwards is the same one every subscription change uses:
        # a registry that has just come into existence is a thing screen 46 can now draw.
        from .io.registry_bootstrap import bootstrap_registry_workspace

        report = bootstrap_registry_workspace(
            root=project_root,
            registry_id=draft.registry_id,
            display_name=draft.display_name,
            usage_reporting_repository=draft.usage_reporting or None,
            commit=draft.commit,
        )
        if isinstance(report, DomainErr):
            return report
        if not report.value.passed:
            # Nothing is re-read from a run that stopped part way: the screens would then be
            # describing a registry the operator was simultaneously being told did not finish.
            return DomainOk(RegistryBootstrapCompletion(report.value))
        refreshed = reread()
        if isinstance(refreshed, DomainErr):
            return refreshed
        return DomainOk(RegistryBootstrapCompletion(report.value, refreshed.value))

    def repository_scan(draft: RepositoryScanDraft):
        """Read one remote authoring repository without adding it to configuration (B-095)."""

        from .io.registry_adoption import scan_repository

        return scan_repository(
            url=draft.url,
            ref=draft.ref,
            registry_root=project_root,
        )

    class RepositoryAdoption:
        """Bind both review halves to this project registry; neither publishes it."""

        @staticmethod
        def prepare(scan, selected):
            from .io.registry_adoption import prepare_adoption

            return prepare_adoption(scan, selected, registry_root=project_root)

        @staticmethod
        def apply(prepared, review_digest):
            from .io.registry_adoption import apply_adoption

            return apply_adoption(
                prepared,
                review_digest,
                registry_root=project_root,
            )

    def adopted_artifacts():
        from .io.registry_adoption import list_adopted_artifacts

        return list_adopted_artifacts(registry_root=project_root)

    def repository_upstream_check(coordinate: str):
        from .io.registry_adoption import check_adopted_upstream

        return check_adopted_upstream(coordinate, registry_root=project_root)

    listed_adoptions = adopted_artifacts()
    initial_adoptions = listed_adoptions.value if isinstance(listed_adoptions, DomainOk) else ()

    def completion_factory(
        completed: CompletedConfiguredInstallation,
        action: Literal["install", "update"],
        source: Callable[[tuple[DeclaredArtifactSetup, ...]], ConsumerScreenSource],
    ) -> ConsumerActionCompletion:
        # A registry can be connected without restarting the shell. Re-read here so setup and
        # reporting after the next install use the configuration that authorized that install,
        # never the snapshot from before onboarding.
        current_configuration = _canonical_consumer_configuration(paths)
        if isinstance(current_configuration, DomainErr):
            return _UnavailableTerminalCompletion(
                "setup/reporting completion is unavailable; the installed payload is unchanged",
                completed.pending_setup,
                source,
            )
        projected = configured_consumer_completion(
            completed,
            current_configuration.value,
            InstallationHost(paths.data_root, project_root, home, Scope.PROJECT, target.profiles),
            action=action,
        )
        if isinstance(projected, DomainErr):
            return _UnavailableTerminalCompletion(
                "setup/reporting completion is unavailable; the installed payload is unchanged",
                completed.pending_setup,
                source,
            )
        review, outcome, service = projected.value
        reporting_result = load_local_reporting_service(
            user_home=home,
            configuration=current_configuration.value.configuration,
        )
        reporting = reporting_result.value if isinstance(reporting_result, DomainOk) else None
        return _CanonicalTerminalCompletion(
            service,
            review,
            outcome,
            reporting,
            completed.pending_setup,
            source,
        )

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
            completion_factory=completion_factory,
            registry_connection=registry_connection,
            registry_refresh=registry_refresh,
            source_connection=source_connection,
            registry_bootstrap=registry_bootstrap,
            repository_scan=repository_scan,
            repository_adoption=RepositoryAdoption(),
            adopted_artifacts=initial_adoptions,
            repository_upstream_check=repository_upstream_check,
            repository_adopted_list=adopted_artifacts,
        )
    )


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

    The harnesses come from the measured target tables, never from a list written beside them: an
    offer marked compatible with a harness nobody has measured is a compatibility claim AART cannot
    keep.

    All four tables, not only `MCP_TARGETS`. A harness that starts no MCP server can still be one
    this machine installs Skills and instructions into -- Codex is measured that way (`B-086`) --
    and deriving the set from the MCP table alone hid it behind a capability it does not need. An
    artifact this machine cannot actually place for a harness is still refused by name at
    installation, which is where that refusal belongs.
    """

    from .domain.harness import DELIVERY_TARGETS, HOOK_TARGETS, MCP_TARGETS, MEMORY_TARGETS

    measured = {harness for harness, _ in MCP_TARGETS}
    measured.update(harness for harness, _ in MEMORY_TARGETS)
    measured.update(harness for harness, _ in HOOK_TARGETS)
    measured.update(harness for harness, _, _ in DELIVERY_TARGETS)
    return MarketplaceTarget(
        tuple(sorted(measured)),
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
