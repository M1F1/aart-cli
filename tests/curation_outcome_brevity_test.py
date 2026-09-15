"""A confirmed Maintainer action states its result once.

`QA-014`/`B-088`. A confirmed `registry init` printed its review and then its outcome, and the two
overlapped: every warning appeared twice, `observed: 6 review paths` restated the headline that had
just counted the same six, and the first follow-up command listed all six paths a third time. The
operator's question after a mutation is whether it worked and what to do next, and fifteen lines of
mostly-repeated text answer it worse than five.

Nothing is hidden from the record: `--json` still carries the review and the outcome in full, and
what the human path drops is only what the same run already printed.
"""

from __future__ import annotations

import unittest

from agent_artifacts.curation.model import (
    CurationAction,
    CurationChange,
    CurationCheck,
    CurationOutcome,
    CurationReview,
    render_curation_outcome,
)
from agent_artifacts.curation.runtime import _follow_up
from agent_artifacts.domain.identifiers import ObjectDigest

DIGEST = ObjectDigest("sha256", "a" * 64)


def _review(*warnings: str) -> CurationReview:
    return CurationReview(
        action=CurationAction.INIT,
        workspace="/tmp/registry",
        mutating=True,
        review_digest=DIGEST,
        snapshot_digest=ObjectDigest("sha256", "b" * 64),
        changes=(CurationChange("aart-registry.json", "added"),),
        warnings=warnings,
    )


def _outcome(*warnings: str, changed: int = 1, observed: int = 0) -> CurationOutcome:
    return CurationOutcome(
        action=CurationAction.INIT,
        status="succeeded",
        changed_paths=changed,
        observed_paths=observed,
        warnings=warnings,
    )


class ConfirmedOutcomeBrevityTest(unittest.TestCase):
    def test_a_warning_the_review_already_stated_is_not_stated_again(self) -> None:
        warning = "registry CI runs AART 1.0.0, pinned in .aart-version"

        rendered = render_curation_outcome(_outcome(warning), reviewed=_review(warning))

        self.assertEqual(tuple(line for line in rendered if "warning:" in line), ())

    def test_a_warning_the_review_did_not_state_is_still_stated(self) -> None:
        rendered = render_curation_outcome(
            _outcome("the finalized tree differs from the reviewed plan"),
            reviewed=_review("registry CI runs AART 1.0.0"),
        )

        self.assertEqual(
            tuple(line for line in rendered if "warning:" in line),
            ("  warning: the finalized tree differs from the reviewed plan",),
        )

    def test_without_a_review_every_warning_is_stated(self) -> None:
        """`--check` and the unconfirmed path render an outcome no review preceded."""

        rendered = render_curation_outcome(_outcome("one", "two"))

        self.assertEqual(
            tuple(line for line in rendered if "warning:" in line),
            ("  warning: one", "  warning: two"),
        )

    def test_an_observed_count_equal_to_the_headline_is_not_repeated(self) -> None:
        rendered = render_curation_outcome(_outcome(changed=6, observed=6))

        self.assertIn("Changed 6 managed paths.", rendered[0])
        self.assertEqual(tuple(line for line in rendered if "observed:" in line), ())

    def test_an_observed_count_that_differs_is_the_whole_point_of_the_line(self) -> None:
        """A read-only action changes nothing and observes drift; that difference is the finding."""

        rendered = render_curation_outcome(
            CurationOutcome(CurationAction.DIFF, "succeeded", 0, observed_paths=2)
        )

        self.assertIn("  observed: 2 review paths", rendered)

    def test_checks_are_still_rendered_beside_a_review(self) -> None:
        rendered = render_curation_outcome(
            CurationOutcome(
                CurationAction.VALIDATE,
                "failed",
                0,
                checks=(CurationCheck("registry", False, ("error: evidence is stale",)),),
            ),
            reviewed=_review(),
        )

        self.assertIn("  check registry: failed", rendered)
        self.assertIn("    error: evidence is stale", rendered)


class FollowUpCommandTest(unittest.TestCase):
    def test_the_follow_up_commands_are_the_aart_pipeline_and_nothing_else(self) -> None:
        """The `git diff` line re-listed every reviewed path and directed nothing new.

        `render_curation_review` already ends a mutating action with "AART will not commit or push;
        review the working-tree diff afterward", which is the same instruction without the
        repetition — and without a shell command, which screen 46 must never show (`QA-017`).
        """

        commands = _follow_up(
            "/tmp/registry",
            (
                CurationChange("aart-registry.json", "added"),
                CurationChange("aart-source.json", "added"),
            ),
            CurationAction.INIT,
        )

        self.assertEqual(
            commands,
            (
                "aart registry validate --source /tmp/registry",
                "aart registry lock --source /tmp/registry",
                "aart registry build --source /tmp/registry",
                "aart registry audit --source /tmp/registry",
            ),
        )

    def test_an_action_with_generated_evidence_still_asks_for_strict_validation(self) -> None:
        commands = _follow_up(
            "/tmp/registry",
            (CurationChange("aart-registry.json", "changed"),),
            CurationAction.FORMAT,
        )

        self.assertEqual(
            commands,
            (
                "aart registry validate --source /tmp/registry --strict",
                "aart registry audit --source /tmp/registry",
            ),
        )


if __name__ == "__main__":
    unittest.main()
