"""INV-285: Marketplace's column headings are ruled off from the offers.

The owner scrolled Marketplace and could not tell the heading line from the first offer: the
headings sat directly on the rows. A rule now runs under each heading, as wide as its column, so
the headings read as headings and each column's width shows even when a cell is cut.
"""

from __future__ import annotations

import re
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.tui_marketplace_rows import _HEADINGS, render_marketplace_rows

_RULE = re.compile(r"─+")
#: The gutter and `Artifact`: the narrowest window whose one heading is whole.
_NARROWEST = 6 + len("Artifact")
_CELL = st.text(alphabet="abcdefghijklmnopqrstuvwxyz/@.-0123456789 ", max_size=40)


def _spans(line: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    return [match.span() for match in pattern.finditer(line)]


class MarketplaceHeadingRuleTest(unittest.TestCase):
    def test_a_rule_separates_the_headings_from_the_first_offer(self) -> None:
        drawn = render_marketplace_rows(
            (("review@1.0.0", "Skill", "company", "acme/skills", "not installed"),),
            current="review@1.0.0",
            selected=(),
            width=120,
        )

        self.assertTrue(drawn[0].lstrip().startswith("Artifact"))
        self.assertEqual(set(drawn[1].strip()), {"─", " "})
        self.assertTrue(drawn[2].startswith("> [ ] review@1.0.0"))

    @given(
        st.lists(st.lists(_CELL, min_size=1, max_size=len(_HEADINGS)), min_size=1, max_size=12),
        st.integers(min_value=_NARROWEST, max_value=200),
        st.booleans(),
    )
    def test_each_rule_starts_under_its_heading_and_spans_its_column(
        self, rows, width, details
    ) -> None:
        keys = [f"offer-{index}" for index in range(len(rows))]
        headings = _HEADINGS if details else _HEADINGS[:2]

        drawn = render_marketplace_rows(
            rows, current=keys[0], selected=(), width=width, keys=keys, details=details
        )

        heading, rule = drawn[0], drawn[1]
        spans = _spans(rule, _RULE)
        # A column the window has no room for is left off whole, from the right (§196).
        headings = headings[: len(spans)]
        self.assertEqual(heading.split(), list(headings))
        starts = [heading.index(name) for name in headings]
        self.assertEqual([start for start, _end in spans], starts)
        for (start, end), name in zip(spans, headings, strict=True):
            self.assertGreaterEqual(end - start, len(name))
        self.assertLessEqual(len(rule), width)
        self.assertTrue(drawn[2].startswith("> "))

    def test_a_narrow_window_rules_off_the_columns_it_draws(self) -> None:
        drawn = render_marketplace_rows(
            (("review@1.0.0", "Skill", "company"),),
            current="review@1.0.0",
            selected=(),
            width=40,
        )

        self.assertEqual(drawn[0].split(), ["Artifact", "Type", "Registry"])
        self.assertEqual(len(_spans(drawn[1], _RULE)), 3)


if __name__ == "__main__":
    unittest.main()
