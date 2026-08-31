"""Which interpreter carries out an effect when a transaction installs more than one artifact.

One Selection is one transaction (D-064), so `execute_installation` is handed one tuple of
interpreters and every member's effects run through it. Two artifacts therefore mean two file
interpreters in that tuple and two runtime interpreters, each bound to the environment it is allowed
to act for.

Dispatch takes the first interpreter that says it supports an effect. If "supports" only asks what
kind of effect it is, the first file interpreter claims every write in the transaction, including
the ones belonging to the other artifact -- and then refuses them, because they are outside the
environment it owns. Failing closed is the right instinct in the wrong place: the effect was
perfectly legitimate and there was an interpreter in the tuple that owned it.

So supporting an effect means being allowed to carry it out, not merely recognizing its type.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from agent_artifacts.domain.credentials import (
    CredentialProviderRef,
    CredentialReference,
)
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CopyTree,
    CreatePythonEnvironment,
    InstallPythonDependencies,
    RemoveOwnedPath,
    UnconfigureHarness,
    VerifyCredential,
    WriteFile,
)
from agent_artifacts.domain.harness import McpRegistration, Scope, mcp_target
from agent_artifacts.domain.identifiers import InputId
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.execution import (
    CredentialEffectInterpreter,
    FileEffectInterpreter,
    HarnessEffectInterpreter,
    RuntimeEffectInterpreter,
)
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.python_runtime import LocalPythonRuntime


def _registration(server: str) -> McpRegistration:
    return McpRegistration(mcp_target("claude", Scope.PROJECT), server, f"/opt/{server}/launch")


def _reference(name: str) -> CredentialReference:
    return CredentialReference(InputId(name), CredentialProviderRef("macos-keychain", "aart", name))


class _Provider:
    provider = "macos-keychain"


def _dispatch(effect, interpreters):
    from agent_artifacts.application.execution import _dispatch as dispatch

    return dispatch(effect, tuple(interpreters))


class TwoArtifactDispatchTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = pathlib.Path(temporary.name).resolve()
        self.first = ArtifactEnvironment("mcp/github", f"{root}/runtimes/mcp/github")
        self.second = ArtifactEnvironment("mcp/gitlab", f"{root}/runtimes/mcp/gitlab")
        self.files = (FileEffectInterpreter(self.first), FileEffectInterpreter(self.second))
        self.runtimes = (
            RuntimeEffectInterpreter(LocalPythonRuntime(self.first)),
            RuntimeEffectInterpreter(LocalPythonRuntime(self.second)),
        )

    def test_a_write_for_the_second_artifact_reaches_the_second_interpreter(self) -> None:
        effect = WriteFile(f"{self.second.root}/launch", "sha256:" + "a" * 64, executable=True)

        self.assertIs(_dispatch(effect, self.files), self.files[1])

    def test_a_write_for_the_first_artifact_still_reaches_the_first(self) -> None:
        effect = WriteFile(f"{self.first.root}/launch", "sha256:" + "a" * 64, executable=True)

        self.assertIs(_dispatch(effect, self.files), self.files[0])

    def test_a_copy_into_the_second_artifact_reaches_the_second_interpreter(self) -> None:
        effect = CopyTree("/store/objects/ab/cd", f"{self.second.payload}")

        self.assertIs(_dispatch(effect, self.files), self.files[1])

    def test_a_removal_inside_the_second_artifact_reaches_the_second_interpreter(self) -> None:
        effect = RemoveOwnedPath(f"{self.second.root}/payload", recursive=True)

        self.assertIs(_dispatch(effect, self.files), self.files[1])

    def test_an_environment_for_the_second_artifact_reaches_the_second_runtime(self) -> None:
        effect = CreatePythonEnvironment("mcp/gitlab", self.second.environment, "/usr/bin/python3")

        self.assertIs(_dispatch(effect, self.runtimes), self.runtimes[1])

    def test_dependencies_for_the_second_artifact_reach_the_second_runtime(self) -> None:
        effect = InstallPythonDependencies(
            self.second.environment, "requirements.txt", "requirements", "pip"
        )

        self.assertIs(_dispatch(effect, self.runtimes), self.runtimes[1])

    def test_a_path_no_interpreter_owns_is_dispatched_to_nobody(self) -> None:
        """Refusing to dispatch says "nothing here may do this"; dispatching to a stranger who then
        refuses says "this could not be done", and the two are different reports."""

        effect = WriteFile("/etc/passwd", "sha256:" + "a" * 64)

        self.assertIsNone(_dispatch(effect, self.files))

    def test_an_effect_of_another_kind_is_still_not_a_file_effect(self) -> None:
        harness = ConfigureHarness("claude", "mcp/github", f"{self.first.root}/settings.json")

        self.assertIsNone(_dispatch(harness, self.files))

    def test_the_second_artifact_reaches_the_harness_interpreter_that_holds_its_registration(
        self,
    ) -> None:
        """Two artifacts mean two harness interpreters, each holding only its own registrations."""

        registry = LocalHarnessRegistry(str(pathlib.Path(self.first.root).parent.parent))
        first = HarnessEffectInterpreter(registry, (_registration("github"),))
        second = HarnessEffectInterpreter(registry, (_registration("gitlab"),))

        chosen = _dispatch(UnconfigureHarness("claude", "gitlab", ".mcp.json"), (first, second))

        self.assertIs(chosen, second)

    def test_a_credential_reference_this_interpreter_was_never_given_is_not_its_effect(
        self,
    ) -> None:
        mine = CredentialEffectInterpreter(_Provider(), (_reference("github-token"),))
        theirs = CredentialEffectInterpreter(_Provider(), (_reference("gitlab-token"),))

        chosen = _dispatch(
            VerifyCredential(str(_reference("gitlab-token")), "macos-keychain"), (mine, theirs)
        )

        self.assertIs(chosen, theirs)

    def test_the_owning_interpreter_actually_carries_it_out(self) -> None:
        """Dispatch is only right if the interpreter it chose can do the work."""

        interpreter = self.files[1]
        digest = interpreter.offer(b"#!/bin/sh\nexec true\n")
        pathlib.Path(self.second.root).mkdir(parents=True)

        applied = interpreter.apply(
            WriteFile(f"{self.second.root}/launch", digest, executable=True)
        )

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))


if __name__ == "__main__":
    unittest.main()
