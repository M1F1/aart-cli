"""INV-274 as §196 revises it: every Marketplace offer is one line, whatever the window.

The owner saw a Marketplace row wrap onto a second line, and `team-glossary@1.0.0` broken into
`team-glossary@1.0.` and `0`. A row is now always one line. A value too long for its column is cut
and marked `…`, and a wider window shows it whole. A column that does not fit even at its heading's
width is left off, whole, and the list says which columns a wider window shows. Headings that are
drawn are never cut, and Artifact is cut only when it is the one column left.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.tui_marketplace_rows import _HEADINGS, render_marketplace_rows

_GUTTER = 6
_VALUE = st.text(alphabet="abcdefghijklmnopqrstuvwxyz/@.-0123456789 ", min_size=0, max_size=30)
_ROWS = st.lists(st.tuples(*(_VALUE for _ in _HEADINGS)), min_size=1, max_size=10)


def _draw(rows, width: int, details: bool = True) -> tuple[str, ...]:
    keys = [f"offer-{index}" for index in range(len(rows))]
    return render_marketplace_rows(
        rows, current=keys[0], selected=(), width=width, keys=keys, details=details
    )


def _columns(drawn: tuple[str, ...]) -> list[tuple[str, int, int]]:
    """Each drawn column's heading, start and width, read off the rule under the headings."""

    rule = drawn[1]
    spans, start = [], None
    for index, character in enumerate(rule + " "):
        if character == "─" and start is None:
            start = index
        elif character != "─" and start is not None:
            spans.append((start, index - start))
            start = None
    return [(drawn[0][begin : begin + size].strip(), begin, size) for begin, size in spans]


def _shown(value: str, cell: str) -> bool:
    """A cell holds its value whole, or a cut beginning of it marked `…`."""

    value = value.strip()
    if not cell.endswith("…"):
        return cell == value
    return value.startswith(cell[:-1].rstrip()) and len(cell) <= len(value)


class EveryOfferIsOneLine(unittest.TestCase):
    @given(_ROWS, st.integers(min_value=_GUTTER + len("Artifact"), max_value=260), st.booleans())
    def test_a_row_never_wraps_and_never_passes_the_window(self, rows, width, details) -> None:
        drawn = _draw(rows, width, details)

        offers = [line for line in drawn if line.startswith(("> [", "  ["))]
        self.assertEqual(len(offers), len(rows))
        self.assertEqual(drawn[2 : 2 + len(rows)], tuple(offers))
        self.assertTrue(all(len(line) <= width for line in drawn), drawn)

    @given(_ROWS, st.integers(min_value=_GUTTER + len("Artifact"), max_value=260), st.booleans())
    def test_drawn_headings_are_whole_and_cells_are_whole_or_marked_cut(
        self, rows, width, details
    ) -> None:
        drawn = _draw(rows, width, details)
        headings = _HEADINGS if details else _HEADINGS[:2]

        columns = _columns(drawn)
        names = [name for name, _start, _size in columns]
        self.assertEqual(names, list(headings[: len(names)]))
        self.assertGreaterEqual(len(names), 1)
        for line, row in zip(drawn[2:], rows, strict=False):
            for index, (_name, start, size) in enumerate(columns):
                cell = line[start : start + size].strip()
                self.assertTrue(_shown(row[index], cell), (row[index], cell, line))
                if index and len(line) > start:
                    self.assertEqual(line[start - 2 : start], "  ", (line, start))

    @given(_ROWS, st.integers(min_value=_GUTTER + len("Artifact"), max_value=260), st.booleans())
    def test_artifact_is_whole_while_any_other_column_is_drawn(self, rows, width, details) -> None:
        drawn = _draw(rows, width, details)

        columns = _columns(drawn)
        if len(columns) > 1:
            _name, start, size = columns[0]
            for line, row in zip(drawn[2:], rows, strict=False):
                self.assertEqual(line[start : start + size].strip(), row[0].strip())

    @given(_ROWS, st.integers(min_value=_GUTTER + len("Artifact"), max_value=200), st.booleans())
    def test_a_wider_window_never_shows_less(self, rows, width, details) -> None:
        narrow = _columns(_draw(rows, width, details))
        wide = _columns(_draw(rows, width + 1, details))

        self.assertGreaterEqual(len(wide), len(narrow))

    @given(_ROWS, st.integers(min_value=_GUTTER + len("Artifact"), max_value=260), st.booleans())
    def test_the_list_names_the_columns_a_wider_window_shows(self, rows, width, details) -> None:
        drawn = _draw(rows, width, details)
        headings = _HEADINGS if details else _HEADINGS[:2]

        left_off = headings[len(_columns(drawn)) :]
        said = " ".join(" ".join(drawn[2 + len(rows) :]).split())
        if left_off:
            self.assertIn(f"Widen the window to see: {', '.join(left_off)}.", said)
        else:
            self.assertNotIn("Widen the window", said)

    @given(_ROWS, st.booleans())
    def test_a_window_wide_enough_cuts_nothing(self, rows, details) -> None:
        count = len(_HEADINGS) if details else 2
        natural = sum(
            max(len(heading), *(len(row[index].strip()) for row in rows))
            for index, heading in enumerate(_HEADINGS[:count])
        )
        width = _GUTTER + natural + 2 * (count - 1)

        drawn = _draw(rows, width, details)

        self.assertEqual(len(_columns(drawn)), count)
        self.assertNotIn("…", "\n".join(drawn))


