from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.source_store import publish_source_snapshot, read_current_source
from agent_artifacts.protocol.capabilities import parse_capability
from agent_artifacts.protocol.semver import parse_semver
from agent_artifacts.sources.git import acquire_git_snapshot
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    GitSnapshotRequest,
    SnapshotLimits,
    SourceInstanceId,
    SourcePublishCommand,
    SourceValidationRequest,
    source_store_paths,
)
from agent_artifacts.sources.validation import validate_source_candidate

_FIXTURE = Path(__file__).parent / "fixtures" / "protocol" / "native-source-v1"
_INSTANCE_ID = SourceInstanceId("git-" + "d" * 32)
_ALIAS = SourceAlias("reference")


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _unwrap(result):
    assert isinstance(result, Ok), result
    return result.value


class GitSourcePublicationE2ETest(unittest.TestCase):
    """The real Git adapter's output is the source store's exact publication input."""

    def _repository(self, root: Path) -> Path:
        repository = root / "repository"
        shutil.copytree(_FIXTURE, repository)
        _git("init", "-b", "main", str(repository))
        _git("-C", str(repository), "config", "user.email", "test@example.invalid")
        _git("-C", str(repository), "config", "user.name", "AART Test")
        _git("-C", str(repository), "add", ".")
        _git("-C", str(repository), "commit", "-m", "initial")
        return repository

    def _acquire_and_publish(self, root: Path, repository: Path, observed_at: int):
        paths = source_store_paths(str(root / "data"), _INSTANCE_ID)
        acquired = acquire_git_snapshot(
            GitSnapshotRequest(
                _INSTANCE_ID,
                _ALIAS,
                repository.as_uri(),
                "main",
                paths.mirror,
                paths.temporary_root,
                SnapshotLimits(),
                30,
                allow_local_transport=True,
            )
        )
        candidate = _unwrap(acquired)
        validated = _unwrap(
            validate_source_candidate(
                SourceValidationRequest(
                    candidate,
                    _unwrap(parse_semver("1.0.0")),
                    (_unwrap(parse_capability("artifact-manifest-v1")),),
                )
            )
        )
        published = _unwrap(
            publish_source_snapshot(SourcePublishCommand(paths, validated, observed_at))
        )
        return paths, candidate, published

    def test_real_resolved_commit_and_snapshot_entries_round_trip_through_a_fresh_reader(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = self._repository(root)
            head = _git("-C", str(repository), "rev-parse", "HEAD")

            paths, candidate, published = self._acquire_and_publish(root, repository, 100)
            loaded = _unwrap(read_current_source(CurrentSourceRequest(paths, _ALIAS)))

            self.assertNotEqual(head, "a" * 40)
            self.assertIs(published.created, True)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(candidate.resolved_revision, head)
            self.assertEqual(published.current.candidate, candidate)
            self.assertEqual(loaded.candidate, candidate)

    def test_an_unmoved_remote_converges_and_its_next_commit_becomes_current(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = self._repository(root)
            paths, first, first_publication = self._acquire_and_publish(root, repository, 100)
            snapshots_before = tuple(sorted(Path(paths.snapshots).iterdir()))

            _, unchanged, second_publication = self._acquire_and_publish(root, repository, 200)

            self.assertEqual(unchanged.resolved_revision, first.resolved_revision)
            self.assertIs(second_publication.created, False)
            self.assertEqual(tuple(sorted(Path(paths.snapshots).iterdir())), snapshots_before)

            readme = repository / "README.md"
            readme.write_text("second revision\n", encoding="utf-8")
            _git("-C", str(repository), "add", "README.md")
            _git("-C", str(repository), "commit", "-m", "second")
            second_head = _git("-C", str(repository), "rev-parse", "HEAD")

            _, moved, third_publication = self._acquire_and_publish(root, repository, 300)
            loaded = _unwrap(read_current_source(CurrentSourceRequest(paths, _ALIAS)))

            self.assertNotEqual(second_head, first.resolved_revision)
            self.assertIs(first_publication.created, True)
            self.assertIs(third_publication.created, True)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(moved.resolved_revision, second_head)
            self.assertEqual(third_publication.current.candidate, moved)
            self.assertEqual(loaded.candidate, moved)


if __name__ == "__main__":
    unittest.main()
