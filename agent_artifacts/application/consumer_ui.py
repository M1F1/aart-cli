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

from .consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    navigation_targets,
)

__all__ = [
    "ConsumerUiCommand",
    "ConsumerUiCommandKind",
    "ConsumerUiEvent",
    "ConsumerUiEventKind",
    "ConsumerUiState",
    "key_event",
    "reduce_consumer_ui",
]


class ConsumerUiEventKind(str, Enum):
    NAVIGATE = "navigate"
    BACK = "back"
    MOVE = "move"
    SET_ROWS = "set-rows"
    TOGGLE_PROFILE = "toggle-profile"
    TOGGLE_SELECTION = "toggle-selection"
    SEARCH = "search"
    SEARCH_OPEN = "search-open"
    SEARCH_CLOSE = "search-close"
    HELP = "help"
    QUIT = "quit"
    CONFIRM_QUIT = "confirm-quit"


class ConsumerUiCommandKind(str, Enum):
    LOAD_SCREEN = "load-screen"
    CONFIRM_QUIT = "confirm-quit"
    EXIT = "exit"


@dataclass(frozen=True, slots=True)
class ConsumerUiEvent:
    kind: ConsumerUiEventKind
    screen: ConsumerScreen | None = None
    key: str = ""
    text: str = ""
    accepted: bool | None = None
    rows: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, ConsumerUiEventKind)
            or (self.screen is not None and not isinstance(self.screen, ConsumerScreen))
            or not isinstance(self.key, str)
            or any(character in self.key for character in "\r\n")
            or not isinstance(self.text, str)
            or any(character in self.text for character in "\r\n")
            or not (self.accepted is None or isinstance(self.accepted, bool))
            or not _rows_valid(self.rows)
        ):
            raise ValueError("consumer UI event is invalid")


@dataclass(frozen=True, slots=True)
class ConsumerUiCommand:
    kind: ConsumerUiCommandKind
    screen: ConsumerScreen | None = None


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
    }
)
_SELECTABLE = frozenset(
    {
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.COLLECTION_PREVIEW,
        ConsumerScreen.COLLECTION_CUSTOMIZE,
        ConsumerScreen.UPDATES,
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
        ):
            raise ValueError("consumer UI state is invalid")
        if self.session.profile is not self.settings.profile:
            object.__setattr__(self, "settings", self.settings.with_profile(self.session.profile))

    @property
    def current_row(self) -> str:
        """The row identity the cursor is on, or empty where the screen has no rows."""

        return self.rows[self.cursor] if self.rows else ""


def _navigate(
    state: ConsumerUiState, screen: ConsumerScreen | None
) -> tuple[ConsumerUiState, tuple[ConsumerUiCommand, ...]]:
    if screen is None or screen not in navigation_targets(state.session.screen):
        return state, ()
    # What the next screen is about: the row somebody was on, or -- where this screen has no rows
    # of its own -- whatever the screen before it was already about.  A detail opened from a
    # detail is still about the same thing.
    updated = replace(
        state,
        session=state.session.navigate(screen),
        focus=state.current_row or state.focus,
        search="",
        help_visible=False,
        quit_pending=False,
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
    if event.kind is ConsumerUiEventKind.TOGGLE_SELECTION:
        return _toggle_selection(state, event.key)
    if event.kind is ConsumerUiEventKind.TOGGLE_PROFILE:
        profile = (
            PresentationProfile.VERBOSE
            if state.session.profile is PresentationProfile.FAST
            else PresentationProfile.FAST
        )
        return (
            replace(
                state,
                session=state.session.switch_profile(profile),
                settings=state.settings.with_profile(profile),
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
    detail: ConsumerScreen | None = None,
) -> ConsumerUiEvent | None:
    """The event one key means here, or None where it means nothing on this screen.

    Mode comes first deliberately.  While the quit prompt or the search filter is open the
    global bindings do not apply at all: during a search `q` types a q, and at the prompt `n`
    answers the question rather than doing whatever `n` would otherwise do.

    `detail` is what Enter opens from the current row, which only the screen knows.
    """

    if (
        not isinstance(key, str)
        or not key
        or (len(key) != 1 and key not in _SPECIAL_KEYS)
        or not isinstance(state, ConsumerUiState)
        or not (detail is None or isinstance(detail, ConsumerScreen))
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
    if key == " ":
        return ConsumerUiEvent(
            ConsumerUiEventKind.TOGGLE_SELECTION, key=cursor or state.current_row
        )
    if key in ("up", "k"):
        return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="up")
    if key in ("down", "j"):
        return ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down")
    if key == "enter" and detail is not None:
        return ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=detail)
    return None
