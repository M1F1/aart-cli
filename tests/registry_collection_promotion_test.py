"""A Registry defines a Collection, publishes it, bumps it and reads it back (§173.3, D-430).

A Collection is the Registry's own curation of artifacts it already approved. Each version pins
the exact approved version of every member, and is published as an artifact is: a package, a
version record of kind `collection` and an audit record, in one reviewed transaction. A promotion
that approves a newer member version publishes the Collection's next version with it (INV-266).
"""

from __future__ import annotations

import dataclasses
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.promotion import (
    PromotionEvidence,
    PromotionSourceKind,
    _version_content,
    load_registry_versions,
    plan_bulk_promotion,
    project_promotion,
    read_registry_version_records,
    registry_catalog_entries,
    registry_state_digest,
)
from aart_cli.application.registry_collections import (
    plan_collection_definition,
    read_registry_collection,
)
from aart_cli.domain.identifiers import ArtifactIdentity, ObjectDigest, SourceAlias
from aart_cli.domain.registry import RegistryContentMode
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from tests.promotion_planning_test import _entry, _evidence, _ready_bundle

_COMPANY = SourceAlias("company")
_EMPTY = SourceSnapshot(SnapshotOrigin.LOCAL, ())
_GITHUB = ArtifactIdentity("mcp", "github-mcp")
_OTHER = ArtifactIdentity("mcp", "other-mcp")


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _promote(
    registry: SourceSnapshot, *bundles, collections=(), mode=RegistryContentMode.SELF_CONTAINED
):
    planned = plan_bulk_promotion(
        registry,
        bundles,
        evidence=tuple(item for bundle in bundles for item in _evidence(bundle))
        + _collection_evidence(*collections),
        approved=_approved(registry),
        mode=mode,
        collections=collections,
    )
    assert isinstance(planned, Ok), planned
    projected = project_promotion(registry, planned.value)
    assert isinstance(projected, Ok), projected
    return planned.value, projected.value


def _registry_with_members() -> SourceSnapshot:
    """A Registry that has approved `mcp/github-mcp@1.0.0` and `mcp/other-mcp@1.0.0`."""

    return _promote(_EMPTY, _ready_bundle("github-mcp"), _ready_bundle("other-mcp"))[1]


def _approved(registry: SourceSnapshot):
    loaded = load_registry_versions(registry)
    assert isinstance(loaded, Ok), loaded
    return loaded.value


def _define(registry, *members, name="data-engineer", summary="Approved data engineering tools."):
    return plan_collection_definition(
        _approved(registry),
        registry,
        target_registry=_COMPANY,
        name=name,
        summary=summary,
        members=members or (_GITHUB,),
    )


def _change(registry, *members, **keywords):
    defined = _define(registry, *members, **keywords)
    assert isinstance(defined, Ok) and defined.value is not None, defined
    return defined.value


def _collection_evidence(*collections):
    return tuple(
        (item.id, PromotionEvidence(_digest("5"), _digest("6"), ())) for item in collections
    )


def _published(registry: SourceSnapshot, *collections, mode=RegistryContentMode.SELF_CONTAINED):
    return _promote(registry, collections=collections, mode=mode)


def _read(projected: SourceSnapshot, version: str = "1.0.0"):
    record = next(
        item
        for item in _approved(projected)
        if str(item.coordinate) == f"company/collection/data-engineer@{version}"
    )
    read = read_registry_collection(projected, record)
    assert isinstance(read, Ok), read
    return read.value


