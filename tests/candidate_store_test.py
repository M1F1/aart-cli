"""Filesystem persistence for durable CP-14 Candidate lifecycle history."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.candidate_store import (
    candidate_history_paths,
    read_candidate_history,
    write_candidate_history,
)
from agent_artifacts.sources.model import SourceInstanceId, source_store_paths
from tests.candidate_history_test import _ready_scan
from tests.maintainer_source_scan_test import _compiled


def _paths(root: str):
    source = source_store_paths(root, SourceInstanceId("git-" + "a" * 32))
    return candidate_history_paths(source)


class CandidateHistoryStoreTest(unittest.TestCase):
    def test_atomic_private_write_round_trips_exact_history(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = _paths(root)
            scan = _ready_scan()

            written = write_candidate_history(paths, scan)
            loaded = read_candidate_history(paths)

            self.assertIsInstance(written, Ok)
            self.assertEqual(loaded, Ok(scan))
            assert isinstance(written, Ok)
            self.assertEqual(written.value.revision, scan.revision)
            self.assertEqual(os.stat(paths.index_file).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(paths.root).st_mode & 0o777, 0o700)
            object_files = tuple(Path(paths.objects).iterdir())
            self.assertEqual(len(object_files), 1)
            self.assertEqual(os.stat(object_files[0]).st_mode & 0o777, 0o600)
            self.assertEqual(tuple(Path(paths.root).rglob(".stage-*")), ())

    def test_missing_history_is_distinct_from_corrupt_history(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = _paths(root)
            self.assertEqual(read_candidate_history(paths), Ok(None))

            Path(paths.root).mkdir(parents=True)
            Path(paths.index_file).write_bytes(b'{"not":"candidate history"}')
            corrupt = read_candidate_history(paths)

            self.assertIsInstance(corrupt, Err)

    def test_missing_referenced_object_refuses_instead_of_erasing_history(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = _paths(root)
            self.assertIsInstance(write_candidate_history(paths, _ready_scan()), Ok)
            next(Path(paths.objects).iterdir()).unlink()

            loaded = read_candidate_history(paths)

            self.assertIsInstance(loaded, Err)
            assert isinstance(loaded, Err)
            self.assertIn("compiled object is missing", loaded.diagnostics[0].message)

    def test_symlink_cannot_impersonate_candidate_history_directory(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = _paths(root)
            external = Path(root) / "external"
            external.mkdir()
            Path(paths.root).parent.mkdir(parents=True)
            Path(paths.root).symlink_to(external, target_is_directory=True)

            self.assertIsInstance(read_candidate_history(paths), Err)
            self.assertIsInstance(write_candidate_history(paths, _ready_scan()), Err)
            self.assertEqual(tuple(external.iterdir()), ())

    def test_interrupted_index_replace_preserves_last_complete_scan(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = _paths(root)
            first = _ready_scan()
            changed = reconcile_source_scan(
                SourceAlias("authors"),
                "b" * 40,
                _compiled(revision="b", server="print('changed')\n"),
                previous=first.history,
                approved=(),
                target_registry=SourceAlias("company"),
            )
            assert isinstance(changed, Ok)
            self.assertIsInstance(write_candidate_history(paths, first), Ok)

            with patch(
                "agent_artifacts.io.candidate_store.os.replace",
                side_effect=OSError("replace failed"),
            ):
                interrupted = write_candidate_history(paths, changed.value)

            self.assertIsInstance(interrupted, Err)
            self.assertEqual(read_candidate_history(paths), Ok(first))
            self.assertEqual(tuple(Path(paths.root).rglob(".stage-*")), ())

    def test_corrupt_immutable_object_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            paths = _paths(root)
            scan = _ready_scan()
            self.assertIsInstance(write_candidate_history(paths, scan), Ok)
            object_file = next(Path(paths.objects).iterdir())
            object_file.write_bytes(b"corrupt")

            rewritten = write_candidate_history(paths, scan)

            self.assertIsInstance(rewritten, Err)
            self.assertEqual(object_file.read_bytes(), b"corrupt")


if __name__ == "__main__":
    unittest.main()
