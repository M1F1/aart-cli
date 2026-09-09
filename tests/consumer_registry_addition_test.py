"""The persistent consumer shell can subscribe to its first approved registry."""

from __future__ import annotations

import unittest
from unittest import mock

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
    ConsumerUiState,
    RegistryDraft,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.consumer_actions import RegistryConnectionSnapshot
from agent_artifacts.tui import _TextTerminal
from agent_artifacts.tui_consumer import CanonicalScreenSource, frame
from tests.consumer_shell_test import screens


def _state(screen: ConsumerScreen, **changes) -> ConsumerUiState:
    return ConsumerUiState(ConsumerSession(screen), **changes)


class RegistryAdditionInteractionTest(unittest.TestCase):
    def test_registries_offers_a_real_add_route(self) -> None:
        state = _state(ConsumerScreen.REGISTRIES)

        event = key_event("a", state)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, ConsumerScreen.REGISTRY_ADD)

        editing, commands = reduce_consumer_ui(state, event)
        self.assertIs(editing.session.screen, ConsumerScreen.REGISTRY_ADD)
        self.assertEqual(commands[0].screen, ConsumerScreen.REGISTRY_ADD)

        source = CanonicalScreenSource(screens())
        editing, _ = reduce_consumer_ui(
            editing,
            type(event)(ConsumerUiEventKind.SET_ROWS, rows=source.rows(editing)),
        )
        drawn = "\n".join(frame(source, editing))
        self.assertIn("Alias", drawn)
        self.assertIn("Registry URL", drawn)
        self.assertIn("Branch or tag", drawn)
        self.assertIn("default registry", drawn)

    def test_entering_the_form_binds_exact_values_to_the_review_command(self) -> None:
        state = _state(
            ConsumerScreen.REGISTRY_ADD,
            rows=("alias", "url", "ref", "default", "connect"),
            registry_draft=RegistryDraft(
                "company",
                "https://git.example.test/company/registry.git",
                "stable",
                True,
            ),
            cursor=4,
        )

        event = key_event("enter", state)
        self.assertEqual(event.kind, ConsumerUiEventKind.REQUEST_ACTION)  # type: ignore[union-attr]
        reviewed, commands = reduce_consumer_ui(state, event)  # type: ignore[arg-type]

        self.assertIs(reviewed.session.screen, ConsumerScreen.REGISTRY_REVIEW)
        self.assertIs(reviewed.action, ConsumerActionKind.REGISTRY_ADD)
        self.assertEqual(commands[0].registry_draft, state.registry_draft)
        self.assertIs(commands[0].action, ConsumerActionKind.REGISTRY_ADD)

    def test_text_fallback_carries_a_whole_url_without_treating_it_as_a_hotkey(self) -> None:
        values = iter(["https://git.example.test/company/registry.git"])
        terminal = _TextTerminal(lambda _prompt: next(values), lambda _line: None)

        self.assertEqual(
            terminal.key(),
            "https://git.example.test/company/registry.git",
        )

    def test_printable_navigation_hotkeys_remain_text_inside_the_form(self) -> None:
        state = _state(
            ConsumerScreen.REGISTRY_ADD,
            rows=("alias", "url", "ref", "default", "connect"),
        )

        for character in "project-kit":
            event = key_event(character, state)
            self.assertIsNotNone(event)
            state, _ = reduce_consumer_ui(state, event)  # type: ignore[arg-type]

        self.assertEqual(state.registry_draft.alias, "project-kit")
        self.assertEqual(state.cursor, 0)

    def test_composed_action_uses_the_canonical_source_add_transaction(self) -> None:
        from agent_artifacts import tui
        from tests.configured_install_command_e2e_test import _environment

        draft = RegistryDraft(
            "team",
            "https://git.example.test/team/registry.git",
            "stable",
            False,
        )
        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            composed = tui._canonical_consumer_actions(
                project=str(env.project), user_home=str(env.home), today=tui.date.today()
            )
            self.assertIsInstance(composed, Ok, composed)
            connector = composed.value._registry_connection
            self.assertIsNotNone(connector)
            with mock.patch(
                "agent_artifacts.commands.source.add_configured_source",
                return_value=Ok(object()),
            ) as add:
                refreshed = connector(draft)  # type: ignore[misc]

        self.assertIsInstance(refreshed, Ok, refreshed)
        request = add.call_args.args[0]
        self.assertEqual(request.source_alias, "team")
        self.assertEqual(request.source_kind, "registry-git")
        self.assertEqual(request.source_location, draft.location)
        self.assertEqual(request.ref, "stable")
        self.assertFalse(request.source_make_default)

    def test_invalid_local_registry_is_refused_before_the_connection_port(self) -> None:
        from agent_artifacts import tui
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            composed = tui._canonical_consumer_actions(
                project=str(env.project), user_home=str(env.home), today=tui.date.today()
            )
        self.assertIsInstance(composed, Ok, composed)
        called: list[RegistryDraft] = []
        composed.value._registry_connection = lambda draft: called.append(draft)  # type: ignore[assignment,func-returns-value]
        command = ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION,
            action=ConsumerActionKind.REGISTRY_ADD,
            registry_draft=RegistryDraft("local", "/tmp/registry", "main", True),
        )

        update = composed.value.handle(command)

        self.assertEqual(called, [])
        self.assertIn("credential-free Git location", "\n".join(update.source.screens.notice))
        self.assertIsInstance(update.event.review_digest, str)
        self.assertEqual(update.event.review_digest, "")

    def test_reviewed_connection_refreshes_the_running_action_context(self) -> None:
        from agent_artifacts import tui
        from tests.configured_install_command_e2e_test import _environment

        draft = RegistryDraft("team", "https://git.example.test/team/registry.git", "main", False)
        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            composed = tui._canonical_consumer_actions(
                project=str(env.project), user_home=str(env.home), today=tui.date.today()
            )
        self.assertIsInstance(composed, Ok, composed)
        actions = composed.value
        calls: list[RegistryDraft] = []

        def connect(value: RegistryDraft):
            calls.append(value)
            return Ok(
                RegistryConnectionSnapshot(
                    actions._context.effective,
                    actions._context.offers,
                    actions._context.maintainer,
                )
            )

        actions._registry_connection = connect
        prepared = actions.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.REGISTRY_ADD,
                registry_draft=draft,
            )
        )
        self.assertTrue(prepared.event.review_digest)
        self.assertIn("Registry connection review", "\n".join(prepared.source.screens.notice))

        completed = actions.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.EXECUTE_ACTION,
                action=ConsumerActionKind.REGISTRY_ADD,
                review_digest=prepared.event.review_digest,
            )
        )

        self.assertEqual(calls, [draft])
        self.assertTrue(completed.event.text)
        self.assertEqual(completed.source.screens.registries, actions._context.offers.registries)


if __name__ == "__main__":
    unittest.main()
