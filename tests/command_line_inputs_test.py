"""§169.4, §186, §201, D-468, D-486: an installation's inputs are answered on the command line.

An agent installing an MCP server with no terminal could not answer a required input: `consume
install` prepared with no sources and refused. §169.4 asks for non-interactive channels that name
the installation target, never a generic input id. The flags name the artifact with its Registry
alias (`ALIAS/KIND/NAME:ID`), and §172.4 copies that one answer into each of the artifact's new
installations, as the TUI's 07 does. A credential is never one of those answers: it is pointed at
its own provider item, which the credential store's prompt fills (§201).
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.command_line_inputs import (
    CommandLineAnswers,
    CommandLineInput,
    declared_defaults,
    missing_input_flags,
    parse_command_line_input,
    resolve_command_line_inputs,
    secret_references,
)
from aart_cli.application.installation_inputs import ArtifactAnswer, InstallationInputField
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactIdentity, InputId, SourceAlias
from aart_cli.domain.inputs import ConfigInput, EnvironmentBinding, SecretInput
from aart_cli.domain.installation_owner import InstallationOwner
from aart_cli.domain.result import Err, Ok

ORG = ConfigInput(InputId("org"), EnvironmentBinding("ORG"))
TOKEN = SecretInput(InputId("token"), EnvironmentBinding("TOKEN"))
GITHUB = ArtifactIdentity("mcp", "github")
JIRA = ArtifactIdentity("mcp", "jira")
COMPANY = SourceAlias("company")
PROVIDER = "macos-keychain"


def _owner(artifact=GITHUB, harness="claude", source=COMPANY):
    return InstallationOwner(source, artifact, Scope.PROJECT, "/root", harness)


def _fields(*owners):
    return tuple(
        InstallationInputField(owner, declared) for owner in owners for declared in (ORG, TOKEN)
    )


def _item(artifact: str, identifier: str, value: str) -> CommandLineInput:
    return CommandLineInput(artifact, InputId(identifier), value)


def _messages(result) -> str:
    assert isinstance(result, Err), result
    return " ".join(
        part
        for diagnostic in result.diagnostics
        for part in (diagnostic.message, *diagnostic.remediation)
    )


_SLUG = st.from_regex(r"[a-z][a-z0-9]{0,6}(-[a-z0-9]{1,4})?", fullmatch=True)


class ParseTest(unittest.TestCase):
    @given(_SLUG, _SLUG, _SLUG, _SLUG, st.text(alphabet=st.characters(exclude_categories=("Cs",))))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_the_value_is_everything_after_the_first_equals(
        self, alias, kind, name, identifier, value
    ) -> None:
        parsed = parse_command_line_input(
            f"{alias}/{kind}/{name}:{identifier}={value}", flag="--input"
        )

        self.assertEqual(parsed, Ok(_item(f"{alias}/{kind}/{name}", identifier, value)))

    def test_a_malformed_flag_says_its_shape_and_never_echoes_a_value(self) -> None:
        for text in ("company/mcp/github=hunter2", "org=hunter2", ":org=hunter2", "x:=hunter2"):
            with self.subTest(text=text):
                message = _messages(parse_command_line_input(text, flag="--input"))

                self.assertIn("--input ALIAS/KIND/NAME:INPUT=VALUE", message)
                self.assertNotIn("hunter2", message)
        message = _messages(parse_command_line_input("company/mcp/github:org", flag="--input"))
        self.assertIn("--input", message)


class ResolveTest(unittest.TestCase):
    def test_an_answer_belongs_to_its_artifact_on_every_harness(self) -> None:
        fields = _fields(_owner(harness="claude"), _owner(harness="opencode"), _owner(JIRA))

        resolved = resolve_command_line_inputs(
            fields, (_item("company/mcp/github", "org", "acme"),)
        )

        self.assertEqual(
            resolved,
            Ok(CommandLineAnswers((ArtifactAnswer(COMPANY, GITHUB, InputId("org"), "acme"),))),
        )

    def test_every_mistake_is_refused_by_name_and_no_value_is_shown(self) -> None:
        fields = _fields(_owner())
        cases = (
            ((_item("company/mcp/jira", "org", "s3cret"),), "company/mcp/github"),
            ((_item("company/mcp/github", "host", "s3cret"),), "org, token"),
            ((_item("company/mcp/github", "token", "s3cret"),), "never an argument"),
            (
                (
                    _item("company/mcp/github", "org", "s3cret"),
                    _item("company/mcp/github", "org", "s3cret"),
                ),
                "twice",
            ),
        )
        for values, named in cases:
            with self.subTest(named=named):
                message = _messages(resolve_command_line_inputs(fields, values))

                self.assertIn(named, message)
                self.assertNotIn("s3cret", message)

    def test_every_mistake_is_said_at_once_and_only_a_credential_sends_you_to_the_store(
        self,
    ) -> None:
        message = _messages(
            resolve_command_line_inputs(
                _fields(_owner()),
                (
                    _item("company/mcp/jira", "org", "x"),
                    _item("company/mcp/wiki", "org", "x"),
                    _item("company/mcp/github", "host", "x"),
                ),
            )
        )

        for named in ("company/mcp/jira", "company/mcp/wiki", "declares no input host"):
            self.assertIn(named, message)
        self.assertNotIn("set-credential", message)

    def test_a_credential_given_as_an_argument_is_sent_to_the_store_instead(self) -> None:
        message = _messages(
            resolve_command_line_inputs(
                _fields(_owner()), (_item("company/mcp/github", "token", "s3cret"),)
            )
        )

        self.assertIn("credential store asks for it", message)
        self.assertIn("consume inputs set-credential", message)
        self.assertNotIn("s3cret", message)


class DefaultTest(unittest.TestCase):
    def test_a_declared_default_stands_unless_a_flag_replaces_it(self) -> None:
        with_default = ConfigInput(InputId("org"), EnvironmentBinding("ORG"), default="acme")
        fields = tuple(
            InstallationInputField(owner, declared)
            for owner in (_owner(harness="claude"), _owner(harness="opencode"), _owner(JIRA))
            for declared in (with_default, TOKEN)
        )
        given_jira = (ArtifactAnswer(COMPANY, JIRA, InputId("org"), "widgets"),)

        self.assertEqual(
            declared_defaults(fields, given_jira),
            (ArtifactAnswer(COMPANY, GITHUB, InputId("org"), "acme"),),
        )
        self.assertEqual(declared_defaults(_fields(_owner()), ()), ())


class SecretTest(unittest.TestCase):
    def test_each_installation_gets_its_own_reference_and_ordinary_inputs_none(self) -> None:
        claude, opencode, jira = _owner(harness="claude"), _owner(harness="opencode"), _owner(JIRA)

        references = secret_references(_fields(claude, opencode, jira), provider=PROVIDER)

        self.assertEqual([item.owner for item in references], [claude, opencode, jira])
        self.assertEqual({item.source.input for item in references}, {TOKEN.id})  # type: ignore[union-attr]
        self.assertEqual(len({item.source.provider for item in references}), 3)  # type: ignore[union-attr]
        only_ordinary = (InstallationInputField(claude, ORG),)
        self.assertEqual(secret_references(only_ordinary, provider=PROVIDER), ())


class MissingFlagsTest(unittest.TestCase):
    def test_the_refusal_prints_one_flag_per_artifact_and_ordinary_input(self) -> None:
        fields = _fields(_owner(harness="claude"), _owner(harness="opencode"))

        # The credential has no flag: the credential store asks for it.
        self.assertEqual(missing_input_flags(fields), ("--input company/mcp/github:org=VALUE",))


if __name__ == "__main__":
    unittest.main()
