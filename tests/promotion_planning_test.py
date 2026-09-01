"""CP-05 reviewed, atomic and non-publishing registry promotion planning."""

from __future__ import annotations

import dataclasses
import json
import unittest

from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.application.promotion import (
    PromotionApplyReceipt,
    PromotionEvidence,
    finalize_promotion,
    load_registry_versions,
    plan_bulk_promotion,
    plan_registry_lifecycle,
    project_lifecycle_update,
    project_promotion,
    validate_promoted_registry,
)
from agent_artifacts.domain.candidates import assess_candidate
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.registry import (
    PromotionMode,
    deprecate_registry_version,
    registry_version_from_candidate,
    revoke_registry_version,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.store.model import make_object_candidate


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _ready_bundle(
    name: str = "github-mcp",
    *,
    server: str = "print('ready')\n",
    version: str = "1.0.0",
) -> CandidateBundle:
    manifest = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": name, "kind": "mcp", "version": version},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    compiled = compile_author_snapshot(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry(f"{name}/aart.json", json.dumps(manifest)),
                _entry(f"{name}/server.py", server),
            ),
        ),
        source_alias=SourceAlias("authors"),
        source="https://git.example/servers.git",
        revision="a" * 40,
    )
    assert isinstance(compiled, Ok)
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok)
    bundle = scanned.value.active[0]
    return dataclasses.replace(bundle, candidate=assess_candidate(bundle.candidate))


def _evidence(bundle: CandidateBundle) -> tuple[tuple[object, PromotionEvidence], ...]:
    return (
        (
            bundle.candidate.id,
            PromotionEvidence(_digest("7"), _digest("8"), ("reviewed warning",)),
        ),
    )


class _RecordingPromotionPort:
    def __init__(self, snapshot: SourceSnapshot) -> None:
        self.snapshot = snapshot
        self.apply_calls = 0

    def current(self):
        return Ok(self.snapshot)

    def apply(self, command):
        self.apply_calls += 1
        projected = project_promotion(self.snapshot, command.plan)
        assert isinstance(projected, Ok)
        self.snapshot = projected.value
        return Ok(
            PromotionApplyReceipt(
                command.plan.review_digest,
                command.plan.next_workspace_digest,
                command.plan.next_registry_snapshot,
                command.plan.changed_paths,
            )
        )


