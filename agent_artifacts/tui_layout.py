"""Pure layout kernel for the text and curses TUI (WP-0 of DESIGN-tui-legibility).

Everything decidable without a terminal lives here: how wide content may be, how a record turns
into aligned lines, how the status bar degrades, and how many rows the detail pane may claim. The
curses layer is left with painting and key handling.

Two rules from the design are enforced structurally rather than by convention:

- ``·`` is never a separator. Hints join with ``, ``, records become columns and field blocks.
- content is bounded to a readable measure rather than to the terminal width, because a line too
  long to track is as unread as a line truncated away.
"""

from __future__ import annotations

import textwrap
from typing import Mapping, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Frozen vocabulary.                                                            #
# --------------------------------------------------------------------------- #

READABLE_MEASURE = 80
"""Bound for wrapped prose: summaries, reasons, the detail view."""

CONTENT_MEASURE = 100
"""Bound for structured lines: list rows, the detail pane, aligned columns."""

SECTION_RULE = "─" * 64
"""Restrained boundary shared by body sections and the persistent key footer."""

STAGE_CONFIRMED = "✓"
STAGE_CURRENT = "▸"
STAGE_PENDING = "·"
STAGE_JOIN = "→"
STAGE_PROJECTION = "…"

BOX_CHECKED = "[x]"
BOX_EMPTY = "[ ]"
BOX_DISABLED = "[!]"

HINT_ORDER: Tuple[Tuple[str, str], ...] = (
    ("space", "toggle"),
    ("enter", "confirm"),
    ("b", "back"),
    ("?", "details"),
    ("/", "search"),
    ("a", "add"),
    ("s", "sync"),
    ("i", "resubscribe"),
    ("r", "remove"),
    ("q", "quit"),
)
"""The canonical hint table. Rendering drops from the right, so later entries are cheaper."""

PROTECTED_HINTS = frozenset({"enter", "q"})
"""Hints that survive any width: without them a screen has no documented exit."""

MIN_LIST_ROWS = 3
"""The list never shrinks below this; the pane gives way first."""

CHROME_ROWS = 4
"""Rows a list screen spends on stepper, title, counters, and the status bar."""

PANE_MIN_HEIGHT = 16
"""Below this the detail pane is dropped entirely and ``?`` remains the route to everything."""

_COLUMN_GAP = 2
_LABEL_GAP = 2
_COUNTER_GAP = 3


def _ellipsize(text: str, width: int) -> str:
    """One visual line no wider than *width*, marking truncation with ``…``."""

    if width <= 0:
        return ""
    flat = text.replace("\r", " ").replace("\n", " ")
    if len(flat) <= width:
        return flat
    if width == 1:
        return STAGE_PROJECTION
    return flat[: width - 1] + STAGE_PROJECTION


def measure(width: int, *, bound: int = READABLE_MEASURE) -> int:
    """Bound *width* to a readable measure, never returning less than one column."""

    return min(max(width, 1), max(bound, 1))


