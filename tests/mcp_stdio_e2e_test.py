"""CP-10 end to end: a real Python MCP server installed, launched by its own generated launcher.

Nothing is simulated below the plan. A real virtual environment is created, a real launcher is
written and made executable, a real harness settings file is merged, and the command that file
records is executed as a subprocess that speaks newline-delimited JSON-RPC over stdio.

The child is started with almost no environment on purpose. Everything it needs must come from the
launcher, so anything it turns out to have inherited is a defect this test is meant to catch.

The secret is a freshly generated 256-bit token and the server reports only its SHA-256, so the
test can prove the right value arrived without any value being printed, stored or asserted on.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import secrets
import subprocess
import sys
import tempfile
import unittest
import uuid

from agent_artifacts.application.installation_verification import (
    VerificationFinding,
    verify_installation,
)
from agent_artifacts.application.runtime_projection import generate_launcher
from agent_artifacts.domain.credentials import CredentialProviderRef, CredentialReference
from agent_artifacts.domain.effects import CreatePythonEnvironment
from agent_artifacts.domain.harness import McpRegistration, Scope, mcp_target
from agent_artifacts.domain.identifiers import InputId
from agent_artifacts.domain.inputs import (
    BoundInput,
    BoundInputs,
    ConfigInput,
    EnvironmentBinding,
    PersistedConfigValue,
    SecretInput,
    SecretProviderReference,
)
from agent_artifacts.domain.launch import LaunchContract, Transport
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import (
    InstallationReceipt,
    config_fingerprint,
    installation_receipt_to_data,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.credentials import SECURITY_TOOL, MacOsKeychainProvider
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.python_runtime import LocalPythonRuntime
from agent_artifacts.io.runtime_projection import LocalProjectionWriter, observe_installation

ARTIFACT = "mcp/github"
SERVER_SOURCE = '''"""A minimal MCP server over stdio. It reports how it was started, never a value."""

import hashlib
import importlib.util
import json
import os
import sys


def facts():
    token = os.environ.get("GITHUB_TOKEN", "")
    return {
        "argv": sys.argv[1:],
        "executable": sys.executable,
        "org": os.environ.get("GITHUB_ORG"),
        "prefix": sys.prefix,
        "aart_importable": importlib.util.find_spec("agent_artifacts") is not None,
        # The digest, never the token: this proves delivery without printing anything secret.
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest() if token else None,
        "token_present": bool(token),
    }


def handle(request):
    method = request.get("method")
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "aart-e2e-github", "version": "1.0.0"},
        }
    if method == "tools/list":
        return {"tools": [{"name": "environment", "description": "How this server was started."}]}
    if method == "tools/call":
        return {"content": [{"type": "text", "text": json.dumps(facts())}]}
    raise LookupError(method)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        try:
            body = {"result": handle(request)}
        except LookupError as error:
            body = {"error": {"code": -32601, "message": str(error)}}
        sys.stdout.write(
            json.dumps({"jsonrpc": "2.0", "id": request.get("id"), **body}) + chr(10)
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
'''


class _FileProvider:
    """A credential provider that is one file and one command, so this runs on every platform."""

    provider = "test-file"

    def __init__(self, path: str) -> None:
        self.path = path

    def resolution_argv(self, reference: CredentialReference) -> tuple[str, ...]:
        return ("/bin/cat", self.path)


def speak(command: str, requests: list[dict]) -> list[dict]:
    """Run `command` as a harness would and exchange newline-delimited JSON-RPC with it."""

    payload = "".join(json.dumps(request) + "\n" for request in requests)
    completed = subprocess.run(
        [command],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=120,
        # Deliberately bare. Every value the server needs must arrive through the launcher.
        env={"PATH": "/usr/bin:/bin"},
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"launcher exited {completed.returncode}: {completed.stderr.decode('utf-8')}"
        )
    return [json.loads(line) for line in completed.stdout.decode("utf-8").splitlines() if line]


class InstalledMcpServerTest(unittest.TestCase):
    """One artifact, installed the canonical way, then started the way a harness starts it."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name)
        self.root = self.scope / ".tabnine/agent/aart/mcp/github"
        self.environment = ArtifactEnvironment(ARTIFACT, str(self.root))
        self.token = secrets.token_hex(32)
        self.organisation = "acme corp; echo not-executed"

        payload = pathlib.Path(self.environment.payload)
        payload.mkdir(parents=True)
        (payload / "server.py").write_text(SERVER_SOURCE, encoding="utf-8")

        secret_file = self.scope / "provider-store"
        secret_file.write_text(self.token, encoding="utf-8")
        secret_file.chmod(0o600)
        self.provider = _FileProvider(str(secret_file))

        created = LocalPythonRuntime(self.environment).create_environment(
            CreatePythonEnvironment(ARTIFACT, self.environment.environment, sys.executable)
        )
        self.assertIsInstance(created, Ok, getattr(created, "diagnostics", ()))

    def bound_inputs(self, provider_name: str) -> BoundInputs:
        token = InputId("github-token")
        org = InputId("github-org")
        return BoundInputs(
            (
                BoundInput(
                    SecretInput(token, EnvironmentBinding("GITHUB_TOKEN")),
                    SecretProviderReference(
                        token, CredentialProviderRef(provider_name, "aart-e2e", "github-token")
                    ),
                ),
                BoundInput(
                    ConfigInput(org, EnvironmentBinding("GITHUB_ORG")),
                    PersistedConfigValue(org, self.organisation),
                ),
            )
        )

    def install(self, resolver: object, provider_name: str) -> InstallationReceipt:
        bound = self.bound_inputs(provider_name)
        contract = LaunchContract("server.py", Transport.STDIO, ("--strict",))
        generated = generate_launcher(
            self.environment,
            contract,
            bound,
            resolvers=(resolver,),  # type: ignore[arg-type]
        )
        self.assertIsInstance(generated, Ok, getattr(generated, "diagnostics", ()))
        projection = generated.value

        written = LocalProjectionWriter(self.environment).write(projection)
        self.assertIsInstance(written, Ok, getattr(written, "diagnostics", ()))
        self.assertTrue(written.value.changed)

        registration = McpRegistration(
            mcp_target("tabnine", Scope.PROJECT), "github", projection.command
        )
        registered = LocalHarnessRegistry(str(self.scope)).register(registration)
        self.assertIsInstance(registered, Ok, getattr(registered, "diagnostics", ()))

        return InstallationReceipt(
            ARTIFACT,
            self.environment.root,
            projection.path,
            written.value.digest,
            self.environment.interpreter,
            Transport.STDIO,
            (registration,),
            bound.credential_references,
            tuple(config_fingerprint(name, value) for name, value in bound.config_values),
        )

    def recorded_command(self) -> str:
        settings = json.loads(
            (self.scope / ".tabnine/agent/settings.json").read_text(encoding="utf-8")
        )
        return settings["mcpServers"]["github"]["command"]

    def test_the_harness_records_a_command_that_starts_a_real_mcp_server(self):
        self.install(self.provider, "test-file")
        command = self.recorded_command()
        self.assertTrue(os.access(command, os.X_OK))

        replies = speak(
            command,
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {}},
            ],
        )
        self.assertEqual([reply["id"] for reply in replies], [1, 2, 3])
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "aart-e2e-github")
        self.assertEqual(replies[1]["result"]["tools"][0]["name"], "environment")
        facts = json.loads(replies[2]["result"]["content"][0]["text"])

        self.assertEqual(facts["executable"], self.environment.interpreter)
        self.assertEqual(facts["prefix"], self.environment.environment)
        self.assertEqual(facts["argv"], ["--strict"])
        # The config value crossed a shell without being interpreted by it.
        self.assertEqual(facts["org"], self.organisation)
        self.assertTrue(facts["token_present"])
        self.assertEqual(
            facts["token_sha256"], hashlib.sha256(self.token.encode("utf-8")).hexdigest()
        )

    def test_aart_is_not_present_in_the_runtime_the_installation_produced(self):
        self.install(self.provider, "test-file")
        facts = json.loads(
            speak(
                self.recorded_command(),
                [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}],
            )[0]["result"]["content"][0]["text"]
        )
        self.assertFalse(facts["aart_importable"])
        self.assertNotIn("aart", os.listdir(f"{self.environment.environment}/bin"))

    def test_no_secret_value_reaches_the_launcher_the_receipt_or_the_harness_file(self):
        receipt = self.install(self.provider, "test-file")
        launcher = pathlib.Path(receipt.launcher).read_text(encoding="utf-8")
        settings = (self.scope / ".tabnine/agent/settings.json").read_text(encoding="utf-8")
        projected = json.dumps(installation_receipt_to_data(receipt))
        for surface, name in (
            (launcher, "launcher"),
            (settings, "harness settings"),
            (projected, "receipt"),
        ):
            with self.subTest(surface=name):
                self.assertNotIn(self.token, surface)
        self.assertIn("test-file:aart-e2e/github-token", projected)
        # The config value is fingerprinted, not copied.
        self.assertNotIn(self.organisation, projected)

    def test_writing_the_same_installation_again_changes_nothing(self):
        first = self.install(self.provider, "test-file")
        before = pathlib.Path(first.launcher).read_bytes()
        bound = self.bound_inputs("test-file")
        generated = generate_launcher(
            self.environment,
            LaunchContract("server.py", Transport.STDIO, ("--strict",)),
            bound,
            resolvers=(self.provider,),  # type: ignore[arg-type]
        )
        again = LocalProjectionWriter(self.environment).write(generated.value)
        self.assertFalse(again.value.changed)
        self.assertEqual(pathlib.Path(first.launcher).read_bytes(), before)

    def test_a_launcher_for_another_artifact_is_never_written_here(self):
        elsewhere = ArtifactEnvironment("mcp/other", str(self.scope / "other"))
        generated = generate_launcher(
            elsewhere, LaunchContract("server.py"), BoundInputs(), resolvers=()
        )
        refused = LocalProjectionWriter(self.environment).write(generated.value)
        self.assertIsInstance(refused, Err)
        self.assertFalse((self.scope / "other").exists())

    def test_the_launcher_reports_a_missing_environment_instead_of_starting_something_else(self):
        self.install(self.provider, "test-file")
        os.rename(self.environment.interpreter, f"{self.environment.interpreter}.moved")
        completed = subprocess.run(
            [self.recorded_command()],
            capture_output=True,
            timeout=60,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(completed.returncode, 78)
        self.assertIn("no runtime environment", completed.stderr.decode("utf-8"))

    def test_the_launcher_fails_loudly_when_the_provider_will_not_answer(self):
        self.install(self.provider, "test-file")
        os.remove(self.provider.path)
        completed = subprocess.run(
            [self.recorded_command()],
            capture_output=True,
            timeout=60,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(completed.returncode, 77)
        self.assertIn("could not read", completed.stderr.decode("utf-8"))

    def test_the_finished_installation_verifies_against_its_own_receipt(self):
        receipt = self.install(self.provider, "test-file")
        registry = LocalHarnessRegistry(str(self.scope))
        self.assertEqual(
            verify_installation(receipt, observe_installation(receipt, registry=registry)), ()
        )

        # And it stops verifying the moment somebody edits the launcher the harness will run.
        pathlib.Path(receipt.launcher).write_text("#!/bin/sh\nexec /bin/false\n", encoding="utf-8")
        self.assertEqual(
            verify_installation(receipt, observe_installation(receipt, registry=registry)),
            (VerificationFinding.LAUNCHER_CHANGED,),
        )

    @unittest.skipUnless(
        sys.platform == "darwin" and os.access(SECURITY_TOOL, os.X_OK),
        "the real Keychain path needs macOS",
    )
    def test_the_real_keychain_delivers_the_secret_to_the_launched_server(self):
        keychain = str(self.scope / f"aart-e2e-{uuid.uuid4().hex}.keychain-db")
        password = uuid.uuid4().hex
        subprocess.run(
            [SECURITY_TOOL, "create-keychain", "-p", password, keychain],
            check=True,
            capture_output=True,
            timeout=60,
        )
        self.addCleanup(
            subprocess.run,
            [SECURITY_TOOL, "delete-keychain", keychain],
            check=False,
            capture_output=True,
            timeout=60,
        )
        for argv in (
            [SECURITY_TOOL, "set-keychain-settings", keychain],
            [SECURITY_TOOL, "unlock-keychain", "-p", password, keychain],
            [
                SECURITY_TOOL,
                "add-generic-password",
                "-a",
                "github-token",
                "-s",
                "aart-e2e",
                "-w",
                self.token,
                keychain,
            ],
        ):
            subprocess.run(argv, check=True, capture_output=True, timeout=60)

        self.install(MacOsKeychainProvider(keychain=keychain), "macos-keychain")
        facts = json.loads(
            speak(
                self.recorded_command(),
                [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}],
            )[0]["result"]["content"][0]["text"]
        )
        self.assertEqual(
            facts["token_sha256"], hashlib.sha256(self.token.encode("utf-8")).hexdigest()
        )
        self.assertEqual(facts["executable"], self.environment.interpreter)
        self.assertNotIn(
            self.token, pathlib.Path(self.environment.root, "launch.sh").read_text("utf-8")
        )


if __name__ == "__main__":
    unittest.main()
