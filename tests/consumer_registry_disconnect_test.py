"""A Registry connection has one reviewed TUI disconnect path (QA-050)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.consumer_actions import RegistryConnectionSnapshot


class RegistryDisconnectInteractionTest(unittest.TestCase):
    def test_d_disconnects_only_the_visible_registry_row(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REGISTRIES),
            rows=("add-registry", "company"),
            cursor=1,
            focus=ConsumerScreen.REGISTRIES.value,
        )

        event = key_event("d", state)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.REQUEST_ACTION)
        self.assertIs(event.action, ConsumerActionKind.REGISTRY_REMOVE)

        reviewed, commands = reduce_consumer_ui(state, event)
        self.assertIs(reviewed.session.screen, ConsumerScreen.REGISTRY_REMOVE)
        self.assertEqual(commands[0].focus, "company")

    def test_disconnect_is_not_enabled_on_add_registry(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REGISTRIES),
            rows=("add-registry", "company"),
        )
        self.assertIsNone(key_event("d", state))

    def test_review_returns_to_registries_after_completion(self) -> None:
        from agent_artifacts.application.consumer_ui import _ACTION_RESULT
        from agent_artifacts.application.consumer_views import navigation_targets

        self.assertIn(
            ConsumerScreen.REGISTRY_REMOVE,
            navigation_targets(ConsumerScreen.REGISTRIES),
        )
        self.assertIs(
            _ACTION_RESULT[(ConsumerActionKind.REGISTRY_REMOVE, ConsumerScreen.REGISTRY_REMOVE)],
            ConsumerScreen.REGISTRIES,
        )


class RegistryDisconnectActionTest(unittest.TestCase):
    def _actions(self):
        from agent_artifacts import tui
        from tests.configured_install_command_e2e_test import _environment

        environment = _environment()
        env = environment.__enter__()
        self.addCleanup(environment.__exit__, None, None, None)
        patcher = mock.patch.dict(os.environ, env.xdg, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        composed = tui._canonical_consumer_actions(
            project=str(env.project), user_home=str(env.home), today=tui.date.today()
        )
        self.assertIsInstance(composed, Ok, composed)
        return composed.value

    def test_review_states_every_effect_and_execution_refreshes_context(self) -> None:
        actions = self._actions()
        registry = actions._context.effective.configuration.sources[0]
        calls = []

        def remove(source):
            calls.append(source)
            return Ok(
                RegistryConnectionSnapshot(
                    actions._context.effective,
                    actions._context.offers,
                    actions._context.maintainer,
                )
            )

        actions._registry_removal = remove
        prepared = actions.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.REGISTRY_REMOVE,
                focus=registry.alias.value,
            )
        )
        review = "\n".join(prepared.source.screens.notice)
        self.assertIn("Disconnect Registry", review)
        self.assertIn("managed snapshot", review)
        self.assertIn("installed artifacts", review)
        self.assertIn("receipts", review)

        completed = actions.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.EXECUTE_ACTION,
                action=ConsumerActionKind.REGISTRY_REMOVE,
                review_digest=prepared.event.review_digest,
            )
        )

        self.assertEqual(calls, [registry])
        self.assertTrue(completed.event.text)

    def test_composition_uses_the_canonical_removal_transaction(self) -> None:
        actions = self._actions()
        registry = actions._context.effective.configuration.sources[0]
        remover = actions._registry_removal
        self.assertIsNotNone(remover)

        with mock.patch(
            "agent_artifacts.commands.source.remove_configured_source", return_value=Ok(object())
        ) as remove:
            result = remover(registry)  # type: ignore[misc]

        self.assertIsInstance(result, Ok, result)
        request = remove.call_args.args[0]
        self.assertEqual(request.source_alias, registry.alias.value)
        self.assertEqual(request.source_action, "remove")
        self.assertIs(remove.call_args.kwargs["expected_source"], registry)


if __name__ == "__main__":
    unittest.main()
