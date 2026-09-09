"""CP-06 canonical Selection, Collection and ownership values."""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.domain.identifiers import ArtifactIdentity, ObjectDigest, SourceAlias
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    Collection,
    CollectionCoordinate,
    CollectionMember,
    OwnershipKind,
    OwnershipReason,
    VersionConstraint,
)


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


class SelectionDomainTest(unittest.TestCase):
    def test_selection_is_frozen_deterministic_and_distinct_from_resolution(self) -> None:
        github = ArtifactRequest(
            ArtifactIdentity("mcp", "github"),
            VersionConstraint("^2"),
            SourceAlias("company"),
        )
        jira = ArtifactRequest(
            ArtifactIdentity("mcp", "jira"),
            VersionConstraint(">=3,<4"),
            SourceAlias("company"),
        )
        collection = CollectionCoordinate(SourceAlias("company"), "data-engineer", "2.1.0")

        selection = ArtifactSelection((jira, github, github), (collection, collection))

        self.assertEqual(selection.artifacts, (github, jira))
        self.assertEqual(selection.collections, (collection,))
        self.assertEqual(selection.derived_from, ())
        self.assertTrue(selection.represents_exact_collections)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            selection.artifacts = ()  # type: ignore[misc]

    def test_collection_is_versioned_declarative_and_member_order_is_canonical(self) -> None:
        github = CollectionMember(
            ArtifactRequest(
                ArtifactIdentity("mcp", "github"),
                VersionConstraint("^2"),
                SourceAlias("company"),
            )
        )
        jira = CollectionMember(
            ArtifactRequest(
                ArtifactIdentity("mcp", "jira"),
                VersionConstraint("^3"),
                SourceAlias("company"),
            )
        )

        collection = Collection(
            CollectionCoordinate(SourceAlias("company"), "data-engineer", "2.1.0"),
            "Data Engineer Toolkit",
            (jira, github, github),
            _digest("a"),
        )

        self.assertEqual(collection.members, (github, jira))
        self.assertEqual(str(collection.coordinate), "company/collection/data-engineer@2.1.0")

    def test_partial_collection_selection_is_custom_not_incomplete_exact_collection(self) -> None:
        collection = CollectionCoordinate(SourceAlias("company"), "data-engineer", "2.1.0")
        selected_member = ArtifactRequest(
            ArtifactIdentity("mcp", "github"),
            VersionConstraint("^2"),
            SourceAlias("company"),
        )

        custom = ArtifactSelection((selected_member,), derived_from=(collection,))

        self.assertFalse(custom.represents_exact_collections)
        self.assertEqual(custom.collections, ())
        self.assertEqual(custom.derived_from, (collection,))

    def test_ownership_reasons_are_typed_and_canonical(self) -> None:
        reasons = {
            OwnershipReason(OwnershipKind.DEPENDENCY, "company/mcp/parent@1.0.0"),
            OwnershipReason(OwnershipKind.DIRECT, "company/mcp/github@^2"),
            OwnershipReason(
                OwnershipKind.COLLECTION,
                "company/collection/data-engineer@2.1.0",
            ),
        }

        self.assertEqual(
            tuple(item.kind for item in sorted(reasons, key=lambda item: item.sort_key)),
            (
                OwnershipKind.COLLECTION,
                OwnershipKind.DEPENDENCY,
                OwnershipKind.DIRECT,
            ),
        )


if __name__ == "__main__":
    unittest.main()
