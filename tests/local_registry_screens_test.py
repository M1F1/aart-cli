"""A local Registry (D-350) is a Registry on every screen, not only on the Maintainer one.

Screen 46 listed every configured Registry, `registry-local` included, while Registries listed only
`registry-git`, and the approved-state read accepted only `registry-git`. A local Registry
therefore showed on screen 46 as "no synchronized approved state yet", and Registries had no row to
sync or disconnect it from.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from aart_cli import tui
from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
)
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Ok
from aart_cli.io.maintainer_sync import read_approved_registry_state
from aart_cli.io.maintainer_views import read_maintainer_views
from aart_cli.tui import _canonical_consumer_configuration, _canonical_marketplace_target
from aart_cli.tui_consumer import read_consumer_offers
from tests.local_registry_checkout_e2e_test import ALIAS, _checkout


class LocalRegistryOnEveryScreenTest(unittest.TestCase):
    def _effective(self, env):
        loaded = _canonical_consumer_configuration(env.paths)
        self.assertIsInstance(loaded, Ok, loaded)
        return loaded.value

    def test_registries_lists_it(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)

            offers = read_consumer_offers(
                self._effective(env),
                data_root=env.paths.data_root,
                target=_canonical_marketplace_target(),
            )

            self.assertIsInstance(offers, Ok, offers)
            self.assertIn(ALIAS, [item.alias for item in offers.value.registries])

    def test_its_approved_state_reads(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)

            approved = read_approved_registry_state(
                self._effective(env), SourceAlias(ALIAS), data_root=env.paths.data_root
            )

            self.assertIsInstance(approved, Ok, approved)
            self.assertEqual(approved.value.revision, env.branch)

    def test_screen_46_does_not_call_it_unsynchronized(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)

            views = read_maintainer_views(
                self._effective(env), data_root=env.paths.data_root, registry_root=None
            )

            self.assertIsInstance(views, Ok, views)
            (registry,) = [item for item in views.value.registries if item.alias == ALIAS]
            self.assertEqual(registry.revision, env.branch)
            self.assertNotIn("no synchronized approved state", " ".join(registry.diagnostics))

    def test_registries_disconnects_it(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project), user_home=str(env.home), today=tui.date.today()
                )
                self.assertIsInstance(composed, Ok, composed)
                actions = composed.value
                prepared = actions.handle(
                    ConsumerUiCommand(
                        ConsumerUiCommandKind.PREPARE_ACTION,
                        action=ConsumerActionKind.REGISTRY_REMOVE,
                        focus=ALIAS,
                    )
                )
                self.assertIs(
                    prepared.event.kind, ConsumerUiEventKind.ACTION_PREPARED, prepared.event
                )
                actions.handle(
                    ConsumerUiCommand(
                        ConsumerUiCommandKind.EXECUTE_ACTION,
                        action=ConsumerActionKind.REGISTRY_REMOVE,
                        review_digest=prepared.event.review_digest,
                    )
                )

            aliases = [item.alias.value for item in self._effective(env).configuration.sources]
            self.assertNotIn(ALIAS, aliases)


if __name__ == "__main__":
    unittest.main()
