"""A Source defines no Collection: the Registry creates it (§173.1, §173.3, D-430).

A Collection manifest in a Source is refused by name, and the artifacts beside it still compile.
The refusal says where a Collection is made instead.
"""

from __future__ import annotations

import json
import unittest

from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Ok
from aart_cli.protocol.authoring import (
    COLLECTION_IN_SOURCE,
    COLLECTION_IN_SOURCE_REMEDIATION,
    compile_author_snapshot,
    compile_author_source,
)
from aart_cli.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from tests.authoring_compiler_test import _file, _json_manifest
from tests.fixture_versions import with_fixture_versions

_COLLECTION = {
    "schema": "aart-cli.dev/collection/v1",
    "name": "data-engineer",
    "summary": "Approved data engineering tools.",
    "artifacts": ["mcp/github@^2"],
}


def _snapshot(*extra) -> SourceSnapshot:
    return SourceSnapshot(
        SnapshotOrigin.IMMUTABLE_GIT,
        (
            _json_manifest("github/aart-cli.json"),
            _file("github/server.py", "print('x')\n"),
            _file("github/src/client.py", "client\n"),
            _file("github/requirements.txt", "dependency\n"),
            *extra,
        ),
    )


def _compile(snapshot: SourceSnapshot):
    return with_fixture_versions(compile_author_source)(
        snapshot,
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
    )


class CollectionInSourceTest(unittest.TestCase):
    def test_a_collection_manifest_is_refused_and_the_artifacts_still_compile(self) -> None:
        manifest = _file("collections/data-engineer/aart-cli.json", json.dumps(_COLLECTION))

        compiled = _compile(_snapshot(manifest))
        alone = _compile(_snapshot())

        assert isinstance(compiled, Ok) and isinstance(alone, Ok), (compiled, alone)
        self.assertEqual(compiled.value.artifacts, alone.value.artifacts)
        (refusal,) = compiled.value.refusals
        self.assertEqual(str(refusal.manifest_path), "collections/data-engineer/aart-cli.json")
        (diagnostic,) = refusal.diagnostics
        self.assertEqual(diagnostic.message, COLLECTION_IN_SOURCE)
        self.assertEqual(diagnostic.remediation, (COLLECTION_IN_SOURCE_REMEDIATION,))
        self.assertIn("aart-cli registry collection", COLLECTION_IN_SOURCE_REMEDIATION)

    def test_the_artifact_only_compiler_refuses_it_too(self) -> None:
        manifest = _file("collections/data-engineer/aart-cli.json", json.dumps(_COLLECTION))

        compiled = with_fixture_versions(compile_author_snapshot)(
            _snapshot(manifest),
            source_alias=SourceAlias("authors"),
            source="https://git.example/authors.git",
            revision="a" * 40,
        )

        self.assertNotIsInstance(compiled, Ok)


if __name__ == "__main__":
    unittest.main()
