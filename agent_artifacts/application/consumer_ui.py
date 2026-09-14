"""Pure interaction reducer for the persistent consumer application.

Terminal adapters hand this module key names and interpret the commands it returns.  The reducer
itself performs no I/O and knows nothing about curses.  Selection, search, help, profile and
navigation therefore remain headlessly testable, and toggling presentation detail cannot touch
semantic plan identity.

Key interpretation lives here too, in :func:`key_event`, because it depends on the mode: while the
search filter is open every printable key is a letter of the query, and a shell that decided that
for itself would eventually let `q` quit instead of typing a q.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from agent_artifacts.domain.registry import PromotionMode

from .consumer_views import (
    SETTING_ROWS,
    SUCCESS_CHOICES,
    ApplicationScreen,
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    is_screen_identifier,
    keeps_focus,
    navigation_targets,
)
from .maintainer_views import (
    MaintainerCandidateFilter,
    MaintainerScreen,
    parse_candidate_filter_row,
    parse_validation_row,
)

__all__ = [
    "ConsumerActionKind",
    "ConsumerUiCommand",
    "ConsumerUiCommandKind",
    "ConsumerUiEvent",
    "ConsumerUiEventKind",
    "ConsumerUiState",
    "KeyBinding",
    "RegistryDraft",
    "RegistryInitDraft",
    "RepositoryScanDraft",
    "SourceDraft",
    "WorkflowProgressStep",
    "WorkflowStepStatus",
    "key_event",
    "key_bindings",
    "opening_state",
    "reduce_consumer_ui",
    "workflow_progress",
]


class ConsumerActionKind(str, Enum):
    """Lifecycle intents the UI may request from the application shell."""

    INSTALL = "install"
    UPDATE = "update"
    VERIFY_REPAIR = "verify-repair"
    UNINSTALL = "uninstall"
    SOURCE_SYNC = "source-sync"
    CANDIDATE_PROMOTION = "candidate-promotion"
    BULK_PROMOTION = "bulk-promotion"
    REGISTRY_ADD = "registry-add"
    REGISTRY_SYNC = "registry-sync"
    REGISTRY_REMOVE = "registry-remove"
    SOURCE_ADD = "source-add"
    REGISTRY_INIT = "registry-init"
    REGISTRY_REBUILD = "registry-rebuild"
    REPOSITORY_SCAN = "repository-scan"
    REPOSITORY_ADOPT = "repository-adopt"
    REPOSITORY_UPSTREAM_CHECK = "repository-upstream-check"
    REPOSITORY_ADOPT_UPDATE = "repository-adopt-update"


class ConsumerUiEventKind(str, Enum):
    NAVIGATE = "navigate"
    BACK = "back"
    MOVE = "move"
    SET_ROWS = "set-rows"
    SET_SELECTION = "set-selection"
    TOGGLE_PROFILE = "toggle-profile"
    TOGGLE_SELECTION = "toggle-selection"
    TOGGLE_SETTING = "toggle-setting"
    TOGGLE_CANDIDATE_FILTER = "toggle-candidate-filter"
    TOGGLE_PROMOTION_MODE = "toggle-promotion-mode"
    SEARCH = "search"
    SEARCH_OPEN = "search-open"
    SEARCH_CLOSE = "search-close"
    HELP = "help"
    QUIT = "quit"
    CONFIRM_QUIT = "confirm-quit"
    REQUEST_ACTION = "request-action"
    ACTION_PREPARED = "action-prepared"
    CONFIRM_ACTION = "confirm-action"
    ACTION_RECORDED = "action-recorded"
    ACTION_FAILED = "action-failed"
    EDIT_REGISTRY = "edit-registry"
    EDIT_SOURCE = "edit-source"
    EDIT_REGISTRY_INIT = "edit-registry-init"
    EDIT_REPOSITORY_SCAN = "edit-repository-scan"


@dataclass(frozen=True, slots=True)
class KeyBinding:
    """One key the current screen accepts and the short meaning its footer displays."""

    key: str
    label: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str)
            or not value
            or any(character in value for character in "\r\n")
            for value in (self.key, self.label)
        ):
            raise ValueError("a key binding needs a safe key and label")


@dataclass(frozen=True, slots=True)
class RegistryDraft:
    """Credential-free input for one approved Git registry subscription."""

    alias: str = ""
    location: str = ""
    ref: str = ""
    make_default: bool = True

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or any(char in value for char in "\r\n")
            for value in (
                self.alias,
                self.location,
                self.ref,
            )
        ) or not isinstance(self.make_default, bool):
            raise ValueError("registry draft is invalid")


#: The two authoring kinds screen 31a offers, in the order Space cycles them.  `registry-git` is
#: deliberately absent: an approved registry is screen 21a's, and 164.2 keeps the two apart.
AUTHORING_SOURCE_KINDS: tuple[str, ...] = ("source-git", "source-local")


@dataclass(frozen=True, slots=True)
class SourceDraft:
    """Credential-free input for one authoring Source subscription (`source-git`/`source-local`).

    It is a separate value from `RegistryDraft` rather than a widened one because the two forms
    collect different things and mean different trust: a registry draft carries `make_default`,
    which an authoring Source can never be, and a source draft carries the kind, which a registry
    never chooses.
    """

    alias: str = ""
    kind: str = AUTHORING_SOURCE_KINDS[0]
    location: str = ""
    ref: str = ""

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or any(char in value for char in "\r\n")
            for value in (self.alias, self.kind, self.location, self.ref)
        ):
            raise ValueError("source draft is invalid")


@dataclass(frozen=True, slots=True)
class RegistryInitDraft:
    """What creating a registry in this project needs, and the one choice it offers (B-090).

    `commit` is the only effect the operator opts into.  The five stages write managed files into
    the checkout either way; whether that becomes a Git commit is a decision about the repository's
    own history, and pushing or merging it is a further decision that is never AART's to make.
    """

    registry_id: str = ""
    display_name: str = ""
    usage_reporting: str = ""
    commit: bool = False

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or any(char in value for char in "\r\n")
            for value in (self.registry_id, self.display_name, self.usage_reporting)
        ) or not isinstance(self.commit, bool):
            raise ValueError("registry init draft is invalid")

    def settled(self) -> "RegistryInitDraft":
        """The same three answers with the spaces around them dropped (`QA-058`).

        Screen 46a's status bar offers `[Space] Toggle`, and on a text row a printable key is
        text, so the space it types lands in the answer.  None of the three can carry one at
        either end -- an identifier is a slug, a display name is one line, a reporting repository
        is `owner/name` -- so surrounding whitespace is not part of what the operator named and
        the identity is judged without it.  Settling happens here, at the boundary that judges,
        rather than while typing, because `Manual Registry` has to stay typeable one key at a
        time.
        """

        return replace(
            self,
            registry_id=self.registry_id.strip(),
            display_name=self.display_name.strip(),
            usage_reporting=self.usage_reporting.strip(),
        )


@dataclass(frozen=True, slots=True)
class RepositoryScanDraft:
    """The credential-free remote identity read once for artifact-scoped adoption."""

    url: str = ""
    ref: str = ""

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or any(char in value for char in "\r\n")
            for value in (self.url, self.ref)
        ):
            raise ValueError("repository scan draft is invalid")


class ConsumerUiCommandKind(str, Enum):
    LOAD_SCREEN = "load-screen"
    CONFIRM_QUIT = "confirm-quit"
    EXIT = "exit"
    PREPARE_ACTION = "prepare-action"
    EXECUTE_ACTION = "execute-action"
    PERSIST_SETTINGS = "persist-settings"


class WorkflowStepStatus(str, Enum):
    """Where one declared screen sits relative to the current workflow position."""

    COMPLETED = "completed"
    CURRENT = "current"
    UPCOMING = "upcoming"


@dataclass(frozen=True, slots=True)
class WorkflowProgressStep:
    screen: ApplicationScreen
    status: WorkflowStepStatus

    def __post_init__(self) -> None:
        if not isinstance(self.screen, (ConsumerScreen, MaintainerScreen)) or not isinstance(
            self.status, WorkflowStepStatus
        ):
            raise ValueError("workflow progress needs a screen and status")


@dataclass(frozen=True, slots=True)
class ConsumerUiEvent:
    kind: ConsumerUiEventKind
    screen: ApplicationScreen | None = None
    action: ConsumerActionKind | None = None
    key: str = ""
    text: str = ""
    accepted: bool | None = None
    rows: tuple[str, ...] = ()
    semantic_identity: str = ""
    selection_identity: str = ""
    review_digest: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, ConsumerUiEventKind)
            or (
                self.screen is not None
                and not isinstance(self.screen, (ConsumerScreen, MaintainerScreen))
            )
            or (self.action is not None and not isinstance(self.action, ConsumerActionKind))
            or not isinstance(self.key, str)
            or any(character in self.key for character in "\r\n")
            or not isinstance(self.text, str)
            or any(character in self.text for character in "\r\n")
            or not (self.accepted is None or isinstance(self.accepted, bool))
            or not _rows_valid(self.rows)
            or not _safe_identity(self.semantic_identity)
            or not _safe_identity(self.selection_identity)
            or not _safe_identity(self.review_digest)
        ):
            raise ValueError("consumer UI event is invalid")


@dataclass(frozen=True, slots=True)
class ConsumerUiCommand:
    kind: ConsumerUiCommandKind
    screen: ApplicationScreen | None = None
    action: ConsumerActionKind | None = None
    selection: tuple[str, ...] = ()
    focus: str = ""
    review_digest: str = ""
    promotion_mode: PromotionMode | None = None
    registry_draft: RegistryDraft | None = None
    source_draft: SourceDraft | None = None
    registry_init_draft: RegistryInitDraft | None = None
    repository_scan_draft: RepositoryScanDraft | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, ConsumerUiCommandKind)
            or (
                self.screen is not None
                and not isinstance(self.screen, (ConsumerScreen, MaintainerScreen))
            )
            or (self.action is not None and not isinstance(self.action, ConsumerActionKind))
            or not _rows_valid(self.selection)
            or not isinstance(self.focus, str)
            or any(character in self.focus for character in "\r\n")
            or not _safe_identity(self.review_digest)
            or (
                self.promotion_mode is not None
                and not isinstance(self.promotion_mode, PromotionMode)
            )
            or (
                self.registry_draft is not None
                and not isinstance(self.registry_draft, RegistryDraft)
            )
            or (self.source_draft is not None and not isinstance(self.source_draft, SourceDraft))
            or (
                self.registry_init_draft is not None
                and not isinstance(self.registry_init_draft, RegistryInitDraft)
            )
            or (
                self.repository_scan_draft is not None
                and not isinstance(self.repository_scan_draft, RepositoryScanDraft)
            )
        ):
            raise ValueError("consumer UI command is invalid")
        if (
            self.kind
            in (
                ConsumerUiCommandKind.PREPARE_ACTION,
                ConsumerUiCommandKind.EXECUTE_ACTION,
            )
            and self.action is None
        ):
            raise ValueError("an action command needs a typed action")
        if self.kind is ConsumerUiCommandKind.EXECUTE_ACTION and not self.review_digest:
            raise ValueError("executing an action needs the reviewed plan identity")


_INITIAL_SESSION = ConsumerSession(ConsumerScreen.DASHBOARD)
_DEFAULT_SETTINGS = ConsumerSettings()

#: Where a filter is meaningful, and where ticking rows is.  Both are properties of the screen,
#: not of the keyboard, so the same key does nothing where the screen has nothing to do with it.
_SEARCHABLE = frozenset(
    {
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.INSTALLED,
        ConsumerScreen.UPDATES,
        ConsumerScreen.CREDENTIALS,
        ConsumerScreen.ACTIVITY,
        MaintainerScreen.CANDIDATES,
    }
)
_SELECTABLE = frozenset(
    {
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.COLLECTION_PREVIEW,
        ConsumerScreen.COLLECTION_CUSTOMIZE,
        ConsumerScreen.UPDATES,
        # Screen 47 assembles one registry transaction, so selecting rows is what it is for.
        MaintainerScreen.BULK_PROMOTION,
        MaintainerScreen.SCAN_RESULT,
    }
)


def _rows_valid(rows: tuple[str, ...]) -> bool:
    return (
        isinstance(rows, tuple)
        and len(set(rows)) == len(rows)
        and all(
            isinstance(item, str) and item and not any(character in item for character in "\r\n")
            for item in rows
        )
    )


def _safe_identity(value: str) -> bool:
    return isinstance(value, str) and not any(character in value for character in "\r\n")


@dataclass(frozen=True, slots=True)
class ConsumerUiState:
    session: ConsumerSession = _INITIAL_SESSION
    settings: ConsumerSettings = _DEFAULT_SETTINGS
    selection: tuple[str, ...] = ()
    search: str = ""
    rows: tuple[str, ...] = ()
    cursor: int = 0
    focus: str = ""
    searching: bool = False
    help_visible: bool = False
    quit_pending: bool = False
    exited: bool = False
    action: ConsumerActionKind | None = None
    #: The action whose attempted run stopped on this screen. It is not `action`: that plan is
    #: gone, so there is nothing left to confirm, and a review still advertising a confirmation is
    #: offering a key whose only possible answer is that nothing was prepared (`QA-033`).
    failed_action: ConsumerActionKind | None = None
    #: What the Candidate list is narrowed to. Screen 53 edits it; screen 35 obeys it.
    candidate_filter: MaintainerCandidateFilter = MaintainerCandidateFilter()
    #: Which promotion the Maintainer is reviewing. Screen 42 chooses it; screens 41 and 43 obey
    #: it. Both modes are composed, so this selects a projection rather than causing one.
    promotion_mode: PromotionMode = PromotionMode.VENDORED
    registry_draft: RegistryDraft = RegistryDraft()
    source_draft: SourceDraft = SourceDraft()
    registry_init_draft: RegistryInitDraft = RegistryInitDraft()
    #: Screen 45 confirms one local commit and then keeps its receipt on screen. This flag lets key
    #: interpretation know whether Enter commits or leaves for the Registry: publication is manual
    #: Git and has no state here (D-255).
    registry_commit_applied: bool = False
    repository_scan_draft: RepositoryScanDraft = RepositoryScanDraft()
    #: The directory this session was launched from, already written for a reader. It is context
    #: for every screen -- an install and a Registry edit land relative to it -- so it is carried
    #: on the state rather than fetched where it is drawn, which keeps the frame off the
    #: filesystem (`QA-053`).
    workspace: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.session, ConsumerSession)
            or not isinstance(self.settings, ConsumerSettings)
            or not _rows_valid(self.rows)
            or not isinstance(self.cursor, int)
            or isinstance(self.cursor, bool)
            or not 0 <= self.cursor < max(len(self.rows), 1)
            or not isinstance(self.focus, str)
            or any(character in self.focus for character in "\r\n")
            or not isinstance(self.searching, bool)
            or len(set(self.selection)) != len(self.selection)
            or any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in self.selection
            )
            or not isinstance(self.search, str)
            or any(character in self.search for character in "\r\n")
            or not isinstance(self.help_visible, bool)
            or not isinstance(self.quit_pending, bool)
            or not isinstance(self.exited, bool)
            or (self.action is not None and not isinstance(self.action, ConsumerActionKind))
            or (
                self.failed_action is not None
                and not isinstance(self.failed_action, ConsumerActionKind)
            )
            # A plan cannot be both awaiting confirmation and already finished with.
            or (self.action is not None and self.failed_action is not None)
            or not isinstance(self.candidate_filter, MaintainerCandidateFilter)
            or not isinstance(self.workspace, str)
            or any(character in self.workspace for character in "\r\n")
            or not isinstance(self.registry_draft, RegistryDraft)
            or not isinstance(self.source_draft, SourceDraft)
            or not isinstance(self.registry_init_draft, RegistryInitDraft)
            or not isinstance(self.registry_commit_applied, bool)
            or not isinstance(self.repository_scan_draft, RepositoryScanDraft)
        ):
            raise ValueError("consumer UI state is invalid")
        if self.session.profile is not self.settings.profile:
            object.__setattr__(self, "settings", self.settings.with_profile(self.session.profile))
        if not self.settings.maintainer_mode and any(
            isinstance(screen, MaintainerScreen)
            for screen in (self.session.screen, *self.session.history)
        ):
            raise ValueError("a Maintainer screen needs Maintainer Mode enabled")

    @property
    def current_row(self) -> str:
        """The row identity the cursor is on, or empty where the screen has no rows."""

        return self.rows[self.cursor] if self.rows else ""


#: Multi-screen jobs whose progress is useful to the operator. Every adjacent pair is an accepted
#: edge in ``navigation_targets``; optional detail/question screens are omitted rather than shown as
#: completed when a real run skipped them. The session history supplies what was actually visited.
_WORKFLOW_ROUTES: tuple[tuple[ApplicationScreen, ...], ...] = (
    (
        MaintainerScreen.CANDIDATES,
        MaintainerScreen.CANDIDATE_DETAILS,
        MaintainerScreen.CANDIDATE_DIFF,
        MaintainerScreen.VALIDATION,
        MaintainerScreen.POLICY_REVIEW,
        MaintainerScreen.PROMOTION_REVIEW,
        MaintainerScreen.PROMOTION_MODE,
        MaintainerScreen.REGISTRY_DIFF,
        MaintainerScreen.REGISTRY_VALIDATION,
        MaintainerScreen.REGISTRY_COMMIT,
    ),
    (
        MaintainerScreen.REGISTRY,
        MaintainerScreen.BULK_PROMOTION,
        MaintainerScreen.REGISTRY_VALIDATION,
        MaintainerScreen.REGISTRY_COMMIT,
    ),
    (
        MaintainerScreen.SOURCES,
        MaintainerScreen.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD_REVIEW,
    ),
    (
        MaintainerScreen.SOURCES,
        MaintainerScreen.SOURCE_SYNC,
        MaintainerScreen.SOURCE_SYNC_RESULT,
    ),
    (
        MaintainerScreen.REGISTRY,
        MaintainerScreen.REGISTRY_INIT,
        MaintainerScreen.REGISTRY_INIT_REVIEW,
    ),
    (
        MaintainerScreen.REGISTRY,
        MaintainerScreen.REGISTRY_REBUILD,
        MaintainerScreen.REGISTRY_REBUILD_REVIEW,
    ),
    (
        MaintainerScreen.REGISTRY,
        MaintainerScreen.REPOSITORY_SCAN,
        MaintainerScreen.SCAN_RESULT,
        MaintainerScreen.ADOPTION_REVIEW,
    ),
    (
        ConsumerScreen.REGISTRIES,
        ConsumerScreen.REGISTRY_ADD,
        ConsumerScreen.REGISTRY_REVIEW,
    ),
    (
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.REVIEW_SELECTION,
        ConsumerScreen.AUTOMATIC_INSPECTION,
        ConsumerScreen.READY,
        ConsumerScreen.INSTALLING,
        ConsumerScreen.SUCCESS,
    ),
    (
        ConsumerScreen.UPDATES,
        ConsumerScreen.UPDATE_INPUTS,
        ConsumerScreen.UPDATING,
        ConsumerScreen.ACTIVITY_DETAILS,
    ),
    (
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ConsumerScreen.UNINSTALL_REVIEW,
        ConsumerScreen.UNINSTALLING,
        ConsumerScreen.ACTIVITY_DETAILS,
    ),
    (
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.ACTIVITY_DETAILS,
    ),
    (
        ConsumerScreen.DOCTOR,
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.ACTIVITY_DETAILS,
    ),
)


def _workflow_route(state: ConsumerUiState) -> tuple[ApplicationScreen, ...] | None:
    """Choose the declared route best supported by the journey actually in session history."""

    for route in _WORKFLOW_ROUTES:
        for current, target in zip(route[:-1], route[1:], strict=True):
            if target not in navigation_targets(current, maintainer_mode=True):
                raise ValueError("workflow progress route is outside the navigation graph")
    candidates = tuple(
        route
        for route in _WORKFLOW_ROUTES
        if state.session.screen in route[1:] and route[0] in state.session.history
    )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda route: sum(screen in state.session.history for screen in route),
    )


def workflow_progress(state: ConsumerUiState) -> tuple[WorkflowProgressStep, ...]:
    """Project completed/current/upcoming screens from the reducer's real navigation state."""

    if not isinstance(state, ConsumerUiState):
        raise ValueError("workflow progress needs consumer UI state")
    route = _workflow_route(state)
    if route is None:
        return ()
    return tuple(
        WorkflowProgressStep(
            screen,
            (
                WorkflowStepStatus.CURRENT
                if screen is state.session.screen
                else (
                    WorkflowStepStatus.COMPLETED
                    if screen in state.session.history
                    else WorkflowStepStatus.UPCOMING
                )
            ),
        )
        for screen in route
    )


