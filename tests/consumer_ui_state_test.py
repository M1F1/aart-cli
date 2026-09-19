from __future__ import annotations

import unittest
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    PresentationProfile,
)


class ConsumerUiStateTest(unittest.TestCase):
    @given(
        st.lists(st.text(alphabet="abcdef", min_size=1, max_size=8), unique=True, max_size=12),
        st.text(alphabet="abcdef", max_size=8),
        st.text(alphabet="abcdef", max_size=8),
    )
    def test_reloading_rows_keeps_the_cursor_then_focus_then_the_first_row(
        self, rows: list[str], standing: str, focus: str
    ) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.MARKETPLACE),
            rows=(standing,) if standing else (),
            focus=focus,
            selection=("selected-but-filtered-out",),
        )
        loaded, commands = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=tuple(rows))
        )
        expected = (
            standing if standing in rows else focus if focus in rows else rows[0] if rows else ""
        )
        self.assertEqual(loaded.current_row, expected)
        self.assertEqual(replace(loaded, rows=state.rows, cursor=state.cursor), state)
        self.assertEqual(commands, ())

    def test_navigation_profile_search_selection_help_and_back_are_pure(self) -> None:
        initial = ConsumerUiState()

        marketplace, commands = reduce_consumer_ui(
            initial,
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.MARKETPLACE),
        )
        searched, _ = reduce_consumer_ui(
            marketplace,
            ConsumerUiEvent(ConsumerUiEventKind.SEARCH, text="github"),
        )
        selected, _ = reduce_consumer_ui(
            searched,
            ConsumerUiEvent(
                ConsumerUiEventKind.TOGGLE_SELECTION,
                key="company/mcp/github@1.0.0",
            ),
        )
        verbose, _ = reduce_consumer_ui(
            selected,
            ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE),
        )
        help_open, _ = reduce_consumer_ui(
            verbose,
            ConsumerUiEvent(ConsumerUiEventKind.HELP),
        )
        back, _ = reduce_consumer_ui(help_open, ConsumerUiEvent(ConsumerUiEventKind.BACK))

        self.assertEqual(initial.session.screen, ConsumerScreen.DASHBOARD)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.LOAD_SCREEN)
        self.assertEqual(searched.search, "github")
        self.assertEqual(selected.selection, ("company/mcp/github@1.0.0",))
        self.assertEqual(verbose.session.profile, PresentationProfile.VERBOSE)
        self.assertTrue(help_open.help_visible)
        self.assertEqual(back.session.screen, ConsumerScreen.DASHBOARD)
        self.assertEqual(back.selection, selected.selection)

    def test_quit_with_selection_requires_confirmation(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.MARKETPLACE),
            selection=("company/mcp/github@1.0.0",),
        )

        pending, commands = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.QUIT))
        cancelled, cancelled_commands = reduce_consumer_ui(
            pending,
            ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_QUIT, accepted=False),
        )
        pending_again, _ = reduce_consumer_ui(cancelled, ConsumerUiEvent(ConsumerUiEventKind.QUIT))
        exited, exit_commands = reduce_consumer_ui(
            pending_again,
            ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_QUIT, accepted=True),
        )

        self.assertTrue(pending.quit_pending)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.CONFIRM_QUIT)
        self.assertFalse(cancelled.quit_pending)
        self.assertEqual(cancelled_commands, ())
        self.assertTrue(exited.exited)
        self.assertEqual(exit_commands[0].kind, ConsumerUiCommandKind.EXIT)

    def test_invalid_contextual_event_is_rejected_without_state_change(self) -> None:
        state = ConsumerUiState()

        after, commands = reduce_consumer_ui(
            state,
            ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SELECTION, key="not-visible-here"),
        )

        self.assertIs(after, state)
        self.assertEqual(commands, ())

    def test_the_way_back_to_the_detail_exists_on_every_screen(self) -> None:
        """INV-154: Fast may hide the routine, but never the route to what it hid.

        Stated over the screen enum rather than over a list, because a screen added later is
        exactly the screen somebody would forget to make switchable, and a list would not notice.
        """

        for screen in ConsumerScreen:
            with self.subTest(screen=screen.value):
                before = ConsumerUiState(ConsumerSession(screen))

                after, commands = reduce_consumer_ui(
                    before, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE)
                )

                self.assertIsNot(after.session.profile, before.session.profile)
                self.assertIs(after.session.screen, before.session.screen)

    @given(st.lists(st.sampled_from(tuple(PresentationProfile)), max_size=30))
    def test_profile_changes_never_change_semantic_identity(
        self, profiles: list[PresentationProfile]
    ) -> None:
        identity = "sha256:" + "a" * 64
        state = ConsumerUiState(
            ConsumerSession(
                ConsumerScreen.READY,
                semantic_identity=identity,
                selection_identity="sha256:" + "b" * 64,
                review_digest="sha256:" + "c" * 64,
            )
        )

        for profile in profiles:
            if state.session.profile is not profile:
                state, _ = reduce_consumer_ui(
                    state, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE)
                )

        self.assertEqual(state.session.semantic_identity, identity)
        self.assertEqual(state.session.selection_identity, "sha256:" + "b" * 64)
        self.assertEqual(state.session.review_digest, "sha256:" + "c" * 64)


if __name__ == "__main__":
    unittest.main()
