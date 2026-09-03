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
import shutil
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


class GitBackedDoctorE2ETest(unittest.TestCase):
    """CP-17 step 4: what `aart doctor` says about the installation the chain just produced.

    D-150's subject, proved where an operator meets it. The installation under test is the real
    one -- synchronized from a Git commit and installed through public verbs -- and the damage is
    done to the tree on disk rather than to a fixture's idea of it.
    """

    def _installed(self, raw: str):
        env = _Environment(Path(raw).resolve(), AUTHORED_SERVER)
        env.run("source", "sync", source_transport=True)
        code, installed = env.run(
            "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, installed)
        runtime = env.project / ".agent-artifacts/runtimes/company/mcp/notes"
        self.assertTrue((runtime / "payload").is_dir(), "nothing to damage")
        return env, runtime

    def _delete_payload(self, runtime: Path) -> None:
        """An installed payload is deliberately read-only, so removing it takes the same
        deliberate act it would take an operator."""

        payload = runtime / "payload"
        payload.chmod(0o700)
        for item in payload.rglob("*"):
            item.chmod(0o700)
        shutil.rmtree(payload)
        self.assertFalse(payload.exists())

    def _report(self, env, *, ok: bool):
        """Doctor's exit code is part of the claim: a machine needing attention does not exit 0."""

        code, report = env.run("doctor")
        self.assertEqual(0 if ok else 1, code, report)
        self.assertEqual(ok, report["ok"])
        return report

    def _health(self, env, *, ok: bool):
        report = self._report(env, ok=ok)
        (installation,) = [item for item in report["items"] if "mcp/notes" in item["coordinate"]]
        return installation

    def test_a_healthy_installation_is_reported_ready(self) -> None:
        """The guard that makes the next test mean something: this is not a doctor that always
        complains."""

        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._installed(raw)
            installation = self._health(env, ok=True)
            self.assertEqual("ready", installation["health"])
            self.assertEqual([], installation["drift"])

    def test_a_payload_somebody_deleted_is_reported_rather_than_called_ready(self) -> None:
        """INV-228. Before D-150 this said `ready` with an empty drift list, while the server
        below could not start -- the payload was measured, then dropped before anything read it."""

        with tempfile.TemporaryDirectory() as raw:
            env, runtime = self._installed(raw)
            self._delete_payload(runtime)

            installation = self._health(env, ok=False)

            self.assertEqual("broken", installation["health"])
            (drift,) = [item for item in installation["drift"] if item["component"] == "payload"]
            self.assertEqual("missing", drift["kind"])
            # INV-175: nothing here can put it back, and the report says so rather than offering
            # a repair that would fail when an operator reached for it.
            self.assertFalse(drift["repairable"])

    def test_the_installation_doctor_calls_broken_really_cannot_start(self) -> None:
        """The verdict is checked against the world, not against another projection of itself."""

        with tempfile.TemporaryDirectory() as raw:
            env, runtime = self._installed(raw)
            launcher = str(runtime / "launch.sh")
            started = speak(launcher, [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])
            self.assertEqual("aart-e2e-github", started[0]["result"]["serverInfo"]["name"])

            self._delete_payload(runtime)

            self.assertEqual("broken", self._health(env, ok=False)["health"])

            with self.assertRaises(AssertionError) as refused:
                speak(str(launcher), [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])
            self.assertIn("server.py", str(refused.exception))


class GitBackedUninstallE2ETest(unittest.TestCase):
    """CP-17 step 4: uninstalling the installation a real commit produced.

    `receipt_persistence_e2e` and `repair_e2e` already prove uninstall is reverse reconciliation,
    but against installations their own fixtures assembled. What is unproven there is that the
    thing being removed is one the public chain really built -- a runtime with a virtual
    environment in it, a launcher a harness really started, and a `.mcp.json` entry that really
    pointed at it. Removing an installation nobody could start proves less than removing this one.
    """

    def _installed(self, raw: str):
        env = _Environment(Path(raw).resolve(), AUTHORED_SERVER)
        env.run("source", "sync", source_transport=True)
        code, _ = env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")
        self.assertEqual(0, code)
        runtime = env.project / ".agent-artifacts/runtimes/company/mcp/notes"
        # It really runs before it is removed, so what follows is about a working installation.
        started = speak(
            str(runtime / "launch.sh"), [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}]
        )
        self.assertEqual("aart-e2e-github", started[0]["result"]["serverInfo"]["name"])
        return env, runtime

    def _uninstall(self, env):
        code, out = env.run(
            "marketplace",
            "uninstall",
            COORDINATE,
            "--profile",
            "claude",
            "--yes",
            "--project",
            str(env.project),
        )
        self.assertEqual(0, code, out)
        return out

    def test_uninstalling_the_live_installation_removes_every_component_it_built(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env, runtime = self._installed(raw)

            receipt = self._uninstall(env)["receipt"]

            self.assertEqual("completed", receipt["status"])
            # Reverse dependency order: the harness stops pointing at the launcher before the
            # launcher goes, and the environment goes before the tree that contains it.
            self.assertEqual(
                [(step["component"], step["effect"]) for step in receipt["steps"]],
                [
                    ("harness:claude", "unconfigure-harness"),
                    ("launcher", "remove-owned-path"),
                    ("runtime-environment", "remove-owned-path"),
                    ("payload", "remove-owned-path"),
                ],
            )
            self.assertTrue(all(step["status"] == "applied" for step in receipt["steps"]))
            self.assertFalse(runtime.exists(), "the tree the install built is still on disk")

    def test_the_harness_no_longer_names_a_server_that_is_gone(self) -> None:
        """The failure this prevents is a harness starting a launcher nobody removed it from."""

        with tempfile.TemporaryDirectory() as raw:
            env, runtime = self._installed(raw)
            self._uninstall(env)

            recorded = json.loads((env.project / ".mcp.json").read_text(encoding="utf-8"))

            self.assertNotIn("notes", recorded["mcpServers"])
            self.assertFalse((runtime / "launch.sh").exists())

    def test_doctor_reports_a_clean_machine_rather_than_drift_it_cannot_repair(self) -> None:
        """The other way to fail this: leave the record behind, so every later report is about an
        installation that no longer exists -- which after D-150 would now be `broken` forever."""

        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._installed(raw)
            self._uninstall(env)

            code, report = env.run("doctor")

            self.assertEqual(0, code, report)
            self.assertTrue(report["ok"])
            self.assertEqual(
                [], [item for item in report["items"] if "notes" in item["coordinate"]]
            )
            self.assertEqual(0, report["summary"]["needs_attention"])


class GitBackedUndoE2ETest(unittest.TestCase):
    """CP-17 step 4: what the live installation says about reversing itself.

    INV-192 is that AART must not invent stronger undo guarantees than a receipt carries. The
    interesting case is this one rather than a setup-bearing artifact, because here the honest
    answer is no: building a virtual environment is not an act anything retained can reverse, and
    the receipt has to say so instead of offering an undo that would fail when reached for.
    """

    def _installed(self, raw: str):
        env = _Environment(Path(raw).resolve(), AUTHORED_SERVER)
        env.run("source", "sync", source_transport=True)
        code, installed = env.run(
            "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(0, code, installed)
        return env, installed

    def test_the_receipt_refuses_an_undo_it_cannot_honour_and_names_why(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, installed = self._installed(raw)

            undo = installed["receipt"]["undo"]

            self.assertFalse(undo["available"])
            self.assertEqual([], undo["components"])
            # The reason names the component that cannot be reversed, not a generic refusal --
            # `create-python-environment` is the effect that makes this install one-way.
            self.assertIn("runtime-environment", undo["reason"])

    def test_asking_to_undo_it_anyway_refuses_by_name_and_changes_nothing(self) -> None:
        """A refusal that left the installation half-reversed would be worse than no undo."""

        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._installed(raw)
            runtime = env.project / ".agent-artifacts/runtimes/company/mcp/notes"

            code, refused = env.run("marketplace", "receipt", "undo", COORDINATE)

            self.assertEqual(1, code)
            self.assertFalse(refused["ok"])
            (diagnostic,) = refused["diagnostics"]
            self.assertEqual("receipt-no-setup", diagnostic["code"])
            self.assertTrue(diagnostic["remediation"], "a refusal with no way forward")

            # Nothing moved, and the server the refusal declined to unbuild still runs.
            self.assertTrue(runtime.exists())
            started = speak(
                str(runtime / "launch.sh"), [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}]
            )
            self.assertEqual("aart-e2e-github", started[0]["result"]["serverInfo"]["name"])
