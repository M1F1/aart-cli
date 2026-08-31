"""One configured approved artifact, installed through the single adapter a caller reaches.

The shell and the public commands are two adapters over one application action (D-074), but until
now each of them would still have had to compose that action's ports by hand: resolve the Selection
out of configured source state, materialize and place the verified object, bind the accepted
screen-07 sources, build the interpreters, take the lease, record, and then re-read the machine.
Two copies of that wiring disagree the first time one changes, and the disagreement is invisible --
both of them install something.

So this proves the composed adapter end to end against durable state: preparation reaches a
reviewable action without touching the machine, completion installs and records exactly the review
that was confirmed, and the machine it hands back was read from disk rather than assembled from
what the install believed it did.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import tempfile
import unittest
from datetime import date

from agent_artifacts.application.execution import InstallationExecutionStatus
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.identifiers import ArtifactIdentity, SourceId
from agent_artifacts.domain.inputs import PromptedConfigValue, SecretProviderReference
from agent_artifacts.domain.placement import artifact_root
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    VersionConstraint,
)
from agent_artifacts.io.configured_installation_action import (
    InstallationHost,
    complete_configured_installation,
    prepare_configured_installation,
)
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.artifact_installation_e2e_test import MOMENT, ORG, TOKEN
from tests.configured_installation_draft_e2e_test import _published_registry
from tests.marketplace_fixtures import configured_source, effective_configuration

TODAY = date(2026, 8, 31)
REFERENCE = CredentialProviderRef("test-file", "aart-e2e", "github-token")


class _FileCredentials:
    """One file standing in for a keychain, so this runs the real path on every platform."""

    provider = "test-file"

    def __init__(self, path: str) -> None:
        self.path = path

    def resolution_argv(self, reference) -> tuple[str, ...]:
        return ("/bin/cat", self.path)

    def available(self) -> ProviderState:
        return ProviderState.AVAILABLE

    def inspect(self, reference) -> Ok:
        return Ok(
            CredentialObservation(
                reference,
                ProviderState.AVAILABLE,
                CredentialState.PRESENT if os.path.exists(self.path) else CredentialState.ABSENT,
                "measured from the file that holds it",
            )
        )

    def store(self, reference, secret=None, *, replace: bool = False) -> Ok:
        return self.inspect(reference)

    def delete(self, reference) -> Ok:
        return self.inspect(reference)


class ConfiguredInstallationActionTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        self.data_root = str(self.root / "data")
        self.project_root = str(self.root / "project")
        self.user_home = str(self.root / "home")
        for path in (self.project_root, self.user_home):
            pathlib.Path(path).mkdir(parents=True)

        self.token = secrets.token_hex(32)
        token_file = self.root / "token"
        token_file.write_text(self.token, encoding="utf-8")
        self.provider = _FileCredentials(str(token_file))

        self.source = configured_source("company", SourceKind.REGISTRY_GIT)
        self.effective = effective_configuration((self.source,), default_registry="company")
        candidate = make_source_candidate(
            source_instance_id(self.source), self.source.alias, "a" * 40, _published_registry()
        )
        assert isinstance(candidate, Ok), candidate
        written = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(self.source)),
                ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
                90,
            )
        )
        self.assertIsInstance(written, Ok, getattr(written, "diagnostics", ()))

        self.selection = ArtifactSelection(
            (
                ArtifactRequest(
                    ArtifactIdentity("mcp", "github"),
                    VersionConstraint("*"),
                    self.source.alias,
                ),
            )
        )
        self.host = InstallationHost(
            data_root=self.data_root,
            project_root=self.project_root,
            user_home=self.user_home,
            scope=Scope.PROJECT,
            profiles=("tabnine",),
        )

    def _answers(self):
        return (PromptedConfigValue(ORG, "acme"), SecretProviderReference(TOKEN, REFERENCE))

    def _prepare(self, sources=None):
        return prepare_configured_installation(
            self.effective,
            self.selection,
            host=self.host,
            sources=self._answers() if sources is None else sources,
            policy=EffectivePolicy(),
            selected_remediations=None,
            credential_providers=(self.provider,),
            resolvers=(self.provider,),
        )

    def _complete(self, prepared):
        return complete_configured_installation(
            prepared,
            expected_review_digest=prepared.review_digest,
            host=self.host,
            policy=EffectivePolicy(),
            credential_providers=(self.provider,),
            recorded_at=MOMENT,
            today=TODAY,
            timeout_seconds=300.0,
            offline=True,
        )

    def _installed_root(self, prepared) -> str:
        return artifact_root(
            prepared.action.installations[0].coordinate,
            Scope.PROJECT,
            project_root=self.project_root,
            data_root=self.data_root,
        )

    def test_unanswered_inputs_stop_at_the_form_rather_than_at_a_refusal(self) -> None:
        """Screen 07 exists because the answer is "not yet", not "no"."""

        prepared = self._prepare(sources=())

        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
        self.assertFalse(prepared.value.ready)
        self.assertIsNone(prepared.value.action)
        self.assertEqual(
            tuple(field.input.id for field in prepared.value.draft.inputs.unanswered), (ORG, TOKEN)
        )

    def test_preparing_reaches_a_reviewable_action_without_touching_the_machine(self) -> None:
        prepared = self._prepare()

        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
        self.assertTrue(prepared.value.ready)
        self.assertIsNotNone(prepared.value.review_digest)
        self.assertFalse(
            pathlib.Path(self._installed_root(prepared.value)).exists(),
            "planning must not have created the tree it plans to write",
        )
        self.assertFalse(
            (pathlib.Path(self.project_root) / ".tabnine/agent/settings.json").exists(),
            "planning must not have registered anything with a harness",
        )

    def test_completing_installs_records_and_hands_back_a_machine_read_from_disk(self) -> None:
        prepared = self._prepare()
        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))

        completed = self._complete(prepared.value)

        self.assertIsInstance(completed, Ok, getattr(completed, "diagnostics", ()))
        self.assertIs(
            completed.value.action.execution.status, InstallationExecutionStatus.COMPLETED
        )
        self.assertEqual(
            completed.value.action.recorded.receipt.review_digest,
            str(prepared.value.review_digest),
        )
        coordinate = str(prepared.value.action.installations[0].coordinate)
        self.assertIn(coordinate, [view.coordinate for view in completed.value.machine.installed])
        settings = pathlib.Path(self.project_root) / ".tabnine/agent/settings.json"
        self.assertTrue(settings.exists(), "the harness the profile named was never registered")
        entry = json.loads(settings.read_text(encoding="utf-8"))["mcpServers"]["github"]

        # The install is only real if what it registered is on disk and runnable. A status of
        # COMPLETED is the executor's verdict; this is the machine's.
        launcher = pathlib.Path(entry["command"])
        self.assertTrue(launcher.exists(), "the harness was pointed at a launcher nobody wrote")
        self.assertTrue(os.access(launcher, os.X_OK), "the launcher was written non-executable")
        self.assertTrue(
            str(launcher).startswith(self._installed_root(prepared.value)),
            "the harness was pointed outside the tree this artifact owns",
        )
        self.assertTrue(
            pathlib.Path(prepared.value.action.installations[0].environment.interpreter).exists(),
            "the artifact-owned interpreter the launcher runs was never created",
        )

    def test_the_secret_reaches_no_surface_the_adapter_produces(self) -> None:
        prepared = self._prepare()
        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
        completed = self._complete(prepared.value)
        self.assertIsInstance(completed, Ok, getattr(completed, "diagnostics", ()))

        surfaces = repr(completed.value) + repr(prepared.value)
        surfaces += repr(completed.value.machine) + repr(completed.value.action.recorded)
        # Both roots: the receipts and the object store live under one, and the artifact's own
        # tree -- launcher included -- lives under the other. A scan of either alone would pass
        # while the value sat in the file the harness actually starts.
        for root in (self.data_root, self.project_root):
            for path in pathlib.Path(root).rglob("*"):
                if path.is_file():
                    surfaces += path.read_text(encoding="utf-8", errors="replace")

        self.assertIn(self.token, pathlib.Path(self.provider.path).read_text(encoding="utf-8"))
        self.assertNotIn(self.token, surfaces)

    def test_a_review_the_caller_did_not_confirm_is_refused_before_the_lease(self) -> None:
        prepared = self._prepare()
        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
        other = prepared.value.action.installations[0].launcher.digest

        refused = complete_configured_installation(
            prepared.value,
            expected_review_digest=other,
            host=self.host,
            policy=EffectivePolicy(),
            credential_providers=(self.provider,),
            recorded_at=MOMENT,
            today=TODAY,
        )

        self.assertIsInstance(refused, Err, refused)
        self.assertFalse(pathlib.Path(self._installed_root(prepared.value)).exists())

    def test_completing_a_form_that_is_not_ready_is_refused(self) -> None:
        prepared = self._prepare(sources=())
        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))

        refused = complete_configured_installation(
            prepared.value,
            expected_review_digest=None,
            host=self.host,
            policy=EffectivePolicy(),
            recorded_at=MOMENT,
            today=TODAY,
        )

        self.assertIsInstance(refused, Err, refused)


if __name__ == "__main__":
    unittest.main()
