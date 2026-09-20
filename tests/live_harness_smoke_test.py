"""Live harness evidence for installed-MCP smoke verification (CP-26.20a, B-162, §170.4).

Every other test of the harness adapters feeds them recorded events. That proves the parsing and
nothing about the claim the adapters exist to make -- that a *current* run of a real harness really
performed the declared call against the installation's own MCP server. §170.4 says so directly: a
substitute test-only MCP configuration proves the adapter fixture, not the user's installation.

So this module runs the real CLI. It is opt-in for two reasons that are not the same reason. It
costs a live model call, and the harness needs a model provider that answers -- which is a property
of the machine, not of the code. Name the harnesses whose providers work here:

    AART_CLI_LIVE_HARNESS=claude python -m unittest tests.live_harness_smoke_test

Comma-separate for more than one. Unnamed harnesses skip, so CI -- which has no harness CLI, no
provider credentials and no business spending them -- runs nothing here. Recorded on 2026-09-20:
Claude Code 2.1.278 passes; OpenCode 1.18.29 is installed but its free tier refuses a headless run
("OpenCode's free tier can only be used from within OpenCode", HTTP 403), which is a model-provider
failure and not an MCP one (§170.5).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from aart_cli.application.mcp_smoke import SmokeDeclaration
from aart_cli.io.harness_smoke import run_harness_smoke
from aart_cli.protocol.json import JsonArray, JsonObject

#: The identity only this server's own configured environment can supply. The harness cannot know
#: it, and neither can the model, so finding it in the tool result is what separates "a call
#: happened" from "the call reached the server this installation configured".
IDENTITY = "ada-lovelace"
SERVER_NAME = "identity"
TOOL = "read_identity"

SERVER = '''#!/usr/bin/env python3
"""A real stdio MCP server whose one read answers out of its own environment."""
import json, os, sys


def send(message_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        continue
    method, message_id = message.get("method"), message.get("id")
    if message_id is None:
        continue
    if method == "initialize":
        send(message_id, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "identity", "version": "1.0.0"}})
    elif method == "tools/list":
        send(message_id, {"tools": [{"name": "read_identity",
                                     "description": "Report the identity this server is configured with.",
                                     "inputSchema": {"type": "object", "properties": {}}}]})
    elif method == "tools/call":
        send(message_id, {"content": [{"type": "text",
                                       "text": "current user: " + os.environ.get("AART_LIVE_IDENTITY", "<unconfigured>")}]})
    else:
        send(message_id, {})
'''


def _requested() -> frozenset[str]:
    raw = os.environ.get("AART_CLI_LIVE_HARNESS", "")
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _live(harness: str) -> str | None:
    """The executable to drive, or None when this machine was not asked to drive it."""

    if harness not in _requested():
        return None
    return shutil.which(harness)


class LiveHarnessSmokeTest(unittest.TestCase):
    def _project(self, stack: tempfile.TemporaryDirectory) -> str:
        """A project holding a real MCP server and the harness's own configuration for it."""

        root = Path(stack.name)
        server = root / "server.py"
        server.write_text(SERVER, encoding="utf-8")
        server.chmod(0o700)
        project = root / "project"
        project.mkdir()
        # Each harness's real discovery path, with the server's identity in its own environment --
        # never handed to the harness, never in the prompt.
        (project / "opencode.json").write_text(
            json.dumps(
                {
                    "$schema": "https://opencode.ai/config.json",
                    "mcp": {
                        SERVER_NAME: {
                            "type": "local",
                            "command": ["python3", str(server)],
                            "enabled": True,
                            "environment": {"AART_LIVE_IDENTITY": IDENTITY},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (project / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        SERVER_NAME: {
                            "command": "python3",
                            "args": [str(server)],
                            "env": {"AART_LIVE_IDENTITY": IDENTITY},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return str(project)

    def _run_live(self, harness: str) -> None:
        executable = _live(harness)
        if executable is None:
            self.skipTest(f"{harness} was not named in AART_CLI_LIVE_HARNESS")
        stack = tempfile.TemporaryDirectory()
        self.addCleanup(stack.cleanup)
        cwd = self._project(stack)

        run = run_harness_smoke(
            harness,
            executable,
            SERVER_NAME,
            SmokeDeclaration(TOOL, JsonObject(()), 15),
            cwd=cwd,
        )

        self.assertEqual(run.outcome, "PASS", run.reason)
        self.assertEqual(run.coverage, "direct-and-harness")
        self.assertIsNotNone(run.version)
        self.assertIsNotNone(run.result)
        # The assessment is separate evidence and never stands in for the observed call (INV-251),
        # so it is asserted beside the result rather than instead of it.
        self.assertEqual(run.assessment.outcome, "PASS", run.assessment.reason)
        assert run.assessment.summary is not None
        self.assertLessEqual(len(run.assessment.summary), 2000)
        self.assertIsNone(run.assessment.possible_error)

        assert run.result is not None
        content = run.result.content
        assert isinstance(content, JsonArray), content
        texts = [
            dict(item.entries).get("text") for item in content.items if isinstance(item, JsonObject)
        ]
        self.assertTrue(
            any(isinstance(text, str) and IDENTITY in text for text in texts),
            f"the live result did not carry the configured identity: {texts!r}",
        )

    def test_claude_performs_the_declared_call_against_the_configured_server(self) -> None:
        self._run_live("claude")

    def test_opencode_performs_the_declared_call_against_the_configured_server(self) -> None:
        self._run_live("opencode")


if __name__ == "__main__":
    unittest.main()
