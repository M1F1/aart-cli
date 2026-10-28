"""INV-277: Marketplace lists at most ten offers, so More info stays on screen."""

from __future__ import annotations

import dataclasses
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.tui_consumer import MarketplaceEntry, frame
from aart_cli.tui_marketplace_rows import _HEADINGS, MARKETPLACE_WINDOW, render_marketplace_rows
from tests.marketplace_cursor_description_test import _distinct, _listed


def _keys(count: int) -> tuple[str, ...]:
    return tuple(f"company/skill/offer-{index:03d}@1.0.0" for index in range(count))


def _shown(keys: tuple[str, ...], lines: tuple[str, ...]) -> tuple[str, ...]:
    drawn = "".join("".join(lines).split())
    return tuple(key for key in keys if key.rpartition("/")[2] in drawn)


def _many(count: int):
    composed = _distinct()
    row = composed.marketplace[0].row
    offers = tuple(
        MarketplaceEntry(
            dataclasses.replace(
                row,
                key=f"{row.source_alias}/{row.identity.kind}/offer-{index:03d}@{row.version}",
                identity=dataclasses.replace(row.identity, name=f"offer-{index:03d}"),
                summary=f"Summary number {index}.",
            )
        )
        for index in range(count)
    )
    return dataclasses.replace(composed, marketplace=offers, collections=())


class MarketplaceListWindowTest(unittest.TestCase):
    def test_the_list_is_the_page_of_ten_that_holds_the_cursor(self):
        @given(
            st.integers(min_value=0, max_value=60),
            st.data(),
            st.sampled_from((25, 120)),
            st.booleans(),
        )
        def holds(count, data, width, details):
            keys = _keys(count)
            current = data.draw(st.sampled_from(keys)) if keys else ""
            lines = render_marketplace_rows(
                tuple(
                    (key.rpartition("/")[2], "Skill", "company", "acme/skills", "not installed")
                    for key in keys
                ),
                current=current,
                selected=(),
                width=width,
                keys=keys,
                details=details,
            )
            shown = _shown(keys, lines)
            self.assertLessEqual(len(shown), MARKETPLACE_WINDOW)
            if not keys:
                return
            index = keys.index(current)
            start = index - index % MARKETPLACE_WINDOW
            self.assertEqual(shown, keys[start : start + MARKETPLACE_WINDOW])
            counter = f"Offers {start + 1}–{start + len(shown)} of {count}; ↑/↓ for more."
            drawn = " ".join(" ".join(lines).split())
            self.assertEqual(counter in drawn, count > MARKETPLACE_WINDOW)
            self.assertEqual("Offers " in drawn, count > MARKETPLACE_WINDOW)

        holds()

    def test_each_offer_is_one_line_under_the_headings_when_the_terminal_has_room(self):
        rows = (
            (
                "database@1.2.3",
                "MCP",
                "company",
                "acme/database-server",
                "update available",
                "user + 2 projects",
                "claude ✓, codex ✓, opencode, tabnine",
                "not configured (3 missing)",
            ),
            (
                "review@1.0.0",
                "Skill",
                "company",
                "obra/superpowers",
                "not installed",
                "",
                "claude, codex",
                "",
            ),
            ("tools@1.0.0", "Collection", "team", "", "installed"),
        )
        widest = [
            max(len(heading), *(len(row[i]) for row in rows if i < len(row)))
            for i, heading in enumerate(_HEADINGS)
        ]
        natural = 6 + sum(widest) + 2 * 7
        for width in (natural, 180):
            lines = render_marketplace_rows(
                rows, current=rows[1][0], selected=(), width=width, details=True
            )
            self.assertEqual(len(lines), 2 + len(rows), lines)
            self.assertTrue(lines[0].startswith("      Artifact"))
            for line, row in zip(lines[2:], rows, strict=True):
                for cell in row:
                    self.assertIn(cell, line)
        # Narrower, a value is cut and marked rather than wrapped onto a second line (§196).
        cut = render_marketplace_rows(
            rows, current="", selected=(), width=natural - 1, details=True
        )
        self.assertEqual(len(cut), 2 + len(rows), cut)
        self.assertIn("…", "\n".join(cut))

    def test_more_info_of_a_late_offer_is_on_the_first_screen(self):
        source, state = _listed(_many(60))
        state = dataclasses.replace(state, cursor=37, viewport_columns=100, viewport_rows=60)
        drawn = "\n".join(frame(source, state))
        self.assertIn("Offers 31–40 of 60", drawn)
        self.assertIn("offer-037", drawn)
        self.assertNotIn("offer-000", drawn)
        for line in source.description(state)[:5]:
            self.assertIn(line.strip(), drawn)


if __name__ == "__main__":
    unittest.main()
