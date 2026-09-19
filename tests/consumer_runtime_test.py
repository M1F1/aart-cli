from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from aart_cli.application.promotion import registry_state_digest
from aart_cli.compiler.graph import compile_marketplace_graph
from aart_cli.configuration.model import SourceKind
from aart_cli.configuration.paths import Platform, resolve_config_paths
from aart_cli.configuration.schema import user_configuration_bytes
from aart_cli.consumer.runtime import (
    _CAPABILITIES,
    _graph_source,
    _registry_security_evidence,
    load_local_consumer_service,
    load_read_only_marketplace,
)
from aart_cli.domain.identifiers import SourceId
from aart_cli.domain.result import Err, Ok
from aart_cli.io.config_store import read_configuration
from aart_cli.io.source_store import publish_source_snapshot
from aart_cli.marketplace.catalog import build_marketplace
from aart_cli.marketplace.model import MarketplaceSourceState
from aart_cli.protocol.hashing import json_digest
from aart_cli.protocol.json import JsonObject
from aart_cli.protocol.native_tree import SourceSnapshot
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.security.attestation_schema import attestation_bytes, security_index_bytes
from aart_cli.security.attestations import (
    AssessmentCacheKey,
    AttestationOrigin,
    AttestationOriginKind,
    AttestationTrust,
    SecurityAttestation,
    SecurityIndex,
    SecurityIndexEntry,
    attestation_digest,
)
from aart_cli.security.baseline import BASELINE_RULES_DIGEST, not_scanned_assessment
from aart_cli.sources.model import (
    CurrentSource,
    SourcePublishCommand,
    ValidatedSourceCandidate,
    assess_source_health,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from aart_cli.store.model import object_store_paths
from aart_cli.tui_marketplace import MarketplaceTarget
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.registry_maintenance_fixtures import (
    append_snapshot_file,
    approved_registry_snapshot,
    native_snapshot,
    replace_snapshot_file,
    snapshot_file,
)


def _current(source, source_id: str, snapshot) -> CurrentSource:
    candidate = make_source_candidate(
        source_instance_id(source),
        source.alias,
        "a" * 40,
        snapshot,
    )
    assert isinstance(candidate, Ok), candidate
    return CurrentSource(candidate.value, SourceId(source_id), 90, "/managed/source")


class ConsumerRuntimeTest(unittest.TestCase):
    def test_persisted_partial_required_source_configuration_cannot_load_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            home = root / "home"
            project = root / "project"
            home.mkdir()
            project.mkdir()
            xdg = {
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local/share"),
                "XDG_CACHE_HOME": str(home / ".cache"),
            }
            platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
            paths = resolve_config_paths(
                platform,
                home=str(home),
                xdg_config_home=xdg["XDG_CONFIG_HOME"],
                xdg_data_home=xdg["XDG_DATA_HOME"],
                xdg_cache_home=xdg["XDG_CACHE_HOME"],
            )
            source = configured_source("company", SourceKind.REGISTRY_GIT)
            configuration = effective_configuration(
                (source,), default_registry="company"
            ).configuration
            config_path = Path(paths.user_config_file)
            config_path.parent.mkdir(parents=True)
            config_path.write_bytes(user_configuration_bytes(configuration))

            with (
                mock.patch.dict(os.environ, xdg, clear=False),
                mock.patch(
                    "aart_cli.consumer.runtime.read_configuration",
                    side_effect=lambda request: (
                        Ok(b'{"schema_version":1,"required_sources":["company","team"]}')
                        if request.path == paths.policy_file
                        else read_configuration(request)
                    ),
                ),
            ):
                loaded = load_local_consumer_service(
                    project=str(project),
                    user_home=str(home),
                )

            self.assertIsInstance(loaded, Err)
            assert isinstance(loaded, Err)
            self.assertEqual(loaded.diagnostics[0].code.value, "source-policy-denied")

    def test_read_only_marketplace_does_not_materialize_native_objects(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            data_root = root / "data"
            source = configured_source("team", SourceKind.SOURCE_GIT)
            candidate = make_source_candidate(
                source_instance_id(source),
                source.alias,
                "a" * 40,
                native_snapshot(),
            )
            assert isinstance(candidate, Ok), candidate
            published = publish_source_snapshot(
                SourcePublishCommand(
                    source_store_paths(str(data_root), source_instance_id(source)),
                    ValidatedSourceCandidate(candidate.value, SourceId("reference-native-source")),
                    90,
                )
            )
            assert isinstance(published, Ok), published

            listed = load_read_only_marketplace(
                effective_configuration((source,)),
                data_root=str(data_root),
            )

            self.assertIsInstance(listed, Ok)
            assert isinstance(listed, Ok)
            self.assertEqual(len(listed.value.items), 2)
            digest = listed.value.items[0].artifact.artifact.object_digest.value
            self.assertFalse(
                (
                    Path(object_store_paths(str(data_root)).objects) / digest[:2] / digest[2:]
                ).exists()
            )

    def test_read_only_marketplace_verifies_but_does_not_materialize_registry_objects(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            data_root = root / "data"
            source = configured_source("company", SourceKind.REGISTRY_GIT)
            candidate = make_source_candidate(
                source_instance_id(source),
                source.alias,
                "a" * 40,
                approved_registry_snapshot(names=("github-mcp", "jira-mcp", "slack-mcp")),
            )
            assert isinstance(candidate, Ok), candidate
            published = publish_source_snapshot(
                SourcePublishCommand(
                    source_store_paths(str(data_root), source_instance_id(source)),
                    ValidatedSourceCandidate(candidate.value, SourceId("test-registry")),
                    90,
                )
            )
            assert isinstance(published, Ok), published

            listed = load_read_only_marketplace(
                effective_configuration((source,), default_registry="company"),
                data_root=str(data_root),
            )

            self.assertIsInstance(listed, Ok)
            assert isinstance(listed, Ok)
            self.assertEqual(len(listed.value.items), 3)
            store = Path(object_store_paths(str(data_root)).objects)
            for item in listed.value.items:
                digest = item.artifact.artifact.object_digest.value
                self.assertFalse((store / digest[:2] / digest[2:]).exists())

    def test_a_registry_carrying_the_retired_representation_is_refused_by_name(self) -> None:
        """CP-26.4: the workspace compiler is not a second projection to fall back on.

        The consumer used to read `aart.lock.json`/`aart.index.json`/`entries/` whenever a
        checkout had no `registry/` tree, so a registry that had never been promoted still
        produced Marketplace rows. Nothing compiles that shape now, and a mixed checkout must be
        named rather than silently projected through whichever branch matched first.
        """

        with tempfile.TemporaryDirectory() as raw:
            paths = object_store_paths(str(Path(raw) / "data"))
            source = configured_source("company", SourceKind.REGISTRY_GIT)
            approved = approved_registry_snapshot()
            mixed = append_snapshot_file(approved, "aart.lock.json", b"{}\n")
            retired = append_snapshot_file(
                append_snapshot_file(
                    SourceSnapshot(
                        approved.origin,
                        tuple(
                            entry
                            for entry in approved.entries
                            if not str(entry.path).startswith("registry/")
                        ),
                    ),
                    "aart.lock.json",
                    b"{}\n",
                ),
                "aart.index.json",
                b"{}\n",
            )

            for snapshot, named in ((mixed, "aart.lock.json"), (retired, "aart.index.json")):
                refused = _graph_source(
                    source,
                    _current(source, "test-registry", snapshot),
                    paths,
                )

                self.assertNotIsInstance(refused, Ok)
                assert isinstance(refused, Err), refused
                message = refused.diagnostics[0].message
                self.assertIn("retired authoring-workspace representation", message)
                self.assertIn(named, message)

    def test_a_registry_that_declares_no_registry_is_refused_as_not_canonical(self) -> None:
        """A refusal names the shape that was expected, so the operator knows what to produce."""

        with tempfile.TemporaryDirectory() as raw:
            source = configured_source("company", SourceKind.REGISTRY_GIT)
            anonymous = append_snapshot_file(
                SourceSnapshot(native_snapshot().origin, ()),
                "README.md",
                b"# not a registry\n",
            )

            refused = _graph_source(
                source,
                _current(source, "test-registry", anonymous),
                object_store_paths(str(Path(raw) / "data")),
            )

            self.assertNotIsInstance(refused, Ok)
            assert isinstance(refused, Err), refused
            message = refused.diagnostics[0].message
            self.assertIn("is not a canonical approved Registry", message)
            self.assertIn("aart-cli-registry.json", message)
            self.assertIn("aart-cli-source.json", message)

    def test_an_approved_registry_projects_every_published_version(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = configured_source("company", SourceKind.REGISTRY_GIT)
            projected = _graph_source(
                source,
                _current(
                    source,
                    "test-registry",
                    approved_registry_snapshot(names=("github-mcp", "jira-mcp")),
                ),
                object_store_paths(str(Path(raw) / "data")),
            )

            assert isinstance(projected, Ok), projected
            self.assertEqual(
                tuple(str(item.identity) for item in projected.value.artifacts),
                ("mcp/github-mcp", "mcp/jira-mcp"),
            )

    def test_invalid_native_or_registry_snapshots_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = object_store_paths(str(Path(raw) / "data"))
            direct = configured_source("team", SourceKind.SOURCE_GIT)
            # A tree that *says* it is a native package source and then is not.  Claiming the
            # marker is what makes this a broken native source rather than an authoring
            # repository, and a broken one must still take nothing from this source into the
            # consumer graph (B-094 widened admission, not this refusal).
            broken_native = SourceSnapshot(
                native_snapshot().origin,
                tuple(
                    replace(entry, content=b"{ not json\n")
                    if str(entry.path) == "aart-cli-source.json"
                    else entry
                    for entry in native_snapshot().entries
                ),
            )
            invalid_native = _graph_source(
                direct,
                _current(direct, "reference-native-source", broken_native),
                paths,
            )
            registry = configured_source("company", SourceKind.REGISTRY_GIT)
            # A native package source is not a Registry: it declares no `aart-cli-registry.json`, so
            # it is refused for what it is rather than compiled as an empty catalog.
            not_a_registry = _graph_source(
                registry,
                _current(registry, "reference-native-source", native_snapshot()),
                paths,
            )
            malformed_catalog = _graph_source(
                registry,
                _current(
                    registry,
                    "test-registry",
                    replace_snapshot_file(
                        approved_registry_snapshot(),
                        "registry/index.json",
                        b"{}\n",
                    ),
                ),
                paths,
            )

            self.assertNotIsInstance(invalid_native, Ok)
            self.assertNotIsInstance(not_a_registry, Ok)
            assert isinstance(not_a_registry, Err), not_a_registry
            # Its packages sit at `artifacts/<kind>/<name>/`, which is the retired unversioned
            # shape: the same tree is a valid authoring Source and is not a Registry.
            self.assertIn(
                "retired authoring-workspace representation",
                not_a_registry.diagnostics[0].message,
            )
            self.assertNotIsInstance(malformed_catalog, Ok)

    def test_an_authoring_source_contributes_nothing_and_takes_nothing_away(self) -> None:
        """INV-199 at the consumer projection: a Source of Candidates is not Marketplace content.

        An authoring repository declares no `aart-cli-source.json` -- it declares `aart-cli.yaml`
        manifests, which compile to Candidates a maintainer has not approved yet.  Reading it as
        a broken native package tree refused the *whole* projection, which is how one subscribed
        author repository used to empty a consumer's Marketplace (B-094/QA-020).  The right
        answer is an empty contribution, and the difference is only visible next to the broken
        native tree above: that one still refuses.
        """

        with tempfile.TemporaryDirectory() as raw:
            paths = object_store_paths(str(Path(raw) / "data"))
            authoring = configured_source("authors", SourceKind.SOURCE_GIT)
            snapshot = append_snapshot_file(
                SourceSnapshot(native_snapshot().origin, ()),
                "skills/review/aart-cli.yaml",
                b"schema: aart-cli.dev/skill/v1\n",
            )

            projected = _graph_source(
                authoring,
                _current(authoring, "authors", snapshot),
                paths,
            )

            self.assertIsInstance(projected, Ok)
            assert isinstance(projected, Ok)
            self.assertEqual(projected.value.artifacts, ())
            self.assertEqual(projected.value.collections, ())
            self.assertEqual(projected.value.alias, authoring.alias)

    def test_registry_runtime_rejects_missing_or_stale_approved_evidence(self) -> None:
        """Every approved row has to be evidenced by this snapshot, not asserted by a catalog."""

        with tempfile.TemporaryDirectory() as raw:
            paths = object_store_paths(str(Path(raw) / "data"))
            source = configured_source("company", SourceKind.REGISTRY_GIT)
            snapshot = approved_registry_snapshot()
            version_path = "registry/versions/mcp/github-mcp/1.0.0.json"

            stale_version_document = json.loads(snapshot_file(snapshot, version_path))
            stale_version_document["object_digest"] = f"sha256:{'0' * 64}"
            stale_version = _graph_source(
                source,
                _current(
                    source,
                    "test-registry",
                    replace_snapshot_file(
                        snapshot,
                        version_path,
                        json.dumps(stale_version_document).encode(),
                    ),
                ),
                paths,
            )
            stale_catalog = _graph_source(
                source,
                _current(
                    source,
                    "test-registry",
                    replace_snapshot_file(snapshot, "registry/index.json", b"{}\n"),
                ),
                paths,
            )
            # The promotion record is what says the version was reviewed; a row without it claims
            # an approval nothing in the snapshot evidences.
            promotion_path = next(
                str(entry.path)
                for entry in snapshot.entries
                if str(entry.path).startswith("registry/promotions/")
                and str(entry.path).endswith(".json")
            )
            unevidenced = _graph_source(
                source,
                _current(
                    source,
                    "test-registry",
                    replace_snapshot_file(snapshot, promotion_path, b"{}\n"),
                ),
                paths,
            )
            tampered_payload = _graph_source(
                source,
                _current(
                    source,
                    "test-registry",
                    replace_snapshot_file(
                        snapshot,
                        "artifacts/mcp/github-mcp/1.0.0/payload/server.py",
                        b"print('tampered')\n",
                    ),
                ),
                paths,
            )

            for result in (stale_version, stale_catalog, unevidenced, tampered_payload):
                self.assertNotIsInstance(result, Ok)

    def test_local_composition_loads_persisted_and_reviewed_prospective_configuration(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            home = root / "home"
            project = root / "project"
            home.mkdir()
            project.mkdir()
            xdg = {
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local/share"),
                "XDG_CACHE_HOME": str(home / ".cache"),
            }
            platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
            config_paths = resolve_config_paths(
                platform,
                home=str(home),
                xdg_config_home=xdg["XDG_CONFIG_HOME"],
                xdg_data_home=xdg["XDG_DATA_HOME"],
                xdg_cache_home=xdg["XDG_CACHE_HOME"],
            )
            source = configured_source("team", SourceKind.SOURCE_GIT)
            configuration = effective_configuration((source,)).configuration
            config_file = Path(config_paths.user_config_file)
            config_file.parent.mkdir(parents=True)
            config_file.write_bytes(user_configuration_bytes(configuration))
            with mock.patch.dict(os.environ, xdg, clear=False):
                missing_snapshot = load_local_consumer_service(
                    project=str(project),
                    user_home=str(home),
                )
            assert isinstance(missing_snapshot, Ok), missing_snapshot
            self.assertEqual(missing_snapshot.value.context.catalog.items, ())
            candidate = make_source_candidate(
                source_instance_id(source),
                source.alias,
                "a" * 40,
                native_snapshot(),
            )
            assert isinstance(candidate, Ok), candidate
            published = publish_source_snapshot(
                SourcePublishCommand(
                    source_store_paths(config_paths.data_root, source_instance_id(source)),
                    ValidatedSourceCandidate(candidate.value, SourceId("reference-native-source")),
                    90,
                )
            )
            assert isinstance(published, Ok), published

            with mock.patch.dict(os.environ, xdg, clear=False):
                persisted = load_local_consumer_service(
                    project=str(project),
                    user_home=str(home),
                )
                disabled = replace(
                    configuration,
                    sources=(replace(source, enabled=False),),
                )
                config_file.write_bytes(user_configuration_bytes(disabled))
                prospective = load_local_consumer_service(
                    project=str(project),
                    user_home=str(home),
                    configuration=configuration,
                )

            assert isinstance(persisted, Ok), persisted
            assert isinstance(prospective, Ok), prospective
            for loaded in (persisted.value, prospective.value):
                rows = loaded.browse(MarketplaceTarget(("claude",), "darwin", "project", "copy"))
                assert isinstance(rows, Ok), rows
                self.assertEqual(
                    tuple(row.key for row in rows.value),
                    ("team/memory/house@1.0.0", "team/skill/code-review@1.0.0"),
                )
                digest = loaded.context.catalog.items[0].artifact.artifact.object_digest.value
                self.assertTrue(
                    (Path(loaded.context.store_paths.objects) / digest[:2] / digest[2:]).is_dir()
                )

    def test_verified_registry_security_index_is_bound_to_exact_marketplace_coordinates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = configured_source("company", SourceKind.REGISTRY_GIT)
            approved = approved_registry_snapshot(names=("github-mcp", "jira-mcp"))
            snapshot = approved
            registry_id = SourceId("test-registry")
            # What an attestation set binds is the registry's published content, recomputed here
            # exactly as the consumer recomputes it.
            state = registry_state_digest(approved)
            assert isinstance(state, Ok), state
            projected_artifacts = _graph_source(
                source,
                _current(source, str(registry_id), approved),
                object_store_paths(str(Path(raw) / "data")),
            )
            assert isinstance(projected_artifacts, Ok), projected_artifacts
            empty_digest = json_digest(JsonObject(()))
            entries = []
            for artifact in projected_artifacts.value.artifacts:
                attestation = SecurityAttestation(
                    1,
                    AssessmentCacheKey(
                        1,
                        artifact.object_digest,
                        "aart-cli-baseline",
                        "1",
                        BASELINE_RULES_DIGEST,
                        empty_digest,
                        empty_digest,
                    ),
                    AttestationOrigin(
                        AttestationOriginKind.REGISTRY_CI,
                        registry_id,
                        "a" * 40,
                        state.value,
                    ),
                    not_scanned_assessment(
                        artifact.object_digest,
                        "Registry CI recorded explicit baseline coverage.",
                    ),
                )
                digest = attestation_digest(attestation)
                path = parse_relative_path(f"security/attestations/{digest.value}.json")
                assert isinstance(path, Ok), path
                entries.append(SecurityIndexEntry(attestation.cache_key, digest, path.value))
                snapshot = append_snapshot_file(
                    snapshot,
                    str(path.value),
                    attestation_bytes(attestation),
                )
            index = SecurityIndex(1, registry_id, state.value, tuple(entries))
            snapshot = append_snapshot_file(
                snapshot,
                "security/index.json",
                security_index_bytes(index),
            )
            current = _current(source, str(registry_id), snapshot)
            paths = object_store_paths(str(Path(raw) / "data"))
            projected = _graph_source(source, current, paths)
            assert isinstance(projected, Ok), projected
            graph = compile_marketplace_graph(
                (projected.value,),
                available_capabilities=_CAPABILITIES,
            )
            assert isinstance(graph, Ok), graph
            effective = effective_configuration((source,), default_registry="company")
            catalog = build_marketplace(
                graph.value,
                effective,
                (
                    MarketplaceSourceState(
                        source,
                        assess_source_health(current, now=100, max_age_seconds=30),
                        0,
                    ),
                ),
            )
            assert isinstance(catalog, Ok), catalog

            evidence = _registry_security_evidence(
                catalog.value,
                ((source, current),),
                now=100,
            )

            self.assertEqual(len(evidence), 2)
            self.assertEqual({item.evidence_age_seconds for item in evidence}, {10})
            trust = {item.coordinate.artifact.name: item.attestation_trust for item in evidence}
            # Every approved version carries the promotion that reviewed it, so registry CI
            # evidence bound to this registry's state is registry-reviewed for all of them.
            self.assertEqual(
                trust,
                {
                    "github-mcp": AttestationTrust.REGISTRY_REVIEWED,
                    "jira-mcp": AttestationTrust.REGISTRY_REVIEWED,
                },
            )
            self.assertTrue(
                all(item.assessment.providers[0].id == "aart-cli-baseline" for item in evidence)
            )

            missing_documents = append_snapshot_file(
                approved,
                "security/index.json",
                security_index_bytes(index),
            )
            missing_current = _current(source, str(registry_id), missing_documents)
            self.assertEqual(
                _registry_security_evidence(
                    catalog.value,
                    ((source, missing_current),),
                    now=100,
                ),
                (),
            )
            tampered = approved
            for entry in entries:
                tampered = append_snapshot_file(tampered, str(entry.path), b"{}\n")
            tampered = append_snapshot_file(
                tampered,
                "security/index.json",
                security_index_bytes(index),
            )
            tampered_current = _current(source, str(registry_id), tampered)
            self.assertEqual(
                _registry_security_evidence(
                    catalog.value,
                    ((source, tampered_current),),
                    now=100,
                ),
                (),
            )
            malformed = append_snapshot_file(
                approved,
                "security/index.json",
                b"{}\n",
            )
            malformed_current = _current(source, str(registry_id), malformed)
            mismatched_index = SecurityIndex(1, SourceId("other-registry"), state.value, ())
            mismatched = append_snapshot_file(
                approved,
                "security/index.json",
                security_index_bytes(mismatched_index),
            )
            mismatched_current = _current(source, str(registry_id), mismatched)
            for degraded in (malformed_current, mismatched_current):
                self.assertEqual(
                    _registry_security_evidence(
                        catalog.value,
                        ((source, degraded),),
                        now=100,
                    ),
                    (),
                )

    def test_direct_native_snapshot_materializes_objects_and_builds_qualified_graph(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = configured_source("team", SourceKind.SOURCE_GIT)
            current = _current(source, "reference-native-source", native_snapshot())
            paths = object_store_paths(str(Path(raw) / "data"))

            projected = _graph_source(source, current, paths)

            assert isinstance(projected, Ok), projected
            self.assertEqual(projected.value.alias, source.alias)
            self.assertEqual(len(projected.value.artifacts), 2)
            self.assertTrue(
                all(
                    (
                        Path(paths.objects)
                        / artifact.object_digest.value[:2]
                        / artifact.object_digest.value[2:]
                    ).is_dir()
                    for artifact in projected.value.artifacts
                )
            )

    def test_registry_catalog_rebinds_runtime_source_identity_and_carries_review_trust(
        self,
    ) -> None:
        """A registry row is the registry's, and it is reviewed because promotion approved it.

        Upstream identity stays in the version record's provenance. Letting it reach the graph
        would make one subscription look like several runtime sources and would route the row
        around the registry's trust overlay.
        """

        with tempfile.TemporaryDirectory() as raw:
            source = configured_source("company", SourceKind.REGISTRY_GIT)
            current = _current(
                source,
                "test-registry",
                approved_registry_snapshot(names=("github-mcp", "jira-mcp")),
            )
            paths = object_store_paths(str(Path(raw) / "data"))
            projected = _graph_source(source, current, paths)
            assert isinstance(projected, Ok), projected
            graph = compile_marketplace_graph(
                (projected.value,),
                available_capabilities=_CAPABILITIES,
            )
            assert isinstance(graph, Ok), graph
            effective = effective_configuration((source,), default_registry="company")
            catalog = build_marketplace(
                graph.value,
                effective,
                (
                    MarketplaceSourceState(
                        source,
                        assess_source_health(current, now=100, max_age_seconds=30),
                        0,
                    ),
                ),
            )

            assert isinstance(catalog, Ok), catalog
            self.assertEqual(len(catalog.value.items), 2)
            self.assertTrue(
                all(
                    item.artifact.source_id == SourceId("test-registry")
                    for item in catalog.value.items
                )
            )
            self.assertEqual(
                {item.trust.kind.value for item in catalog.value.items},
                {"registry-reviewed"},
            )
            # No committed attestation set, so there is no security evidence to report.
            self.assertEqual(
                _registry_security_evidence(
                    catalog.value,
                    ((source, current),),
                    now=100,
                ),
                (),
            )


if __name__ == "__main__":
    unittest.main()
