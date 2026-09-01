"""CP-04 contracts for manifest-first native authoring and canonical compilation."""

from __future__ import annotations

import json
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import (
    ComplianceLevel,
    compile_author_snapshot,
    discover_author_manifests,
)
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
    compile_native_package,
)
from agent_artifacts.protocol.paths import SafeRelativePath, parse_relative_path
from tests.credential_fixtures import assignment


def _path(raw: str) -> SafeRelativePath:
    parsed = parse_relative_path(raw)
    assert isinstance(parsed, Ok)
    return parsed.value


def _file(raw: str, content: bytes | str, *, executable: bool = False) -> SnapshotEntry:
    data = content.encode() if isinstance(content, str) else content
    return SnapshotEntry(_path(raw), SnapshotEntryKind.FILE, data, executable)


def _snapshot(*entries: SnapshotEntry) -> SourceSnapshot:
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, entries)


def _document(*, name: str = "github-mcp") -> dict[str, object]:
    return {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": name, "kind": "mcp", "version": "1.4.0"},
        "payload": {
            "include": ["server.py", "src/**", "requirements.txt"],
            "exclude": ["tests/**", "**/__pycache__/**"],
        },
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
        "compatibility": {"harnesses": ["codex", "claude"], "platforms": ["linux"]},
    }


def _json_manifest(path: str = "github/aart.json", *, name: str = "github-mcp") -> SnapshotEntry:
    return _file(path, json.dumps(_document(name=name), sort_keys=True))


def _yaml_manifest(path: str = "github/aart.yaml") -> SnapshotEntry:
    return _file(
        path,
        """schema: aart.dev/mcp/v1
artifact:
  name: github-mcp
  kind: mcp
  version: 1.4.0
payload:
  include:
    - server.py
    - src/**
    - requirements.txt
  exclude:
    - tests/**
    - "**/__pycache__/**"
transport:
  type: stdio
runtime:
  type: python
  version: ">=3.11"
launch:
  type: python
  entrypoint: server.py
compatibility:
  harnesses:
    - codex
    - claude
  platforms:
    - linux
""",
    )


def _compile(snapshot: SourceSnapshot):
    return compile_author_snapshot(
        snapshot,
        source_alias=SourceAlias("internal"),
        source="https://git.example/agent-mcp-servers.git",
        revision="a" * 40,
    )


class AuthorManifestDiscoveryTest(unittest.TestCase):
    def test_repository_without_a_manifest_has_no_native_candidate(self) -> None:
        snapshot = _snapshot(
            _file("README.md", "# Server"),
            _file("server.py", "print('standalone')"),
        )

        discovered = discover_author_manifests(snapshot)
        compiled = _compile(snapshot)

        self.assertEqual(discovered, Ok(()))
        self.assertEqual(compiled, Ok(()))

    def test_only_supported_manifest_basenames_define_candidates(self) -> None:
        snapshot = _snapshot(
            _file("README.md", "aart.yaml is documented here"),
            _file("server.py", "print('not a candidate')"),
            _file("launcher.sh", "#!/bin/sh"),
            _json_manifest("jira/aart.json", name="jira-mcp"),
            _yaml_manifest("github/aart.yaml"),
            _file("nested/AART.yaml", "case-sensitive"),
            _file("nested/aart.yml", "unsupported suffix"),
        )

        discovered = discover_author_manifests(snapshot)

        self.assertIsInstance(discovered, Ok)
        assert isinstance(discovered, Ok)
        self.assertEqual(
            tuple(str(item.path) for item in discovered.value),
            ("github/aart.yaml", "jira/aart.json"),
        )

    def test_two_manifests_in_one_directory_are_an_ambiguous_boundary(self) -> None:
        discovered = discover_author_manifests(_snapshot(_json_manifest(), _yaml_manifest()))

        self.assertIsInstance(discovered, Err)
        assert isinstance(discovered, Err)
        self.assertEqual(discovered.diagnostics[0].code.value, "author-tree-invalid")


