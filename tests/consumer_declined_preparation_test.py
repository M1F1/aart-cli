"""A preparation that refused leaves nothing that looks confirmable.

`QA-018`/`B-092`. Add Registry navigates to Review before asking the action adapter to prepare the
exact transaction, because the operator must see the plan on the screen that asks for consent. When
preparation refuses — a duplicate alias, an origin already connected, an unreachable URL — the
adapter clears its pending action and reports a decline with no review digest, and the reducer
correctly declined to record it as a plan. What it did not do was leave the review screen, so the
operator was left reading "press Enter to connect" about a connection that no longer existed;
pressing Enter reached the execution boundary with nothing pending and answered "nothing was
prepared for this action".

A decline now returns to the screen the review was opened from — for Add Registry, the form, with
its values intact and the refusal underneath it — and clears the pending action, so a later Enter
cannot even reach a confirmation.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    RegistryDraft,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)

REVIEW = "sha256:" + "c" * 64


def _declined(state: ConsumerUiState, action: ConsumerActionKind):
    return reduce_consumer_ui(
        state,
        ConsumerUiEvent(ConsumerUiEventKind.ACTION_PREPARED, action=action),
    )


def _requested_registry_addition() -> ConsumerUiState:
    """The exact state the shell is in when Add Registry has asked for its preparation."""

    state = ConsumerUiState(
        ConsumerSession(ConsumerScreen.REGISTRIES),
        rows=("add-registry",),
        cursor=0,
        registry_draft=RegistryDraft(alias="company"),
    )
    opened, _ = reduce_consumer_ui(
        state, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.REGISTRY_ADD)
    )
    requested, _ = reduce_consumer_ui(
        opened,
        ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=ConsumerActionKind.REGISTRY_ADD),
    )
    assert requested.session.screen is ConsumerScreen.REGISTRY_REVIEW, requested.session.screen
    return requested


class DeclinedPreparationTest(unittest.TestCase):
    def test_a_declined_registry_addition_returns_to_the_form_it_was_reviewed_from(self) -> None:
        requested = _requested_registry_addition()

        declined, commands = _declined(requested, ConsumerActionKind.REGISTRY_ADD)

        self.assertIs(declined.session.screen, ConsumerScreen.REGISTRY_ADD)
        self.assertEqual(
            tuple(command.kind for command in commands),
            (ConsumerUiCommandKind.LOAD_SCREEN,),
        )
        self.assertIs(commands[0].screen, ConsumerScreen.REGISTRY_ADD)

    def test_a_declined_preparation_keeps_the_values_the_operator_typed(self) -> None:
        requested = _requested_registry_addition()

        declined, _ = _declined(requested, ConsumerActionKind.REGISTRY_ADD)

        self.assertEqual(declined.registry_draft.alias, "company")

    def test_a_declined_preparation_leaves_no_action_pending(self) -> None:
        requested = _requested_registry_addition()

        declined, _ = _declined(requested, ConsumerActionKind.REGISTRY_ADD)

        self.assertIsNone(declined.action)
        self.assertIsNone(declined.session.review_digest)

    def test_enter_after_a_decline_cannot_reach_the_execution_boundary(self) -> None:
        """The negative `B-092` asks for: no failed preparation may become an execute command."""

        requested = _requested_registry_addition()
        declined, _ = _declined(requested, ConsumerActionKind.REGISTRY_ADD)

        confirmed, commands = reduce_consumer_ui(
            declined, ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_ACTION)
        )

        self.assertEqual(
            tuple(
                command
                for command in commands
                if command.kind is ConsumerUiCommandKind.EXECUTE_ACTION
            ),
            (),
        )
        self.assertIsNone(confirmed.action)

    def test_a_prepared_action_still_records_its_plan_and_stays_on_the_review(self) -> None:
        """The accepting side of the same branch: a real digest is still a real plan."""

        requested = _requested_registry_addition()

        prepared, commands = reduce_consumer_ui(
            requested,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.REGISTRY_ADD,
                review_digest=REVIEW,
            ),
        )

        self.assertIs(prepared.session.screen, ConsumerScreen.REGISTRY_REVIEW)
        self.assertIs(prepared.action, ConsumerActionKind.REGISTRY_ADD)
        self.assertEqual(prepared.session.review_digest, REVIEW)
        self.assertEqual(commands, ())

    def test_a_decline_naming_another_action_changes_nothing(self) -> None:
        requested = _requested_registry_addition()

        unchanged, commands = _declined(requested, ConsumerActionKind.INSTALL)

        self.assertIs(unchanged, requested)
        self.assertEqual(commands, ())

    def test_a_decline_with_no_screen_to_return_to_still_clears_the_action(self) -> None:
        """A review reached with no history behind it must not stay confirmable either."""

        stranded = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REGISTRY_REVIEW),
            action=ConsumerActionKind.REGISTRY_ADD,
            settings=ConsumerSettings(),
        )

        declined, commands = _declined(stranded, ConsumerActionKind.REGISTRY_ADD)

        self.assertIsNone(declined.action)
        self.assertEqual(commands, ())


if __name__ == "__main__":
    unittest.main()
