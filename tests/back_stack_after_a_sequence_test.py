"""CP-21 step 6: a finished sequence leaves the back stack (`QA-072`).

`QA-027` gave every finished journey a forward exit -- one key that lands on the list the next piece
of work starts from -- and stopped there. The stack was untouched, so Esc from that list walked back
into the wizard that had just run. The operator hit it from two directions: Initialize Registry, and
an install from Marketplace.

These are claims about the session's own stack, so they are stated over `reduce` rather than over a
rendered frame. The heading reads the same stack (`D-236`), so a trail with a place named twice is
the same defect seen from the other side, and one test says so.
"""

from __future__ import annotations

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
)
from agent_artifacts.application.maintainer_views import MaintainerScreen


def _state(screen, *history, maintainer: bool = True) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen, history=tuple(history)),
        settings=ConsumerSettings(maintainer_mode=maintainer),
    )


def _navigate(state: ConsumerUiState, screen) -> ConsumerUiState:
    updated, _ = reduce_consumer_ui(
        state, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=screen)
    )
    return updated


def _back(state: ConsumerUiState) -> ConsumerUiState:
    updated, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.BACK))
    return updated


class FinishedSequenceLeavesTheStackTest(TestCase):
    """Returning to a place already on the stack is a return, not a step deeper."""

    def _finished_registry_init(self) -> ConsumerUiState:
        """The operator's own journey: Registry, Initialize, its review, then back to Registry."""

        return _state(
            MaintainerScreen.REGISTRY_INIT_REVIEW,
            ConsumerScreen.DASHBOARD,
            MaintainerScreen.DASHBOARD,
            MaintainerScreen.REGISTRY,
            MaintainerScreen.REGISTRY_INIT,
        )

    def test_landing_back_on_the_screen_a_journey_started_from_rewinds_to_it(self) -> None:
        landed = _navigate(self._finished_registry_init(), MaintainerScreen.REGISTRY)

        self.assertIs(landed.session.screen, MaintainerScreen.REGISTRY)
        self.assertEqual(
            landed.session.history, (ConsumerScreen.DASHBOARD, MaintainerScreen.DASHBOARD)
        )

    def test_esc_after_it_reaches_the_dashboard_rather_than_the_finished_wizard(self) -> None:
        landed = _back(_navigate(self._finished_registry_init(), MaintainerScreen.REGISTRY))

        self.assertIs(landed.session.screen, MaintainerScreen.DASHBOARD)

    def test_marketplace_after_an_install_goes_back_to_the_dashboard(self) -> None:
        state = _state(
            ConsumerScreen.SUCCESS,
            ConsumerScreen.DASHBOARD,
            ConsumerScreen.MARKETPLACE,
            ConsumerScreen.ARTIFACT_DETAILS,
            ConsumerScreen.REVIEW_SELECTION,
            ConsumerScreen.READY,
            ConsumerScreen.INSTALLING,
            maintainer=False,
        )

        landed = _navigate(state, ConsumerScreen.MARKETPLACE)

        self.assertEqual(landed.session.history, (ConsumerScreen.DASHBOARD,))
        self.assertIs(_back(landed).session.screen, ConsumerScreen.DASHBOARD)

    def test_a_place_is_never_on_the_stack_twice(self) -> None:
        state = _state(
            MaintainerScreen.SOURCE_SYNC_RESULT,
            ConsumerScreen.DASHBOARD,
            MaintainerScreen.DASHBOARD,
            MaintainerScreen.SOURCES,
            MaintainerScreen.SOURCE_DETAILS,
            MaintainerScreen.SOURCE_SYNC,
        )

        landed = _navigate(state, MaintainerScreen.SOURCES)
        trail = (*landed.session.history, landed.session.screen)

        self.assertEqual(len(trail), len(set(trail)))

    def test_a_forward_step_to_somewhere_new_still_pushes(self) -> None:
        state = _state(
            MaintainerScreen.SOURCES, ConsumerScreen.DASHBOARD, MaintainerScreen.DASHBOARD
        )

        landed = _navigate(state, MaintainerScreen.SOURCE_DETAILS)

        self.assertEqual(
            landed.session.history,
            (ConsumerScreen.DASHBOARD, MaintainerScreen.DASHBOARD, MaintainerScreen.SOURCES),
        )


class EscFromAListReachesItsDashboardTest(TestCase):
    """The second half of `QA-072`: a list answers to the dashboard that declares it."""

    def test_a_list_reached_sideways_still_leaves_to_its_own_dashboard(self) -> None:
        """Candidates is reachable from the Registry screen, and is owned by the dashboard."""

        state = _state(
            MaintainerScreen.CANDIDATES,
            ConsumerScreen.DASHBOARD,
            MaintainerScreen.DASHBOARD,
            MaintainerScreen.REGISTRY,
        )

        self.assertIs(_back(state).session.screen, MaintainerScreen.DASHBOARD)

    def test_a_consumer_list_leaves_to_the_home_dashboard(self) -> None:
        state = _state(
            ConsumerScreen.INSTALLED,
            ConsumerScreen.DASHBOARD,
            ConsumerScreen.DOCTOR,
            maintainer=False,
        )

        self.assertIs(_back(state).session.screen, ConsumerScreen.DASHBOARD)

    def test_a_detail_below_a_list_still_goes_back_to_that_list(self) -> None:
        """Only a dashboard's own lists are redirected; a drill-down keeps ordinary back."""

        state = _state(
            MaintainerScreen.SOURCE_DETAILS,
            ConsumerScreen.DASHBOARD,
            MaintainerScreen.DASHBOARD,
            MaintainerScreen.SOURCES,
        )

        self.assertIs(_back(state).session.screen, MaintainerScreen.SOURCES)

    def test_esc_never_invents_a_forward_step_to_a_dashboard_never_visited(self) -> None:
        """Leaving is a return. A dashboard nobody has been to is not somewhere to return to."""

        stranded = _state(ConsumerScreen.INSTALLED, maintainer=False)

        self.assertIs(_back(stranded), stranded)

    def test_a_list_whose_dashboard_is_not_on_the_stack_walks_the_stack_it_has(self) -> None:
        state = _state(ConsumerScreen.INSTALLED, ConsumerScreen.DOCTOR, maintainer=False)

        self.assertIs(_back(state).session.screen, ConsumerScreen.DOCTOR)

    def test_a_dashboard_itself_still_walks_its_own_stack(self) -> None:
        state = _state(MaintainerScreen.DASHBOARD, ConsumerScreen.DASHBOARD)

        self.assertIs(_back(state).session.screen, ConsumerScreen.DASHBOARD)
