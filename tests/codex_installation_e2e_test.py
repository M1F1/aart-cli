"""End to end: an authored MCP server and a Skill, installed into Codex and read back by Codex.

The Skill half is a file in a directory, and `tests/codex_harness_test.py` already proves Codex
reads it. The MCP half is the one B-096 held open, and it is different in kind from every other
harness here: AART does not write Codex's configuration, Codex does. So the thing worth proving end
to end is that a real installation -- compiled from an author's manifest, published to an object
store, planned against the measured target and executed -- ends with Codex itself listing the
server, and with the launcher that install wrote actually starting when it is run.

Codex is user scope only, which is measured rather than chosen: `codex mcp add` writes the global
configuration and offers no project flag.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest

from agent_artifacts.application.artifact_installation import (
    installation_remediations,
    plan_artifact_installation,
)
from agent_artifacts.application.consumer_session import begin_installation
from agent_artifacts.application.execution import (
    InstallationExecutionStatus,
    execute_installation,
)
from agent_artifacts.application.installation_planning import inspect_requirements
from agent_artifacts.application.installation_proposal import desired_state_for, intended_receipt
from agent_artifacts.application.installed_state import current_state_from_observation
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.harness import Scope, mcp_target
from agent_artifacts.domain.identifiers import InputId, SourceAlias
from agent_artifacts.domain.inputs import PersistedConfigValue, SecretProviderReference
from agent_artifacts.domain.inspection import (
    EnvironmentFacts,
    RemediationCapability,
    RemediationCapabilityKind,
)
from agent_artifacts.domain.policies import EffectivePolicy
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
from agent_artifacts.io.environment_inspection import LocalEnvironmentInspector
from agent_artifacts.io.execution import LocalMutationLock
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.installation_execution import interpreters_for
from agent_artifacts.io.object_store import publish_object, read_object
from agent_artifacts.io.runtime_projection import observe_installation
from agent_artifacts.protocol.authoring import (
    compile_author_snapshot,
    package_payload_root,
    read_package_description,
)
from agent_artifacts.sources.local import read_local_snapshot
from agent_artifacts.sources.model import LocalSnapshotRequest, SnapshotLimits, source_instance_id
from agent_artifacts.store.model import (
    ObjectPublishCommand,
    ObjectReadRequest,
    make_object_candidate,
    object_store_paths,
)
from tests.mcp_stdio_e2e_test import SERVER_SOURCE, _FileProvider, speak

TOKEN = InputId("github-token")
ORG = InputId("github-org")
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")

MANIFEST = {
    "schema": "aart.dev/mcp/v1",
    "artifact": {"name": "github", "kind": "mcp", "version": "1.5.0"},
    "payload": {"include": ["server.py", "requirements.txt"]},
    "transport": {"type": "stdio"},
    "runtime": {"type": "python", "version": ">=3.10"},
    "launch": {"type": "python", "entrypoint": "server.py", "arguments": ["--strict"]},
    "inputs": [
        {
            "id": "github-token",
            "kind": "secret",
            "inject": {"type": "environment", "variable": "GITHUB_TOKEN"},
            "help": {"label": "GitHub token", "format_hint": "ghp_..."},
        },
        {
            "id": "github-org",
            "kind": "config",
            "default": "acme",
            "inject": {"type": "environment", "variable": "GITHUB_ORG"},
            "help": {"label": "GitHub organisation"},
        },
    ],
    "python": {"dependencies": {"type": "requirements", "path": "requirements.txt"}},
    "compatibility": {"harnesses": ["codex"]},
}


@unittest.skipUnless(shutil.which("codex"), "Codex is not installed on this machine")
class CodexMcpInstallationTest(unittest.TestCase):
    """One authored server, installed at Codex's user scope, then listed and started."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name).resolve()
        (self.scope / ".codex").mkdir()
        self.state_root = str(self.scope / "state")
        self.registry = LocalHarnessRegistry(str(self.scope))

        self.package = self._publish(self._compile())
        self.description = self._describe()

        self.token = secrets.token_hex(32)
        secret_file = self.scope / "provider-store"
        secret_file.write_text(self.token, encoding="utf-8")
        secret_file.chmod(0o600)
        self.provider = _FileProvider(str(secret_file))

        self.target = mcp_target("codex", Scope.USER)
        self.planned = self._plan()
        self.desired = desired_state_for(self.planned)
        self.receipt = intended_receipt(self.planned)
        self.facts, self.remediations = self._offer()

    def _compile(self):
        repository = self.scope / "author"
        (repository / "github").mkdir(parents=True)
        (repository / "github/aart.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        (repository / "github/server.py").write_text(SERVER_SOURCE, encoding="utf-8")
        (repository / "github/requirements.txt").write_text(
            "# no third-party packages\n", encoding="utf-8"
        )

        alias = SourceAlias("company")
        configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(repository), None, True)
        acquired = read_local_snapshot(
            LocalSnapshotRequest(
                source_instance_id(configured), alias, str(repository), SnapshotLimits()
            )
        )
        self.assertIsInstance(acquired, Ok, getattr(acquired, "diagnostics", ()))
        compiled = compile_author_snapshot(
            acquired.value.snapshot,
            source_alias=alias,
            source="https://github.company/company/servers.git",
            revision="c" * 40,
        )
        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        return compiled.value[0]

    def _publish(self, compiled):
        self.paths = object_store_paths(str(self.scope / "store"))
        candidate = make_object_candidate(compiled.canonical_entries)
        self.assertIsInstance(candidate, Ok, getattr(candidate, "diagnostics", ()))
        published = publish_object(ObjectPublishCommand(self.paths, candidate.value))
        self.assertIsInstance(published, Ok, getattr(published, "diagnostics", ()))
        self.object_digest = candidate.value.digest
        return compiled.package

    def _describe(self):
        stored = read_object(ObjectReadRequest(self.paths, self.object_digest))
        self.assertIsInstance(stored, Ok, getattr(stored, "diagnostics", ()))
        self.published = pathlib.Path(package_payload_root(stored.value.root))
        described = read_package_description(stored.value.candidate.entries)
        self.assertIsInstance(described, Ok, getattr(described, "diagnostics", ()))
        return described.value

    def _resolved(self) -> ResolvedArtifact:
        digest = self.package.payload_digest
        return ResolvedArtifact(
            RegistryArtifactVersion(
                self.package.coordinate,
                CandidateId("b" * 64),
                self.package.provenance.input_digest,
                digest,
                digest,
                self.object_digest,
                digest,
                PromotionMode.VENDORED,
                PublicationStage.PUBLISHED,
            ),
            (KIT,),
        )

    def _capabilities(self) -> tuple[RemediationCapability, ...]:
        return (
            RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, "pip"),
            RemediationCapability(RemediationCapabilityKind.CREDENTIAL_PROVIDER, "test-file"),
            RemediationCapability(RemediationCapabilityKind.HARNESS_CONFIGURATION, "codex"),
        )

    def _sources(self):
        return (
            SecretProviderReference(
                TOKEN, CredentialProviderRef("test-file", "aart-e2e", "github-token")
            ),
            PersistedConfigValue(ORG, "acme"),
        )

    def _plan(self):
        planned = plan_artifact_installation(
            self._resolved(),
            self.description,
            root=str(self.scope / ".codex/aart/mcp/github"),
            payload_source=str(self.published),
            sources=self._sources(),
            policy=EffectivePolicy(),
            facts=EnvironmentFacts(sys.platform, remediation_capabilities=self._capabilities()),
            base_interpreter=sys.executable,
            targets=(self.target,),
            resolvers=(self.provider,),  # type: ignore[arg-type]
        )
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        return planned.value

    def _offer(self):
        inspected = inspect_requirements(
            self.planned.requirements, LocalEnvironmentInspector(self._capabilities())
        )
        self.assertIsInstance(inspected, Ok, getattr(inspected, "diagnostics", ()))
        options = installation_remediations((self.planned,), inspected.value, EffectivePolicy())
        self.assertIsInstance(options, Ok, getattr(options, "diagnostics", ()))
        return inspected.value, tuple(item.remediation for item in options.value)

    def _inspect(self, _=None):
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

    def _selection(self) -> ResolvedSelection:
        coordinate = self.package.coordinate
        return ResolvedSelection(
            ArtifactSelection(
                (
                    ArtifactRequest(
                        coordinate.artifact,
                        VersionConstraint(coordinate.version or "*"),
                        coordinate.source,
                    ),
                )
            ),
            (self.planned.artifact,),
        )

    def _install(self):
        begun = begin_installation(
            (self.planned,),
            self._selection(),
            self.facts,
            EffectivePolicy(),
            observed=((self.package.coordinate, self._inspect()),),
            selected_remediations=self.remediations,
        )
        self.assertIsInstance(begun, Ok, getattr(begun, "diagnostics", ()))
        assembled = interpreters_for(
            (self.planned,),
            registry=self.registry,
            credential_providers=(self.provider,),  # type: ignore[arg-type]
            timeout_seconds=300.0,
            offline=True,
        )
        self.assertIsInstance(assembled, Ok, getattr(assembled, "diagnostics", ()))
        executed = execute_installation(
            begun.value.proposal,
            policy=EffectivePolicy(),
            interpreters=assembled.value,
            inspect=self._inspect,
            lock=LocalMutationLock(self.state_root, str(self.scope)),
        )
        self.assertIsInstance(executed, Ok, getattr(executed, "diagnostics", ()))
        return executed.value

    def _listed(self) -> list[dict]:
        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(self.scope / ".codex")
        completed = subprocess.run(
            ("codex", "mcp", "list", "--json"),
            capture_output=True,
            text=True,
            timeout=120,
            env=environment,
        )
        self.assertEqual(0, completed.returncode, completed.stderr[:400])
        return json.loads(completed.stdout)

    # -- what has to be true ------------------------------------------------------------------

    def test_the_install_converges_rather_than_reporting_drift_it_cannot_fix(self) -> None:
        outcome = self._install()

        self.assertIs(outcome.status, InstallationExecutionStatus.COMPLETED)

    def test_codex_lists_the_server_this_install_registered(self) -> None:
        self._install()

        self.assertEqual(["github"], [entry["name"] for entry in self._listed()])

    def test_the_launcher_codex_was_given_starts_the_server_the_author_wrote(self) -> None:
        """A registration Codex accepts and cannot start is not an installation."""

        self._install()

        command = self._listed()[0]["transport"]["command"]
        reply = speak(command, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}])
        answers = json.loads(reply[0]["result"]["content"][0]["text"])

        self.assertEqual(["--strict"], answers["argv"])
        self.assertEqual("acme", answers["org"])
        self.assertTrue(answers["token_present"])

    def test_no_written_file_carries_the_secret_the_install_reads_at_launch(self) -> None:
        self._install()

        for path in self.scope.rglob("*"):
            if path.is_file() and "provider-store" not in str(path):
                self.assertNotIn(
                    self.token, path.read_bytes().decode("utf-8", "replace"), f"{path}"
                )


if __name__ == "__main__":
    unittest.main()
