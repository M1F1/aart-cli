"""CP-21 step 4: one skeleton every screen fills (`QA-065`, `QA-067`, `QA-068`, `QA-070`).

The operator's words for what these replace are *"teraz to jest wolna amerykanka odnosnie UI"*:
sections and the key legend sat at different heights on different screens, rules touched their text,
and an empty section was still drawn as a pair of rules with nothing between them. Every claim here
is stated over a rendered frame rather than over an intention, because the finding is about what the
screen looks like.
"""

from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from agent_artifacts import tui
from agent_artifacts.application.consumer_ui import ConsumerUiState, key_bindings
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    RegistryView,
    project_dashboard,
)
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, frame
from agent_artifacts.tui_layout import SECTION_RULE, anchor, footer_start, screen_frame


def _registry(alias: str) -> RegistryView:
    return RegistryView(
        alias,
        "connected",
        "healthy",
        2,
        0,
        "registry-git",
        f"https://git.example/{alias}.git",
        "main",
        "a" * 40,
        "sha256:" + "b" * 64,
        ("registry-reviewed",),
    )


class ScreenSkeletonKernelTest(TestCase):
    """The composition rule, decided without a terminal."""

    def test_one_rule_separates_two_regions_and_a_blank_stands_either_side_of_it(self) -> None:
        lines = screen_frame(("title",), ("body",), footer=("keys",))

        self.assertEqual(
            lines,
            ("title", "", SECTION_RULE, "", "body", "", SECTION_RULE, "", "keys"),
        )

    def test_an_empty_region_takes_its_rule_with_it(self) -> None:
        """`QA-065`: an empty section was drawn as two rules with nothing between them."""

        lines = screen_frame(("title",), (), ("body",), footer=("keys",))

        self.assertEqual(
            lines,
            ("title", "", SECTION_RULE, "", "body", "", SECTION_RULE, "", "keys"),
        )
        self.assertNotIn(
            (SECTION_RULE, SECTION_RULE),
            tuple(zip(lines, lines[1:], strict=False)),
        )

    def test_a_region_of_nothing_but_blanks_counts_as_empty(self) -> None:
        lines = screen_frame(("title",), ("", "   ", ""), footer=("keys",))

        self.assertEqual(lines.count(SECTION_RULE), 1)

    def test_the_footer_is_always_drawn_even_when_every_region_is_empty(self) -> None:
        self.assertEqual(screen_frame((), (), footer=("keys",)), ("keys",))

    def test_the_footer_begins_at_the_last_rule_so_the_terminal_can_place_it_whole(self) -> None:
        lines = screen_frame(("title",), ("body",), footer=("local", "global"))

        self.assertEqual(lines[footer_start(lines) :], (SECTION_RULE, "", "local", "global"))

    def test_the_context_line_stands_flush_on_the_footer_rule(self) -> None:
        """`QA-086`: the launch directory is the footer's caption, not a section above it.

        The operator drew it -- *"chce zeby working at bylo tu - to sie tyczy wszystkich
        widokow"*. A blank between the line and the rule would read as a section that happens to
        sit last; touching the rule is what says it belongs to the block below it.
        """

        lines = screen_frame(("title",), ("body",), context=("at /lab",), footer=("keys",))

        self.assertEqual(
            lines,
            (
                "title",
                "",
                SECTION_RULE,
                "",
                "body",
                "",
                SECTION_RULE,
                "",
                "at /lab",
                SECTION_RULE,
                "",
                "keys",
            ),
        )

    def test_the_footer_block_starts_at_the_context_line_so_padding_lands_above_it(self) -> None:
        lines = screen_frame(("title",), ("body",), context=("at /lab",), footer=("keys",))

        self.assertEqual(lines[footer_start(lines) :], ("at /lab", SECTION_RULE, "", "keys"))

        placed = anchor(lines, height=len(lines) + 3)

        self.assertEqual(placed[-4:], ("at /lab", SECTION_RULE, "", "keys"))
        self.assertEqual(placed[len(lines) - 4 : len(lines) - 1], ("", "", ""))

    def test_a_frame_given_no_context_is_composed_exactly_as_before(self) -> None:
        self.assertEqual(
            screen_frame(("title",), ("body",), context=(), footer=("keys",)),
            screen_frame(("title",), ("body",), footer=("keys",)),
        )

    def test_a_context_line_of_nothing_but_blanks_draws_no_rule_of_its_own(self) -> None:
        lines = screen_frame(("title",), context=("", "  "), footer=("keys",))

        self.assertEqual(lines, ("title", "", SECTION_RULE, "", "keys"))

    def test_a_screen_with_nothing_but_context_still_shows_it_above_the_keys(self) -> None:
        lines = screen_frame((), context=("at /lab",), footer=("keys",))

        self.assertEqual(lines, ("at /lab", SECTION_RULE, "", "keys"))

    def test_a_short_frame_is_padded_so_the_footer_sits_on_the_bottom_row(self) -> None:
        """`QA-068`: the legend floated under the body with the terminal blank beneath it."""

        lines = screen_frame(("title",), ("body",), footer=("local", "global"))

        placed = anchor(lines, height=12)

        self.assertEqual(len(placed), 12)
        self.assertEqual(placed[-4:], (SECTION_RULE, "", "local", "global"))
        self.assertEqual(placed[: footer_start(lines)], lines[: footer_start(lines)])

    def test_a_frame_taller_than_the_terminal_is_left_alone_for_the_terminal_to_clip(self) -> None:
        lines = screen_frame(("title",), tuple(f"row {n}" for n in range(40)), footer=("keys",))

        self.assertEqual(anchor(lines, height=10), tuple(lines))

    def test_padding_goes_above_the_footer_rather_than_below_it(self) -> None:
        lines = screen_frame(("title",), footer=("keys",))

        placed = anchor(lines, height=8)

        self.assertEqual(placed[-1], "keys")
        self.assertEqual(placed[0], "title")


