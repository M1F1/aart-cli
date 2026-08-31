"""A configured approved artifact becomes a placed screen-07 draft from durable source state."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import tempfile
import unittest
from typing import cast

from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.application.promotion import (
    PromotionEvidence,
    plan_bulk_promotion,
    plan_registry_lifecycle,
    project_lifecycle_update,
    project_promotion,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.candidates import CandidateId, assess_candidate
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.identifiers import ArtifactIdentity, SourceAlias, SourceId
from agent_artifacts.domain.inputs import PromptedConfigValue, SecretProviderReference
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import publish_registry_version
from agent_artifacts.domain.result import Ok
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    VersionConstraint,
)
from agent_artifacts.io.configured_installation import prepare_configured_installation_draft
from agent_artifacts.io.object_store import read_object
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from agent_artifacts.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from agent_artifacts.store.model import ObjectReadRequest, object_store_paths
from tests.artifact_installation_e2e_test import MANIFEST, ORG, SERVER_SOURCE, TOKEN
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.promotion_planning_test import _entry, _evidence

KEYCHAIN = CredentialProviderRef("macos-keychain", "aart/mcp/github", "default")


#: One MCP server, as an author's repository holds it before anything compiles it.
AUTHORED_MCP: tuple[tuple[str, str], ...] = (
    ("github/aart.json", json.dumps(MANIFEST)),
    ("github/server.py", SERVER_SOURCE),
    ("github/requirements.txt", "# no third-party packages\n"),
)


def _published_registry(authored: tuple[tuple[str, str], ...] = AUTHORED_MCP) -> SourceSnapshot:
    """Take an author's files all the way to a published registry snapshot.

    Every step is the real one -- compile, scan, assess, promote, publish -- because the point of
    the fixture is that what an install resolves is what a registry approved, not a value this test
    handed it. `authored` is a parameter so the same path can carry an artifact a harness reads;
    nothing else about the pipeline changes for one.
    """

    compiled = compile_author_snapshot(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            tuple(_entry(path, content) for path, content in authored),
        ),
        source_alias=SourceAlias("authors"),
        source="https://git.example/servers.git",
        revision="a" * 40,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok), scanned
    bundle = scanned.value.active[0]
    bundle = dataclasses.replace(bundle, candidate=assess_candidate(bundle.candidate))
    evidence = cast(tuple[tuple[CandidateId, PromotionEvidence], ...], _evidence(bundle))
    empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
    promoted = plan_bulk_promotion(empty, (bundle,), evidence=evidence, approved=())
    assert isinstance(promoted, Ok), promoted
    projected = project_promotion(empty, promoted.value)
    assert isinstance(projected, Ok), projected
    local = promoted.value.versions[0]
    public = publish_registry_version(local, local.registry_snapshot)
    lifecycle = plan_registry_lifecycle(projected.value, (local,), (public,))
    assert isinstance(lifecycle, Ok), lifecycle
    published = project_lifecycle_update(projected.value, lifecycle.value)
    assert isinstance(published, Ok), published
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, published.value.entries)


class ConfiguredInstallationDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        self.data_root = str(self.root / "data")
        self.project_root = str(self.root / "project")
        self.source = configured_source("company", SourceKind.REGISTRY_GIT)
        self.effective = effective_configuration((self.source,), default_registry="company")
        snapshot = _published_registry()
        candidate = make_source_candidate(
            source_instance_id(self.source), self.source.alias, "a" * 40, snapshot
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
        self.selection = ArtifactSelection(
            (
                ArtifactRequest(
                    ArtifactIdentity("mcp", "github"),
                    VersionConstraint("*"),
                    self.source.alias,
                ),
            )
        )

    def _draft(self, sources=()):
        return prepare_configured_installation_draft(
            self.effective,
            self.selection,
            data_root=self.data_root,
            project_root=self.project_root,
            scope=Scope.PROJECT,
            profiles=("tabnine",),
            sources=sources,
            policy=EffectivePolicy(),
        )

    def test_verified_registry_content_is_materialized_and_exposes_pending_inputs(self) -> None:
        drafted = self._draft()

        self.assertIsInstance(drafted, Ok, getattr(drafted, "diagnostics", ()))
        assert isinstance(drafted, Ok)
        self.assertFalse(drafted.value.ready)
        self.assertEqual(
            tuple(field.input.id for field in drafted.value.inputs.unanswered),
            (ORG, TOKEN),
        )
        self.assertEqual(drafted.value.inputs.views()[0].default, "acme")
        version = drafted.value.selection.artifacts[0].version
        stored = read_object(
            ObjectReadRequest(object_store_paths(self.data_root), version.object_digest)
        )
        self.assertIsInstance(stored, Ok)
        assert isinstance(stored, Ok)
        self.assertIsNotNone(stored.value)

    def test_submitted_config_and_provider_reference_make_placements_ready(self) -> None:
        drafted = self._draft(
            (
                PromptedConfigValue(ORG, "acme"),
                SecretProviderReference(TOKEN, KEYCHAIN),
            )
        )

        self.assertIsInstance(drafted, Ok, getattr(drafted, "diagnostics", ()))
        assert isinstance(drafted, Ok)
        self.assertTrue(drafted.value.ready)
        placed = drafted.value.prepared_placements()
        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        assert isinstance(placed, Ok)
        self.assertEqual(placed.value[0].sources, drafted.value.inputs.sources)
        self.assertFalse(any(hasattr(source, "secret") for source in placed.value[0].sources))


if __name__ == "__main__":
    unittest.main()
