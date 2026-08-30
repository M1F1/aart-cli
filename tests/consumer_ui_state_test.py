from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    PresentationProfile,
)


class ConsumerUiStateTest(unittest.TestCase):
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
