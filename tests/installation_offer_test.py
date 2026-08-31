"""One Selection becomes one offer: what would be installed, measured, and what it needs agreed.

Everything an install needs already exists -- `plan_artifact_installation` decides what one artifact
would do here, `inspect_requirements` measures whether this machine can, `installation_remediations`
says what somebody would have to agree to, and `begin_installation` turns the three into a review.
What did not exist was anything in production that put them together. The only caller was a test
that wired them by hand, which is why neither the shell's action handler nor the public commands
could reach the canonical path: each would have had to repeat that wiring, and two copies of it
would disagree the first time one changed.

The offer is not a decision. It plans, it measures and it lists what could be agreed to; it selects
no remediation and performs no effect. Deciding is `begin_installation`, and it is deliberately a
second call, because the thing between the two is a person.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_session import begin_installation
from agent_artifacts.application.installation_offer import (
    OFFER_NOT_PLANNABLE,
    ArtifactPlacement,
    InstallationOffer,
    offer_installation,
)
from agent_artifacts.domain.harness import Scope, mcp_target
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import CurrentState
from agent_artifacts.domain.result import Err, Ok
from tests.artifact_installation_test import (
    INTERPRETER,
    PAYLOAD_SOURCE,
    _capabilities,
    _description,
    _facts,
    _Inspector,
    _Keychain,
    _sources,
)
from tests.installation_proposal_test import ROOT, _resolved, _selection


def _placement(name: str = "github", *, root: str = ROOT, **overrides: object):
    fields: dict[str, object] = {
        "artifact": _resolved(name),
        "description": _description(),
        "root": root,
        "payload_source": PAYLOAD_SOURCE,
        "targets": (mcp_target("tabnine", Scope.PROJECT),),
        "sources": _sources(),
    }
    fields.update(overrides)
    return ArtifactPlacement(**fields)  # type: ignore[arg-type]


def _nothing_installed(desired):
    """This machine, before any of it exists: observed, and observed to be absent."""

    return CurrentState(desired.artifact)


def _offer(*placements, policy: EffectivePolicy | None = None, inspector=None, observe=None):
    return offer_installation(
        placements or (_placement(),),
        policy=policy or EffectivePolicy(),
        facts=_facts(),
        inspect=_Inspector(_capabilities()) if inspector is None else inspector,
        observe=_nothing_installed if observe is None else observe,
        base_interpreter=INTERPRETER,
        resolvers=(_Keychain(),),
    )


class InstallationOfferTest(unittest.TestCase):
    def test_one_call_plans_measures_and_offers(self) -> None:
        offered = _offer()

        self.assertIsInstance(offered, Ok, getattr(offered, "diagnostics", ()))
        self.assertIsInstance(offered.value, InstallationOffer)
        self.assertEqual(len(offered.value.installations), 1)
        self.assertTrue(offered.value.facts.facts, "the offer must carry what it measured")

    def test_the_measured_facts_are_what_the_inspector_said_not_what_was_passed_in(self) -> None:
        """The facts going in carry capabilities; the facts coming out carry measurements."""

        offered = _offer()

        self.assertIsInstance(offered, Ok, getattr(offered, "diagnostics", ()))
        self.assertEqual(_facts().facts, ())
        self.assertTrue(offered.value.facts.facts)

    def test_every_artifact_in_the_selection_is_planned(self) -> None:
        offered = _offer(_placement("github"), _placement("gitlab", root=ROOT + "-gitlab"))

        self.assertIsInstance(offered, Ok, getattr(offered, "diagnostics", ()))
        self.assertEqual(
            [str(item.coordinate.artifact) for item in offered.value.installations],
            ["mcp/github", "mcp/gitlab"],
        )

    def test_one_unplannable_artifact_refuses_the_whole_offer(self) -> None:
        """A Selection is confirmed once. Offering the half that planned would let somebody
        confirm an install of two artifacts and receive one."""

        offered = _offer(
            _placement(), _placement("gitlab", description=_description(contract=None))
        )

        self.assertIsInstance(offered, Err)
        self.assertIn("gitlab", offered.diagnostics[0].message)

    def test_an_inspection_that_fails_refuses_rather_than_offering_unmeasured_work(self) -> None:
        class _Broken:
            def inspect(self, requirements):
                return Err((_unmeasurable(),))

        offered = _offer(inspector=_Broken())

        self.assertIsInstance(offered, Err)

    def test_what_is_offered_is_what_begin_installation_accepts(self) -> None:
        """The offer and the acceptance must be computed by the same functions, or somebody can
        choose the one thing the plan then rejects."""

        offered = _offer()
        self.assertIsInstance(offered, Ok, getattr(offered, "diagnostics", ()))
        offer = offered.value

        begun = begin_installation(
            offer.installations,
            _selection(*(placement.artifact for placement in (_placement(),))),
            offer.facts,
            EffectivePolicy(),
            observed=offer.observed,
            selected_remediations=offer.selected(),
        )

        self.assertIsInstance(begun, Ok, getattr(begun, "diagnostics", ()))

    def test_the_offer_selects_nothing_on_its_own(self) -> None:
        """`remediations` is what could be agreed to. Agreeing is somebody else's call."""

        offered = _offer()

        self.assertIsInstance(offered, Ok, getattr(offered, "diagnostics", ()))
        self.assertEqual(
            offered.value.selected(),
            tuple(item.remediation for item in offered.value.remediations),
        )

    def test_every_installation_is_observed_before_it_is_offered(self) -> None:
        """`begin_installation` refuses an unobserved artifact, so the offer must supply one."""

        offered = _offer(_placement("github"), _placement("gitlab", root=ROOT + "-gitlab"))

        self.assertIsInstance(offered, Ok, getattr(offered, "diagnostics", ()))
        self.assertEqual(
            [str(coordinate) for coordinate, _ in offered.value.observed],
            ["public/mcp/github@1.5.0", "public/mcp/gitlab@1.5.0"],
        )

    def test_an_observer_that_cannot_look_refuses_rather_than_reporting_nothing(self) -> None:
        """Reporting an empty state here would say "nothing is installed" about a machine nobody
        managed to look at, and a first install would then write over whatever is there."""

        def _blind(desired):
            raise OSError("the harness registry is unreadable")

        offered = _offer(observe=_blind)

        self.assertIsInstance(offered, Err)
        self.assertIs(offered.diagnostics[0].code, OFFER_NOT_PLANNABLE)
        self.assertIn("could not be observed", offered.diagnostics[0].message)

    def test_no_placements_is_a_refusal_rather_than_an_empty_offer(self) -> None:
        offered = offer_installation(
            (),
            policy=EffectivePolicy(),
            facts=_facts(),
            inspect=_Inspector(_capabilities()),
            observe=_nothing_installed,
        )

        self.assertIsInstance(offered, Err)
        self.assertIs(offered.diagnostics[0].code, OFFER_NOT_PLANNABLE)


def _unmeasurable():
    from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity

    return Diagnostic(DiagnosticCode("environment-unmeasurable"), Severity.ERROR, "no")


if __name__ == "__main__":
    unittest.main()
