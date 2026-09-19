"""Safe screen-07 composition before an installation can become an offer.

§169.4-6 and D-353: the unit of collection is the installation, not the declared input. Two
harnesses are two installations, so they are two fields, and answering one does not answer the
other.
"""

from __future__ import annotations

import unittest

from aart_cli.application.consumer_views import ConfigInputView, CredentialInputView
from aart_cli.application.installation_inputs import (
    InstallationInputUse,
    OwnedInputSource,
    compose_installation_inputs,
)
from aart_cli.domain.credentials import CredentialProviderRef
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    SourceAlias,
)
from aart_cli.domain.inputs import (
    ConfigInput,
    EnvironmentBinding,
    InputGuidance,
    PersistedConfigValue,
    PromptedConfigValue,
    SecretInput,
    SecretProviderReference,
)
from aart_cli.domain.installation_owner import InstallationOwner, installation_owner
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Err, Ok

ORG = InputId("org")
TOKEN = InputId("token")
KEYCHAIN = CredentialProviderRef("macos-keychain", "aart-cli.claude.-.project", "token")
OTHER_KEYCHAIN = CredentialProviderRef("macos-keychain", "aart-cli.opencode.-.project", "token")


def _coordinate(name: str) -> ArtifactCoordinate:
    return ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", name), "1.0.0")


def _owner(name: str = "github", *, harness: str = "claude") -> InstallationOwner:
    return installation_owner(
        _coordinate(name),
        scope=Scope.PROJECT,
        root="/work/project",
        harness=harness,
    )


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
    def test_one_artifact_on_two_harnesses_is_two_fields_per_input(self) -> None:
        """The acceptance in one test: separate targets collect separately (§169.6, D-333)."""

        claude = _owner(harness="claude")
        opencode = _owner(harness="opencode")
        uses = tuple(
            InstallationInputUse(owner, declared)
            for owner in (claude, opencode)
            for declared in (_config(), _secret())
        )

        composed = compose_installation_inputs(
            uses,
            (
                OwnedInputSource(claude, PersistedConfigValue(ORG, "platform-team")),
                OwnedInputSource(claude, SecretProviderReference(TOKEN, KEYCHAIN)),
                OwnedInputSource(opencode, PersistedConfigValue(ORG, "other-team")),
                OwnedInputSource(opencode, SecretProviderReference(TOKEN, OTHER_KEYCHAIN)),
            ),
            EffectivePolicy(),
        )

        self.assertIsInstance(composed, Ok, getattr(composed, "diagnostics", ()))
        assert isinstance(composed, Ok)
        self.assertTrue(composed.value.ready)
        self.assertEqual(4, len(composed.value.fields))
        self.assertEqual(
            {(claude, ORG), (claude, TOKEN), (opencode, ORG), (opencode, TOKEN)},
            {(field.owner, field.input.id) for field in composed.value.fields},
        )
        self.assertNotEqual(
            composed.value.sources_for(claude), composed.value.sources_for(opencode)
        )

    def test_answering_one_target_leaves_the_other_unanswered(self) -> None:
        """No copy-answers and no cross-target prefill: the other target is still a question."""

        claude = _owner(harness="claude")
        opencode = _owner(harness="opencode")
        uses = tuple(InstallationInputUse(owner, _config()) for owner in (claude, opencode))

        composed = compose_installation_inputs(
            uses,
            (OwnedInputSource(claude, PromptedConfigValue(ORG, "platform-team")),),
            EffectivePolicy(),
        )

        assert isinstance(composed, Ok), composed
        self.assertFalse(composed.value.ready)
        self.assertEqual(
            ((opencode, ORG),),
            tuple((item.owner, item.input.id) for item in composed.value.unanswered),
        )
        self.assertEqual(
            (PromptedConfigValue(ORG, "platform-team"),), composed.value.sources_for(claude)
        )
        self.assertEqual((), composed.value.sources_for(opencode))

    def test_two_artifacts_are_two_owners_even_on_one_harness(self) -> None:
        github = _owner("github")
        issues = _owner("issues")
        composed = compose_installation_inputs(
            tuple(InstallationInputUse(owner, _secret()) for owner in (github, issues)),
            (
                OwnedInputSource(github, SecretProviderReference(TOKEN, KEYCHAIN)),
                OwnedInputSource(issues, SecretProviderReference(TOKEN, OTHER_KEYCHAIN)),
            ),
            EffectivePolicy(),
        )

        assert isinstance(composed, Ok), composed
        self.assertEqual(2, len(composed.value.fields))
        self.assertEqual(
            (SecretProviderReference(TOKEN, KEYCHAIN),), composed.value.sources_for(github)
        )

    def test_the_same_id_declared_differently_is_no_longer_a_conflict(self) -> None:
        """It was a conflict only because the id was the key; two owners are simply two fields."""

        github = _owner("github")
        issues = _owner("issues")
        composed = compose_installation_inputs(
            (
                InstallationInputUse(github, _config()),
                InstallationInputUse(issues, ConfigInput(ORG, EnvironmentBinding("OTHER_ORG"))),
            ),
            (),
            EffectivePolicy(),
        )

        assert isinstance(composed, Ok), composed
        self.assertEqual(2, len(composed.value.fields))
        self.assertEqual(
            {"GITHUB_ORG", "OTHER_ORG"},
            {field.input.binding.variable for field in composed.value.fields},
        )

    def test_a_declared_default_is_prefilled_but_not_silently_accepted(self) -> None:
        owner = _owner()
        pending = compose_installation_inputs(
            (InstallationInputUse(owner, _config(default="acme")),),
            (),
            EffectivePolicy(),
        )

        assert isinstance(pending, Ok), pending
        self.assertFalse(pending.value.ready)
        self.assertEqual(tuple(item.input.id for item in pending.value.unanswered), (ORG,))
        view = pending.value.views()[0]
        self.assertIsInstance(view, ConfigInputView)
        assert isinstance(view, ConfigInputView)
        self.assertEqual(view.default, "acme")
        self.assertIsNone(view.current)

        accepted = compose_installation_inputs(
            pending.value.uses,
            (OwnedInputSource(owner, PromptedConfigValue(ORG, "acme")),),
            EffectivePolicy(),
        )

        assert isinstance(accepted, Ok), accepted
        self.assertTrue(accepted.value.ready)
        self.assertEqual(accepted.value.sources_for(owner), (PromptedConfigValue(ORG, "acme"),))

    def test_a_secret_cannot_cross_the_form_as_ordinary_config(self) -> None:
        owner = _owner()
        refused = compose_installation_inputs(
            (InstallationInputUse(owner, _secret()),),
            (OwnedInputSource(owner, PromptedConfigValue(TOKEN, "ordinary-config")),),
            EffectivePolicy(),
        )

        assert isinstance(refused, Err), refused
        self.assertEqual(refused.diagnostics[0].code.value, "input-binding-invalid")

    def test_an_answer_for_an_installation_this_composition_lacks_is_dropped(self) -> None:
        """Narrowing the chosen harnesses re-composes with fewer owners; their answers survive it.

        Refusing here would make the harness-choice screen impossible: it composes the same
        selection again with the harnesses somebody ticked, and the answers already given for the
        ones they did not tick have nothing left to attach to.
        """

        github = _owner("github")
        composed = compose_installation_inputs(
            (InstallationInputUse(github, _config()),),
            (
                OwnedInputSource(github, PromptedConfigValue(ORG, "acme")),
                OwnedInputSource(_owner("issues"), PromptedConfigValue(ORG, "stale")),
                OwnedInputSource(github, PromptedConfigValue(TOKEN, "never-declared")),
            ),
            EffectivePolicy(),
        )

        assert isinstance(composed, Ok), composed
        self.assertTrue(composed.value.ready)
        self.assertEqual((PromptedConfigValue(ORG, "acme"),), composed.value.sources_for(github))


