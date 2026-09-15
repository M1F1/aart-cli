"""Versioned Collection authoring uses the same explicit manifest discovery boundary."""

from __future__ import annotations

import json
import unittest

from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot, compile_author_source
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from tests.authoring_compiler_test import _file, _json_manifest


def _collection(*, version: str | None = "2.1.0") -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "aart.dev/collection/v1",
        "name": "data-engineer",
        "summary": "Approved data engineering tools.",
        "artifacts": ["company/mcp/github@^2", "company/skill/code-review@^1"],
    }
    if version is not None:
        document["version"] = version
    return document


def _compile(snapshot: SourceSnapshot):
    return compile_author_source(
        snapshot,
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
    )


class AuthoringCollectionCompilerTest(unittest.TestCase):
    def test_one_source_compiles_artifacts_and_versioned_collections_without_conflating_them(
        self,
    ) -> None:
        snapshot = SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _json_manifest("github/aart.json"),
                _file("github/server.py", "print('x')\n"),
                _file("github/src/client.py", "client\n"),
                _file("github/requirements.txt", "dependency\n"),
                _file("collections/data-engineer/aart.json", json.dumps(_collection())),
            ),
        )

        compiled = _compile(snapshot)
        artifacts_only = compile_author_snapshot(
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
        self.assertEqual(collection.version, "2.1.0")
        self.assertEqual(
            tuple(str(item) for item in collection.members),
            ("company/mcp/github@^2", "company/skill/code-review@^1"),
        )
        self.assertEqual(str(collection.manifest_path), "collections/data-engineer/aart.json")

    def test_collection_version_is_required_and_semver(self) -> None:
        for version in (None, "latest"):
            with self.subTest(version=version):
                snapshot = SourceSnapshot(
                    SnapshotOrigin.IMMUTABLE_GIT,
                    (
                        _file(
                            "collections/data-engineer/aart.json",
                            json.dumps(_collection(version=version)),
                        ),
                    ),
                )

                compiled = _compile(snapshot)

                self.assertIsInstance(compiled, Err)
                assert isinstance(compiled, Err)
                self.assertIn("version", compiled.diagnostics[0].message.lower())

    def test_collection_compilation_is_deterministic_under_snapshot_order(self) -> None:
        first = _file("collections/first/aart.json", json.dumps(_collection()))
        second_document = _collection(version="3.0.0") | {"name": "second"}
        second = _file("collections/second/aart.json", json.dumps(second_document))

        left = _compile(SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, (second, first)))
        right = _compile(SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, (first, second)))

        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
