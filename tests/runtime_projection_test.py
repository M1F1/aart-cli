"""CP-10 — the generated runtime projection: what a launcher may and may not contain."""

from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.application.runtime_projection import (
    LAUNCHER_BINDING_UNSUPPORTED,
    LAUNCHER_INVALID,
    LAUNCHER_PROVIDER_UNRESOLVABLE,
    LAUNCHER_TRANSPORT_CONFLICT,
    MISSING_CONFIGURATION_STATUS,
    generate_launcher,
)
from aart_cli.domain.configuration_files import (
    configuration_value_problem,
    render_configuration_file,
)
from aart_cli.domain.credentials import CredentialProviderRef, CredentialReference
from aart_cli.domain.identifiers import InputId
from aart_cli.domain.inputs import (
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
from aart_cli.domain.launch import (
    LAUNCHER_FILENAME,
    LaunchContract,
    Transport,
    launcher_path,
    shell_quote,
)
from aart_cli.domain.python_runtime import ArtifactEnvironment
from aart_cli.domain.result import Err, Ok

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

    def test_a_config_value_is_never_written_into_the_launcher(self):
        hostile = "'; touch /tmp/pwned; echo '"
        bound = bind(
            BoundInput(
                ConfigInput(InputId("org"), EnvironmentBinding("GITHUB_ORG")),
                PersistedConfigValue(InputId("org"), hostile),
            )
        )
        content = generate(bound).value.content
        self.assertNotIn(hostile, content)
        self.assertNotIn("touch", content)
        self.assertIn("/config/", content)

    def test_a_launcher_without_configuration_reads_no_file_and_takes_no_harness(self):
        content = generate(bind(BoundInput(token_input(), token_source()))).value.content
        self.assertNotIn("AART_HARNESS", content)
        self.assertNotIn("/config/", content)

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


def _started(root: pathlib.Path, bound: BoundInputs, *argv: str, contract=None):
    """Run the generated launcher for real, with an interpreter that reports what it was given."""

    environment = ArtifactEnvironment("mcp/github", str(root))
    projection = generate_launcher(environment, contract or LaunchContract("server.py"), bound)
    launcher = pathlib.Path(projection.value.path)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(projection.value.content, encoding="utf-8")
    launcher.chmod(0o700)
    interpreter = pathlib.Path(environment.interpreter)
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text(
        '#!/bin/sh\nshift\nprintf "env=%s\\n" "${GITHUB_ORG-unset}"\n'
        'for argument in "$@"; do printf "arg=%s\\n" "$argument"; done\n',
        encoding="utf-8",
    )
    interpreter.chmod(0o700)
    return subprocess.run(
        [str(launcher), *argv], capture_output=True, text=True, timeout=30, check=False
    )


def _configured(**values: str) -> BoundInputs:
    items = []
    for name, value in values.items():
        identifier = InputId(name.replace("_", "-"))
        binding = (
            EnvironmentBinding("GITHUB_ORG")
            if name == "org"
            else CliArgumentBinding(f"--{identifier}")
        )
        items.append(
            BoundInput(ConfigInput(identifier, binding), PersistedConfigValue(identifier, value))
        )
    return BoundInputs(tuple(items))


class LauncherReadsHarnessConfigurationTest(unittest.TestCase):
    """The configured values reach the process from the starting harness's file (D-264)."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name) / "mcp" / "github"
        (self.root / "config").mkdir(parents=True)
        self.bound = _configured(org="acme", site_url="https://forge.example")

    def _write(self, harness: str, content: str) -> None:
        (self.root / "config" / f"{harness}.conf").write_text(content, encoding="utf-8")

    def test_each_harness_starts_the_server_with_its_own_values(self):
        self._write(
            "claude", render_configuration_file("mcp/github", "claude", self.bound.config_values)
        )
        self._write(
            "opencode",
            render_configuration_file(
                "mcp/github",
                "opencode",
                ((InputId("org"), "other-org"), (InputId("site-url"), "https://two.example")),
            ),
        )
        claude = _started(self.root, self.bound, "claude")
        opencode = _started(self.root, self.bound, "opencode")
        self.assertEqual(claude.returncode, 0, claude.stderr)
        self.assertEqual(
            claude.stdout.splitlines(), ["env=acme", "arg=--site-url", "arg=https://forge.example"]
        )
        self.assertEqual(
            opencode.stdout.splitlines(),
            ["env=other-org", "arg=--site-url", "arg=https://two.example"],
        )

    @settings(max_examples=25, deadline=None)
    @given(
        st.text(
            st.characters(codec="utf-8", exclude_categories=("Cc", "Cf", "Cs", "Zl", "Zp")),
            min_size=1,
            max_size=40,
        ).filter(lambda value: configuration_value_problem(value) is None)
    )
    def test_any_value_the_file_can_hold_reaches_the_process_exactly_and_runs_nothing(self, value):
        self._write(
            "claude",
            render_configuration_file(
                "mcp/github",
                "claude",
                ((InputId("org"), value), (InputId("site-url"), f"{value}$(touch pwned)")),
            ),
        )
        started = _started(self.root, self.bound, "claude")
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(
            started.stdout.split("\n")[:3],
            [f"env={value}", "arg=--site-url", f"arg={value}$(touch pwned)"],
        )
        self.assertFalse((self.root / "pwned").exists())
        self.assertFalse(pathlib.Path("pwned").exists())

    def test_started_without_a_harness_it_stops_and_says_why(self):
        for argv in ((), ("../state",), ("",)):
            with self.subTest(argv=argv):
                started = _started(self.root, self.bound, *argv)
                self.assertEqual(started.returncode, MISSING_CONFIGURATION_STATUS)
                self.assertIn("without the harness", started.stderr)
                self.assertEqual(started.stdout, "")

    def test_a_missing_file_stops_it_and_names_where_to_set_the_values(self):
        started = _started(self.root, self.bound, "codex")
        self.assertEqual(started.returncode, MISSING_CONFIGURATION_STATUS)
        self.assertIn("has no configuration for codex", started.stderr)
        self.assertIn("User variables and credentials", started.stderr)

    def test_a_missing_or_repeated_value_stops_it_rather_than_starting_half_configured(self):
        for content, reason in (
            ("org=acme\n", "has no value for site-url"),
            ("org=acme\norg=other\nsite-url=https://x\n", "sets org twice"),
            ("org=\nsite-url=https://x\n", "has no value for org"),
        ):
            with self.subTest(content=content):
                self._write("claude", content)
                started = _started(self.root, self.bound, "claude")
                self.assertEqual(started.returncode, MISSING_CONFIGURATION_STATUS)
                self.assertIn(reason, started.stderr)
                self.assertEqual(started.stdout, "")

    def test_a_config_variable_may_not_collide_with_a_declared_environment_binding(self):
        bound = bind(
            BoundInput(
                ConfigInput(InputId("org"), CliArgumentBinding("--org")),
                PersistedConfigValue(InputId("org"), "acme"),
            ),
            BoundInput(
                ConfigInput(InputId("shadow"), EnvironmentBinding("AART_CONFIG_ORG")),
                PersistedConfigValue(InputId("shadow"), "overwritten"),
            ),
        )
        result = generate(bound)
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, LAUNCHER_INVALID)


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
