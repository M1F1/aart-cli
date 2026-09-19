"""CP-23 task 16.4: reviewed configuration edits run through the lifecycle boundary."""

from __future__ import annotations

import contextlib
import json
import pathlib
import secrets
import tempfile
import unittest
from datetime import date

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
    ConsumerUiState,
)
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.application.execution import LifecycleExecutionStatus
from aart_cli.application.installation_inputs import OwnedInputSource
from aart_cli.configuration.model import SourceKind
from aart_cli.domain.credentials import CredentialProviderRef
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactCoordinate, ArtifactIdentity, SourceId
from aart_cli.domain.inputs import PromptedConfigValue, SecretProviderReference
from aart_cli.domain.installation_owner import installation_owner
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.selection import ArtifactRequest, ArtifactSelection, VersionConstraint
from aart_cli.io.configured_configuration_action import (
    complete_configured_configuration,
    prepare_configured_configuration,
)
from aart_cli.io.configured_installation_action import (
    InstallationHost,
    complete_configured_installation,
    prepare_configured_installation,
)
from aart_cli.io.consumer_actions import ConsumerActionContext, LocalConsumerActions
from aart_cli.io.consumer_machine import read_consumer_machine, read_installed_inspections
from aart_cli.io.source_store import publish_source_snapshot
from aart_cli.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from aart_cli.tui_consumer import run_consumer_shell
from tests.artifact_installation_e2e_test import MANIFEST, MOMENT, ORG, TOKEN
from tests.configured_installation_action_e2e_test import _FileCredentials
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP, _published_registry
from tests.consumer_shell_test import BACKSPACE, DOWN, ENTER, SPACE, FakeTerminal
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.mcp_stdio_e2e_test import speak

TODAY = date(2026, 9, 14)
EDITED_AT = "2026-09-14T12:00:00+00:00"
REFERENCE = CredentialProviderRef("test-file", "aart-e2e", "github-token")
HARNESSES = ("claude", "opencode", "tabnine")


