"""`QA-080`: the counts on Ready must be reconcilable with what somebody asked for.

Reported in issue #7 against the released `v0.1.1`: installing one MCP server said `2 launcher(s)
written`. One of the two files is the launcher the harness runs; the other is the configuration file
that harness reads (D-264). One effect kind covers both, so the counter called both launchers, and a
reader who asked for one server had no way to reconcile the number with their own request.

The same table left a placement -- a Skill delivered into a harness, which has no launcher at all --
as `1 other change`.
"""

from __future__ import annotations

import unittest

from aart_cli.application.consumer_session import begin_installation
from aart_cli.application.consumer_views import PresentationProfile
from aart_cli.application.installation_proposal import BoundInputs
from aart_cli.domain.harness import McpRegistration, Scope, mcp_target
from aart_cli.domain.inspection import EnvironmentFact, EnvironmentFacts, FactState
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Ok
from aart_cli.tui_consumer import render_ready
from tests.consumer_flow_test import _begin, _selection
from tests.installation_proposal_test import _launcher, _planned
from tests.placement_offer_test import _machine, _nothing_installed, _offer, _skill_placement


def _ready(flow) -> str:
    assert isinstance(flow, Ok), getattr(flow, "diagnostics", ())
    return "\n".join(render_ready(flow.value.plan, PresentationProfile.FAST))


def _registrations(*harnesses: str) -> tuple[McpRegistration, ...]:
    command = _launcher().command
    return tuple(
        McpRegistration(mcp_target(harness, Scope.PROJECT), "github", command, (harness,))
        for harness in harnesses
    )


class InstallReviewCountsTest(unittest.TestCase):
    def test_a_launcher_and_a_configuration_file_are_not_two_launchers(self) -> None:
        text = _ready(_begin())

        self.assertIn("1 launcher(s) written", text)
        self.assertIn("1 configuration file(s) written", text)
        self.assertNotIn("2 launcher(s) written", text)

    def test_one_launcher_serves_every_harness_that_keeps_its_own_configuration(self) -> None:
        text = _ready(_begin(_planned(registrations=_registrations("tabnine", "claude"))))

        self.assertIn("1 launcher(s) written", text)
        self.assertIn("2 configuration file(s) written", text)

    def test_an_artifact_that_configures_nothing_reports_only_its_launcher(self) -> None:
        unconfigured = _planned(bound=BoundInputs(()), declared=(), configuration=())

        text = _ready(_begin(unconfigured, credential_observations=()))

        self.assertIn("1 launcher(s) written", text)
        self.assertNotIn("configuration file(s) written", text)

    def test_an_artifact_with_no_launcher_says_what_it_does_instead(self) -> None:
        offered = _offer(_skill_placement())
        assert isinstance(offered, Ok), getattr(offered, "diagnostics", ())
        (placement,) = offered.value.installations
        facts = EnvironmentFacts(
            "darwin",
            tuple(EnvironmentFact(item.id, FactState.AVAILABLE) for item in placement.requirements),
            _machine(),
        )

        text = _ready(
            begin_installation(
                (placement,),
                _selection(placement.artifact),
                facts,
                EffectivePolicy(),
                observed=((placement.coordinate, _nothing_installed(placement)),),
            )
        )

        self.assertIn("1 harness file(s) delivered", text)
        self.assertNotIn("launcher", text)
        self.assertNotIn("other change", text)


if __name__ == "__main__":
    unittest.main()
