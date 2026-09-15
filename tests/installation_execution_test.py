"""Assembling the interpreters one confirmed Selection is carried out through.

`execute_installation` is handed one tuple of interpreters for the whole transaction, and every
member's effects run through it. Deciding what goes in that tuple was the last piece of the install
composition that only existed hand-wired in a test, so a command and the shell's action handler
would each have had to build it -- and two copies of it disagree the first time one changes.

The rule the assembly follows is the one the interpreters already enforce: each is bound to what it
is allowed to touch. One file interpreter per artifact, holding that artifact's launcher content;
one runtime interpreter per artifact, bound to its environment; one harness interpreter per
artifact, holding its registrations and its name; and one credential interpreter per provider,
holding the references that name it. Nothing here reads a secret value.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from agent_artifacts.application.installation_proposal import intended_receipt
from agent_artifacts.domain.credentials import CredentialProviderRef
from agent_artifacts.domain.effects import ConfigureHarness, WriteFile
from agent_artifacts.domain.inputs import (
    ConfigInput,
    EnvironmentBinding,
    PersistedConfigValue,
    SecretProviderReference,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.execution import (
    CredentialEffectInterpreter,
    FileEffectInterpreter,
    HarnessEffectInterpreter,
    RuntimeEffectInterpreter,
)
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.installation_execution import (
    INTERPRETERS_UNAVAILABLE,
    interpreters_for,
)
from tests.artifact_installation_test import ORG, TOKEN, _description, _plan
from tests.installation_proposal_test import _resolved

SECOND_ROOT = "/home/agent/.agent-artifacts/runtimes/public/mcp/gitlab"


def _dispatch(effect, interpreters):
    from agent_artifacts.application.execution import _dispatch as dispatch

    return dispatch(effect, tuple(interpreters))


class _Provider:
    def __init__(self, provider: str = "macos-keychain") -> None:
        self.provider = provider


class _Vault:
    provider = "vault"

    def resolution_argv(self, reference):
        return ("vault", "read", reference.provider.service)


def _planned(description=None, **overrides):
    planned = _plan(description, **overrides)
    assert isinstance(planned, Ok), getattr(planned, "diagnostics", ())
    return planned.value


class _Assembles:
    """The two artifacts every case here is assembled from."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.registry = LocalHarnessRegistry(str(pathlib.Path(temporary.name).resolve()))
        self.first = _planned()
        self.second = _planned(resolved=_resolved("gitlab"), root=SECOND_ROOT)

    def _assembled(self, *installations, **kwargs):
        assembled = interpreters_for(
            installations or (self.first,),
            registry=self.registry,
            credential_providers=kwargs.pop("credential_providers", (_Provider(),)),
            **kwargs,
        )
        self.assertIsInstance(assembled, Ok, getattr(assembled, "diagnostics", ()))
        return assembled.value


class InterpreterAssemblyTest(_Assembles, unittest.TestCase):
    def test_one_artifact_gets_one_interpreter_of_each_kind(self) -> None:
        assembled = self._assembled()

        self.assertEqual(
            [type(item) for item in assembled],
            [
                FileEffectInterpreter,
                RuntimeEffectInterpreter,
                HarnessEffectInterpreter,
                CredentialEffectInterpreter,
            ],
        )

    def test_the_file_interpreter_already_holds_the_launcher_it_will_write(self) -> None:
        """The effect carries a digest, never the bytes. This is where the bytes come from."""

        files = self._assembled()[0]

        self.assertIn(str(self.first.launcher.digest), files.contents)
        self.assertEqual(
            files.contents[str(self.first.launcher.digest)],
            self.first.launcher.content.encode("utf-8"),
        )

    def test_the_runtime_interpreter_is_bound_to_that_artifact_and_carries_its_limits(self) -> None:
        runtime = self._assembled(self.first, timeout_seconds=42.0, offline=True)[1]

        self.assertEqual(runtime.runtime.environment, self.first.environment)
        self.assertEqual(runtime.runtime.timeout_seconds, 42.0)
        self.assertTrue(runtime.runtime.offline)

    def test_the_harness_interpreter_holds_that_artifact_registrations_and_its_name(self) -> None:
        harness = self._assembled()[2]

        self.assertEqual(harness.registrations, self.first.registrations)
        self.assertEqual(harness.artifact, self.first.environment.artifact)

    def test_the_credential_interpreter_holds_the_references_naming_its_provider(self) -> None:
        credentials = self._assembled()[3]

        self.assertEqual(credentials.references, intended_receipt(self.first).credentials)
        self.assertEqual(credentials.provider.provider, "macos-keychain")


