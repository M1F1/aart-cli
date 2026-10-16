"""Collection authoring uses the same explicit manifest discovery boundary.

A Collection manifest carries no version, like any source manifest (§173.1). Its members are its
dependencies, so the exact version each resolves to is part of what the Collection is: a member's
new approved version is the Collection's next version too (D-425).
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from aart_cli.application.registry_versions import ApprovedRegistryVersions
from aart_cli.domain.identifiers import ArtifactIdentity, SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import compile_author_snapshot, compile_author_source
from aart_cli.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from tests.authoring_compiler_test import _file, _json_manifest
from tests.fixture_versions import with_fixture_versions
from tests.registry_versions_test import _approved


def _collection(*, version: str | None = None) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "aart-cli.dev/collection/v1",
        "name": "data-engineer",
        "summary": "Approved data engineering tools.",
        "artifacts": ["company/mcp/github@^2", "company/skill/code-review@^1"],
    }
    if version is not None:
        document["version"] = version
    return document


def _compile(snapshot: SourceSnapshot, versions=None):
    return with_fixture_versions(compile_author_source)(
        snapshot,
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
        **({} if versions is None else {"versions": versions}),
    )


_GITHUB = ArtifactIdentity("mcp", "github")
_REVIEW = ArtifactIdentity("skill", "code-review")
_DATA_ENGINEER = ArtifactIdentity("collection", "data-engineer")


def _only_collection(approved) -> SourceSnapshot:
    snapshot = SourceSnapshot(
        SnapshotOrigin.IMMUTABLE_GIT,
        (_file("collections/data-engineer/aart-cli.json", json.dumps(_collection())),),
    )
    compiled = _compile(snapshot, ApprovedRegistryVersions(approved, SourceAlias("company")))
    assert isinstance(compiled, Ok), compiled
    return compiled.value.collections[0]


class AuthoringCollectionCompilerTest(unittest.TestCase):
    def test_one_source_compiles_artifacts_and_versioned_collections_without_conflating_them(
        self,
    ) -> None:
        snapshot = SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _json_manifest("github/aart-cli.json"),
                _file("github/server.py", "print('x')\n"),
                _file("github/src/client.py", "client\n"),
                _file("github/requirements.txt", "dependency\n"),
                _file("collections/data-engineer/aart-cli.json", json.dumps(_collection())),
            ),
        )

        compiled = _compile(snapshot)
        artifacts_only = with_fixture_versions(compile_author_snapshot)(
            snapshot,
            source_alias=SourceAlias("authors"),
            source="https://git.example/authors.git",
            revision="a" * 40,
        )

        self.assertIsInstance(compiled, Ok)
        self.assertIsInstance(artifacts_only, Ok)
        assert isinstance(compiled, Ok) and isinstance(artifacts_only, Ok)
        self.assertEqual(len(compiled.value.artifacts), 1)
        self.assertEqual(compiled.value.artifacts, artifacts_only.value)
        self.assertEqual(len(compiled.value.collections), 1)
        collection = compiled.value.collections[0]
        self.assertEqual(collection.name, "data-engineer")
        self.assertEqual(collection.version, "1.0.0")
        self.assertEqual(
            tuple(str(item) for item in collection.members),
            ("company/mcp/github@^2", "company/skill/code-review@^1"),
        )
        self.assertEqual(str(collection.manifest_path), "collections/data-engineer/aart-cli.json")

    def test_a_collection_that_writes_a_version_is_refused(self) -> None:
        for version in ("2.1.0", "latest"):
            with self.subTest(version=version):
                snapshot = SourceSnapshot(
                    SnapshotOrigin.IMMUTABLE_GIT,
                    (
                        _file(
                            "collections/data-engineer/aart-cli.json",
                            json.dumps(_collection(version=version)),
                        ),
                    ),
                )

                compiled = _compile(snapshot)

                self.assertIsInstance(compiled, Err)
                assert isinstance(compiled, Err)
                self.assertIn("the Registry assigns versions", compiled.diagnostics[0].message)

    def test_collection_compilation_is_deterministic_under_snapshot_order(self) -> None:
        first = _file("collections/first/aart-cli.json", json.dumps(_collection()))
        second_document = _collection() | {"name": "second"}
        second = _file("collections/second/aart-cli.json", json.dumps(second_document))

        left = _compile(SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, (second, first)))
        right = _compile(SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, (first, second)))

        self.assertEqual(left, right)


class CollectionVersionFollowsItsMembersTest(unittest.TestCase):
    def test_unchanged_members_keep_the_collection_s_version(self) -> None:
        members = (
            _approved("2.0.0", "a", identity=_GITHUB),
            _approved("1.0.0", "b", identity=_REVIEW),
        )
        first = _only_collection(members)
        published = replace(
            _approved("1.0.0", "x", identity=_DATA_ENGINEER), input_digest=first.input_digest
        )

        again = _only_collection((*members, published))

        self.assertEqual(first.version, "1.0.0")
        self.assertEqual(again.version, "1.0.0")
        self.assertEqual(again.input_digest, first.input_digest)

    def test_a_member_s_new_version_is_the_collection_s_next_version(self) -> None:
        members = (
            _approved("2.0.0", "a", identity=_GITHUB),
            _approved("1.0.0", "b", identity=_REVIEW),
        )
        first = _only_collection(members)
        published = replace(
            _approved("1.0.0", "x", identity=_DATA_ENGINEER), input_digest=first.input_digest
        )

        moved = _only_collection((*members, published, _approved("2.0.1", "c", identity=_GITHUB)))

        self.assertNotEqual(moved.input_digest, first.input_digest)
        self.assertEqual(moved.version, "1.0.1")

    def test_a_new_version_outside_a_member_s_constraint_changes_nothing(self) -> None:
        members = (
            _approved("2.0.0", "a", identity=_GITHUB),
            _approved("1.0.0", "b", identity=_REVIEW),
        )
        first = _only_collection(members)

        beyond = _only_collection((*members, _approved("3.0.0", "c", identity=_GITHUB)))

        self.assertEqual(beyond.input_digest, first.input_digest)


if __name__ == "__main__":
    unittest.main()
