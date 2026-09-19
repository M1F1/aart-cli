"""`QA-079`: the review says which harnesses will receive the artifact, and why that is not a menu.

The operator installed and only afterwards found out where it had gone. Nothing on the way through
named a harness, so there was no point at which the answer could have been checked, let alone
changed.

CP-23 task 10 (D-260) made the set a choice: screen 05 offers the eligible harnesses and the
reviewed plan is narrowed to the ones ticked. Ready names that choice as the user's intent, and no
longer claims the set is every harness the machine measured.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_views import PresentationProfile
from aart_cli.domain.result import Ok
from aart_cli.tui_consumer import render_ready
from tests.consumer_flow_test import _begin


class ReviewNamesTheHarnessesTest(unittest.TestCase):
    def _ready(self, *, chosen: tuple[str, ...] = ()) -> str:
        begun = _begin()
        assert isinstance(begun, Ok), getattr(begun, "diagnostics", ())
        plan = replace(begun.value.plan, chosen_targets=chosen)
        return "\n".join(render_ready(plan, PresentationProfile.FAST))

    def test_the_review_names_the_harness_the_artifact_will_reach(self) -> None:
        self.assertIn("tabnine", self._ready())

    def test_it_names_the_chosen_set_as_a_choice_rather_than_everything_measured(self) -> None:
        text = self._ready(chosen=("tabnine",))

        self.assertIn("Harnesses: tabnine (chosen for this installation).", text)
        self.assertNotIn("every harness this machine measured", text)


if __name__ == "__main__":
    unittest.main()