class TwoArtifactAssemblyTest(_Assembles, unittest.TestCase):
    def test_each_artifact_launcher_reaches_its_own_file_interpreter(self) -> None:
        assembled = self._assembled(self.first, self.second)

        chosen = _dispatch(
            WriteFile(self.second.launcher.path, str(self.second.launcher.digest), True), assembled
        )

        self.assertIsInstance(chosen, FileEffectInterpreter)
        self.assertEqual(chosen.environment, self.second.environment)

    def test_each_artifact_registration_reaches_its_own_harness_interpreter(self) -> None:
        assembled = self._assembled(self.first, self.second)
        registration = self.second.registrations[0]

        chosen = _dispatch(
            ConfigureHarness(
                registration.target.harness,
                self.second.environment.artifact,
                registration.target.settings_file,
            ),
            assembled,
        )

        self.assertIsInstance(chosen, HarnessEffectInterpreter)
        self.assertEqual(chosen.artifact, self.second.environment.artifact)

    def test_two_artifacts_on_one_provider_share_one_credential_interpreter(self) -> None:
        assembled = self._assembled(self.first, self.second)

        credentials = [item for item in assembled if isinstance(item, CredentialEffectInterpreter)]

        self.assertEqual(len(credentials), 1)

    def test_a_provider_nobody_supplied_is_refused_before_anything_is_touched(self) -> None:
        """Refusing here names the missing adapter. Letting it through would surface half-way
        through a transaction that has already written files, as an effect nobody carries out."""

        refused = interpreters_for((self.first,), registry=self.registry, credential_providers=())

        self.assertIsInstance(refused, Err, refused)
        self.assertEqual(refused.diagnostics[0].code, INTERPRETERS_UNAVAILABLE)
        self.assertIn("macos-keychain", refused.diagnostics[0].message)

    def test_two_providers_get_one_interpreter_each(self) -> None:
        vaulted = _planned(
            resolved=_resolved("gitlab"),
            root=SECOND_ROOT,
            sources=(
                SecretProviderReference(
                    TOKEN, CredentialProviderRef("vault", "aart", "gitlab-token")
                ),
                PersistedConfigValue(ORG, "acme"),
            ),
            resolvers=(_Vault(),),
        )

        assembled = self._assembled(
            self.first,
            vaulted,
            credential_providers=(_Provider(), _Provider("vault")),
        )

        credentials = [item for item in assembled if isinstance(item, CredentialEffectInterpreter)]

        self.assertEqual(
            [item.provider.provider for item in credentials], ["macos-keychain", "vault"]
        )

    def test_an_artifact_with_no_credentials_needs_no_provider(self) -> None:
        plain = _planned(
            description=_description(
                inputs=(ConfigInput(ORG, EnvironmentBinding("GITHUB_ORG"), default="acme"),)
            ),
            sources=(PersistedConfigValue(ORG, "acme"),),
        )

        assembled = interpreters_for((plain,), registry=self.registry, credential_providers=())

        self.assertIsInstance(assembled, Ok, getattr(assembled, "diagnostics", ()))


class AssemblyRefusalTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.registry = LocalHarnessRegistry(str(pathlib.Path(temporary.name).resolve()))

    def test_it_refuses_anything_that_is_not_a_planned_installation(self) -> None:
        with self.assertRaises(ValueError):
            interpreters_for((object(),), registry=self.registry)

    def test_it_refuses_one_adapter_claiming_a_provider_another_already_holds(self) -> None:
        with self.assertRaises(ValueError):
            interpreters_for(
                (),
                registry=self.registry,
                credential_providers=(_Provider(), _Provider()),
            )


if __name__ == "__main__":
    unittest.main()