class ConfiguredConfigurationActionE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        self.data_root = str(self.root / "data")
        self.project_root = str(self.root / "project")
        self.user_home = str(self.root / "home")
        pathlib.Path(self.project_root).mkdir()
        pathlib.Path(self.user_home).mkdir()

        token_file = self.root / "provider"
        token_file.write_text(secrets.token_hex(32), encoding="utf-8")
        self.provider = _FileCredentials(str(token_file))
        source = configured_source("company", SourceKind.REGISTRY_GIT)
        self.effective = effective_configuration((source,), default_registry="company")
        manifest = json.loads(json.dumps(MANIFEST))
        config_input = next(item for item in manifest["inputs"] if item["id"] == ORG.value)
        config_input["default"] = "acme-team"
        config_input["validation"] = {"type": "pattern", "pattern": "[a-z]+-team"}
        authored = tuple(
            (item[0], json.dumps(manifest)) if item[0] == "github/aart-cli.json" else item
            for item in AUTHORED_MCP
        )
        candidate = make_source_candidate(
            source_instance_id(source),
            source.alias,
            "a" * 40,
            _published_registry(authored),
        )
        assert isinstance(candidate, Ok), candidate
        published = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(source)),
                ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
                90,
            )
        )
        assert isinstance(published, Ok), published
        self.host = InstallationHost(
            self.data_root,
            self.project_root,
            self.user_home,
            Scope.PROJECT,
            HARNESSES,
        )
        selection = ArtifactSelection(
            (
                ArtifactRequest(
                    ArtifactIdentity("mcp", "github"),
                    VersionConstraint("*"),
                    source.alias,
                ),
            )
        )
        prepared = prepare_configured_installation(
            self.effective,
            selection,
            host=self.host,
            # One value on every harness is now said once per harness: each is its own
            # installation and asks its own question (D-353).
            sources=tuple(
                OwnedInputSource(
                    installation_owner(
                        ArtifactCoordinate(
                            source.alias, ArtifactIdentity("mcp", "github"), "1.0.0"
                        ),
                        scope=Scope.PROJECT,
                        root=self.project_root,
                        harness=harness,
                    ),
                    answer,
                )
                for harness in HARNESSES
                for answer in (
                    PromptedConfigValue(ORG, "original-team"),
                    SecretProviderReference(TOKEN, REFERENCE),
                )
            ),
            policy=EffectivePolicy(),
            selected_remediations=None,
            credential_providers=(self.provider,),
            resolvers=(self.provider,),
        )
        assert isinstance(prepared, Ok), prepared
        installed = complete_configured_installation(
            prepared.value,
            expected_review_digest=prepared.value.review_digest,
            host=self.host,
            policy=EffectivePolicy(),
            credential_providers=(self.provider,),
            recorded_at=MOMENT,
            today=TODAY,
            timeout_seconds=300.0,
            offline=True,
        )
        assert isinstance(installed, Ok), installed

    def _inspection(self):
        inspected = read_installed_inspections(
            state_root=self.host.state_root,
            harness_root=self.host.harness_root,
            scope=self.host.scope,
            profiles=self.host.profiles,
            credential_providers=(self.provider,),
        )
        self.assertIsInstance(inspected, Ok, getattr(inspected, "diagnostics", ()))
        assert isinstance(inspected, Ok)
        self.assertEqual(len(inspected.value.inspections), 1)
        return inspected.value.inspections[0]

    def _project_files(self) -> dict[str, bytes]:
        return {
            str(path): path.read_bytes()
            for path in pathlib.Path(self.project_root).rglob("*")
            if path.is_file()
        }

    def _edit(self, harnesses: tuple[str, ...], value: str):
        before = self._inspection()
        files_before = self._project_files()
        prepared = prepare_configured_configuration(
            before,
            input_id=ORG,
            harnesses=harnesses,
            value=value,
            policy=EffectivePolicy(),
        )
        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
        assert isinstance(prepared, Ok)
        self.assertEqual(
            {step.component.name for step in prepared.value.plan.repair.steps}, set(harnesses)
        )
        completed = complete_configured_configuration(
            prepared.value,
            expected_review_digest=prepared.value.review_digest,
            host=self.host,
            policy=EffectivePolicy(),
            credential_providers=(self.provider,),
            recorded_at=EDITED_AT,
            today=TODAY,
            offline=True,
        )
        self.assertIsInstance(completed, Ok, getattr(completed, "diagnostics", ()))
        assert isinstance(completed, Ok)
        self.assertIs(completed.value.outcome.status, LifecycleExecutionStatus.COMPLETED)

        after = self._inspection()
        old_records = {item.harness: item for item in before.record.receipt.configuration_files}
        new_records = {item.harness: item for item in after.record.receipt.configuration_files}
        for harness in HARNESSES:
            if harness in harnesses:
                self.assertNotEqual(old_records[harness].digest, new_records[harness].digest)
            else:
                self.assertEqual(old_records[harness], new_records[harness])

        files_after = self._project_files()
        changed = {
            path
            for path in files_before.keys() | files_after.keys()
            if files_before.get(path) != files_after.get(path)
        }
        self.assertEqual(changed, {new_records[item].path for item in harnesses})

        receipt = after.record.receipt
        registrations = {item.target.harness: item for item in receipt.registrations}
        for harness in HARNESSES:
            registration = registrations[harness]
            replies = speak(
                [registration.command, *registration.arguments],
                [{"jsonrpc": "2.0", "id": 1, "method": "tools/call"}],
            )
            facts = json.loads(replies[0]["result"]["content"][0]["text"])
            self.assertEqual(facts["org"], value if harness in harnesses else "original-team")

        durable = repr(completed.value.machine.activity) + repr(completed.value.machine.receipts)
        state_root = pathlib.Path(self.host.state_root)
        for path in state_root.rglob("*"):
            if path.is_file():
                durable += path.read_text(encoding="utf-8", errors="replace")
        self.assertNotIn(value, durable)
        return prepared.value, completed.value

    def test_edit_one_harness(self) -> None:
        self._edit(("opencode",), "one-team")

    def test_edit_a_chosen_set(self) -> None:
        self._edit(("claude", "tabnine"), "several-team")

    def test_edit_all_harnesses(self) -> None:
        self._edit(HARNESSES, "all-team")

    def test_empty_and_stale_harness_choices_are_refused_before_planning(self) -> None:
        inspection = self._inspection()

        for harnesses in ((), ("removed",)):
            with self.subTest(harnesses=harnesses):
                prepared = prepare_configured_configuration(
                    inspection,
                    input_id=ORG,
                    harnesses=harnesses,
                    value="reviewed-team",
                    policy=EffectivePolicy(),
                )

                self.assertIsInstance(prepared, Err)
                self.assertIn("harness", prepared.diagnostics[0].message)

    def test_unrelated_drift_is_refused_so_an_edit_cannot_carry_a_repair(self) -> None:
        """INV-179: a configuration edit touches its files and nothing else, even something broken."""

        receipt = self._inspection().record.receipt
        launcher = pathlib.Path(receipt.launcher)
        launcher.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        files_before = self._project_files()

        prepared = prepare_configured_configuration(
            self._inspection(),
            input_id=ORG,
            harnesses=("claude",),
            value="reviewed-team",
            policy=EffectivePolicy(),
        )

        self.assertIsInstance(prepared, Err)
        assert isinstance(prepared, Err)
        self.assertIn("verify or repair it", prepared.diagnostics[0].message)
        self.assertEqual(self._project_files(), files_before)

    def test_a_chosen_file_changed_after_review_is_refused(self) -> None:
        inspection = self._inspection()
        prepared = prepare_configured_configuration(
            inspection,
            input_id=ORG,
            harnesses=("claude",),
            value="reviewed-team",
            policy=EffectivePolicy(),
        )
        self.assertIsInstance(prepared, Ok)
        assert isinstance(prepared, Ok)
        record = next(
            item
            for item in inspection.record.receipt.configuration_files
            if item.harness == "claude"
        )
        pathlib.Path(record.path).write_text("changed outside AART\n", encoding="utf-8")

        completed = complete_configured_configuration(
            prepared.value,
            expected_review_digest=prepared.value.review_digest,
            host=self.host,
            policy=EffectivePolicy(),
            credential_providers=(self.provider,),
            recorded_at=EDITED_AT,
            today=TODAY,
        )

        self.assertIsInstance(completed, Err)
        self.assertIn("changed outside AART since Review", completed.diagnostics[0].message)
        self.assertEqual(pathlib.Path(record.path).read_text(), "changed outside AART\n")

    def test_real_handler_applies_the_approved_validation_without_retaining_the_value(self) -> None:
        machine = read_consumer_machine(
            state_root=self.host.state_root,
            harness_root=self.host.harness_root,
            today=TODAY,
            project_root=self.host.project_root,
            user_home=self.host.user_home,
            data_root=self.host.data_root,
            credential_providers=(self.provider,),
        )
        self.assertIsInstance(machine, Ok)
        assert isinstance(machine, Ok)
        handler = LocalConsumerActions(
            ConsumerActionContext(
                self.host,
                self.effective,
                machine.value,
                policy=EffectivePolicy(),
                credential_providers=(self.provider,),
            )
        )
        candidate = "not/the-approved-shape"

        update = handler.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.CONFIGURE,
                focus=str(self._inspection().coordinate),
                targets=("claude",),
                config_answers=((ORG.value, candidate),),
            )
        )

        self.assertIs(update.event.kind, ConsumerUiEventKind.ACTION_PREPARED)
        self.assertFalse(update.event.review_digest)
        self.assertIn("declared pattern rule", "\n".join(update.source.screens.notice))
        self.assertNotIn(candidate, repr(update))

    def test_credential_set_uses_the_installed_authored_briefing_then_verifies(self) -> None:
        token_path = pathlib.Path(self.provider.path)
        token_path.unlink()
        calls = []

        class Provider(_FileCredentials):
            def store(provider_self, reference, secret=None, *, replace=False):
                calls.append((secret, replace))
                pathlib.Path(provider_self.path).write_text("provider-held", encoding="utf-8")
                return provider_self.inspect(reference)

        briefings = []

        def handover(briefing=()):
            briefings.append(tuple(briefing))
            return contextlib.nullcontext()

        provider = Provider(str(token_path))
        machine = read_consumer_machine(
            state_root=self.host.state_root,
            harness_root=self.host.harness_root,
            today=TODAY,
            project_root=self.host.project_root,
            user_home=self.host.user_home,
            data_root=self.host.data_root,
            credential_providers=(provider,),
        )
        self.assertIsInstance(machine, Ok)
        assert isinstance(machine, Ok)
        handler = LocalConsumerActions(
            ConsumerActionContext(
                self.host,
                self.effective,
                machine.value,
                policy=EffectivePolicy(),
                credential_providers=(provider,),
            ),
            terminal_handover=handover,
        )
        receipt_value = self._inspection().record.receipt
        focus = str(receipt_value.credentials[0])
        prepared = handler.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.CREDENTIAL_SET,
                focus=focus,
            )
        )
        self.assertTrue(prepared.event.review_digest, prepared.source.screens.notice)

        done = handler.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.EXECUTE_ACTION,
                action=ConsumerActionKind.CREDENTIAL_SET,
                focus=focus,
                review_digest=prepared.event.review_digest,
            )
        )

        self.assertIs(done.event.kind, ConsumerUiEventKind.ACTION_RECORDED)
        self.assertEqual(calls, [(None, False)])
        (briefing,) = briefings
        self.assertIn("GitHub token", "\n".join(briefing))
        self.assertIn(str(self._inspection().coordinate), "\n".join(briefing))

    def test_screen_22a_runs_one_reviewed_edit_through_the_real_handler(self) -> None:
        machine = read_consumer_machine(
            state_root=self.host.state_root,
            harness_root=self.host.harness_root,
            today=TODAY,
            project_root=self.host.project_root,
            user_home=self.host.user_home,
            data_root=self.host.data_root,
            credential_providers=(self.provider,),
        )
        self.assertIsInstance(machine, Ok)
        assert isinstance(machine, Ok)
        handler = LocalConsumerActions(
            ConsumerActionContext(
                self.host,
                self.effective,
                machine.value,
                policy=EffectivePolicy(),
                credential_providers=(self.provider,),
                offline=True,
            ),
            now=lambda: __import__("datetime").datetime.fromisoformat(EDITED_AT),
        )
        coordinate = self._inspection().coordinate
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.USER_INPUT_DETAILS),
            focus=coordinate,
            user_inputs_artifact=coordinate,
        )
        value = "shell-team"
        terminal = FakeTerminal(
            ENTER,
            DOWN,
            SPACE,
            DOWN,
            SPACE,
            ENTER,
            # 22c opens holding the value the chosen harness has now; it is cleared, then replaced.
            *(BACKSPACE for _ in "original-team"),
            *(ord(character) for character in value),
            ENTER,
            ENTER,
            ENTER,
        )

        finished = run_consumer_shell(
            handler.source(), state=state, terminal=terminal, action_handler=handler
        )

        self.assertTrue(finished.exited)
        self.assertIs(finished.session.screen, ConsumerScreen.USER_INPUT_DETAILS)
        self.assertTrue(
            terminal.screen_containing(f"claude: original-team → {value}"),
            "\n---\n".join("\n".join(item) for item in terminal.frames),
        )
        self.assertTrue(terminal.screen_containing(f"> {ORG} [original-team]"))
        after = self._inspection().record.receipt.configuration_files
        values = {
            item.harness: pathlib.Path(item.path).read_text(encoding="utf-8") for item in after
        }
        self.assertIn(f"{ORG}={value}\n", values["claude"])
        self.assertIn(f"{ORG}=original-team\n", values["opencode"])
        self.assertIn(f"{ORG}=original-team\n", values["tabnine"])


if __name__ == "__main__":
    unittest.main()
