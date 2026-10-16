"""Promotion publishes a Collection, and the Registry reads it back (§173.3, B-067 layers 1–2).

A Collection Candidate is approved into a Registry exactly as an artifact is: a package, a version
record of kind `collection` and an audit record, in one reviewed transaction. Its members are its
dependencies, so approval resolves each against the target Registry and refuses one that resolves
to nothing, naming it (D-425, D-427).
"""

from __future__ import annotations

import dataclasses
import json
import unittest

from aart_cli.application.maintainer import reconcile_source_scan
from aart_cli.application.promotion import (
    PromotionEvidence,
    _version_content,
    load_registry_versions,
    plan_bulk_promotion,
    project_promotion,
    read_registry_version_records,
    registry_catalog_entries,
    registry_state_digest,
)
from aart_cli.application.registry_collections import (
    COLLECTION_MEMBER_UNRESOLVED,
    assess_collection_candidate,
    read_registry_collection,
)
from aart_cli.application.registry_versions import ApprovedRegistryVersions
from aart_cli.domain.candidates import CandidateState
from aart_cli.domain.identifiers import ObjectDigest, SourceAlias
from aart_cli.domain.registry import PromotionMode
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import compile_author_source
from aart_cli.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from tests.promotion_planning_test import _entry, _evidence, _ready_bundle

_COMPANY = SourceAlias("company")
_EMPTY = SourceSnapshot(SnapshotOrigin.LOCAL, ())


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _registry_with_member() -> SourceSnapshot:
    """A Registry that has approved `mcp/github-mcp@1.0.0`, the member every Collection names."""

    member = _ready_bundle("github-mcp")
    planned = plan_bulk_promotion(_EMPTY, (member,), evidence=_evidence(member), approved=())
    assert isinstance(planned, Ok), planned
    projected = project_promotion(_EMPTY, planned.value)
    assert isinstance(projected, Ok), projected
    return projected.value


def _approved(registry: SourceSnapshot):
    loaded = load_registry_versions(registry)
    assert isinstance(loaded, Ok), loaded
    return loaded.value


def _collection(registry: SourceSnapshot, *members: str, name: str = "data-engineer"):
    """The Collection Candidate a Sync against `registry` would produce, assessed for approval."""

    approved = _approved(registry)
    versions = ApprovedRegistryVersions(approved, _COMPANY)
    manifest = {
        "schema": "aart-cli.dev/collection/v1",
        "name": name,
        "summary": "Approved data engineering tools.",
        "artifacts": list(members or ("mcp/github-mcp@^1",)),
    }
    compiled = compile_author_source(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (_entry(f"collections/{name}/aart-cli.json", json.dumps(manifest)),),
        ),
        source_alias=SourceAlias("authors"),
        source="https://git.example/collections.git",
        revision="c" * 40,
        versions=versions,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "c" * 40,
        compiled.value.artifacts,
        previous=(),
        approved=approved,
        target_registry=_COMPANY,
        collections=compiled.value.collections,
    )
    assert isinstance(scanned, Ok), scanned
    return assess_collection_candidate(scanned.value.collection_active[0], versions)


def _collection_evidence(*collections):
    return tuple(
        (item.id, PromotionEvidence(_digest("5"), _digest("6"), ())) for item in collections
    )


def _published(registry: SourceSnapshot, *collections, mode=PromotionMode.VENDORED):
    planned = plan_bulk_promotion(
        registry,
        (),
        evidence=_collection_evidence(*collections),
        approved=_approved(registry),
        mode=mode,
        collections=collections,
    )
    assert isinstance(planned, Ok), planned
    projected = project_promotion(registry, planned.value)
    assert isinstance(projected, Ok), projected
    return planned.value, projected.value