class CollectionDefinitionTest(unittest.TestCase):
    def test_a_new_collection_pins_each_member_s_approved_version_at_1_0_0(self) -> None:
        change = _change(_registry_with_members(), _GITHUB, _OTHER)

        self.assertEqual(change.version, "1.0.0")
        self.assertEqual(
            [str(item) for item in change.members],
            ["mcp/github-mcp@1.0.0", "mcp/other-mcp@1.0.0"],
        )

    def test_a_member_pins_its_highest_approved_version(self) -> None:
        registry = _promote(
            _registry_with_members(),
            _ready_bundle("github-mcp", version="1.0.1", server="print('next')\n"),
        )[1]

        self.assertEqual(
            [str(item) for item in _change(registry).members], ["mcp/github-mcp@1.0.1"]
        )

    def test_a_member_the_registry_has_not_approved_is_refused_by_name(self) -> None:
        defined = _define(_registry_with_members(), _GITHUB, ArtifactIdentity("skill", "absent"))

        assert isinstance(defined, Err), defined
        self.assertEqual(
            defined.diagnostics[0].message, "skill/absent has no approved version in company"
        )

    def test_a_collection_cannot_be_a_member(self) -> None:
        defined = _define(_registry_with_members(), ArtifactIdentity("collection", "other"))

        self.assertIsInstance(defined, Err)

    def test_a_new_collection_needs_a_summary(self) -> None:
        self.assertIsInstance(_define(_registry_with_members(), summary=None), Err)

    def test_the_same_members_and_summary_change_nothing(self) -> None:
        registry = _registry_with_members()
        _, projected = _published(registry, _change(registry))

        unchanged = _define(projected)

        self.assertEqual(unchanged, Ok(None))

    def test_a_changed_definition_is_the_next_registry_version(self) -> None:
        registry = _registry_with_members()
        _, projected = _published(registry, _change(registry))

        changed = _change(projected, _GITHUB, _OTHER, summary=None)

        self.assertEqual(changed.version, "1.0.1")
        self.assertEqual(changed.summary, "Approved data engineering tools.")


class CollectionPromotionTest(unittest.TestCase):
    def test_approval_writes_a_package_a_version_record_and_an_audit(self) -> None:
        registry = _registry_with_members()
        change = _change(registry)

        plan, _ = _published(registry, change)

        written = {str(item.path) for item in plan.changes if item.kind.value != "unchanged"}
        self.assertIn("artifacts/collection/data-engineer/1.0.0/collection.json", written)
        self.assertIn("registry/versions/collection/data-engineer/1.0.0.json", written)
        self.assertIn(f"registry/promotions/{change.id.value}.json", written)
        (version,) = plan.versions
        self.assertEqual(str(version.coordinate), "company/collection/data-engineer@1.0.0")
        self.assertEqual(version.candidate_id, change.id)
        self.assertEqual(version.canonical_digest, change.canonical_digest)
        (audit,) = plan.audits
        self.assertIs(audit.source_provenance.kind, PromotionSourceKind.LOCAL_SNAPSHOT)
        self.assertEqual(
            audit.source_provenance.local_snapshot_digest, audit.registry_snapshot_before
        )

    def test_the_registry_reads_it_back_with_its_members_pinned(self) -> None:
        registry = _registry_with_members()
        _, projected = _published(registry, _change(registry))

        read = _read(projected)

        self.assertEqual(str(read.coordinate), "company/collection/data-engineer@1.0.0")
        self.assertEqual(read.summary, "Approved data engineering tools.")
        self.assertEqual([str(item.request) for item in read.members], ["mcp/github-mcp@1.0.0"])

    def test_a_collection_is_vendored_even_in_a_referenced_transaction(self) -> None:
        registry = _registry_with_members()

        plan, projected = _published(
            registry, _change(registry), mode=RegistryContentMode.PINNED_REFERENCE
        )

        (version,) = plan.versions
        self.assertIs(version.mode, RegistryContentMode.SELF_CONTAINED)
        self.assertIsInstance(load_registry_versions(projected), Ok)

    def test_a_published_collection_version_is_immutable(self) -> None:
        registry = _registry_with_members()
        change = _change(registry)
        _, projected = _published(registry, change)

        again = plan_bulk_promotion(
            projected,
            (),
            evidence=_collection_evidence(change),
            approved=_approved(projected),
            collections=(change,),
        )

        assert isinstance(again, Err), again
        self.assertIn("already contains this exact candidate", again.diagnostics[0].message)

    def test_a_tampered_collection_package_makes_the_registry_unreadable(self) -> None:
        """Even when every record and catalog was rewritten to agree with the changed bytes.

        The content digest alone catches a plain edit. What only the package check catches is a
        Registry whose metadata was rebound, consistently, over a Collection nobody reviewed.
        """

        registry = _registry_with_members()
        _, projected = _published(registry, _change(registry))
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
        registry = _registry_with_members()
        _, projected = _published(registry, _change(registry))
        version = next(
            item for item in _approved(projected) if item.coordinate.artifact.kind == "collection"
        )
        stale = dataclasses.replace(version, canonical_digest=_digest("9"))

        self.assertIsInstance(read_registry_collection(projected, stale), Err)


