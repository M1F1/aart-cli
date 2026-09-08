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

from dataclasses import dataclass, replace
from enum import Enum

from agent_artifacts.domain.registry import PromotionMode

from .consumer_views import (
    SETTING_ROWS,
    ApplicationScreen,
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    keeps_focus,
    navigation_targets,
)
from .maintainer_views import (
    MaintainerCandidateFilter,
    MaintainerScreen,
    parse_candidate_filter_row,
)

__all__ = [
    "ConsumerActionKind",
    "ConsumerUiCommand",
    "ConsumerUiCommandKind",
    "ConsumerUiEvent",
    "ConsumerUiEventKind",
    "ConsumerUiState",
    "RegistryDraft",
    "SourceDraft",
    "key_event",
    "opening_state",
    "reduce_consumer_ui",
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
    SOURCE_ADD = "source-add"


class ConsumerUiEventKind(str, Enum):
    NAVIGATE = "navigate"
    BACK = "back"
    MOVE = "move"
    SET_ROWS = "set-rows"
    SET_SELECTION = "set-selection"
    TOGGLE_PROFILE = "toggle-profile"
    TOGGLE_SELECTION = "toggle-selection"
    TOGGLE_SETTING = "toggle-setting"
    TOGGLE_FILE_DIFF = "toggle-file-diff"
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
    EDIT_REGISTRY = "edit-registry"
    EDIT_SOURCE = "edit-source"


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


class ConsumerUiCommandKind(str, Enum):
    LOAD_SCREEN = "load-screen"
    CONFIRM_QUIT = "confirm-quit"
    EXIT = "exit"
    PREPARE_ACTION = "prepare-action"
    EXECUTE_ACTION = "execute-action"
    PERSIST_SETTINGS = "persist-settings"


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
    #: What the Candidate list is narrowed to. Screen 53 edits it; screen 35 obeys it.
    candidate_filter: MaintainerCandidateFilter = MaintainerCandidateFilter()
    #: Whether the Candidate diff is also showing raw canonical file changes (INV-202).
    file_diff: bool = False
    #: Which promotion the Maintainer is reviewing. Screen 42 chooses it; screens 41 and 43 obey
    #: it. Both modes are composed, so this selects a projection rather than causing one.
    promotion_mode: PromotionMode = PromotionMode.VENDORED
    registry_draft: RegistryDraft = RegistryDraft()
    source_draft: SourceDraft = SourceDraft()

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
            or not isinstance(self.candidate_filter, MaintainerCandidateFilter)
            or not isinstance(self.file_diff, bool)
            or not isinstance(self.registry_draft, RegistryDraft)
            or not isinstance(self.source_draft, SourceDraft)
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


def opening_state(settings: ConsumerSettings) -> ConsumerUiState:
    """The state a session opens in, at the preferences somebody last chose.

    The session's profile and the stored detail level have to be set together: state validation
    lets the session win, so seeding only the settings would open Fast for somebody who chose
    Verbose and then silently rewrite their preference back.
    """

    if not isinstance(settings, ConsumerSettings):
        raise ValueError("opening the consumer application needs consumer settings")
    return ConsumerUiState(
        session=replace(_INITIAL_SESSION, profile=settings.profile), settings=settings
    )


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
    updated = replace(
        state,
        session=state.session.navigate(screen),
        focus=focus,
        search="",
        help_visible=False,
        quit_pending=False,
        file_diff=False,
    )
    return updated, (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, screen),)


def _back(state: ConsumerUiState) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    session = state.session.back()
    if session is state.session:
        return state, ()
    updated = replace(
        state,
        session=session,
        focus="",
        search="",
        help_visible=False,
        quit_pending=False,
        file_diff=False,
    )
    return updated, (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, session.screen),)


