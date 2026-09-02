from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_artifacts import tui
from agent_artifacts.curation.model import (
    CurationChange,
    CurationOutcome,
    CurationReview,
)
from agent_artifacts.curation.runtime import PreparedCuration
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot


def _action_index(name):
    return [action for action, _label in tui.CANONICAL_MAINTAINER_ACTIONS].index(name)


def _scripted(values):
    answers = iter(values)

    def read(_prompt=""):
        return next(answers)

    return read


class _Service:
    def __init__(self):
        self.prepared = []
        self.finalized = []

    def prepare(self, request):
        self.prepared.append(request)
        review = CurationReview(
            request.action,
            request.workspace,
            True,
            ObjectDigest("sha256", "a" * 64),
            ObjectDigest("sha256", "b" * 64),
            (CurationChange("artifacts/skill/demo/artifact.json", "added"),),
            follow_up_commands=("git -C /registry diff -- artifacts/skill/demo",),
        )
        return Ok(PreparedCuration(review, SourceSnapshot(SnapshotOrigin.LOCAL, ())))

    def finalize(self, prepared, reviewed_digest):
        self.finalized.append((prepared, reviewed_digest))
        return Ok(
            CurationOutcome(
                prepared.review.action,
                "succeeded",
                1,
                follow_up_commands=prepared.review.follow_up_commands,
            )
        )


class TuiCurationTest(unittest.TestCase):
    def test_canonical_action_menu_explains_security_and_no_commit_push_boundary(self) -> None:
        labels = "\n".join(label for _action, label in tui.CANONICAL_MAINTAINER_ACTIONS)
        self.assertIn("security", labels.lower())
        self.assertIn("diff", labels.lower())
        self.assertIn("commit", labels.lower())
        self.assertIn("push", labels.lower())


class WorkspaceClassificationTest(unittest.TestCase):
    """A workspace is a registry only when it says so (DESIGN §3.2)."""

    def test_an_empty_git_checkout_is_not_classified_as_a_registry(self) -> None:
        # Inferring the maintainer role from "looks like a repository" is what sent a consumer
        # into registry curation during live acceptance. Only the explicit current marker counts.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".git").mkdir()

            self.assertFalse(tui._is_canonical_maintainer_workspace(str(root)))

    def test_a_directory_with_the_current_registry_marker_is_a_maintainer_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "aart-registry.json").write_text("{}", encoding="utf-8")

            self.assertTrue(tui._is_canonical_maintainer_workspace(str(root)))

    def test_a_retired_registry_marker_does_not_classify_the_workspace(self) -> None:
        # A retired marker is not translated into the current one; it simply is not a registry.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "registry.json").write_text("{}", encoding="utf-8")
            (root / "catalog.json").write_text("{}", encoding="utf-8")

            self.assertFalse(tui._is_canonical_maintainer_workspace(str(root)))


if __name__ == "__main__":
    unittest.main()