def _same_workflow(current: ApplicationScreen, target: ApplicationScreen) -> bool:
    return any(current in route and target in route for route in _WORKFLOW_ROUTES)


# These reverse-navigation relationships retain one Source or Candidate through optional detail
# screens without adding those screens to the progress chrome (`QA-073`, CP-23/01).
_SUBJECT_PRESERVING_BACK_EDGES = frozenset(
    {
        (MaintainerScreen.SOURCE_DETAILS, MaintainerScreen.SOURCES),
        (MaintainerScreen.SOURCE_SYNC, MaintainerScreen.SOURCE_DETAILS),
        (MaintainerScreen.CANDIDATE_LIFECYCLE, MaintainerScreen.CANDIDATE_DETAILS),
        (MaintainerScreen.PROVENANCE, MaintainerScreen.CANDIDATE_DETAILS),
        (MaintainerScreen.VERSION_CONFLICT, MaintainerScreen.CANDIDATE_DETAILS),
        (MaintainerScreen.PROVENANCE, MaintainerScreen.CANDIDATE_LIFECYCLE),
        (MaintainerScreen.VERSION_CONFLICT, MaintainerScreen.PROVENANCE),
        (MaintainerScreen.VALIDATION_DETAILS, MaintainerScreen.VALIDATION),
        (MaintainerScreen.POLICY_REVIEW, MaintainerScreen.VALIDATION_DETAILS),
    }
)