class ScreenSkeletonEdgeTest(TestCase):
    """The claims `make mutants` found nothing was holding."""

    def test_a_region_that_is_not_lines_of_text_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            screen_frame(("title",), (1, 2), footer=("keys",))  # type: ignore[arg-type]

    def test_a_height_that_is_not_a_count_of_rows_is_refused(self) -> None:
        lines = screen_frame(("title",), footer=("keys",))

        for height in (-1, True, "12", 1.5):
            with self.subTest(height=height), self.assertRaises(ValueError):
                anchor(lines, height=height)  # type: ignore[arg-type]

    def test_a_frame_that_exactly_fills_the_terminal_is_padded_by_nothing(self) -> None:
        """The boundary between padding and leaving alone is the exact fit, not one either side."""

        lines = screen_frame(("title",), ("body",), footer=("keys",))

        self.assertEqual(anchor(lines, height=len(lines)), lines)
        self.assertEqual(len(anchor(lines, height=len(lines) + 1)), len(lines) + 1)

    def test_what_is_inserted_above_the_footer_is_blank_rows(self) -> None:
        lines = screen_frame(("title",), footer=("keys",))

        placed = anchor(lines, height=9)

        inserted = placed[footer_start(lines) : footer_start(placed)]

        self.assertEqual(len(inserted), 9 - len(lines))
        self.assertEqual(set(inserted), {""})

    def test_a_terminal_with_no_rows_to_give_pads_nothing(self) -> None:
        lines = screen_frame(("title",), footer=("keys",))

        self.assertEqual(anchor(lines, height=0), lines)

    def test_the_last_rule_wins_even_when_it_is_the_very_last_line(self) -> None:
        frame_lines = ("title", "", SECTION_RULE, "", "body", "", SECTION_RULE)

        self.assertEqual(footer_start(frame_lines), 6)

    def test_a_rule_at_the_top_of_a_frame_is_still_found(self) -> None:
        self.assertEqual(footer_start((SECTION_RULE, "keys")), 0)

    def test_a_frame_with_no_rule_at_all_keeps_its_last_line_as_the_footer(self) -> None:
        """`B-077`: answering "no footer" would let a long body clip the only way out."""

        self.assertEqual(footer_start(("only", "two")), 1)
        self.assertEqual(footer_start(()), 0)


