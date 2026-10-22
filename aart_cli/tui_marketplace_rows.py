"""Complete Marketplace cells on a shared grid, or labeled rows in a narrow viewport."""

from __future__ import annotations

from dataclasses import replace
from itertools import zip_longest
from textwrap import wrap
from typing import Sequence

from aart_cli.tui_layout import Frame, render, wrap_lines

_HEADINGS = ("Artifact", "Registry", "Upstream", "Status", "Scope", "Harnesses", "Configuration")
_MINIMUM = (8, 8, 8, 9, 5, 9, 13)
"""Never below a heading, so the header line names every column in full (INV-274)."""
_GUTTER = 6
_GAP = 2
_GRID_MINIMUM = _GUTTER + sum(_MINIMUM) + _GAP * (len(_HEADINGS) - 1)
MARKETPLACE_WINDOW = 10
"""Offers drawn at once; the rest are a page away (INV-277)."""


def _lines(value: str, width: int, *, indent: int = 0) -> tuple[str, ...]:
    return tuple(
        wrap(
            value,
            width=width,
            subsequent_indent=" " * min(indent, max(width - 1, 0)),
            break_long_words=True,
            break_on_hyphens=False,
        )
        or ("",)
    )


def _sizes(rows: Sequence[Sequence[str]], available: int) -> list[int]:
    """Each column as wide as its widest value, narrowed widest-first only when they do not fit.

    A row then takes one line whenever the terminal has room for it (D-456); a column wraps only
    after every wider column has given up its excess, and never below its minimum.
    """

    sizes = [
        max(minimum, len(heading), *(len(row[index]) for row in rows if index < len(row)))
        for index, (heading, minimum) in enumerate(zip(_HEADINGS, _MINIMUM, strict=True))
    ]
    while sum(sizes) > available:
        widest = max(
            (index for index, size in enumerate(sizes) if size > _MINIMUM[index]),
            key=lambda index: sizes[index],
        )
        sizes[widest] -= 1
    return sizes


def render_marketplace_rows(
    rows: Sequence[Sequence[str]],
    *,
    current: str,
    selected: tuple[str, ...],
    width: int,
    keys: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Keep complete cells and logical row identity independent of physical line count.

    ``width`` is usable columns, with curses's reserved last column already excluded. ``keys``
    identify the rows for the cursor and selection; without them a row is keyed by its first cell.
    Empty cells remain explicit in stacked mode; short Collection rows share the same headings.
    Only the page of ``MARKETPLACE_WINDOW`` offers that holds the cursor is drawn, so More info
    for that offer follows the list on screen however many offers there are (INV-277).
    """

    if width < 1:
        raise ValueError("Marketplace needs at least one usable column")
    grid = width >= _GRID_MINIMUM
    keyed = list(keys) if keys is not None else [row[0] for row in rows]
    if len(keyed) != len(rows):
        raise ValueError("Marketplace needs one key per row")
    focused = keyed.index(current) if current in keyed else 0
    start = focused - focused % MARKETPLACE_WINDOW
    page = rows[start : start + MARKETPLACE_WINDOW]
    drawn: list[str] = []
    if grid:
        sizes = _sizes(rows, width - _GUTTER - _GAP * (len(_HEADINGS) - 1))
        drawn.append(
            " " * _GUTTER
            + (" " * _GAP)
            .join(heading.ljust(size) for heading, size in zip(_HEADINGS, sizes, strict=True))
            .rstrip()
        )
        # The headings are ruled off from the first offer, each rule as wide as its column (D-464).
        drawn.append(" " * _GUTTER + (" " * _GAP).join("─" * size for size in sizes))
    for key, row in zip(keyed[start : start + MARKETPLACE_WINDOW], page, strict=True):
        cells = tuple(row) + ("",) * (len(_HEADINGS) - len(row))
        mark = f"{'>' if key == current else ' '} {'[x]' if key in selected else '[ ]'}"
        if grid:
            wrapped = [_lines(cell, size) for cell, size in zip(cells, sizes, strict=True)]
            for index, parts in enumerate(zip_longest(*wrapped, fillvalue="")):
                prefix = mark + " " if index == 0 else " " * _GUTTER
                drawn.append(
                    (
                        prefix
                        + (" " * _GAP).join(
                            part.ljust(size) for part, size in zip(parts, sizes, strict=True)
                        )
                    ).rstrip()
                )
        else:
            drawn.extend(_lines(mark, width))
            for heading, cell in zip(_HEADINGS, cells, strict=True):
                drawn.extend(_lines(f"  {heading}: {cell or '—'}", width, indent=4))
            # Stacked fields need a boundary between offers; a grid row is its own line (D-456).
            drawn.append("")
    if len(rows) > MARKETPLACE_WINDOW:
        counter = f"Offers {start + 1}–{start + len(page)} of {len(rows)}; ↑/↓ for more."
        drawn.extend(("", *_lines(counter, width)))
    if not rows:
        drawn.extend(_lines("Nothing here yet.", width))
    return tuple(drawn)


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
