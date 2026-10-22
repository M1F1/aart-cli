"""INV-285: Installed names its columns, ruled off from the rows, like Marketplace.

The owner opened Installed and saw `ready  configured` with nothing saying which column was which.
Installed now draws a heading line over the same grid as its rows, and a rule under each heading.
"""

from __future__ import annotations

import dataclasses
import re
import unittest

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.tui_consumer import CanonicalScreenSource, _reload, frame
from tests.consumer_shell_test import screens

_HEADINGS = ("Artifact", "Health", "Scope", "Project", "Configuration")


def _drawn() -> list[str]:
    source = CanonicalScreenSource(screens())
    state = _reload(
        source, ConsumerUiState(ConsumerSession(ConsumerScreen.INSTALLED)), entering=True
    )
    return frame(source, dataclasses.replace(state, viewport_columns=120, viewport_rows=30))


class InstalledColumnHeadingsTest(unittest.TestCase):
    def test_the_headings_sit_over_their_cells_with_a_rule_between(self) -> None:
        lines = _drawn()
        at = next(index for index, line in enumerate(lines) if line.lstrip().startswith("Artifact"))
        heading, rule, first = lines[at], lines[at + 1], lines[at + 2]

        self.assertEqual(heading.split(), list(_HEADINGS))
        self.assertTrue(first.startswith("> [ ] public/mcp/github@1.6.0"), lines)
        self.assertEqual(
            [match.start() for match in re.finditer(r"─+", rule)],
            [heading.index(name) for name in _HEADINGS],
        )
        self.assertEqual(first[heading.index("Health") :].split()[0], "ready")
        self.assertEqual(first[heading.index("Configuration") :].strip(), "configured")


if __name__ == "__main__":
    unittest.main()
