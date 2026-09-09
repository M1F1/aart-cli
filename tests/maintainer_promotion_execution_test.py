"""CP-14 screen 45 executes only the exact registry transaction screen 43 reviewed."""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.application.maintainer import CandidateBundle
from agent_artifacts.application.maintainer_promotion import (
    CandidatePromotionCommitReceipt,
    CandidatePromotionExecutionResult,
    MaintainerCandidatePromotionPorts,
    execute_candidate_promotion,
    prepare_candidate_promotion_transaction,
)
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.application.maintainer_views import (
    project_maintainer_registry_commit,
    project_maintainer_registry_validation,
)
from agent_artifacts.application.promotion import (
    PromotionApplyReceipt,
    load_registry_versions,
    project_promotion,
    validate_promoted_registry,
)
from agent_artifacts.domain.candidates import assess_candidate
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from agent_artifacts.sources.model import source_snapshot_digest
from agent_artifacts.tui_maintainer import (
    render_maintainer_registry_commit,
    render_maintainer_registry_validation,
)
from tests.maintainer_promotion_test import _bundle


def _approved(snapshot: SourceSnapshot) -> ApprovedRegistryState:
    digest = source_snapshot_digest(snapshot)
    assert isinstance(digest, Ok)
    versions = load_registry_versions(snapshot)
    assert isinstance(versions, Ok)
    return ApprovedRegistryState(SourceAlias("company"), "f" * 40, digest.value, versions.value)


class _PromotionOutput:
    def __init__(self, snapshot: SourceSnapshot, calls: list[str]) -> None:
        self.snapshot = snapshot
        self.calls = calls
        self.apply_calls = 0
        self.corrupt_readback = False

    def current(self):
        self.calls.append("workspace")
        if self.corrupt_readback and self.apply_calls:
            return Ok(
                SourceSnapshot(
                    SnapshotOrigin.LOCAL,
                    self.snapshot.entries
                    + (
                        dataclasses.replace(
                            self.snapshot.entries[0],
                            path=dataclasses.replace(
                                self.snapshot.entries[0].path,
                                parts=("unreviewed",),
                            ),
                        ),
                    ),
                )
            )
        return Ok(self.snapshot)

    def apply(self, command):
        self.calls.append("write")
        self.apply_calls += 1
        projected = project_promotion(self.snapshot, command.plan)
        assert isinstance(projected, Ok), projected
        self.snapshot = projected.value
        return Ok(
            PromotionApplyReceipt(
                command.plan.review_digest,
                command.plan.next_workspace_digest,
                command.plan.next_registry_snapshot,
                command.plan.changed_paths,
            )
        )


def _prepared(snapshot: SourceSnapshot):
    bundle = _bundle()
    policy = EffectivePolicy()
    return prepare_candidate_promotion_transaction(
        bundle,
        validate_candidate(bundle, policy=policy),
        policy,
        _approved(snapshot),
        snapshot,
        mode=PromotionMode.VENDORED,
    )


class CandidatePromotionExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        self.prepared = _prepared(self.snapshot)
        assert isinstance(self.prepared, Ok), self.prepared
        self.calls: list[str] = []
        self.output = _PromotionOutput(self.snapshot, self.calls)

    def _ports(
        self,
        *,
        candidate: CandidateBundle | None = None,
        approved: ApprovedRegistryState | None = None,
        commit_fails: bool = False,
    ) -> MaintainerCandidatePromotionPorts:
        observed = self.prepared.value.promotions[0].observed

        def read_candidate(_candidate_id):
            self.calls.append("candidate")
            return Ok(observed if candidate is None else candidate)

        def read_approved(_alias):
            self.calls.append("approved")
            return Ok(self.prepared.value.promotions[0].approved if approved is None else approved)

        def commit(command):
            self.calls.append("commit")
            if commit_fails:
                return Err(
                    (
                        Diagnostic(
                            DiagnosticCode("test-commit-failed"),
                            Severity.ERROR,
                            "commit failed",
                        ),
                    )
                )
            return Ok(
                CandidatePromotionCommitReceipt(
                    command.review_digest,
                    "c" * 40,
                    command.subject,
                    command.paths,
                )
            )

        return MaintainerCandidatePromotionPorts(
            read_candidate,
            read_approved,
            self.output,
            commit,
        )

    def test_success_rechecks_replans_validates_writes_once_and_validates_readback(self) -> None:
        completed = execute_candidate_promotion(
            self.prepared.value,
            self.prepared.value.review_digest,
            self._ports(),
        )

        assert isinstance(completed, Ok), completed
        self.assertIsInstance(completed.value, CandidatePromotionExecutionResult)
        self.assertEqual(self.output.apply_calls, 1)
        # The approved baseline is read once, before any Candidate: every Candidate a transaction
        # carries is prepared against the same baseline, so reading it per Candidate would let a
        # bulk transaction assemble members against two different registries.
        self.assertEqual(self.calls[:2], ["approved", "candidate"])
        self.assertEqual(self.calls.count("write"), 1)
        self.assertLess(self.calls.index("approved"), self.calls.index("write"))
        self.assertGreater(self.calls.index("commit"), self.calls.index("write"))
        persisted = load_registry_versions(self.output.snapshot)
        assert isinstance(persisted, Ok), persisted
        self.assertIsInstance(validate_promoted_registry(self.output.snapshot, persisted.value), Ok)
        self.assertEqual(
            completed.value.registry_snapshot,
            self.prepared.value.plan.next_registry_snapshot,
        )

    def test_a_different_confirmation_digest_reads_and_writes_nothing(self) -> None:
        completed = execute_candidate_promotion(
            self.prepared.value,
            ObjectDigest("sha256", "0" * 64),
            self._ports(),
        )

        self.assertIsInstance(completed, Err)
        self.assertEqual(self.calls, [])

    def test_a_moved_candidate_refuses_before_reading_or_writing_the_registry(self) -> None:
        original = self.prepared.value.promotions[0].observed
        moved = dataclasses.replace(
            original,
            candidate=assess_candidate(original.candidate),
        )

        completed = execute_candidate_promotion(
            self.prepared.value,
            self.prepared.value.review_digest,
            self._ports(candidate=moved),
        )

        self.assertIsInstance(completed, Err)
        self.assertEqual(self.calls, ["approved", "candidate"])
        self.assertEqual(self.output.apply_calls, 0)

    def test_a_moved_approved_baseline_refuses_before_reading_or_writing_the_workspace(
        self,
    ) -> None:
        moved = dataclasses.replace(
            self.prepared.value.promotions[0].approved,
            revision="1" * 40,
        )

        completed = execute_candidate_promotion(
            self.prepared.value,
            self.prepared.value.review_digest,
            self._ports(approved=moved),
        )

        self.assertIsInstance(completed, Err)
        self.assertEqual(self.calls, ["approved"])
        self.assertEqual(self.output.apply_calls, 0)

    def test_a_workspace_that_moved_after_screen_43_refuses_before_writing(self) -> None:
        self.output.snapshot = SourceSnapshot(
            SnapshotOrigin.LOCAL,
            self.prepared.value.projected.entries
            + (
                dataclasses.replace(
                    self.prepared.value.projected.entries[0],
                    content=b"moved",
                ),
            ),
        )

        completed = execute_candidate_promotion(
            self.prepared.value,
            self.prepared.value.review_digest,
            self._ports(),
        )

        self.assertIsInstance(completed, Err)
        self.assertEqual(self.output.apply_calls, 0)
        self.assertNotIn("write", self.calls)

    def test_a_commit_failure_reports_that_validated_files_remain_in_the_checkout(self) -> None:
        completed = execute_candidate_promotion(
            self.prepared.value,
            self.prepared.value.review_digest,
            self._ports(commit_fails=True),
        )

        assert isinstance(completed, Err), completed
        self.assertEqual(self.output.apply_calls, 1)
        self.assertIn("commit failed", completed.diagnostics[0].message)
        self.assertIn("remain in the checkout", completed.diagnostics[0].message)

    def test_a_persisted_tree_that_does_not_match_the_plan_is_not_committed(self) -> None:
        self.output.corrupt_readback = True

        completed = execute_candidate_promotion(
            self.prepared.value,
            self.prepared.value.review_digest,
            self._ports(),
        )

        assert isinstance(completed, Err), completed
        self.assertEqual(self.output.apply_calls, 1)
        self.assertNotIn("commit", self.calls)
        self.assertIn("persisted registry", completed.diagnostics[0].message)


class CandidatePromotionScreenProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        snapshot = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        prepared = _prepared(snapshot)
        assert isinstance(prepared, Ok), prepared
        self.prepared = prepared.value

    def test_screen_44_reports_the_validated_projected_registry_without_writing(self) -> None:
        view = project_maintainer_registry_validation(self.prepared)
        drawn = "\n".join(render_maintainer_registry_validation(view, PresentationProfile.VERBOSE))

        self.assertEqual(view.registry_snapshot, str(self.prepared.registry_snapshot))
        self.assertIn("Registry validation: Passed", drawn)
        self.assertIn("Canonical package digests", drawn)
        self.assertIn("No approved registry state has been written", drawn)

    def test_screen_45_names_the_exact_write_and_that_it_never_pushes(self) -> None:
        ready = project_maintainer_registry_commit(self.prepared)
        drawn = "\n".join(render_maintainer_registry_commit(ready, PresentationProfile.FAST))

        self.assertFalse(ready.applied)
        self.assertIn("Ready to write approved registry state", drawn)
        self.assertIn("Git push: no", drawn)
        self.assertIn("Enter commits this exact local transaction", drawn)

        completed = CandidatePromotionExecutionResult(
            self.prepared.review_digest,
            self.prepared.registry_snapshot,
            self.prepared.plan.next_workspace_digest,
            self.prepared.plan.changed_paths,
            self.prepared.approved_version_count,
            "c" * 40,
            "Promote mcp/github-mcp@1.0.0 to company",
        )
        applied = project_maintainer_registry_commit(self.prepared, result=completed)
        persisted = "\n".join(render_maintainer_registry_commit(applied, PresentationProfile.FAST))
        self.assertTrue(applied.applied)
        self.assertIn("Approved registry state written locally", persisted)


if __name__ == "__main__":
    unittest.main()
