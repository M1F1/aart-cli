"""Live filesystem contract for the company Tabnine build's project and user MCP targets."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.marketplace_lifecycle_e2e_test import _environment
from tests.reference_registry import (
    ESSENTIALS,
    memory,
    reference_snapshot,
    skill,
    write_reference_registry,
)

_COORDINATE = "reference/mcp/atlassian"


_MANIFEST = {
    "schema": "aart-cli.dev/mcp/v1",
    "artifact": {
        "name": "atlassian",
        "kind": "mcp",
        "summary": "Connect the company Atlassian service.",
    },
    "payload": {"include": ["server.py"]},
    "transport": {"type": "stdio"},
    "runtime": {"type": "python", "version": ">=3.10"},
    "launch": {"type": "python", "entrypoint": "server.py"},
    "compatibility": {"harnesses": ["tabnine"]},
}


def _source_with_mcp(root: Path) -> Path:
    """The reference Registry, with an approved Atlassian server beside its Skill."""

    server = (
        ("atlassian/aart-cli.json", json.dumps(_MANIFEST)),
        ("atlassian/server.py", "print('atlassian')\n"),
    )
    return write_reference_registry(
        root / "registry", reference_snapshot(skill(), memory(), server, ESSENTIALS)
    )


class TabnineMcpE2ETest(unittest.TestCase):
    def test_project_and_user_scopes_use_company_settings_files_independently(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = _source_with_mcp(Path(raw))
            with _environment(source) as environment:
                project_code, project_payload = environment.run(
                    "consume",
                    "install",
                    _COORDINATE,
                    "--profile",
                    "tabnine",
                    "--yes",
                )
                user_code, user_payload = environment.run(
                    "consume",
                    "install",
                    _COORDINATE,
                    "--profile",
                    "tabnine",
                    "--scope",
                    "user",
                    "--yes",
                )

                self.assertEqual(project_code, 0, project_payload)
                self.assertEqual(user_code, 0, user_payload)
                project_file = environment.project / ".tabnine/agent/settings.json"
                user_file = environment.home / ".tabnine/agent/settings.json"
                # A Registry registration names its Registry and scope (§169), so the two scopes
                # never claim one server name between them.
                for path, server in (
                    (project_file, "atlassian-reference-project"),
                    (user_file, "atlassian-reference-user"),
                ):
                    self.assertEqual(
                        list(json.loads(path.read_text(encoding="utf-8"))["mcpServers"]), [server]
                    )
                # The unmeasured standalone files are not a destination; the company-proven
                # settings files above are. Neither destination is accepted silently.
                self.assertFalse((environment.project / ".tabnine/mcp_servers.json").exists())
                self.assertFalse((environment.home / ".tabnine/mcp_servers.json").exists())

                project_status, project_status_payload = environment.run(
                    "consume", "status", "--profile", "tabnine"
                )
                user_status, user_status_payload = environment.run(
                    "consume",
                    "status",
                    "--profile",
                    "tabnine",
                    "--scope",
                    "user",
                )
                self.assertEqual(project_status, 0, project_status_payload)
                self.assertEqual(user_status, 0, user_status_payload)
                self.assertEqual(project_status_payload["items"][0]["status"], "current")
                self.assertEqual(user_status_payload["items"][0]["status"], "current")

                removed_project, removed_project_payload = environment.run(
                    "consume",
                    "uninstall",
                    _COORDINATE,
                    "--profile",
                    "tabnine",
                    "--yes",
                )
                self.assertEqual(removed_project, 0, removed_project_payload)
                # The settings file AART created stays behind, emptied, for now (B-204).
                self.assertEqual(
                    json.loads(project_file.read_text(encoding="utf-8"))["mcpServers"], {}
                )
                self.assertEqual(
                    list(json.loads(user_file.read_text(encoding="utf-8"))["mcpServers"]),
                    ["atlassian-reference-user"],
                )

                removed_user, removed_user_payload = environment.run(
                    "consume",
                    "uninstall",
                    _COORDINATE,
                    "--profile",
                    "tabnine",
                    "--scope",
                    "user",
                    "--yes",
                )
                self.assertEqual(removed_user, 0, removed_user_payload)
                self.assertEqual(
                    json.loads(user_file.read_text(encoding="utf-8"))["mcpServers"], {}
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