class AuthorCompilerTest(unittest.TestCase):
    def test_all_five_artifact_kinds_lower_through_one_canonical_package_contract(self) -> None:
        fixtures = (
            ("skill", "review", "SKILL.md", "# Review\n"),
            ("guideline", "python", "python.md", "Use Ruff.\n"),
            ("memory", "house", "house.md", "Remember tests.\n"),
            (
                "hook",
                "guard",
                "hook.json",
                '{"command":"${SCRIPT_DIR}/guard.sh","event":"PreToolUse",'
                '"matcher":"Bash","name":"guard"}',
            ),
        )
        entries: list[SnapshotEntry] = []
        for kind, name, filename, content in fixtures:
            document = {
                "schema": f"aart.dev/{kind}/v1",
                "artifact": {"name": name, "kind": kind, "version": "1.0.0"},
                "payload": {"include": [filename]},
            }
            entries.extend(
                (
                    _file(f"{kind}/aart.json", json.dumps(document)),
                    _file(f"{kind}/{filename}", content),
                )
            )
        entries.extend(
            (
                _json_manifest("mcp/aart.json"),
                _file("mcp/server.py", "server"),
                _file("mcp/src/client.py", "client"),
                _file("mcp/requirements.txt", "dependency"),
            )
        )

        compiled = _compile(_snapshot(*entries))

        self.assertIsInstance(compiled, Ok)
        assert isinstance(compiled, Ok)
        self.assertEqual(
            tuple(item.package.kind.value for item in compiled.value),
            ("guideline", "hook", "mcp", "memory", "skill"),
        )
        self.assertTrue(
            all(
                isinstance(compile_native_package(item.canonical_entries), Ok)
                for item in compiled.value
            )
        )

    def test_yaml_manifest_compiles_declared_boundary_to_canonical_native_package(self) -> None:
        compiled = _compile(
            _snapshot(
                _yaml_manifest(),
                _file("github/server.py", "print('github')\n", executable=True),
                _file("github/src/client.py", "CLIENT = True\n"),
                _file("github/requirements.txt", "httpx==1.0\n"),
                _file("github/tests/test_server.py", "must not ship\n"),
                _file("github/.env", assignment("TOKEN", "must-not-ship") + "\n"),
                _file("unrelated/repo.txt", "must not affect artifact\n"),
            )
        )

        self.assertIsInstance(compiled, Ok)
        assert isinstance(compiled, Ok)
        self.assertEqual(len(compiled.value), 1)
        artifact = compiled.value[0]
        self.assertEqual(str(artifact.package.coordinate), "internal/mcp/github-mcp@1.4.0")
        self.assertEqual(artifact.package.protocol, "stdio")
        self.assertEqual(artifact.compliance, ComplianceLevel.AART_NATIVE)
        self.assertEqual(artifact.package.compatibility.python, ">=3.11")
        self.assertEqual(artifact.package.compatibility.harnesses, ("claude", "codex"))
        self.assertEqual(
            tuple(str(entry.path) for entry in artifact.canonical_entries),
            (
                "artifact.json",
                "payload/mcp.json",
                "payload/requirements.txt",
                "payload/server.py",
                "payload/src/client.py",
                "provenance.json",
            ),
        )
        self.assertNotIn(
            b"must-not-ship", b"".join(item.content for item in artifact.canonical_entries)
        )
        native = compile_native_package(artifact.canonical_entries)
        self.assertIsInstance(native, Ok)
        assert isinstance(native, Ok)
        self.assertEqual(native.value.payload_digest, artifact.package.payload_digest)

    def test_external_launcher_is_explicitly_aart_compatible_not_native(self) -> None:
        document = _document()
        document.pop("runtime")
        document["launch"] = {"type": "external-script", "path": "launcher.sh"}
        payload = document["payload"]
        assert isinstance(payload, dict)
        payload["include"] = ["launcher.sh"]
        document["compatibility"] = {"harnesses": ["codex"]}

        compiled = _compile(
            _snapshot(
                _file("github/aart.json", json.dumps(document)),
                _file("github/launcher.sh", "#!/bin/sh\nexec server\n", executable=True),
            )
        )

        self.assertIsInstance(compiled, Ok)
        assert isinstance(compiled, Ok)
        artifact = compiled.value[0]
        self.assertEqual(artifact.compliance, ComplianceLevel.AART_COMPATIBLE)
        self.assertEqual(artifact.package.compatibility.platforms, ())
        descriptor = next(
            entry.content
            for entry in artifact.canonical_entries
            if str(entry.path) == "payload/mcp.json"
        )
        self.assertIn(b"${AART_PAYLOAD}/launcher.sh", descriptor)

    def test_selected_content_and_executable_metadata_change_the_input_digest(self) -> None:
        entries = (
            _json_manifest(),
            _file("github/server.py", "server"),
            _file("github/src/client.py", "client"),
            _file("github/requirements.txt", "dependency"),
        )
        baseline = _compile(_snapshot(*entries))
        content_change = _compile(
            _snapshot(*entries[:-1], _file("github/requirements.txt", "new dependency"))
        )
        mode_change = _compile(
            _snapshot(
                entries[0],
                _file("github/server.py", "server", executable=True),
                *entries[2:],
            )
        )

        self.assertIsInstance(baseline, Ok)
        self.assertIsInstance(content_change, Ok)
        self.assertIsInstance(mode_change, Ok)
        assert (
            isinstance(baseline, Ok)
            and isinstance(content_change, Ok)
            and isinstance(mode_change, Ok)
        )
        self.assertNotEqual(baseline.value[0].input_digest, content_change.value[0].input_digest)
        self.assertNotEqual(baseline.value[0].input_digest, mode_change.value[0].input_digest)

    def test_multiple_manifests_compile_as_independent_sorted_boundaries(self) -> None:
        github = _document(name="github-mcp")
        jira = _document(name="jira-mcp")
        compiled = _compile(
            _snapshot(
                _file("jira/aart.json", json.dumps(jira)),
                _file("github/aart.json", json.dumps(github)),
                _file("github/server.py", "github"),
                _file("github/src/client.py", "github client"),
                _file("github/requirements.txt", "github-dep"),
                _file("jira/server.py", "jira"),
                _file("jira/src/client.py", "jira client"),
                _file("jira/requirements.txt", "jira-dep"),
            )
        )

        self.assertIsInstance(compiled, Ok)
        assert isinstance(compiled, Ok)
        self.assertEqual(
            tuple(str(item.manifest_path) for item in compiled.value),
            ("github/aart.json", "jira/aart.json"),
        )
        self.assertNotEqual(compiled.value[0].input_digest, compiled.value[1].input_digest)

    def test_nested_manifest_roots_do_not_leak_into_parent_payload(self) -> None:
        parent = _document(name="parent-mcp")
        parent_payload = parent["payload"]
        assert isinstance(parent_payload, dict)
        parent_payload["include"] = ["**"]
        child = _document(name="child-mcp")
        compiled = _compile(
            _snapshot(
                _file("aart.json", json.dumps(parent)),
                _file("server.py", "parent"),
                _file("child/aart.json", json.dumps(child)),
                _file("child/server.py", "child"),
                _file("child/src/client.py", "child client"),
                _file("child/requirements.txt", "child dependency"),
            )
        )

        self.assertIsInstance(compiled, Ok)
        assert isinstance(compiled, Ok)
        parent_artifact = next(
            item for item in compiled.value if item.package.coordinate.artifact.name == "parent-mcp"
        )
        self.assertNotIn(
            b"child",
            b"".join(
                entry.content
                for entry in parent_artifact.canonical_entries
                if str(entry.path).startswith("payload/")
            ),
        )

    def test_excludes_win_and_empty_declared_payload_is_rejected(self) -> None:
        document = _document()
        payload = document["payload"]
        assert isinstance(payload, dict)
        payload["exclude"] = ["server.py", "src/**", "requirements.txt"]
        compiled = _compile(
            _snapshot(
                _file("github/aart.json", json.dumps(document)),
                _file("github/server.py", "server"),
                _file("github/src/client.py", "client"),
                _file("github/requirements.txt", "dependency"),
            )
        )

        self.assertIsInstance(compiled, Err)
        assert isinstance(compiled, Err)
        self.assertEqual(compiled.diagnostics[0].code.value, "author-payload-invalid")

    def test_traversal_patterns_and_selected_non_files_are_rejected(self) -> None:
        for unsafe in ("../secret", "/absolute", "dir\\file"):
            with self.subTest(pattern=unsafe):
                document = _document()
                payload = document["payload"]
                assert isinstance(payload, dict)
                payload["include"] = [unsafe]
                compiled = _compile(_snapshot(_file("github/aart.json", json.dumps(document))))
                self.assertIsInstance(compiled, Err)

        document = _document()
        payload = document["payload"]
        assert isinstance(payload, dict)
        payload["include"] = ["src/**"]
        compiled = _compile(
            _snapshot(
                _file("github/aart.json", json.dumps(document)),
                SnapshotEntry(_path("github/src/link"), SnapshotEntryKind.SYMLINK),
            )
        )
        self.assertIsInstance(compiled, Err)
        assert isinstance(compiled, Err)
        self.assertEqual(compiled.diagnostics[0].code.value, "author-payload-invalid")

    def test_duplicate_yaml_keys_are_rejected_instead_of_silently_overridden(self) -> None:
        malformed = _yaml_manifest()
        malformed = SnapshotEntry(
            malformed.path,
            malformed.kind,
            malformed.content.replace(
                b"  name: github-mcp\n", b"  name: github-mcp\n  name: shadowed\n"
            ),
        )

        compiled = _compile(_snapshot(malformed))

        self.assertIsInstance(compiled, Err)
        assert isinstance(compiled, Err)
        self.assertEqual(compiled.diagnostics[0].code.value, "author-manifest-invalid")

    @given(
        unrelated_name=st.from_regex(r"[a-z][a-z0-9]{0,10}\.txt", fullmatch=True),
        unrelated_content=st.binary(max_size=128),
        reverse=st.booleans(),
    )
    def test_unrelated_repository_changes_and_entry_order_do_not_change_input_digest(
        self,
        unrelated_name: str,
        unrelated_content: bytes,
        reverse: bool,
    ) -> None:
        base = [
            _json_manifest(),
            _file("github/server.py", "server"),
            _file("github/src/client.py", "client"),
            _file("github/requirements.txt", "dependency"),
        ]
        changed = [*base, _file(f"unrelated/{unrelated_name}", unrelated_content)]
        if reverse:
            changed.reverse()

        left = _compile(_snapshot(*base))
        right = _compile(_snapshot(*changed))

        self.assertIsInstance(left, Ok)
        self.assertIsInstance(right, Ok)
        assert isinstance(left, Ok) and isinstance(right, Ok)
        self.assertEqual(left.value[0].input_digest, right.value[0].input_digest)
        self.assertEqual(left.value[0].canonical_entries, right.value[0].canonical_entries)


