"""`QA-053`: every frame says which directory this session is working in.

The operator reported that a screen never names the directory `aart` was launched from, so there is
no way to tell from the frame whether an install or a Registry edit is about to land in the lab
checkout or in the real project -- "chcialbym jeszcze widziec gdzies u dolu / albo u gory sciezke z
jakiej odpalilem aart zeby wiedziec w jakim konteksie jestem".

The path is context for everything a screen offers, so it is frame chrome rather than a line one
screen remembers to print. **Where** that chrome sits was revised by `QA-066`/`QA-069` (`D-235`):
the operator, having lived with the directory directly under the title, moved it into the footer
above the keys, so the top line carries only the trail. What these tests hold is unchanged -- every
screen names the directory, a session without one prints no line -- and only the place changed.

These tests render the real frame, and hold the abbreviation to a property: a shown path is
bounded, and it always keeps the segment that identifies it.
"""

from __future__ import annotations

import os
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.consumer_ui import ConsumerUiState, opening_state
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.tui import launch_workspace
from agent_artifacts.tui_consumer import CanonicalScreenSource, frame
from agent_artifacts.tui_layout import CONTENT_MEASURE, abbreviate_path, footer_start
from tests.consumer_shell_test import screens


def _state(screen, *, workspace: str) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        workspace=workspace,
    )


class WorkspaceContextLineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CanonicalScreenSource(screens())

    def test_the_directory_is_the_last_fact_before_the_keys(self) -> None:
        lines = frame(self.source, _state(ConsumerScreen.DASHBOARD, workspace="~/code/aart-cli"))

        self.assertTrue(lines[0].startswith("AART / "))
        self.assertNotIn("aart-cli", lines[0])
        self.assertEqual("working at ~/code/aart-cli", lines[footer_start(lines) - 2])

    def test_every_screen_carries_the_same_context(self) -> None:
        for screen in (
            ConsumerScreen.DASHBOARD,
            ConsumerScreen.REGISTRIES,
            ConsumerScreen.UPDATES,
            MaintainerScreen.REGISTRY,
        ):
            with self.subTest(screen=screen):
                lines = frame(self.source, _state(screen, workspace="~/lab/seven"))

                self.assertEqual("working at ~/lab/seven", lines[footer_start(lines) - 2])

    def test_a_session_without_a_directory_prints_no_context_line(self) -> None:
        lines = frame(self.source, _state(ConsumerScreen.DASHBOARD, workspace=""))

        self.assertTrue(lines[0].startswith("AART / "))
        self.assertNotIn("working at", "\n".join(lines))

    def test_opening_a_session_carries_the_directory_it_was_launched_from(self) -> None:
        state = opening_state(ConsumerSettings(), workspace="~/code/aart-cli")

        self.assertEqual("~/code/aart-cli", state.workspace)

    def test_a_home_path_is_shown_against_the_home_marker(self) -> None:
        self.assertEqual(
            "~/code/aart-cli", abbreviate_path("/Users/mifi/code/aart-cli", home="/Users/mifi")
        )

    def test_a_path_outside_home_keeps_its_root(self) -> None:
        self.assertEqual("/srv/aart", abbreviate_path("/srv/aart", home="/Users/mifi"))

    def test_a_long_path_drops_leading_segments_rather_than_the_name(self) -> None:
        shown = abbreviate_path("/" + "/".join(f"segment{index}" for index in range(40)), home="")

        self.assertTrue(shown.startswith("…/"))
        self.assertTrue(shown.endswith("segment39"))

    @given(
        st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=30
            ),
            min_size=1,
            max_size=25,
        )
    )
    def test_a_shown_path_is_bounded_and_keeps_its_final_segment(self, segments: list[str]) -> None:
        shown = abbreviate_path("/" + "/".join(segments), home="")

        self.assertLessEqual(len(shown), CONTENT_MEASURE)
        tail = segments[-1]
        self.assertTrue(shown.endswith(tail) or shown.endswith("…"))


class LaunchWorkspaceTest(unittest.TestCase):
    """The boundary resolves the same directory the actions work in, and writes it for a reader."""

    def test_an_explicit_project_under_home_is_shown_against_the_home_marker(self) -> None:
        self.assertEqual(
            "~/code/aart-cli",
            launch_workspace("/Users/mifi/code/aart-cli", "/Users/mifi"),
        )

    def test_a_relative_project_is_resolved_before_it_is_shown(self) -> None:
        shown = launch_workspace(".", "/nowhere-that-exists")

        self.assertEqual(os.path.abspath("."), shown)

    def test_no_project_names_the_directory_the_process_was_launched_in(self) -> None:
        self.assertEqual(
            launch_workspace(None, "/nowhere-that-exists"), os.path.abspath(os.getcwd())
        )


if __name__ == "__main__":
    unittest.main()
