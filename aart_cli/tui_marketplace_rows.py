"""Lists on a shared grid, one line per row, cut rather than wrapped (§196, §199)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from textwrap import wrap
from typing import Sequence

from aart_cli.tui_layout import Frame, render, wrap_lines

_HEADINGS = (
    "Artifact",
    "Type",
    "Registry",
    "Upstream",
    "Status",
    "Scope",
    "Harnesses",
    "Configuration",
)
_BRIEF = 2
"""Artifact and Type, the columns drawn until `d` asks for the details (INV-297)."""
_GUTTER = 6
_GAP = 2
_CUT = "…"
MARKETPLACE_WINDOW = 10
"""Offers drawn at once; the rest are a page away (INV-277)."""


def _lines(value: str, width: int) -> tuple[str, ...]:
    return tuple(wrap(value, width=width, break_long_words=True, break_on_hyphens=False) or ("",))


def _span(sizes: Sequence[int]) -> int:
    return sum(sizes) + _GAP * (len(sizes) - 1)


def _fit(natural: Sequence[int], available: int, layout: "ColumnLayout") -> list[int] | None:
    """These columns narrowed to fit `available`, or None when their headings alone do not.

    Only the details give up width while any is drawn, widest first, and the brief columns after
    the first only once they are the last ones left. A column is therefore left off before a brief
    one is cut, and the first is cut only when it is drawn alone. No column goes below its heading.
    """

    sizes = list(natural)
    narrowing = range(min(layout.brief, len(sizes) - 1), len(sizes))
    while _span(sizes) > available:
        narrowable = [index for index in narrowing if sizes[index] > len(layout.headings[index])]
        if not narrowable:
            return None
        sizes[max(narrowable, key=lambda index: sizes[index])] -= 1
    return sizes


def _sizes(
    rows: Sequence[Sequence[str]],
    available: int,
    count: int,
    layout: "ColumnLayout",
    indents: Sequence[int],
) -> list[int]:
    """The width of each column drawn: as wide as its widest value when the window has room.

    A column that does not fit even at its heading's width is left off, from the right, so every
    heading drawn is whole. Only a window narrower than the first heading cuts that heading.
    """

    natural = [
        max(
            (
                len(heading),
                *(
                    len(row[index].strip()) + (indent if index == 0 else 0)
                    for row, indent in zip(rows, indents, strict=True)
                    if index < len(row)
                ),
            )
        )
        for index, heading in enumerate(layout.headings[:count])
    ]
    for drawn in range(count, 0, -1):
        fitted = _fit(natural[:drawn], available, layout)
        if fitted is not None:
            return fitted
    return [max(available, 1)]


def _cell(value: str, size: int, indent: int = 0) -> str:
    """The value whole, or its beginning marked `…` when the column is narrower (§196)."""

    value = " " * indent + value.strip()
    if len(value) > size:
        # A cut that ends at a space keeps the column's width, so the next column stays in place.
        value = value[: max(size - 1, 0)].rstrip() + _CUT
    return value[:size].ljust(size)


@dataclass(frozen=True, slots=True)
class ColumnLayout:
    """One list's columns: their headings, how many are drawn without details, and its rows' noun.

    Marketplace and the lists of installations draw through the same grid (§196, §199), so what
    one does with a narrow window the other does too.
    """

    headings: tuple[str, ...]
    brief: int
    noun: str


MARKETPLACE_COLUMNS = ColumnLayout(_HEADINGS, _BRIEF, "Offers")


def render_columns(
    layout: ColumnLayout,
    rows: Sequence[Sequence[str]],
    *,
    current: str,
    selected: tuple[str, ...],
    width: int,
    keys: Sequence[str] | None = None,
    details: bool = True,
    indents: Sequence[int] | None = None,
) -> tuple[str, ...]:
    """Draw each row as one line under whole headings, however narrow the window (INV-274).

    ``width`` is usable columns, with curses's reserved last column already excluded. ``keys``
    identify the rows for the cursor and selection; without them a row is keyed by its first cell.
    Short rows share the same headings. Only the page of ``MARKETPLACE_WINDOW`` rows that holds the
    cursor is drawn, so More info for that row follows the list on screen however many rows there
    are (INV-277). Without ``details`` only the layout's brief columns are drawn, from each row's
    first cells (INV-297, INV-300). ``indents`` shift a row's first cell right, as a Collection's
    members sit under it. Columns the window has no room for are named under the list.
    """

    if width < 1:
        raise ValueError("a list needs at least one usable column")
    headings = layout.headings if details else layout.headings[: layout.brief]
    keyed = list(keys) if keys is not None else [row[0] for row in rows]
    shifts = list(indents) if indents is not None else [0] * len(rows)
    if len(keyed) != len(rows) or len(shifts) != len(rows):
        raise ValueError("a list needs one key and one indent per row")
    focused = keyed.index(current) if current in keyed else 0
    start = focused - focused % MARKETPLACE_WINDOW
    page = rows[start : start + MARKETPLACE_WINDOW]
    drawn: list[str] = []
    sizes = _sizes(rows, max(width - _GUTTER, 1), len(headings), layout, shifts)
    drawn.append(
        (
            " " * _GUTTER
            + (" " * _GAP).join(
                # Only the columns drawn have a size; the rest are named under the list.
                heading[:size].ljust(size)
                for heading, size in zip(headings, sizes, strict=False)
            )
        )[:width].rstrip()
    )
    # The headings are ruled off from the first row, each rule as wide as its column (D-464).
    drawn.append((" " * _GUTTER + (" " * _GAP).join("─" * size for size in sizes))[:width])
    for key, row, indent in zip(
        keyed[start : start + MARKETPLACE_WINDOW],
        page,
        shifts[start : start + MARKETPLACE_WINDOW],
        strict=True,
    ):
        cells = tuple(row) + ("",) * len(headings)
        mark = f"{'>' if key == current else ' '} {'[x]' if key in selected else '[ ]'}"
        line = (" " * _GAP).join(
            _cell(cell, size, indent if index == 0 else 0)
            for index, (cell, size) in enumerate(zip(cells, sizes, strict=False))
        )
        drawn.append((mark + " " + line)[:width].rstrip())
    if rows and len(sizes) < len(headings):
        hidden = f"Widen the window to see: {', '.join(headings[len(sizes) :])}."
        drawn.extend(("", *_lines(hidden, width)))
    if len(rows) > MARKETPLACE_WINDOW:
        counter = f"{layout.noun} {start + 1}–{start + len(page)} of {len(rows)}; ↑/↓ for more."
        drawn.extend(("", *_lines(counter, width)))
    if not rows:
        drawn.extend(_lines("Nothing here yet.", width))
    return tuple(drawn)


def render_marketplace_rows(
    rows: Sequence[Sequence[str]],
    *,
    current: str,
    selected: tuple[str, ...],
    width: int,
    keys: Sequence[str] | None = None,
    details: bool = True,
) -> tuple[str, ...]:
    """Marketplace's offers on :func:`render_columns`: Artifact and Type, then the details."""

    return render_columns(
        MARKETPLACE_COLUMNS,
        rows,
        current=current,
        selected=selected,
        width=width,
        keys=keys,
        details=details,
    )


def marketplace_viewport(
    view: Frame, *, columns: int, height: int, offset: int
) -> tuple[Frame, int]:
    """Page Marketplace's content while keeping its headings and the shared footer.

    Offset -1 follows the focused logical row. Returning the clamped offset prevents repeated
    PageDown at the end from accumulating invisible pages before PageUp can move again.
    """
    if not height:
        return view, offset
    content = wrap_lines(
        render(Frame(actions=view.actions, described=view.described)), width=columns + 1
    )
    first = next((i for i, line in enumerate(content) if line.startswith((">", "  ["))), 0)
    sticky, content = content[:first], content[first:]
    static = replace(view, actions=(), described=())
    overhead = len(wrap_lines(render(static), width=columns + 1)) + 3
    budget = max(height - overhead - len(sticky), 1)
    focused = next((i for i, line in enumerate(content) if line.startswith(">")), 0)
    start = (0 if focused < budget else focused) if offset < 0 else offset
    start = min(max(start, 0), max(len(content) - budget, 0))
    return replace(view, actions=(*sticky, *content[start : start + budget]), described=()), start
