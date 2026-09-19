"""CP-14 production reader composes Source health and durable Candidate history once."""

from __future__ import annotations

import dataclasses
import tempfile
import time
import unittest
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.maintainer import CandidateBundle, reconcile_source_scan
from aart_cli.application.maintainer_views import (
    UNBOUND_SCAN_DIAGNOSTIC,
    MaintainerSourceStatus,
)
from aart_cli.configuration.model import SourceKind
from aart_cli.domain.candidates import assess_candidate
from aart_cli.domain.identifiers import SourceAlias, SourceId
from aart_cli.domain.result import Err, Ok
from aart_cli.io.candidate_store import candidate_history_paths, write_candidate_history
from aart_cli.io.maintainer_views import read_maintainer_views
from aart_cli.io.source_store import publish_source_snapshot
from aart_cli.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from aart_cli.protocol.paths import SafeRelativePath
from aart_cli.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.candidate_history_test import _compiled, _ready_scan
from tests.maintainer_collection_history_test import _scan as _collection_scan
from tests.marketplace_fixtures import configured_source, effective_configuration


def _ready_scan_at(digit: str):
    """`_ready_scan` at another revision: a Scan carries it in its compiled Candidates too."""

    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        digit * 40,
        _compiled(revision=digit),
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok)
    active = scanned.value.active[0]
    ready = CandidateBundle(assess_candidate(active.candidate), active.artifact)
    return dataclasses.replace(scanned.value, active=(ready,), history=(ready,))


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
        self._publish_source(self.authors, revision)

    def _publish_source(self, source, revision: str, *, data_root: str | None = None) -> None:
        candidate = make_source_candidate(
            source_instance_id(source),
            source.alias,
            revision,
            _snapshot(),
        )
        assert isinstance(candidate, Ok)
        published = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(
                    self.data_root if data_root is None else data_root,
                    source_instance_id(source),
                ),
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

    def test_history_from_the_previous_pinned_revision_reads_as_needing_a_sync(self) -> None:
        """CP-24.01: one inconsistent Source must not take the whole local state down.

        Issue #8: the reader refused every view with `maintainer-composition-invalid`, so a single
        Source whose stored scan predates its pin hid every other Source, every Candidate and every
        Registry -- and the only recovery was deleting the history by hand. The scan is not
        Candidate data for this pin, so it is not projected as any; the Source says so and names
        the remedy.
        """

        self._publish("b" * 40)
        self._write_scan()

        composed = read_maintainer_views(self.effective, data_root=self.data_root)

        self.assertIsInstance(composed, Ok)
        assert isinstance(composed, Ok)
        source = composed.value.sources[0]
        self.assertEqual(source.status, MaintainerSourceStatus.ATTENTION)
        self.assertEqual(source.candidate_count, 0)
        self.assertEqual(composed.value.dashboard.candidate_count, 0)
        self.assertEqual(
            source.diagnostics,
            (
                "Candidate history was recorded at another revision than the pinned snapshot; "
                "run Source Sync on this Source to rebuild it from the pinned snapshot",
            ),
        )

    # Revisions are drawn as one hex digit repeated, because what the claim quantifies over is the
    # pair, not the alphabet -- and `same` makes sure both halves of the pair are actually drawn
    # rather than left to the odds of two independent draws colliding.
    # `differing_executors` is suppressed for the same reason the other property suites suppress
    # it: `make mutants` runs the suite twice in one process, which is not the flakiness the check
    # is looking for.
    @settings(
        max_examples=25,
        deadline=None,
        suppress_health_check=(HealthCheck.too_slow, HealthCheck.differing_executors),
    )
    @given(
        pinned=st.sampled_from("0123456789abcdef"),
        other=st.sampled_from("0123456789abcdef"),
        same=st.booleans(),
    )
    def test_any_stored_scan_either_binds_the_pin_or_asks_for_a_sync(
        self, pinned: str, other: str, same: bool
    ) -> None:
        """The universal half of CP-24.01: no pair of revisions may make the state unloadable."""

        scanned = pinned if same else other

        with tempfile.TemporaryDirectory() as temporary:
            data_root = str(Path(temporary) / "data")
            self._publish_source(self.authors, pinned * 40, data_root=data_root)
            paths = source_store_paths(data_root, source_instance_id(self.authors))
            written = write_candidate_history(
                candidate_history_paths(paths),
                _ready_scan_at(scanned),
            )
            self.assertIsInstance(written, Ok)

            composed = read_maintainer_views(self.effective, data_root=data_root)

            self.assertIsInstance(composed, Ok)
            assert isinstance(composed, Ok)
            source = composed.value.sources[0]
            if scanned == pinned:
                self.assertEqual(source.candidate_count, 1)
                self.assertNotIn(UNBOUND_SCAN_DIAGNOSTIC, source.diagnostics)
            else:
                self.assertEqual(source.candidate_count, 0)
                self.assertEqual(source.status, MaintainerSourceStatus.ATTENTION)
                self.assertIn(UNBOUND_SCAN_DIAGNOSTIC, source.diagnostics)

    def test_a_collection_candidate_of_an_unbound_scan_is_not_projected_either(self) -> None:
        """The same scan feeds the collection lists, so tolerating it must not leak them."""

        self._publish("b" * 40)
        self._write_collection_scan()

        composed = read_maintainer_views(self.effective, data_root=self.data_root)

        self.assertIsInstance(composed, Ok)
        assert isinstance(composed, Ok)
        self.assertEqual(composed.value.collection_candidates or (), ())
        self.assertEqual(composed.value.dashboard.candidate_count, 0)

    def test_an_unbound_scan_hides_neither_the_other_sources_nor_their_candidates(self) -> None:
        """What the refusal actually cost: every other Source disappeared with it."""

        self._publish("b" * 40)
        self._write_scan()
        second = configured_source("mirrors", SourceKind.SOURCE_GIT)
        effective = effective_configuration(
            (self.registry, self.authors, second), default_registry="company"
        )
        self._publish_source(second, "c" * 40)

        composed = read_maintainer_views(effective, data_root=self.data_root)

        self.assertIsInstance(composed, Ok)
        assert isinstance(composed, Ok)
        self.assertEqual(
            [source.alias for source in composed.value.sources], ["authors", "mirrors"]
        )
        self.assertEqual(composed.value.dashboard.source_count, 2)


if __name__ == "__main__":
    unittest.main()
