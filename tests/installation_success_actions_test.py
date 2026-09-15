"""CP-23 task 06: Success's actions are working rows, separate from the outcome they follow.

Screen 11 used to print ``[ View installed ] [ View receipt ] [ Done ]`` as prose under the outcome
while its only key was ``Enter → Done``. The names are now the rows of its actions block. Each
opens what it names: Installed, the exact receipt this operation recorded, and Marketplace, leaving
the finished wizard. The outcome is the view's status. Undo is never a row: this surface has no
reviewed installation undo, so its absence is explained instead (D-256). Nothing on Success,
including Esc, reaches back into the wizard that already ran.
"""

from __future__ import annotations

import dataclasses
import string
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    PresentationProfile,
    UndoAvailability,
)
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    _reload,
    frame,
    render_receipt_detail,
    render_transaction_success,
)
from tests.consumer_install_flow_shell_test import at
from tests.consumer_install_flow_shell_test import screens as flow_screens
from tests.consumer_shell_test import screens as shell_screens
from tests.consumer_transaction_screens_test import _bulk_flow, _ran

_ROWS = (
    ConsumerScreen.INSTALLED.value,
    ConsumerScreen.RECEIPT_DETAILS.value,
    ConsumerScreen.MARKETPLACE.value,
)
_LABELS = {
    ConsumerScreen.INSTALLED.value: "View installed",
    ConsumerScreen.RECEIPT_DETAILS.value: "View receipt",
    ConsumerScreen.MARKETPLACE.value: "Done",
}
_WIZARD = frozenset(
    {
        ConsumerScreen.REVIEW_SELECTION,
        ConsumerScreen.AUTOMATIC_INSPECTION,
        ConsumerScreen.REQUIRED_INPUTS,
        ConsumerScreen.REMEDIATION,
        ConsumerScreen.READY,
        ConsumerScreen.INSTALLING,
    }
)
_KEYS = st.one_of(
    st.sampled_from(("up", "down", "enter", "escape", "backspace", " ")),
    st.sampled_from(tuple(string.ascii_letters + string.digits + string.punctuation)),
)


def _success(profile: PresentationProfile = PresentationProfile.FAST, *, receipts=()):
    """Screen 11 over a recorded outcome, focused on the receipt the operation recorded."""

    _, state = at(ConsumerScreen.SUCCESS, profile)
    composed = dataclasses.replace(flow_screens(), receipts=receipts)
    source = CanonicalScreenSource(composed)
    recorded = receipts[-1].recorded_at if receipts else ""
    return source, _reload(source, dataclasses.replace(state, focus=recorded), entering=True)


def _press(source, state: ConsumerUiState, key: str):
    event = key_event(key, state, detail=source.detail(state))
    if event is None:
        return state, ()
    moved, commands = reduce_consumer_ui(state, event)
    return _reload(
        source, moved, entering=moved.session.screen is not state.session.screen
    ), commands


def _on_row(state: ConsumerUiState, row: str) -> ConsumerUiState:
    return dataclasses.replace(state, cursor=state.rows.index(row))