class CollectionAutoBumpTest(unittest.TestCase):
    """INV-266: a member's new approved version is the Collection's next version, at once."""

    def _with_collection(self, *members):
        registry = _registry_with_members()
        return _published(registry, _change(registry, *members))[1]

    def test_a_member_s_new_version_publishes_the_collection_s_next_version(self) -> None:
        registry = self._with_collection(_GITHUB, _OTHER)
        bundle = _ready_bundle("github-mcp", version="1.0.1", server="print('next')\n")

        plan, projected = _promote(registry, bundle)

        self.assertEqual(
            sorted(str(item.coordinate) for item in plan.versions),
            ["company/collection/data-engineer@1.0.1", "company/mcp/github-mcp@1.0.1"],
        )
        self.assertEqual(
            [str(item.request) for item in _read(projected, "1.0.1").members],
            ["mcp/github-mcp@1.0.1", "mcp/other-mcp@1.0.0"],
        )
        self.assertEqual(_read(projected, "1.0.1").summary, "Approved data engineering tools.")

    def test_the_bump_is_audited_with_the_member_s_policy(self) -> None:
        registry = self._with_collection()
        bundle = _ready_bundle("github-mcp", version="1.0.1", server="print('next')\n")

        plan, _ = _promote(registry, bundle)

        (collection,) = (
            item for item in plan.versions if item.coordinate.artifact.kind == "collection"
        )
        bump = next(item for item in plan.audits if item.candidate_id == collection.candidate_id)
        ((_, member_evidence),) = _evidence(bundle)
        self.assertEqual(bump.effective_policy_digest, member_evidence.effective_policy_digest)

    def test_a_promotion_of_a_non_member_bumps_nothing(self) -> None:
        registry = self._with_collection(_GITHUB)

        plan, _ = _promote(
            registry, _ready_bundle("other-mcp", version="1.0.1", server="print('next')\n")
        )

        self.assertEqual(
            [str(item.coordinate) for item in plan.versions], ["company/mcp/other-mcp@1.0.1"]
        )

    def test_a_collection_the_transaction_defines_is_not_bumped_twice(self) -> None:
        registry = self._with_collection(_GITHUB)
        bundle = _ready_bundle("github-mcp", version="1.0.1", server="print('next')\n")
        change = _change(registry, _GITHUB, _OTHER)

        plan, _ = _promote(registry, bundle, collections=(change,))

        self.assertEqual(
            sorted(str(item.coordinate) for item in plan.versions),
            ["company/collection/data-engineer@1.0.1", "company/mcp/github-mcp@1.0.1"],
        )

    @given(st.integers(min_value=1, max_value=4))
    def test_each_member_bump_is_one_collection_version(self, bumps: int) -> None:
        registry = self._with_collection()
        for step in range(1, bumps + 1):
            bundle = _ready_bundle("github-mcp", version=f"1.0.{step}", server=f"print({step})\n")
            registry = _promote(registry, bundle)[1]

        collections = sorted(
            str(item.coordinate)
            for item in _approved(registry)
            if item.coordinate.artifact.kind == "collection"
        )

        self.assertEqual(
            collections,
            [f"company/collection/data-engineer@1.0.{step}" for step in range(bumps + 1)],
        )
        self.assertEqual(
            [str(item.request) for item in _read(registry, f"1.0.{bumps}").members],
            [f"mcp/github-mcp@1.0.{bumps}"],
        )


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


if __name__ == "__main__":
    unittest.main()
