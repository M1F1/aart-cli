"""D-398: Fast says what the reader acts on, and `[v]` says it gives more.

The operator: *"chce ogolnie zeby uzytkownik doswiadczyl minimalistycznego intuicyjnego TUI ktore nie
przytloczy go informacjami jesli nie wlaczy opcji more info klikajac [v]"*. Three things were said
in Fast that the reader could not act on: a count of ticked rows on every screen an install passes
through, Ready's risk vocabulary and review identity, and a key named for the mode it was in.
"""

from __future__ import annotations

import dataclasses
import unittest

from aart_cli.application.consumer_ui import key_bindings
from aart_cli.application.consumer_views import ConsumerScreen, PresentationProfile
from aart_cli.tui_consumer import frame, render_ready
from tests.consumer_install_flow_shell_test import at, plan_view

_TICKED = ("public/mcp/github@1.6.0",)


def _drawn(screen: ConsumerScreen, profile=PresentationProfile.FAST) -> str:
    source, state = at(screen, profile)
    return "\n".join(frame(source, dataclasses.replace(state, selection=_TICKED)))


class TheSelectedCountTest(unittest.TestCase):
    def test_a_screen_an_install_passes_through_does_not_count_the_ticks(self) -> None:
        for screen in (ConsumerScreen.READY, ConsumerScreen.INSTALLING, ConsumerScreen.SUCCESS):
            with self.subTest(screen=screen):
                self.assertNotIn("1 selected", _drawn(screen))

    def test_the_harness_choice_does_not_count_the_artifacts_ticked_before_it(self) -> None:
        # D-401: on 05 Space ticks harnesses, so a count of Marketplace ticks reads as theirs.
        self.assertNotIn("1 selected", _drawn(ConsumerScreen.REVIEW_SELECTION))

    def test_the_screen_rows_are_ticked_on_still_counts_them(self) -> None:
        self.assertIn("1 selected", _drawn(ConsumerScreen.MARKETPLACE))

    def test_more_info_counts_them_everywhere(self) -> None:
        self.assertIn("1 selected", _drawn(ConsumerScreen.READY, PresentationProfile.VERBOSE))


class ReadyTest(unittest.TestCase):
    def test_a_material_risk_is_still_said_in_fast_and_the_routine_ones_are_not(self) -> None:
        # INV-151 holds under D-398: network access and high-risk code are said in plain words.
        view = dataclasses.replace(
            plan_view(),
            risks=("local-mutation", "network-mutation", "high-risk-execution"),
        )

        fast = "\n".join(render_ready(view, PresentationProfile.FAST))

        self.assertIn("changes network access", fast)
        self.assertIn("runs high-risk code", fast)
        self.assertNotIn("local mutation", fast)
        self.assertNotIn("Risks:", fast)


class TheDetailKeyTest(unittest.TestCase):
    def test_v_is_named_for_what_pressing_it_gives(self) -> None:
        for profile, label in (
            (PresentationProfile.FAST, "More info"),
            (PresentationProfile.VERBOSE, "Less info"),
        ):
            with self.subTest(profile=profile):
                _, state = at(ConsumerScreen.MARKETPLACE, profile)
                legend = {(item.key, item.label) for item in key_bindings(state)}

                self.assertIn(("v", label), legend)


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
