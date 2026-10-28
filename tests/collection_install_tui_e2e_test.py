"""§173.5: the TUI installs a Collection as one artifact, through the real composed shell.

The Registry here approved two artifacts and a Collection naming both. Screen 05 offers the
Collection as one row, a harness only when it hosts every member, and says why the others are not
offered; one tick per harness installs every member there. 07a puts a Collection and harness on one
scope, and every member there goes to it (D-422).
"""

from __future__ import annotations

import unittest
from unittest import mock

from aart_cli.application.consumer_views import ConsumerScreen
from aart_cli.domain.result import Ok
from aart_cli.io.receipt_store import LocalReceiptStore
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import RegistryCollection, _published_registries
from tests.consumer_application_e2e_test import _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, INSTALL_CUSTOM, RIGHT, SPACE
from tests.installation_harness_choice_test import _AUTHORED_MCP, _AUTHORED_SKILL

STARTER = "company/collection/starter@1.0.0"
_AUTHORED_STARTER = RegistryCollection(
    "starter", "The dummy server and code review.", ("mcp/dummy", "skill/code-review")
)
#: Marketplace rows are the two artifacts, then the Collection; Enter opens its preview.
_TO_PREVIEW = (DOWN, DOWN, ENTER)


def _with_starter(_authored, **keywords):
    return _published_registries(_AUTHORED_SKILL, _AUTHORED_MCP, _AUTHORED_STARTER, **keywords)


class CollectionInstallShellTest(unittest.TestCase):
    def _drive(self, *keys: int):
        with (
            mock.patch(
                "tests.configured_install_command_e2e_test._published_registry", _with_starter
            ),
            _environment() as env,
        ):
            finished, terminal, _ = _drive(
                env, _at(ConsumerScreen.MARKETPLACE), *_TO_PREVIEW, *INSTALL_CUSTOM, *keys
            )
            stored = LocalReceiptStore(str(env.paths.data_root) + "/state").installations()
            assert isinstance(stored, Ok), getattr(stored, "diagnostics", ())
            installed = sorted(
                (
                    item.receipt.owner.artifact.name,
                    item.receipt.owner.harness,
                    item.receipt.owner.scope.value,
                )
                for item in stored.value
            )
            return finished, terminal, installed

    def test_05_offers_the_collection_as_one_row_and_names_what_a_harness_cannot_host(self):
        finished, terminal, installed = self._drive()

        self.assertIs(finished.session.screen, ConsumerScreen.REVIEW_SELECTION)
        self.assertEqual(
            finished.rows, (f"pairs:{STARTER}\tclaude,opencode,tabnine",), terminal.last
        )
        self.assertIn(
            f"codex is not offered for {STARTER}: it cannot host company/mcp/dummy@1.0.0.",
            terminal.last,
        )
        self.assertEqual(installed, [])

    def test_one_tick_per_harness_installs_every_member_there(self):
        finished, terminal, installed = self._drive(SPACE, RIGHT, SPACE, ENTER, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(
            installed,
            [
                ("code-review", "claude", "project"),
                ("code-review", "opencode", "project"),
                ("dummy", "claude", "project"),
                ("dummy", "opencode", "project"),
            ],
        )

    def test_07a_puts_the_collection_and_harness_on_one_scope_for_every_member(self):
        finished, terminal, installed = self._drive(
            # 05: claude and opencode, then on to 07a.
            SPACE,
            RIGHT,
            SPACE,
            ENTER,
            # 07a: past "All installations" to the Collection on claude, then to User: 07a opens
            # on its first column (§209, B-195).
            DOWN,
            RIGHT,
            SPACE,
            ENTER,
            ENTER,
        )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertTrue(terminal.screen_containing("All installations"), "07a was never drawn")
        self.assertEqual(
            installed,
            [
                ("code-review", "claude", "user"),
                ("code-review", "opencode", "project"),
                ("dummy", "claude", "user"),
                ("dummy", "opencode", "project"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
