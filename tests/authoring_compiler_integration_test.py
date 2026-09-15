"""CP-04 acquisition-boundary integration for a real author repository tree."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.sources.local import read_local_snapshot
from agent_artifacts.sources.model import LocalSnapshotRequest, SnapshotLimits, source_instance_id


class AuthorCompilerIntegrationTest(unittest.TestCase):
    def test_local_acquisition_to_canonical_package_uses_only_declared_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            artifact = root / "github"
            (artifact / "src").mkdir(parents=True)
            (artifact / "tests").mkdir()
            manifest = {
                "schema": "aart.dev/mcp/v1",
                "artifact": {"name": "github-mcp", "kind": "mcp", "version": "1.0.0"},
                "payload": {
                    "include": ["server.py", "src/**", "requirements.txt"],
                    "exclude": ["tests/**"],
                },
                "transport": {"type": "stdio"},
                "runtime": {"type": "python", "version": ">=3.11"},
                "launch": {"type": "python", "entrypoint": "server.py"},
                "compatibility": {"harnesses": ["codex"]},
            }
            (artifact / "aart.json").write_text(json.dumps(manifest), encoding="utf-8")
            (artifact / "server.py").write_text("print('ready')\n", encoding="utf-8")
            (artifact / "src" / "service.py").write_text("READY = True\n", encoding="utf-8")
            (artifact / "requirements.txt").write_text("dependency==1.0\n", encoding="utf-8")
            (artifact / "tests" / "test_service.py").write_text("excluded\n", encoding="utf-8")
            (artifact / ".env").write_text("excluded configuration\n", encoding="utf-8")

            alias = SourceAlias("fixture")
            configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(root), None, True)
            acquired = read_local_snapshot(
                LocalSnapshotRequest(
                    source_instance_id(configured),
                    alias,
                    str(root),
                    SnapshotLimits(),
                )
            )
            self.assertIsInstance(acquired, Ok)
            assert isinstance(acquired, Ok)

            compiled = compile_author_snapshot(
                acquired.value.snapshot,
                source_alias=alias,
                source="https://git.example/agent-mcp-servers.git",
                revision="b" * 40,
            )

            self.assertIsInstance(compiled, Ok)
            assert isinstance(compiled, Ok)
            package = compiled.value[0]
            self.assertEqual(str(package.manifest_path), "github/aart.json")
            self.assertEqual(
                tuple(
                    str(entry.path)
                    for entry in package.canonical_entries
                    if str(entry.path).startswith("payload/")
                ),
                (
                    "payload/mcp.json",
                    "payload/requirements.txt",
                    "payload/server.py",
                    "payload/src/service.py",
                ),
            )


if __name__ == "__main__":
    unittest.main()