class CutCellsKeepTheGrid(unittest.TestCase):
    def test_a_value_cut_at_a_space_still_fills_its_column(self) -> None:
        rows = (
            ("manual-check@1.0.1", "Skill", "lab", "skill", "update available", "user + 1 project",
             "claude, opencode", "configured"),
            ("code-review@1.0.0", "Skill", "lab", "catalog", "installed", "1 project",
             "claude ✓, opencode ✓", "configured"),
        )  # fmt: skip

        # Artifact and Type whole and every detail at its heading's width, so `claude, opencode`
        # is cut just after its space.
        whole = len("manual-check@1.0.1") - len("Artifact") + len("Skill") - len("Type")
        drawn = _draw(rows, 6 + sum(len(heading) for heading in _HEADINGS) + 2 * 7 + whole)

        columns = _columns(drawn)
        self.assertEqual([name for name, *_ in columns], list(_HEADINGS))
        for line in drawn[2:4]:
            for _name, start, _size in columns[1:]:
                self.assertEqual(line[start - 2 : start], "  ", (line, start))
        _name, start, size = columns[6]
        self.assertEqual(drawn[2][start : start + size], "claude,… ")


class TheOwnersRows(unittest.TestCase):
    def test_team_glossary_is_never_broken_across_lines(self) -> None:
        rows = (
            ("guard-bash@1.0.0", "Hook", "lab", "catalog", "not installed", "", "claude", ""),
            (
                "team-glossary@1.0.0",
                "Memory",
                "lab",
                "catalog",
                "not installed",
                "",
                "claude, tabnine",
                "",
            ),
            (
                "manual-check@1.0.1",
                "Skill",
                "lab",
                "skill",
                "update available",
                "user + 1 project",
                "claude ✓, opencode, tabnine",
                "not configured (1 missing)",
            ),
        )

        for width in (60, 80, 100, 130):
            with self.subTest(width=width):
                drawn = _draw(rows, width)
                self.assertEqual(
                    [line[_GUTTER:].split()[0] for line in drawn[2:5]],
                    ["guard-bash@1.0.0", "team-glossary@1.0.0", "manual-check@1.0.1"],
                )
                self.assertFalse(drawn[5:6] and drawn[5].strip(), drawn)
                self.assertTrue(all(len(line) <= width for line in drawn), drawn)


if __name__ == "__main__":
    unittest.main()
