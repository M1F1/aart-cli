"""A manifest that would not compile is reported, not silently dropped (`QA-063`)."""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.application.maintainer_views import (
    MaintainerSourceSyncResultView,
)
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.tui_maintainer import render_source_sync_result


class SourceSyncRefusalViewTest(unittest.TestCase):
    """`QA-063`: tolerating a manifest is only an improvement if the operator hears about it.

    Compiling each manifest on its own merits lets a Source with one bad file still produce
    Candidates for the good ones. That is worth nothing -- worse than the Source-wide abort it
    replaces -- if the bad one then vanishes from the report. The Sync landed on this screen, so
    this is where it has to say what it could not read, and name the file.
    """

    def _view(
        self,
        refusals: tuple[tuple[str, str], ...],
        candidates: tuple[tuple[CandidateState, int], ...] = ((CandidateState.NEW, 1),),
    ) -> MaintainerSourceSyncResultView:
        return MaintainerSourceSyncResultView(
            "authors",
            "company",
            "updated",
            "a" * 40,
            # Every manifest the walk found: the ones that became Candidates and the ones that
            # would not compile. Counting only the first kind is what made a refusal disappear.
            sum(count for _, count in candidates) + len(refusals),
            candidates,
            "sha256:" + "b" * 64,
            refusals,
        )

    def test_a_refused_manifest_still_counts_as_a_discovered_manifest(self) -> None:
        view = self._view((("bad/aart.json", "invalid SemVer: 'not-a-version'"),))

        self.assertEqual(2, view.manifest_count)
        self.assertEqual(1, view.candidate_count)

    def test_the_view_carries_each_refused_manifest_with_its_path(self) -> None:
        view = self._view((("bad/aart.json", "invalid SemVer: 'not-a-version'"),))

        self.assertEqual((("bad/aart.json", "invalid SemVer: 'not-a-version'"),), view.refusals)

    def test_a_refused_manifest_is_named_on_the_screen_the_sync_lands_on(self) -> None:
        drawn = "\n".join(
            render_source_sync_result(
                self._view((("bad/aart.json", "invalid SemVer: 'not-a-version'"),)),
                PresentationProfile.FAST,
            )
        )

        self.assertIn("bad/aart.json", drawn)
        self.assertIn("not-a-version", drawn)

    def test_a_clean_sync_says_nothing_about_refusals(self) -> None:
        """An empty section is `QA-068`'s fault; a Source with nothing wrong has nothing to say."""

        drawn = "\n".join(render_source_sync_result(self._view(()), PresentationProfile.FAST))

        self.assertNotIn("could not", drawn.casefold())
        self.assertNotIn("refus", drawn.casefold())

    def test_a_refusal_cannot_carry_a_blank_path_or_a_line_break(self) -> None:
        for refusal in (("", "why"), ("bad/aart.json", ""), ("bad\naart.json", "why")):
            with self.subTest(refusal=refusal):
                with self.assertRaises(ValueError):
                    self._view((refusal,))


if __name__ == "__main__":
    unittest.main()
