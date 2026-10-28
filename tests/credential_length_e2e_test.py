"""§204, INV-308, INV-309, D-492: a credential cut by the store's prompt is caught and entered again.

The owner's Jira token arrived as 128 characters: macOS's own prompt keeps at most 128 and drops
the rest without a word. Here the artifact declares how long its token is, the store's "prompt"
cuts what it is given to 128, and the other way to enter it is a fake that stores the whole value
in the store itself, as the real dialog does, so aart-cli never holds it. The real Keychain and the
real dialog are never touched.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import unittest
from unittest import mock

from aart_cli import cli
from aart_cli.domain.credentials import CredentialObservation, CredentialState, ProviderState
from aart_cli.domain.result import Ok
from aart_cli.io.credential_entry import EntryOutcome
from tests.artifact_installation_e2e_test import MANIFEST, SERVER_SOURCE
from tests.configured_install_command_e2e_test import _environment

GITHUB = "company/mcp/github"
CEILING = 128
WHOLE = 190
DECLARED = copy.deepcopy(MANIFEST)
DECLARED["inputs"][0]["validation"] = {
    "min_length": 150,
    "message": "GitHub tokens here have 190 characters",
}
AUTHORED = (
    ("github/aart-cli.json", json.dumps(DECLARED)),
    ("github/server.py", SERVER_SOURCE),
    ("github/requirements.txt", "# no third-party packages\n"),
)


class _CuttingStore:
    """A store whose prompt keeps at most 128 characters of what the person typed."""

    provider = "test-keychain"

    def __init__(self, typed: int = WHOLE, cut: int = CEILING) -> None:
        self.typed, self.cut = typed, cut
        self.stored: dict[str, int] = {}

    @staticmethod
    def _address(reference) -> str:
        return f"{reference.provider.service}/{reference.provider.account}"

    def available(self) -> ProviderState:
        return ProviderState.AVAILABLE

    def inspect(self, reference) -> Ok:
        held = self.stored.get(self._address(reference))
        return Ok(
            CredentialObservation(
                reference,
                ProviderState.AVAILABLE,
                CredentialState.ABSENT if held is None else CredentialState.PRESENT,
                "" if held is None else f"a value of {held} bytes is present",
                length=held,
                clipped=held == self.cut,
            )
        )

    def resolution_argv(self, reference) -> tuple[str, ...]:
        return ("/usr/bin/false", "--service", reference.provider.service)

    def store(self, reference, secret=None, *, replace: bool = False) -> Ok:
        # Only the length is kept: that is all a test needs, and no value is ever made up.
        self.stored[self._address(reference)] = min(self.typed, self.cut)
        return self.inspect(reference)

    def delete(self, reference) -> Ok:
        self.stored.pop(self._address(reference), None)
        return self.inspect(reference)


class _OtherWay:
    """The dialog, as far as aart-cli can tell: asked with a reason, it stores in the store."""

    def __init__(self, store: _CuttingStore, outcome: EntryOutcome) -> None:
        self.store, self.outcome = store, outcome
        self.reasons: list[str] = []

    def enter(self, reference, *, reason: str) -> EntryOutcome:
        self.reasons.append(reason)
        if self.outcome is EntryOutcome.ENTERED:
            self.store.stored[self.store._address(reference)] = WHOLE
        return self.outcome


def _run(env, store, entry, *argv: str, as_json: bool = True) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with (
        mock.patch.dict(os.environ, env.xdg, clear=False),
        mock.patch("os.getcwd", return_value=str(env.project)),
        mock.patch("aart_cli.commands.marketplace._credential_providers", lambda: (store,)),
        mock.patch("aart_cli.commands.marketplace._credential_entry", lambda: (entry,)),
        mock.patch("aart_cli.commands.marketplace._terminal_present", lambda: True),
        mock.patch("aart_cli.cli_inputs._terminal_present", lambda: True),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = cli.main([*argv, "--project", str(env.project), *(("--json",) if as_json else ())])
    return code, out.getvalue(), err.getvalue()


def _install(env, store, entry) -> None:
    code, out, _ = _run(env, store, entry, "consume", "install", GITHUB, "--profile", "claude")
    digest = json.loads(out)["review_digest"]
    code, out, _ = _run(
        env,
        store,
        entry,
        "consume",
        "install",
        GITHUB,
        "--profile",
        "claude",
        "--yes",
        "--expect",
        digest,
    )
    assert code == 0, out


def _set_credential(env, store, entry) -> tuple[int, str]:
    named = ("consume", "inputs", "set-credential", GITHUB, "github-token", "--harness", "claude")
    code, out, _ = _run(env, store, entry, *named)
    assert code == 0, out
    digest = json.loads(out)["review_digest"]
    code, out, _ = _run(env, store, entry, *named, "--yes", "--expect", digest)
    return code, out


class ACutCredentialIsEnteredAgainTest(unittest.TestCase):
    def test_the_install_asks_the_other_way_and_keeps_the_whole_value(self) -> None:
        store = _CuttingStore()
        entry = _OtherWay(store, EntryOutcome.ENTERED)
        with _environment(authored=AUTHORED) as env:
            _install(env, store, entry)
            code, out, _ = _run(env, store, entry, "doctor")
            receipts = [
                path.read_text(encoding="utf-8")
                for path in (env.home / ".aart-cli").rglob("*.json")
                if "credential_checks" in path.read_text(encoding="utf-8")
            ]

        self.assertEqual(len(entry.reasons), 1)
        self.assertIn("128 characters, expected at least 150", entry.reasons[0])
        self.assertIn("GitHub tokens here have 190 characters", entry.reasons[0])
        self.assertEqual(list(store.stored.values()), [WHOLE])
        self.assertTrue(receipts, "the receipt records the declared length")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["credentials"][0]["health"], "present")

    def test_a_value_left_cut_is_not_configured_wherever_it_is_read(self) -> None:
        store = _CuttingStore()
        entry = _OtherWay(store, EntryOutcome.CANCELLED)
        with _environment(authored=AUTHORED) as env:
            _install(env, store, entry)
            code, out, _ = _run(env, store, entry, "doctor")
            _, text, _ = _run(env, store, entry, "doctor", as_json=False)
            _, listed, _ = _run(env, store, entry, "consume", "inputs", "list", as_json=False)

        self.assertNotEqual(code, 0)
        credential = json.loads(out)["credentials"][0]
        self.assertEqual(credential["health"], "invalid")
        self.assertIn("128 characters, expected at least 150", credential["detail"])
        self.assertIn("is not configured: the stored value has 128 characters", text)
        self.assertIn("Not configured: the stored value has 128 characters", listed)

    def test_set_credential_fails_by_name_while_the_value_is_still_cut(self) -> None:
        store = _CuttingStore()
        cancelled = _OtherWay(store, EntryOutcome.CANCELLED)
        with _environment(authored=AUTHORED) as env:
            _install(env, store, cancelled)
            code, out = _set_credential(env, store, cancelled)
            entered = _OtherWay(store, EntryOutcome.ENTERED)
            fixed, after = _set_credential(env, store, entered)

        self.assertNotEqual(code, 0)
        self.assertIn("github-token is not configured: the stored value has 128", out)
        self.assertEqual(fixed, 0, after)
        self.assertEqual(len(entered.reasons), 1)
        self.assertEqual(list(store.stored.values()), [WHOLE])

    def test_a_value_that_fits_asks_nothing_more(self) -> None:
        store = _CuttingStore(typed=160, cut=4096)
        entry = _OtherWay(store, EntryOutcome.ENTERED)
        with _environment(authored=AUTHORED) as env:
            _install(env, store, entry)

        self.assertEqual(entry.reasons, [])
        self.assertEqual(list(store.stored.values()), [160])


if __name__ == "__main__":
    unittest.main()
