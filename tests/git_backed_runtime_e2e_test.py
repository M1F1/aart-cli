"""CP-17 step 3b: the server an operator ends up running came out of a real Git commit.

`mcp_stdio_e2e_test` already starts a real MCP server and speaks JSON-RPC to it, but it assembles
the installation itself -- it writes the payload by hand, creates the environment by hand, and calls
`generate_launcher` directly. Nothing joins that runtime to the chain in front of it. This does: one
real Git repository, synchronized and installed through public verbs only, and then the launcher
that install wrote is executed exactly as a harness would execute it.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent_artifacts.domain.result import Ok
from agent_artifacts.io.receipt_store import LocalReceiptStore
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.git_backed_consumer_e2e_test import _Environment
from tests.mcp_stdio_e2e_test import SERVER_SOURCE, speak

COORDINATE = "company/mcp/notes"

#: The same server `mcp_stdio_e2e_test` starts, published as an artifact that declares no inputs.
#:
#: The artifact declares none deliberately. `aart marketplace install` has no way to answer a
#: declared input -- the form belongs to the persistent shell -- so an artifact that declares one
#: cannot be installed through the CLI at all, which the refusal test below pins. Credential and
#: config delivery into a launched server is `mcp_stdio_e2e_test`'s subject and is not restated
#: here; what this file adds is that the chain in front of the runtime produces a runtime that runs.
MANIFEST = {
    "schema": "aart.dev/mcp/v1",
    "artifact": {"name": "notes", "kind": "mcp", "version": "1.0.0"},
    "payload": {"include": ["server.py", "requirements.txt"]},
    "transport": {"type": "stdio"},
    "runtime": {"type": "python", "version": ">=3.11"},
    "launch": {"type": "python", "entrypoint": "server.py", "arguments": ["--strict"]},
}
AUTHORED_SERVER: tuple[tuple[str, str], ...] = (
    ("notes/aart.json", json.dumps(MANIFEST)),
    ("notes/server.py", SERVER_SOURCE),
    ("notes/requirements.txt", "# no third-party packages\n"),
)


def _facts(replies: list[dict]) -> dict:
    """What the running server reports about the process it is."""

    return json.loads(replies[-1]["result"]["content"][0]["text"])


class GitBackedRuntimeE2ETest(unittest.TestCase):
    def test_the_server_started_from_a_git_commit_runs_in_the_runtime_that_install_built(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env = _Environment(Path(raw).resolve(), AUTHORED_SERVER)

            sync_code, synchronized = env.run("source", "sync", source_transport=True)

            self.assertEqual(sync_code, 0, synchronized)
            self.assertEqual(synchronized["sources"][0]["resolved_revision"], env.head)

            install_code, installed = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(install_code, 0, installed)
            self.assertEqual(installed["receipt"]["artifacts"][0]["source_revision"], env.head)
            # The install really built a runtime rather than only placing files.
            self.assertEqual(
                [step["effect"] for step in installed["receipt"]["steps"]],
                ["copy-tree", "create-python-environment", "write-file", "configure-harness"],
            )

            runtime = env.project / ".agent-artifacts/runtimes/company/mcp/notes"
            launcher = runtime / "launch.sh"

            self.assertTrue(os.access(launcher, os.X_OK), "the harness could not run this")

            replies = speak(
                str(launcher),
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {}},
                ],
            )

            self.assertEqual([reply["id"] for reply in replies], [1, 2, 3])
            # The bytes answering here are the ones the commit carried: `serverInfo` is a literal in
            # `server.py`, and nothing between the author's file and this process rewrote it.
            self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "aart-e2e-github")
            self.assertEqual(replies[1]["result"]["tools"][0]["name"], "environment")

            facts = _facts(replies)

            # The interpreter is the one the install created, not the one running this test.
            self.assertEqual(facts["executable"], str(runtime / "runtime/.venv/bin/python"))
            self.assertEqual(facts["prefix"], str(runtime / "runtime/.venv"))
            # The launch arguments the manifest declared reached the process as declared.
            self.assertEqual(facts["argv"], ["--strict"])
            # An artifact's runtime is not AART's runtime, however it was obtained.
            self.assertFalse(facts["aart_importable"])

    def test_the_harness_file_records_the_launcher_that_was_just_proven_to_start(self) -> None:
        """The harness starts what the file names, so naming something else is the whole failure."""

        with tempfile.TemporaryDirectory() as raw:
            env = _Environment(Path(raw).resolve(), AUTHORED_SERVER)
            env.run("source", "sync", source_transport=True)
            env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")

            recorded = json.loads((env.project / ".mcp.json").read_text(encoding="utf-8"))
            command = recorded["mcpServers"]["notes"]["command"]

            self.assertEqual(
                command,
                str(env.project / ".agent-artifacts/runtimes/company/mcp/notes/launch.sh"),
            )
            replies = speak(command, [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])
            self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "aart-e2e-github")

    def test_an_artifact_that_declares_inputs_is_refused_by_name_rather_than_half_installed(
        self,
    ) -> None:
        """Why the artifact above declares none, stated as a claim instead of left as a choice.

        The CLI has no flag that answers a declared input; the form belongs to the persistent shell.
        What matters at this boundary is that the verb says so and stops, because the alternative --
        installing a server that cannot start -- is the failure an operator would meet later, at a
        harness, with nothing naming the cause.
        """

        with tempfile.TemporaryDirectory() as raw:
            env = _Environment(Path(raw).resolve(), AUTHORED_MCP)
            env.run("source", "sync", source_transport=True)

            code, payload = env.run(
                "marketplace", "install", "company/mcp/github", "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 1, payload)
            self.assertFalse(payload["ok"])
            self.assertFalse(payload["finalized"])
            self.assertEqual(
                [item["code"] for item in payload["diagnostics"]], ["consumer-invalid"]
            )
            self.assertEqual(
                sorted((item["id"], item["kind"]) for item in payload["inputs"]),
                [("github-org", "config"), ("github-token", "credential")],
            )
            # Nothing was built for an install that cannot complete.
            self.assertFalse((env.project / ".agent-artifacts").exists(), payload)
            self.assertFalse((env.project / ".mcp.json").exists(), payload)

            persisted = LocalReceiptStore(str(Path(env.paths.data_root) / "state")).actions()
            self.assertIsInstance(persisted, Ok, persisted)
            assert isinstance(persisted, Ok)
            self.assertEqual(persisted.value, ())


if __name__ == "__main__":
    unittest.main()