class SuccessRowsTest(unittest.TestCase):
    def test_the_actions_are_rows_and_the_outcome_is_the_view_status(self) -> None:
        source, state = _success()

        actions = source.actions(state)
        status = "\n".join(source.status(state))
        drawn = "\n".join(frame(source, state))

        self.assertEqual(state.rows, _ROWS)
        self.assertEqual(actions, ("> View installed", "  View receipt", "  Done"))
        self.assertTrue(status)
        self.assertNotIn("View installed", status)
        self.assertNotIn("[ View", drawn)
        self.assertNotIn("[ Done ]", drawn)

    def test_enter_on_each_row_goes_where_its_name_says(self) -> None:
        source, state = _success()

        for row, screen in (
            (ConsumerScreen.INSTALLED.value, ConsumerScreen.INSTALLED),
            (ConsumerScreen.RECEIPT_DETAILS.value, ConsumerScreen.RECEIPT_DETAILS),
            (ConsumerScreen.MARKETPLACE.value, ConsumerScreen.MARKETPLACE),
        ):
            with self.subTest(row=row):
                moved, commands = _press(source, _on_row(state, row), "enter")

                self.assertIs(moved.session.screen, screen)
                self.assertEqual(
                    {command.kind for command in commands}, {ConsumerUiCommandKind.LOAD_SCREEN}
                )

    def test_done_leaves_the_finished_wizard(self) -> None:
        source, state = _success()

        done, _ = _press(source, _on_row(state, ConsumerScreen.MARKETPLACE.value), "enter")

        self.assertEqual(done.session.history, (ConsumerScreen.DASHBOARD,))

    def test_view_receipt_opens_the_exact_receipt_this_operation_recorded(self) -> None:
        receipts = shell_screens().receipts
        older, recorded = receipts[1], receipts[0]
        self.assertNotEqual(older.recorded_at, recorded.recorded_at)
        source, state = _success(receipts=(older, recorded))

        opened, _ = _press(source, _on_row(state, ConsumerScreen.RECEIPT_DETAILS.value), "enter")
        drawn = "\n".join(frame(source, opened))

        self.assertIs(opened.session.screen, ConsumerScreen.RECEIPT_DETAILS)
        self.assertEqual(opened.focus, recorded.recorded_at)
        self.assertIn(f"Recorded: {recorded.recorded_at}", drawn)
        self.assertNotIn(f"Recorded: {older.recorded_at}", drawn)

    def test_view_installed_and_done_carry_no_row_name_as_a_subject(self) -> None:
        source, state = _success(receipts=shell_screens().receipts)

        for row in (ConsumerScreen.INSTALLED.value, ConsumerScreen.MARKETPLACE.value):
            with self.subTest(row=row):
                moved, _ = _press(source, _on_row(state, row), "enter")

                self.assertEqual(moved.focus, "")

    def test_the_enter_label_names_the_focused_choice(self) -> None:
        source, state = _success()

        for row, label in _LABELS.items():
            with self.subTest(row=row):
                on = _on_row(state, row)
                legend = key_bindings(on, detail=source.detail(on))

                self.assertIn(("Enter", label), {(item.key, item.label) for item in legend})

    def test_verbose_describes_where_the_focused_row_goes_and_fast_does_not(self) -> None:
        source, verbose = _success(PresentationProfile.VERBOSE)
        _, fast = _success(PresentationProfile.FAST)

        described = [source.description(_on_row(verbose, row)) for row in _ROWS]

        self.assertTrue(all(described), described)
        self.assertEqual(len({lines for lines in described}), len(_ROWS))
        fast_drawn = frame(source, fast)
        self.assertFalse(any(line.strip() in "\n".join(fast_drawn) for line in described[0]))
        self.assertTrue(
            any(line.strip() in "\n".join(frame(source, verbose)) for line in described[0])
        )


class LeavingSuccessNeverReplaysTest(unittest.TestCase):
    def test_esc_after_completion_goes_to_marketplace_rather_than_back_into_the_wizard(
        self,
    ) -> None:
        source, state = _success()

        left, commands = _press(source, state, "escape")

        self.assertIs(left.session.screen, ConsumerScreen.MARKETPLACE)
        self.assertEqual(left.session.history, (ConsumerScreen.DASHBOARD,))
        self.assertEqual(
            {command.kind for command in commands}, {ConsumerUiCommandKind.LOAD_SCREEN}
        )

    @given(keys=st.lists(_KEYS, max_size=10))
    def test_no_key_sequence_on_success_prepares_executes_or_reenters_the_wizard(
        self, keys: list[str]
    ) -> None:
        source, state = _success(receipts=shell_screens().receipts)
        for key in keys:
            if state.session.screen is not ConsumerScreen.SUCCESS or state.quit_pending:
                break
            state, commands = _press(source, state, key)
            self.assertFalse(
                {command.kind for command in commands}
                & {ConsumerUiCommandKind.PREPARE_ACTION, ConsumerUiCommandKind.EXECUTE_ACTION},
                key,
            )
            self.assertNotIn(state.session.screen, _WIZARD, key)


class UndoIsExplainedNotOfferedTest(unittest.TestCase):
    def test_an_unavailable_undo_states_its_reason_and_is_no_row(self) -> None:
        flow = _ran(_bulk_flow())
        view = flow.outcome

        drawn = "\n".join(render_transaction_success(view, PresentationProfile.FAST))

        self.assertFalse(view.undo.available)
        self.assertIn(f"Undo unavailable: {view.undo.reason}", drawn)
        self.assertNotIn("[ Undo ]", drawn)
        self.assertNotIn("View installed", drawn)

    def test_a_reversible_transaction_still_offers_no_undo_this_surface_cannot_review(
        self,
    ) -> None:
        view = dataclasses.replace(
            _ran(_bulk_flow()).outcome,
            undo=UndoAvailability(True, "every change can be reversed", ("launcher",)),
        )

        drawn = "\n".join(render_transaction_success(view, PresentationProfile.FAST))

        self.assertIn("Undo is not offered here", drawn)
        self.assertNotIn("[ Undo ]", drawn)

    def test_the_receipt_does_not_promise_an_undo_the_success_screen_withholds(self) -> None:
        receipt = dataclasses.replace(
            shell_screens().receipts[0],
            undo=UndoAvailability(True, "every change can be reversed", ("launcher",)),
        )

        drawn = "\n".join(render_receipt_detail(receipt, PresentationProfile.VERBOSE))

        self.assertIn("no reviewed undo is offered here", drawn)
        self.assertNotIn("Undo: available", drawn)


if __name__ == "__main__":
    unittest.main()
