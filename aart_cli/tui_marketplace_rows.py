"""Complete Marketplace cells on a shared grid, or labeled rows in a narrow viewport."""

from __future__ import annotations

from dataclasses import replace
from itertools import zip_longest
from textwrap import wrap
from typing import Sequence

from aart_cli.tui_layout import Frame, render, wrap_lines

_HEADINGS = ("Artifact", "Status", "Scope", "Harnesses", "Unset")
_MINIMUM = (16, 16, 7, 9, 5)
_GUTTER = 6
_GAP = 2
_GRID_MINIMUM = _GUTTER + sum(_MINIMUM) + _GAP * (len(_HEADINGS) - 1)


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


def render_marketplace_rows(
    rows: Sequence[Sequence[str]], *, current: str, selected: tuple[str, ...], width: int
) -> tuple[str, ...]:
    """Keep complete cells and logical row identity independent of physical line count.

    ``width`` is usable columns, with curses's reserved last column already excluded.
    Empty cells remain explicit in stacked mode; short Collection rows share the same headings.
    """

    if width < 1:
        raise ValueError("Marketplace needs at least one usable column")
    grid = width >= _GRID_MINIMUM
    sizes = (_MINIMUM[0] + max(width - _GRID_MINIMUM, 0), *_MINIMUM[1:])
    drawn: list[str] = []
    if grid:
        drawn.append(
            " " * _GUTTER
            + (" " * _GAP)
            .join(heading.ljust(size) for heading, size in zip(_HEADINGS, sizes, strict=True))
            .rstrip()
        )
    for row in rows:
        key = row[0]
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
        drawn.append("")
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
