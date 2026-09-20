"""`QA-027`: the end of a sequence is where the next one starts, not a dead end.

A completed Maintainer sequence left the operator on its result screen with no forward key at all.
Enter did nothing, so the only way anywhere was Esc, Esc, Esc back through every intermediate
screen of the journey they had just finished.  In the operator's own words: after adding a Source
and having it go well, the next Enter should return to the first screen of that section, so another
one can be added.

Screen 45 already worked this way -- once its commit had happened, Enter meant "go on to the
registry" rather than "confirm".  The rule existed and was applied to one screen.  This states it
for the result screens that have no forward route of their own, and gives the finished promotion
journey the one key back to Candidates it was missing.
"""

from __future__ import annotations

import unittest

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import ConsumerSession, ConsumerSettings
from aart_cli.application.maintainer_views import (
    MaintainerScreen,
    maintainer_navigation_targets,
)


def _state(screen, **changes) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen, history=(MaintainerScreen.SOURCES, MaintainerScreen.SOURCE_SYNC)),
        settings=ConsumerSettings().with_maintainer_mode(True),
        **changes,
    )


class TerminalResultReturnTest(unittest.TestCase):
    def test_enter_on_the_source_sync_result_returns_to_sources(self) -> None:
        event = key_event("enter", _state(MaintainerScreen.SOURCE_SYNC_RESULT))

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, MaintainerScreen.SOURCES)

    def test_the_route_it_takes_is_a_declared_one(self) -> None:
        """A key that navigates somewhere the map does not allow is a key that does nothing."""

        self.assertIn(
            MaintainerScreen.SOURCES,
            maintainer_navigation_targets(MaintainerScreen.SOURCE_SYNC_RESULT),
        )

    def test_the_footer_says_where_that_enter_goes(self) -> None:
        labels = {
            binding.label for binding in key_bindings(_state(MaintainerScreen.SOURCE_SYNC_RESULT))
        }

        self.assertIn("Sources", labels)

    def test_pressing_it_really_moves_the_session(self) -> None:
        moved, _ = reduce_consumer_ui(
            _state(MaintainerScreen.SOURCE_SYNC_RESULT),
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.SOURCES),
        )

        self.assertIs(moved.session.screen, MaintainerScreen.SOURCES)

    def test_a_finished_promotion_is_one_key_from_the_next_candidate(self) -> None:
        """The other half of the finding: the completed Candidate journey had no way back."""

        registry = ConsumerUiState(
            ConsumerSession(MaintainerScreen.REGISTRY),
            settings=ConsumerSettings().with_maintainer_mode(True),
        )

        event = key_event("c", registry)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, MaintainerScreen.CANDIDATES)
        self.assertIn(
            MaintainerScreen.CANDIDATES,
            maintainer_navigation_targets(MaintainerScreen.REGISTRY),
        )

    def test_the_registry_commit_still_goes_on_to_the_registry(self) -> None:
        """`D-069`'s screen 45 rule is the precedent this generalizes, not something it replaces."""

        committed = ConsumerUiState(
            ConsumerSession(MaintainerScreen.REGISTRY_COMMIT),
            settings=ConsumerSettings().with_maintainer_mode(True),
        )

        event = key_event("enter", committed)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, MaintainerScreen.REGISTRY)

    def test_a_review_waiting_for_its_confirmation_is_not_a_result(self) -> None:
        waiting = ConsumerUiState(
            ConsumerSession(MaintainerScreen.SOURCE_SYNC),
            settings=ConsumerSettings().with_maintainer_mode(True),
            action=ConsumerActionKind.SOURCE_SYNC,
        )

        event = key_event("enter", waiting)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.CONFIRM_ACTION)


if __name__ == "__main__":
    unittest.main()
