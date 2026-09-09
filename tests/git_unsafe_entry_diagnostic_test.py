"""A refused Git entry says what it is and what to do about it.

`QA-019`/`B-093`. The refusal is correct and stays exactly as fail-closed as it was — AART never
follows or materializes an entry it has not reviewed. What it did not do was tell the operator
anything they could act on: a symlink, a submodule, an unreadable mode and an unsafe path all
produced `Git tree contains an unsafe entry: 'AGENTS.md'`, so the one question the operator has —
what do I change in my repository — had no answer in the output.

Each refusal now names the entry kind it observed and carries remediation. The link target is never
printed: it has not passed the repository's path-safety rules, and naming an unreviewed path is the
thing this boundary exists to prevent.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err
from agent_artifacts.sources.git import _tree_listing
from agent_artifacts.sources.model import (
    GitSnapshotRequest,
    SnapshotLimits,
    SourceInstanceId,
)

OBJECT_ID = "a" * 40


def _request(root: str, limits: SnapshotLimits | None = None) -> GitSnapshotRequest:
    return GitSnapshotRequest(
        SourceInstanceId("git-" + "c" * 32),
        SourceAlias("team"),
        "https://example.test/team/repo.git",
        "main",
        str(Path(root) / "mirror.git"),
        str(Path(root) / "tmp"),
        limits or SnapshotLimits(),
        30,
    )


def _refuse(listing: bytes, limits: SnapshotLimits | None = None):
    with tempfile.TemporaryDirectory() as root:
        refused = _tree_listing(listing, _request(root, limits))
    assert isinstance(refused, Err), refused
    return refused.diagnostics[0]


class UnsafeGitEntryDiagnosticTest(unittest.TestCase):
    def test_a_symlink_is_named_as_a_symbolic_link_with_its_path(self) -> None:
        diagnostic = _refuse(f"120000 blob {OBJECT_ID} 12\tAGENTS.md\0".encode())

        self.assertIn("symbolic link", diagnostic.message)
        self.assertIn("AGENTS.md", diagnostic.message)

    def test_a_symlink_refusal_never_names_the_link_target(self) -> None:
        """The target is an unreviewed path, which is exactly what this boundary refuses to read."""

        diagnostic = _refuse(f"120000 blob {OBJECT_ID} 9\tAGENTS.md\0".encode())

        self.assertNotIn("CLAUDE.md", diagnostic.message + " ".join(diagnostic.remediation))

    def test_a_symlink_refusal_offers_a_safe_correction(self) -> None:
        diagnostic = _refuse(f"120000 blob {OBJECT_ID} 12\tAGENTS.md\0".encode())

        remediation = " ".join(diagnostic.remediation)
        self.assertIn("regular file", remediation)
        self.assertTrue(diagnostic.remediation)

    def test_a_submodule_is_named_as_a_submodule_rather_than_malformed(self) -> None:
        """`ls-tree -l` reports `-` for a gitlink's size, which used to read as a broken listing."""

        diagnostic = _refuse(f"160000 commit {OBJECT_ID}       -\tvendor/dep\0".encode())

        self.assertIn("submodule", diagnostic.message)
        self.assertIn("vendor/dep", diagnostic.message)
        self.assertTrue(diagnostic.remediation)

    def test_an_unsafe_path_is_named_as_a_path_rather_than_a_file_kind(self) -> None:
        diagnostic = _refuse(f"100644 blob {OBJECT_ID} 1\t../escape\0".encode())

        self.assertIn("path", diagnostic.message)
        self.assertTrue(diagnostic.remediation)

    def test_an_unreadable_mode_is_named_as_an_unsupported_git_mode(self) -> None:
        diagnostic = _refuse(f"100600 blob {OBJECT_ID} 1\tfile\0".encode())

        self.assertIn("mode", diagnostic.message)
        self.assertIn("file", diagnostic.message)
        self.assertTrue(diagnostic.remediation)

    def test_a_regular_file_and_an_executable_are_still_accepted(self) -> None:
        for mode in ("100644", "100755"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as root:
                    listed = _tree_listing(
                        f"{mode} blob {OBJECT_ID} 1\tfile\0".encode(), _request(root)
                    )

                self.assertNotIsInstance(listed, Err)

    def test_a_depth_refusal_still_names_the_bound_it_exceeded(self) -> None:
        diagnostic = _refuse(
            f"100644 blob {OBJECT_ID} 1\tone/two\0".encode(), SnapshotLimits(max_depth=1)
        )

        self.assertIn("one/two", diagnostic.message)
        self.assertTrue(diagnostic.remediation)

    def test_every_refusal_carries_a_next_step(self) -> None:
        listings = (
            f"120000 blob {OBJECT_ID} 12\tAGENTS.md\0".encode(),
            f"160000 commit {OBJECT_ID}       -\tvendor/dep\0".encode(),
            f"100644 blob {OBJECT_ID} 1\t../escape\0".encode(),
            f"100600 blob {OBJECT_ID} 1\tfile\0".encode(),
        )
        for listing in listings:
            with self.subTest(listing=listing):
                self.assertTrue(_refuse(listing).remediation)


if __name__ == "__main__":
    unittest.main()
