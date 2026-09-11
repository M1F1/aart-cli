"""`QA-087`: every view fills the same blocks, and actions never share one with view status.

The operator's words are the specification: *"nigdy akcja i menu do wyboru nie powinno byc w jednym
bloku z statusem widoku"*, and *"kazdy widok powinien miec ta strukture … bo teraz co widok jest
inaczej mam wrazenie"*. A reader scanning for something to press should not have to read prose to
find it, and prose standing between two rows reads like a row.

`Frame` gives the blocks somewhere to be said (`D-243`). What is held here is the other half: that
each screen puts the right thing in each of them. `MIXED_SCREENS` is the shrinking list of screens
that still do not, so the exceptions are named in one place rather than discovered one manual run at
a time -- *"zeby nie bylo zbyt wielu wyjatkow od reguly"*.
"""

from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_candidates,
    project_maintainer_dashboard,
)
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, frame
from agent_artifacts.tui_layout import SECTION_RULE
from tests.consumer_shell_test import screens

#: Screens whose body still answers prose and rows together. Every entry is work, not a decision;
#: `CP-22` steps 5-7 empty this set. Nothing may be added to it.
MIXED_SCREENS = frozenset(
    {
        ConsumerScreen.REGISTRIES,
        ConsumerScreen.REGISTRY_ADD,
        ConsumerScreen.SETTINGS,
        ConsumerScreen.DOCTOR,
        MaintainerScreen.SOURCE_ADD,
        MaintainerScreen.REGISTRY,
        MaintainerScreen.REGISTRY_INIT,
        MaintainerScreen.REPOSITORY_SCAN,
        MaintainerScreen.REGISTRY_REBUILD,
    }
)


def _blocks(lines: tuple[str, ...]) -> list[tuple[str, ...]]:
    """The rendered frame back as the blocks it was composed from."""

    blocks: list[tuple[str, ...]] = []
    current: list[str] = []
    for line in lines:
        if line == SECTION_RULE:
            blocks.append(tuple(current))
            current = []
            continue
        current.append(line)
    blocks.append(tuple(current))
    return [tuple(block) for block in (tuple(b) for b in blocks)]


def _spoken(block: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(line for line in block if line.strip())


class DashboardBlockTest(TestCase):
    """The Dashboard the operator drew, read off the real composition."""

    def _frame(self, *, first_run: bool, verbose: bool = False) -> tuple[str, ...]:
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0)) if first_run else screens()
        )
        profile = PresentationProfile.VERBOSE if verbose else PresentationProfile.FAST
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.DASHBOARD, profile=profile),
            settings=ConsumerSettings(profile=profile),
            workspace="/lab/consumer-project",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_the_actions_block_holds_the_navigation_rows_and_nothing_else(self) -> None:
        blocks = _blocks(self._frame(first_run=True))

        self.assertEqual(
            _spoken(blocks[1]),
            (
                "> Marketplace",
                "  Installed",
                "  Updates",
                "  Registries",
                "  Credentials",
                "  Activity",
                "  Doctor",
                "  Settings",
            ),
        )

    def test_the_first_run_guidance_is_the_state_of_the_view_not_a_row(self) -> None:
        """It was drawn above the menu, inside the menu's own block."""

        blocks = _blocks(self._frame(first_run=True))
        guidance = next(
            block for block in blocks if any("Welcome to AART" in line for line in block)
        )

        self.assertNotIn(guidance, blocks[:2])
        self.assertIn("SETUP REQUIRED", guidance)
        self.assertNotIn("> Marketplace", guidance)

    def test_the_counts_are_the_state_of_the_view_on_a_machine_past_its_first_run(self) -> None:
        blocks = _blocks(self._frame(first_run=False))

        self.assertEqual(_spoken(blocks[1])[0], "> Marketplace")
        self.assertTrue(any("installed" in line for line in blocks[-3]))

    def test_the_block_order_is_rows_then_cursor_description_then_view_status(self) -> None:
        blocks = _blocks(self._frame(first_run=True, verbose=True))

        self.assertEqual(_spoken(blocks[1])[0], "> Marketplace")
        self.assertEqual(
            _spoken(blocks[2]),
            ("Browse and install approved tools from configured registries.",),
        )
        self.assertIn("Welcome to AART — this looks like your first run.", blocks[3])

    def test_no_block_announces_itself_now_that_it_holds_only_actions(self) -> None:
        """`Navigation:` labelled a block whose contents are the navigation."""

        self.assertNotIn("Navigation:", self._frame(first_run=True))


class MaintainerDashboardBlockTest(TestCase):
    def _frame(self) -> tuple[str, ...]:
        views = MaintainerViews(
            project_maintainer_dashboard(()), (), project_maintainer_candidates(()), ()
        )
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
        )
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.DASHBOARD),
            settings=ConsumerSettings().with_maintainer_mode(True),
            workspace="/lab/registry",
        )
        state = replace(state, rows=source.rows(state), cursor=0)
        return frame(source, state)

    def test_the_actions_block_holds_the_navigation_rows_and_nothing_else(self) -> None:
        blocks = _blocks(self._frame())

        self.assertTrue(_spoken(blocks[1]))
        for line in _spoken(blocks[1]):
            self.assertTrue(line.startswith(("> ", "  ")), line)

    def test_the_maintainer_overview_is_the_state_of_the_view(self) -> None:
        blocks = _blocks(self._frame())
        overview = _spoken(blocks[2])

        self.assertEqual(overview[0], "Maintainer overview")
        self.assertFalse([line for line in overview if line.startswith("> ")])

    def test_an_unavailable_composition_is_state_rather_than_something_to_put_a_cursor_on(
        self,
    ) -> None:
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.DASHBOARD),
            settings=ConsumerSettings().with_maintainer_mode(True),
        )

        self.assertEqual(source.actions(state), ())
        self.assertEqual(source.status(state), ("Maintainer state is not available yet.",))

    def test_no_block_announces_itself(self) -> None:
        self.assertNotIn("Maintainer navigation:", self._frame())


class EveryScreenBlockTest(TestCase):
    """The enforcement: a migrated screen's actions block holds only what the cursor acts on."""

    def setUp(self) -> None:
        self.source = CanonicalScreenSource(screens())

    def test_a_migrated_screen_puts_no_prose_where_the_cursor_rows_go(self) -> None:
        for screen in (*ConsumerScreen, *MaintainerScreen):
            if screen in MIXED_SCREENS:
                continue
            state = ConsumerUiState(
                ConsumerSession(screen),
                settings=ConsumerSettings().with_maintainer_mode(True),
            )
            state = replace(state, rows=self.source.rows(state), cursor=0)
            if not state.rows:
                continue
            with self.subTest(screen=screen):
                for line in _spoken(self.source.actions(state)):
                    self.assertFalse(
                        line.endswith(".") and not line.startswith(("> ", "  ")),
                        f"{screen.value}: prose in the actions block -- {line!r}",
                    )

    def test_the_list_of_screens_that_still_mix_only_ever_shrinks(self) -> None:
        """A reminder in the only place that would notice: nine left, and no route to add one."""

        self.assertEqual(len(MIXED_SCREENS), 9)
