"""End to end: an author's repository, compiled, published, and installed from what it declares.

The other install E2E starts from a `PlannedInstallation` a test wrote. This one starts from an
author's manifest and never writes one: the runtime, the dependency descriptor, the launch
arguments and both runtime inputs are declared once in `aart.json`, compiled into a package,
written to a store as bytes, and read back out of `artifact.json` by the machine doing the
installing -- which has never seen the author's repository.

The proof is what happens afterwards. The server the author wrote starts through a launcher nobody
wrote, with the arguments the manifest declared, the configuration value a person supplied and a
secret read at launch from a provider, out of an interpreter the installation owns.

The same run is drawn. Screens 05 to 11 are read out of the running consumer application, reached
by the routes a person navigates, so what somebody would have confirmed before this install is the
install that ran.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import sys
import tempfile
import unittest
from dataclasses import asdict

from agent_artifacts.application.artifact_installation import (
    installation_remediations,
    plan_artifact_installation,
)
from agent_artifacts.application.consumer_session import (
    assemble_consumer_machine,
    begin_installation,
    record_installation,
)
from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerScreen
from agent_artifacts.application.execution import (
    InstallationExecutionStatus,
    execute_installation,
)
from agent_artifacts.application.installation_action import (
    complete_installation_action,
    prepare_installation_action,
)
from agent_artifacts.application.installation_offer import ArtifactPlacement, offer_installation
from agent_artifacts.application.installation_planning import inspect_requirements
from agent_artifacts.application.installation_proposal import (
    desired_state_for,
    intended_receipt,
)
from agent_artifacts.application.installed_state import current_state_from_observation
from agent_artifacts.application.receipt_recording import record_installation_transaction
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
from agent_artifacts.io.consumer_machine import read_consumer_machine
from agent_artifacts.io.environment_inspection import LocalEnvironmentInspector
from agent_artifacts.io.execution import LocalMutationLock
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.installation_execution import interpreters_for
from agent_artifacts.io.object_store import publish_object, read_object
from agent_artifacts.io.receipt_store import LocalReceiptStore
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
from agent_artifacts.tui_consumer import CanonicalScreenSource, _reload, frame, screens_from
from tests.consumer_session_e2e_test import TODAY, _route
from tests.mcp_stdio_e2e_test import SERVER_SOURCE, _FileProvider, speak

MOMENT = "2026-08-31T17:05:00+00:00"

TOKEN = InputId("github-token")
ORG = InputId("github-org")
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")

MANIFEST = {
    "schema": "aart.dev/mcp/v1",
    "artifact": {"name": "github", "kind": "mcp", "version": "1.5.0"},
    "payload": {"include": ["server.py", "requirements.txt"]},
    "transport": {"type": "stdio"},
    "runtime": {"type": "python", "version": ">=3.11"},
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
    "compatibility": {"harnesses": ["tabnine"]},
}


class AuthoredInstallationTest(unittest.TestCase):
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

        self.planned = self._plan()
        self.environment = self.planned.environment
        self.desired = desired_state_for(self.planned)
        self.receipt = intended_receipt(self.planned)
        self.facts, self.remediations = self._offer()

    # -- the author's side -------------------------------------------------------------------

    def _compile(self):
        repository = self.scope / "author"
        (repository / "github").mkdir(parents=True)
        (repository / "github/aart.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        (repository / "github/server.py").write_text(SERVER_SOURCE, encoding="utf-8")
        # Empty of packages on purpose: this proves the descriptor is carried, read and honoured
        # without the test reaching a package index.
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
        """Put the canonical package in the object store, the way anything downstream receives it."""

        self.paths = object_store_paths(str(self.scope / "store"))
        candidate = make_object_candidate(compiled.canonical_entries)
        self.assertIsInstance(candidate, Ok, getattr(candidate, "diagnostics", ()))
        published = publish_object(ObjectPublishCommand(self.paths, candidate.value))
        self.assertIsInstance(published, Ok, getattr(published, "diagnostics", ()))
        self.object_digest = candidate.value.digest
        return compiled.package

    # -- the installing machine's side -------------------------------------------------------

    def _describe(self):
        """Read what the artifact needs out of the store, not from the compiler in memory."""

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
                digest,
                PromotionMode.VENDORED,
                PublicationStage.PUBLISHED,
            ),
            (KIT,),
        )

    def _capabilities(self) -> tuple[RemediationCapability, ...]:
        """What this machine can actually be asked to fix, and nothing it cannot."""

        return (
            RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, "pip"),
            RemediationCapability(RemediationCapabilityKind.CREDENTIAL_PROVIDER, "test-file"),
            RemediationCapability(RemediationCapabilityKind.HARNESS_CONFIGURATION, "tabnine"),
        )

    def _plan(self):
        planned = plan_artifact_installation(
            self._resolved(),
            self.description,
            root=str(self.scope / ".tabnine/agent/aart/mcp/github"),
            payload_source=str(self.published),
            sources=(
                SecretProviderReference(
                    TOKEN, CredentialProviderRef("test-file", "aart-e2e", "github-token")
                ),
                PersistedConfigValue(ORG, "acme"),
            ),
            policy=EffectivePolicy(),
            facts=EnvironmentFacts(sys.platform, remediation_capabilities=self._capabilities()),
            base_interpreter=sys.executable,
            targets=(mcp_target("tabnine", Scope.PROJECT),),
            resolvers=(self.provider,),  # type: ignore[arg-type]
        )
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        return planned.value

    def _offer(self):
        """Inspect this machine for what the package asked for, and offer what would fix it."""

        inspected = inspect_requirements(
            self.planned.requirements, LocalEnvironmentInspector(self._capabilities())
        )
        self.assertIsInstance(inspected, Ok, getattr(inspected, "diagnostics", ()))
        options = installation_remediations((self.planned,), inspected.value, EffectivePolicy())
        self.assertIsInstance(options, Ok, getattr(options, "diagnostics", ()))
        return inspected.value, tuple(item.remediation for item in options.value)

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

    def _interpreters(self, installations=None):
        assembled = interpreters_for(
            (self.planned,) if installations is None else installations,
            registry=self.registry,
            credential_providers=(self.provider,),  # type: ignore[arg-type]
            timeout_seconds=300.0,
            offline=True,
        )
        self.assertIsInstance(assembled, Ok, getattr(assembled, "diagnostics", ()))
        return assembled.value

    def _begin(self):
        begun = begin_installation(
            (self.planned,),
            self._selection(),
            self.facts,
            EffectivePolicy(),
            observed=((self.package.coordinate, self._inspect()),),
            selected_remediations=self.remediations,
        )
        self.assertIsInstance(begun, Ok, getattr(begun, "diagnostics", ()))
        return begun.value

    def _install(self, flow=None):
        """Run the whole confirmed Selection, the way a confirmation runs it.

        One artifact is a transaction with one member, so this goes through the same
        `execute_installation` a bulk install goes through rather than a per-artifact shortcut.
        """

        flow = self._begin() if flow is None else flow
        executed = execute_installation(
            flow.proposal,
            policy=EffectivePolicy(),
            interpreters=self._interpreters(),
            inspect=self._inspect,
            lock=LocalMutationLock(self.state_root, str(self.scope)),
        )
        self.assertIsInstance(executed, Ok, getattr(executed, "diagnostics", ()))
        return flow.proposal, executed.value

    def _drawn(self, screen: ConsumerScreen, flow, machine=None) -> str:
        """Draw one screen of this flow, reached the way a person reaches it."""

        source = CanonicalScreenSource(
            screens_from(
                assemble_consumer_machine((), today=TODAY) if machine is None else machine,
                plan=flow.plan,
                transaction=flow.outcome,
            )
        )
        state = _reload(source, ConsumerUiState(), entering=True)
        for hop in _route(screen):
            state, _ = reduce_consumer_ui(
                state, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=hop)
            )
            state = _reload(source, state, entering=True)
        self.assertIs(state.session.screen, screen)
        return "\n".join(frame(source, state))

    def _server_answers(self) -> dict:
        settings = json.loads(
            (self.scope / ".tabnine/agent/settings.json").read_text(encoding="utf-8")
        )
        reply = speak(
            settings["mcpServers"]["github"]["command"],
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}],
        )
        return json.loads(reply[0]["result"]["content"][0]["text"])

    # -- what has to be true ------------------------------------------------------------------

    def test_the_composed_offer_is_the_one_this_test_wired_by_hand(self) -> None:
        """`offer_installation` is what production will call, so it has to reach the same answer.

        This test built the plan, the measurement and the remediation offer separately, because
        until now nothing put them together. If the composition disagreed with the hand-wiring on
        any of the three, the path a person reaches would not be the path this file proves works.
        """

        offered = offer_installation(
            (
                ArtifactPlacement(
                    self._resolved(),
                    self.description,
                    root=str(self.scope / ".tabnine/agent/aart/mcp/github"),
                    payload_source=str(self.published),
                    targets=(mcp_target("tabnine", Scope.PROJECT),),
                    sources=(
                        SecretProviderReference(
                            TOKEN, CredentialProviderRef("test-file", "aart-e2e", "github-token")
                        ),
                        PersistedConfigValue(ORG, "acme"),
                    ),
                ),
            ),
            policy=EffectivePolicy(),
            facts=EnvironmentFacts(sys.platform, remediation_capabilities=self._capabilities()),
            inspect=LocalEnvironmentInspector(self._capabilities()),
            observe=lambda _planned: self._inspect(),
            base_interpreter=sys.executable,
            resolvers=(self.provider,),
        )

        self.assertIsInstance(offered, Ok, getattr(offered, "diagnostics", ()))
        offer = offered.value
        self.assertEqual(offer.installations, (self.planned,))
        self.assertEqual(offer.facts, self.facts)
        self.assertEqual(offer.selected(), self.remediations)
        self.assertEqual([str(item) for item, _ in offer.observed], [str(self.package.coordinate)])

    def test_the_composed_offer_installs_for_real(self) -> None:
        """One action, reviewed, accepted, run and recorded through the shared application seam."""

        prepared = prepare_installation_action(
            self._selection(),
            (
                ArtifactPlacement(
                    self._resolved(),
                    self.description,
                    root=str(self.scope / ".tabnine/agent/aart/mcp/github"),
                    payload_source=str(self.published),
                    targets=(mcp_target("tabnine", Scope.PROJECT),),
                    sources=(
                        SecretProviderReference(
                            TOKEN, CredentialProviderRef("test-file", "aart-e2e", "github-token")
                        ),
                        PersistedConfigValue(ORG, "acme"),
                    ),
                ),
            ),
            policy=EffectivePolicy(),
            facts=EnvironmentFacts(sys.platform, remediation_capabilities=self._capabilities()),
            inspect=LocalEnvironmentInspector(self._capabilities()),
            observe=lambda _planned: self._inspect(),
            selected_remediations=None,
            base_interpreter=sys.executable,
            resolvers=(self.provider,),
        )
        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
        completed = complete_installation_action(
            prepared.value,
            expected_review_digest=prepared.value.review_digest,
            policy=EffectivePolicy(),
            interpreters=self._interpreters(prepared.value.installations),
            inspect=self._inspect,
            lock=LocalMutationLock(self.state_root, str(self.scope)),
            store=LocalReceiptStore(self.state_root),
            recorded_at=MOMENT,
        )

        self.assertIsInstance(completed, Ok, getattr(completed, "diagnostics", ()))
        self.assertEqual(
            completed.value.recorded.receipt.review_digest, str(prepared.value.review_digest)
        )
        self.assertEqual(self._server_answers()["org"], "acme")

    def test_an_authored_manifest_installs_and_the_server_answers_what_it_declared(self) -> None:
        _, outcome = self._install()

        self.assertIs(outcome.status, InstallationExecutionStatus.COMPLETED)
        answers = self._server_answers()
        self.assertEqual(answers["argv"], ["--strict"])
        self.assertEqual(answers["org"], "acme")
        self.assertTrue(answers["token_present"])
        self.assertTrue(self.environment.owns(answers["executable"]))
        self.assertFalse(answers["aart_importable"])

    def test_the_payload_that_is_installed_is_the_one_the_store_verified(self) -> None:
        self._install()

        self.assertTrue(
            str(self.published).startswith(self.paths.objects),
            "the payload an install copies from has to be the store's verified copy",
        )
        self.assertEqual(
            (self.published / "server.py").read_bytes(),
            pathlib.Path(self.environment.payload_path("server.py")).read_bytes(),
        )

    def test_the_declared_dependencies_are_installed_into_the_environment_it_owns(self) -> None:
        proposal, _ = self._install()

        installed = {type(effect).__name__ for effect in proposal.effects}
        self.assertIn("InstallPythonDependencies", installed)
        self.assertTrue(pathlib.Path(self.environment.interpreter).exists())
        self.assertTrue(
            pathlib.Path(self.environment.payload_path("requirements.txt")).exists(),
            "the descriptor an installer read has to have travelled inside the payload",
        )

    def test_the_review_screens_draw_this_install_rather_than_an_empty_flow(self) -> None:
        """Screens 05 to 09, read out of the shell rather than out of a view a test built."""

        flow = self._begin()

        review = self._drawn(ConsumerScreen.REVIEW_SELECTION, flow)
        inspection = self._drawn(ConsumerScreen.AUTOMATIC_INSPECTION, flow)
        inputs = self._drawn(ConsumerScreen.REQUIRED_INPUTS, flow)
        ready = self._drawn(ConsumerScreen.READY, flow)

        for drawn in (review, inspection, inputs, ready):
            self.assertNotIn("Nothing has been planned yet", drawn)
        self.assertIn(str(self.package.coordinate), review)
        self.assertIn("python-runtime", inspection)
        self.assertIn("GitHub token", inputs)
        self.assertIn("GitHub organisation", inputs)

    def test_the_success_screen_reports_the_install_that_actually_ran(self) -> None:
        flow = self._begin()
        _, outcome = self._install(flow)

        recorded = record_installation(flow, outcome, recorded_at=MOMENT)
        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))

        drawn = self._drawn(ConsumerScreen.SUCCESS, recorded.value)
        self.assertNotIn("Nothing has run yet", drawn)
        self.assertIn(str(self.package.coordinate), drawn)

    def test_no_drawn_screen_carries_the_secret_the_install_arranges_to_read(self) -> None:
        """§156: what a person reads is a surface, and a surface never carries a credential."""

        flow = self._begin()
        _, outcome = self._install(flow)
        recorded = record_installation(flow, outcome, recorded_at=MOMENT).value

        drawn = "\n".join(
            self._drawn(screen, recorded)
            for screen in (
                ConsumerScreen.REVIEW_SELECTION,
                ConsumerScreen.AUTOMATIC_INSPECTION,
                ConsumerScreen.REQUIRED_INPUTS,
                ConsumerScreen.REMEDIATION,
                ConsumerScreen.READY,
                ConsumerScreen.SUCCESS,
            )
        )

        self.assertNotIn(self.token, drawn)
        self.assertIn("github-token", drawn)

    def test_the_transaction_this_run_recorded_is_what_the_next_machine_reads(self) -> None:
        """A receipt nobody can read back is not a record (B-030).

        Nothing in-memory survives: the machine is read from the state root and the harness root
        this install actually wrote, by a reader that has never seen the proposal.
        """

        flow = self._begin()
        _, outcome = self._install(flow)

        recorded = record_installation_transaction(
            outcome,
            recorded_at=MOMENT,
            store=LocalReceiptStore(self.state_root),
            receipts=((self.package.coordinate, intended_receipt(self.planned)),),
        )
        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))

        reread = read_consumer_machine(
            state_root=self.state_root,
            harness_root=str(self.scope),
            today=TODAY,
            project_root=str(self.scope),
            user_home=str(self.scope / "home"),
            data_root=str(self.scope / "data"),
        )

        self.assertIsInstance(reread, Ok, getattr(reread, "diagnostics", ()))
        machine = reread.value
        self.assertEqual(
            [item.coordinate for item in machine.installed], [str(self.package.coordinate)]
        )
        self.assertEqual(len(machine.activity.entries), 1)
        self.assertEqual(machine.activity.entries[0].summary, "Installed 1 artifact")
        self.assertEqual(len(machine.receipts), 1)
        self.assertEqual(machine.receipts[0].review_digest, str(flow.proposal.review_digest))
        self.assertEqual(
            [item.coordinate for item in machine.receipts[0].artifacts],
            [str(self.package.coordinate)],
        )
        # The Collection that asked for this artifact is still the reason it is here.
        self.assertEqual([item.collection for item in machine.collections], [KIT.owner])

    def test_the_reread_machine_carries_no_secret_and_no_invented_credential_fact(self) -> None:
        """The provider that resolves this token at launch is not an inspector, and a machine that
        cannot ask is not entitled to an answer."""

        flow = self._begin()
        _, outcome = self._install(flow)
        self.assertIsInstance(
            record_installation_transaction(
                outcome,
                recorded_at=MOMENT,
                store=LocalReceiptStore(self.state_root),
                receipts=((self.package.coordinate, intended_receipt(self.planned)),),
            ),
            Ok,
        )

        machine = read_consumer_machine(
            state_root=self.state_root,
            harness_root=str(self.scope),
            today=TODAY,
            project_root=str(self.scope),
            user_home=str(self.scope / "home"),
            data_root=str(self.scope / "data"),
        ).value

        drawn = "\n".join(
            self._drawn(screen, flow, machine)
            for screen in (ConsumerScreen.INSTALLED, ConsumerScreen.ACTIVITY)
        )
        self.assertIn(str(self.package.coordinate), drawn)
        self.assertNotIn(self.token, json.dumps(asdict(machine), default=str))
        self.assertNotIn(self.token, drawn)
        self.assertEqual([item.input for item in machine.credentials], ["github-token"])
        self.assertEqual(machine.credentials[0].health, "unknown")
        self.assertEqual(machine.credentials[0].provider_state, "unknown")
        self.assertEqual(machine.credentials[0].dependants, (str(self.package.coordinate),))

    def test_no_reviewed_surface_carries_the_secret_the_install_arranges_to_read(self) -> None:
        proposal, outcome = self._install()

        surfaces = json.dumps(
            {
                "plan": [str(item.effect) for item in proposal.plan.mutation.effects],
                "digest": str(proposal.review_digest),
                "outcome": [
                    str(item)
                    for member in outcome.artifacts
                    if member.outcome is not None
                    for item in member.outcome.primary.applied
                ],
            }
        )
        self.assertNotIn(self.token, surfaces)
        self.assertNotIn(self.token, self.planned.launcher.content)
        self.assertTrue(self._server_answers()["token_present"])


if __name__ == "__main__":
    unittest.main()