def _set_rows(
    state: ConsumerUiState, rows: tuple[str, ...]
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    """Take the rows a screen is currently showing, keeping the cursor on the same row if it is
    still there.  A filter hides rows; it never moves what somebody was looking at, and it never
    unticks anything."""

    standing = state.current_row
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
    (
        ConsumerActionKind.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD,
    ): MaintainerScreen.SOURCE_ADD_REVIEW,
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


def _request_action(
    state: ConsumerUiState, action: ConsumerActionKind | None
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if action is None:
        return state, ()
    target = _ACTION_REVIEW.get((action, state.session.screen))
    focus = state.focus or state.current_row
    if target is None:
        return state, ()
    # A bulk promotion is defined by what was selected, so an empty selection is not a request.
    if action is ConsumerActionKind.BULK_PROMOTION:
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
        action not in (ConsumerActionKind.REGISTRY_ADD, ConsumerActionKind.SOURCE_ADD) and not focus
    ):
        return state, ()

    moved, navigation = _navigate(state, target)
    if moved is state:
        return state, ()
    if state.session.screen is ConsumerScreen.MARKETPLACE:
        focus = ""
    prepared = replace(moved, action=action, quit_pending=False)
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
    (ConsumerActionKind.SOURCE_ADD, MaintainerScreen.SOURCE_ADD_REVIEW): None,
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
    (
        ConsumerActionKind.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD_REVIEW,
    ): MaintainerScreen.SOURCES,
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
}


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
        ), ()
    target = _ACTION_RESULT.get((action, state.session.screen))
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
    if event.kind is ConsumerUiEventKind.TOGGLE_FILE_DIFF:
        if state.session.screen is not MaintainerScreen.CANDIDATE_DIFF:
            return state, ()
        return replace(state, file_diff=not state.file_diff, quit_pending=False), ()
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
            and state.session.screen is not ConsumerScreen.REGISTRY_ADD
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
    if key == "a" and state.session.screen is ConsumerScreen.REGISTRIES:
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.REGISTRY_ADD)
    if key == "a" and state.session.screen is MaintainerScreen.SOURCES:
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.SOURCE_ADD)
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
    if key == "i":
        action = (
            ConsumerActionKind.UPDATE
            if state.session.screen in (ConsumerScreen.UPDATES, ConsumerScreen.UPDATE_INPUTS)
            else ConsumerActionKind.INSTALL
        )
        return ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=action)
    if key == "r" and state.session.screen in (
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ConsumerScreen.DOCTOR,
    ):
        return ConsumerUiEvent(
            ConsumerUiEventKind.REQUEST_ACTION,
            action=ConsumerActionKind.VERIFY_REPAIR,
        )
    if key == "r" and state.session.screen is MaintainerScreen.CANDIDATE_DETAILS:
        return ConsumerUiEvent(
            ConsumerUiEventKind.NAVIGATE,
            screen=MaintainerScreen.CANDIDATE_LIFECYCLE,
        )
    if key == "u" and state.session.screen in (
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ConsumerScreen.INSTALLED_COLLECTION_DETAILS,
    ):
        return ConsumerUiEvent(
            ConsumerUiEventKind.REQUEST_ACTION,
            action=ConsumerActionKind.UNINSTALL,
        )
    # The mode belongs to the promotion under review, so only the screen whose question it is
    # may change it.
    if key == "m" and state.session.screen is MaintainerScreen.PROMOTION_MODE:
        return ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROMOTION_MODE)
    if key == "p" and state.session.screen is MaintainerScreen.VALIDATION:
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.POLICY_REVIEW)
    if key == "d" and state.session.screen is MaintainerScreen.CANDIDATE_DETAILS:
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.CANDIDATE_DIFF)
    # INV-202: the raw canonical file diff is secondary evidence somebody asks for, never the
    # review itself, so it has its own key rather than riding along with the semantic diff.
    if key == "f" and state.session.screen is MaintainerScreen.CANDIDATE_DIFF:
        return ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_FILE_DIFF)
    # The Product Specification gives `f` to filters. Screen 37 claimed it first for the raw file
    # diff, and both keep it: one key means what the screen it was pressed on is about.
    if key == "f" and state.session.screen is MaintainerScreen.CANDIDATES:
        return ConsumerUiEvent(
            ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.CANDIDATE_FILTERS
        )
    # "Collections are candidates too", so the way into them is the Candidate surface rather than a
    # separate place in the dashboard: `c` opens the Collection Candidates of the same scan.
    if key == "c" and state.session.screen is MaintainerScreen.CANDIDATES:
        return ConsumerUiEvent(
            ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.COLLECTION_CANDIDATES
        )
    # `add-registry` is a button screen 21 draws above its rows, not a subscription, so it is the
    # one row here that cannot be fetched.  Asking for a refresh with no row under the cursor is
    # not a request either: there would be nothing to name in the review.
    if (
        key == "s"
        and state.session.screen is ConsumerScreen.REGISTRIES
        and (state.focus or state.current_row) not in ("", "add-registry")
    ):
        return ConsumerUiEvent(
            ConsumerUiEventKind.REQUEST_ACTION,
            action=ConsumerActionKind.REGISTRY_SYNC,
        )
    if key == "s" and state.session.screen in (
        MaintainerScreen.SOURCES,
        MaintainerScreen.SOURCE_DETAILS,
    ):
        return ConsumerUiEvent(
            ConsumerUiEventKind.REQUEST_ACTION,
            action=ConsumerActionKind.SOURCE_SYNC,
        )
    if key == "enter" and state.session.screen is MaintainerScreen.BULK_PROMOTION:
        return ConsumerUiEvent(
            ConsumerUiEventKind.REQUEST_ACTION,
            action=ConsumerActionKind.BULK_PROMOTION,
        )
    if key == "enter" and state.session.screen is MaintainerScreen.REGISTRY_DIFF:
        return ConsumerUiEvent(
            ConsumerUiEventKind.REQUEST_ACTION,
            action=ConsumerActionKind.CANDIDATE_PROMOTION,
        )
    # Screen 45 keeps its receipt on screen after the commit, so Enter means "confirm" only while
    # there is something to confirm; once the write happened it means "go on to the registry".
    if (
        key == "enter"
        and state.action is None
        and state.session.screen is MaintainerScreen.REGISTRY_COMMIT
    ):
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.REGISTRY)
    if key == "enter" and state.session.screen in (
        ConsumerScreen.READY,
        ConsumerScreen.UPDATE_INPUTS,
        ConsumerScreen.UNINSTALL_REVIEW,
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.REGISTRY_REVIEW,
        ConsumerScreen.REGISTRY_SYNC,
        MaintainerScreen.SOURCE_SYNC,
        MaintainerScreen.REGISTRY_COMMIT,
    ):
        return ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_ACTION)
    if key == "enter" and detail is not None:
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=detail)
    return None
