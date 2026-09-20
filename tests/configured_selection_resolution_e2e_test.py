"""Configured registry snapshots resolve Selection through their approved version records.

The legacy browse catalog is evidence of what a source contains, not proof that a version crossed
the CP-05 approval/publication boundary.  This adapter must recover the real Candidate and registry
snapshot identities from ``registry/versions/*`` and must never synthesize them from a TUI row.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from typing import cast

from aart_cli.application.promotion import (
    PromotionEvidence,
    plan_registry_lifecycle,
    project_lifecycle_update,
    project_promotion,
)
from aart_cli.configuration.model import SourceKind
from aart_cli.domain.candidates import CandidateId
from aart_cli.domain.identifiers import ArtifactIdentity, SourceId
from aart_cli.domain.registry import (
    PublicationStage,
    RegistryArtifactVersion,
    publish_registry_version,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    VersionConstraint,
)
from aart_cli.io.configured_selection import resolve_configured_selection
from aart_cli.io.source_store import publish_source_snapshot
from aart_cli.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from aart_cli.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.promotion_planning_test import _evidence, _ready_bundle


def _approved_snapshot(*, published: bool) -> tuple[SourceSnapshot, RegistryArtifactVersion]:
    bundle = _ready_bundle()
    from aart_cli.application.promotion import plan_bulk_promotion

    empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
    evidence = cast(tuple[tuple[CandidateId, PromotionEvidence], ...], _evidence(bundle))
    planned = plan_bulk_promotion(empty, (bundle,), evidence=evidence, approved=())
    assert isinstance(planned, Ok), planned
    projected = project_promotion(empty, planned.value)
    assert isinstance(projected, Ok), projected
    version = planned.value.versions[0]
    if published:
        public = publish_registry_version(version, version.registry_snapshot)
        lifecycle = plan_registry_lifecycle(projected.value, (version,), (public,))
        assert isinstance(lifecycle, Ok), lifecycle
        updated = project_lifecycle_update(projected.value, lifecycle.value)
        assert isinstance(updated, Ok), updated
        projected = updated
        version = public
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, projected.value.entries), version


class ConfiguredSelectionResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_root = temporary.name
        self.source = configured_source("company", SourceKind.REGISTRY_GIT)
        self.effective = effective_configuration((self.source,), default_registry="company")

    def _publish(self, snapshot: SourceSnapshot) -> None:
        candidate = make_source_candidate(
            source_instance_id(self.source),
            self.source.alias,
            "a" * 40,
            snapshot,
        )
        assert isinstance(candidate, Ok), candidate
        written = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(self.source)),
                ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
                90,
            )
        )
        self.assertIsInstance(written, Ok, getattr(written, "diagnostics", ()))

    def _selection(self) -> ArtifactSelection:
        return ArtifactSelection(
            (
                ArtifactRequest(
                    ArtifactIdentity("mcp", "github-mcp"),
                    VersionConstraint("*"),
                    self.source.alias,
                ),
            )
        )

    def test_a_published_version_resolves_with_its_real_approval_identity(self) -> None:
        snapshot, version = _approved_snapshot(published=True)
        self._publish(snapshot)

        resolved = resolve_configured_selection(
            self.effective,
            self._selection(),
            data_root=self.data_root,
        )

        self.assertIsInstance(resolved, Ok, getattr(resolved, "diagnostics", ()))
        assert isinstance(resolved, Ok)
        self.assertEqual(len(resolved.value.artifacts), 1)
        actual = resolved.value.artifacts[0].version
        self.assertEqual(actual, version)
        self.assertEqual(actual.publication, PublicationStage.PUBLISHED)
        self.assertEqual(actual.candidate_id, version.candidate_id)
        self.assertEqual(actual.registry_snapshot, version.registry_snapshot)
        self.assertEqual(actual.canonical_digest, version.canonical_digest)

    def test_the_branch_the_consumer_reads_publishes_what_it_carries_without_rewriting_it(
        self,
    ) -> None:
        """The record a maintainer wrote stays as written; the reading is what changed (D-207).

        Publication is presence on the canonical consumer-visible branch (INV-242), and this
        snapshot is the one this consumer synchronized. Refusing it would be waiting for a write
        that the accepted promote → commit → review → merge workflow never performs (`QA-034`).
        """

        snapshot, version = _approved_snapshot(published=False)
        self._publish(snapshot)

        resolved = resolve_configured_selection(
            self.effective,
            self._selection(),
            data_root=self.data_root,
        )

        self.assertIsInstance(resolved, Ok, getattr(resolved, "diagnostics", ()))
        assert isinstance(resolved, Ok)
        self.assertEqual(version.publication, PublicationStage.PROMOTED_LOCAL)
        self.assertEqual(
            resolved.value.artifacts[0].version,
            replace(version, publication=PublicationStage.PUBLISHED),
        )

    def test_an_artifact_the_branch_does_not_carry_is_still_not_found(self) -> None:
        """Nothing about publication loosens what a snapshot has to actually contain."""

        snapshot, _ = _approved_snapshot(published=False)
        self._publish(snapshot)

        resolved = resolve_configured_selection(
            self.effective,
            ArtifactSelection(
                (
                    ArtifactRequest(
                        ArtifactIdentity("mcp", "absent-mcp"),
                        VersionConstraint("*"),
                        self.source.alias,
                    ),
                )
            ),
            data_root=self.data_root,
        )

        self.assertIsInstance(resolved, Err)
        assert isinstance(resolved, Err)
        self.assertEqual(resolved.diagnostics[0].code.value, "artifact-not-found")


if __name__ == "__main__":
    unittest.main()
