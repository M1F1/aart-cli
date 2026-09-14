"""§167's frame and key contract as one checker, so every drawn state is held to the same rules.

CP-23 task 14 asks for compliance "checked over every declared screen and relevant conditional
state". A rule restated per screen drifts one screen at a time, which is how the audit found forms
advertising keys they type instead. So the rules live here once, and the tests that draw screens
ask this module what a drawn state breaks.

Each check answers with the violations it found as sentences, never a bare boolean, so a failing
sweep says which screen broke which rule and on which line.
"""

from __future__ import annotations

from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
)
from agent_artifacts.tui_consumer import ConsumerScreenSource

#: How a legend spells a key, and the name the shell hands the reducer for it.
_KEY_NAMES = {
    "Enter": ("enter",),
    "Esc": ("escape",),
    "Space": (" ",),
    "Backspace": ("backspace",),
    "↑/↓": ("up", "down"),
}

#: The universal keys and the one event each must mean wherever the legend offers it.
_UNIVERSAL = {
    "v": ConsumerUiEventKind.TOGGLE_PROFILE,
    "?": ConsumerUiEventKind.HELP,
    "q": ConsumerUiEventKind.QUIT,
}


def _key_names(key: str) -> tuple[str, ...]:
    if key in _KEY_NAMES or len(key) == 1:
        return _KEY_NAMES.get(key, (key,))
    names: list[str] = []
    for part in key.split("/"):
        if part not in _KEY_NAMES and len(part) != 1:
            raise ValueError(f"a legend key {key!r} has no name the shell could send")
        names.extend(_KEY_NAMES.get(part, (part,)))
    return tuple(names)


def _event(
    source: ConsumerScreenSource, state: ConsumerUiState, name: str
) -> ConsumerUiEvent | None:
    return key_event(name, state, detail=source.detail(state))


def key_violations(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """Every key the legend offers must do something here, and a universal key its one thing.

    `Type` is the one binding that is not a key: it stands for the printable characters a text
    field takes, and what it promises is checked by `literal_violations`.
    """

    found: list[str] = []
    screen = state.session.screen.value
    for binding in key_bindings(state, detail=source.detail(state)):
        if binding.key == "Type":
            continue
        for name in _key_names(binding.key):
            event = _event(source, state, name)
            if event is None:
                found.append(f"{screen}: [{binding.key}] {binding.label} does nothing here")
            elif name in _UNIVERSAL and not state.quit_pending and not state.searching:
                if event.kind is not _UNIVERSAL[name]:
                    found.append(
                        f"{screen}: [{binding.key}] {binding.label} means {event.kind.value}"
                    )
    return tuple(found)


def literal_violations(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """On a text field the universal letters are text, and the legend must not promise otherwise.

    §167: "Text-entry mode preserves literal text input." A field that swallowed `v` could not hold
    a name with a v in it, so while the cursor is on one `v`, `?` and `q` are typed; everywhere else
    they are the commands the legend names.
    """

    advertised = {item.key for item in key_bindings(state, detail=source.detail(state))}
    if "Type" not in advertised:
        return ()
    found: list[str] = []
    screen = state.session.screen.value
    for letter, command in _UNIVERSAL.items():
        event = _event(source, state, letter)
        if event is None or event.kind is command or not event.kind.name.startswith("EDIT_"):
            found.append(f"{screen}: typing {letter!r} into {state.current_row!r} is not text")
        elif not event.text.endswith(letter):
            found.append(f"{screen}: typing {letter!r} into {state.current_row!r} lost it")
        if letter in advertised:
            found.append(f"{screen}: [{letter}] is advertised on a field that types it")
    return tuple(found)