class PromotionPlanningTest(unittest.TestCase):
    def test_bulk_vendoring_is_default_order_independent_and_one_transaction(self) -> None:
        first = _ready_bundle()
        second = _ready_bundle("jira-mcp", server="print('jira')\n")
        empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        evidence = _evidence(first) + _evidence(second)

        planned = plan_bulk_promotion(empty, (second, first), evidence=evidence, approved=())
        reordered = plan_bulk_promotion(empty, (first, second), evidence=evidence, approved=())

        self.assertIsInstance(planned, Ok)
        self.assertEqual(planned, reordered)
        assert isinstance(planned, Ok)
        plan = planned.value
        self.assertEqual(plan.mode, PromotionMode.VENDORED)
        paths = {str(change.path) for change in plan.changes}
        self.assertIn("artifacts/mcp/github-mcp/1.0.0/artifact.json", paths)
        self.assertIn("artifacts/mcp/github-mcp/1.0.0/payload/server.py", paths)
        self.assertIn("artifacts/mcp/jira-mcp/1.0.0/provenance.json", paths)
        self.assertIn("registry/versions/mcp/github-mcp/1.0.0.json", paths)
        self.assertIn("registry/index.json", paths)
        self.assertIn("registry/snapshot.json", paths)
        self.assertEqual(len(plan.versions), 2)
        self.assertEqual(len(plan.audits), 2)
        object_digests = {
            bundle.candidate.artifact.coordinate.artifact: make_object_candidate(
                bundle.artifact.canonical_entries
            ).value.digest
            for bundle in (first, second)
        }
        self.assertEqual(
            {item.coordinate.artifact: item.object_digest for item in plan.versions},
            object_digests,
        )
        self.assertTrue(
            all(item.registry_snapshot == plan.next_registry_snapshot for item in plan.versions)
        )

        output = _RecordingPromotionPort(empty)
        applied = finalize_promotion(plan, plan.review_digest, output=output)

        self.assertIsInstance(applied, Ok)
        self.assertEqual(output.apply_calls, 1)
        self.assertEqual(output.snapshot.origin, SnapshotOrigin.LOCAL)
        self.assertIsInstance(validate_promoted_registry(output.snapshot, plan.versions), Ok)
        self.assertEqual(load_registry_versions(output.snapshot), Ok(plan.versions))

    def test_a_registry_stays_readable_after_a_second_promotion(self) -> None:
        """A registry that can hold only one promotion transaction is not a registry.

        Every approved version record binds the registry's current content digest, and promoting
        anything rewrites the content those earlier records were bound to. A promotion that writes
        only the new records therefore leaves the whole snapshot unreadable to every consumer --
        and `update` cannot mean anything in a registry that can never hold a second version.
        """

        empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        first = _ready_bundle("github-mcp")
        promoted = plan_bulk_promotion(empty, (first,), evidence=_evidence(first), approved=())
        self.assertIsInstance(promoted, Ok, getattr(promoted, "diagnostics", ()))
        assert isinstance(promoted, Ok)
        one = project_promotion(empty, promoted.value)
        self.assertIsInstance(one, Ok, getattr(one, "diagnostics", ()))
        assert isinstance(one, Ok)
        approved = load_registry_versions(one.value)
        self.assertIsInstance(approved, Ok, getattr(approved, "diagnostics", ()))
        assert isinstance(approved, Ok)

        second = _ready_bundle("jira-mcp")
        again = plan_bulk_promotion(
            one.value, (second,), evidence=_evidence(second), approved=approved.value
        )
        self.assertIsInstance(again, Ok, getattr(again, "diagnostics", ()))
        assert isinstance(again, Ok)
        two = project_promotion(one.value, again.value)
        self.assertIsInstance(two, Ok, getattr(two, "diagnostics", ()))
        assert isinstance(two, Ok)

        readable = load_registry_versions(two.value)

        self.assertIsInstance(readable, Ok, getattr(readable, "diagnostics", ()))
        assert isinstance(readable, Ok)
        self.assertEqual(
            {str(item.coordinate) for item in readable.value},
            {"company/mcp/github-mcp@1.0.0", "company/mcp/jira-mcp@1.0.0"},
        )
        # One approved content snapshot, named by every record in it: that is what makes the
        # registry's answer to "what did you approve" a single reviewable fact.
        self.assertEqual(len({item.registry_snapshot for item in readable.value}), 1)

    def test_a_second_promotion_leaves_the_first_package_byte_identical(self) -> None:
        """Rebinding a retained record is metadata; the content at a coordinate never moves."""

        empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        first = _ready_bundle("github-mcp")
        promoted = plan_bulk_promotion(empty, (first,), evidence=_evidence(first), approved=())
        assert isinstance(promoted, Ok), promoted
        one = project_promotion(empty, promoted.value)
        assert isinstance(one, Ok), one
        approved = load_registry_versions(one.value)
        assert isinstance(approved, Ok), approved
        before = {
            str(entry.path): entry.content
            for entry in one.value.entries
            if str(entry.path).startswith("artifacts/")
        }

        second = _ready_bundle("jira-mcp")
        again = plan_bulk_promotion(
            one.value, (second,), evidence=_evidence(second), approved=approved.value
        )
        assert isinstance(again, Ok), again
        two = project_promotion(one.value, again.value)
        assert isinstance(two, Ok), two

        after = {
            str(entry.path): entry.content
            for entry in two.value.entries
            if str(entry.path).startswith("artifacts/mcp/github-mcp/")
        }
        self.assertTrue(after)
        self.assertEqual(after, {path: before[path] for path in after})

    def test_review_mismatch_cannot_reach_the_atomic_output_port(self) -> None:
        bundle = _ready_bundle()
        empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        planned = plan_bulk_promotion(empty, (bundle,), evidence=_evidence(bundle), approved=())
        assert isinstance(planned, Ok)
        output = _RecordingPromotionPort(empty)

        refused = finalize_promotion(planned.value, _digest("0"), output=output)

        self.assertIsInstance(refused, Err)
        self.assertEqual(output.apply_calls, 0)

    def test_existing_coordinate_with_different_content_is_a_hard_conflict(self) -> None:
        published = _ready_bundle(server="print('old')\n")
        changed = _ready_bundle(server="print('new')\n")
        approved = registry_version_from_candidate(
            published.candidate,
            object_digest=make_object_candidate(published.artifact.canonical_entries).value.digest,
            registry_snapshot=_digest("1"),
            mode=PromotionMode.VENDORED,
        )

        planned = plan_bulk_promotion(
            SourceSnapshot(SnapshotOrigin.LOCAL, ()),
            (changed,),
            evidence=_evidence(changed),
            approved=(approved,),
        )

        self.assertIsInstance(planned, Err)
        assert isinstance(planned, Err)
        self.assertIn("immutable", planned.diagnostics[0].message)

    def test_existing_version_path_with_different_bytes_is_a_hard_conflict(self) -> None:
        bundle = _ready_bundle()
        occupied = SourceSnapshot(
            SnapshotOrigin.LOCAL,
            (_entry("artifacts/mcp/github-mcp/1.0.0/artifact.json", "{}\n"),),
        )

        planned = plan_bulk_promotion(
            occupied,
            (bundle,),
            evidence=_evidence(bundle),
            approved=(),
        )

        self.assertIsInstance(planned, Err)

    def test_referenced_mode_is_explicit_and_never_vendors_payload(self) -> None:
        bundle = _ready_bundle()
        planned = plan_bulk_promotion(
            SourceSnapshot(SnapshotOrigin.LOCAL, ()),
            (bundle,),
            evidence=_evidence(bundle),
            approved=(),
            mode=PromotionMode.REFERENCED,
        )

        self.assertIsInstance(planned, Ok)
        assert isinstance(planned, Ok)
        paths = {str(change.path) for change in planned.value.changes}
        self.assertIn("references/mcp/github-mcp/1.0.0.json", paths)
        self.assertFalse(any(path.startswith("artifacts/") for path in paths))
        self.assertEqual(planned.value.mode, PromotionMode.REFERENCED)

    def test_lifecycle_metadata_changes_without_mutating_immutable_payload(self) -> None:
        bundle = _ready_bundle()
        empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        promoted = plan_bulk_promotion(empty, (bundle,), evidence=_evidence(bundle), approved=())
        assert isinstance(promoted, Ok)
        registry = project_promotion(empty, promoted.value)
        assert isinstance(registry, Ok)
        version = promoted.value.versions[0]
        deprecated = deprecate_registry_version(
            version,
            reason="Use the supported replacement",
            replacement="company/mcp/github-mcp@2.0.0",
        )

        planned = plan_registry_lifecycle(registry.value, (version,), (deprecated,))

        self.assertIsInstance(planned, Ok)
        assert isinstance(planned, Ok)
        self.assertEqual(planned.value.registry_snapshot, version.registry_snapshot)
        self.assertTrue(
            all(str(change.path).startswith("registry/") for change in planned.value.changes)
        )
        updated = project_lifecycle_update(registry.value, planned.value)
        self.assertIsInstance(updated, Ok)
        assert isinstance(updated, Ok)
        before_payload = {
            str(item.path): item.content
            for item in registry.value.entries
            if str(item.path).startswith("artifacts/")
        }
        after_payload = {
            str(item.path): item.content
            for item in updated.value.entries
            if str(item.path).startswith("artifacts/")
        }
        self.assertEqual(before_payload, after_payload)
        self.assertIsInstance(validate_promoted_registry(updated.value, (deprecated,)), Ok)

    def test_lifecycle_plan_refuses_any_immutable_version_change(self) -> None:
        bundle = _ready_bundle()
        empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        promoted = plan_bulk_promotion(empty, (bundle,), evidence=_evidence(bundle), approved=())
        assert isinstance(promoted, Ok)
        registry = project_promotion(empty, promoted.value)
        assert isinstance(registry, Ok)
        version = promoted.value.versions[0]
        invalid = dataclasses.replace(
            revoke_registry_version(version, reason="Unsafe"),
            payload_digest=_digest("9"),
        )

        planned = plan_registry_lifecycle(registry.value, (version,), (invalid,))

        self.assertIsInstance(planned, Err)

    def test_registry_validation_detects_vendored_payload_tampering(self) -> None:
        bundle = _ready_bundle()
        empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
        promoted = plan_bulk_promotion(empty, (bundle,), evidence=_evidence(bundle), approved=())
        assert isinstance(promoted, Ok)
        registry = project_promotion(empty, promoted.value)
        assert isinstance(registry, Ok)
        entries = tuple(
            dataclasses.replace(item, content=b"tampered\n")
            if str(item.path) == "artifacts/mcp/github-mcp/1.0.0/payload/server.py"
            else item
            for item in registry.value.entries
        )

        validated = validate_promoted_registry(
            SourceSnapshot(registry.value.origin, entries),
            promoted.value.versions,
        )

        self.assertIsInstance(validated, Err)


if __name__ == "__main__":
    unittest.main()
