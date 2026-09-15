"""Safe screen-07 composition before an installation can become an offer."""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_views import ConfigInputView, CredentialInputView
from agent_artifacts.application.installation_inputs import (
    INPUT_DECLARATION_CONFLICT,
    InstallationInputUse,
    compose_installation_inputs,
)
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    SourceAlias,
)
from agent_artifacts.domain.inputs import (
    ConfigInput,
    EnvironmentBinding,
    InputGuidance,
    PersistedConfigValue,
    PromptedConfigValue,
    SecretInput,
    SecretProviderReference,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok

ORG = InputId("org")
TOKEN = InputId("token")
KEYCHAIN = CredentialProviderRef("macos-keychain", "aart/mcp/github", "default")


def _coordinate(name: str) -> ArtifactCoordinate:
    return ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", name), "1.0.0")


def _config(*, default: str | None = None) -> ConfigInput:
    return ConfigInput(
        ORG,
        EnvironmentBinding("GITHUB_ORG"),
        guidance=InputGuidance("GitHub organization", example="platform-team"),
        default=default,
    )


def _secret() -> SecretInput:
    return SecretInput(
        TOKEN,
        EnvironmentBinding("GITHUB_TOKEN"),
        guidance=InputGuidance("GitHub token", format_hint="opaque token"),
    )


class InstallationInputsTest(unittest.TestCase):
    def test_equivalent_inputs_are_one_field_with_every_dependant(self) -> None:
        github = _coordinate("github")
        issues = _coordinate("issues")
        uses = tuple(
            InstallationInputUse(owner, declared)
            for owner in (github, issues)
            for declared in (_config(), _secret())
        )

        composed = compose_installation_inputs(
            uses,
            (
                PersistedConfigValue(ORG, "platform-team"),
                SecretProviderReference(TOKEN, KEYCHAIN),
            ),
            EffectivePolicy(),
        )

        self.assertIsInstance(composed, Ok, getattr(composed, "diagnostics", ()))
        assert isinstance(composed, Ok)
        self.assertTrue(composed.value.ready)
        self.assertEqual(len(composed.value.fields), 2)
        self.assertTrue(
            all(field.dependants == (github, issues) for field in composed.value.fields)
        )
        self.assertEqual(composed.value.sources_for(github), composed.value.sources_for(issues))
        token = next(view for view in composed.value.views() if view.id == TOKEN.value)
        self.assertIsInstance(token, CredentialInputView)
        assert isinstance(token, CredentialInputView)
        self.assertEqual(token.provider_reference, f"{TOKEN}@{KEYCHAIN}")
        self.assertFalse(hasattr(token, "value"))

    def test_a_declared_default_is_prefilled_but_not_silently_accepted(self) -> None:
        owner = _coordinate("github")
        pending = compose_installation_inputs(
            (InstallationInputUse(owner, _config(default="acme")),),
            (),
            EffectivePolicy(),
        )

        self.assertIsInstance(pending, Ok)
        assert isinstance(pending, Ok)
        self.assertFalse(pending.value.ready)
        self.assertEqual(tuple(item.input.id for item in pending.value.unanswered), (ORG,))
        view = pending.value.views()[0]
        self.assertIsInstance(view, ConfigInputView)
        assert isinstance(view, ConfigInputView)
        self.assertEqual(view.default, "acme")
        self.assertIsNone(view.current)

        accepted = compose_installation_inputs(
            pending.value.uses,
            (PromptedConfigValue(ORG, "acme"),),
            EffectivePolicy(),
        )

        self.assertIsInstance(accepted, Ok)
        assert isinstance(accepted, Ok)
        self.assertTrue(accepted.value.ready)
        self.assertEqual(accepted.value.sources_for(owner), (PromptedConfigValue(ORG, "acme"),))

    def test_the_same_id_with_different_semantics_refuses_instead_of_picking_one(self) -> None:
        github = _coordinate("github")
        issues = _coordinate("issues")
        conflict = compose_installation_inputs(
            (
                InstallationInputUse(github, _config()),
                InstallationInputUse(
                    issues,
                    ConfigInput(ORG, EnvironmentBinding("OTHER_ORG")),
                ),
            ),
            (),
            EffectivePolicy(),
        )

        self.assertIsInstance(conflict, Err)
        assert isinstance(conflict, Err)
        self.assertIs(conflict.diagnostics[0].code, INPUT_DECLARATION_CONFLICT)
        self.assertIn(str(github), conflict.diagnostics[0].message)
        self.assertIn(str(issues), conflict.diagnostics[0].message)

    def test_a_secret_cannot_cross_the_form_as_ordinary_config(self) -> None:
        refused = compose_installation_inputs(
            (InstallationInputUse(_coordinate("github"), _secret()),),
            (PromptedConfigValue(TOKEN, "ordinary-config"),),
            EffectivePolicy(),
        )

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertEqual(refused.diagnostics[0].code.value, "input-binding-invalid")


if __name__ == "__main__":
    unittest.main()
