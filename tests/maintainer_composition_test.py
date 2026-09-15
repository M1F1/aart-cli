"""CP-14 production reader composes Source health and durable Candidate history once."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.identifiers import SourceId
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.candidate_store import candidate_history_paths, write_candidate_history
from agent_artifacts.io.maintainer_views import read_maintainer_views
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import SafeRelativePath
from agent_artifacts.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.candidate_history_test import _ready_scan
from tests.maintainer_collection_history_test import _scan as _collection_scan
from tests.marketplace_fixtures import configured_source, effective_configuration


def _snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        SnapshotOrigin.IMMUTABLE_GIT,
        (
            SnapshotEntry(
                SafeRelativePath(("aart-source.json",)),
                SnapshotEntryKind.FILE,
                b'{"schema_version":1}',
            ),
        ),
    )


class MaintainerCompositionTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_root = str(Path(temporary.name) / "data")
        self.authors = configured_source("authors", SourceKind.SOURCE_GIT)
        self.registry = configured_source("company", SourceKind.REGISTRY_GIT)
        self.effective = effective_configuration(
            (self.registry, self.authors), default_registry="company"
        )

    def _publish(self, revision: str = "a" * 40) -> None:
        candidate = make_source_candidate(
            source_instance_id(self.authors),
            self.authors.alias,
            revision,
            _snapshot(),
        )
        assert isinstance(candidate, Ok)
        published = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(self.authors)),
                ValidatedSourceCandidate(candidate.value, SourceId("author-source")),
                int(time.time()),
            )
        )
        self.assertIsInstance(published, Ok)

    def _write_scan(self) -> None:
        source_paths = source_store_paths(self.data_root, source_instance_id(self.authors))
        written = write_candidate_history(candidate_history_paths(source_paths), _ready_scan())
        self.assertIsInstance(written, Ok)

    def _write_collection_scan(self) -> None:
        source_paths = source_store_paths(self.data_root, source_instance_id(self.authors))
        written = write_candidate_history(
            candidate_history_paths(source_paths),
            _collection_scan("a" * 40),
        )
        self.assertIsInstance(written, Ok)

    def test_reader_projects_only_authoring_sources_with_matching_history(self) -> None:
        self._publish()
        self._write_scan()

        composed = read_maintainer_views(self.effective, data_root=self.data_root)

        self.assertIsInstance(composed, Ok)
        assert isinstance(composed, Ok)
        self.assertEqual([source.alias for source in composed.value.sources], ["authors"])
        self.assertEqual(composed.value.dashboard.source_count, 1)
        self.assertEqual(composed.value.dashboard.candidate_count, 1)
        self.assertEqual(composed.value.dashboard.ready_count, 1)

    def test_missing_history_is_an_unscanned_source_not_a_reader_failure(self) -> None:
        self._publish()

        composed = read_maintainer_views(self.effective, data_root=self.data_root)

        self.assertIsInstance(composed, Ok)
        assert isinstance(composed, Ok)
        self.assertEqual(composed.value.sources[0].candidate_count, 0)

    def test_reader_composes_durable_collection_candidate_and_unavailable_validation(self) -> None:
        self._publish()
        self._write_collection_scan()

        composed = read_maintainer_views(self.effective, data_root=self.data_root)

        self.assertIsInstance(composed, Ok)
        assert isinstance(composed, Ok)
        self.assertEqual(composed.value.dashboard.candidate_count, 1)
        self.assertEqual(len(composed.value.collection_candidates or ()), 1)
        collection = (composed.value.collection_candidates or ())[0]
        self.assertEqual(collection.coordinate, "company/collection/data-engineer@2.1.0")
        validation = composed.value.collection_validation(collection.candidate_id)
        assert validation is not None
        self.assertEqual(validation.outcome, "unavailable")

    def test_corrupt_history_refuses_instead_of_projecting_zero_candidates(self) -> None:
        self._publish()
        paths = candidate_history_paths(
            source_store_paths(self.data_root, source_instance_id(self.authors))
        )
        Path(paths.root).mkdir(parents=True)
        Path(paths.index_file).write_bytes(b"corrupt")

        composed = read_maintainer_views(self.effective, data_root=self.data_root)

        self.assertIsInstance(composed, Err)

    def test_history_from_the_previous_pinned_revision_refuses_composition(self) -> None:
        self._publish("b" * 40)
        self._write_scan()

        composed = read_maintainer_views(self.effective, data_root=self.data_root)

        self.assertIsInstance(composed, Err)


if __name__ == "__main__":
    unittest.main()
