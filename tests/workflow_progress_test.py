"""CP-19 step 11: workflow chrome and Back share the reducer's real journey state."""

from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, frame
from tests.maintainer_candidate_shell_test import _shell, _views


def _state(screen, *history) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen, history=history),
        settings=ConsumerSettings().with_maintainer_mode(True),
        focus="candidate-id",
    )


class WorkflowProgressTest(TestCase):
    def setUp(self) -> None:
        self.empty = CanonicalScreenSource(ConsumerScreens(project_dashboard((), registry_count=0)))

    def test_each_workflow_family_shows_completed_current_and_upcoming_steps(self) -> None:
        scenarios = (
            (
                _state(
                    MaintainerScreen.CANDIDATE_DIFF,
                    MaintainerScreen.CANDIDATES,
                    MaintainerScreen.CANDIDATE_DETAILS,
                ),
                "✓ Candidate",
                "▸ Diff",
                "· Promotion Review",
            ),
            (
                _state(
                    MaintainerScreen.REGISTRY_INIT_REVIEW,
                    MaintainerScreen.REGISTRY,
                    MaintainerScreen.REGISTRY_INIT,
                ),
                "✓ Registry",
                "▸ Review Init",
                "·",
            ),
            (
                _state(
                    MaintainerScreen.REGISTRY_REBUILD,
                    MaintainerScreen.REGISTRY,
                ),
                "✓ Registry",
                "▸ Rebuild Registry",
                "· Review Rebuild",
            ),
            (
                _state(
                    MaintainerScreen.SOURCE_SYNC,
                    MaintainerScreen.SOURCES,
                ),
                "✓ Sources",
                "▸ Source Sync",
                "· Source Sync Result",
            ),
            (
                _state(
                    MaintainerScreen.SOURCE_ADD_REVIEW,
                    MaintainerScreen.SOURCES,
                    MaintainerScreen.SOURCE_ADD,
                ),
                "✓ Sources",
                "▸ Review Source",
                "·",
            ),
            (
                _state(
                    ConsumerScreen.AUTOMATIC_INSPECTION,
                    ConsumerScreen.MARKETPLACE,
                    ConsumerScreen.REVIEW_SELECTION,
                ),
                "✓ Marketplace",
                "▸ Automatic Inspection",
                "· Ready",
            ),
        )

        for state, completed, current, upcoming in scenarios:
            with self.subTest(screen=state.session.screen):
                drawn = "\n".join(frame(self.empty, state))
                self.assertIn(completed, drawn)
                self.assertIn(current, drawn)
                if upcoming != "·":
                    self.assertIn(upcoming, drawn)
                progress_lines = tuple(
                    line for line in drawn.splitlines() if any(icon in line for icon in "✓▸·")
                )
                self.assertTrue(progress_lines)
                self.assertTrue(all(len(line) <= 100 for line in progress_lines))

    def test_dashboard_and_owning_lists_do_not_claim_a_workflow_has_started(self) -> None:
        for screen in (
            ConsumerScreen.DASHBOARD,
            ConsumerScreen.MARKETPLACE,
            MaintainerScreen.CANDIDATES,
            MaintainerScreen.REGISTRY,
            MaintainerScreen.SOURCES,
        ):
            with self.subTest(screen=screen):
                self.assertNotIn("▸", "\n".join(frame(self.empty, _state(screen))))

    def test_back_inside_candidate_promotion_keeps_the_same_candidate_available(self) -> None:
        views = _views()
        source = _shell(views)
        assert views.candidates is not None
        candidate = views.candidates[0].id
        state = replace(
            _state(
                MaintainerScreen.CANDIDATE_DIFF,
                MaintainerScreen.CANDIDATES,
                MaintainerScreen.CANDIDATE_DETAILS,
            ),
            focus=candidate,
        )

        returned, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.BACK))
        drawn = "\n".join(frame(source, returned))

        self.assertIs(returned.session.screen, MaintainerScreen.CANDIDATE_DETAILS)
        self.assertEqual(returned.focus, candidate)
        self.assertNotIn("not available", drawn.casefold())
        self.assertIn("▸ Details", drawn)

    def test_every_back_edge_in_candidate_promotion_retains_its_stable_subject(self) -> None:
        route = (
            MaintainerScreen.CANDIDATES,
            MaintainerScreen.CANDIDATE_DETAILS,
            MaintainerScreen.CANDIDATE_DIFF,
            MaintainerScreen.VALIDATION,
            MaintainerScreen.POLICY_REVIEW,
            MaintainerScreen.PROMOTION_REVIEW,
            MaintainerScreen.PROMOTION_MODE,
            MaintainerScreen.REGISTRY_DIFF,
            MaintainerScreen.REGISTRY_VALIDATION,
            MaintainerScreen.REGISTRY_COMMIT,
        )
        for index in range(2, len(route)):
            with self.subTest(screen=route[index]):
                state = _state(route[index], *route[:index])
                returned, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.BACK))

                self.assertIs(returned.session.screen, route[index - 1])
                self.assertEqual(returned.focus, "candidate-id")

    def test_back_outside_a_workflow_still_clears_stale_detail_focus(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(
                ConsumerScreen.ACTIVITY_DETAILS,
                history=(ConsumerScreen.ACTIVITY,),
            ),
            focus="activity-record",
        )

        returned, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.BACK))

        self.assertIs(returned.session.screen, ConsumerScreen.ACTIVITY)
        self.assertEqual(returned.focus, "")


if __name__ == "__main__":
    import unittest

    unittest.main()