class CollectionAssessmentTest(unittest.TestCase):
    def test_a_collection_whose_members_are_approved_is_ready(self) -> None:
        collection = _collection(_registry_with_member())

        self.assertIs(collection.state, CandidateState.READY)
        self.assertEqual(collection.findings, ())

    def test_a_member_the_registry_has_not_approved_blocks_it_and_is_named(self) -> None:
        collection = _collection(_registry_with_member(), "mcp/github-mcp@^1", "skill/absent")

        self.assertIs(collection.state, CandidateState.INVALID)
        self.assertEqual(
            [(item.code, item.message) for item in collection.findings],
            [
                (
                    COLLECTION_MEMBER_UNRESOLVED,
                    "member skill/absent matches no approved version in company",
                )
            ],
        )

    def test_a_constraint_no_approved_version_satisfies_blocks_it(self) -> None:
        collection = _collection(_registry_with_member(), "mcp/github-mcp@^2")

        self.assertIs(collection.state, CandidateState.INVALID)


class CollectionPromotionTest(unittest.TestCase):
    def test_approval_writes_a_package_a_version_record_and_an_audit(self) -> None:
        registry = _registry_with_member()
        collection = _collection(registry)

        plan, projected = _published(registry, collection)

        written = {str(item.path) for item in plan.changes if item.kind.value != "unchanged"}
        self.assertIn("artifacts/collection/data-engineer/1.0.0/collection.json", written)
        self.assertIn("registry/versions/collection/data-engineer/1.0.0.json", written)
        self.assertIn(f"registry/promotions/{collection.id.value}.json", written)
        (version,) = plan.versions
        self.assertEqual(str(version.coordinate), "company/collection/data-engineer@1.0.0")
        self.assertEqual(version.candidate_id, collection.id)
        self.assertEqual(version.canonical_digest, collection.canonical_digest)

    def test_the_registry_reads_it_back_as_the_collection_that_was_approved(self) -> None:
        registry = _registry_with_member()
        collection = _collection(registry)
        _, projected = _published(registry, collection)

        approved = _approved(projected)
        version = next(item for item in approved if item.coordinate.artifact.kind == "collection")
        read = read_registry_collection(projected, version)

        assert isinstance(read, Ok), read
        self.assertEqual(str(read.value.coordinate), "company/collection/data-engineer@1.0.0")
        self.assertEqual(read.value.summary, "Approved data engineering tools.")
        self.assertEqual([str(item.request) for item in read.value.members], ["mcp/github-mcp@^1"])
        self.assertEqual(read.value.registry_snapshot, version.registry_snapshot)

    def test_a_sync_after_approval_records_the_collection_as_promoted(self) -> None:
        registry = _registry_with_member()
        _, projected = _published(registry, _collection(registry))

        self.assertIs(_collection_state_after_sync(projected), CandidateState.PROMOTED)

    def test_a_collection_is_vendored_even_in_a_referenced_transaction(self) -> None:
        registry = _registry_with_member()

        plan, projected = _published(registry, _collection(registry), mode=PromotionMode.REFERENCED)

        (version,) = plan.versions
        self.assertIs(version.mode, PromotionMode.VENDORED)
        self.assertIsInstance(load_registry_versions(projected), Ok)

    def test_a_collection_and_an_artifact_publish_in_one_transaction(self) -> None:
        registry = _registry_with_member()
        collection = _collection(registry)
        artifact = _ready_bundle("other-mcp")

        planned = plan_bulk_promotion(
            registry,
            (artifact,),
            evidence=_evidence(artifact) + _collection_evidence(collection),
            approved=_approved(registry),
            collections=(collection,),
        )

        assert isinstance(planned, Ok), planned
        self.assertEqual(
            sorted(str(item.coordinate) for item in planned.value.versions),
            ["company/collection/data-engineer@1.0.0", "company/mcp/other-mcp@1.0.0"],
        )

    def test_an_invalid_collection_is_refused(self) -> None:
        registry = _registry_with_member()
        collection = _collection(registry, "skill/absent")

        planned = plan_bulk_promotion(
            registry,
            (),
            evidence=_collection_evidence(collection),
            approved=_approved(registry),
            collections=(collection,),
        )

        self.assertIsInstance(planned, Err)

    def test_a_published_collection_version_is_immutable(self) -> None:
        registry = _registry_with_member()
        collection = _collection(registry)
        _, projected = _published(registry, collection)

        again = plan_bulk_promotion(
            projected,
            (),
            evidence=_collection_evidence(collection),
            approved=_approved(projected),
            collections=(collection,),
        )

        assert isinstance(again, Err), again
        self.assertIn("already contains this exact candidate", again.diagnostics[0].message)

    def test_a_tampered_collection_package_makes_the_registry_unreadable(self) -> None:
        """Even when every record and catalog was rewritten to agree with the changed bytes.

        The content digest alone catches a plain edit. What only the package check catches is a
        Registry whose metadata was rebound, consistently, over a Collection nobody reviewed.
        """

        registry = _registry_with_member()
        _, projected = _published(registry, _collection(registry))
        path = "artifacts/collection/data-engineer/1.0.0/collection.json"
        tampered = SourceSnapshot(
            projected.origin,
            tuple(
                _entry(path, item.content.decode().replace("Approved", "Unreviewed"))
                if str(item.path) == path
                else item
                for item in projected.entries
            ),
        )

        loaded = load_registry_versions(_rebound(tampered))

        assert isinstance(loaded, Err), loaded
        self.assertIn("published Collection package digest is invalid", str(loaded.diagnostics))

    def test_reading_a_package_whose_bytes_differ_from_the_record_is_refused(self) -> None:
        registry = _registry_with_member()
        _, projected = _published(registry, _collection(registry))
        version = next(
            item for item in _approved(projected) if item.coordinate.artifact.kind == "collection"
        )
        stale = dataclasses.replace(version, canonical_digest=_digest("9"))

        self.assertIsInstance(read_registry_collection(projected, stale), Err)


