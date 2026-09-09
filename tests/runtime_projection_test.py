"""CP-10 — the generated runtime projection: what a launcher may and may not contain."""

from __future__ import annotations

import re
import subprocess
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_artifacts.application.runtime_projection import (
    LAUNCHER_BINDING_UNSUPPORTED,
    LAUNCHER_INVALID,
    LAUNCHER_PROVIDER_UNRESOLVABLE,
    LAUNCHER_TRANSPORT_CONFLICT,
    generate_launcher,
)
from agent_artifacts.domain.credentials import CredentialProviderRef, CredentialReference
from agent_artifacts.domain.identifiers import InputId
from agent_artifacts.domain.inputs import (
    BoundInput,
    BoundInputs,
    CliArgumentBinding,
    ConfigInput,
    EnvironmentBinding,
    FileBinding,
    PersistedConfigValue,
    SecretInput,
    SecretProviderReference,
    StdinBinding,
)
from agent_artifacts.domain.launch import (
    LAUNCHER_FILENAME,
    LaunchContract,
    Transport,
    launcher_path,
    shell_quote,
)
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.result import Err, Ok

ROOT = "/opt/agents/.tabnine/agent/aart/mcp/github"
ENVIRONMENT = ArtifactEnvironment("mcp/github", ROOT)
KEYCHAIN = CredentialProviderRef("macos-keychain", "aart", "github-token")


class _Resolver:
    """A provider that can name the argv resolving a reference, and nothing else."""

    provider = "macos-keychain"

    def resolution_argv(self, reference: CredentialReference) -> tuple[str, ...]:
        return (
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            reference.provider.account,
            "-s",
            reference.provider.service,
            "-w",
        )


def token_input(binding: object = None) -> SecretInput:
    return SecretInput(InputId("github-token"), binding or EnvironmentBinding("GITHUB_TOKEN"))


def token_source() -> SecretProviderReference:
    return SecretProviderReference(InputId("github-token"), KEYCHAIN)


def bind(*items: BoundInput) -> BoundInputs:
    return BoundInputs(items)


def generate(bound: BoundInputs, contract: LaunchContract | None = None):
    return generate_launcher(
        ENVIRONMENT,
        contract or LaunchContract("server.py"),
        bound,
        resolvers=(_Resolver(),),
    )


class ShellQuotingTest(unittest.TestCase):
    def test_quoting_is_single_quoted_and_closes_every_embedded_quote(self):
        self.assertEqual(shell_quote("plain"), "'plain'")
        self.assertEqual(shell_quote(""), "''")
        self.assertEqual(shell_quote("it's"), "'it'\\''s'")
        self.assertEqual(shell_quote("$(rm -rf /)"), "'$(rm -rf /)'")

    def test_quoting_refuses_a_value_that_cannot_survive_an_argument_vector(self):
        with self.assertRaises(ValueError):
            shell_quote("before\x00after")
        with self.assertRaises(ValueError):
            shell_quote(b"bytes")  # type: ignore[arg-type]

    @settings(max_examples=40, deadline=None)
    @given(
        st.lists(
            st.text(
                alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
                min_size=0,
                max_size=40,
            ),
            min_size=1,
            max_size=8,
        )
    )
    def test_any_value_reaches_a_real_shell_exactly_as_written(self, values: list[str]):
        script = "printf '%s\\0' " + " ".join(shell_quote(value) for value in values)
        completed = subprocess.run(
            ["/bin/sh", "-c", script],
            capture_output=True,
            check=True,
            timeout=30,
        )
        produced = completed.stdout.decode("utf-8").split("\x00")[:-1]
        self.assertEqual(produced, values)


class LaunchContractTest(unittest.TestCase):
    def test_entrypoint_stays_inside_the_payload(self):
        for bad in ("", "/absolute.py", "../escape.py", "a/../../escape.py", "with\nnewline"):
            with self.subTest(entrypoint=bad), self.assertRaises(ValueError):
                LaunchContract(bad)

    def test_transport_and_arguments_are_validated(self):
        with self.assertRaises(ValueError):
            LaunchContract("server.py", transport="stdio")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            LaunchContract("server.py", arguments=("ok", "bad\x00"))
        contract = LaunchContract("bin/server.py", Transport.STDIO, ("--strict",))
        self.assertEqual(contract.transport, Transport.STDIO)

    def test_the_launcher_sits_at_the_artifact_root(self):
        self.assertEqual(launcher_path(ENVIRONMENT), f"{ROOT}/{LAUNCHER_FILENAME}")


