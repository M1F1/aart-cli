"""CP-16: Doctor reports the three offline capabilities before installation.

The scenarios use configured approved-registry snapshots and never invoke install.  The broken
payload snapshot is deliberate: it still contains the approved version metadata, so it proves that
``metadata`` and ``canonical_payload`` are independently observed rather than two labels on one
boolean.  Dependency readiness is honest about the boundary AART owns: no declared packages means
``not-required``; a declaration with no durable package-cache evidence means ``unverified``.
"""

from __future__ import annotations

import shutil
import unittest

from agent_artifacts.application.promotion import (
    load_registry_versions,
    plan_registry_lifecycle,
    project_lifecycle_update,
)
from agent_artifacts.configuration.model import (
    ReportingSettings,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.schema import user_configuration_bytes
from agent_artifacts.domain.identifiers import SourceId
from agent_artifacts.domain.registry import PromotionMode, deprecate_registry_version
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from agent_artifacts.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import (
    AUTHORED_MCP,
    _promote_one,
    _published_registries,
)
from tests.marketplace_fixtures import configured_source
from tests.placed_installation_e2e_test import AUTHORED_SKILL


def _source_paths(env):
    return source_store_paths(env.paths.data_root, source_instance_id(env.source))


def _publish_registry_snapshot(env, snapshot: SourceSnapshot) -> None:
    candidate = make_source_candidate(
        source_instance_id(env.source), env.source.alias, "d" * 40, snapshot
    )
    assert isinstance(candidate, Ok), candidate
    published = publish_source_snapshot(
        SourcePublishCommand(
            _source_paths(env),
            ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
            91,
        )
    )
    assert isinstance(published, Ok), published


class DoctorOfflineReadinessE2ETest(unittest.TestCase):
    def test_cached_skill_is_reported_before_any_install_is_attempted(self) -> None:
        with _environment() as env:
            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["items"], [])
            source = payload["offline_readiness"]["sources"][0]
            self.assertEqual(source["alias"], "company")
            self.assertEqual(source["metadata"], "cached")
            self.assertEqual(
                source["artifacts"],
                [
                    {
                        "coordinate": "company/skill/code-review@1.2.0",
                        "metadata": "cached",
                        "canonical_payload": "cached",
                        "runtime_dependencies": "not-required",
                    }
                ],
            )
            self.assertFalse(
                (env.project / ".claude/skills/code-review").exists(),
                "Doctor attempted the install it was meant to assess",
            )

    def test_cached_metadata_does_not_claim_missing_canonical_payload(self) -> None:
        with _environment(promotion_mode=PromotionMode.REFERENCED) as env:
            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            readiness = payload["offline_readiness"]["sources"][0]
            self.assertEqual(readiness["metadata"], "cached")
            self.assertEqual(len(readiness["artifacts"]), 1)
            artifact = readiness["artifacts"][0]
            self.assertEqual(artifact["metadata"], "cached")
            self.assertEqual(artifact["canonical_payload"], "missing")
            self.assertEqual(artifact["runtime_dependencies"], "unverified")

    def test_one_missing_payload_does_not_hide_a_later_cached_artifact(self) -> None:
        with _environment() as env:
            snapshot = _promote_one(
                AUTHORED_MCP,
                onto=SourceSnapshot(SnapshotOrigin.LOCAL, ()),
                revision="b" * 40,
                mode=PromotionMode.REFERENCED,
            )
            snapshot = _promote_one(
                AUTHORED_SKILL,
                onto=snapshot,
                revision="c" * 40,
                mode=PromotionMode.VENDORED,
            )
            _publish_registry_snapshot(env, snapshot)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            artifacts = payload["offline_readiness"]["sources"][0]["artifacts"]
            self.assertEqual(len(artifacts), 2)
            self.assertEqual(
                {item["canonical_payload"] for item in artifacts},
                {"cached", "missing"},
            )

    def test_deprecated_registry_metadata_is_not_presented_as_installable_offline(self) -> None:
        with _environment() as env:
            snapshot = _published_registries(AUTHORED_MCP, AUTHORED_SKILL)
            loaded = load_registry_versions(snapshot)
            self.assertIsInstance(loaded, Ok, loaded)
            assert isinstance(loaded, Ok)
            after = tuple(
                deprecate_registry_version(version, reason="superseded")
                if version.coordinate.artifact.kind == "mcp"
                else version
                for version in loaded.value
            )
            lifecycle = plan_registry_lifecycle(snapshot, loaded.value, after)
            self.assertIsInstance(lifecycle, Ok, lifecycle)
            assert isinstance(lifecycle, Ok)
            projected = project_lifecycle_update(snapshot, lifecycle.value)
            self.assertIsInstance(projected, Ok, projected)
            assert isinstance(projected, Ok)
            _publish_registry_snapshot(
                env,
                SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, projected.value.entries),
            )

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            artifacts = payload["offline_readiness"]["sources"][0]["artifacts"]
            self.assertEqual(
                [item["coordinate"] for item in artifacts],
                ["company/skill/code-review@1.2.0"],
            )

    def test_declared_runtime_dependencies_are_not_inferred_from_a_cached_payload(self) -> None:
        with _environment(authored=AUTHORED_MCP) as env:
            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            artifact = payload["offline_readiness"]["sources"][0]["artifacts"][0]
            self.assertEqual(artifact["coordinate"], "company/mcp/github@1.5.0")
            self.assertEqual(artifact["canonical_payload"], "cached")
            self.assertEqual(artifact["runtime_dependencies"], "unverified")

    def test_an_unsynchronized_source_reports_cold_metadata_without_inventing_artifacts(
        self,
    ) -> None:
        with _environment() as env:
            shutil.rmtree(_source_paths(env).root)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertEqual(
                payload["offline_readiness"]["sources"],
                [{"alias": "company", "metadata": "missing", "artifacts": []}],
            )

    def test_every_enabled_source_is_observed_without_treating_a_plain_source_as_a_registry(
        self,
    ) -> None:
        with _environment() as env:
            disabled = configured_source("aaa-disabled", SourceKind.REGISTRY_GIT, enabled=False)
            cold = configured_source("bbb-cold", SourceKind.REGISTRY_GIT)
            local = configured_source(
                "ccc-local",
                SourceKind.SOURCE_LOCAL,
                location=str(env.root / "local-source"),
            )
            configuration = UserConfiguration(
                1,
                (disabled, cold, local, env.source),
                env.source.alias,
                SyncSettings(),
                ReportingSettings(),
            )
            env_config = env.paths.user_config_file
            with open(env_config, "wb") as stream:
                stream.write(user_configuration_bytes(configuration))

            initial = make_source_candidate(
                source_instance_id(local),
                local.alias,
                "temporary",
                SourceSnapshot(SnapshotOrigin.LOCAL, ()),
            )
            self.assertIsInstance(initial, Ok, initial)
            assert isinstance(initial, Ok)
            candidate = make_source_candidate(
                initial.value.instance_id,
                initial.value.alias,
                f"local:{initial.value.snapshot_digest.value}",
                initial.value.snapshot,
            )
            self.assertIsInstance(candidate, Ok, candidate)
            assert isinstance(candidate, Ok)
            published = publish_source_snapshot(
                SourcePublishCommand(
                    source_store_paths(env.paths.data_root, source_instance_id(local)),
                    ValidatedSourceCandidate(candidate.value, SourceId("local-source")),
                    90,
                )
            )
            self.assertIsInstance(published, Ok, published)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            readiness = payload["offline_readiness"]["sources"]
            self.assertEqual(
                [source["alias"] for source in readiness],
                ["bbb-cold", "ccc-local", "company"],
            )
            self.assertEqual(readiness[0]["metadata"], "missing")
            self.assertEqual(readiness[1]["metadata"], "cached")
            self.assertEqual(readiness[1]["artifacts"], [])
            self.assertEqual(len(readiness[2]["artifacts"]), 1)

    def test_human_output_keeps_the_three_capabilities_visibly_separate(self) -> None:
        with _environment(authored=AUTHORED_MCP) as env:
            code, output = env.run_text("doctor")

            self.assertEqual(code, 0, output)
            self.assertIn("Offline readiness", output)
            self.assertIn("metadata cached", output)
            self.assertIn("canonical payload cached", output)
            self.assertIn("runtime dependencies unverified", output)
            # The claim is about this section, not the whole report: "cached" is not "installed",
            # and a later section that legitimately says "installed artifact" is not a violation
            # of it. Scanning the whole report held this only for as long as no other section
            # used the word.
            offline = next(
                block for block in output.split("\n\n") if block.startswith("Offline readiness")
            )
            self.assertNotIn("installed", offline.lower())


if __name__ == "__main__":
    unittest.main()
