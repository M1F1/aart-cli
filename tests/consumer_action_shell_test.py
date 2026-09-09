"""CP-13 action commands cross the persistent shell through one injected handler."""

from __future__ import annotations

import unittest
from dataclasses import replace

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
)
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    ConsumerActionUpdate,
    run_consumer_shell,
)
from tests.consumer_install_flow_shell_test import plan_view
from tests.consumer_install_flow_shell_test import screens as flow_screens
from tests.consumer_marketplace_shell_test import screens as marketplace_screens
from tests.consumer_shell_test import ENTER, SPACE, FakeTerminal

PLAN = plan_view()
SEMANTIC = PLAN.semantic_identity
SELECTION = PLAN.selection.semantic_identity
REVIEW = PLAN.review_digest
RECORDED_AT = "2026-08-31T16:04:00+00:00"


def _prepared_source() -> CanonicalScreenSource:
    return CanonicalScreenSource(replace(marketplace_screens(), plan=plan_view()))


class FakeActionHandler:
    def __init__(self) -> None:
        self.commands: list[ConsumerUiCommand] = []

    def handle(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        self.commands.append(command)
        if command.kind is ConsumerUiCommandKind.PREPARE_ACTION:
            return ConsumerActionUpdate(
                _prepared_source(),
                ConsumerUiEvent(
                    ConsumerUiEventKind.ACTION_PREPARED,
                    action=command.action,
                    semantic_identity=SEMANTIC,
                    selection_identity=SELECTION,
                    review_digest=REVIEW,
                ),
            )
        return ConsumerActionUpdate(
            CanonicalScreenSource(
                replace(
                    marketplace_screens(),
                    plan=plan_view(),
                    outcome=flow_screens().outcome,
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=command.action,
                text=RECORDED_AT,
            ),
        )


class WrongActionHandler:
    def handle(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        return ConsumerActionUpdate(
            _prepared_source(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=ConsumerActionKind.UNINSTALL,
                text=RECORDED_AT,
            ),
        )


class ConsumerActionShellTest(unittest.TestCase):
    def test_preparation_replaces_the_source_before_review_is_drawn(self) -> None:
        source = CanonicalScreenSource(marketplace_screens())
        handler = FakeActionHandler()
        terminal = FakeTerminal(SPACE, ord("i"), ord("q"), ord("y"))
        state = ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE))

        finished = run_consumer_shell(source, terminal, state=state, action_handler=handler)

        self.assertTrue(finished.exited)
        self.assertEqual(handler.commands[0].kind, ConsumerUiCommandKind.PREPARE_ACTION)
        self.assertTrue(terminal.screen_containing("unique artifact(s) will be installed"))
        self.assertTrue(terminal.screen_containing(f"Review identity: {REVIEW}"))

    def test_execution_draws_progress_then_refreshes_the_source_and_opens_the_result(self) -> None:
        handler = FakeActionHandler()
        terminal = FakeTerminal(ENTER)
        state = ConsumerUiState(
            ConsumerSession(
                ConsumerScreen.READY,
                semantic_identity=SEMANTIC,
                selection_identity=SELECTION,
                review_digest=REVIEW,
            ),
            selection=("public/mcp/github@1.6.0",),
            action=ConsumerActionKind.INSTALL,
        )

        finished = run_consumer_shell(
            _prepared_source(), terminal, state=state, action_handler=handler
        )

        self.assertEqual(handler.commands[0].kind, ConsumerUiCommandKind.EXECUTE_ACTION)
        self.assertEqual(handler.commands[0].review_digest, REVIEW)
        self.assertTrue(terminal.screen_containing("AART / Installing"))
        self.assertTrue(terminal.screen_containing("AART / Success"))
        self.assertEqual(finished.session.screen, ConsumerScreen.SUCCESS)
        self.assertEqual(finished.focus, RECORDED_AT)
        self.assertEqual(finished.selection, ())

    def test_an_action_without_an_injected_handler_fails_closed(self) -> None:
        source = CanonicalScreenSource(marketplace_screens())
        terminal = FakeTerminal(SPACE, ord("i"))
        state = ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE))

        with self.assertRaisesRegex(ValueError, "action handler"):
            run_consumer_shell(source, terminal, state=state)

    def test_a_handler_cannot_return_another_actions_result(self) -> None:
        source = CanonicalScreenSource(marketplace_screens())
        terminal = FakeTerminal(SPACE, ord("i"))
        state = ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE))

        with self.assertRaisesRegex(ValueError, "wrong action update"):
            run_consumer_shell(
                source,
                terminal,
                state=state,
                action_handler=WrongActionHandler(),
            )


if __name__ == "__main__":
    unittest.main()
