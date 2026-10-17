"""INV-274: Marketplace fields stay named and complete at every usable width."""

from __future__ import annotations

import dataclasses
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.tui_consumer import frame, run_consumer_shell
from aart_cli.tui_marketplace_rows import render_marketplace_rows
from tests.marketplace_cursor_description_test import _distinct, _listed

HEADINGS = ("Artifact", "Status", "Scope", "Harnesses", "Unset")
ROW = (
    "company/mcp/a-very-long-artifact-coordinate@1.2.3",
    "update available",
    "user + 17 projects",
    "claude ✓, codex ✓, opencode, tabnine",
    "12 not set",
)


def flat(text):
    return "".join(text.split())


class ReadableMarketplaceRowsTest(unittest.TestCase):
    def test_grid_wraps_cells_on_their_headings_and_keeps_full_values(self):
        lines = render_marketplace_rows((ROW,), current=ROW[0], selected=(ROW[0],), width=80)
        header = lines[0]
        starts = [header.index(label) for label in HEADINGS]
        ends = starts[1:] + [80]
        self.assertTrue(lines[1].startswith("> [x] "))
        for value, start, end in zip(ROW, starts, ends, strict=True):
            recovered = "".join(line[start:end].strip() for line in lines[1:])
            self.assertEqual(flat(recovered), flat(value))
        self.assertTrue(all(len(line) <= 80 for line in lines))

    def test_narrow_layout_stacks_labeled_fields_without_ellipsis(self):
        lines = render_marketplace_rows((ROW,), current=ROW[0], selected=(), width=26)
        shown = flat("\n".join(lines))
        for label, value in zip(HEADINGS, ROW, strict=True):
            self.assertIn(flat(label + ":" + value), shown)
        self.assertIn("> [ ]", "\n".join(lines))
        self.assertTrue(all(len(line) <= 26 for line in lines))
        self.assertNotIn("…", "\n".join(lines))

    def test_every_generated_width_preserves_all_labels_and_values(self):
        @given(
            st.integers(min_value=1, max_value=140),
            st.text(alphabet="abcdef0123456789-_/", min_size=1, max_size=180),
        )
        def holds(width, value):
            row = (
                value,
                "update available",
                "user + 17 projects",
                "codex ✓, opencode",
                "3 not set",
            )
            lines = render_marketplace_rows((row,), current=value, selected=(), width=width)
            self.assertTrue(all(len(line) <= width for line in lines))
            if width < 67:
                shown = flat("\n".join(lines))
                for label, cell in zip(HEADINGS, row, strict=True):
                    self.assertIn(flat(label + ":" + cell), shown)
            else:
                starts = [lines[0].index(label) for label in HEADINGS]
                for i, cell in enumerate(row):
                    end = starts[i + 1] if i < 4 else width
                    self.assertEqual(
                        flat("".join(line[starts[i] : end] for line in lines[1:])), flat(cell)
                    )

        holds()

    def test_empty_rows_and_absent_collection_cells_are_explicit(self):
        for width in (1, 26, 80):
            self.assertIn(
                "Nothinghereyet.",
                flat("".join(render_marketplace_rows((), current="", selected=(), width=width))),
            )
        with self.assertRaises(ValueError):
            render_marketplace_rows((), current="", selected=(), width=0)
        lines = render_marketplace_rows(
            (("team/collection/tools@1.0.0", "installed"),), current="", selected=(), width=26
        )
        for label in ("Scope", "Harnesses", "Unset"):
            self.assertIn(label + ": —", "\n".join(lines))

    def test_header_gutter_and_left_aligned_cells_match(self):
        lines = render_marketplace_rows((ROW,), current=ROW[0], selected=(), width=80)
        self.assertTrue(lines[0].startswith("      Artifact"))
        for label, value in zip(HEADINGS, ROW, strict=True):
            self.assertTrue(lines[1][lines[0].index(label) :].startswith(value.split()[0][:5]))

    def test_paging_reaches_every_details_line_and_never_exceeds_generated_viewports(self):
        from aart_cli.tui_layout import Frame, render, wrap_lines
        from aart_cli.tui_marketplace_rows import marketplace_viewport

        @given(st.integers(min_value=15, max_value=120), st.integers(min_value=20, max_value=60))
        def holds(width, height):
            actions = render_marketplace_rows((ROW,), current=ROW[0], selected=(), width=width)
            details = tuple(f"Detail {n:02d}: evidence" for n in range(15))
            view = Frame(
                trail=("Marketplace",), actions=actions, described=details, keys=("[q] Quit",)
            )
            seen = []
            for offset in range(0, 250):
                paged, actual = marketplace_viewport(
                    view, columns=width, height=height, offset=offset
                )
                lines = wrap_lines(render(paged), width=width + 1)
                self.assertLessEqual(len(lines), height)
                self.assertTrue(all(len(line) <= width for line in lines))
                seen.extend(paged.actions)
                if actual < offset:
                    break
            shown = flat("".join(seen))
            for detail in details:
                self.assertIn(flat(detail), shown)
            empty, offset = marketplace_viewport(
                Frame(keys=("[q] Quit",)), columns=width, height=height, offset=-1
            )
            self.assertEqual(offset, 0)
            self.assertIn("[q] Quit", render(empty))

        holds()

    def test_explicit_top_offset_does_not_refollow_a_later_focused_row(self):
        from aart_cli.tui_layout import Frame
        from aart_cli.tui_marketplace_rows import marketplace_viewport

        actions = tuple((">" if i == 25 else " ") + f" [ ] offer-{i:02d}" for i in range(40))
        view = Frame(trail=("Marketplace",), actions=actions, keys=("[q] Quit",))
        automatic, at = marketplace_viewport(view, columns=80, height=20, offset=-1)
        top, offset = marketplace_viewport(view, columns=80, height=20, offset=0)
        self.assertEqual(offset, 0)
        self.assertGreater(at, 0)
        self.assertTrue(automatic.actions[0].startswith(">"))
        self.assertEqual(top.actions[0], actions[0])

    def test_empty_marketplace_has_one_message_and_grid_absent_facts_are_blank(self):
        from aart_cli.application.consumer_views import PresentationProfile

        source, state = _listed(
            dataclasses.replace(_distinct(), marketplace=(), collections=()),
            profile=PresentationProfile.LESS_INFO,
        )
        shown = "\n".join(
            frame(source, dataclasses.replace(state, viewport_columns=80, viewport_rows=30))
        )
        self.assertEqual(shown.count("Nothing here yet."), 1)
        lines = render_marketplace_rows(
            (("team/collection/tools@1.0.0", "installed"),), current="", selected=(), width=80
        )
        start = lines[0].index("Scope")
        self.assertTrue(all(not line[start:].strip() for line in lines[1:]))

    def test_collection_rows_keep_all_column_labels(self):
        lines = render_marketplace_rows(
            (("company/collection/team@1.0.0", "installed"),), current="", selected=(), width=80
        )
        for label in HEADINGS:
            self.assertIn(label, lines[0])
        self.assertIn("installed", "\n".join(lines))

    def test_short_curses_keeps_the_focused_row_and_pages_complete_content(self):
        from aart_cli.application.consumer_views import PresentationProfile
        from aart_cli.tui import _CursesTerminal

        source, state = _listed(_distinct(), profile=PresentationProfile.LESS_INFO)
        state = dataclasses.replace(state, cursor=len(state.rows) - 1)

        class Screen:
            def __init__(self):
                self.frames = []
                self.painted = []
                self.keys = iter((338,) * 100 + (339, ord("q")))

            def clear(self):
                self.painted = []

            def getmaxyx(self):
                return 26, 27

            def addstr(self, row, column, text):
                self.painted.append(text)

            def refresh(self):
                self.frames.append(tuple(self.painted))

            def getch(self):
                return next(self.keys)

        screen = Screen()
        terminal = _CursesTerminal(screen)
        result = run_consumer_shell(source, terminal, state=state)
        self.assertEqual(result.current_row, state.current_row)
        self.assertTrue(any(line.startswith(">") for line in screen.frames[0]))
        self.assertIn("PgUp/PgDn", "\n".join(screen.frames[0]))
        self.assertTrue(all(len(line) <= 26 for view in screen.frames for line in view))
        self.assertIn("Unset: —", "\n".join(screen.frames[-2]))
        self.assertEqual(screen.frames[-3], screen.frames[-2], "the end must clamp")
        self.assertNotEqual(
            screen.frames[-2], screen.frames[-1], "one PageUp must move immediately"
        )

    def test_curses_preserves_the_last_character_of_a_full_width_value(self):
        from aart_cli.tui import _CursesTerminal

        class Screen:
            def clear(self):
                self.lines = []

            def getmaxyx(self):
                return 20, 12

            def addstr(self, row, col, value):
                self.lines.append(value)

            def refresh(self):
                pass

        screen = Screen()
        terminal = _CursesTerminal(screen)
        terminal.draw(("abcdefghijkL", "", "q"))
        self.assertEqual(terminal.columns, 11)
        self.assertEqual(flat("".join(screen.lines[:-1])), "abcdefghijkL")

    def test_shell_uses_resized_terminal_width_without_changing_offer_state(self):
        source, state = _listed(_distinct())
        state = dataclasses.replace(state, selection=(state.current_row,))

        class Terminal:
            columns = 64

            def __init__(self):
                self.frames = []
                self.keys = iter(("resize", "v", "q", "y"))

            def draw(self, lines):
                self.frames.append(lines)

            def key(self):
                key = next(self.keys)
                if key == "resize":
                    self.columns = 26
                return key

        terminal = Terminal()
        result = run_consumer_shell(source, terminal, state=state, settings_writer=lambda _: None)
        self.assertEqual(
            (result.rows, result.cursor, result.selection, result.search),
            (state.rows, state.cursor, state.selection, state.search),
        )
        self.assertIn("Artifact", "\n".join(terminal.frames[0]))
        self.assertIn("Status:", "\n".join(terminal.frames[1]))
        self.assertIn("Harnesses:", "\n".join(terminal.frames[1]))
