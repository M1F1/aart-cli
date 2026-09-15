"""Screens 10 and 11 when the install was a Selection, not one artifact.

An install is confirmed once and may establish several artifacts, so what it produces is one
transaction (D-064). Drawing that as a single lifecycle result would have to pick one member to
name and silently drop the rest -- including a member that never ran, which is exactly the member
somebody needs to see.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_session import begin_installation, record_installation
from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerScreen
from agent_artifacts.application.execution import (
    InstallationArtifactExecution,
    InstallationExecutionOutcome,
)
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Ok
from agent_artifacts.tui_consumer import CanonicalScreenSource, _reload, frame, screens_from
from tests.consumer_session_e2e_test import TODAY, _route
from tests.installation_proposal_test import _nothing_installed, _planned, _selection
from tests.installation_transaction_test import _proposal

MOMENT = "2026-08-31T17:05:00+00:00"


def _machine():
    from agent_artifacts.application.consumer_session import assemble_consumer_machine

    return assemble_consumer_machine((), today=TODAY)


def _flow():
    planned = _planned()
    begun = begin_installation(
        (planned,),
        _selection(planned.artifact),
        EnvironmentFacts("darwin", ()),
        EffectivePolicy(),
        observed=((planned.coordinate, _nothing_installed(planned)),),
    )
    assert isinstance(begun, Ok), getattr(begun, "diagnostics", ())
    return begun.value


def _bulk_flow():
    """A flow over two artifacts, where the second was never attempted."""

    proposal, _ = _proposal()
    from agent_artifacts.application.consumer_session import ConsumerFlow
    from agent_artifacts.application.consumer_views import project_install_plan

    return ConsumerFlow(proposal, project_install_plan(proposal.plan))


def _ran(flow, *, attempted: bool = True):
    outcome = InstallationExecutionOutcome(
        flow.proposal,
        tuple(
            InstallationArtifactExecution(
                plan,
                not_attempted=True,
                detail="everything was already true"
                if attempted
                else "not attempted because an earlier artifact did not complete",
            )
            for plan in flow.proposal.lifecycle
        ),
    )
    recorded = record_installation(flow, outcome, recorded_at=MOMENT)
    assert isinstance(recorded, Ok), getattr(recorded, "diagnostics", ())
    return recorded.value


def _drawn(screen: ConsumerScreen, flow) -> str:
    source = CanonicalScreenSource(
        screens_from(_machine(), plan=flow.plan, transaction=flow.outcome)
    )
    state = _reload(source, ConsumerUiState(), entering=True)
    for hop in _route(screen):
        state, _ = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=hop)
        )
        state = _reload(source, state, entering=True)
    assert state.session.screen is screen
    return "\n".join(frame(source, state))


class TransactionScreenTest(unittest.TestCase):
    def test_nothing_has_run_until_something_has(self) -> None:
        drawn = _drawn(ConsumerScreen.SUCCESS, _flow())

        self.assertIn("Nothing has run yet", drawn)

    def test_success_reports_the_selection_rather_than_one_of_its_artifacts(self) -> None:
        flow = _ran(_bulk_flow())

        drawn = _drawn(ConsumerScreen.SUCCESS, flow)

        self.assertIn("Installed 2 artifacts", drawn)
        for member in flow.outcome.artifacts:
            self.assertIn(member.coordinate, drawn)

    def test_a_member_that_never_ran_is_drawn_rather_than_dropped(self) -> None:
        flow = _ran(_bulk_flow(), attempted=False)

        drawn = _drawn(ConsumerScreen.INSTALLING, flow)

        # Drawn the way every other status is drawn, but drawn.
        self.assertIn("not attempted", drawn)
        self.assertIn("earlier artifact", drawn)

    def test_no_drawn_transaction_screen_offers_an_undo_it_cannot_perform(self) -> None:
        flow = _ran(_bulk_flow())

        drawn = _drawn(ConsumerScreen.SUCCESS, flow)

        self.assertFalse(flow.outcome.undo.available)
        self.assertNotIn("[ Undo ]", drawn)


if __name__ == "__main__":
    unittest.main()
