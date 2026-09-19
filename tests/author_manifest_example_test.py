"""The example MCP author manifest in `docs/examples` is what AART actually accepts.

The file exists to be copied into somebody else's repository, so an example that drifted from the
parser would be handed on and refused there, far from anyone who could tell why. These tests read
the committed bytes — not a dictionary rebuilt beside them — through the same discovery, parsing and
compilation a Source Sync uses.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.inputs import ConfigInput, EnvironmentBinding, SecretInput
from aart_cli.domain.python_runtime import RequirementsFile
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import (
    compile_author_snapshot,
    discover_author_manifests,
    parse_author_manifest,
)
from tests.authoring_compiler_test import _file, _snapshot

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "docs/examples/author-source/example-mcp/aart-cli.yaml"


def _example_snapshot():
    return _snapshot(
        _file("example-mcp/aart-cli.yaml", EXAMPLE.read_bytes()),
        _file("example-mcp/server.py", "print()\n"),
        _file("example-mcp/requirements.txt", "mcp==1.0.0\n"),
    )


class AuthorManifestExampleTest(unittest.TestCase):
    def _parsed(self):
        discovered = discover_author_manifests(_example_snapshot())
        self.assertIsInstance(discovered, Ok, getattr(discovered, "diagnostics", ()))
        self.assertEqual(len(discovered.value), 1)
        parsed = parse_author_manifest(discovered.value[0])
        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        return parsed.value

    def test_example_declares_a_python_stdio_mcp(self) -> None:
        manifest = self._parsed()

        self.assertEqual(manifest.schema, "aart-cli.dev/mcp/v1")
        self.assertEqual(
            (manifest.kind, manifest.name, str(manifest.version)), ("mcp", "example-mcp", "1.0.0")
        )
        self.assertEqual(manifest.transport, "stdio")
        self.assertEqual(manifest.runtime, "python")
        self.assertEqual(manifest.contract.entrypoint, "server.py")
        self.assertEqual(manifest.dependencies, RequirementsFile("requirements.txt"))
        self.assertEqual(manifest.harnesses, ("claude", "opencode", "tabnine"))
        self.assertEqual(manifest.platforms, ("darwin", "linux"))

    def test_example_keeps_its_secret_apart_from_its_configuration(self) -> None:
        inputs = {str(item.id.value): item for item in self._parsed().inputs}

        token = inputs["api-token"]
        self.assertIsInstance(token, SecretInput)
        self.assertEqual(token.binding, EnvironmentBinding("EXAMPLE_API_TOKEN"))
        self.assertTrue(token.required)
        self.assertIsNotNone(token.guidance.obtain_from)

        base_url = inputs["base-url"]
        self.assertIsInstance(base_url, ConfigInput)
        self.assertEqual(base_url.binding, EnvironmentBinding("EXAMPLE_BASE_URL"))
        self.assertEqual(base_url.default, "https://api.example.com")

    def test_example_compiles_beside_the_files_it_names(self) -> None:
        compiled = compile_author_snapshot(
            _example_snapshot(),
            source_alias=SourceAlias("example"),
            source="https://example.test/example-mcp.git",
            revision="a" * 40,
        )

        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        self.assertEqual(len(compiled.value), 1)

    def test_example_is_refused_without_the_dependency_file_it_points_at(self) -> None:
        compiled = compile_author_snapshot(
            _snapshot(
                _file("example-mcp/aart-cli.yaml", EXAMPLE.read_bytes()),
                _file("example-mcp/server.py", "print()\n"),
            ),
            source_alias=SourceAlias("example"),
            source="https://example.test/example-mcp.git",
            revision="a" * 40,
        )

        self.assertIsInstance(compiled, Err)


if __name__ == "__main__":
    unittest.main()
