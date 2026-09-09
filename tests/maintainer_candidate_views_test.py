"""CP-14 screens 35–37 project persisted Candidates, details and semantic-first diffs."""

from __future__ import annotations

import json
import unittest

from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.application.maintainer_views import project_maintainer_candidates
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _compiled(*, revision: str, version: str, server: str, requirement: str):
    manifest = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "github-mcp", "kind": "mcp", "version": version},
        "payload": {"include": ["server.py", "requirements.txt"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
        "inputs": [
            {
                "id": "github-token",
                "kind": "secret",
                "inject": {"type": "environment", "variable": "GITHUB_TOKEN"},
                "help": {
                    "label": "GitHub token",
                    "format_hint": "provider-issued token",
                    "obtain_from": {
                        "label": "GitHub Settings",
                        "url": "https://github.example/settings/tokens",
                    },
                },
            },
            {
                "id": "user-id",
                "kind": "config",
                "inject": {"type": "cli-argument", "argument": "--user-id"},
                "help": {"label": "User ID", "example": "pl847362"},
            },
        ],
        "python": {"dependencies": {"type": "requirements", "path": "requirements.txt"}},
    }
    compiled = compile_author_snapshot(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry("github/aart.json", json.dumps(manifest, sort_keys=True)),
                _entry("github/server.py", server),
                _entry("github/requirements.txt", requirement),
            ),
        ),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision=revision * 40,
    )
    assert isinstance(compiled, Ok), compiled
    return compiled.value


def _changed_scan():
    first = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        _compiled(
            revision="a",
            version="1.0.0",
            server="print('old')\n",
            requirement="mcp==1.12.0\n",
        ),
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(first, Ok), first
    second = reconcile_source_scan(
        SourceAlias("authors"),
        "b" * 40,
        _compiled(
            revision="b",
            version="1.1.0",
            server="print('new')\n",
            requirement="mcp==1.14.0\n",
        ),
        previous=first.value.history,
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(second, Ok), second
    return second.value


class MaintainerCandidateProjectionTest(unittest.TestCase):
    def test_active_candidate_detail_is_complete_and_secret_value_free(self) -> None:
        candidates = project_maintainer_candidates((_changed_scan(),))

        self.assertEqual(len(candidates), 1)
        view = candidates[0]
        self.assertEqual(view.state, CandidateState.CHANGED)
        self.assertEqual(view.artifact, "mcp/github-mcp")
        self.assertEqual(view.version, "1.1.0")
        self.assertEqual(view.source_alias, "authors")
        self.assertEqual(view.source_revision, "b" * 40)
        self.assertEqual(view.manifest_path, "github/aart.json")
        self.assertEqual(view.runtime, "python >=3.11")
        self.assertEqual(view.transport, "stdio")
        self.assertEqual(view.dependency_descriptor, "requirements: requirements.txt")
        self.assertEqual(
            [(item.kind, item.id) for item in view.inputs],
            [
                ("SECRET", "github-token"),
                ("CONFIG", "user-id"),
            ],
        )
        self.assertEqual(view.inputs[0].obtain_from, "GitHub Settings")
        self.assertIsNone(view.inputs[0].example)
        self.assertFalse(hasattr(view.inputs[0], "value"))
        self.assertEqual(view.inputs[1].example, "pl847362")

    def test_diff_is_semantic_first_with_bounded_files_as_secondary_evidence(self) -> None:
        view = project_maintainer_candidates((_changed_scan(),))[0]

        changes = {item.field: (item.before, item.after) for item in view.semantic_changes}
        self.assertEqual(changes["version"], ("1.0.0", "1.1.0"))
        self.assertEqual(
            changes["dependency requirements.txt"],
            ("mcp==1.12.0", "mcp==1.14.0"),
        )
        files = {item.path: item for item in view.file_changes}
        self.assertEqual(files["payload/server.py"].status, "modified")
        self.assertTrue(any("print('new')" in line for line in files["payload/server.py"].diff))
        self.assertLessEqual(sum(len(item.diff) for item in view.file_changes), 200)
        self.assertEqual(view.baseline, "Candidate 1.0.0")

    def test_candidate_ids_are_the_unique_stable_row_identity(self) -> None:
        view = project_maintainer_candidates((_changed_scan(),))[0]

        self.assertRegex(view.id, r"^[0-9a-f]{64}$")
        self.assertNotEqual(view.id, view.coordinate)


if __name__ == "__main__":
    unittest.main()
