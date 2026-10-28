"""The shared Credentials and variables module the TUI and `consume inputs` both read (§198, D-483).

What an installation key names, which ordinary inputs an installation has and what each holds, and
what a credential's state is in words, decided once. These hold the module on its own, beside the
end-to-end tests that drive it through the CLI and the screens.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import ConsumerActionKind
from aart_cli.application.consumer_views import ConfigurationFileView, CredentialRecordView
from aart_cli.application.credentials_and_variables import (
    PLACEHOLDER_STATE,
    configuration_identifiers,
    credential_setting,
    credential_state,
    installation_inputs,
    installation_parts,
)
from aart_cli.domain.installation_owner import compose_installation_key

_WORD = st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=1, max_size=12)
KEY = compose_installation_key("public/mcp/github@1.6.0", "claude", "project", "/work/shop")


def _file(values=(), inputs=(), path="/work/shop/.claude/github.json", state="matched"):
    return ConfigurationFileView(
        "public/mcp/github@1.6.0", "claude", path, state, values, inputs=inputs, installation=KEY
    )


def _credential(health="present", actions=("verify", "replace"), placeholder=False):
    return CredentialRecordView(
        "keychain:aart-cli/github-token",
        "github-token",
        "macos-keychain",
        "aart-cli",
        "github-token",
        "available",
        health,
        "",
        (KEY,),
        actions,
        placeholder,
    )


class InstallationKeyTest(unittest.TestCase):
    @given(
        coordinate=_WORD.map(lambda name: f"public/mcp/{name}@1.0.0"),
        label=_WORD,
        scope=st.sampled_from(("user", "project")),
        root=st.text(alphabet="/abc#@ -", min_size=1, max_size=24),
    )
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_a_key_splits_back_into_its_parts_whatever_the_root_holds(
        self, coordinate, label, scope, root
    ) -> None:
        key = compose_installation_key(coordinate, label, scope, root)

        self.assertEqual(installation_parts(key), (coordinate, label, scope, root))

    def test_a_key_with_no_owner_is_a_bare_coordinate(self) -> None:
        self.assertEqual(
            installation_parts("public/mcp/github@1.6.0"), ("public/mcp/github@1.6.0", "", "", "")
        )


class InstallationInputsTest(unittest.TestCase):
    def test_an_input_the_file_holds_but_does_not_declare_is_still_listed(self) -> None:
        held = _file(values=(("github-org", "platform"),))

        self.assertEqual(configuration_identifiers((held,)), ["github-org"])

    def test_each_value_carries_its_file_its_state_and_the_documentation(self) -> None:
        inputs = installation_inputs(
            KEY,
            (_file(values=(("github-org", "platform"),), inputs=("github-org", "api-url")),),
            (),
            "https://docs.example.com/github",
        )

        self.assertEqual(
            [(item.input, item.value, item.path, item.state) for item in inputs.configuration],
            [
                ("api-url", None, "/work/shop/.claude/github.json", "matched"),
                ("github-org", "platform", "/work/shop/.claude/github.json", "matched"),
            ],
        )
        self.assertEqual(inputs.documentation, "https://docs.example.com/github")
        self.assertEqual(installation_inputs(KEY, (), ()).documentation, "")

    def test_a_value_is_read_only_from_a_file_that_declares_or_holds_it(self) -> None:
        declaring = _file(inputs=("api-url",))
        other = _file(values=(("github-org", "platform"),), path="/work/shop/other.json")

        inputs = installation_inputs(KEY, (declaring, other), ())

        self.assertEqual(
            [(item.input, item.path) for item in inputs.configuration],
            [("api-url", declaring.path), ("github-org", other.path)],
        )


class CredentialWordsTest(unittest.TestCase):
    def test_a_state_is_said_in_words_and_never_as_a_value(self) -> None:
        for view, expected in (
            (_credential(), "Configured securely"),
            (_credential(placeholder=True), PLACEHOLDER_STATE),
            (_credential("absent", ("verify", "set")), "Absent"),
            (_credential("invalid"), "Not configured"),
            (_credential("unknown", ("verify",)), "Unknown"),
        ):
            with self.subTest(health=view.health, placeholder=view.placeholder):
                self.assertEqual(credential_state(view), expected)

    def test_setting_stores_a_new_item_replaces_one_there_and_waits_on_an_unknown(self) -> None:
        self.assertEqual(
            credential_setting(_credential("absent", ("verify", "set"))),
            ("set", ConsumerActionKind.CREDENTIAL_SET),
        )
        self.assertEqual(
            credential_setting(_credential()), ("replace", ConsumerActionKind.CREDENTIAL_REPLACE)
        )
        self.assertIsNone(credential_setting(_credential("unknown", ("verify",))))
        self.assertIsNone(credential_setting(_credential("unknown", ())))


if __name__ == "__main__":
    unittest.main()
