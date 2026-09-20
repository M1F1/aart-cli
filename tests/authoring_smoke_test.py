from __future__ import annotations

import unittest

from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import (
    AUTHORING_EXTENSION,
    DiscoveredAuthorManifest,
    compile_author_snapshot,
    parse_author_manifest,
)
from aart_cli.protocol.json import JsonObject
from aart_cli.protocol.native_schema import parse_artifact_manifest
from aart_cli.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from aart_cli.protocol.paths import parse_relative_path


def _path(value: str):
    parsed = parse_relative_path(value)
    assert isinstance(parsed, Ok)
    return parsed.value


def _manifest(smoke: str, *, inputs: str = "") -> bytes:
    return f"""schema: aart-cli.dev/mcp/v1
artifact:
  kind: mcp
  name: identity
  version: 1.0.0
payload:
  include:
    - server.py
transport:
  type: stdio
runtime:
  type: python
  version: '>=3.11'
launch:
  type: python
  entrypoint: server.py
{inputs}{smoke}""".encode()


def _parse(content: bytes):
    return parse_author_manifest(DiscoveredAuthorManifest(_path("identity/aart-cli.yaml"), content))


class AuthoringSmokeDeclarationTest(unittest.TestCase):
    def test_minimal_read_only_declaration_has_bounded_defaults(self) -> None:
        parsed = _parse(_manifest("smoke_test:\n  tool: get_current_user\n  read_only: true\n"))
        assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())

        smoke = parsed.value.smoke_test
        assert smoke is not None
        self.assertEqual(dict(smoke.entries)["tool"], "get_current_user")
        self.assertEqual(dict(smoke.entries)["arguments"], JsonObject(()))
        self.assertEqual(dict(smoke.entries)["timeout_seconds"], 15)

    def test_declaration_survives_canonical_compilation_unchanged_in_meaning(self) -> None:
        content = _manifest("smoke_test:\n  tool: get_current_user\n  read_only: true\n")
        snapshot = SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                SnapshotEntry(_path("identity/aart-cli.yaml"), SnapshotEntryKind.FILE, content),
                SnapshotEntry(
                    _path("identity/server.py"), SnapshotEntryKind.FILE, b"print('server')\n"
                ),
            ),
        )
        compiled = compile_author_snapshot(
            snapshot,
            source_alias=SourceAlias("local"),
            source="https://example.invalid/identity.git",
            revision="a" * 40,
        )
        assert isinstance(compiled, Ok), getattr(compiled, "diagnostics", ())
        artifact_entry = next(
            entry
            for entry in compiled.value[0].canonical_entries
            if str(entry.path) == "artifact.json"
        )
        canonical = parse_artifact_manifest(artifact_entry.content)
        assert isinstance(canonical, Ok), getattr(canonical, "diagnostics", ())
        intent = dict(canonical.value.extensions)[AUTHORING_EXTENSION]
        assert isinstance(intent, JsonObject)
        smoke = intent.get("smoke_test")
        assert isinstance(smoke, JsonObject)
        self.assertEqual(dict(smoke.entries)["arguments"], JsonObject(()))
        self.assertEqual(dict(smoke.entries)["timeout_seconds"], 15)

    def test_read_only_must_be_literal_true(self) -> None:
        parsed = _parse(_manifest("smoke_test:\n  tool: get_current_user\n  read_only: false\n"))
        self.assertIsInstance(parsed, Err)
        self.assertIn("read_only must be true", parsed.diagnostics[0].message)

    def test_argument_reference_may_name_config_but_never_a_secret(self) -> None:
        inputs = """inputs:
  - id: tenant
    kind: config
    required: true
    inject:
      type: environment
      variable: TENANT
  - id: token
    kind: secret
    required: true
    inject:
      type: environment
      variable: TOKEN
"""
        accepted = _parse(
            _manifest(
                "smoke_test:\n  tool: read_identity\n  read_only: true\n  arguments:\n    tenant:\n      configuration: tenant\n",
                inputs=inputs,
            )
        )
        self.assertIsInstance(accepted, Ok)

        refused = _parse(
            _manifest(
                "smoke_test:\n  tool: read_identity\n  read_only: true\n  arguments:\n    token:\n      configuration: token\n",
                inputs=inputs,
            )
        )
        self.assertIsInstance(refused, Err)
        self.assertIn("non-secret configuration", refused.diagnostics[0].message)

    def test_expectation_vocabulary_is_bounded(self) -> None:
        parsed = _parse(
            _manifest(
                "smoke_test:\n  tool: get_current_user\n  read_only: true\n  expect:\n    script: rm -rf /\n"
            )
        )
        self.assertIsInstance(parsed, Err)
        self.assertIn("unknown field 'script'", parsed.diagnostics[0].message)

    def test_the_service_read_claim_is_an_explicit_opt_in_that_must_be_true(self) -> None:
        """`reaches_service` is the author's reviewed statement, so only `true` states it.

        §170.3 keeps the minimal declaration at tool and read-only, so this stays optional; and
        a field that accepted `false` or a string would let a manifest look like it made the claim
        without making it.
        """

        absent = _parse(_manifest("smoke_test:\n  tool: read_identity\n  read_only: true\n"))
        assert isinstance(absent, Ok), getattr(absent, "diagnostics", ())
        assert absent.value.smoke_test is not None
        self.assertNotIn("reaches_service", dict(absent.value.smoke_test.entries))

        declared = _parse(
            _manifest(
                "smoke_test:\n  tool: read_identity\n  read_only: true\n  reaches_service: true\n"
            )
        )
        assert isinstance(declared, Ok), getattr(declared, "diagnostics", ())
        assert declared.value.smoke_test is not None
        self.assertIs(dict(declared.value.smoke_test.entries)["reaches_service"], True)

        refused = _parse(
            _manifest(
                "smoke_test:\n  tool: read_identity\n  read_only: true\n  reaches_service: false\n"
            )
        )
        self.assertIsInstance(refused, Err)
        self.assertIn("smoke_test.reaches_service must be true", refused.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
