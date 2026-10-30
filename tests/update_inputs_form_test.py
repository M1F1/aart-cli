"""§161, B-262: screen 16 asks what an update newly needs with the Required Inputs form.

An update that needs a value its installation does not hold opens the same form screen 07 has: Set
later, one field per value, Continue. Continue prepares the same update again with the answers, and
16 then shows its review. Escape goes back to 15, and a new update starts with an empty form.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    CONFIG_CONTINUE_ROW,
    CONFIG_SET_LATER_ROW,
    ConsumerActionKind,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    InstallationConfigDraft,
    InstallationConfigField,
    input_form_open,
    key_event,
    reduce_consumer_ui,
    typing_text,
)
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.domain.inputs import SKIPPED_INPUT
from aart_cli.tui_consumer import CanonicalScreenSource, frame
from tests.consumer_shell_test import screens
from tests.install_time_config_form_test import _config_view

ARTIFACT = "company/mcp/warehouse@1.5.0"
OWNER = "company/mcp/warehouse"
FIELD = InstallationConfigField("project-id", "", None, owner=OWNER, required=True)
ROW = FIELD.row
REVIEW = "sha256:" + "c" * 64


def _updating() -> ConsumerUiState:
    """Screen 16 right after `i` on 15, while the update is being prepared."""

    return ConsumerUiState(
        ConsumerSession(ConsumerScreen.UPDATE_INPUTS, history=(ConsumerScreen.UPDATES,)),
        action=ConsumerActionKind.UPDATE,
        selection=(ARTIFACT,),
    )


def _asked(state: ConsumerUiState | None = None) -> ConsumerUiState:
    opened, commands = reduce_consumer_ui(
        state or _updating(),
        ConsumerUiEvent(
            ConsumerUiEventKind.ACTION_PREPARED,
            action=ConsumerActionKind.UPDATE,
            config_draft=InstallationConfigDraft((FIELD,)),
        ),
    )
    assert [command.screen for command in commands] == [ConsumerScreen.UPDATE_INPUTS], commands
    # The screen source draws the rows on LOAD_SCREEN; this is what it draws for the form.
    return replace(opened, rows=(CONFIG_SET_LATER_ROW, ROW, CONFIG_CONTINUE_ROW), cursor=1)


def _press(state: ConsumerUiState, key: str):
    event = key_event(key, state)
    assert event is not None, key
    return reduce_consumer_ui(state, event)


class TheFormOpensOnSixteenTest(unittest.TestCase):
    def test_an_update_that_needs_a_value_opens_the_form_and_stays_on_16(self) -> None:
        opened = _asked()

        self.assertIs(opened.session.screen, ConsumerScreen.UPDATE_INPUTS)
        self.assertTrue(input_form_open(opened))
        self.assertIsNone(opened.session.review_digest)
        self.assertTrue(typing_text(opened))

    def test_continue_prepares_the_same_update_with_the_answers(self) -> None:
        typed, _ = _press(_asked(), "p-42")
        accepted, _ = _press(typed, "enter")
        at_continue = replace(accepted, cursor=2)

        submitted, commands = _press(at_continue, "enter")

        (command,) = commands
        self.assertIs(command.kind, ConsumerUiCommandKind.PREPARE_ACTION)
        self.assertIs(command.action, ConsumerActionKind.UPDATE)
        self.assertEqual(command.selection, (ARTIFACT,))
        self.assertEqual(command.config_answers, ((ROW, "p-42"),))
        self.assertFalse(submitted.config_form_active)
        self.assertIs(submitted.session.screen, ConsumerScreen.UPDATE_INPUTS)

    def test_continue_does_nothing_until_every_required_value_is_given(self) -> None:
        self.assertIsNone(key_event("enter", replace(_asked(), cursor=2)))

    def test_set_later_answers_the_rest_with_the_placeholder(self) -> None:
        _, commands = _press(replace(_asked(), cursor=0), "enter")

        (command,) = commands
        self.assertIs(command.action, ConsumerActionKind.UPDATE)
        self.assertEqual(command.config_answers, ((ROW, SKIPPED_INPUT),))

    def test_the_prepared_review_closes_the_form_and_enter_confirms_it(self) -> None:
        typed, _ = _press(_asked(), "p-42")
        accepted, _ = _press(typed, "enter")
        submitted, _ = _press(replace(accepted, cursor=2), "enter")

        reviewed, _ = reduce_consumer_ui(
            submitted,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.UPDATE,
                semantic_identity="sha256:" + "a" * 64,
                selection_identity="sha256:" + "b" * 64,
                review_digest=REVIEW,
            ),
        )

        self.assertEqual(reviewed.session.review_digest, REVIEW)
        self.assertFalse(input_form_open(reviewed))
        event = key_event("enter", reviewed)
        self.assertIs(event.kind, ConsumerUiEventKind.CONFIRM_ACTION)

    def test_prepared_again_the_form_keeps_what_was_typed(self) -> None:
        typed, _ = _press(_asked(), "p-42")

        again = _asked(typed)

        self.assertEqual(again.config_draft.value(ROW), "p-42")

    def test_escape_goes_back_to_updates(self) -> None:
        back, _ = _press(_asked(), "escape")

        self.assertIs(back.session.screen, ConsumerScreen.UPDATES)


class ANewUpdateStartsEmptyTest(unittest.TestCase):
    def test_what_was_typed_for_another_update_is_not_carried_over(self) -> None:
        stale = ConsumerUiState(
            ConsumerSession(ConsumerScreen.UPDATES),
            selection=(ARTIFACT,),
            rows=(ARTIFACT,),
            config_draft=InstallationConfigDraft((replace(FIELD, value="old"),)),
        )

        moved, commands = reduce_consumer_ui(
            stale,
            ConsumerUiEvent(ConsumerUiEventKind.REQUEST_ACTION, action=ConsumerActionKind.UPDATE),
        )

        self.assertIs(moved.session.screen, ConsumerScreen.UPDATE_INPUTS)
        self.assertEqual(moved.config_draft.fields, ())
        self.assertEqual(commands[0].config_answers, ())

    def test_a_ready_update_never_opens_the_form(self) -> None:
        reviewed, _ = reduce_consumer_ui(
            _updating(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.UPDATE,
                semantic_identity="sha256:" + "a" * 64,
                selection_identity="sha256:" + "b" * 64,
                review_digest=REVIEW,
            ),
        )

        self.assertFalse(input_form_open(reviewed))
        self.assertEqual(reviewed.session.review_digest, REVIEW)


class SixteenDrawsTheFormTest(unittest.TestCase):
    def test_the_form_is_drawn_on_16_as_on_07(self) -> None:
        source = CanonicalScreenSource(replace(screens(), installation_inputs=(_config_view(),)))
        field = InstallationConfigField("organization", "acme", None)
        state = replace(
            _updating(),
            config_draft=InstallationConfigDraft((field,)),
            config_form_active=True,
        )
        state = replace(state, rows=source.rows(state), cursor=1)

        drawn = "\n".join(frame(source, state))

        self.assertEqual(
            source.rows(state), (CONFIG_SET_LATER_ROW, "organization", CONFIG_CONTINUE_ROW)
        )
        self.assertRegex(drawn, r"\n[> ] Set later\n")
        self.assertIn("GitHub organization", drawn)
        self.assertIn("[acme]", drawn)
        self.assertIn("[Type] Edit", drawn)


if __name__ == "__main__":
    unittest.main()
