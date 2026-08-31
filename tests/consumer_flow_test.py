"""The action somebody is in the middle of, held beside the machine it will change.

Screens 05 to 11 are projections of a flow, not of a machine. Until now nothing built one, so a
running consumer application drew "Nothing has been planned yet" no matter what had been planned:
every piece existed -- a package that says what it needs, a plan, an inspection, remediations, a
proposal, an execution -- with nothing holding them together between one screen and the next.

This is that holder. It is built once from a proposal and rebuilt after an action, never derived
inside a draw, so drawing the same screen twice cannot produce two different answers.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_session import (
    FLOW_INVALID,
    ConsumerFlow,
    begin_installation,
    record_installation,
)
from agent_artifacts.application.consumer_views import ConsumerPlanView
from agent_artifacts.application.execution import ExecutionOutcome, LifecycleExecutionOutcome
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok
from tests.installation_proposal_test import (
    ORG,
    TOKEN,
    _nothing_installed,
    _planned,
    _selection,
)

FACTS = EnvironmentFacts("darwin", ())


def _credential() -> CredentialObservation:
    return CredentialObservation(
        CredentialReference(TOKEN, CredentialProviderRef("macos-keychain", "aart", "github-token")),
        ProviderState.AVAILABLE,
        CredentialState.PRESENT,
    )


def _begin(planned=None, **overrides):
    planned = _planned() if planned is None else planned
    fields: dict[str, object] = {
        "observed": ((planned.coordinate, _nothing_installed(planned)),),
        "credential_observations": (_credential(),),
    }
    fields.update(overrides)
    return begin_installation(
        (planned,),
        _selection(planned.artifact),
        FACTS,
        EffectivePolicy(),
        **fields,  # type: ignore[arg-type]
    )


def _outcome(flow: ConsumerFlow) -> LifecycleExecutionOutcome:
    """What executing this flow's own plan, changing nothing, would report."""

    plan = flow.proposal.lifecycle[0]
    return LifecycleExecutionOutcome(plan, ExecutionOutcome(plan.review_digest, (), True))


def _reason(result) -> str:
    return result.diagnostics[0].message


class BegunFlowTest(unittest.TestCase):
    def test_a_begun_flow_carries_the_plan_the_review_screens_draw(self) -> None:
        begun = _begin()

        self.assertIsInstance(begun, Ok, getattr(begun, "diagnostics", ()))
        self.assertIsInstance(begun.value, ConsumerFlow)
        self.assertIsInstance(begun.value.plan, ConsumerPlanView)

    def test_the_plan_a_flow_carries_projects_the_proposal_it_carries(self) -> None:
        """One plan, two shapes.

        A review naming different effects than the proposal runs is exactly what
        `InstallationProposal` exists to make impossible, and projecting from anything other than
        the proposal's own plan would put that back.
        """

        flow = _begin().value

        self.assertEqual(flow.plan.review_digest, str(flow.proposal.review_digest))
        self.assertEqual(len(flow.plan.effects), len(flow.proposal.plan.mutation.effects))

    def test_the_inputs_the_flow_shows_are_the_ones_the_artifacts_declare(self) -> None:
        flow = _begin().value

        self.assertEqual([item.id for item in flow.plan.inputs], sorted([str(ORG), str(TOKEN)]))

    def test_a_credential_the_machine_already_holds_is_shown_as_held(self) -> None:
        """Screen 07 asks for what is missing, so what a provider already has has to reach it."""

        flow = _begin().value
        secret = next(item for item in flow.plan.inputs if item.id == str(TOKEN))

        self.assertEqual(secret.health, CredentialState.PRESENT.value)

    def test_no_flow_carries_a_credential_value_anywhere_a_screen_could_draw_it(self) -> None:
        flow = _begin().value
        secret = next(item for item in flow.plan.inputs if item.id == str(TOKEN))

        self.assertFalse(hasattr(secret, "value"))
        self.assertIn("macos-keychain", str(secret.provider_reference))

    def test_a_flow_that_would_change_nothing_says_so(self) -> None:
        flow = _begin().value

        self.assertEqual(flow.converged, flow.proposal.converged)

    def test_a_flow_begins_holding_no_outcome_because_nothing_has_run(self) -> None:
        self.assertIsNone(_begin().value.outcome)

    def test_what_the_proposal_refuses_the_flow_refuses(self) -> None:
        refused = _begin(observed=())

        self.assertIsInstance(refused, Err)
        self.assertIn("nothing was observed", _reason(refused))

    def test_a_flow_cannot_be_begun_from_something_that_is_not_an_installation(self) -> None:
        refused = begin_installation(
            ("github",),  # type: ignore[arg-type]
            _selection(_planned().artifact),
            FACTS,
            EffectivePolicy(),
        )

        self.assertIsInstance(refused, Err)


class RecordedOutcomeTest(unittest.TestCase):
    def test_an_outcome_is_recorded_onto_the_flow_that_planned_it(self) -> None:
        flow = _begin().value

        after = record_installation(flow, _outcome(flow))

        self.assertIsInstance(after, Ok, getattr(after, "diagnostics", ()))
        self.assertEqual(
            after.value.outcome.review_digest, str(flow.proposal.lifecycle[0].review_digest)
        )
        self.assertIs(after.value.proposal, flow.proposal)

    def test_recording_an_outcome_leaves_the_reviewed_plan_alone(self) -> None:
        flow = _begin().value

        after = record_installation(flow, _outcome(flow)).value

        self.assertIs(after.plan, flow.plan)
        self.assertIsNone(flow.outcome)

    def test_an_outcome_from_a_plan_this_flow_never_proposed_is_refused(self) -> None:
        """Screens 10 and 11 report what ran.

        Reporting one flow's result against another's review is how somebody reads "installed"
        about an install that never happened.
        """

        flow = _begin().value
        other = _begin(_planned(registrations=())).value

        refused = record_installation(flow, _outcome(other))

        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.diagnostics[0].code, FLOW_INVALID)


if __name__ == "__main__":
    unittest.main()