def wrap(text: str, *, width: int) -> Tuple[str, ...]:
    """Wrap prose at the readable measure, collapsing embedded line breaks."""

    limit = measure(width)
    flat = text.replace("\r", " ").replace("\n", " ")
    wrapped = textwrap.wrap(
        flat,
        width=limit,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return tuple(wrapped) or ("",)


def _column_widths(rows: Sequence[Sequence[str]], *, budget: int) -> Tuple[int, ...]:
    """Fit natural column widths into *budget*, shrinking the widest later column first.

    The first column is identity and is shrunk only once every other column is down to one
    character, so a long summary can never push a key off screen.
    """

    count = max((len(row) for row in rows), default=0)
    if not count:
        return ()
    widths = [
        max((len(row[index]) for row in rows if index < len(row)), default=0)
        for index in range(count)
    ]
    gaps = _COLUMN_GAP * (count - 1)
    while sum(widths) + gaps > budget:
        shrinkable = [index for index in range(1, count) if widths[index] > 1]
        if not shrinkable:
            shrinkable = [index for index in range(count) if widths[index] > 1]
        if not shrinkable:
            break
        widest = max(shrinkable, key=lambda index: (widths[index], index))
        widths[widest] -= 1
    return tuple(widths)


def columns(rows: Sequence[Sequence[str]], *, width: int) -> Tuple[str, ...]:
    """Lay every row out on one shared column grid, so positions never drift between rows."""

    if not rows:
        return ()
    budget = measure(width, bound=CONTENT_MEASURE)
    widths = _column_widths(rows, budget=budget)
    if not widths:
        return tuple("" for _row in rows)
    lines = []
    for row in rows:
        cells = []
        for index, cell_width in enumerate(widths):
            cell = row[index] if index < len(row) else ""
            cells.append(_ellipsize(cell, cell_width).ljust(cell_width))
        lines.append(_ellipsize((" " * _COLUMN_GAP).join(cells).rstrip(), budget))
    return tuple(lines)


def field_block(fields: Sequence[Tuple[str, str]], *, indent: int, width: int) -> Tuple[str, ...]:
    """Render ``label   value`` lines on one label column, wrapping values under the value column."""

    if not fields:
        return ()
    budget = measure(width, bound=CONTENT_MEASURE)
    pad = " " * max(indent, 0)
    label_width = max(len(label) for label, _value in fields)
    value_column = len(pad) + label_width + _LABEL_GAP
    available = max(budget - value_column, 1)
    lines = []
    for label, value in fields:
        wrapped = wrap(value, width=available) if value else ("",)
        head = f"{pad}{label.ljust(label_width)}{' ' * _LABEL_GAP}{wrapped[0]}"
        lines.append(_ellipsize(head.rstrip(), budget))
        for continuation in wrapped[1:]:
            lines.append(_ellipsize(f"{' ' * value_column}{continuation}".rstrip(), budget))
    return tuple(lines)


def _hint_text(hints: Sequence[Tuple[str, str]]) -> str:
    return ", ".join(f"{key}={action}" for key, action in hints)


def status_bar(
    hints: Sequence[Tuple[str, str]],
    *,
    counters: Sequence[str] = (),
    width: int,
) -> str:
    """Compose the pinned bar: hints on the left, counters right-aligned.

    The bar is exempt from ``CONTENT_MEASURE`` — it is a single line whose value is proportional
    to what fits. Under pressure it sheds counters from the right, then unprotected hints from the
    right, and only then truncates.
    """

    if width <= 0:
        return ""
    remaining = list(hints)
    shown_counters = list(counters)
    while True:
        left = _hint_text(remaining)
        right = (" " * _COUNTER_GAP).join(shown_counters)
        if not right:
            if len(left) <= width:
                return left
        else:
            if len(left) + _COUNTER_GAP + len(right) <= width:
                filler = width - len(left) - len(right)
                return f"{left}{' ' * filler}{right}"
            shown_counters.pop()
            continue
        droppable = [
            index for index, (key, _action) in enumerate(remaining) if key not in PROTECTED_HINTS
        ]
        if not droppable:
            return _ellipsize(left, width)
        remaining.pop(droppable[-1])


def pane_budget(*, height: int, requested: int) -> int:
    """Rows the detail pane may occupy, or zero when the terminal cannot afford one.

    The give-up order is fixed: the pane yields before the list, the list never falls below
    :data:`MIN_LIST_ROWS`, and the status bar is never sacrificed.
    """

    if requested <= 0 or height < PANE_MIN_HEIGHT:
        return 0
    spare = height - CHROME_ROWS - MIN_LIST_ROWS
    if spare <= 0:
        return 0
    return min(requested, spare)


STAGE_MARKERS: Mapping[str, str] = {
    "confirmed": STAGE_CONFIRMED,
    "current": STAGE_CURRENT,
    "pending": STAGE_PENDING,
}

KEY_NAMES = frozenset({"Enter", "Esc", "Space", "Tab", "Backspace"})
"""The keys a screen may address the reader by name. Naming one makes a line a prompt."""


def is_action_prompt(line: str) -> bool:
    """True when a line's subject is a key press: what pressing something will do.

    Read from the line itself rather than from a list of remembered sentences, so a screen written
    tomorrow is held to the same rule as the ones written today.
    """

    if not isinstance(line, str):
        raise ValueError("an action prompt is a line of text")
    stripped = line.strip()
    if not stripped.endswith("."):
        return False
    return any(word.strip(",;:.") in KEY_NAMES for word in stripped.split())


def separate(*blocks: Sequence[str]) -> Tuple[str, ...]:
    """Blocks of lines joined by exactly one blank line, with empty blocks dropped.

    A screen is read in groups, not in lines, and the operator reported that a screen written as
    one undifferentiated block is unreadable -- "powinno byc wiecej pustych linii pomiedzy
    wierszami tekstu" (`QA-029`). Composing groups here keeps the separation exactly one line
    wherever a block turns out to be absent, which is what an ad-hoc ``("", *notice)`` gets wrong.
    """

    kept = []
    for block in blocks:
        lines = [line for line in block]
        if any(not isinstance(line, str) for line in lines):
            raise ValueError("a block is lines of text")
        while lines and not lines[-1].strip():
            lines.pop()
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines:
            kept.append(tuple(lines))
    if not kept:
        return ()
    joined: list[str] = list(kept[0])
    for block in kept[1:]:
        joined.extend(("", *block))
    return tuple(joined)


def section(lines: Sequence[str]) -> Tuple[str, ...]:
    """Put one explanatory region between the shared restrained boundaries."""

    body = separate(lines)
    return () if not body else (SECTION_RULE, *body, SECTION_RULE)


def cards(*blocks: Sequence[str]) -> Tuple[str, ...]:
    """Keep list records visually separate while retaining one compact reading order."""

    return separate(*blocks)


def action_prompt(facts: Sequence[str], prompt: str) -> Tuple[str, ...]:
    """The facts, one blank line, then the single line saying what a key press will do.

    A screen whose only actionable sentence is the ninth line of an undifferentiated block has not
    delivered the action: the reader has to read the whole screen to find the one line addressed to
    them, and reports that it is lost in the text (`QA-029`). The separation is the entire rule, so
    it lives here and is applied at the seam every screen already passes through, rather than being
    a habit each screen has to remember. The prompt goes last because last is where reading stops.
    """

    if not is_action_prompt(prompt):
        raise ValueError(f"not an action prompt: {prompt!r}")
    body = separate(facts)
    if not body:
        return (prompt,)
    return (*body, "", prompt)


BOX_MARKERS: Mapping[str, str] = {
    "checked": BOX_CHECKED,
    "empty": BOX_EMPTY,
    "disabled": BOX_DISABLED,
}

__all__ = [
    "BOX_CHECKED",
    "BOX_DISABLED",
    "BOX_EMPTY",
    "BOX_MARKERS",
    "CHROME_ROWS",
    "CONTENT_MEASURE",
    "HINT_ORDER",
    "KEY_NAMES",
    "MIN_LIST_ROWS",
    "PANE_MIN_HEIGHT",
    "PROTECTED_HINTS",
    "READABLE_MEASURE",
    "SECTION_RULE",
    "STAGE_CONFIRMED",
    "STAGE_CURRENT",
    "STAGE_JOIN",
    "STAGE_MARKERS",
    "STAGE_PENDING",
    "STAGE_PROJECTION",
    "action_prompt",
    "cards",
    "columns",
    "field_block",
    "is_action_prompt",
    "measure",
    "pane_budget",
    "section",
    "separate",
    "status_bar",
    "wrap",
]
