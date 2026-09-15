"""CP-23 task 09: a Candidate the local Registry already records is not offered again.

The owner committed a promotion and came back to a Candidates row still reading ``New``, with the
review, the registry diff and bulk promotion all still offering the same Candidate. Candidate state
only moves to ``promoted`` when Source Sync reconciles against the *synchronized* approved Registry,
and a local commit is deliberately not a sync (D-249), so nothing had changed what the screens read.

The answer is derived from what the Registry trees record, never stored beside history (D-259): a
Candidate the local checkout records and the synchronized Registry does not is ``Promoted locally``;
one the synchronized Registry records is ``Promoted``. Either refuses another promotion, in every
projection and at the one transaction choke point, and a restart reads the same trees and says the
same thing.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.application.maintainer_promotion import (
    CandidatePromotionRecord,
    candidate_promotion_record,
    prepare_candidate_promotion_transaction,
    prepare_promotion_transaction,
)
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.application.maintainer_views import (
    project_maintainer_bulk_promotion,
    project_maintainer_candidates,
    project_maintainer_promotion_review,
    project_maintainer_registry_diff,
)
from agent_artifacts.application.promotion import (
    PromotionEvidence,
    load_registry_versions,
    plan_bulk_promotion,
    project_promotion,
)
from agent_artifacts.domain.candidates import CandidateState, assess_candidate
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from agent_artifacts.sources.model import source_snapshot_digest
from agent_artifacts.tui_maintainer import maintainer_candidate_detail, render_maintainer_candidates
from tests.candidate_history_test import _ready_scan
from tests.maintainer_composition_e2e_test import _two_ready_candidates
from tests.maintainer_source_scan_test import _compiled

_COMPANY = SourceAlias("company")
_EMPTY = SourceSnapshot(SnapshotOrigin.LOCAL, ())
_POLICY = EffectivePolicy()


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _ready(bundle: CandidateBundle) -> CandidateBundle:
    validation = validate_candidate(bundle, policy=_POLICY)
    return CandidateBundle(
        assess_candidate(
            bundle.candidate,
            findings=validation.findings,
            manual_approval_required=validation.manual_approval_required,
        ),
        bundle.artifact,
    )


def _promoted_tree(*bundles: CandidateBundle) -> SourceSnapshot:
    """The Registry tree a committed promotion of exactly these Candidates leaves behind."""

    ready = tuple(_ready(bundle) for bundle in bundles)
    planned = plan_bulk_promotion(
        _EMPTY,
        ready,
        evidence=tuple(
            (item.candidate.id, PromotionEvidence(_digest("1"), _digest("2"))) for item in ready
        ),
        approved=(),
    )
    assert isinstance(planned, Ok), planned
    projected = project_promotion(_EMPTY, planned.value)
    assert isinstance(projected, Ok), projected
    return projected.value


def _versions(tree: SourceSnapshot):
    loaded = load_registry_versions(tree)
    assert isinstance(loaded, Ok), loaded
    return loaded.value


def _approved(tree: SourceSnapshot) -> ApprovedRegistryState:
    digest = source_snapshot_digest(tree)
    assert isinstance(digest, Ok), digest
    return ApprovedRegistryState(_COMPANY, "f" * 40, digest.value, _versions(tree))


def _messages(result) -> str:
    assert isinstance(result, Err), result
    return " ".join(item.message for item in result.diagnostics)


class PromotionRecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = _ready_scan().active[0]
        self.recorded = _versions(_promoted_tree(self.bundle))

    def test_the_local_checkout_alone_records_it_as_promoted_locally(self) -> None:
        record = candidate_promotion_record(self.bundle, approved=(), local=self.recorded)

        self.assertIs(record, CandidatePromotionRecord.PROMOTED_LOCALLY)

    def test_the_synchronized_registry_recording_it_makes_it_promoted(self) -> None:
        for local in (self.recorded, (), None):
            with self.subTest(local=local):
                record = candidate_promotion_record(
                    self.bundle, approved=self.recorded, local=local
                )

                self.assertIs(record, CandidatePromotionRecord.PROMOTED)

    def test_no_record_or_no_readable_tree_is_not_a_promotion(self) -> None:
        for approved, local in (((), ()), (None, None), ((), None), (None, ())):
            with self.subTest(approved=approved, local=local):
                record = candidate_promotion_record(self.bundle, approved=approved, local=local)

                self.assertIs(record, CandidatePromotionRecord.NOT_PROMOTED)

    def test_a_genuinely_new_version_is_not_covered_by_the_old_record(self) -> None:
        newer = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            _compiled(revision="b", version="1.1.0", server="print('newer')\n"),
            previous=_ready_scan().history,
            approved=(),
            target_registry=_COMPANY,
        )
        assert isinstance(newer, Ok), newer

        record = candidate_promotion_record(newer.value.active[0], approved=(), local=self.recorded)

        self.assertNotEqual(newer.value.active[0].candidate.id, self.bundle.candidate.id)
        self.assertIs(record, CandidatePromotionRecord.NOT_PROMOTED)

    def test_the_same_version_with_different_content_is_not_covered_either(self) -> None:
        conflicting = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            _compiled(revision="b", server="print('same version, other code')\n"),
            previous=_ready_scan().history,
            approved=(),
            target_registry=_COMPANY,
        )
        assert isinstance(conflicting, Ok), conflicting
        candidate = conflicting.value.active[0].candidate

        record = candidate_promotion_record(
            conflicting.value.active[0], approved=(), local=self.recorded
        )

        self.assertEqual(candidate.artifact.coordinate, self.bundle.candidate.artifact.coordinate)
        self.assertNotEqual(candidate.id, self.bundle.candidate.id)
        self.assertIs(record, CandidatePromotionRecord.NOT_PROMOTED)

    def test_a_repeat_source_sync_keeps_the_candidate_the_checkout_records(self) -> None:
        first = _ready_scan()
        again = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=first.history,
            approved=(),
            target_registry=_COMPANY,
        )
        assert isinstance(again, Ok), again

        record = candidate_promotion_record(again.value.active[0], approved=(), local=self.recorded)

        self.assertEqual(again.value.active[0].candidate.id, self.bundle.candidate.id)
        self.assertIs(record, CandidatePromotionRecord.PROMOTED_LOCALLY)

    def test_source_sync_after_registry_sync_promotes_it_and_keeps_its_history(self) -> None:
        first = _ready_scan()
        synced = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=first.history,
            approved=self.recorded,
            target_registry=_COMPANY,
        )
        assert isinstance(synced, Ok), synced
        promoted = synced.value.active[0]

        self.assertIs(promoted.candidate.state, CandidateState.PROMOTED)
        self.assertIn(promoted.candidate.id, {item.candidate.id for item in synced.value.history})
        self.assertIs(
            candidate_promotion_record(promoted, approved=self.recorded, local=self.recorded),
            CandidatePromotionRecord.PROMOTED,
        )

    @given(
        local=st.sets(st.sampled_from((0, 1))),
        approved=st.sets(st.sampled_from((0, 1))),
    )
    def test_each_of_several_candidates_is_judged_by_its_own_record(
        self, local: set[int], approved: set[int]
    ) -> None:
        bundles = _two_ready_candidates().active

        def recorded(chosen: set[int]):
            picked = tuple(bundles[index] for index in sorted(chosen))
            return _versions(_promoted_tree(*picked)) if picked else ()

        for index, bundle in enumerate(bundles):
            record = candidate_promotion_record(
                bundle, approved=recorded(approved), local=recorded(local)
            )
            expected = (
                CandidatePromotionRecord.PROMOTED
                if index in approved
                else CandidatePromotionRecord.PROMOTED_LOCALLY
                if index in local
                else CandidatePromotionRecord.NOT_PROMOTED
            )
            self.assertIs(record, expected, (index, local, approved))


class CandidatesSayWhatTheRegistryRecordsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scan = _two_ready_candidates()
        self.promoted, self.other = self.scan.active

    def _views(self, record: CandidatePromotionRecord):
        return project_maintainer_candidates(
            (self.scan,), promotion={self.promoted.candidate.id.value: record}
        )

    def test_the_row_and_its_detail_read_promoted_locally_and_nothing_older(self) -> None:
        views = self._views(CandidatePromotionRecord.PROMOTED_LOCALLY)
        cursor = self.promoted.candidate.id.value

        table = render_maintainer_candidates(views, cursor=cursor, profile=PresentationProfile.FAST)
        row = next(line for line in table if line.startswith(">"))
        detail = "\n".join(maintainer_candidate_detail(views, cursor=cursor))

        self.assertIn("Promoted locally", row)
        self.assertIn("Promoted locally", detail)
        for older in ("New", "Ready", "Published"):
            self.assertNotIn(older, row)
            self.assertNotIn(older, detail)

    def test_a_synchronized_record_reads_promoted(self) -> None:
        views = self._views(CandidatePromotionRecord.PROMOTED)
        cursor = self.promoted.candidate.id.value

        row = next(
            line
            for line in render_maintainer_candidates(
                views, cursor=cursor, profile=PresentationProfile.FAST
            )
            if line.startswith(">")
        )

        self.assertIn("Promoted", row)
        self.assertNotIn("locally", row)
        self.assertNotIn("Published", row)

    def test_the_other_candidate_keeps_its_own_state(self) -> None:
        views = self._views(CandidatePromotionRecord.PROMOTED_LOCALLY)
        other = next(item for item in views if item.id == self.other.candidate.id.value)

        self.assertIs(other.promotion, CandidatePromotionRecord.NOT_PROMOTED)
        self.assertIs(other.state, CandidateState.READY)

    def test_without_evidence_the_projection_is_unchanged(self) -> None:
        self.assertEqual(
            project_maintainer_candidates((self.scan,)),
            self._views(CandidatePromotionRecord.NOT_PROMOTED),
        )


class NoRecordedCandidateIsOfferedAgainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = _ready_scan().active[0]
        self.validation = validate_candidate(self.bundle, policy=_POLICY)
        self.approved = _approved(_EMPTY)

    def test_review_and_diff_refuse_in_every_mode_and_name_the_way_on(self) -> None:
        for mode in PromotionMode:
            with self.subTest(mode=mode):
                review = project_maintainer_promotion_review(
                    self.bundle,
                    self.validation,
                    _POLICY,
                    self.approved,
                    mode=mode,
                    promotion=CandidatePromotionRecord.PROMOTED_LOCALLY,
                )
                diff = project_maintainer_registry_diff(
                    self.bundle,
                    self.validation,
                    _POLICY,
                    self.approved,
                    _EMPTY,
                    mode=mode,
                    promotion=CandidatePromotionRecord.PROMOTED_LOCALLY,
                )

                self.assertFalse(review.confirmable)
                self.assertFalse(diff.plannable)
                for refusals in (review.refusals, diff.refusals):
                    joined = " ".join(refusals)
                    self.assertIn("already promoted", joined)
                    self.assertIn("Registry Sync", joined)

    def test_a_synchronized_record_refuses_and_points_at_source_sync(self) -> None:
        review = project_maintainer_promotion_review(
            self.bundle,
            self.validation,
            _POLICY,
            self.approved,
            mode=PromotionMode.VENDORED,
            promotion=CandidatePromotionRecord.PROMOTED,
        )

        self.assertFalse(review.confirmable)
        self.assertIn("Source Sync", " ".join(review.refusals))

    def test_an_unrecorded_candidate_is_still_offered(self) -> None:
        review = project_maintainer_promotion_review(
            self.bundle, self.validation, _POLICY, self.approved, mode=PromotionMode.VENDORED
        )
        diff = project_maintainer_registry_diff(
            self.bundle,
            self.validation,
            _POLICY,
            self.approved,
            _EMPTY,
            mode=PromotionMode.VENDORED,
        )

        self.assertTrue(review.confirmable, review.refusals)
        self.assertTrue(diff.plannable, diff.refusals)

    def test_bulk_promotion_excludes_only_the_recorded_candidate_and_says_why(self) -> None:
        scan = _two_ready_candidates()
        promoted, other = scan.active
        runs = tuple((item, validate_candidate(item, policy=_POLICY)) for item in scan.active)

        bulk = project_maintainer_bulk_promotion(
            _COMPANY,
            runs,
            self.approved,
            promotion={promoted.candidate.id.value: CandidatePromotionRecord.PROMOTED_LOCALLY},
        )

        self.assertEqual(
            tuple(item.candidate_id for item in bulk.candidates), (other.candidate.id.value,)
        )
        excluded = {item.candidate_id: item.reason for item in bulk.excluded}
        self.assertIn("already promoted", excluded[promoted.candidate.id.value])


class TheTransactionRefusesADuplicateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = _ready_scan().active[0]
        self.validation = validate_candidate(self.bundle, policy=_POLICY)
        self.tree = _promoted_tree(self.bundle)

    def test_a_synchronized_tree_that_records_the_candidate_is_refused_by_name(self) -> None:
        # Registry Sync has observed the published commit but Source Sync has not run yet, so the
        # Candidate still reads Ready and the baseline matches exactly: only the record refuses.
        prepared = prepare_candidate_promotion_transaction(
            self.bundle, self.validation, _POLICY, _approved(self.tree), self.tree
        )

        self.assertIn("already promoted", _messages(prepared))

    def test_an_unpublished_local_commit_names_the_duplicate_rather_than_only_the_baseline(
        self,
    ) -> None:
        prepared = prepare_candidate_promotion_transaction(
            self.bundle, self.validation, _POLICY, _approved(_EMPTY), self.tree
        )

        self.assertIn("already promoted", _messages(prepared))

    def test_a_selection_containing_one_recorded_candidate_is_refused_whole(self) -> None:
        scan = _two_ready_candidates()
        promoted, _ = scan.active
        tree = _promoted_tree(promoted)

        prepared = prepare_promotion_transaction(
            scan.active,
            tuple(validate_candidate(item, policy=_POLICY) for item in scan.active),
            _POLICY,
            _approved(tree),
            tree,
        )

        self.assertIn("already promoted", _messages(prepared))

    def test_a_failed_promotion_leaves_the_candidate_promotable(self) -> None:
        # Nothing was written, so the tree the retry reads still records nothing for it.
        prepared = prepare_candidate_promotion_transaction(
            self.bundle, self.validation, _POLICY, _approved(_EMPTY), _EMPTY
        )

        self.assertIsInstance(prepared, Ok, prepared)
        self.assertIs(
            candidate_promotion_record(self.bundle, approved=(), local=_versions(_EMPTY)),
            CandidatePromotionRecord.NOT_PROMOTED,
        )


if __name__ == "__main__":
    unittest.main()
