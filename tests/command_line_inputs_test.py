"""§169.4, §186, D-468: an installation's inputs are answered on the command line, per artifact.

An agent installing an MCP server with no terminal could not answer a required input: `consume
install` prepared with no sources and refused. §169.4 asks for non-interactive channels that name
the installation target, never a generic input id. The flags name the artifact with its Registry
alias (`ALIAS/KIND/NAME:ID`), and §172.4 copies that one answer into each of the artifact's new
installations, as the TUI's 07 does.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.command_line_inputs import (
    CommandLineInput,
    declared_defaults,
    missing_input_flags,
    parse_command_line_input,
    resolve_command_line_inputs,
    secret_references,
    secret_variables,
)
from aart_cli.application.installation_inputs import ArtifactAnswer, InstallationInputField
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactIdentity, InputId, SourceAlias
from aart_cli.domain.inputs import (
    BoundInput,
    BoundInputs,
    ConfigInput,
    EnvironmentBinding,
    SecretInput,
    SecretProviderReference,
)
from aart_cli.domain.installation_owner import InstallationOwner, credential_address
from aart_cli.domain.result import Err, Ok
from tests.credential_fixtures import assignment

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
            fields,
            (_item("company/mcp/github", "org", "acme"),),
            (_item("company/mcp/jira", "token", "JIRA_TOKEN"),),
        )

        assert isinstance(resolved, Ok), resolved
        self.assertEqual(
            resolved.value.answers, (ArtifactAnswer(COMPANY, GITHUB, InputId("org"), "acme"),)
        )
        self.assertEqual(
            resolved.value.secrets, (_item("company/mcp/jira", "token", "JIRA_TOKEN"),)
        )

    def test_every_mistake_is_refused_by_name_and_no_value_is_shown(self) -> None:
        fields = _fields(_owner())
        cases = (
            ((_item("company/mcp/jira", "org", "s3cret"),), (), "company/mcp/github"),
            ((_item("company/mcp/github", "host", "s3cret"),), (), "org, token"),
            ((_item("company/mcp/github", "token", "s3cret"),), (), "--secret-env"),
            ((), (_item("company/mcp/github", "org", "ORG_VAR"),), "--input"),
            (
                (
                    _item("company/mcp/github", "org", "s3cret"),
                    _item("company/mcp/github", "org", "s3cret"),
                ),
                (),
                "twice",
            ),
        )
        for values, secrets, named in cases:
            with self.subTest(named=named):
                message = _messages(resolve_command_line_inputs(fields, values, secrets))

                self.assertIn(named, message)
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
    def test_each_installation_gets_its_own_reference(self) -> None:
        claude, opencode = _owner(harness="claude"), _owner(harness="opencode")
        fields = _fields(claude, opencode, _owner(JIRA))

        named = secret_references(
            fields,
            (),
            (_item("company/mcp/github", "token", "GH"),),
            set_later=False,
            provider=PROVIDER,
        )
        later = secret_references(
            fields,
            tuple(field for field in fields if field.owner.artifact == JIRA),
            (),
            set_later=True,
            provider=PROVIDER,
        )

        self.assertEqual([item.owner for item in named], [claude, opencode])
        self.assertEqual(len({item.source.provider for item in named}), 2)  # type: ignore[union-attr]
        self.assertEqual([item.owner.artifact for item in later], [JIRA])
        self.assertEqual(secret_references(fields, (), (), set_later=False, provider=PROVIDER), ())

    def test_a_variable_reaches_every_reference_of_its_artifact_and_no_other(self) -> None:
        claude, opencode, jira = _owner(harness="claude"), _owner(harness="opencode"), _owner(JIRA)

        def bound(owner):
            return (
                owner,
                BoundInputs(
                    (
                        BoundInput(
                            TOKEN,
                            SecretProviderReference(
                                TOKEN.id, credential_address(owner, TOKEN.id, provider=PROVIDER)
                            ),
                        ),
                    )
                ),
            )

        variables = secret_variables(
            (bound(claude), bound(opencode), bound(jira)),
            (_item("company/mcp/github", "token", "GH"),),
        )

        self.assertEqual(sorted(variables.values()), ["GH", "GH"])
        self.assertEqual(len(variables), 2)


class MissingFlagsTest(unittest.TestCase):
    def test_the_refusal_prints_one_flag_per_artifact_and_input(self) -> None:
        fields = _fields(_owner(harness="claude"), _owner(harness="opencode"))

        self.assertEqual(
            missing_input_flags(fields),
            (
                "--input company/mcp/github:org=VALUE",
                "--secret-env " + assignment("company/mcp/github:token", "ENVIRONMENT_VARIABLE"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