class InstallationInputGuardTest(unittest.TestCase):
    """Each argument is refused on its own, so one bad one cannot be hidden by a good other."""

    def test_uses_sources_and_policy_are_each_refused_alone(self) -> None:
        owner = _owner()
        good_use = InstallationInputUse(owner, _config())
        good_source = OwnedInputSource(owner, PromptedConfigValue(ORG, "acme"))
        for label, uses, sources, policy in (
            ("uses", (good_use, "not a use"), (good_source,), EffectivePolicy()),
            ("sources", (good_use,), (good_source, "not a source"), EffectivePolicy()),
            ("policy", (good_use,), (good_source,), "not a policy"),
        ):
            with self.subTest(argument=label):
                refused = compose_installation_inputs(uses, sources, policy)  # type: ignore[arg-type]
                self.assertIsInstance(refused, Err, refused)
                self.assertEqual(
                    refused.diagnostics[0].code.value,
                    "installation-input-composition-invalid",
                )


class InstallationInputViewTest(unittest.TestCase):
    """Two rows may now legitimately share an input id, so the row key names the owner."""

    def test_each_owner_gets_its_own_row_with_its_own_key(self) -> None:
        claude = _owner(harness="claude")
        opencode = _owner(harness="opencode")
        composed = compose_installation_inputs(
            tuple(InstallationInputUse(owner, _secret()) for owner in (claude, opencode)),
            (OwnedInputSource(claude, SecretProviderReference(TOKEN, KEYCHAIN)),),
            EffectivePolicy(),
        )

        assert isinstance(composed, Ok), composed
        views = composed.value.views()

        self.assertEqual(2, len(views))
        self.assertEqual({view.id for view in views}, {TOKEN.value})
        self.assertEqual(len({view.row for view in views}), 2)
        answered = next(view for view in views if view.owner == str(claude))
        self.assertIsInstance(answered, CredentialInputView)
        assert isinstance(answered, CredentialInputView)
        self.assertEqual(answered.provider_reference, f"{TOKEN}@{KEYCHAIN}")
        self.assertFalse(hasattr(answered, "value"))
        unanswered = next(view for view in views if view.owner == str(opencode))
        assert isinstance(unanswered, CredentialInputView)
        self.assertIsNone(unanswered.provider_reference)


if __name__ == "__main__":
    unittest.main()
