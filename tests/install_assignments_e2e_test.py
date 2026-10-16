"""§172.2 and §172.5: each artifact goes into its own pairs, and one transaction may span scopes.

The ConfiguredInstallationActionTest fixture is reused: one approved `mcp/github` with an ordinary
input and a secret, published from a configured Registry. Here it is installed into claude at
project scope and opencode at user scope, in one prepared action and one completed transaction.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from aart_cli.application.execution import InstallationExecutionStatus
from aart_cli.application.installation_inputs import OwnedInputSource
from aart_cli.domain.harness import Scope, mcp_target
from aart_cli.domain.identifiers import ArtifactCoordinate, ArtifactIdentity
from aart_cli.domain.inputs import PromptedConfigValue, SecretProviderReference
from aart_cli.domain.installation_owner import installation_owner
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Err, Ok
from aart_cli.io.configured_installation import InstallationAssignment
from aart_cli.io.configured_installation_action import (
    complete_configured_installation,
    prepare_configured_installation,
)
from tests import configured_installation_action_e2e_test as fixture
from tests.artifact_installation_e2e_test import MOMENT, ORG, TOKEN
from tests.configured_installation_action_e2e_test import REFERENCE, TODAY

KEY = "company/mcp/github@1.5.0"


class EachPairIsOneInstallationTest(unittest.TestCase):
    setUp = fixture.ConfiguredInstallationActionTest.setUp

    def _owner(self, harness: str, scope: Scope):
        return installation_owner(
            ArtifactCoordinate(self.source.alias, ArtifactIdentity("mcp", "github"), "1.5.0"),
            scope=scope,
            root=self.project_root if scope is Scope.PROJECT else self.user_home,
            harness=harness,
        )

    def _prepare(self, assignments, pairs):
        return prepare_configured_installation(
            self.effective,
            self.selection,
            host=self.host,
            sources=tuple(
                OwnedInputSource(self._owner(harness, scope), source)
                for harness, scope in pairs
                for source in (
                    PromptedConfigValue(ORG, "acme"),
                    SecretProviderReference(TOKEN, REFERENCE),
                )
            ),
            policy=EffectivePolicy(),
            selected_remediations=None,
            credential_providers=(self.provider,),
            resolvers=(self.provider,),
            assignments=assignments,
        )

    def test_one_transaction_writes_each_scope_under_its_own_root(self) -> None:
        pairs = (("claude", Scope.PROJECT), ("opencode", Scope.USER))
        prepared = self._prepare(
            tuple(InstallationAssignment(KEY, harness, scope) for harness, scope in pairs), pairs
        )
        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
        self.assertEqual(
            {(owner.harness, owner.scope) for owner in prepared.value.draft.owners}, set(pairs)
        )

        completed = complete_configured_installation(
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

        self.assertIsInstance(completed, Ok, getattr(completed, "diagnostics", ()))
        self.assertIs(
            completed.value.action.execution.status, InstallationExecutionStatus.COMPLETED
        )
        for harness, scope, root in (
            ("claude", Scope.PROJECT, self.project_root),
            ("opencode", Scope.USER, self.user_home),
        ):
            target = mcp_target(harness, scope)
            settings = pathlib.Path(root) / target.settings_file
            self.assertTrue(settings.is_file(), f"{harness} was not registered under its root")
            servers = json.loads(settings.read_text(encoding="utf-8"))[target.server_map]
            self.assertEqual(set(servers), {f"github-company-{scope.value}"})
        # Nothing of the user-scope installation lands in the project, or the other way round.
        self.assertFalse((pathlib.Path(self.project_root) / "opencode.json").exists())
        self.assertFalse((pathlib.Path(self.user_home) / ".mcp.json").exists())
        # The machine read afterwards measures each installation against its own root.
        installed = completed.value.machine.installed
        self.assertEqual(
            sorted((view.harness, view.scope, view.health, view.drift) for view in installed),
            [("claude", "project", "ready", ()), ("opencode", "user", "ready", ())],
        )

    def test_an_artifact_left_without_a_pair_is_refused_by_name(self) -> None:
        prepared = prepare_configured_installation(
            self.effective,
            self.selection,
            host=self.host,
            sources=(),
            policy=EffectivePolicy(),
            selected_remediations=None,
            assignments=(InstallationAssignment("company/mcp/other@1.0.0", "claude", Scope.USER),),
        )

        self.assertIsInstance(prepared, Err)
        self.assertIn("company/mcp/other@1.0.0", prepared.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
