"""D-394: a Marketplace row says where that artifact is already installed.

The operator: *"w marketplace chce widziec czy dany artefakt mam juz zainstalowany czy nie"*. Only
Artifact Details said so; the row was the offer key alone (D-385).
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
)
from aart_cli.tui_consumer import frame
from tests.configured_install_command_e2e_test import COORDINATE
from tests.consumer_application_e2e_test import _actions
from tests.installed_multi_uninstall_e2e_test import SECOND, _two_skills


class MarketplaceInstalledNoteTest(unittest.TestCase):
    def test_an_installed_offer_names_its_harness_and_an_uninstalled_one_says_nothing(self) -> None:
        with _two_skills() as env:
            code, installed = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(code, 0, installed)
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                source = _actions(env).source()
                empty = ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE))
                state = ConsumerUiState(
                    ConsumerSession(ConsumerScreen.MARKETPLACE), rows=source.rows(empty)
                )
                rows = [line for line in frame(source, state) if "[ ]" in line]

            installed_row = next(line for line in rows if COORDINATE in line)
            other_row = next(line for line in rows if SECOND in line)
            self.assertTrue(installed_row.endswith("installed: claude"), installed_row)
            self.assertNotIn("installed", other_row)


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