def _rebound(snapshot: SourceSnapshot) -> SourceSnapshot:
    """Every version record and catalog rewritten to bind the snapshot's current content."""

    digest = registry_state_digest(snapshot)
    records = read_registry_version_records(snapshot)
    assert isinstance(digest, Ok) and isinstance(records, Ok)
    versions = tuple(
        dataclasses.replace(item, registry_snapshot=digest.value) for item in records.value
    )
    catalogs = registry_catalog_entries(snapshot, versions)
    assert isinstance(catalogs, Ok)
    rewritten = {
        **{
            f"registry/versions/{item.coordinate.artifact.kind}/{item.coordinate.artifact.name}/"
            f"{item.coordinate.version}.json": _version_content(item)
            for item in versions
        },
        **dict(catalogs.value),
    }
    return SourceSnapshot(
        snapshot.origin,
        tuple(
            _entry(str(item.path), rewritten[str(item.path)].decode())
            if str(item.path) in rewritten
            else item
            for item in snapshot.entries
        ),
    )


def _collection_state_after_sync(registry: SourceSnapshot) -> CandidateState:
    return _resynced(registry).state


def _resynced(registry: SourceSnapshot):
    approved = _approved(registry)
    manifest = {
        "schema": "aart-cli.dev/collection/v1",
        "name": "data-engineer",
        "summary": "Approved data engineering tools.",
        "artifacts": ["mcp/github-mcp@^1"],
    }
    compiled = compile_author_source(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (_entry("collections/data-engineer/aart-cli.json", json.dumps(manifest)),),
        ),
        source_alias=SourceAlias("authors"),
        source="https://git.example/collections.git",
        revision="c" * 40,
        versions=ApprovedRegistryVersions(approved, _COMPANY),
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "c" * 40,
        compiled.value.artifacts,
        previous=(),
        approved=approved,
        target_registry=_COMPANY,
        collections=compiled.value.collections,
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value.collection_active[0]


if __name__ == "__main__":
    unittest.main()
