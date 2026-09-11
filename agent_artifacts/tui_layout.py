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


HOME_MARKER = "~"
"""Home written as one character, so a path says where it is without saying who is reading it."""


def abbreviate_path(path: str, *, home: str = "", width: int = CONTENT_MEASURE) -> str:
    """One line naming a directory: home written as ``~``, and length bought from the front.

    A directory is identified by its tail -- the thing somebody is actually in -- so when the path
    will not fit, the leading segments are what goes. Ellipsizing the end instead would spend the
    line on the part that is the same for every checkout and drop the only part that answers the
    question the line exists to answer (`QA-053`).
    """

    if not isinstance(path, str):
        raise ValueError("a path is a line of text")
    shown = path.replace("\r", " ").replace("\n", " ").strip()
    if not shown:
        return ""
    if home:
        base = home.replace("\r", " ").replace("\n", " ").strip().rstrip("/")
        if base and (shown == base or shown.startswith(base + "/")):
            shown = HOME_MARKER + shown[len(base) :]
    if len(shown) <= width:
        return shown
    segments = [segment for segment in shown.split("/") if segment]
    for index in range(1, len(segments)):
        candidate = f"{STAGE_PROJECTION}/" + "/".join(segments[index:])
        if len(candidate) <= width:
            return candidate
    return _ellipsize(segments[-1] if segments else shown, width)


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
    return () if not body else (SECTION_RULE, "", *body, "", SECTION_RULE)


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


def screen_frame(
    *regions: Sequence[str],
    footer: Sequence[str],
    context: Sequence[str] = (),
) -> Tuple[str, ...]:
    """The one skeleton every screen fills: regions in order, rules only between the ones that spoke.

    The operator's complaint was that each screen composed itself -- *"teraz to jest wolna
    amerykanka odnosnie UI"* (`QA-067`) -- so sections, spacing and the legend landed at different
    heights depending on which screen had been written when. Composing here makes the arrangement a
    property of the frame rather than a habit each screen has to remember.

    A rule is a *separator*, which is the whole reason the empty-section fault disappears. It is
    drawn between two regions that both have something to say, never around a region, so a region
    that turns out empty takes its rule with it instead of leaving the pair of rules with nothing
    between them that `QA-065` reported. The blank either side of a rule comes from the same place,
    so text never touches a boundary.

    The footer is a region that is always drawn, because a screen with no documented way out is the
    first-run trap the legend exists to remove. It is passed separately rather than as the last
    region for exactly that reason: the others may all be empty and it still appears.

    ``context`` is the footer's caption -- the standing fact a reader needs in order to know what
    the keys below it would act on, which today is the directory the session was launched in. It is
    the one line drawn *flush* on a rule, with no blank between them, and that is the whole point
    (`QA-086`): a blank would read as a section that merely happens to sit last, where touching the
    rule says it belongs to the block beneath it. Being part of the footer block is also what puts
    the terminal's padding above it rather than under it, and what keeps it on screen when a long
    body is clipped.
    """

    kept: list[Tuple[str, ...]] = []
    for region in regions:
        kept.append(_region(region))
    caption, keys = _region(context), _region(footer)
    composed: list[str] = []
    for region in (*kept, caption):
        if not region:
            continue
        if composed:
            composed.extend(("", SECTION_RULE, ""))
        composed.extend(region)
    if keys:
        if caption:
            composed.extend((SECTION_RULE, ""))
        elif composed:
            composed.extend(("", SECTION_RULE, ""))
        composed.extend(keys)
    return tuple(composed)


def _region(region: Sequence[str]) -> Tuple[str, ...]:
    """One region of a frame, checked and trimmed, or nothing at all."""

    lines = tuple(region)
    if any(not isinstance(line, str) for line in lines):
        raise ValueError("a screen region is lines of text")
    return separate(lines)


def footer_start(lines: Sequence[str]) -> int:
    """Where the persistent key footer begins: the last rule, and everything after it.

    ``screen_frame`` separates regions with rules and draws the footer last, so the final rule is
    the footer's own boundary by construction. Reading it back off the composed frame keeps the
    terminal free of any knowledge of what a screen contains -- it places a block it can find,
    rather than being told a row number by something that would have to guess the height.

    A frame with no rule at all still has a last line, and the last line is where the way out
    lives, so that is what is returned rather than "no footer". Answering "nothing" would let a
    body long enough to fill the terminal clip the only documented exit off the screen (`B-077`).

    The block reaches back over whatever stands flush on that rule, because ``screen_frame`` leaves
    a blank above every rule it draws except the one under a caption (`QA-086`). So the frame says
    where its own footer begins without the terminal being told: text touching the last rule is the
    footer's caption and belongs to the block, and padding lands above it rather than between them.
    """

    for index in range(len(lines) - 1, -1, -1):
        if lines[index] == SECTION_RULE:
            start = index
            while start and lines[start - 1] != "":
                start -= 1
            return start
    return max(len(lines) - 1, 0)


def anchor(lines: Sequence[str], *, height: int) -> Tuple[str, ...]:
    """Pad above the footer so it sits on the bottom row of a terminal this tall (`QA-068`).

    On a short screen the legend used to float directly under the body with the rest of the
    terminal blank beneath it, so the eye had to hunt for the keys at a different height on every
    screen. The padding goes above the footer rather than below it because below it there is
    nothing: the footer is the last thing read, and last is where reading stops.

    A frame taller than the terminal is returned untouched. Deciding what to drop is clipping, and
    clipping is the terminal's job -- this function only ever adds blank rows.
    """

    if not isinstance(height, int) or isinstance(height, bool) or height < 0:
        raise ValueError("anchoring needs a terminal height in rows")
    body = tuple(lines)
    if len(body) >= height:
        return body
    start = footer_start(body)
    return (*body[:start], *("",) * (height - len(body)), *body[start:])


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
    "HOME_MARKER",
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
    "abbreviate_path",
    "action_prompt",
    "anchor",
    "cards",
    "columns",
    "field_block",
    "footer_start",
    "is_action_prompt",
    "measure",
    "pane_budget",
    "screen_frame",
    "section",
    "separate",
    "status_bar",
    "wrap",
]
