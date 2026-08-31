"""CP-13 action intent: keys and controls become typed application requests, never effects."""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession

ARTIFACT = "public/mcp/github@1.6.0"
OTHER = "public/mcp/jira@2.2.0"
SEMANTIC = "sha256:" + "a" * 64
SELECTION = "sha256:" + "b" * 64
REVIEW = "sha256:" + "c" * 64
RECORDED_AT = "2026-08-31T16:04:00+00:00"


def _request(state: ConsumerUiState, action: ConsumerActionKind) -> tuple[ConsumerUiState, tuple]:
    return reduce_consumer_ui(
        state,
        ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=action),
    )


class ConsumerInstallActionTest(unittest.TestCase):
    def test_marketplace_install_requests_preparation_for_the_whole_selection(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.MARKETPLACE),
            selection=(ARTIFACT, OTHER),
            rows=(ARTIFACT, OTHER),
            cursor=1,
        )

        event = key_event("i", state)
        self.assertEqual(
            event,
            ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=ConsumerActionKind.INSTALL),
        )
        assert event is not None
        review, commands = reduce_consumer_ui(state, event)

        self.assertEqual(review.session.screen, ConsumerScreen.REVIEW_SELECTION)
        self.assertIs(review.action, ConsumerActionKind.INSTALL)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.PREPARE_ACTION)
        self.assertIs(commands[0].action, ConsumerActionKind.INSTALL)
        self.assertEqual(commands[0].selection, (ARTIFACT, OTHER))
        self.assertEqual(commands[0].focus, "")
        self.assertEqual(commands[1].kind, ConsumerUiCommandKind.LOAD_SCREEN)

    def test_install_without_a_selection_is_not_a_request(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.MARKETPLACE),
            rows=(ARTIFACT,),
        )

        after, commands = _request(state, ConsumerActionKind.INSTALL)

        self.assertIs(after, state)
        self.assertEqual(commands, ())

    def test_ready_executes_only_the_prepared_review_identity(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.MARKETPLACE),
            selection=(ARTIFACT,),
            rows=(ARTIFACT,),
        )
        review, _ = _request(state, ConsumerActionKind.INSTALL)
        prepared, commands = reduce_consumer_ui(
            review,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.INSTALL,
                semantic_identity=SEMANTIC,
                selection_identity=SELECTION,
                review_digest=REVIEW,
            ),
        )
        self.assertEqual(commands, ())
        self.assertEqual(prepared.session.review_digest, REVIEW)

        ready = prepared
        for screen in (ConsumerScreen.AUTOMATIC_INSPECTION, ConsumerScreen.READY):
            ready, _ = reduce_consumer_ui(
                ready,
                ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=screen),
            )
        event = key_event("enter", ready)
        self.assertEqual(event, ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_ACTION))
        assert event is not None
        running, commands = reduce_consumer_ui(ready, event)

        self.assertEqual(running.session.screen, ConsumerScreen.INSTALLING)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.EXECUTE_ACTION)
        self.assertIs(commands[0].action, ConsumerActionKind.INSTALL)
        self.assertEqual(commands[0].review_digest, REVIEW)
        self.assertEqual(commands[1].kind, ConsumerUiCommandKind.LOAD_SCREEN)

    def test_recorded_install_refreshes_into_success_and_clears_selection(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(
                ConsumerScreen.INSTALLING,
                semantic_identity=SEMANTIC,
                selection_identity=SELECTION,
                review_digest=REVIEW,
            ),
            selection=(ARTIFACT,),
            action=ConsumerActionKind.INSTALL,
        )

        completed, commands = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=ConsumerActionKind.INSTALL,
                text=RECORDED_AT,
            ),
        )

        self.assertEqual(completed.session.screen, ConsumerScreen.SUCCESS)
        self.assertEqual(completed.focus, RECORDED_AT)
        self.assertEqual(completed.selection, ())
        self.assertIsNone(completed.action)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.LOAD_SCREEN)


class ConsumerInstalledActionTest(unittest.TestCase):
    def test_installed_artifact_can_prepare_minimal_repair_or_uninstall(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS),
            focus=ARTIFACT,
        )

        repair_event = key_event("r", state)
        self.assertEqual(
            repair_event,
            ConsumerUiEvent(
                ConsumerUiEventKind.REQUEST_ACTION,
                action=ConsumerActionKind.VERIFY_REPAIR,
            ),
        )
        assert repair_event is not None
        repair, repair_commands = reduce_consumer_ui(state, repair_event)

        self.assertEqual(repair.session.screen, ConsumerScreen.VERIFY_REPAIR)
        self.assertEqual(repair_commands[0].focus, ARTIFACT)
        self.assertIs(repair_commands[0].action, ConsumerActionKind.VERIFY_REPAIR)

        uninstall_event = key_event("u", state)
        assert uninstall_event is not None
        uninstall, uninstall_commands = reduce_consumer_ui(state, uninstall_event)

        self.assertEqual(uninstall.session.screen, ConsumerScreen.UNINSTALL_REVIEW)
        self.assertEqual(uninstall_commands[0].focus, ARTIFACT)
        self.assertIs(uninstall_commands[0].action, ConsumerActionKind.UNINSTALL)

    def test_lifecycle_preparation_needs_a_review_but_invents_no_selection_identity(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS),
            focus=ARTIFACT,
        )
        review, _ = _request(state, ConsumerActionKind.VERIFY_REPAIR)

        prepared, commands = reduce_consumer_ui(
            review,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.VERIFY_REPAIR,
                review_digest=REVIEW,
            ),
        )

        self.assertEqual(commands, ())
        self.assertEqual(prepared.session.review_digest, REVIEW)
        self.assertIsNone(prepared.session.selection_identity)
        self.assertIsNone(prepared.session.semantic_identity)

    def test_update_uses_the_selected_rows_and_repair_cannot_run_on_marketplace(self) -> None:
        updates = ConsumerUiState(
            ConsumerSession(ConsumerScreen.UPDATES),
            selection=(ARTIFACT, OTHER),
            rows=(ARTIFACT, OTHER),
        )

        review, commands = _request(updates, ConsumerActionKind.UPDATE)

        self.assertEqual(review.session.screen, ConsumerScreen.UPDATE_INPUTS)
        self.assertEqual(commands[0].selection, (ARTIFACT, OTHER))

        marketplace = ConsumerUiState(
            ConsumerSession(ConsumerScreen.MARKETPLACE),
            selection=(ARTIFACT,),
            rows=(ARTIFACT,),
        )
        after, invalid = _request(marketplace, ConsumerActionKind.VERIFY_REPAIR)
        self.assertIs(after, marketplace)
        self.assertEqual(invalid, ())


if __name__ == "__main__":
    unittest.main()