class GeneratedLauncherTest(unittest.TestCase):
    def test_the_launcher_runs_the_interpreter_the_artifact_owns(self):
        result = generate(bind())
        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        content = result.value.content
        self.assertIn(shell_quote(ENVIRONMENT.interpreter), content)
        self.assertIn(shell_quote(ENVIRONMENT.payload_path("server.py")), content)
        self.assertEqual(result.value.path, f"{ROOT}/{LAUNCHER_FILENAME}")
        self.assertTrue(result.value.executable)

    def test_the_launcher_never_reaches_for_an_interpreter_it_does_not_own(self):
        content = generate(bind()).value.content
        for absent in ("/usr/bin/python", "python3", "$(command -v python", "PATH=/usr"):
            self.assertNotIn(absent, content)

    def test_the_launcher_installs_nothing_and_does_not_need_aart(self):
        """Only two programs may be invoked: the owned interpreter and the secret provider.

        Asserted by reading every command the script runs rather than by searching for words --
        the artifact\'s own installed path legitimately contains "aart" and ".venv".
        """

        content = generate(bind(BoundInput(token_input(), token_source()))).value.content
        invoked = set()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            if stripped.startswith("exec "):
                invoked.add(stripped.split()[1])
            for match in re.finditer(r"\$\((\S+)", stripped):
                invoked.add(match.group(1))
        self.assertEqual(invoked, {'"$AART_INTERPRETER"', "'/usr/bin/security'"})

    def test_a_secret_is_resolved_at_launch_rather_than_written_into_the_file(self):
        content = generate(bind(BoundInput(token_input(), token_source()))).value.content
        self.assertIn("/usr/bin/security", content)
        self.assertIn("find-generic-password", content)
        self.assertIn("export GITHUB_TOKEN", content)
        # The value is captured from the provider, never assigned as a literal.
        self.assertIn('GITHUB_TOKEN="$(', content)

    def test_a_config_value_is_quoted_so_a_shell_reproduces_it_exactly(self):
        hostile = "'; touch /tmp/pwned; echo '"
        bound = bind(
            BoundInput(
                ConfigInput(InputId("org"), EnvironmentBinding("GITHUB_ORG")),
                PersistedConfigValue(InputId("org"), hostile),
            )
        )
        content = generate(bound).value.content
        # Skip the environment guard: this asserts what the assignment expands to, and the
        # artifact-owned interpreter it checks for does not exist on this machine.
        body = content.split("fi\n", 1)[1].split("exec ")[0]
        script = body + 'printf "%s" "$GITHUB_ORG"'
        completed = subprocess.run(
            ["/bin/sh", "-c", script], capture_output=True, check=True, timeout=30
        )
        self.assertEqual(completed.stdout.decode("utf-8"), hostile)

    def test_a_cli_bound_secret_reaches_the_command_line_through_a_variable(self):
        bound = bind(BoundInput(token_input(CliArgumentBinding("--token")), token_source()))
        content = generate(bound).value.content
        self.assertIn("--token", content)
        self.assertIn('"$AART_SECRET_GITHUB_TOKEN"', content)

    def test_a_stdin_binding_is_refused_because_the_transport_owns_stdin(self):
        bound = bind(BoundInput(token_input(StdinBinding()), token_source()))
        result = generate(bound)
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, LAUNCHER_TRANSPORT_CONFLICT)

    def test_a_file_binding_is_refused_rather_than_quietly_writing_a_secret_to_disk(self):
        bound = bind(BoundInput(token_input(FileBinding("/tmp/token")), token_source()))
        result = generate(bound)
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, LAUNCHER_BINDING_UNSUPPORTED)

    def test_a_provider_nobody_can_resolve_fails_generation_instead_of_being_skipped(self):
        elsewhere = CredentialProviderRef("vault", "aart", "github-token")
        bound = bind(
            BoundInput(
                token_input(),
                SecretProviderReference(InputId("github-token"), elsewhere),
            )
        )
        result = generate_launcher(
            ENVIRONMENT, LaunchContract("server.py"), bound, resolvers=(_Resolver(),)
        )
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, LAUNCHER_PROVIDER_UNRESOLVABLE)

    def test_a_secret_variable_may_not_collide_with_a_declared_environment_binding(self):
        bound = bind(
            BoundInput(token_input(CliArgumentBinding("--token")), token_source()),
            BoundInput(
                ConfigInput(InputId("shadow"), EnvironmentBinding("AART_SECRET_GITHUB_TOKEN")),
                PersistedConfigValue(InputId("shadow"), "overwritten"),
            ),
        )
        result = generate(bound)
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, LAUNCHER_INVALID)

    def test_generation_is_deterministic_and_digests_its_own_content(self):
        bound = bind(BoundInput(token_input(), token_source()))
        first = generate(bound).value
        second = generate(bound).value
        self.assertEqual(first.content, second.content)
        self.assertEqual(str(first.digest), str(second.digest))
        self.assertEqual(first.digest.algorithm, "sha256")

    def test_the_launcher_stops_when_the_environment_it_needs_is_missing(self):
        content = generate(bind()).value.content
        self.assertIn("set -eu", content)
        self.assertIn("exit 78", content)


class LauncherSecrecyPropertyTest(unittest.TestCase):
    @settings(max_examples=50, deadline=None)
    @given(
        st.lists(
            st.tuples(
                st.from_regex(r"\A[a-z][a-z0-9]{0,8}\Z"),
                st.sampled_from(("env", "cli")),
                st.booleans(),
            ),
            min_size=0,
            max_size=5,
            unique_by=lambda item: item[0],
        ),
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs", "Cc")), min_size=0, max_size=30
        ).map(str.strip),
    )
    def test_no_arrangement_of_inputs_puts_a_provider_value_in_the_file(self, plan, value):
        items = []
        for name, kind, secret in plan:
            identifier = InputId(name)
            binding = (
                EnvironmentBinding(name.upper().replace("-", "_"))
                if kind == "env"
                else CliArgumentBinding(f"--{name}")
            )
            if secret:
                items.append(
                    BoundInput(
                        SecretInput(identifier, binding),
                        SecretProviderReference(
                            identifier, CredentialProviderRef("macos-keychain", "aart", name)
                        ),
                    )
                )
            else:
                items.append(
                    BoundInput(
                        ConfigInput(identifier, binding),
                        PersistedConfigValue(identifier, value or "unset"),
                    )
                )
        result = generate(bind(*items))
        if isinstance(result, Err):
            return
        content = result.value.content
        # Every secret appears only as a resolution command, never as an assigned literal.
        for name, _kind, secret in plan:
            if secret:
                self.assertIn("find-generic-password", content)
                self.assertNotIn(f"={name}", content)


if __name__ == "__main__":
    unittest.main()
