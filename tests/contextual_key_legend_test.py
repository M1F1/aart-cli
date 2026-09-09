"""`QA-026`: the persistent footer names what the current screen can do.

The accepted catalog makes shortcuts contextual.  A fixed footer makes two opposite promises at
once: it hides Maintainer actions such as Registry rebuild, and advertises Space on screens where
nothing is selectable.  These tests render the real frame and walk one advertised key so the
legend cannot become a second, decorative keyboard map.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.tui_consumer import CanonicalScreenSource, frame, run_consumer_shell
from tests.consumer_shell_test import FakeTerminal, screens


def _state(screen, *, rows: tuple[str, ...] = ()) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        rows=rows,
    )


class ContextualKeyLegendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CanonicalScreenSource(screens())

    def _footer(self, state: ConsumerUiState) -> str:
        return "\n".join(line for line in frame(self.source, state) if line.startswith("Keys"))

    def test_registry_actions_are_in_the_footer_before_the_global_keys(self) -> None:
        drawn = frame(self.source, _state(MaintainerScreen.REGISTRY))
        footer = self._footer(_state(MaintainerScreen.REGISTRY))

        for shortcut, action in (
            ("n", "Initialize"),
            ("b", "Rebuild"),
            ("s", "Scan Repository"),
            ("u", "Check upstream"),
        ):
            self.assertIn(f"{shortcut} {action}", footer)
        self.assertLess(footer.index("n Initialize"), footer.index("↑/↓"))
        self.assertFalse(any(line.startswith("Actions:") for line in drawn), drawn)

    def test_an_advertised_registry_key_opens_the_screen_it_names(self) -> None:
        terminal = FakeTerminal(ord("b"))

        finished = run_consumer_shell(
            self.source,
            terminal,
            state=_state(MaintainerScreen.REGISTRY),
        )

        self.assertTrue(finished.exited)
        self.assertTrue(
            any(frame_lines[0] == "AART / Rebuild Registry" for frame_lines in terminal.frames)
        )

    def test_each_maintainer_screen_names_its_own_shortcuts(self) -> None:
        expected = {
            MaintainerScreen.SOURCES: ("a Add Source", "s Sync"),
            MaintainerScreen.CANDIDATES: ("f Filters", "c Collections"),
            MaintainerScreen.CANDIDATE_DIFF: ("f Files",),
            MaintainerScreen.SCAN_RESULT: ("a Adopt",),
            MaintainerScreen.ADOPTED_ARTIFACTS: ("Enter Check upstream",),
            MaintainerScreen.UPSTREAM_CHECK: ("a Review new version",),
            MaintainerScreen.PROMOTION_MODE: ("m Mode",),
            MaintainerScreen.VALIDATION: ("p Promote",),
        }

        for screen, labels in expected.items():
            with self.subTest(screen=screen):
                footer = self._footer(_state(screen))
                for label in labels:
                    self.assertIn(label, footer)

    def test_structural_keys_appear_only_where_the_screen_can_use_them(self) -> None:
        dashboard = self._footer(
            _state(ConsumerScreen.DASHBOARD, rows=(ConsumerScreen.MARKETPLACE.value,))
        )
        marketplace = self._footer(
            _state(ConsumerScreen.MARKETPLACE, rows=("public/mcp/github@1.6.0",))
        )

        self.assertIn("Enter Open", dashboard)
        self.assertNotIn("Space", dashboard)
        self.assertIn("Space Select", marketplace)
        self.assertIn("/ Search", marketplace)
        self.assertIn("i Install", marketplace)

    def test_global_exit_and_help_keys_remain_visible_on_every_screen(self) -> None:
        for screen in (ConsumerScreen.DASHBOARD, MaintainerScreen.REGISTRY):
            with self.subTest(screen=screen):
                footer = self._footer(_state(screen))
                self.assertIn("↑/↓ Move", footer)
                self.assertIn("Esc Back", footer)
                self.assertIn("? Help", footer)
                self.assertIn("q Quit", footer)


if __name__ == "__main__":
    unittest.main()
