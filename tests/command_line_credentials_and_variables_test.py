"""§198, INV-299, D-483: Credentials and variables from the command line.

`consume inputs list` reads what each installation holds. `consume inputs set` changes one ordinary
value of one installation, as an argument, because ordinary configuration is not secret.
`consume inputs set-credential` takes no value at all: it lends the terminal to the credential
store's own prompt, so the value never passes through aart-cli. All three go through the service
the TUI's Credentials and variables uses. The real Keychain is never touched: the store here is a
fake whose "prompt" makes up the value inside the store, where aart-cli cannot see it.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import secrets
import unittest
from unittest import mock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli import cli
from aart_cli.application.consumer_ui import ConsumerActionKind
from aart_cli.application.credentials_and_variables import (
    InstallationSelector,
    select_installations,
)
from aart_cli.consumer_actions import LocalConsumerActions
from aart_cli.domain.credentials import CredentialObservation, CredentialState, ProviderState
from aart_cli.domain.inputs import SKIPPED_INPUT
from aart_cli.domain.installation_owner import compose_installation_key
from aart_cli.domain.result import Ok
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.credential_fixtures import access_token

GITHUB = "company/mcp/github"


class _PromptingStore:
    """A credential store whose own prompt is the only way a value set later arrives.

    `store` with no carrier is the store asking the person itself. What the person "types" is
    made up here, inside the store, so a test can show it never went through aart-cli. A carrier
    only ever arrives from the install's Set later, holding the placeholder.
    """

    provider = "test-keychain"

    def __init__(self) -> None:
        self.stored: dict[str, str] = {}
        self.carried: list[str] = []
        self.prompted: list[tuple[str, bool]] = []
        self.typed = secrets.token_hex(16)

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
                placeholder=held == SKIPPED_INPUT,
            )
        )

    def resolution_argv(self, reference) -> tuple[str, ...]:
        return ("/usr/bin/false", "--service", reference.provider.service)

    def store(self, reference, secret=None, *, replace: bool = False) -> Ok:
        address = self._address(reference)
        if secret is None:
            self.prompted.append((address, replace))
            self.stored[address] = self.typed
        else:
            self.carried.append(secret.consume())
            self.stored[address] = self.carried[-1]
        return self.inspect(reference)

    def delete(self, reference) -> Ok:
        self.stored.pop(self._address(reference), None)
        return self.inspect(reference)


def _run(env, store, *argv: str, terminal: bool = False, as_json: bool = True):
    """One CLI invocation, with its stdout and stderr, against the fake store only."""

    out, err = io.StringIO(), io.StringIO()
    with (
        mock.patch.dict(os.environ, env.xdg, clear=False),
        mock.patch("os.getcwd", return_value=str(env.project)),
        mock.patch("aart_cli.commands.marketplace._credential_providers", lambda: (store,)),
        mock.patch("aart_cli.cli_inputs._terminal_present", lambda: terminal),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = cli.main([*argv, "--project", str(env.project), *(("--json",) if as_json else ())])
    return code, out.getvalue(), err.getvalue()


def _install(env, store, harnesses: str = "claude") -> None:
    code, out, _ = _run(
        env, store, "consume", "install", GITHUB, "--profile", harnesses, "--set-later", "--yes"
    )
    assert code == 0, out


def _config(env, harness: str) -> str:
    return (
        env.project / f".{harness}/aart-cli/mcp/company/github/config/{harness}.conf"
    ).read_text(encoding="utf-8")


def _files(root: pathlib.Path) -> list[pathlib.Path]:
    return [path for path in root.rglob("*") if path.is_file()]


class InputsListTest(unittest.TestCase):
    def test_list_shows_values_credential_state_placeholders_and_the_command_for_each(
        self,
    ) -> None:
        store = _PromptingStore()
        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store)

            code, out, _ = _run(env, store, "consume", "inputs", "list")

            self.assertEqual(code, 0, out)
            payload = json.loads(out)
            [installation] = payload["installations"]
            self.assertTrue(installation["coordinate"].startswith(GITHUB + "@"))
            self.assertEqual(
                (installation["harness"], installation["scope"]), ("claude", "project")
            )
            self.assertEqual(installation["root"], str(env.project))
            [config] = installation["configuration"]
            self.assertEqual((config["input"], config["value"]), ("github-org", "acme"))
            self.assertFalse(config["placeholder"])
            self.assertEqual(
                config["command"],
                f"aart-cli consume inputs set {GITHUB} github-org=VALUE --harness claude "
                f"--scope project --project {env.project}",
            )
            [credential] = installation["credentials"]
            self.assertEqual(credential["input"], "github-token")
            self.assertEqual(credential["state"], "present")
            self.assertTrue(credential["placeholder"])
            self.assertEqual(
                credential["command"],
                f"aart-cli consume inputs set-credential {GITHUB} github-token --harness claude "
                f"--scope project --project {env.project}",
            )
            self.assertNotIn("value", credential)

            code, text, _ = _run(env, store, "consume", "inputs", "list", as_json=False)
            self.assertEqual(code, 0, text)
            self.assertIn("github-org = acme", text)
            self.assertIn(f"github-token: Still the {SKIPPED_INPUT} placeholder", text)
            self.assertIn(credential["command"], text)

    def test_list_narrows_to_a_coordinate_and_a_harness(self) -> None:
        store = _PromptingStore()
        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store, "claude,opencode")

            _, every, _ = _run(env, store, "consume", "inputs", "list")
            _, one, _ = _run(
                env, store, "consume", "inputs", "list", GITHUB, "--harness", "opencode"
            )
            _, none, _ = _run(env, store, "consume", "inputs", "list", "company/mcp/git")

            self.assertEqual(
                sorted(item["harness"] for item in json.loads(every)["installations"]),
                ["claude", "opencode"],
            )
            self.assertEqual(
                [item["harness"] for item in json.loads(one)["installations"]], ["opencode"]
            )
            self.assertEqual(json.loads(none)["installations"], [])


class InputsSetTest(unittest.TestCase):
    def test_set_reviews_then_changes_one_value_of_one_installation(self) -> None:
        store = _PromptingStore()
        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store, "claude,opencode")
            change = (
                "consume",
                "inputs",
                "set",
                GITHUB,
                "github-org=platform",
                "--harness",
                "claude",
            )

            code, out, _ = _run(env, store, *change)

            self.assertEqual(code, 0, out)
            review = json.loads(out)
            self.assertFalse(review["finalized"])
            self.assertEqual((review["from"], review["to"]), ("acme", "platform"))
            self.assertIn("github-org=acme", _config(env, "claude"))

            code, out, _ = _run(env, store, *change, "--yes", "--expect", "sha256:" + "0" * 64)
            self.assertNotEqual(code, 0, out)
            self.assertIn("github-org=acme", _config(env, "claude"))

            code, out, _ = _run(env, store, *change, "--yes", "--expect", review["review_digest"])

            self.assertEqual(code, 0, out)
            self.assertTrue(json.loads(out)["finalized"])
            self.assertIn("github-org=platform", _config(env, "claude"))
            self.assertIn("github-org=acme", _config(env, "opencode"))

    def test_set_goes_through_the_service_credentials_and_variables_uses(self) -> None:
        store = _PromptingStore()
        handled: list[ConsumerActionKind] = []
        original = LocalConsumerActions.handle

        def recording(actions, command):
            handled.append(command.action)
            return original(actions, command)

        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store)
            with mock.patch.object(LocalConsumerActions, "handle", recording):
                code, out, _ = _run(
                    env, store, "consume", "inputs", "set", GITHUB, "github-org=x", "--yes"
                )
                self.assertEqual(code, 0, out)
                code, out, _ = _run(
                    env,
                    store,
                    "consume",
                    "inputs",
                    "set-credential",
                    GITHUB,
                    "github-token",
                    "--yes",
                    terminal=True,
                )
                self.assertEqual(code, 0, out)

        self.assertEqual(
            handled,
            [
                ConsumerActionKind.CONFIGURE,
                ConsumerActionKind.CONFIGURE,
                ConsumerActionKind.CREDENTIAL_REPLACE,
                ConsumerActionKind.CREDENTIAL_REPLACE,
            ],
        )

    def test_a_credential_is_never_an_argument_and_its_value_is_not_repeated(self) -> None:
        store = _PromptingStore()
        token = access_token()
        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store)

            for as_json in (True, False):
                with self.subTest(as_json=as_json):
                    code, out, err = _run(
                        env,
                        store,
                        "consume",
                        "inputs",
                        "set",
                        GITHUB,
                        f"github-token={token}",
                        "--yes",
                        as_json=as_json,
                    )

                    self.assertNotEqual(code, 0)
                    self.assertIn("set-credential", out)
                    self.assertNotIn(token, out + err)
            self.assertEqual(store.prompted, [])
            self.assertEqual(list(store.stored.values()), [SKIPPED_INPUT])

    def test_an_ambiguous_or_unknown_installation_is_refused_with_each_match(self) -> None:
        store = _PromptingStore()
        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store, "claude,opencode")

            code, out, _ = _run(env, store, "consume", "inputs", "set", GITHUB, "github-org=x")
            self.assertNotEqual(code, 0)
            message = json.dumps(json.loads(out)["diagnostics"])
            self.assertIn("--harness claude", message)
            self.assertIn("--harness opencode", message)

            code, out, _ = _run(
                env, store, "consume", "inputs", "set", "company/mcp/git", "github-org=x"
            )
            self.assertNotEqual(code, 0)
            self.assertIn("company/mcp/git", out)
            self.assertIn("github-org=acme", _config(env, "claude"))


class InputsSetCredentialTest(unittest.TestCase):
    def test_the_store_prompts_and_the_value_never_passes_through_aart(self) -> None:
        store = _PromptingStore()
        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store)
            setting = ("consume", "inputs", "set-credential", GITHUB, "github-token")

            code, out, _ = _run(env, store, *setting)

            self.assertEqual(code, 0, out)
            review = json.loads(out)
            self.assertFalse(review["finalized"])
            self.assertEqual(review["intent"], "replace")
            self.assertIn(f"--yes --expect {review['review_digest']}", review["command"])
            self.assertEqual(store.prompted, [])

            code, out, err = _run(
                env, store, *setting, "--yes", "--expect", review["review_digest"], terminal=True
            )

            self.assertEqual(code, 0, out)
            self.assertTrue(json.loads(out)["finalized"])
            [(_, replacing)] = store.prompted
            self.assertTrue(replacing)
            # Only the install's Set later ever handed the store a value.
            self.assertEqual(store.carried, [SKIPPED_INPUT])
            # The briefing is on stderr, so stdout stays the command's document.
            self.assertIn("GitHub token — needed by", err)
            _, listed, _ = _run(env, store, "consume", "inputs", "list")
            [credential] = json.loads(listed)["installations"][0]["credentials"]
            self.assertFalse(credential["placeholder"])
            self.assertNotIn(store.typed, out + err + listed)
            leaked = [
                path
                for path in _files(env.root)
                if store.typed in path.read_text(encoding="utf-8", errors="replace")
            ]
            self.assertEqual(leaked, [])

    def test_without_a_terminal_nothing_changes_and_the_command_is_given(self) -> None:
        store = _PromptingStore()
        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store)

            code, out, _ = _run(
                env, store, "consume", "inputs", "set-credential", GITHUB, "github-token", "--yes"
            )

            self.assertNotEqual(code, 0)
            payload = json.loads(out)
            self.assertFalse(payload["finalized"])
            self.assertIn("terminal", json.dumps(payload["diagnostics"]))
            self.assertIn(
                f"aart-cli consume inputs set-credential {GITHUB} github-token", payload["command"]
            )
            self.assertEqual(store.prompted, [])
            self.assertEqual(list(store.stored.values()), [SKIPPED_INPUT])

    def test_an_ordinary_input_or_a_value_is_refused(self) -> None:
        store = _PromptingStore()
        token = access_token()
        with _environment(authored=AUTHORED_MCP) as env:
            _install(env, store)

            for given_input, named in (("github-org", "inputs set"), (f"github-token={token}", "")):
                with self.subTest(given_input=given_input.split("=")[0]):
                    code, out, err = _run(
                        env,
                        store,
                        "consume",
                        "inputs",
                        "set-credential",
                        GITHUB,
                        given_input,
                        "--yes",
                        terminal=True,
                    )

                    self.assertNotEqual(code, 0)
                    self.assertIn(named, out)
                    self.assertNotIn(token, out + err)
            self.assertEqual(store.prompted, [])


#: Few letters, so selectors and installations collide often and one name is often a prefix of
#: another (`a/mcp/a` beside `a/mcp/ab`), which is the confusion selection must not make.
_PART = st.text(alphabet="ab-", min_size=1, max_size=3).filter(
    lambda text: text[0] != "-" and text[-1] != "-"
)


@st.composite
def _installations(draw) -> tuple[str, ...]:
    keys = draw(
        st.lists(
            st.tuples(
                _PART,
                _PART,
                st.sampled_from(("claude", "opencode", "tabnine")),
                st.sampled_from(("project", "user")),
            ),
            max_size=6,
            unique=True,
        )
    )
    return tuple(
        compose_installation_key(f"{alias}/mcp/{name}@1.0.0", harness, scope, f"/{scope}")
        for alias, name, harness, scope in keys
    )


class InstallationSelectionPropertyTest(unittest.TestCase):
    @given(
        _installations(),
        _PART,
        _PART,
        st.sampled_from(("", "claude", "opencode")),
        st.sampled_from(("", "project", "user")),
        st.booleans(),
    )
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_a_selector_picks_exactly_the_installations_it_names(
        self, keys, alias, name, harness, scope, versioned
    ) -> None:
        coordinate = f"{alias}/mcp/{name}" + ("@1.0.0" if versioned else "")
        chosen = select_installations(keys, InstallationSelector(coordinate, harness, scope))

        expected = tuple(
            key
            for key in keys
            if key.split("#")[0] in (coordinate, f"{coordinate}@1.0.0")
            and harness in ("", key.split("#")[1])
            and scope in ("", key.split("#")[2])
        )
        self.assertEqual(chosen, expected)


if __name__ == "__main__":
    unittest.main()
