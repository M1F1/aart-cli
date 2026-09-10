"""CP-19 step 12: shared visual hierarchy for sections, rows, help, footer and focus."""

from __future__ import annotations

from unittest import TestCase

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    PresentationProfile,
    RegistryView,
    project_dashboard,
)
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, frame
from agent_artifacts.tui_layout import SECTION_RULE


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


class TuiVisualHierarchyTest(TestCase):
    def setUp(self) -> None:
        self.source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=2),
                registries=(_registry("company"), _registry("team")),
            )
        )

    def test_dashboard_bounds_the_focused_explanation_and_separates_activity(self) -> None:
        # `QA-070` made the explanation a mode: Verbose is the screen that has one to bound.
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.DASHBOARD, profile=PresentationProfile.VERBOSE),
            rows=(ConsumerScreen.MARKETPLACE.value,),
        )
        lines = frame(self.source, state)
        explanation = lines.index("Browse and install approved tools from configured registries.")

        self.assertEqual(lines[explanation - 2], SECTION_RULE)
        self.assertEqual(lines[explanation - 1], "")
        self.assertEqual(lines[explanation + 1], "")
        self.assertEqual(lines[explanation + 2], SECTION_RULE)
        self.assertNotIn("About Marketplace:", lines)
        recent = lines.index("Recent activity:")
        self.assertEqual(lines[recent - 1], "")

    def test_each_registry_is_a_separate_card_and_every_actionable_row_shows_focus(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REGISTRIES),
            rows=("add-registry", "company", "team"),
            cursor=2,
        )
        lines = frame(self.source, state)
        company = next(index for index, line in enumerate(lines) if "company — connected" in line)
        team = next(index for index, line in enumerate(lines) if "team — connected" in line)

        self.assertEqual(lines[company - 1], "")
        self.assertEqual(lines[team - 1], "")
        self.assertTrue(lines[team].startswith("> "))
        self.assertTrue(lines[company].startswith("  "))

    def test_help_has_one_key_or_related_pair_per_keycap_line(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.INSTALLED),
            help_visible=True,
        )
        lines = frame(self.source, state)
        # Help is a region of its own now, so it ends at the rule that follows it (`QA-067`).
        opened = lines.index("Keyboard help")
        help_lines = lines[opened + 1 : lines.index(SECTION_RULE, opened)]

        self.assertGreater(len(help_lines), 8)
        self.assertTrue(all(line.startswith("[") for line in help_lines if line))
        self.assertTrue(all(line.count("[") == 1 for line in help_lines if line))

    def test_footer_is_one_compact_keycap_block_below_a_separator(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.DASHBOARD),
            rows=(ConsumerScreen.MARKETPLACE.value,),
        )
        lines = frame(self.source, state)
        footer_rule = len(lines) - 1 - tuple(reversed(lines)).index(SECTION_RULE)
        footer = lines[footer_rule + 1 :]

        self.assertTrue(footer)
        # The skeleton puts one blank under every rule (`QA-067`), so the keycap block starts below
        # it; what the claim is about is that the block itself is nothing but keycap lines.
        self.assertEqual(footer[0], "")
        self.assertTrue(all(line.startswith("[") for line in footer[1:]))
        self.assertIn("[Enter] Open", "\n".join(footer))
        self.assertIn("[↑/↓] Move", "\n".join(footer))
        self.assertNotIn("Keys here", "\n".join(footer))
        self.assertNotIn("Keys always", "\n".join(footer))
        self.assertNotIn("\n\n", "\n".join(footer[1:]))


if __name__ == "__main__":
    import unittest

    unittest.main()
