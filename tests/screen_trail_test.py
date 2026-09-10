"""CP-21 step 5: where the launch directory lives, and what a nested title says.

`QA-066`/`QA-069` and `QA-071`/`QA-083` are two pairs that pull against each other, so each pair is
settled once here rather than one finding at a time. The operator revised themselves mid-run on the
first pair -- separate the directory from the title, then move it out of the header entirely -- and
the second pair asks to add a parent to a title while removing a repeated word from it.
"""

from __future__ import annotations

from unittest import TestCase

from agent_artifacts.application.consumer_ui import ConsumerActionKind, ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    RegistryView,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, frame
from agent_artifacts.tui_layout import SECTION_RULE, footer_start


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


class LaunchDirectoryPlacementTest(TestCase):
    """`QA-066`/`QA-069`, settled together: the directory leaves the header for the footer."""

    def setUp(self) -> None:
        self.source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=2),
                registries=(_registry("company"),),
            )
        )

    def _frame(self, workspace: str = "/work/project") -> tuple[str, ...]:
        return frame(
            self.source,
            ConsumerUiState(ConsumerSession(ConsumerScreen.DASHBOARD), workspace=workspace),
        )

    def test_the_heading_carries_the_trail_and_nothing_else(self) -> None:
        lines = self._frame()

        self.assertEqual(lines[0], "AART / Dashboard")
        self.assertNotIn("/work/project", lines[0])
        self.assertEqual(lines[1], "")

    def test_the_directory_sits_in_the_footer_above_the_keys(self) -> None:
        lines = self._frame()

        directory = lines.index("working at /work/project")
        footer = footer_start(lines)

        self.assertLess(directory, footer)
        self.assertEqual(lines[directory + 1], "")
        self.assertEqual(lines[directory + 2], SECTION_RULE)
        self.assertTrue(lines[-1].startswith("["))

    def test_a_session_with_no_workspace_draws_no_directory_line_and_no_rule_for_it(self) -> None:
        lines = self._frame(workspace="")

        self.assertFalse([line for line in lines if line.startswith("working at")])
        self.assertEqual(lines.count(SECTION_RULE), self._frame().count(SECTION_RULE) - 1)


class NestedTitleTest(TestCase):
    """`QA-071`/`QA-083`, settled as one scheme: name the parent, say each word once."""

    def setUp(self) -> None:
        self.source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=2))
        )

    def _heading(self, screen, *history) -> str:
        state = ConsumerUiState(
            ConsumerSession(screen, history=tuple(history)),
            settings=ConsumerSettings(maintainer_mode=True),
        )
        return frame(self.source, state)[0]

    def test_a_nested_view_names_the_parent_it_was_reached_through(self) -> None:
        heading = self._heading(
            MaintainerScreen.SOURCES, ConsumerScreen.DASHBOARD, MaintainerScreen.DASHBOARD
        )

        self.assertEqual(heading, "AART / Maintainer / Sources")

    def test_the_word_maintainer_is_said_once_however_deep_the_view(self) -> None:
        heading = self._heading(
            MaintainerScreen.SOURCE_DETAILS,
            ConsumerScreen.DASHBOARD,
            MaintainerScreen.DASHBOARD,
            MaintainerScreen.SOURCES,
        )

        self.assertEqual(heading, "AART / Maintainer / Sources / Source Details")
        self.assertEqual(heading.count("Maintainer"), 1)

    def test_the_home_dashboard_is_aart_itself_rather_than_a_step_in_the_trail(self) -> None:
        self.assertEqual(self._heading(ConsumerScreen.DASHBOARD), "AART / Dashboard")
        self.assertEqual(
            self._heading(ConsumerScreen.MARKETPLACE, ConsumerScreen.DASHBOARD),
            "AART / Marketplace",
        )

    def test_a_maintainer_dashboard_reached_from_home_still_names_itself_whole(self) -> None:
        self.assertEqual(
            self._heading(MaintainerScreen.DASHBOARD, ConsumerScreen.DASHBOARD),
            "AART / Maintainer Dashboard",
        )

    def test_a_consumer_view_names_the_list_it_was_opened_from(self) -> None:
        self.assertEqual(
            self._heading(
                ConsumerScreen.ARTIFACT_DETAILS,
                ConsumerScreen.DASHBOARD,
                ConsumerScreen.MARKETPLACE,
            ),
            "AART / Marketplace / Artifact Details",
        )

    def test_a_screen_that_did_not_run_still_says_so_after_its_trail(self) -> None:
        """`QA-033`'s suffix survives the scheme: it qualifies the whole trail, so it goes last."""

        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.MARKETPLACE, history=(ConsumerScreen.DASHBOARD,)),
            failed_action=ConsumerActionKind.INSTALL,
        )

        self.assertEqual(frame(self.source, state)[0], "AART / Marketplace - did not run")