_BARE_CANDIDATE_FOCUS_SCREENS = frozenset(
    {
        MaintainerScreen.CANDIDATE_DETAILS,
        MaintainerScreen.CANDIDATE_DIFF,
        MaintainerScreen.CANDIDATE_LIFECYCLE,
        MaintainerScreen.PROVENANCE,
        MaintainerScreen.VERSION_CONFLICT,
    }
)


def _back_focus(state: ConsumerUiState, target: ApplicationScreen) -> str:
    """Keep one workflow subject, reducing a validation-row pair to its Candidate when needed."""

    if not (
        _same_workflow(state.session.screen, target)
        or (state.session.screen, target) in _SUBJECT_PRESERVING_BACK_EDGES
    ):
        return ""
    focus = state.focus
    if target in _BARE_CANDIDATE_FOCUS_SCREENS:
        row = parse_validation_row(focus)
        if row is not None:
            return row.candidate_id
    return focus


def opening_state(settings: ConsumerSettings, *, workspace: str = "") -> ConsumerUiState:
    """The state a session opens in, at the preferences somebody last chose.

    The session's profile and the stored detail level have to be set together: state validation
    lets the session win, so seeding only the settings would open Fast for somebody who chose
    Verbose and then silently rewrite their preference back.
    """

    if not isinstance(settings, ConsumerSettings):
        raise ValueError("opening the consumer application needs consumer settings")
    return ConsumerUiState(
        session=replace(_INITIAL_SESSION, profile=settings.profile),
        settings=settings,
        workspace=workspace,
    )


#: The draft each form owns, and therefore what "a new one" means when that form is opened.
#: Opening a form and returning to a refused one look alike from the screen and are opposite
#: requirements: `QA-028` wants the first empty, `QA-018`/`D-184` wants the second untouched. This
#: is read only on forward navigation, which is the difference between them.
_FORM_DRAFTS: dict[ApplicationScreen, Callable[[ConsumerUiState], ConsumerUiState]] = {
    ConsumerScreen.REGISTRY_ADD: lambda state: replace(state, registry_draft=RegistryDraft()),
    MaintainerScreen.SOURCE_ADD: lambda state: replace(state, source_draft=SourceDraft()),
    MaintainerScreen.REGISTRY_INIT: lambda state: replace(
        state, registry_init_draft=RegistryInitDraft()
    ),
    MaintainerScreen.REPOSITORY_SCAN: lambda state: replace(
        state, repository_scan_draft=RepositoryScanDraft()
    ),
}


def _navigate(
    state: ConsumerUiState, screen: ApplicationScreen | None
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if screen is None or screen not in navigation_targets(
        state.session.screen, maintainer_mode=state.settings.maintainer_mode
    ):
        return state, ()
    # What the next screen is about: the row somebody was on, or -- where this screen has no rows
    # of its own -- whatever the screen before it was already about.  A detail opened from a
    # detail is still about the same thing.
    focus = (
        state.focus
        if keeps_focus(state.session.screen, screen)
        else state.current_row or state.focus
    )
    # A dashboard's rows are destinations, so the row somebody was on is where they are going and
    # not what they are looking at. Carrying one forward put `31-sources` into a refusal as if it
    # were a Source alias, and the message then named no Source at all (`QA-077`).
    if is_screen_identifier(focus):
        focus = ""
    updated = replace(
        state,
        session=state.session.navigate(screen),
        focus=focus,
        search="",
        help_visible=False,
        quit_pending=False,
        failed_action=None,
    )
    # Only the form being entered is emptied. Each form owns one draft, and entering one is not a
    # reason to discard what somebody typed into another (`QA-028`).
    empty = _FORM_DRAFTS.get(screen)
    if empty is not None:
        updated = empty(updated)
    return updated, (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, screen),)


#: The dashboard each list answers to: the one that declares it as a forward route. A list is a
#: place the reader goes *to* from a dashboard, so leaving it goes back there however they arrived
#: -- Candidates is reachable sideways from the Registry screen, and Esc from it still means "done
#: looking at candidates" rather than "back into whatever finished a moment ago" (`QA-072`).
_OWNING_DASHBOARD: dict[ApplicationScreen, ApplicationScreen] = {
    **{
        target: ConsumerScreen.DASHBOARD
        for target in navigation_targets(ConsumerScreen.DASHBOARD, maintainer_mode=False)
    },
    **{
        target: MaintainerScreen.DASHBOARD
        for target in navigation_targets(MaintainerScreen.DASHBOARD, maintainer_mode=True)
    },
}


