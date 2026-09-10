"""`QA-079`: the review says which harnesses will receive the artifact, and why that is not a menu.

The operator installed and only afterwards found out where it had gone. Nothing on the way through
named a harness, so there was no point at which the answer could have been checked, let alone
changed.

The set is not a preference and offering it as one would be a lie of a different kind: the shell
installs into every harness this build measured that the artifact itself declares support for
(`D-231`), so it is derived from the machine and the manifest, with nothing left over for anybody
to choose. What was missing is that the screen never said so. It says both halves now -- the names,
and where they come from.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.domain.result import Ok
from agent_artifacts.tui_consumer import render_ready
from tests.consumer_flow_test import _begin


class ReviewNamesTheHarnessesTest(unittest.TestCase):
    def _ready(self) -> str:
        begun = _begin()
        assert isinstance(begun, Ok), getattr(begun, "diagnostics", ())
        return "\n".join(render_ready(begun.value.plan, PresentationProfile.FAST))

    def test_the_review_names_the_harness_the_artifact_will_reach(self) -> None:
        self.assertIn("tabnine", self._ready())

    def test_it_says_where_that_set_came_from_rather_than_offering_it_as_a_choice(self) -> None:
        text = self._ready()

        self.assertIn("Harnesses:", text)
        self.assertIn("declares", text)


if __name__ == "__main__":
    unittest.main()
