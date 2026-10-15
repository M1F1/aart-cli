"""D-394: what a Marketplace row's installed note says, read off the installations directly.

Kept out of the acceptance test beside it, which drives the public shell only (INV-114).
"""

from __future__ import annotations

import unittest

from aart_cli.application.consumer_views import InstalledArtifactView
from aart_cli.tui_consumer import _installed_note


class InstalledNoteTest(unittest.TestCase):
    def _view(self, coordinate: str, harness: str, health: str) -> InstalledArtifactView:
        return InstalledArtifactView(coordinate, health, (), (), (), harness=harness)

    def test_any_installed_version_counts_and_a_health_other_than_ready_is_named(self) -> None:
        installed = (
            self._view("company/skill/review@1.0.0", "codex", "update"),
            self._view("company/skill/review@1.2.0", "claude", "ready"),
            self._view("company/skill/review-extra@1.2.0", "opencode", "ready"),
        )

        self.assertEqual(
            _installed_note("company/skill/review@1.2.0", installed),
            "  installed: claude, codex (update)",
        )
        self.assertEqual(_installed_note("company/skill/lint@1.0.0", installed), "")


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