def _back(state: ConsumerUiState) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    # CP-23 task 06: the install already ran, so the screens behind Success are a finished wizard
    # -- Installing, and Ready still asking to confirm. Leaving goes where Done does.
    if state.session.screen is ConsumerScreen.SUCCESS:
        return _navigate(state, ConsumerScreen.MARKETPLACE)
    owner = _OWNING_DASHBOARD.get(state.session.screen)
    if owner is not None and owner in state.session.history:
        session = state.session.navigate(owner)
    else:
        session = state.session.back()
    if session is state.session:
        return state, ()
    updated = replace(
        state,
        session=session,
        # A wizard-like journey remains about the same stable subject while walking backwards.
        # Browsing back to an unrelated list still clears stale detail focus as before.
        focus=_back_focus(state, session.screen),
        search="",
        help_visible=False,
        quit_pending=False,
        failed_action=None,
    )
    return updated, (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, session.screen),)


def _set_rows(
    state: ConsumerUiState, rows: tuple[str, ...]
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Take the rows a screen is currently showing, keeping the cursor on the same row if it is
    still there.  A filter hides rows; it never moves what somebody was looking at, and it never
    unticks anything."""

    standing = state.current_row
    if standing not in rows:
        standing = state.focus
    cursor = rows.index(standing) if standing in rows else 0
    return replace(state, rows=rows, cursor=cursor), ()


def _set_selection(
    state: ConsumerUiState, selected: tuple[str, ...]
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Replace what is ticked, for a screen that opens with an opinion about it.

    A Collection opens with every member ticked, because opening a Collection is asking for the
    Collection. Untick from there; this event is how a screen says so, and it is only ever sent as
    a screen is entered.
    """

    if state.session.screen not in _SELECTABLE:
        return state, ()
    return replace(state, selection=tuple(dict.fromkeys(selected)), quit_pending=False), ()


def _move(
    state: ConsumerUiState, direction: str
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if not state.rows or direction not in ("up", "down"):
        return state, ()
    step = -1 if direction == "up" else 1
    return replace(state, cursor=(state.cursor + step) % len(state.rows)), ()


def _toggle_selection(
    state: ConsumerUiState, key: str
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    key = key or state.current_row
    if state.session.screen not in _SELECTABLE or not key:
        return state, ()
    if key in state.selection:
        selected = tuple(item for item in state.selection if item != key)
    else:
        selected = (*state.selection, key)
    return replace(state, selection=selected, quit_pending=False), ()


_ACTION_REVIEW: dict[tuple[ConsumerActionKind, ApplicationScreen], ApplicationScreen] = {
    (ConsumerActionKind.REGISTRY_ADD, ConsumerScreen.REGISTRY_ADD): ConsumerScreen.REGISTRY_REVIEW,
    # A refresh is requested from the list, where the row being refreshed is the row under the
    # cursor; its review is a screen of its own so the fetch is stated before it happens (B-084).
    (ConsumerActionKind.REGISTRY_SYNC, ConsumerScreen.REGISTRIES): ConsumerScreen.REGISTRY_SYNC,
    (ConsumerActionKind.REGISTRY_REMOVE, ConsumerScreen.REGISTRIES): ConsumerScreen.REGISTRY_REMOVE,
    (
        ConsumerActionKind.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD,
    ): MaintainerScreen.SOURCE_ADD_REVIEW,
    (
        ConsumerActionKind.REGISTRY_INIT,
        MaintainerScreen.REGISTRY_INIT,
    ): MaintainerScreen.REGISTRY_INIT_REVIEW,
    (
        ConsumerActionKind.REGISTRY_REBUILD,
        MaintainerScreen.REGISTRY_REBUILD,
    ): MaintainerScreen.REGISTRY_REBUILD_REVIEW,
    (
        ConsumerActionKind.REPOSITORY_SCAN,
        MaintainerScreen.REPOSITORY_SCAN,
    ): MaintainerScreen.SCAN_RESULT,
    (
        ConsumerActionKind.REPOSITORY_ADOPT,
        MaintainerScreen.SCAN_RESULT,
    ): MaintainerScreen.ADOPTION_REVIEW,
    (
        ConsumerActionKind.REPOSITORY_UPSTREAM_CHECK,
        MaintainerScreen.ADOPTED_ARTIFACTS,
    ): MaintainerScreen.UPSTREAM_CHECK,
    (
        ConsumerActionKind.REPOSITORY_ADOPT_UPDATE,
        MaintainerScreen.UPSTREAM_CHECK,
    ): MaintainerScreen.ADOPTION_REVIEW,
    (ConsumerActionKind.INSTALL, ConsumerScreen.MARKETPLACE): ConsumerScreen.REVIEW_SELECTION,
    (ConsumerActionKind.INSTALL, ConsumerScreen.ARTIFACT_DETAILS): ConsumerScreen.REVIEW_SELECTION,
    (
        ConsumerActionKind.INSTALL,
        ConsumerScreen.COLLECTION_PREVIEW,
    ): ConsumerScreen.REVIEW_SELECTION,
    (
        ConsumerActionKind.INSTALL,
        ConsumerScreen.COLLECTION_CUSTOMIZE,
    ): ConsumerScreen.REVIEW_SELECTION,
    (ConsumerActionKind.UPDATE, ConsumerScreen.UPDATES): ConsumerScreen.UPDATE_INPUTS,
    (
        ConsumerActionKind.VERIFY_REPAIR,
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
    ): ConsumerScreen.VERIFY_REPAIR,
    (ConsumerActionKind.VERIFY_REPAIR, ConsumerScreen.DOCTOR): ConsumerScreen.VERIFY_REPAIR,
    (
        ConsumerActionKind.UNINSTALL,
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
    ): ConsumerScreen.UNINSTALL_REVIEW,
    (
        ConsumerActionKind.UNINSTALL,
        ConsumerScreen.INSTALLED_COLLECTION_DETAILS,
    ): ConsumerScreen.UNINSTALL_REVIEW,
    (ConsumerActionKind.SOURCE_SYNC, MaintainerScreen.SOURCES): MaintainerScreen.SOURCE_SYNC,
    (
        ConsumerActionKind.SOURCE_SYNC,
        MaintainerScreen.SOURCE_DETAILS,
    ): MaintainerScreen.SOURCE_SYNC,
    (
        ConsumerActionKind.CANDIDATE_PROMOTION,
        MaintainerScreen.REGISTRY_DIFF,
    ): MaintainerScreen.REGISTRY_VALIDATION,
    # Screen 47 selects; the transaction it assembles is reviewed and committed on the same two
    # screens a single promotion uses, because it is the same kind of transaction.
    (
        ConsumerActionKind.BULK_PROMOTION,
        MaintainerScreen.BULK_PROMOTION,
    ): MaintainerScreen.REGISTRY_VALIDATION,
}

#: The screens an action can be asked from, which are also the screens a declined preparation
#: returns to (`QA-018`/`D-184`). Derived from `_ACTION_REVIEW` so that adding an action cannot
#: leave a refusal with nowhere to be drawn.
ACTION_REQUEST_SCREENS: frozenset[ApplicationScreen] = frozenset(
    origin for _action, origin in _ACTION_REVIEW
)


#: Actions whose subject is the row under the cursor right now, rather than the row that opened
#: the screen they are requested from. Screen 46h's rows are stages of one run, and the registry
#: alias focused back on screen 46 is not one of them: inheriting it would ask for a run nobody
#: chose, which is what a shell walk-through of the keys found it doing (`QA-025`).
_ROW_IS_THE_REQUEST = frozenset(
    {
        ConsumerActionKind.REGISTRY_REBUILD,
        # Doctor is entered from Dashboard with that screen identifier as navigation focus. Its
        # repair action is about the measured installed issue under the cursor, never "29-doctor".
        ConsumerActionKind.VERIFY_REPAIR,
        # Navigation focus can still name the screen that opened this list. A Registry refresh is
        # always about the visible row, never that stale workflow subject (`QA-043`).
        ConsumerActionKind.REGISTRY_SYNC,
        ConsumerActionKind.REGISTRY_REMOVE,
    }
)


def _request_action(
    state: ConsumerUiState, action: ConsumerActionKind | None
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if action is None:
        return state, ()
    target = _ACTION_REVIEW.get((action, state.session.screen))
    focus = (
        state.current_row or state.focus
        if action in _ROW_IS_THE_REQUEST
        else state.focus or state.current_row
    )
    if target is None:
        return state, ()
    # A bulk promotion is defined by what was selected, so an empty selection is not a request.
    if action in (ConsumerActionKind.BULK_PROMOTION, ConsumerActionKind.REPOSITORY_ADOPT):
        if not state.selection:
            return state, ()
    elif action in (ConsumerActionKind.INSTALL, ConsumerActionKind.UPDATE):
        if not state.selection and not (
            action is ConsumerActionKind.INSTALL
            and state.session.screen is not ConsumerScreen.MARKETPLACE
            and focus
        ):
            return state, ()
    elif (
        action
        not in (
            ConsumerActionKind.REGISTRY_ADD,
            ConsumerActionKind.SOURCE_ADD,
            ConsumerActionKind.REGISTRY_INIT,
            ConsumerActionKind.REPOSITORY_SCAN,
        )
        and not focus
    ):
        return state, ()

    moved, navigation = _navigate(state, target)
    if moved is state:
        return state, ()
    if state.session.screen is ConsumerScreen.MARKETPLACE:
        focus = ""
    prepared = replace(
        moved,
        action=action,
        quit_pending=False,
        registry_commit_applied=(
            False
            if action in (ConsumerActionKind.CANDIDATE_PROMOTION, ConsumerActionKind.BULK_PROMOTION)
            else moved.registry_commit_applied
        ),
    )
    command = ConsumerUiCommand(
        ConsumerUiCommandKind.PREPARE_ACTION,
        action=action,
        selection=state.selection,
        focus=focus,
        promotion_mode=(
            state.promotion_mode
            if action in (ConsumerActionKind.CANDIDATE_PROMOTION, ConsumerActionKind.BULK_PROMOTION)
            else None
        ),
        registry_draft=(
            state.registry_draft if action is ConsumerActionKind.REGISTRY_ADD else None
        ),
        source_draft=(state.source_draft if action is ConsumerActionKind.SOURCE_ADD else None),
        registry_init_draft=(
            state.registry_init_draft if action is ConsumerActionKind.REGISTRY_INIT else None
        ),
        repository_scan_draft=(
            state.repository_scan_draft if action is ConsumerActionKind.REPOSITORY_SCAN else None
        ),
    )
    return prepared, (command, *navigation)


def _declined_preparation(
    state: ConsumerUiState,
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """`QA-018`: a refusal leaves no screen that still asks to confirm something.

    The review screen is opened before the adapter is asked to prepare, because consent is given on
    it. When the preparation refuses, that screen is about a plan that does not exist -- it went on
    saying "press Enter to connect", and Enter reached the execution boundary with nothing pending.
    The session returns to the screen the review was opened from, which for a form is the form with
    everything the operator typed still in it, and the pending action is cleared so a later Enter
    cannot reach a confirmation at all. The refusal itself is already on that screen: the adapter
    sent it as a notice with this event.
    """

    cleared = replace(state, action=None, quit_pending=False)
    session = state.session.back()
    if session is state.session:
        return cleared, ()
    return (
        replace(cleared, session=session, help_visible=False, search=""),
        (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, session.screen),),
    )


def _action_prepared(
    state: ConsumerUiState, event: ConsumerUiEvent
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    action = event.action
    if action is None or action is not state.action:
        return state, ()
    if not event.review_digest:
        return _declined_preparation(state)
    # Scanning is the completed read-only action: the result is now on screen and there is no
    # mutation waiting for confirmation.  Adoption starts a separate reviewed action from it.
    if action in (
        ConsumerActionKind.REPOSITORY_SCAN,
        ConsumerActionKind.REPOSITORY_UPSTREAM_CHECK,
    ):
        return replace(state, action=None, quit_pending=False), ()
    if action in (ConsumerActionKind.INSTALL, ConsumerActionKind.UPDATE) and (
        not event.semantic_identity or not event.selection_identity
    ):
        return state, ()
    session = replace(
        state.session,
        semantic_identity=event.semantic_identity or None,
        selection_identity=event.selection_identity or None,
        review_digest=event.review_digest,
    )
    return replace(state, session=session, quit_pending=False), ()


_ACTION_RUNNING: dict[tuple[ConsumerActionKind, ApplicationScreen], ApplicationScreen | None] = {
    (ConsumerActionKind.REGISTRY_ADD, ConsumerScreen.REGISTRY_REVIEW): None,
    (ConsumerActionKind.REGISTRY_SYNC, ConsumerScreen.REGISTRY_SYNC): None,
    (ConsumerActionKind.REGISTRY_REMOVE, ConsumerScreen.REGISTRY_REMOVE): None,
    (ConsumerActionKind.SOURCE_ADD, MaintainerScreen.SOURCE_ADD_REVIEW): None,
    (ConsumerActionKind.REGISTRY_INIT, MaintainerScreen.REGISTRY_INIT_REVIEW): None,
    (ConsumerActionKind.REGISTRY_REBUILD, MaintainerScreen.REGISTRY_REBUILD_REVIEW): None,
    (ConsumerActionKind.REPOSITORY_ADOPT, MaintainerScreen.ADOPTION_REVIEW): None,
    (ConsumerActionKind.REPOSITORY_ADOPT_UPDATE, MaintainerScreen.ADOPTION_REVIEW): None,
    (ConsumerActionKind.INSTALL, ConsumerScreen.READY): ConsumerScreen.INSTALLING,
    (ConsumerActionKind.UPDATE, ConsumerScreen.UPDATE_INPUTS): ConsumerScreen.UPDATING,
    (
        ConsumerActionKind.VERIFY_REPAIR,
        ConsumerScreen.VERIFY_REPAIR,
    ): None,
    (ConsumerActionKind.UNINSTALL, ConsumerScreen.UNINSTALL_REVIEW): ConsumerScreen.UNINSTALLING,
    (ConsumerActionKind.SOURCE_SYNC, MaintainerScreen.SOURCE_SYNC): None,
    (
        ConsumerActionKind.CANDIDATE_PROMOTION,
        MaintainerScreen.REGISTRY_COMMIT,
    ): None,
    (
        ConsumerActionKind.BULK_PROMOTION,
        MaintainerScreen.REGISTRY_COMMIT,
    ): None,
}


def _confirm_action(
    state: ConsumerUiState,
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    action, review_digest = state.action, state.session.review_digest
    if action is None or review_digest is None:
        return state, ()
    key = (action, state.session.screen)
    if key not in _ACTION_RUNNING:
        return state, ()
    command = ConsumerUiCommand(
        ConsumerUiCommandKind.EXECUTE_ACTION,
        action=action,
        selection=state.selection,
        focus=state.focus,
        review_digest=review_digest,
    )
    target = _ACTION_RUNNING[key]
    if target is None:
        return replace(state, quit_pending=False), (command,)
    moved, navigation = _navigate(state, target)
    return moved, (command, *navigation)


_ACTION_RESULT: dict[tuple[ConsumerActionKind, ApplicationScreen], ApplicationScreen] = {
    (ConsumerActionKind.REGISTRY_ADD, ConsumerScreen.REGISTRY_REVIEW): ConsumerScreen.REGISTRIES,
    (ConsumerActionKind.REGISTRY_SYNC, ConsumerScreen.REGISTRY_SYNC): ConsumerScreen.REGISTRIES,
    (ConsumerActionKind.REGISTRY_REMOVE, ConsumerScreen.REGISTRY_REMOVE): ConsumerScreen.REGISTRIES,
    (
        ConsumerActionKind.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD_REVIEW,
    ): MaintainerScreen.SOURCES,
    (
        ConsumerActionKind.REGISTRY_INIT,
        MaintainerScreen.REGISTRY_INIT_REVIEW,
    ): MaintainerScreen.REGISTRY,
    (
        ConsumerActionKind.REGISTRY_REBUILD,
        MaintainerScreen.REGISTRY_REBUILD_REVIEW,
    ): MaintainerScreen.REGISTRY,
    (ConsumerActionKind.INSTALL, ConsumerScreen.INSTALLING): ConsumerScreen.SUCCESS,
    (ConsumerActionKind.UPDATE, ConsumerScreen.UPDATING): ConsumerScreen.ACTIVITY_DETAILS,
    (
        ConsumerActionKind.VERIFY_REPAIR,
        ConsumerScreen.VERIFY_REPAIR,
    ): ConsumerScreen.ACTIVITY_DETAILS,
    (ConsumerActionKind.UNINSTALL, ConsumerScreen.UNINSTALLING): ConsumerScreen.ACTIVITY_DETAILS,
    (
        ConsumerActionKind.SOURCE_SYNC,
        MaintainerScreen.SOURCE_SYNC,
    ): MaintainerScreen.SOURCE_SYNC_RESULT,
    (
        ConsumerActionKind.REPOSITORY_ADOPT,
        MaintainerScreen.ADOPTION_REVIEW,
    ): MaintainerScreen.REGISTRY,
    (
        ConsumerActionKind.REPOSITORY_ADOPT_UPDATE,
        MaintainerScreen.ADOPTION_REVIEW,
    ): MaintainerScreen.REGISTRY,
}


#: The screens an action states itself on: the review it opens before running, and the screen the
#: run lands on afterwards. Derived for the same reason the request screens are -- a review whose
#: plan is not drawn is a screen asking somebody to confirm nothing, and a result whose stages are
#: not drawn is a run that reports only that it happened (`QA-024`).
ACTION_ANSWER_SCREENS: frozenset[ApplicationScreen] = frozenset(
    _ACTION_REVIEW.values()
) | frozenset(_ACTION_RESULT.values())


def _owning_screen(
    action: ConsumerActionKind, screen: ApplicationScreen
) -> ApplicationScreen | None:
    """Where a run confirmed on this screen belongs once it is over, however it ended.

    A refused run and a recorded one leave for the same place, because the operator was never
    asking to be on a review screen: they were asking for the run, and the run is finished.
    """

    return _ACTION_RESULT.get((action, screen))


def _action_failed(
    state: ConsumerUiState, event: ConsumerUiEvent
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """An attempted run stopped, so its review becomes the finished result of that attempt.

    The screen does not move. The refusal is drawn where it was caused, and moving away from it
    would take the explanation with it. What changes is that there is no plan left to confirm:
    `action` clears, and `failed_action` says which run this screen is now the end of (`QA-033`).
    """

    action = event.action
    if action is None or action is not state.action:
        return state, ()
    return replace(state, action=None, failed_action=action, quit_pending=False), ()


def _action_recorded(
    state: ConsumerUiState, event: ConsumerUiEvent
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    action = event.action
    if action is None or action is not state.action or not event.text:
        return state, ()
    if (
        action in (ConsumerActionKind.CANDIDATE_PROMOTION, ConsumerActionKind.BULK_PROMOTION)
        and state.session.screen is MaintainerScreen.REGISTRY_COMMIT
    ):
        return replace(
            state,
            selection=(),
            quit_pending=False,
            action=None,
            registry_commit_applied=True,
        ), (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, state.session.screen),)
    target = _owning_screen(action, state.session.screen)
    if target is None:
        return state, ()
    moved, commands = _navigate(state, target)
    focus = (
        state.focus
        if action in (ConsumerActionKind.SOURCE_SYNC, ConsumerActionKind.REGISTRY_SYNC)
        else event.text
    )
    return replace(
        moved,
        selection=(),
        focus=focus,
        quit_pending=False,
        action=None,
    ), commands


def _apply_setting(
    state: ConsumerUiState, settings: ConsumerSettings
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Move one preference and ask for it to be kept.

    The session's profile and the stored detail level are the same choice, so switching with `v`
    and switching on screen 28 go through here together rather than through two rules that could
    disagree. Persistence is a command because the reducer is pure: it says the preference should
    outlive the session, and the shell is what can make that true.
    """

    return (
        replace(
            state,
            session=state.session.switch_profile(settings.profile),
            settings=settings,
            quit_pending=False,
        ),
        (ConsumerUiCommand(ConsumerUiCommandKind.PERSIST_SETTINGS),),
    )


def reduce_consumer_ui(
    state: ConsumerUiState,
    event: ConsumerUiEvent,
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Apply one UI event and return explicit commands for the imperative shell."""

    if not isinstance(state, ConsumerUiState) or not isinstance(event, ConsumerUiEvent):
        raise ValueError("consumer UI reduction needs typed state and event")
    if state.exited:
        return state, ()
    if event.kind is ConsumerUiEventKind.NAVIGATE:
        return _navigate(state, event.screen)
    if event.kind is ConsumerUiEventKind.BACK:
        return _back(state)
    if event.kind is ConsumerUiEventKind.SET_ROWS:
        return _set_rows(state, event.rows)
    if event.kind is ConsumerUiEventKind.MOVE:
        return _move(state, event.text)
    if event.kind is ConsumerUiEventKind.SET_SELECTION:
        return _set_selection(state, event.rows)
    if event.kind is ConsumerUiEventKind.TOGGLE_SELECTION:
        return _toggle_selection(state, event.key)
    if event.kind is ConsumerUiEventKind.REQUEST_ACTION:
        return _request_action(state, event.action)
    if event.kind is ConsumerUiEventKind.ACTION_PREPARED:
        return _action_prepared(state, event)
    if event.kind is ConsumerUiEventKind.CONFIRM_ACTION:
        return _confirm_action(state)
    if event.kind is ConsumerUiEventKind.ACTION_RECORDED:
        return _action_recorded(state, event)
    if event.kind is ConsumerUiEventKind.ACTION_FAILED:
        return _action_failed(state, event)
    if event.kind is ConsumerUiEventKind.EDIT_REGISTRY:
        if state.session.screen is not ConsumerScreen.REGISTRY_ADD:
            return state, ()
        draft = state.registry_draft
        if event.key == "alias":
            draft = replace(draft, alias=event.text)
        elif event.key == "url":
            draft = replace(draft, location=event.text)
        elif event.key == "ref":
            draft = replace(draft, ref=event.text)
        elif event.key == "default" and event.accepted is not None:
            draft = replace(draft, make_default=event.accepted)
        else:
            return state, ()
        return replace(state, registry_draft=draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_SOURCE:
        if state.session.screen is not MaintainerScreen.SOURCE_ADD:
            return state, ()
        source_draft = state.source_draft
        if event.key == "alias":
            source_draft = replace(source_draft, alias=event.text)
        elif event.key == "location":
            source_draft = replace(source_draft, location=event.text)
        elif event.key == "ref":
            source_draft = replace(source_draft, ref=event.text)
        elif event.key == "kind":
            # Space cycles the two authoring kinds rather than accepting typed text: the set is
            # closed by 164.2, and a form that let one be typed would let `registry-git` in.
            offset = AUTHORING_SOURCE_KINDS.index(source_draft.kind)
            source_draft = replace(
                source_draft,
                kind=AUTHORING_SOURCE_KINDS[(offset + 1) % len(AUTHORING_SOURCE_KINDS)],
            )
        else:
            return state, ()
        return replace(state, source_draft=source_draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_REGISTRY_INIT:
        if state.session.screen is not MaintainerScreen.REGISTRY_INIT:
            return state, ()
        init_draft = state.registry_init_draft
        if event.key == "id":
            init_draft = replace(init_draft, registry_id=event.text)
        elif event.key == "name":
            init_draft = replace(init_draft, display_name=event.text)
        elif event.key == "reporting":
            init_draft = replace(init_draft, usage_reporting=event.text)
        elif event.key == "commit" and event.accepted is not None:
            init_draft = replace(init_draft, commit=event.accepted)
        else:
            return state, ()
        return replace(state, registry_init_draft=init_draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.EDIT_REPOSITORY_SCAN:
        if state.session.screen is not MaintainerScreen.REPOSITORY_SCAN:
            return state, ()
        scan_draft = state.repository_scan_draft
        if event.key == "url":
            scan_draft = replace(scan_draft, url=event.text)
        elif event.key == "ref":
            scan_draft = replace(scan_draft, ref=event.text)
        else:
            return state, ()
        return replace(state, repository_scan_draft=scan_draft, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.TOGGLE_PROFILE:
        return _apply_setting(state, state.settings.toggled("detail-level"))
    if event.kind is ConsumerUiEventKind.TOGGLE_SETTING:
        if state.session.screen is not ConsumerScreen.SETTINGS or event.key not in SETTING_ROWS:
            return state, ()
        return _apply_setting(state, state.settings.toggled(event.key))
    if event.kind is ConsumerUiEventKind.TOGGLE_PROMOTION_MODE:
        if state.session.screen is not MaintainerScreen.PROMOTION_MODE:
            return state, ()
        chosen = (
            PromotionMode.REFERENCED
            if state.promotion_mode is PromotionMode.VENDORED
            else PromotionMode.VENDORED
        )
        return replace(state, promotion_mode=chosen, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.TOGGLE_CANDIDATE_FILTER:
        # Screen 53's rows are facet values, so a row is parsed back into the typed facet it
        # addresses rather than being pulled apart here. A row nothing can be made of changes
        # nothing, which is what an unaddressable row should do.
        if state.session.screen is not MaintainerScreen.CANDIDATE_FILTERS:
            return state, ()
        parsed = parse_candidate_filter_row(event.key)
        if parsed is None:
            return state, ()
        facet, value = parsed
        return (
            replace(
                state,
                candidate_filter=state.candidate_filter.toggled(facet, value),
                quit_pending=False,
            ),
            (),
        )
    if event.kind is ConsumerUiEventKind.SEARCH:
        if state.session.screen not in _SEARCHABLE:
            return state, ()
        return replace(state, search=event.text, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.SEARCH_OPEN:
        if state.session.screen not in _SEARCHABLE:
            return state, ()
        return replace(state, searching=True, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.SEARCH_CLOSE:
        if not state.searching:
            return state, ()
        kept = state.search if event.accepted is True else ""
        return replace(state, searching=False, search=kept, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.HELP:
        return replace(state, help_visible=not state.help_visible, quit_pending=False), ()
    if event.kind is ConsumerUiEventKind.QUIT:
        if state.selection:
            return replace(state, quit_pending=True), (
                ConsumerUiCommand(ConsumerUiCommandKind.CONFIRM_QUIT),
            )
        return replace(state, exited=True), (ConsumerUiCommand(ConsumerUiCommandKind.EXIT),)
    if event.kind is ConsumerUiEventKind.CONFIRM_QUIT and state.quit_pending:
        if event.accepted is True:
            return replace(state, exited=True, quit_pending=False), (
                ConsumerUiCommand(ConsumerUiCommandKind.EXIT),
            )
        return replace(state, quit_pending=False), ()
    return state, ()


#: Names the terminal shell gives the keys that are not one printable character.
_SPECIAL_KEYS = frozenset({"up", "down", "enter", "escape", "backspace"})


@dataclass(frozen=True, slots=True)
class _ScreenBinding:
    """A screen-specific shortcut, including both its event and its displayed meaning."""

    display: KeyBinding
    event: ConsumerUiEvent


def _navigate_binding(key: str, label: str, screen: ApplicationScreen) -> _ScreenBinding:
    return _ScreenBinding(
        KeyBinding(key, label),
        ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=screen),
    )


def _action_binding(key: str, label: str, action: ConsumerActionKind) -> _ScreenBinding:
    return _ScreenBinding(
        KeyBinding(key, label),
        ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=action),
    )


def _event_binding(key: str, label: str, kind: ConsumerUiEventKind) -> _ScreenBinding:
    return _ScreenBinding(KeyBinding(key, label), ConsumerUiEvent(kind))


#: The contextual letter keys have one authority: :func:`key_event` translates this table and the
#: footer displays it. Adding a route without its explanation, or explaining a key that routes
#: nowhere, is therefore not representable (`QA-026`). Structural keys such as Space and Enter are
#: derived below from the same screen sets and review maps that the reducer uses.
_SCREEN_BINDINGS: dict[ApplicationScreen, tuple[_ScreenBinding, ...]] = {
    ConsumerScreen.MARKETPLACE: (_action_binding("i", "Install", ConsumerActionKind.INSTALL),),
    ConsumerScreen.ARTIFACT_DETAILS: (_action_binding("i", "Install", ConsumerActionKind.INSTALL),),
    ConsumerScreen.COLLECTION_PREVIEW: (
        _action_binding("i", "Install", ConsumerActionKind.INSTALL),
    ),
    ConsumerScreen.COLLECTION_CUSTOMIZE: (
        _action_binding("i", "Install", ConsumerActionKind.INSTALL),
    ),
    ConsumerScreen.UPDATES: (_action_binding("i", "Update", ConsumerActionKind.UPDATE),),
    ConsumerScreen.INSTALLED_ARTIFACT_DETAILS: (
        _action_binding("r", "Repair", ConsumerActionKind.VERIFY_REPAIR),
        _action_binding("u", "Uninstall", ConsumerActionKind.UNINSTALL),
    ),
    ConsumerScreen.INSTALLED_COLLECTION_DETAILS: (
        _action_binding("u", "Uninstall", ConsumerActionKind.UNINSTALL),
    ),
    ConsumerScreen.DOCTOR: (
        _action_binding("r", "Repair issues", ConsumerActionKind.VERIFY_REPAIR),
    ),
    ConsumerScreen.REGISTRIES: (
        _navigate_binding("a", "Add Registry", ConsumerScreen.REGISTRY_ADD),
        _action_binding("s", "Sync", ConsumerActionKind.REGISTRY_SYNC),
        _action_binding("d", "Disconnect", ConsumerActionKind.REGISTRY_REMOVE),
    ),
    MaintainerScreen.SOURCES: (
        _navigate_binding("a", "Add Source", MaintainerScreen.SOURCE_ADD),
        _action_binding("s", "Sync", ConsumerActionKind.SOURCE_SYNC),
    ),
    MaintainerScreen.SOURCE_DETAILS: (
        _action_binding("s", "Sync", ConsumerActionKind.SOURCE_SYNC),
    ),
    MaintainerScreen.CANDIDATES: (
        _navigate_binding("f", "Filters", MaintainerScreen.CANDIDATE_FILTERS),
        _navigate_binding("c", "Collections", MaintainerScreen.COLLECTION_CANDIDATES),
    ),
    MaintainerScreen.CANDIDATE_DETAILS: (
        _navigate_binding("d", "Diff", MaintainerScreen.CANDIDATE_DIFF),
        _navigate_binding("r", "Lifecycle", MaintainerScreen.CANDIDATE_LIFECYCLE),
    ),
    # Screen 39 is a drill-down, not a dead end. The evidence was already produced before the
    # screen opened, so continuing to the policy that judges it needs no second action (`QA-074`).
    MaintainerScreen.VALIDATION_DETAILS: (
        _navigate_binding("Enter", "Policy", MaintainerScreen.POLICY_REVIEW),
    ),
    MaintainerScreen.PROMOTION_MODE: (
        _event_binding("m", "Toggle mode", ConsumerUiEventKind.TOGGLE_PROMOTION_MODE),
    ),
    MaintainerScreen.REGISTRY: (
        # Where a finished promotion lands, so the next one starts one key away instead of behind
        # an Esc for every screen of the journey just completed (`QA-027`).
        _navigate_binding("c", "Candidates", MaintainerScreen.CANDIDATES),
        _navigate_binding("n", "Initialize", MaintainerScreen.REGISTRY_INIT),
        _navigate_binding("b", "Rebuild", MaintainerScreen.REGISTRY_REBUILD),
        _navigate_binding("s", "Scan Repository", MaintainerScreen.REPOSITORY_SCAN),
        _navigate_binding("u", "Check upstream", MaintainerScreen.ADOPTED_ARTIFACTS),
    ),
    # The end of a Source journey. Enter is bound here rather than left to the generic rule
    # because a result screen has nothing to open, and an Enter that does nothing is how somebody
    # ends up pressing Esc through every screen they just walked (`QA-027`).
    MaintainerScreen.SOURCE_SYNC_RESULT: (
        _navigate_binding("Enter", "Sources", MaintainerScreen.SOURCES),
    ),
    MaintainerScreen.SCAN_RESULT: (
        _action_binding("a", "Adopt", ConsumerActionKind.REPOSITORY_ADOPT),
    ),
    MaintainerScreen.UPSTREAM_CHECK: (
        _action_binding("a", "Review new version", ConsumerActionKind.REPOSITORY_ADOPT_UPDATE),
    ),
    MaintainerScreen.ADOPTED_ARTIFACTS: (
        _action_binding("Enter", "Check upstream", ConsumerActionKind.REPOSITORY_UPSTREAM_CHECK),
    ),
    MaintainerScreen.BULK_PROMOTION: (
        _action_binding("Enter", "Review promotion", ConsumerActionKind.BULK_PROMOTION),
    ),
    MaintainerScreen.REGISTRY_DIFF: (
        _action_binding("Enter", "Review promotion", ConsumerActionKind.CANDIDATE_PROMOTION),
    ),
    MaintainerScreen.REGISTRY_REBUILD: (
        _action_binding("Enter", "Review run", ConsumerActionKind.REGISTRY_REBUILD),
    ),
}

_FORM_SCREENS = frozenset(
    {
        ConsumerScreen.REGISTRY_ADD,
        MaintainerScreen.SOURCE_ADD,
        MaintainerScreen.REGISTRY_INIT,
        MaintainerScreen.REPOSITORY_SCAN,
    }
)
#: What Space changes on each form that has something to change, said by name.
#:
#: `QA-088`: the sentence that used to carry this -- "Space toggles default", "Space switches
#: kind" -- is gone from the screen, so a shared "Toggle" would have dropped the only word that
#: said what the key is for.
_FORM_TOGGLE_LABELS: dict[ApplicationScreen, str] = {
    ConsumerScreen.REGISTRY_ADD: "Make default",
    MaintainerScreen.SOURCE_ADD: "Switch kind",
    MaintainerScreen.REGISTRY_INIT: "Local commit",
}
_CONFIRM_SCREENS = frozenset(
    {
        ConsumerScreen.READY,
        ConsumerScreen.UPDATE_INPUTS,
        ConsumerScreen.UNINSTALL_REVIEW,
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.REGISTRY_REVIEW,
        ConsumerScreen.REGISTRY_SYNC,
        ConsumerScreen.REGISTRY_REMOVE,
        MaintainerScreen.SOURCE_SYNC,
        MaintainerScreen.REGISTRY_COMMIT,
        MaintainerScreen.ADOPTION_REVIEW,
        MaintainerScreen.SOURCE_ADD_REVIEW,
        MaintainerScreen.REGISTRY_INIT_REVIEW,
        MaintainerScreen.REGISTRY_REBUILD_REVIEW,
    }
)


def _binding_enabled(binding: _ScreenBinding, state: ConsumerUiState) -> bool:
    if binding.event.action in (
        ConsumerActionKind.REGISTRY_SYNC,
        ConsumerActionKind.REGISTRY_REMOVE,
    ):
        return state.current_row not in ("", "add-registry")
    return True


def _screen_binding(key: str, state: ConsumerUiState) -> _ScreenBinding | None:
    return next(
        (
            binding
            for binding in _SCREEN_BINDINGS.get(state.session.screen, ())
            if binding.display.key.lower() == key and _binding_enabled(binding, state)
        ),
        None,
    )


def key_bindings(
    state: ConsumerUiState, *, detail: ApplicationScreen | None = None
) -> tuple[KeyBinding, ...]:
    """Return the keys that can act in this exact UI state, specific actions first."""

    if not isinstance(state, ConsumerUiState) or not (
        detail is None or isinstance(detail, (ConsumerScreen, MaintainerScreen))
    ):
        raise ValueError("key bindings need consumer UI state and an optional detail screen")
    if state.quit_pending:
        return (KeyBinding("y/Enter", "Quit"), KeyBinding("n/Esc", "Stay"))
    if state.searching:
        return (
            KeyBinding("Type", "Search"),
            KeyBinding("Backspace", "Edit"),
            KeyBinding("Enter", "Apply"),
            KeyBinding("Esc", "Cancel"),
        )

    bindings = [
        binding.display
        for binding in _SCREEN_BINDINGS.get(state.session.screen, ())
        if _binding_enabled(binding, state)
    ]
    keys = {binding.key.lower() for binding in bindings}
    if state.session.screen in _FORM_SCREENS:
        # `QA-088`: a form accepts four keys and used to describe them in a sentence above a
        # legend that advertised two. They are all keys, so they are all in the legend, in the
        # order a reader uses them: change a field, then move on.
        bindings.append(KeyBinding("Type", "Edit"))
        bindings.append(KeyBinding("Backspace", "Delete"))
        toggle = _FORM_TOGGLE_LABELS.get(state.session.screen)
        if toggle is not None:
            bindings.append(KeyBinding("Space", toggle))
        bindings.append(KeyBinding("Enter", "Next / continue"))
    elif state.session.screen is ConsumerScreen.SETTINGS:
        bindings.append(KeyBinding("Space/Enter", "Change"))
    elif state.session.screen is MaintainerScreen.CANDIDATE_FILTERS:
        bindings.append(KeyBinding("Space/Enter", "Toggle filter"))
    else:
        if state.session.screen in _SELECTABLE and " " not in keys:
            bindings.append(KeyBinding("Space", "Select"))
        if state.failed_action is not None and "enter" not in keys:
            # The run is over. The only thing Enter can honestly do here is leave.
            bindings.append(KeyBinding("Enter", "Back to list"))
        elif state.session.screen in _CONFIRM_SCREENS and "enter" not in keys:
            label = "Continue" if state.action is None else "Confirm"
            bindings.append(KeyBinding("Enter", label))
        elif detail is not None and "enter" not in keys:
            # Success's rows are choices rather than things to open, so Enter says which one.
            choices: dict[ConsumerScreen | MaintainerScreen, str] = (
                dict(SUCCESS_CHOICES) if state.session.screen is ConsumerScreen.SUCCESS else {}
            )
            label = choices.get(detail, "Open")
            bindings.append(KeyBinding("Enter", label))
        elif (
            state.session.screen is MaintainerScreen.REGISTRY_COMMIT
            and state.action is None
            and "enter" not in keys
        ):
            bindings.append(KeyBinding("Enter", "Registry"))
    if state.session.screen in _SEARCHABLE:
        bindings.append(KeyBinding("/", "Search"))
    bindings.append(KeyBinding("v", "Fast / Verbose"))
    bindings.extend(
        (
            KeyBinding("↑/↓", "Move"),
            KeyBinding("Esc", "Back"),
            KeyBinding("?", "Help"),
            KeyBinding("q", "Quit"),
        )
    )
    return tuple(bindings)


def key_event(
    key: str,
    state: ConsumerUiState,
    *,
    cursor: str = "",
    detail: ApplicationScreen | None = None,
) -> ConsumerUiEvent | None:
    """The event one key means here, or None where it means nothing on this screen.

    Mode comes first deliberately.  While the quit prompt or the search filter is open the
    global bindings do not apply at all: during a search `q` types a q, and at the prompt `n`
    answers the question rather than doing whatever `n` would otherwise do.

    `detail` is what Enter opens from the current row, which only the screen knows.
    """

    if not isinstance(state, ConsumerUiState):
        raise ValueError("key translation needs a key name and consumer UI state")
    if (
        not isinstance(key, str)
        or not key
        or (
            len(key) != 1
            and key not in _SPECIAL_KEYS
            and state.session.screen
            not in (
                ConsumerScreen.REGISTRY_ADD,
                MaintainerScreen.REGISTRY_INIT,
                MaintainerScreen.REPOSITORY_SCAN,
            )
        )
        or not (detail is None or isinstance(detail, (ConsumerScreen, MaintainerScreen)))
    ):
        raise ValueError("key translation needs a key name and consumer UI state")

    if state.quit_pending:
        if key in ("y", "Y", "enter"):
            return ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_QUIT, accepted=True)
        if key in ("n", "N", "escape"):
            return ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_QUIT, accepted=False)
        return None

    if state.searching:
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH_CLOSE, accepted=False)
        if key == "enter":
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH_CLOSE, accepted=True)
        if key == "backspace":
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH, text=state.search[:-1])
        if len(key) == 1 and key.isprintable():
            return ConsumerUiEvent(ConsumerUiEventKind.SEARCH, text=state.search + key)
        return None

    if state.session.screen is MaintainerScreen.REGISTRY_INIT:
        row = cursor or state.current_row
        values = {
            "id": state.registry_init_draft.registry_id,
            "name": state.registry_init_draft.display_name,
            "reporting": state.registry_init_draft.usage_reporting,
        }
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == " " and row == "commit":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REGISTRY_INIT,
                key="commit",
                accepted=not state.registry_init_draft.commit,
            )
        if key == "enter":
            if row == "initialize":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.REGISTRY_INIT,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REGISTRY_INIT, key=row, text=values[row][:-1]
            )
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_REGISTRY_INIT, key=row, text=text)
        return None

    if state.session.screen is MaintainerScreen.REPOSITORY_SCAN:
        row = cursor or state.current_row
        values = {
            "url": state.repository_scan_draft.url,
            "ref": state.repository_scan_draft.ref,
        }
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == "enter":
            if row == "scan":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.REPOSITORY_SCAN,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REPOSITORY_SCAN,
                key=row,
                text=values[row][:-1],
            )
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REPOSITORY_SCAN,
                key=row,
                text=text,
            )
        return None

    if state.session.screen is MaintainerScreen.SOURCE_ADD:
        row = cursor or state.current_row
        values = {
            "alias": state.source_draft.alias,
            "location": state.source_draft.location,
            "ref": state.source_draft.ref,
        }
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == " " and row == "kind":
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_SOURCE, key="kind")
        if key == "enter":
            if row == "connect":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.SOURCE_ADD,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_SOURCE, key=row, text=values[row][:-1])
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_SOURCE, key=row, text=text)
        return None

    if state.session.screen is ConsumerScreen.REGISTRY_ADD:
        row = cursor or state.current_row
        values = {
            "alias": state.registry_draft.alias,
            "url": state.registry_draft.location,
            "ref": state.registry_draft.ref,
        }
        if key == "escape":
            return ConsumerUiEvent(ConsumerUiEventKind.BACK)
        if key == "up":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
        if key == "down":
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if key == " " and row == "default":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REGISTRY,
                key="default",
                accepted=not state.registry_draft.make_default,
            )
        if key == "enter":
            if row == "connect":
                return ConsumerUiEvent(
                    ConsumerUiEventKind.REQUEST_ACTION,
                    action=ConsumerActionKind.REGISTRY_ADD,
                )
            return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
        if row in values and key == "backspace":
            return ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_REGISTRY, key=row, text=values[row][:-1]
            )
        if row in values and key.isprintable():
            text = key if len(key) > 1 else values[row] + key
            return ConsumerUiEvent(ConsumerUiEventKind.EDIT_REGISTRY, key=row, text=text)
        return None

    if key == "q":
        return ConsumerUiEvent(ConsumerUiEventKind.QUIT)
    if key == "escape":
        return ConsumerUiEvent(ConsumerUiEventKind.BACK)
    if key == "/":
        return ConsumerUiEvent(ConsumerUiEventKind.SEARCH_OPEN)
    if key == "?":
        return ConsumerUiEvent(ConsumerUiEventKind.HELP)
    if key == "v":
        return ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE)
    binding = _screen_binding(key, state)
    if binding is not None:
        return binding.event
    # Screen 28 is the one screen whose rows are settings rather than artifacts, so space and
    # Enter move a preference here instead of ticking or opening something.
    if key in (" ", "enter") and state.session.screen is ConsumerScreen.SETTINGS:
        row = cursor or state.current_row
        return None if not row else ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SETTING, key=row)
    # Screen 53's rows are facet values, not artifacts: ticking one narrows the list rather than
    # putting anything in `selection`, which is what every action reads.
    if key in (" ", "enter") and state.session.screen is MaintainerScreen.CANDIDATE_FILTERS:
        row = cursor or state.current_row
        return (
            None
            if not row
            else ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_CANDIDATE_FILTER, key=row)
        )
    if key == " ":
        return ConsumerUiEvent(
            ConsumerUiEventKind.TOGGLE_SELECTION, key=cursor or state.current_row
        )
    if key in ("up", "k"):
        return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
    if key in ("down", "j"):
        return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
    # Screen 45 keeps its receipt on screen after the commit, so Enter means "confirm" only while
    # there is something to confirm; once the write happened it means "go on to the registry".
    if (
        key == "enter"
        and state.action is None
        and state.session.screen is MaintainerScreen.REGISTRY_COMMIT
    ):
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.REGISTRY)
    # A run that stopped leaves the same way a run that finished does, for the screen that owns
    # it -- the review it was confirmed from is now that attempt's result (`QA-033`).
    if key == "enter" and state.failed_action is not None:
        owner = _owning_screen(state.failed_action, state.session.screen)
        if owner is not None:
            return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=owner)
        return ConsumerUiEvent(ConsumerUiEventKind.BACK)
    if key == "enter" and state.session.screen in _CONFIRM_SCREENS:
        return ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_ACTION)
    if key == "enter" and detail is not None:
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=detail)
    return None
