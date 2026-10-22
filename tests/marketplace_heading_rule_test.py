"""INV-285: Marketplace's column headings are ruled off from the offers.

The owner scrolled Marketplace and could not tell the heading line from the first offer: the
headings sat directly on the rows. A rule now runs under each heading, as wide as its column, so
the headings read as headings and each column's width shows even when a cell wraps.
"""

from __future__ import annotations

import re
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.tui_marketplace_rows import _GRID_MINIMUM, _HEADINGS, render_marketplace_rows

_RULE = re.compile(r"─+")
_CELL = st.text(alphabet="abcdefghijklmnopqrstuvwxyz/@.-0123456789 ", max_size=40)


def _spans(line: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    return [match.span() for match in pattern.finditer(line)]


class MarketplaceHeadingRuleTest(unittest.TestCase):
    def test_a_rule_separates_the_headings_from_the_first_offer(self) -> None:
        drawn = render_marketplace_rows(
            (("skill/review@1.0.0", "company", "acme/skills", "not installed"),),
            current="skill/review@1.0.0",
            selected=(),
            width=120,
        )

        self.assertTrue(drawn[0].lstrip().startswith("Artifact"))
        self.assertEqual(set(drawn[1].strip()), {"─", " "})
        self.assertTrue(drawn[2].startswith("> [ ] skill/review@1.0.0"))

    @given(
        st.lists(st.lists(_CELL, min_size=1, max_size=len(_HEADINGS)), min_size=1, max_size=12),
        st.integers(min_value=_GRID_MINIMUM, max_value=200),
    )
    def test_each_rule_starts_under_its_heading_and_spans_its_column(self, rows, width) -> None:
        keys = [f"offer-{index}" for index in range(len(rows))]

        drawn = render_marketplace_rows(rows, current=keys[0], selected=(), width=width, keys=keys)

        heading, rule = drawn[0], drawn[1]
        starts = [heading.index(name) for name in _HEADINGS]
        spans = _spans(rule, _RULE)
        self.assertEqual([start for start, _end in spans], starts)
        for (start, end), name in zip(spans, _HEADINGS, strict=True):
            self.assertGreaterEqual(end - start, len(name))
        self.assertLessEqual(len(rule), width)
        self.assertTrue(drawn[2].startswith("> "))

    def test_the_narrow_stacked_form_has_no_heading_line_to_rule(self) -> None:
        drawn = render_marketplace_rows(
            (("skill/review@1.0.0", "company"),),
            current="skill/review@1.0.0",
            selected=(),
            width=_GRID_MINIMUM - 1,
        )

        self.assertNotIn("─", "\n".join(drawn))


if __name__ == "__main__":
    unittest.main()
