"""Reading a selected artifact out of the store and deciding what installing it would involve.

This is the step between "somebody selected `public/mcp/github`" and an offer: one read and three
decisions. The read is the only effect, and it is the one place a wrong answer is silent -- a
package this machine cannot read is not a package that declares nothing, and treating the second as
the first installs an artifact that starts nothing and asks for nothing, with no error anywhere.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.artifact_placement import PLACEMENT_UNAVAILABLE, placement_for
from agent_artifacts.io.object_store import publish_object
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.sources.local import read_local_snapshot
from agent_artifacts.sources.model import (
    LocalSnapshotRequest,
    SnapshotLimits,
    source_instance_id,
)
from agent_artifacts.store.model import (
    ObjectPublishCommand,
    make_object_candidate,
    object_store_paths,
)
from tests.artifact_installation_e2e_test import MANIFEST, SERVER_SOURCE
from tests.installation_proposal_test import _resolved

PROFILES = ("tabnine",)

#: An artifact a harness reads rather than starts: no transport, no runtime, no launch, no inputs.
#: `read_package_description` returns an empty description for it, and that is the discriminator
#: `placement_for` routes on.
SKILL_MANIFEST = {
    "schema": "aart.dev/skill/v1",
    "artifact": {"name": "code-review", "kind": "skill", "version": "1.2.0"},
    "payload": {"include": ["SKILL.md", "reference.md"]},
    "compatibility": {"harnesses": ["claude"]},
}


class PlacementResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name).resolve()
        self.project = str(self.scope / "project")
        self.data = str(self.scope / "data")
        self.store = object_store_paths(str(self.scope / "store"))
        self.artifact = self._publish()

    def _publish(self):
        repository = self.scope / "author"
        (repository / "github").mkdir(parents=True)
        (repository / "github/aart.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        (repository / "github/server.py").write_text(SERVER_SOURCE, encoding="utf-8")
        (repository / "github/requirements.txt").write_text("# none\n", encoding="utf-8")

        alias = SourceAlias("company")
        configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(repository), None, True)
        acquired = read_local_snapshot(
            LocalSnapshotRequest(
                source_instance_id(configured), alias, str(repository), SnapshotLimits()
            )
        )
        self.assertIsInstance(acquired, Ok, getattr(acquired, "diagnostics", ()))
        compiled = compile_author_snapshot(
            acquired.value.snapshot,
            source_alias=alias,
            source="https://github.company/company/servers.git",
            revision="c" * 40,
        )
        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        package = compiled.value[0]
        candidate = make_object_candidate(package.canonical_entries)
        self.assertIsInstance(candidate, Ok, getattr(candidate, "diagnostics", ()))
        published = publish_object(ObjectPublishCommand(self.store, candidate.value))
        self.assertIsInstance(published, Ok, getattr(published, "diagnostics", ()))
        return _stored_artifact(package.package, candidate.value.digest)

    def _place(self, **overrides):
        fields = {
            "scope": Scope.PROJECT,
            "profiles": PROFILES,
            "project_root": self.project,
            "data_root": self.data,
            "store": self.store,
        }
        fields.update(overrides)
        return placement_for(self.artifact, **fields)  # type: ignore[arg-type]

    def test_it_reads_what_the_package_declares_rather_than_assuming_it_declares_nothing(
        self,
    ) -> None:
        placed = self._place()

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertIsNotNone(placed.value.description.contract)
        self.assertTrue(placed.value.description.inputs)

    def test_the_root_is_the_placement_policy_and_carries_no_harness(self) -> None:
        placed = self._place()

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertTrue(
            placed.value.root.startswith(f"{self.project}/.agent-artifacts/runtimes/"),
            placed.value.root,
        )
        self.assertNotIn(".tabnine", placed.value.root)

    def test_the_payload_source_is_the_stored_object_this_machine_verified(self) -> None:
        placed = self._place()

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertTrue(placed.value.payload_source.startswith(self.store.objects))

    def test_every_requested_profile_becomes_a_measured_target(self) -> None:
        placed = self._place(profiles=("tabnine", "claude"))

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual([target.harness for target in placed.value.targets], ["tabnine", "claude"])

    def test_a_harness_nobody_measured_is_named_rather_than_skipped(self) -> None:
        """A profile quietly dropped is an install that reports success and leaves the harness
        somebody asked for with no way to start the server."""

        placed = self._place(profiles=("tabnine", "emacs"))

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        self.assertIn("emacs", placed.diagnostics[0].message)

    def test_naming_no_profile_at_all_is_refused(self) -> None:
        placed = self._place(profiles=())

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)

    def test_an_object_this_store_does_not_hold_names_the_digest_it_wanted(self) -> None:
        placed = placement_for(
            _resolved(),
            scope=Scope.PROJECT,
            profiles=PROFILES,
            project_root=self.project,
            data_root=self.data,
            store=self.store,
        )

        self.assertIsInstance(placed, Err)
        self.assertIn("does not hold", placed.diagnostics[0].message)
        self.assertTrue(placed.diagnostics[0].remediation)

    def test_a_user_scope_placement_leaves_the_project_tree_alone(self) -> None:
        placed = self._place(scope=Scope.USER)

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertTrue(placed.value.root.startswith(f"{self.data}/runtimes/"), placed.value.root)


class DeliveredPlacementTest(unittest.TestCase):
    """A Skill: read out of the store, and turned into the deliveries an install would make.

    The MCP path answers "which harnesses does this register with"; this one answers "where does
    each harness read it from", and the two are measured from different tables. Nothing here is
    invented from the artifact's name: the destination comes from `DELIVERY_TARGETS` and the
    source from the package's own payload.
    """

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name).resolve()
        self.project = str(self.scope / "project")
        self.data = str(self.scope / "data")
        self.harness = str(self.scope / "project")
        self.store = object_store_paths(str(self.scope / "store"))
        self.artifact = self._publish()

    def _publish(self):
        repository = self.scope / "author"
        (repository / "code-review").mkdir(parents=True)
        (repository / "code-review/aart.json").write_text(
            json.dumps(SKILL_MANIFEST), encoding="utf-8"
        )
        (repository / "code-review/SKILL.md").write_text("# review\n", encoding="utf-8")
        (repository / "code-review/reference.md").write_text("detail\n", encoding="utf-8")

        alias = SourceAlias("company")
        configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(repository), None, True)
        acquired = read_local_snapshot(
            LocalSnapshotRequest(
                source_instance_id(configured), alias, str(repository), SnapshotLimits()
            )
        )
        self.assertIsInstance(acquired, Ok, getattr(acquired, "diagnostics", ()))
        compiled = compile_author_snapshot(
            acquired.value.snapshot,
            source_alias=alias,
            source="https://github.company/company/skills.git",
            revision="d" * 40,
        )
        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        package = compiled.value[0]
        candidate = make_object_candidate(package.canonical_entries)
        self.assertIsInstance(candidate, Ok, getattr(candidate, "diagnostics", ()))
        published = publish_object(ObjectPublishCommand(self.store, candidate.value))
        self.assertIsInstance(published, Ok, getattr(published, "diagnostics", ()))
        self.package = package.package
        return _stored_artifact(package.package, candidate.value.digest)

    def _place(self, **overrides):
        fields = {
            "scope": Scope.PROJECT,
            "profiles": ("claude",),
            "project_root": self.project,
            "data_root": self.data,
            "harness_root": self.harness,
            "store": self.store,
        }
        fields.update(overrides)
        return placement_for(self.artifact, **fields)  # type: ignore[arg-type]

    def test_a_skill_is_placed_with_the_delivery_the_harness_reads_it_from(self) -> None:
        placed = self._place()

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        (delivery,) = placed.value.deliveries
        self.assertEqual("claude", delivery.harness)
        self.assertEqual(
            f"{self.harness}/.claude/skills/code-review", delivery.destination
        )
        self.assertIs(DeliveryKind.TREE, delivery.kind)

    def test_the_delivery_is_made_from_the_copy_this_install_owns(self) -> None:
        """Not from the store. A repair copies from what the installation placed, which is the
        only tree this artifact controls: the store's object is shared and may be pruned."""

        placed = self._place()

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        (delivery,) = placed.value.deliveries
        self.assertTrue(delivery.source.startswith(f"{placed.value.root}/"), delivery.source)
        self.assertNotIn(self.store.objects, delivery.source)

    def test_a_skill_registers_with_nothing(self) -> None:
        placed = self._place()

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual((), placed.value.targets)

    def test_what_is_delivered_is_digested_so_a_later_repair_can_compare_it(self) -> None:
        placed = self._place()

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        (delivery,) = placed.value.deliveries
        self.assertEqual("sha256", delivery.digest.algorithm)
        self.assertEqual(self.package.payload_digest, placed.value.payload_digest)

    def test_every_requested_harness_gets_its_own_delivery(self) -> None:
        placed = self._place(profiles=("claude", "tabnine"))

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual(
            [
                (item.harness, item.destination)
                for item in sorted(placed.value.deliveries, key=lambda item: item.harness)
            ],
            [
                ("claude", f"{self.harness}/.claude/skills/code-review"),
                ("tabnine", f"{self.harness}/.tabnine/agent/skills/code-review"),
            ],
        )

    def test_a_harness_with_no_measured_place_for_this_kind_is_named(self) -> None:
        """Named rather than skipped, for the same reason a missing MCP target is: an install
        that reports success and delivers nowhere leaves the harness with nothing to read."""

        placed = self._place(profiles=("claude", "emacs"))

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        self.assertIn("emacs", placed.diagnostics[0].message)

    def test_placing_a_delivered_artifact_with_no_harness_root_is_refused(self) -> None:
        """A destination relative to a root nobody supplied would be resolved against whatever
        working directory the install happened to run in."""

        placed = self._place(harness_root=None)

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)

    def test_a_user_scope_skill_is_delivered_under_the_user_root(self) -> None:
        home = str(self.scope / "home")
        placed = self._place(scope=Scope.USER, harness_root=home)

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        (delivery,) = placed.value.deliveries
        self.assertEqual(f"{home}/.claude/skills/code-review", delivery.destination)


def _stored_artifact(package, digest: ObjectDigest):
    from agent_artifacts.domain.candidates import CandidateId
    from agent_artifacts.domain.registry import (
        PromotionMode,
        PublicationStage,
        RegistryArtifactVersion,
    )
    from agent_artifacts.domain.selection import (
        OwnershipKind,
        OwnershipReason,
        ResolvedArtifact,
    )

    payload = package.payload_digest
    return ResolvedArtifact(
        RegistryArtifactVersion(
            package.coordinate,
            CandidateId("b" * 64),
            package.provenance.input_digest,
            payload,
            digest,
            digest,
            digest,
            PromotionMode.VENDORED,
            PublicationStage.PUBLISHED,
        ),
        (OwnershipReason(OwnershipKind.DIRECT, str(package.coordinate)),),
    )


if __name__ == "__main__":
    unittest.main()
