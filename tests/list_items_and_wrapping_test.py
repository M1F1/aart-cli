"""D-386, D-389: list items take a dash, open lower-case, stand a blank line apart, and wrap.

The operator asked for numbers and lower case (*"wypisuj te rzeczy jako lista z numerkami i
zaczynaj od malej litery podpunkt"*), then wrapping and a blank line between items (*"gdy tekst
nie miesci sie w linijce mozesz go zawijac? ... przy kazdym bullet albo podpunkcie mozesz je
oddzielac pusta linia"*), then took the numbers back: *"jednak wrzucanie wszedzie tych cyferek
bylo bledem"* -- a number beside a count read as the count on the Dashboard (D-389).
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.tui_layout import (
    SECTION_RULE,
    bulleted,
    listed,
    lowercase_first,
    stated,
    wrap_lines,
)


class NumberedListsTest(unittest.TestCase):
    def test_items_are_dashed_lower_case_and_a_blank_line_apart(self) -> None:
        self.assertEqual(
            listed(("Install its Python dependencies with pip", "Store the credential")),
            ("  - install its Python dependencies with pip", "", "  - store the credential"),
        )

    def test_a_hyphenated_word_is_lowered_like_any_other(self) -> None:
        self.assertEqual(lowercase_first("Re-run the build"), "re-run the build")

    def test_names_and_acronyms_keep_their_case(self) -> None:
        for name in (
            "GitHub token",
            "MCP server",
            "AART home",
            "company/mcp/github@1.0.0",
            "Maintainer Mode off hides Sources",
            "Source Sync does not promote Candidates",
        ):
            self.assertEqual(lowercase_first(name), name)

    def test_a_status_is_a_dashed_list_of_lower_case_statements(self) -> None:
        self.assertEqual(
            bulleted(stated(("2 ready", "", "Actions: repair issues."))),
            ("- 2 ready", "", "- actions: repair issues."),
        )


class WrappingTest(unittest.TestCase):
    def test_a_long_item_wraps_under_its_own_text(self) -> None:
        line = "  - install its Python dependencies with pip into the private environment"

        self.assertEqual(
            wrap_lines((line,), width=40),
            (
                "  - install its Python dependencies",
                "    with pip into the private",
                "    environment",
            ),
        )

    def test_a_cursor_row_wraps_under_its_label(self) -> None:
        wrapped = wrap_lines(
            ("> [ ] company/skill/review  a review skill for pull requests",), width=30
        )

        self.assertEqual(wrapped[0], "> [ ] company/skill/review  a")
        self.assertTrue(all(line.startswith("      ") for line in wrapped[1:]), wrapped)

    def test_a_section_rule_is_never_split(self) -> None:
        self.assertEqual(wrap_lines((SECTION_RULE,), width=20), (SECTION_RULE[:19],))

    @given(
        st.lists(
            st.text(
                alphabet=st.characters(codec="ascii", categories=("L", "N", "Zs")), max_size=200
            ),
            max_size=8,
        ),
        st.integers(min_value=12, max_value=120),
    )
    def test_no_line_is_wider_than_the_terminal_and_no_word_is_lost(self, lines, width) -> None:
        wrapped = wrap_lines(tuple(lines), width=width)

        self.assertTrue(all(len(line) <= width - 1 for line in wrapped), wrapped)
        self.assertEqual("".join("".join(lines).split()), "".join("".join(wrapped).split()))


class TheTerminalWrapsTest(unittest.TestCase):
    def test_a_line_wider_than_the_terminal_is_drawn_whole_on_two_rows(self) -> None:
        from aart_cli import tui
        from aart_cli.tui_layout import Frame, render
        from tests.screen_skeleton_test import _Screen

        screen = _Screen(height=24, width=40)
        item = "  - install its Python dependencies with pip into the private environment"
        tui._CursesTerminal(screen).draw(render(Frame(trail=("heading",), status=(item,))))

        painted = [value for _, _, value in screen.written]
        self.assertIn("  - install its Python dependencies", painted)
        self.assertIn("    environment", painted)


if __name__ == "__main__":
    unittest.main()
