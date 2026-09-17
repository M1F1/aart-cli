"""CP-25.08: the Dashboard separates Candidates awaiting action from settled ones (issue #9).

`Candidates: N` counted every durable record, so a Source whose Candidates were all promoted still
reported work waiting for the maintainer. The records themselves must stay -- Promoted, Superseded,
Rejected and Source Removed are the audit trail -- so the fix is in the arithmetic the Dashboard
shows, not in what is stored.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.application.maintainer_views import (
    MaintainerSourceStatus,
    MaintainerSourceView,
    project_maintainer_dashboard,
)
from agent_artifacts.domain.candidates import (
    ACTIVE_CANDIDATE_STATES,
    SETTLED_CANDIDATE_STATES,
    CandidateState,
)
from agent_artifacts.tui_maintainer import (
    render_maintainer_dashboard,
    render_maintainer_source,
)


def _source(
    alias: str,
    states: tuple[tuple[CandidateState, int], ...],
) -> MaintainerSourceView:
    return MaintainerSourceView(
        alias,
        "git",
        f"https://example.invalid/{alias}.git",
        "main",
        True,
        MaintainerSourceStatus.SYNCED,
        "a" * 40,
        1_700_000_000,
        sum(count for _, count in states),
        states,
        ("company",),
    )


class TheTwoHalvesOfTheVocabularyTest(unittest.TestCase):
    """Every state belongs to exactly one half, or some state goes uncounted on the Dashboard."""

    def test_the_halves_partition_the_state_vocabulary(self) -> None:
        self.assertEqual(ACTIVE_CANDIDATE_STATES | SETTLED_CANDIDATE_STATES, set(CandidateState))
        self.assertEqual(ACTIVE_CANDIDATE_STATES & SETTLED_CANDIDATE_STATES, set())

    def test_a_candidate_waiting_on_a_human_decision_is_awaiting_action(self) -> None:
        """A targeted mutation moved `APPROVAL_REQUIRED` into the settled half and no test noticed.

        It is the most literally pending state there is -- the Candidate is stopped precisely
        because it wants a maintainer -- so classing it as settled would have hidden the very work
        issue #9 is about, in the name of fixing issue #9.
        """

        for state in (
            CandidateState.NEW,
            CandidateState.CHANGED,
            CandidateState.READY,
            CandidateState.WARNING,
            CandidateState.INVALID,
            CandidateState.APPROVAL_REQUIRED,
        ):
            with self.subTest(state=state):
                self.assertIn(state, ACTIVE_CANDIDATE_STATES)

    def test_an_approval_required_candidate_is_counted_as_awaiting_action(self) -> None:
        source = _source("authors", ((CandidateState.APPROVAL_REQUIRED, 2),))

        dashboard = project_maintainer_dashboard((source,))

        self.assertEqual(dashboard.active_candidate_count, 2)
        self.assertEqual(dashboard.settled_candidate_count, 0)
        self.assertIn(
            "Candidates: 2",
            "\n".join(render_maintainer_dashboard(dashboard, PresentationProfile.FAST)),
        )

    def test_a_promoted_candidate_is_settled_rather_than_waiting(self) -> None:
        for state in (
            CandidateState.PROMOTED,
            CandidateState.SUPERSEDED,
            CandidateState.REJECTED,
            CandidateState.SOURCE_REMOVED,
        ):
            with self.subTest(state=state):
                self.assertIn(state, SETTLED_CANDIDATE_STATES)


class APromotedSourceLooksSettledTest(unittest.TestCase):
    def test_two_promoted_candidates_leave_nothing_awaiting_action(self) -> None:
        source = _source("authors", ((CandidateState.PROMOTED, 2),))

        self.assertEqual(source.active_count, 0)
        self.assertEqual(source.settled_count, 2)
        self.assertEqual(source.count(CandidateState.PROMOTED), 2)

    def test_the_durable_records_are_still_counted_in_the_total(self) -> None:
        """The audit trail is not deleted to make the Dashboard read nicely."""

        source = _source("authors", ((CandidateState.PROMOTED, 2),))

        self.assertEqual(source.candidate_count, 2)
        self.assertEqual(source.candidate_states, ((CandidateState.PROMOTED, 2),))


class TheDashboardArithmeticCannotContradictItselfTest(unittest.TestCase):
    def test_a_mixed_source_splits_into_the_two_halves_and_they_sum_to_the_total(self) -> None:
        source = _source(
            "authors",
            (
                (CandidateState.READY, 3),
                (CandidateState.INVALID, 1),
                (CandidateState.PROMOTED, 2),
            ),
        )

        dashboard = project_maintainer_dashboard((source,))

        self.assertEqual(dashboard.candidate_count, 6)
        self.assertEqual(dashboard.active_candidate_count, 4)
        self.assertEqual(dashboard.settled_candidate_count, 2)
        self.assertEqual(
            dashboard.active_candidate_count + dashboard.settled_candidate_count,
            dashboard.candidate_count,
        )

    def test_ready_and_invalid_stay_derived_from_the_same_candidate_set(self) -> None:
        source = _source(
            "authors",
            (
                (CandidateState.READY, 3),
                (CandidateState.INVALID, 1),
                (CandidateState.PROMOTED, 2),
            ),
        )

        dashboard = project_maintainer_dashboard((source,))

        self.assertEqual(dashboard.ready_count, 3)
        self.assertEqual(dashboard.validation_failure_count, 1)
        self.assertLessEqual(
            dashboard.ready_count + dashboard.validation_failure_count,
            dashboard.active_candidate_count,
        )

    def test_the_lifecycle_breakdown_carries_every_state_that_occurs(self) -> None:
        dashboard = project_maintainer_dashboard(
            (
                _source("authors", ((CandidateState.READY, 3), (CandidateState.PROMOTED, 2))),
                _source("vendors", ((CandidateState.PROMOTED, 1), (CandidateState.REJECTED, 4))),
            )
        )

        self.assertEqual(
            dashboard.lifecycle_counts,
            (
                (CandidateState.READY, 3),
                (CandidateState.PROMOTED, 3),
                (CandidateState.REJECTED, 4),
            ),
        )

    def test_an_empty_registry_has_no_breakdown_and_no_counts(self) -> None:
        dashboard = project_maintainer_dashboard(())

        self.assertEqual(dashboard.lifecycle_counts, ())
        self.assertEqual(dashboard.active_candidate_count, 0)
        self.assertEqual(dashboard.settled_candidate_count, 0)


class TheScreenSaysWhichIsWhichTest(unittest.TestCase):
    def _rendered(self, source: MaintainerSourceView, profile: PresentationProfile) -> str:
        return "\n".join(
            render_maintainer_dashboard(project_maintainer_dashboard((source,)), profile)
        )

    def test_a_fully_promoted_source_does_not_report_candidates_awaiting_action(self) -> None:
        rendered = self._rendered(
            _source("authors", ((CandidateState.PROMOTED, 2),)), PresentationProfile.FAST
        )

        self.assertIn("Candidates: 0 awaiting action, 2 settled", rendered)

    def test_a_source_with_nothing_settled_still_reads_as_it_always_did(self) -> None:
        """No settled records means no second clause: the fix must not tax the ordinary case."""

        rendered = self._rendered(
            _source("authors", ((CandidateState.READY, 3),)), PresentationProfile.FAST
        )

        self.assertIn("Candidates: 3", rendered)
        self.assertNotIn("settled", rendered)

    def test_verbose_carries_the_full_lifecycle_breakdown(self) -> None:
        source = _source("authors", ((CandidateState.READY, 3), (CandidateState.PROMOTED, 2)))

        verbose = self._rendered(source, PresentationProfile.VERBOSE)
        fast = self._rendered(source, PresentationProfile.FAST)

        self.assertIn("Candidate lifecycle: ready=3, promoted=2", verbose)
        self.assertNotIn("Candidate lifecycle", fast)

    def test_the_source_row_leads_with_what_is_still_waiting(self) -> None:
        """`QA-092`'s complaint in its original place: two promoted Candidates are not a backlog."""

        rendered = "\n".join(
            render_maintainer_source(
                _source("authors", ((CandidateState.PROMOTED, 2),)),
                PresentationProfile.FAST,
            )
        )

        self.assertIn("Candidates: 0 awaiting action", rendered)
        self.assertIn("2 settled", rendered)


if __name__ == "__main__":
    unittest.main()
