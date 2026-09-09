"""End to end: an authored MCP server and a Skill, installed into OpenCode and read back by it.

`tests/opencode_harness_test.py` proves the target tables name locations OpenCode reads. That is
only half of a harness. This is the other half: an author's manifest, compiled, published to an
object store, planned against the measured OpenCode target and executed, with the assertions made
against the file that lands and the process that starts -- and, where OpenCode is installed,
against what OpenCode itself reports back.

The MCP half matters more here than for a harness whose shape AART already wrote. OpenCode spells a
local server as one `command` vector with a `type`, so an install that writes Claude's shape into
`opencode.json` produces a file that parses, validates, sits in the right place, and starts nothing.
Only running it catches that, which is why the launcher this install writes is executed and asked a
question, exactly as `tests/artifact_installation_e2e_test.py` does for Tabnine.
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
from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.harness import (
    Scope,
    delivery_destination,
    delivery_target,
    mcp_target,
)
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
from tests.marketplace_lifecycle_e2e_test import _FIXTURE, _environment
from tests.mcp_stdio_e2e_test import SERVER_SOURCE, _FileProvider, speak

TOKEN = InputId("github-token")
ORG = InputId("github-org")
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")

#: The same authored server the Tabnine E2E uses, declaring OpenCode instead. Everything the
#: install needs -- runtime, dependencies, launch arguments, both inputs -- is declared here once.
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
    "compatibility": {"harnesses": ["opencode"]},
}


class OpenCodeMcpInstallationTest(unittest.TestCase):
    """One authored server, installed into the project OpenCode target and then started."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name).resolve()
        self.state_root = str(self.scope / "state")
        self.registry = LocalHarnessRegistry(str(self.scope))

        self.package = self._publish(self._compile())
        self.description = self._describe()

        self.token = secrets.token_hex(32)
        secret_file = self.scope / "provider-store"
        secret_file.write_text(self.token, encoding="utf-8")
        secret_file.chmod(0o600)
        self.provider = _FileProvider(str(secret_file))

        self.target = mcp_target("opencode", Scope.PROJECT)
        self.planned = self._plan()
        self.desired = desired_state_for(self.planned)
        self.receipt = intended_receipt(self.planned)
        self.facts, self.remediations = self._offer()

    # -- the author's side -------------------------------------------------------------------

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

    # -- the installing machine's side -------------------------------------------------------

    def _describe(self):
        stored = read_object(ObjectReadRequest(self.paths, self.object_digest))
        self.assertIsInstance(stored, Ok, getattr(stored, "diagnostics", ()))
        self.assertIsNotNone(stored.value, "the package this test published is not in the store")
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
            RemediationCapability(RemediationCapabilityKind.HARNESS_CONFIGURATION, "opencode"),
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
            root=str(self.scope / ".opencode/aart/mcp/github"),
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
        """What this machine already has, and what it would be asked to arrange."""

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
        self.assertIs(executed.value.status, InstallationExecutionStatus.COMPLETED)
        return executed.value

    def _settings(self) -> dict:
        path = self.scope / self.target.settings_file
        self.assertTrue(path.exists(), f"{path} was never written")
        return json.loads(path.read_text(encoding="utf-8"))

    # -- what has to be true ------------------------------------------------------------------

    def test_the_server_is_registered_in_the_shape_opencode_reads(self) -> None:
        self._install()

        entry = self._settings()["mcp"]["github"]

        self.assertEqual("local", entry["type"])
        self.assertIsInstance(entry["command"], list)
        # The launcher this install wrote is the whole vector: the author's `--strict` is baked
        # into the script, which is what keeps a harness from having to reproduce it.
        self.assertEqual(
            [os.path.join(str(self.scope), ".opencode/aart/mcp/github/launch.sh")],
            entry["command"],
        )
        self.assertNotIn("args", entry, "OpenCode reads one vector; `args` is Claude's spelling")

    def test_the_registered_command_starts_the_server_the_author_wrote(self) -> None:
        """The proof a shape is right is that something starts when the harness runs it."""

        self._install()

        command = self._settings()["mcp"]["github"]["command"]
        reply = speak(
            command[0],
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}],
        )
        answers = json.loads(reply[0]["result"]["content"][0]["text"])

        self.assertEqual(["--strict"], answers["argv"])
        self.assertEqual("acme", answers["org"])
        self.assertTrue(answers["token_present"])

    def test_the_settings_file_is_the_one_opencode_merges(self) -> None:
        self._install()

        self.assertTrue((self.scope / "opencode.json").exists())

    def test_no_written_file_carries_the_secret_the_install_reads_at_launch(self) -> None:
        self._install()

        for path in self.scope.rglob("*"):
            if path.is_file() and "provider-store" not in str(path):
                self.assertNotIn(
                    self.token, path.read_bytes().decode("utf-8", "replace"), f"{path}"
                )


