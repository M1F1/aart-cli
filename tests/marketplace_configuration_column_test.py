"""INV-281: a row says whether an installation is configured, in words a reader understands.

The column was `Unset` with a count such as `3 not set`. The owner could not tell what it meant.
It is `Configuration` now: `configured` when every input has a value, `not configured (N missing)`
while any input still holds `AART_NOT_SET`, and empty for an offer nothing installs.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    configuration_cell,
    installed_cells,
    marketplace_cells,
)
from aart_cli.tui_marketplace_rows import render_marketplace_rows
from tests.marketplace_columns_e2e_test import _view

_KEY = "company/skill/review@1.2.0"


class ConfigurationCellTest(unittest.TestCase):
    def test_the_words_say_configured_or_how_many_inputs_are_missing(self) -> None:
        self.assertEqual(configuration_cell(0, installed=False), "")
        self.assertEqual(configuration_cell(0, installed=True), "configured")
        self.assertEqual(configuration_cell(1, installed=True), "not configured (1 missing)")
        self.assertEqual(configuration_cell(3, installed=True), "not configured (3 missing)")

    @given(st.lists(st.integers(min_value=0, max_value=4), max_size=5))
    def test_an_offer_sums_the_missing_inputs_of_every_installation(self, counts) -> None:
        installed = tuple(
            _view(_KEY, "claude", root=f"/p/{index}", unset=tuple("X" * count))
            for index, count in enumerate(counts)
        )

        cell = marketplace_cells(_KEY, installed, ("claude",))[-1]

        missing = sum(counts)
        if not counts:
            self.assertEqual(cell, "")
        elif missing:
            self.assertEqual(cell, f"not configured ({missing} missing)")
        else:
            self.assertEqual(cell, "configured")

    def test_an_installation_says_its_own_configuration(self) -> None:
        self.assertEqual(
            installed_cells(_view(_KEY, "claude", unset=("A", "B")), "ready")[-1],
            "not configured (2 missing)",
        )
        self.assertEqual(installed_cells(_view(_KEY, "claude"), "ready")[-1], "configured")

    def test_the_heading_is_configuration_and_unset_is_gone(self) -> None:
        cells = (
            "skill/review@1.2.0",
            "company",
            "",
            "installed",
            "project",
            "claude ✓",
            "not configured (2 missing)",
        )

        wide = render_marketplace_rows((cells,), current=_KEY, selected=(), keys=(_KEY,), width=160)
        narrow = render_marketplace_rows(
            (cells,), current=_KEY, selected=(), keys=(_KEY,), width=40
        )

        self.assertIn("Configuration", wide[0])
        self.assertIn("not configured (2 missing)", wide[2])
        self.assertIn("Configuration: not configured", " ".join(" ".join(narrow).split()))
        self.assertNotIn("Unset", "\n".join((*wide, *narrow)))


if __name__ == "__main__":
    unittest.main()
