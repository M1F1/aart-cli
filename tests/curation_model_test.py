from __future__ import annotations

import unittest

from aart_cli.curation.model import (
    CurationAction,
    CurationChange,
    CurationCheck,
    CurationOutcome,
    CurationRequest,
    CurationReview,
    render_curation_outcome,
    render_curation_review,
)
from aart_cli.domain.identifiers import ObjectDigest


class CurationModelTest(unittest.TestCase):
    def test_request_requires_a_normalized_absolute_workspace(self) -> None:
        with self.assertRaises(ValueError):
            CurationRequest(CurationAction.VALIDATE, "relative")

    def test_invalid_change_review_check_and_outcome_values_fail_closed(self) -> None:
        digest = ObjectDigest("sha256", "a" * 64)
        for build in (
            lambda: CurationChange("../outside", "changed"),
            lambda: CurationCheck("Bad Name", True),
            lambda: CurationReview(
                CurationAction.DIFF,
                "/tmp/registry",
                False,
                ObjectDigest("sha256", "bad"),
                digest,
            ),
            lambda: CurationOutcome(CurationAction.AUDIT, "failed", 1),
        ):
            with self.subTest(build=build):
                with self.assertRaises(ValueError):
                    build()

    def test_review_and_outcome_render_exact_evidence_and_follow_up(self) -> None:
        digest = ObjectDigest("sha256", "a" * 64)
        review = CurationReview(
            action=CurationAction.COLLECTION,
            workspace="/tmp/registry",
            mutating=True,
            review_digest=digest,
            snapshot_digest=ObjectDigest("sha256", "b" * 64),
            changes=(CurationChange("collections/demo.json", "added"),),
            checks=(CurationCheck("registry", True),),
            warnings=("Review generated starter content.",),
            follow_up_commands=("aart-cli registry validate --source /tmp/registry --strict",),
        )
        rendered = "\n".join(render_curation_review(review))
        self.assertIn("collection", rendered)
        self.assertIn("collections/demo.json", rendered)
        self.assertIn(str(digest), rendered)
        self.assertIn(
            "AART will not commit or push; review the working-tree diff afterward.", rendered
        )
        self.assertNotIn("Finalizing publish", rendered)

        outcome = CurationOutcome(
            action=CurationAction.COLLECTION,
            status="succeeded",
            changed_paths=1,
            follow_up_commands=review.follow_up_commands,
        )
        summary = "\n".join(render_curation_outcome(outcome))
        self.assertIn("Changed 1 managed path", summary)
        self.assertIn("aart-cli registry validate", summary)

        failed = CurationOutcome(
            CurationAction.AUDIT,
            "failed",
            0,
            checks=(CurationCheck("audit", False, ("error: evidence is stale",)),),
        )
        self.assertIn("failed", "\n".join(render_curation_outcome(failed)))
        self.assertIn(
            "no changes were required",
            "\n".join(
                render_curation_outcome(CurationOutcome(CurationAction.REVENDOR, "no-op", 0))
            ),
        )
        self.assertIn(
            "completed read-only",
            "\n".join(
                render_curation_outcome(
                    CurationOutcome(CurationAction.DIFF, "succeeded", 0, observed_paths=2)
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
