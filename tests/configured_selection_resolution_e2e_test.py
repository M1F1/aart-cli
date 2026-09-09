"""Configured registry snapshots resolve Selection through their approved version records.

The legacy browse catalog is evidence of what a source contains, not proof that a version crossed
the CP-05 approval/publication boundary.  This adapter must recover the real Candidate and registry
snapshot identities from ``registry/versions/*`` and must never synthesize them from a TUI row.
"""

from __future__ import annotations

import tempfile
import unittest
from typing import cast

from agent_artifacts.application.promotion import (
    PromotionEvidence,
    plan_registry_lifecycle,
    project_lifecycle_update,
    project_promotion,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.identifiers import ArtifactIdentity, SourceId
from agent_artifacts.domain.registry import (
    PublicationStage,
    RegistryArtifactVersion,
    publish_registry_version,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    VersionConstraint,
)
from agent_artifacts.io.configured_selection import resolve_configured_selection
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from agent_artifacts.sources.model import (
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
    from agent_artifacts.application.promotion import plan_bulk_promotion

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

    def test_a_local_promotion_is_not_invented_into_a_published_offer(self) -> None:
        snapshot, version = _approved_snapshot(published=False)
        self._publish(snapshot)

        resolved = resolve_configured_selection(
            self.effective,
            self._selection(),
            data_root=self.data_root,
        )

        self.assertIsInstance(resolved, Err)
        assert isinstance(resolved, Err)
        self.assertEqual(version.publication, PublicationStage.PROMOTED_LOCAL)
        self.assertEqual(resolved.diagnostics[0].code.value, "artifact-not-found")


if __name__ == "__main__":
    unittest.main()
