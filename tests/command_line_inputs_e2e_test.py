"""§186, §201, INV-287, INV-302, D-468, D-486: `consume install` answers inputs without the TUI.

The flags name the artifact with its Registry alias. A configuration value is an argument. A
credential is never one: the review says the credential store will ask for it, and applying the
review in a terminal hands that terminal to the store's own prompt, so its value passes through no
part of aart-cli and reaches no file, receipt or output. With no terminal the apply is refused before
anything is written. The real Keychain is never touched: the store here is a fake that "prompts" by
making up its own value, the way a person would type one aart-cli never sees.
"""

from __future__ import annotations

import contextlib
import io
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

GITHUB = "company/mcp/github"
TOKEN = f"{GITHUB}:github-token"


class _RecordingCredentialStore:
    """One item per address, holding exactly what the install handed over."""

    provider = "test-keychain"

    def __init__(self) -> None:
        self.stored: dict[str, str] = {}
        #: What the store's own prompt took from the person, which aart-cli never handed over.
        self.prompted: list[str] = []

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
        if secret is None:
            typed = secrets.token_hex(16)
            self.prompted.append(typed)
            self.stored[self._address(reference)] = typed
        else:
            # Only `--set-later`'s placeholder is ever carried.
            self.stored[self._address(reference)] = secret.consume()
        return self.inspect(reference)

    def delete(self, reference) -> Ok:
        self.stored.pop(self._address(reference), None)
        return self.inspect(reference)


def _install(env, *flags: str, store=None, terminal: bool = False):
    providers = () if store is None else (store,)
    briefing = io.StringIO()
    with (
        mock.patch("aart_cli.commands.marketplace._credential_providers", return_value=providers),
        mock.patch("aart_cli.commands.marketplace._terminal_present", return_value=terminal),
        contextlib.redirect_stderr(briefing),
    ):
        code, payload = env.run("consume", "install", GITHUB, "--profile", "claude", *flags)
    return code, payload, briefing.getvalue()


def _files(root: pathlib.Path) -> list[pathlib.Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def _messages(payload) -> str:
    return " ".join(
        part
        for diagnostic in payload["diagnostics"]
        for part in (diagnostic["message"], *diagnostic.get("remediation", ()))
    )


class CommandLineInputsTest(unittest.TestCase):
    def test_the_review_says_the_credential_store_will_ask_for_the_credential(self) -> None:
        store = _RecordingCredentialStore()
        with _environment(authored=AUTHORED_MCP) as env:
            code, payload, _ = _install(env, store=store)

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            asked = payload["review"]["asked_by_credential_store"]
            self.assertEqual([item["input"] for item in asked], [TOKEN])
            self.assertEqual(asked[0]["guidance"][0]["label"], "GitHub token")
            self.assertEqual(store.stored, {})
            self.assertEqual(list(env.project.iterdir()), [])

    def test_without_a_terminal_the_apply_is_refused_and_nothing_is_written(self) -> None:
        store = _RecordingCredentialStore()
        with _environment(authored=AUTHORED_MCP) as env:
            code, payload, _ = _install(env, "--yes", store=store, terminal=False)

            self.assertNotEqual(code, 0)
            self.assertFalse(payload["finalized"])
            messages = _messages(payload)
            self.assertIn(TOKEN, messages)
            self.assertIn("no terminal", messages)
            self.assertIn("--set-later", messages)
            self.assertIn("consume inputs set-credential", messages)
            self.assertEqual(store.stored, {})
            self.assertEqual(list(env.project.iterdir()), [])

    def test_in_a_terminal_the_store_asks_and_the_credential_reaches_only_the_store(self) -> None:
        store = _RecordingCredentialStore()
        with _environment(authored=AUTHORED_MCP) as env:
            code, payload, briefing = _install(
                env,
                "--input",
                f"{GITHUB}:github-org=platform-team",
                "--yes",
                store=store,
                terminal=True,
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertEqual(len(store.prompted), 1)
            self.assertEqual(list(store.stored.values()), store.prompted)
            # The store's prompt is preceded by what the credential is, on the terminal.
            self.assertIn("GitHub token — needed by company/mcp/github", briefing)
            self.assertIn("test-keychain asks for it next", briefing)
            config = env.project / ".claude/aart-cli/mcp/company/github/config/claude.conf"
            self.assertIn(f"{ORG}=platform-team\n", config.read_text(encoding="utf-8"))
            typed = store.prompted[0]
            leaked = [
                path
                for path in _files(env.root)
                if typed in path.read_text(encoding="utf-8", errors="replace")
            ]
            self.assertEqual(leaked, [])
            self.assertNotIn(typed, briefing)

    def test_set_later_stores_the_placeholder_and_keeps_the_default(self) -> None:
        store = _RecordingCredentialStore()
        with _environment(authored=AUTHORED_MCP) as env:
            code, payload, _ = _install(env, "--set-later", "--yes", store=store)

            self.assertEqual(code, 0, payload)
            self.assertNotIn("asked_by_credential_store", payload.get("review", {}))
            self.assertEqual(store.prompted, [])
            self.assertEqual(list(store.stored.values()), [SKIPPED_INPUT])
            config = env.project / ".claude/aart-cli/mcp/company/github/config/claude.conf"
            self.assertIn(f"{ORG}=acme\n", config.read_text(encoding="utf-8"))

    def test_mistakes_are_refused_before_anything_is_written(self) -> None:
        store = _RecordingCredentialStore()
        value = secrets.token_hex(8)
        cases = (
            (("--input", f"{TOKEN}={value}"), store, "never an argument"),
            (("--input", "company/mcp/jira:github-org=x"), store, GITHUB),
            (("--set-later",), None, "no credential store"),
            ((), None, TOKEN),
        )
        for flags, held, named in cases:
            with self.subTest(named=named), _environment(authored=AUTHORED_MCP) as env:
                code, payload, briefing = _install(env, *flags, "--yes", store=held, terminal=True)

                self.assertNotEqual(code, 0)
                self.assertFalse(payload["ok"])
                messages = _messages(payload)
                self.assertIn(named, messages)
                self.assertNotIn(value, messages + briefing)
                self.assertEqual(list(env.project.iterdir()), [])
        self.assertEqual(store.stored, {})


if __name__ == "__main__":
    unittest.main()