class LocalAuthorRevisionTest(unittest.TestCase):
    def test_local_snapshot_digest_is_a_canonical_pinned_author_revision(self) -> None:
        revision = "local:" + "b" * 64
        compiled = compile_author_snapshot(
            SourceSnapshot(
                SnapshotOrigin.LOCAL,
                (
                    _json_manifest(),
                    _file("github/server.py", "print()\n"),
                    _file("github/requirements.txt", "mcp==1.0.0\n"),
                ),
            ),
            source_alias=SourceAlias("local-authors"),
            source="/work/authors",
            revision=revision,
        )

        self.assertIsInstance(compiled, Ok)
        assert isinstance(compiled, Ok)
        artifact = compiled.value[0]
        self.assertEqual(artifact.package.provenance.revision, revision)
        native = compile_native_package(artifact.canonical_entries)
        self.assertIsInstance(native, Ok)
        assert isinstance(native, Ok)
        assert native.value.provenance is not None
        self.assertEqual(native.value.provenance.origin.kind, "local")
        self.assertEqual(native.value.provenance.origin.url, "/work/authors")
        self.assertEqual(native.value.provenance.origin.resolved_commit, revision)

    def test_local_revision_requires_an_absolute_normalized_location(self) -> None:
        compiled = compile_author_snapshot(
            _snapshot(),
            source_alias=SourceAlias("local-authors"),
            source="relative/authors",
            revision="local:" + "b" * 64,
        )

        self.assertIsInstance(compiled, Err)


if __name__ == "__main__":
    unittest.main()
