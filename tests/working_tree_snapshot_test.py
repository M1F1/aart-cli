"""An author's checkout is read as Git sees it, so local clutter never reaches a Source.

`source-local`, `author check`, `registry scan` and `registry promote --checkout` read the author's
own directory. When that directory is in a Git work tree, the files Git would commit are the
Source: tracked files plus untracked ones `.gitignore` does not exclude. A virtual environment, a
cache or an editor directory the author ignores is not part of it, so its symlinks and size are
not the author's problem. A directory outside Git is read whole, exactly as before, and the
bounded, symlink-refusing reader still guards every file that is read.
"""

from __future__ import annotations

import os
import string
import subprocess
import tempfile
import unittest
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.io.working_tree import read_working_tree
from aart_cli.sources.local import read_local_snapshot
from aart_cli.sources.model import LocalSnapshotRequest, SnapshotLimits, SourceInstanceId


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(root),
            "GIT_AUTHOR_NAME": "Author",
            "GIT_AUTHOR_EMAIL": "author@example.invalid",
            "GIT_COMMITTER_NAME": "Author",
            "GIT_COMMITTER_EMAIL": "author@example.invalid",
        },
    )


def _request(root: Path, **limits: int) -> LocalSnapshotRequest:
    return LocalSnapshotRequest(
        SourceInstanceId("local-" + "d" * 32),
        SourceAlias("authors"),
        os.path.realpath(root),
        SnapshotLimits(**limits),
    )


def _files(result: object) -> set[str]:
    assert isinstance(result, Ok), result
    return {
        str(entry.path) for entry in result.value.snapshot.entries if entry.kind.value == "file"
    }


def _repository(root: Path) -> None:
    _git(root, "init", "-q")
    (root / "skill").mkdir()
    (root / "skill" / "aart-cli.yaml").write_text("schema: x\n")
    (root / "skill" / "SKILL.md").write_text("# Skill\n")
    (root / ".gitignore").write_text(".venv/\n__pycache__/\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")


def _virtual_environment(root: Path) -> None:
    bin_directory = root / ".venv" / "bin"
    bin_directory.mkdir(parents=True)
    (bin_directory / "python").symlink_to("/usr/bin/python3")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"\0" * 64)


class WorkingTreeSnapshotTest(unittest.TestCase):
    def test_an_ignored_virtual_environment_is_not_part_of_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _repository(root)
            _virtual_environment(root)

            self.assertIsInstance(read_local_snapshot(_request(root)), Err)
            self.assertEqual(
                _files(read_working_tree(_request(root))),
                {".gitignore", "skill/aart-cli.yaml", "skill/SKILL.md"},
            )

    def test_a_new_untracked_manifest_is_part_of_the_source(self) -> None:
        """An author who has not yet run `git add` still sees the artifact they just wrote."""

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _repository(root)
            (root / "guide").mkdir()
            (root / "guide" / "aart-cli.yaml").write_text("schema: y\n")

            self.assertIn("guide/aart-cli.yaml", _files(read_working_tree(_request(root))))

    def test_a_tracked_file_reads_its_working_tree_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _repository(root)
            (root / "skill" / "SKILL.md").write_text("# Edited\n")
            result = read_working_tree(_request(root))
            assert isinstance(result, Ok)
            content = {str(entry.path): entry.content for entry in result.value.snapshot.entries}
            self.assertEqual(content["skill/SKILL.md"], b"# Edited\n")

    def test_a_tracked_file_deleted_from_the_working_tree_is_gone(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _repository(root)
            (root / "skill" / "SKILL.md").unlink()

            self.assertNotIn("skill/SKILL.md", _files(read_working_tree(_request(root))))

    def test_a_symlink_git_would_commit_is_still_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _repository(root)
            (root / "skill" / "link").symlink_to("SKILL.md")

            failed = read_working_tree(_request(root))
            assert isinstance(failed, Err)
            self.assertIn("symlinks are forbidden: skill/link", failed.diagnostics[0].message)

    def test_ignored_files_do_not_count_against_the_limits(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _repository(root)
            (root / "__pycache__").mkdir()
            for index in range(5):
                (root / "__pycache__" / f"{index}.pyc").write_bytes(b"x")

            self.assertIsInstance(read_working_tree(_request(root, max_files=3)), Ok)
            self.assertIsInstance(read_local_snapshot(_request(root, max_files=3)), Err)

    def test_a_subdirectory_of_a_repository_is_read_relative_to_itself(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _repository(root)
            (root / "skill" / ".venv").mkdir()
            (root / "skill" / ".venv" / "python").symlink_to("/usr/bin/python3")

            self.assertEqual(
                _files(read_working_tree(_request(root / "skill"))),
                {"aart-cli.yaml", "SKILL.md"},
            )

    def test_a_directory_outside_git_is_read_whole_as_before(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "aart-cli.yaml").write_text("schema: x\n")
            (root / "notes.txt").write_text("n\n")
            self.assertEqual(read_working_tree(_request(root)), read_local_snapshot(_request(root)))
            (root / "link").symlink_to("notes.txt")
            self.assertIsInstance(read_working_tree(_request(root)), Err)


_NAME = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6)


class WorkingTreeSnapshotPropertyTest(unittest.TestCase):
    @settings(max_examples=25, deadline=None)
    @given(
        kept=st.sets(_NAME, min_size=1, max_size=5),
        ignored=st.sets(_NAME, max_size=5),
    )
    def test_the_source_is_exactly_what_git_would_commit(
        self, kept: set[str], ignored: set[str]
    ) -> None:
        ignored = ignored - kept
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _git(root, "init", "-q")
            (root / ".gitignore").write_text("".join(f"/{name}.ignored\n" for name in ignored))
            for name in kept:
                (root / f"{name}.kept").write_text(name)
            for name in ignored:
                (root / f"{name}.ignored").symlink_to("/usr/bin/python3")

            self.assertEqual(
                _files(read_working_tree(_request(root))),
                {".gitignore", *(f"{name}.kept" for name in kept)},
            )


if __name__ == "__main__":
    unittest.main()
