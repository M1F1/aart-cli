"""CP-12 end to end: break a real installation one component at a time, and repair it.

Every repair below runs through the real interpreters against real files, and every one is followed
by a fresh inspection rather than by an assumption. The final check is the only one that really
matters: after the repair, the server starts again through its own launcher and answers.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import shutil
import sys
import tempfile
import unittest

from agent_artifacts.application.execution import (
    ExecutionStatus,
    StepStatus,
    execute_repair,
    execution_outcome_to_data,
)
from agent_artifacts.application.installation_verification import verify_installation
from agent_artifacts.application.installed_state import (
    current_state_from_observation,
    desired_state_from_receipt,
    removal_state_from_receipt,
)
from agent_artifacts.application.reconciliation import plan_repair
from agent_artifacts.application.runtime_projection import generate_launcher
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.effects import CreatePythonEnvironment
from agent_artifacts.domain.harness import McpRegistration, Scope, mcp_target
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    SourceAlias,
)
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
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import InstallationReceipt
from agent_artifacts.domain.reconciliation import Component, ComponentId, ComponentState
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.execution import (
    CredentialEffectInterpreter,
    FileEffectInterpreter,
    HarnessEffectInterpreter,
    RuntimeEffectInterpreter,
)
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.python_runtime import LocalPythonRuntime
from agent_artifacts.io.runtime_projection import LocalProjectionWriter, observe_installation
from tests.mcp_stdio_e2e_test import SERVER_SOURCE, _FileProvider, speak

ARTIFACT = "mcp/github"
COORDINATE = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.5.0")


class RepairedInstallationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name)
        self.root = self.scope / ".tabnine/agent/aart/mcp/github"
        self.environment = ArtifactEnvironment(ARTIFACT, str(self.root))
        self.token = secrets.token_hex(32)
        self.registry = LocalHarnessRegistry(str(self.scope))

        payload = pathlib.Path(self.environment.payload)
        payload.mkdir(parents=True)
        (payload / "server.py").write_text(SERVER_SOURCE, encoding="utf-8")
        self.source = self.scope / "store/github"
        shutil.copytree(payload, self.source)

        secret_file = self.scope / "provider-store"
        secret_file.write_text(self.token, encoding="utf-8")
        secret_file.chmod(0o600)
        self.provider = _FileProvider(str(secret_file))

        created = LocalPythonRuntime(self.environment).create_environment(
            CreatePythonEnvironment(ARTIFACT, self.environment.environment, sys.executable)
        )
        self.assertIsInstance(created, Ok, getattr(created, "diagnostics", ()))

        self.projection = generate_launcher(
            self.environment,
            LaunchContract("server.py", Transport.STDIO, ("--strict",)),
            self.bound(),
            resolvers=(self.provider,),  # type: ignore[arg-type]
        ).value
        LocalProjectionWriter(self.environment).write(self.projection)
        self.registration = McpRegistration(
            mcp_target("tabnine", Scope.PROJECT), "github", self.projection.command
        )
        self.registry.register(self.registration)
        self.receipt = InstallationReceipt(
            ARTIFACT,
            self.environment.root,
            self.projection.path,
            self.projection.digest,
            self.environment.interpreter,
            Transport.STDIO,
            (self.registration,),
            self.bound().credential_references,
        )
        self.desired = desired_state_from_receipt(
            COORDINATE, self.receipt, base_interpreter=sys.executable
        )

    def bound(self) -> BoundInputs:
        token, org = InputId("github-token"), InputId("github-org")
        return BoundInputs(
            (
                BoundInput(
                    SecretInput(token, EnvironmentBinding("GITHUB_TOKEN")),
                    SecretProviderReference(
                        token, CredentialProviderRef("test-file", "aart-e2e", "github-token")
                    ),
                ),
                BoundInput(
                    ConfigInput(org, EnvironmentBinding("GITHUB_ORG")),
                    PersistedConfigValue(org, "acme"),
                ),
            )
        )

    def interpreters(self):
        files = FileEffectInterpreter(self.environment)
        files.offer(self.projection.content.encode("utf-8"))
        return (
            files,
            RuntimeEffectInterpreter(LocalPythonRuntime(self.environment)),
            HarnessEffectInterpreter(self.registry, (self.registration,)),
            CredentialEffectInterpreter(
                self.provider,  # type: ignore[arg-type]
                self.receipt.credentials,
            ),
        )

    def inspect(self):
        return self.inspect_for(self.desired)

    def inspect_for(self, desired):
        observed = observe_installation(self.receipt, registry=self.registry)
        return current_state_from_observation(
            desired,
            self.receipt,
            observed,
            credentials=(
                (("github-token", ComponentState.MATCHED),)
                if os.path.exists(self.provider.path)
                else (("github-token", ComponentState.ABSENT),)
            ),
        )

    def repair(self, **kwargs):
        planned = plan_repair(self.desired, self.inspect(), policy=EffectivePolicy())
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        outcome = execute_repair(
            planned.value, self.desired, self.interpreters(), inspect=self.inspect, **kwargs
        )
        self.assertIsInstance(outcome, Ok, getattr(outcome, "diagnostics", ()))
        return outcome.value

    def server_answers(self) -> dict:
        settings = json.loads(
            (self.scope / ".tabnine/agent/settings.json").read_text(encoding="utf-8")
        )
        reply = speak(
            settings["mcpServers"]["github"]["command"],
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}],
        )[0]
        return json.loads(reply["result"]["content"][0]["text"])

    def test_an_intact_installation_needs_no_repair_and_touches_nothing(self):
        before = pathlib.Path(self.receipt.launcher).read_bytes()
        outcome = self.repair()
        self.assertEqual(outcome.steps, ())
        self.assertIs(outcome.status, ExecutionStatus.CONVERGED)
        self.assertEqual(pathlib.Path(self.receipt.launcher).read_bytes(), before)

    def test_an_edited_launcher_is_repaired_and_the_server_starts_again(self):
        pathlib.Path(self.receipt.launcher).write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
        with self.assertRaises(AssertionError):
            self.server_answers()

        outcome = self.repair()
        self.assertEqual(
            [(step.component, step.status) for step in outcome.steps],
            [(ComponentId(Component.LAUNCHER), StepStatus.APPLIED)],
        )
        self.assertIs(outcome.status, ExecutionStatus.CONVERGED)
        self.assertEqual(
            verify_installation(
                self.receipt, observe_installation(self.receipt, registry=self.registry)
            ),
            (),
        )

        facts = self.server_answers()
        self.assertEqual(facts["executable"], self.environment.interpreter)
        self.assertEqual(facts["org"], "acme")
        self.assertTrue(facts["token_present"])

    def test_a_deleted_harness_entry_is_restored_without_rewriting_the_launcher(self):
        launcher_before = pathlib.Path(self.receipt.launcher).stat().st_mtime_ns
        self.registry.unregister(mcp_target("tabnine", Scope.PROJECT), "github")
        outcome = self.repair()
        self.assertEqual(
            [(step.component, step.status) for step in outcome.steps],
            [(ComponentId(Component.HARNESS, "tabnine"), StepStatus.APPLIED)],
        )
        self.assertIs(outcome.status, ExecutionStatus.CONVERGED)
        self.assertEqual(pathlib.Path(self.receipt.launcher).stat().st_mtime_ns, launcher_before)
        self.assertEqual(self.server_answers()["org"], "acme")

    def test_a_destroyed_runtime_is_rebuilt_and_the_server_starts_again(self):
        shutil.rmtree(self.environment.environment)
        outcome = self.repair()
        self.assertEqual(
            [step.component for step in outcome.steps],
            [ComponentId(Component.RUNTIME_ENVIRONMENT)],
        )
        self.assertIs(outcome.status, ExecutionStatus.CONVERGED)
        self.assertTrue(os.access(self.environment.interpreter, os.X_OK))
        self.assertEqual(self.server_answers()["prefix"], self.environment.environment)

    def test_two_broken_components_are_repaired_in_dependency_order(self):
        shutil.rmtree(self.environment.environment)
        self.registry.unregister(mcp_target("tabnine", Scope.PROJECT), "github")
        outcome = self.repair()
        self.assertEqual(
            [step.component for step in outcome.steps],
            [
                ComponentId(Component.RUNTIME_ENVIRONMENT),
                ComponentId(Component.HARNESS, "tabnine"),
            ],
        )
        self.assertIs(outcome.status, ExecutionStatus.CONVERGED)
        self.assertEqual(self.server_answers()["prefix"], self.environment.environment)

    def test_a_missing_credential_reports_that_it_is_waiting_for_a_person(self):
        os.remove(self.provider.path)
        outcome = self.repair()
        self.assertEqual(
            [(step.component, step.status) for step in outcome.steps],
            [(ComponentId(Component.CREDENTIAL, "github-token"), StepStatus.FAILED)],
        )
        self.assertIs(outcome.status, ExecutionStatus.FAILED)
        self.assertIn("entered by someone", outcome.steps[0].detail)
        self.assertEqual(
            [item.component for item in outcome.residual_drift],
            [ComponentId(Component.CREDENTIAL, "github-token")],
        )

    def test_a_writer_holding_no_content_refuses_rather_than_writing_something_else(self):
        pathlib.Path(self.receipt.launcher).write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
        planned = plan_repair(self.desired, self.inspect(), policy=EffectivePolicy()).value
        empty = FileEffectInterpreter(self.environment)
        outcome = execute_repair(planned, self.desired, (empty,), inspect=self.inspect).value
        self.assertEqual(outcome.steps[0].status, StepStatus.FAILED)
        self.assertIn("nobody planned", outcome.steps[0].detail)
        self.assertEqual(
            pathlib.Path(self.receipt.launcher).read_text(encoding="utf-8"),
            "#!/bin/sh\nexit 9\n",
        )

    def test_a_repair_outcome_names_components_and_carries_no_secret(self):
        pathlib.Path(self.receipt.launcher).write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
        projected = json.dumps(execution_outcome_to_data(self.repair()))
        self.assertIn("launcher", projected)
        self.assertNotIn(self.token, projected)

    def test_uninstall_is_reverse_reconciliation_and_retains_credentials(self):
        removal = removal_state_from_receipt(COORDINATE, self.receipt)
        planned = plan_repair(removal, self.inspect_for(removal), policy=EffectivePolicy())
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        outcome = execute_repair(
            planned.value,
            removal,
            self.interpreters(),
            inspect=lambda: self.inspect_for(removal),
        ).value

        self.assertIs(outcome.status, ExecutionStatus.CONVERGED)
        self.assertEqual(
            [step.component for step in outcome.steps],
            [
                ComponentId(Component.HARNESS, "tabnine"),
                ComponentId(Component.LAUNCHER),
                ComponentId(Component.RUNTIME_ENVIRONMENT),
                ComponentId(Component.PAYLOAD),
            ],
        )
        self.assertFalse(self.root.exists())
        self.assertTrue(os.path.exists(self.provider.path))
        settings = json.loads(
            (self.scope / ".tabnine/agent/settings.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("github", settings["mcpServers"])


if __name__ == "__main__":
    unittest.main()
