"""§167's frame and key contract as one checker, so every drawn state is held to the same rules.

CP-23 task 14 asks for compliance "checked over every declared screen and relevant conditional
state". A rule restated per screen drifts one screen at a time, which is how the audit found forms
advertising keys they type instead. So the rules live here once, and the tests that draw screens
ask this module what a drawn state breaks.

Each check answers with the violations it found as sentences, never a bare boolean, so a failing
sweep says which screen broke which rule and on which line.
"""

from __future__ import annotations

import re
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
    typing_text,
)
from aart_cli.application.consumer_views import PresentationProfile
from aart_cli.tui_consumer import ConsumerScreenSource, compose_frame

#: A row as the actions block draws it: the cursor gutter, then the row itself.
_ROW = re.compile(r"^(> |  )\S")
#: What a row says under itself, indented past the gutter.
_UNDER_ROW = re.compile(r"^    ")
#: A group heading names the rows under it; a sentence or a label with a value is prose.
_NOT_A_HEADING = re.compile(r"[.:;!?]")
#: Keyboard talk that belongs to the legend: a key in brackets, a padded button, or a key that
#: "selects", "opens" and so on in a sentence.
_CONTROL = re.compile(
    r"\[(Enter|Esc|Space|Tab|Backspace|↑/↓|\?|/)\]"
    r"|\[ [A-Z][A-Za-z ]*[a-z] \]"
    r"|\b(Enter|Space|Esc|Backspace) (selects|checks|toggles|opens|switches|continues|confirms"
    r"|reviews|advances|removes|returns|changes)\b"
)

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
        typed = ConsumerUiEventKind.SEARCH if state.searching else None
        if (
            event is None
            or event.kind is command
            or not (event.kind is typed or event.kind.name.startswith("EDIT_"))
        ):
            found.append(f"{screen}: typing {letter!r} into {state.current_row!r} is not text")
        elif not event.text.endswith(letter):
            found.append(f"{screen}: typing {letter!r} into {state.current_row!r} lost it")
        if letter in advertised:
            found.append(f"{screen}: [{letter}] is advertised on a field that types it")
    return tuple(found)


def _spoken(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(line for line in lines if line.strip())


def frame_violations(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """What one composed frame breaks of §167's shared frame.

    - The actions block holds rows, what a row says under itself, and headings that group rows.
      Prose, counts and labelled values are the state of the view and go to its status.
    - It draws exactly the rows the state holds, with the cursor on the one the state is on, and
      no actions block at all where there are no rows.
    - The cursor description is Verbose only, and only where there is a row to describe.
    - The body does not name the screen again under the trail, and does not talk about keys: that
      is the legend's.
    """

    blocks = compose_frame(source, state)
    screen = state.session.screen.value
    found: list[str] = []
    actions = _spoken(blocks.actions)
    if not state.rows and actions:
        found.append(f"{screen}: draws an actions block with no rows: {actions[0]!r}")
    for index, line in enumerate(actions):
        if _ROW.match(line) or _UNDER_ROW.match(line):
            continue
        following = actions[index + 1] if index + 1 < len(actions) else ""
        if _ROW.match(following) and not _NOT_A_HEADING.search(line):
            continue
        found.append(f"{screen}: prose among the rows: {line!r}")
    drawn = [line for line in actions if _ROW.match(line)]
    if state.rows and actions:
        cursors = [index for index, line in enumerate(drawn) if line.startswith("> ")]
        if len(drawn) != len(state.rows):
            found.append(f"{screen}: draws {len(drawn)} row(s) for {len(state.rows)} in the state")
        elif cursors != [state.cursor]:
            found.append(f"{screen}: the cursor is drawn on {cursors}, not row {state.cursor}")
    if blocks.described and state.session.profile is not PresentationProfile.VERBOSE:
        found.append(f"{screen}: describes the cursor row in Fast")
    if blocks.described and not state.rows:
        found.append(f"{screen}: describes a row on a screen with none")
    title = blocks.trail[0].split(" / ")[-1].removesuffix(" - did not run").casefold()
    for line in (*actions, *blocks.described, *blocks.status, *blocks.notice):
        said = line.strip().removeprefix("> ").removeprefix("- ").strip()
        if said.casefold() == title:
            found.append(f"{screen}: names itself again under the trail: {line!r}")
        if _CONTROL.search(line):
            found.append(f"{screen}: keyboard talk outside the legend: {line!r}")
    return tuple(found)


def _same_rows(
    before: tuple[str, ...], after: tuple[str, ...], old: ConsumerUiState, new: ConsumerUiState
) -> bool:
    """The rows `v` left alone, allowing only a row that names the detail level to name the new one.

    A row showing the stored preference itself, as Settings' detail level does, is a row about the
    very thing `v` changed. The state cannot hold the new preference with the old presentation --
    it keeps the two in step -- so the allowance is stated on the drawn lines instead.
    """

    was, now = (item.session.profile.value.title() for item in (old, new))
    return len(before) == len(after) and all(
        line == drawn or (was in line and line.replace(was, now) == drawn)
        for line, drawn in zip(before, after, strict=True)
    )


def toggle_violations(source: ConsumerScreenSource, state: ConsumerUiState) -> tuple[str, ...]:
    """§167: `v` changes the presentation and nothing else, and pressing it again undoes it.

    Outside a text field `v` must switch the profile, keep selection, focus, drafts, review and
    navigation exactly as they were, and ask for nothing but keeping the preference.
    """

    # A shell that has exited takes no more keys, so there is no `v` to press on its last frame.
    if typing_text(state) or state.quit_pending or state.searching or state.exited:
        return ()
    screen = state.session.screen.value
    event = key_event("v", state, detail=source.detail(state))
    if event is None or event.kind is not ConsumerUiEventKind.TOGGLE_PROFILE:
        return (f"{screen}: v does not switch Fast / Verbose",)
    found: list[str] = []
    after, commands = reduce_consumer_ui(state, event)
    if any(command.kind is not ConsumerUiCommandKind.PERSIST_SETTINGS for command in commands):
        found.append(f"{screen}: v asks for more than keeping the preference")
    # The stored detail level is the choice; the session shows whatever it holds (`_apply_setting`).
    if (
        after.settings.profile is state.settings.profile
        or after.session.profile is not after.settings.profile
    ):
        found.append(f"{screen}: v leaves the profile where it was")
    unchanged = replace(
        after,
        session=after.session.switch_profile(state.session.profile),
        settings=state.settings,
    )
    if unchanged != state:
        found.append(f"{screen}: v changes more than the presentation")
    if not _same_rows(source.actions(state), source.actions(after), state, after):
        # §167's one cursor-description rule: Verbose describes the row under the cursor in the
        # description block, rather than growing every row.
        found.append(f"{screen}: v redraws the rows instead of describing the cursor row")
    back, _ = reduce_consumer_ui(after, event)
    if back != state:
        found.append(f"{screen}: v pressed twice does not return to where it started")
    return tuple(found)
