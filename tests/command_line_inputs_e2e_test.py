"""§186, INV-287, D-468: `consume install` answers an MCP server's inputs without a terminal.

The flags name the artifact with its Registry alias. A configuration value is an argument; a
credential is the name of an environment variable, read only after the review was confirmed and
handed straight to the credential store, so it reaches no file, receipt or output. The real
Keychain is never touched: the store here is a fake that records what it was given.
"""

from __future__ import annotations

import os
import pathlib
import secrets
import unittest
from unittest import mock

from aart_cli.domain.credentials import CredentialObservation, CredentialState, ProviderState
from aart_cli.domain.inputs import SKIPPED_INPUT
from aart_cli.domain.result import Ok
from tests.artifact_installation_e2e_test import ORG
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.credential_fixtures import assignment

GITHUB = "company/mcp/github"
VARIABLE = "AART_CLI_TEST_GITHUB_TOKEN"
TOKEN_FLAG = "--secret-env " + assignment(f"{GITHUB}:github-token", "ENVIRONMENT_VARIABLE")


class _RecordingCredentialStore:
    """One item per address, holding exactly what the install handed over."""

    provider = "test-keychain"

    def __init__(self) -> None:
        self.stored: dict[str, str] = {}

    @staticmethod
    def _address(reference) -> str:
        return f"{reference.provider.service}/{reference.provider.account}"

    def available(self) -> ProviderState:
        return ProviderState.AVAILABLE

    def inspect(self, reference) -> Ok:
        held = self._address(reference) in self.stored
        return Ok(
            CredentialObservation(
                reference,
                ProviderState.AVAILABLE,
                CredentialState.PRESENT if held else CredentialState.ABSENT,
            )
        )

    def resolution_argv(self, reference) -> tuple[str, ...]:
        return ("/usr/bin/false", "--service", reference.provider.service)

    def store(self, reference, secret=None, *, replace: bool = False) -> Ok:
        assert secret is not None, "a carried credential arrives with its value"
        self.stored[self._address(reference)] = secret.consume()
        return self.inspect(reference)

    def delete(self, reference) -> Ok:
        self.stored.pop(self._address(reference), None)
        return self.inspect(reference)


def _install(env, *flags: str, environment: dict[str, str] | None = None, store=None):
    providers = () if store is None else (store,)
    with (
        mock.patch("aart_cli.commands.marketplace._credential_providers", return_value=providers),
        mock.patch.dict(os.environ, environment or {}, clear=False),
    ):
        return env.run("consume", "install", GITHUB, "--profile", "claude", *flags)


def _files(root: pathlib.Path) -> list[pathlib.Path]:
    return [path for path in root.rglob("*") if path.is_file()]


class CommandLineInputsTest(unittest.TestCase):
    def test_the_refusal_names_the_flag_for_each_missing_input(self) -> None:
        with _environment(authored=AUTHORED_MCP) as env:
            code, payload = _install(env, store=_RecordingCredentialStore())

            self.assertNotEqual(code, 0)
            # The organisation has a declared default, which stands as its answer (§172.4).
            self.assertEqual([item["id"] for item in payload["inputs"]], ["github-token"])
            self.assertEqual(payload["inputs"][0]["flag"], TOKEN_FLAG)
            self.assertIn(TOKEN_FLAG, " ".join(payload["diagnostics"][0]["remediation"]))
            self.assertEqual(list(env.project.iterdir()), [])

    def test_flags_install_and_the_credential_reaches_only_the_store(self) -> None:
        token = secrets.token_hex(16)
        store = _RecordingCredentialStore()
        with _environment(authored=AUTHORED_MCP) as env:
            code, payload = _install(
                env,
                "--input",
                f"{GITHUB}:github-org=platform-team",
                "--secret-env",
                f"{GITHUB}:github-token={VARIABLE}",
                "--yes",
                environment={VARIABLE: token},
                store=store,
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertEqual(list(store.stored.values()), [token])
            config = env.project / ".claude/aart-cli/mcp/company/github/config/claude.conf"
            self.assertIn(f"{ORG}=platform-team\n", config.read_text(encoding="utf-8"))
            leaked = [
                path
                for path in _files(env.root)
                if token in path.read_text(encoding="utf-8", errors="replace")
            ]
            self.assertEqual(leaked, [])

    def test_set_later_stores_the_placeholder_and_keeps_the_default(self) -> None:
        store = _RecordingCredentialStore()
        with _environment(authored=AUTHORED_MCP) as env:
            code, payload = _install(env, "--set-later", "--yes", store=store)

            self.assertEqual(code, 0, payload)
            self.assertEqual(list(store.stored.values()), [SKIPPED_INPUT])
            config = env.project / ".claude/aart-cli/mcp/company/github/config/claude.conf"
            self.assertIn(f"{ORG}=acme\n", config.read_text(encoding="utf-8"))

    def test_mistakes_are_refused_before_anything_is_written(self) -> None:
        store = _RecordingCredentialStore()
        cases = (
            (("--secret-env", f"{GITHUB}:github-token={VARIABLE}"), store, VARIABLE),
            (("--input", "company/mcp/jira:github-org=x"), store, GITHUB),
            (("--input", f"{GITHUB}:github-token=x"), store, "--secret-env"),
            (("--set-later",), None, "no credential store"),
        )
        for flags, held, named in cases:
            with self.subTest(named=named), _environment(authored=AUTHORED_MCP) as env:
                with mock.patch.dict(os.environ, {VARIABLE: ""}, clear=False):
                    code, payload = _install(env, *flags, "--yes", store=held)

                self.assertNotEqual(code, 0)
                self.assertFalse(payload["ok"])
                messages = " ".join(
                    part
                    for diagnostic in payload["diagnostics"]
                    for part in (diagnostic["message"], *diagnostic.get("remediation", ()))
                )
                self.assertIn(named, messages)
                self.assertEqual(list(env.project.iterdir()), [])
        self.assertEqual(store.stored, {})


if __name__ == "__main__":
    unittest.main()