class OpenCodeSkillInstallationTest(unittest.TestCase):
    """The public command, asked for OpenCode, over a real source and a real project tree."""

    def _source(self, root: pathlib.Path) -> pathlib.Path:
        """The reference source, with its Skill declaring OpenCode as well."""

        location = root / "source"
        shutil.copytree(_FIXTURE, location)
        manifest_path = location / "artifacts/skill/code-review/artifact.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["compatibility"]["profiles"] = ["claude", "opencode"]
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return location

    def test_a_skill_declaring_opencode_installs_where_opencode_reads_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = self._source(pathlib.Path(raw).resolve())
            with _environment(source) as env:
                code, payload = env.run(
                    "marketplace",
                    "install",
                    "reference/skill/code-review",
                    "--profile",
                    "opencode",
                    "--yes",
                )

                self.assertEqual(0, code, payload)
                installed = env.project / delivery_destination(
                    delivery_target("opencode", Scope.PROJECT, ArtifactKind.SKILL), "code-review"
                )
                self.assertTrue(
                    (installed / "SKILL.md").exists(),
                    sorted(str(path) for path in env.project.rglob("*")),
                )

    def test_the_skill_is_not_installed_into_another_harness_directory(self) -> None:
        """Asking for OpenCode installs for OpenCode. Claude's tree is somebody else's."""

        with tempfile.TemporaryDirectory() as raw:
            source = self._source(pathlib.Path(raw).resolve())
            with _environment(source) as env:
                env.run(
                    "marketplace",
                    "install",
                    "reference/skill/code-review",
                    "--profile",
                    "opencode",
                    "--yes",
                )

                self.assertFalse((env.project / ".claude").exists())
                self.assertFalse((env.project / ".agents").exists())


@unittest.skipUnless(shutil.which("opencode"), "OpenCode is not installed on this machine")
class InstalledOpenCodeReadsWhatWasInstalledTest(unittest.TestCase):
    """The installed OpenCode, asked what it sees, in a project and a home this test made."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.home = self.root / "home"
        self.project.mkdir()
        self.home.mkdir()

    def _run(self, *arguments: str) -> str:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("XDG_") and key != "OPENCODE_CONFIG"
        }
        environment["HOME"] = str(self.home)
        completed = subprocess.run(
            ("opencode", *arguments),
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(self.project),
            env=environment,
        )
        if completed.returncode != 0:
            self.skipTest(
                f"`opencode {' '.join(arguments)}` is unavailable: {completed.stderr[:200]}"
            )
        return completed.stdout

    def test_a_skill_delivered_where_the_table_says_is_found_by_opencode(self) -> None:
        target = delivery_target("opencode", Scope.PROJECT, ArtifactKind.SKILL)
        destination = self.project / delivery_destination(target, "aart-probe")
        destination.mkdir(parents=True)
        (destination / "SKILL.md").write_text(
            "---\nname: aart-probe\ndescription: A probe this test installed.\n---\n\nBody.\n",
            encoding="utf-8",
        )

        found = self._run("debug", "skill")

        self.assertIn("aart-probe", found)

    def test_a_server_registered_where_the_table_says_is_merged_by_opencode(self) -> None:
        target = mcp_target("opencode", Scope.PROJECT)
        (self.project / target.settings_file).write_text(
            json.dumps({"mcp": {"aart-probe": {"type": "local", "command": ["/usr/bin/true"]}}}),
            encoding="utf-8",
        )

        merged = json.loads(self._run("debug", "config"))

        self.assertIn("aart-probe", merged.get("mcp", {}))


if __name__ == "__main__":
    unittest.main()