class ScreenSkeletonFrameTest(TestCase):
    """The same rule, read off screens the operator actually walked."""

    def setUp(self) -> None:
        self.source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=2),
                registries=(_registry("company"), _registry("team")),
            )
        )

    def _state(self, screen: ConsumerScreen, **kwargs: object) -> ConsumerUiState:
        return ConsumerUiState(ConsumerSession(screen), **kwargs)  # type: ignore[arg-type]

    def test_no_screen_ever_draws_two_rules_with_nothing_between_them(self) -> None:
        for screen in (
            ConsumerScreen.DASHBOARD,
            ConsumerScreen.REGISTRIES,
            ConsumerScreen.MARKETPLACE,
            ConsumerScreen.INSTALLED,
            ConsumerScreen.ACTIVITY,
            ConsumerScreen.SETTINGS,
        ):
            with self.subTest(screen=screen):
                lines = frame(self.source, self._state(screen))
                for above, below in zip(lines, lines[1:], strict=False):
                    self.assertFalse(
                        above == SECTION_RULE and below == SECTION_RULE,
                        f"{screen.value} drew an empty section",
                    )

    def test_every_rule_has_one_blank_line_above_and_below_it(self) -> None:
        """`QA-067`: text touching its rule is what left the screen with no breathing room."""

        for screen in (
            ConsumerScreen.DASHBOARD,
            ConsumerScreen.REGISTRIES,
            ConsumerScreen.ACTIVITY,
        ):
            with self.subTest(screen=screen):
                lines = frame(self.source, self._state(screen))
                for index, line in enumerate(lines):
                    if line != SECTION_RULE:
                        continue
                    self.assertEqual(lines[index - 1], "", f"{screen.value}: text above a rule")
                    if index + 1 < len(lines):
                        self.assertNotEqual(lines[index + 1], SECTION_RULE)

    def test_the_key_legend_is_the_last_thing_on_every_screen(self) -> None:
        for screen in (ConsumerScreen.DASHBOARD, ConsumerScreen.REGISTRIES):
            with self.subTest(screen=screen):
                state = self._state(screen)
                lines = frame(self.source, state)
                last = key_bindings(state, detail=self.source.detail(state))[-1]
                self.assertIn(f"[{last.key}] {last.label}", lines[-1])

    def test_screen_keys_sit_on_a_line_above_the_universal_ones(self) -> None:
        """`QA-068`: one line mixed the keys this screen offers with the ways out of it."""

        state = self._state(ConsumerScreen.REGISTRIES)
        lines = frame(self.source, state)

        self.assertEqual(lines[-1], "[↑/↓] Move   [Esc] Back   [?] Help   [q] Quit")
        self.assertNotIn("[Esc] Back", lines[-2])
        self.assertIn("[a] Add", lines[-2])

    def test_the_help_block_appears_only_once_help_is_asked_for(self) -> None:
        """`QA-065`: help was already on screen, so `?` looked like it did nothing."""

        state = self._state(ConsumerScreen.DASHBOARD)

        self.assertNotIn("Keyboard help", frame(self.source, state))
        self.assertIn("Keyboard help", frame(self.source, replace(state, help_visible=True)))

    def test_the_cursor_description_is_a_mode_the_v_key_turns_on(self) -> None:
        """`QA-070`: the per-row explanations are switchable rather than always present."""

        fast = ConsumerUiState(
            ConsumerSession(ConsumerScreen.DASHBOARD, profile=PresentationProfile.FAST),
            rows=(ConsumerScreen.MARKETPLACE.value,),
            settings=ConsumerSettings(profile=PresentationProfile.FAST),
        )
        verbose = ConsumerUiState(
            ConsumerSession(ConsumerScreen.DASHBOARD, profile=PresentationProfile.VERBOSE),
            rows=(ConsumerScreen.MARKETPLACE.value,),
            settings=ConsumerSettings(profile=PresentationProfile.VERBOSE),
        )
        described = "Browse and install approved tools from configured registries."

        self.assertNotIn(described, frame(self.source, fast))
        self.assertIn(described, frame(self.source, verbose))


class _Screen:
    """The smallest terminal that can say where something was painted."""

    def __init__(self, height: int, width: int = 80) -> None:
        self.written: list[tuple[int, int, str]] = []
        self._size = (height, width)

    def clear(self) -> None:
        self.written.clear()

    def getmaxyx(self) -> tuple[int, int]:
        return self._size

    def addstr(self, row: int, column: int, value: str) -> None:
        self.written.append((row, column, value))

    def refresh(self) -> None:
        pass


class AnchoredFooterTest(TestCase):
    """`QA-068`: the legend is placed, not merely drawn after the body."""

    def test_a_short_screen_puts_the_whole_legend_on_the_bottom_rows(self) -> None:
        screen = _Screen(height=24)
        lines = screen_frame(("heading",), ("one", "two"), footer=("[a] Add", "[q] Quit"))

        tui._CursesTerminal(screen).draw(lines)

        self.assertEqual([row for row, _, _ in screen.written[-4:]], [19, 20, 21, 22])
        self.assertEqual(screen.written[-1][2], "[q] Quit")
        self.assertEqual(screen.written[-2][2], "[a] Add")
        self.assertEqual(screen.written[-4][2], SECTION_RULE)

    def test_a_body_taller_than_the_terminal_is_clipped_and_the_legend_survives_whole(self) -> None:
        screen = _Screen(height=8)
        lines = screen_frame(
            ("heading",), tuple(f"row {n}" for n in range(40)), footer=("[a] Add", "[q] Quit")
        )

        tui._CursesTerminal(screen).draw(lines)

        painted = [value for _, _, value in screen.written]
        self.assertEqual(painted[-2:], ["[a] Add", "[q] Quit"])
        self.assertIn(SECTION_RULE, painted)
        self.assertEqual(len(painted), 7)
