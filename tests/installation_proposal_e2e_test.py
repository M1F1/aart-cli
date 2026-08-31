"""End to end: an artifact nobody has installed, installed from the plan somebody reviewed.

Nothing on this machine exists at the start -- no payload, no environment, no launcher, no harness
entry. What follows is the whole canonical path: a resolved Selection is lowered into one planned
installation, inspected against the real machine, reviewed as one `InstallPlan`, and executed as
the lifecycle plans that plan named. The proof is not that the effects reported success. It is that
afterwards the server starts through its own generated launcher and answers a harness, and that a
second process reads back the receipt the plan said it would leave.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import sys
import tempfile
import unittest

from agent_artifacts.application.execution import LifecycleExecutionStatus, execute_lifecycle
from agent_artifacts.application.installation_proposal import (
    PlannedInstallation,
    desired_state_for,
    intended_receipt,
    propose_installation,
)
from agent_artifacts.application.installed_state import current_state_from_observation
from agent_artifacts.application.receipt_recording import record_lifecycle_outcome
from agent_artifacts.application.runtime_projection import generate_launcher
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.harness import McpRegistration, Scope, mcp_target
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    ObjectDigest,
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
from agent_artifacts.domain.inspection import EnvironmentFacts
from agent_artifacts.domain.launch import LaunchContract, Transport
from agent_artifacts.domain.plans import install_plan_to_data
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.reconciliation import ComponentState
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    OwnershipKind,
    OwnershipReason,
    ResolvedArtifact,
    ResolvedSelection,
    VersionConstraint,
)
from agent_artifacts.io.execution import (
    CredentialEffectInterpreter,
    FileEffectInterpreter,
    HarnessEffectInterpreter,
    LocalMutationLock,
    RuntimeEffectInterpreter,
)
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.python_runtime import LocalPythonRuntime
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.io.runtime_projection import observe_installation
from tests.mcp_stdio_e2e_test import SERVER_SOURCE, _FileProvider, speak

ARTIFACT = "mcp/github"
COORDINATE = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.5.0")
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")
TOKEN = InputId("github-token")
ORG = InputId("github-org")


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


class ProposedInstallationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name)
        self.state_root = str(self.scope / "state")
        self.store = LocalReceiptStore(self.state_root)
        self.registry = LocalHarnessRegistry(str(self.scope))

        # Where the artifact is published from, and where nothing is installed yet.
        self.source = self.scope / "store/github"
        self.source.mkdir(parents=True)
        (self.source / "server.py").write_text(SERVER_SOURCE, encoding="utf-8")
        self.root = self.scope / ".tabnine/agent/aart/mcp/github"
        self.environment = ArtifactEnvironment(ARTIFACT, str(self.root))

        self.token = secrets.token_hex(32)
        secret_file = self.scope / "provider-store"
        secret_file.write_text(self.token, encoding="utf-8")
        secret_file.chmod(0o600)
        self.provider = _FileProvider(str(secret_file))

        self.contract = LaunchContract("server.py", Transport.STDIO, ("--strict",))
        self.launcher = generate_launcher(
            self.environment,
            self.contract,
            self.bound(),
            resolvers=(self.provider,),  # type: ignore[arg-type]
        ).value
        self.registration = McpRegistration(
            mcp_target("tabnine", Scope.PROJECT), "github", self.launcher.command
        )
        self.planned = PlannedInstallation(
            self.resolved(),
            self.environment,
            self.contract,
            self.launcher,
            self.bound(),
            (self.registration,),
            payload_source=str(self.source),
            base_interpreter=sys.executable,
            runtime="python",
        )
        self.desired = desired_state_for(self.planned)
        self.receipt = intended_receipt(self.planned)

    def bound(self) -> BoundInputs:
        return BoundInputs(
            (
                BoundInput(
                    SecretInput(TOKEN, EnvironmentBinding("GITHUB_TOKEN")),
                    SecretProviderReference(
                        TOKEN, CredentialProviderRef("test-file", "aart-e2e", "github-token")
                    ),
                ),
                BoundInput(
                    ConfigInput(ORG, EnvironmentBinding("GITHUB_ORG")),
                    PersistedConfigValue(ORG, "acme"),
                ),
            )
        )

    def resolved(self) -> ResolvedArtifact:
        return ResolvedArtifact(
            RegistryArtifactVersion(
                COORDINATE,
                CandidateId("b" * 64),
                _digest("a"),
                _digest("c"),
                _digest("d"),
                _digest("e"),
                PromotionMode.VENDORED,
                PublicationStage.PUBLISHED,
            ),
            (KIT,),
        )

    def selection(self) -> ResolvedSelection:
        artifact = self.planned.artifact
        return ResolvedSelection(
            ArtifactSelection(
                (
                    ArtifactRequest(
                        COORDINATE.artifact,
                        VersionConstraint(COORDINATE.version or "*"),
                        COORDINATE.source,
                    ),
                )
            ),
            (artifact,),
        )

    def inspect(self, _=None):
        """What this machine currently says about the artifact, measured every time."""

        return current_state_from_observation(
            self.desired,
            self.receipt,
            observe_installation(self.receipt, registry=self.registry),
            credentials=(
                (
                    str(TOKEN),
                    ComponentState.MATCHED
                    if os.path.exists(self.provider.path)
                    else ComponentState.ABSENT,
                ),
            ),
        )

    def interpreters(self):
        files = FileEffectInterpreter(self.environment)
        files.offer(self.launcher.content.encode("utf-8"))
        return (
            files,
            RuntimeEffectInterpreter(LocalPythonRuntime(self.environment)),
            HarnessEffectInterpreter(
                self.registry, (self.registration,), artifact=self.environment.artifact
            ),
            CredentialEffectInterpreter(
                self.provider,  # type: ignore[arg-type]
                self.receipt.credentials,
            ),
        )

    def propose(self):
        proposed = propose_installation(
            (self.planned,),
            self.selection(),
            EnvironmentFacts("darwin", ()),
            EffectivePolicy(),
            observed=((COORDINATE, self.inspect()),),
        )
        self.assertIsInstance(proposed, Ok, getattr(proposed, "diagnostics", ()))
        return proposed.value

    def install(self):
        proposal = self.propose()
        executed = execute_lifecycle(
            proposal.lifecycle[0],
            policy=EffectivePolicy(),
            interpreters=self.interpreters(),
            inspect=self.inspect,
            lock=LocalMutationLock(self.state_root, str(self.scope)),
        )
        self.assertIsInstance(executed, Ok, getattr(executed, "diagnostics", ()))
        return proposal, executed.value

    def server_answers(self) -> dict:
        settings = json.loads(
            (self.scope / ".tabnine/agent/settings.json").read_text(encoding="utf-8")
        )
        reply = speak(
            settings["mcpServers"]["github"]["command"],
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}],
        )
        return json.loads(reply[0]["result"]["content"][0]["text"])

    def test_a_reviewed_plan_installs_an_artifact_that_then_answers_its_harness(self) -> None:
        _, outcome = self.install()

        self.assertIs(outcome.status, LifecycleExecutionStatus.COMPLETED)
        answers = self.server_answers()
        self.assertEqual(answers["argv"], ["--strict"])
        self.assertEqual(answers["org"], "acme")
        self.assertTrue(answers["token_present"])
        self.assertTrue(self.environment.owns(answers["executable"]))
        self.assertFalse(answers["aart_importable"])

    def test_the_receipt_the_plan_intended_is_the_receipt_a_second_process_reads(self) -> None:
        _, outcome = self.install()

        recorded = record_lifecycle_outcome(
            outcome,
            recorded_at="2026-08-31T14:32:00+00:00",
            store=self.store,
            receipt=self.receipt,
        )

        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        read = LocalReceiptStore(self.state_root).record(COORDINATE)
        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        self.assertEqual(read.value.receipt, self.receipt)
        self.assertEqual(read.value.ownership, (KIT,))

    def test_running_the_same_proposal_again_changes_nothing(self) -> None:
        self.install()

        second = self.propose()

        self.assertTrue(second.converged)
        self.assertEqual(second.plan.mutation.effects, ())
        self.assertEqual(self.server_answers()["org"], "acme")

    def test_a_credential_already_held_by_its_provider_is_not_stored_again(self) -> None:
        proposal = self.propose()

        kinds = {type(item.effect).__name__ for item in proposal.plan.mutation.effects}

        self.assertEqual(
            kinds, {"CopyTree", "CreatePythonEnvironment", "WriteFile", "ConfigureHarness"}
        )

    def test_the_reviewed_plan_never_carries_the_secret_the_installation_delivers(self) -> None:
        proposal, _ = self.install()

        encoded = json.dumps(install_plan_to_data(proposal.plan), sort_keys=True)

        self.assertNotIn(self.token, encoded)
        self.assertTrue(self.server_answers()["token_present"])
        launcher = pathlib.Path(self.receipt.launcher).read_text(encoding="utf-8")
        self.assertNotIn(self.token, launcher)


if __name__ == "__main__":
    unittest.main()
