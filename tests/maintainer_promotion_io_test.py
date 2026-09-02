"""The concrete promotion Git adapter owns only the exact reviewed local commit."""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

from agent_artifacts.application.maintainer_promotion import CandidatePromotionCommitCommand
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.result import Err
from agent_artifacts.io.maintainer_promotion import commit_candidate_promotion
from agent_artifacts.protocol.paths import SafeRelativePath


def _git(root: pathlib.Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


class CandidatePromotionGitCommitTest(unittest.TestCase):
    def test_an_existing_staged_change_is_refused_without_staging_reviewed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            _git(root, "init", "-b", "main")
            _git(root, "config", "user.name", "AART Test")
            _git(root, "config", "user.email", "aart@example.invalid")
            reviewed = root / "reviewed.json"
            unrelated = root / "unrelated.json"
            reviewed.write_text("old\n", encoding="utf-8")
            unrelated.write_text("old\n", encoding="utf-8")
            _git(root, "add", "reviewed.json", "unrelated.json")
            _git(root, "commit", "-m", "Initial registry")
            initial = _git(root, "rev-parse", "HEAD")

            reviewed.write_text("promoted\n", encoding="utf-8")
            unrelated.write_text("user change\n", encoding="utf-8")
            _git(root, "add", "unrelated.json")
            completed = commit_candidate_promotion(
                str(root),
                CandidatePromotionCommitCommand(
                    ObjectDigest("sha256", "a" * 64),
                    "Promote example@1.0.0 to company",
                    (SafeRelativePath(("reviewed.json",)),),
                ),
            )

            assert isinstance(completed, Err), completed
            self.assertIn("already contains changes", completed.diagnostics[0].message)
            self.assertEqual(_git(root, "rev-parse", "HEAD"), initial)
            self.assertEqual(_git(root, "diff", "--cached", "--name-only"), "unrelated.json")


if __name__ == "__main__":
    unittest.main()
