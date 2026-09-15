"""What an author declares about runtime inputs and dependencies, and what survives compilation.

§91 keeps confidential inputs and ordinary configuration apart; §107 keeps runtime requirements,
package requirements and runtime inputs apart from each other; §108 says AART points at an existing
Python dependency descriptor rather than inventing a language for one. All three describe things a
manifest declares, and until now the manifest parser accepted `inputs` and dropped it -- an author
could declare a secret and get an artifact that asks for nothing.

These are the declarations, the rules that make them safe, and the proof that they reach the
compiled artifact rather than stopping at the parser.
"""

from __future__ import annotations

import json
import unittest

from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.inputs import (
    CliArgumentBinding,
    ConfigInput,
    EnvironmentBinding,
    SecretInput,
)
from agent_artifacts.domain.python_runtime import PyProjectSpec, RequirementsFile
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import (
    compile_author_snapshot,
    discover_author_manifests,
    parse_author_manifest,
)
from tests.authoring_compiler_test import _file, _snapshot

TOKEN = {
    "id": "github-token",
    "kind": "secret",
    "required": True,
    "inject": {"type": "environment", "variable": "GITHUB_TOKEN"},
    "help": {
        "label": "GitHub token",
        "description": "Personal access token used to authenticate to GitHub.",
        "format_hint": "ghp_...",
        "obtain_from": {
            "label": "Create a GitHub token",
            "url": "https://github.company/settings/tokens",
        },
    },
}

HOST = {
    "id": "github-host",
    "kind": "config",
    "required": True,
    "default": "https://github.com",
    "inject": {"type": "cli-argument", "argument": "--github-host"},
    "validation": {"type": "url", "allowed_hosts": ["github.com"]},
    "help": {"label": "GitHub URL", "example": "https://github.company"},
}


def _document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "github-mcp", "kind": "mcp", "version": "1.4.0"},
        "payload": {"include": ["server.py", "requirements.txt"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
        "inputs": [TOKEN, HOST],
        "python": {"dependencies": {"type": "requirements", "path": "requirements.txt"}},
    }
    document.update(overrides)
    # A `None` override removes the key rather than declaring a null, so a fixture can describe an
    # artifact that says nothing about a runtime as easily as one that says something wrong.
    return {key: value for key, value in document.items() if value is not None}


def _manifest(**overrides: object):
    entry = _file("github/aart.json", json.dumps(_document(**overrides), sort_keys=True))
    discovered = discover_author_manifests(_snapshot(entry))
    assert isinstance(discovered, Ok), getattr(discovered, "diagnostics", ())
    return discovered.value[0]


def _parsed(**overrides: object):
    return parse_author_manifest(_manifest(**overrides))


def _reason(result) -> str:
    return result.diagnostics[0].message


class DeclaredInputTest(unittest.TestCase):
    def test_a_declared_secret_is_a_secret_input_bound_the_way_the_manifest_says(self) -> None:
        parsed = _parsed()

        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        secret = parsed.value.inputs[0]
        self.assertIsInstance(secret, SecretInput)
        self.assertEqual(str(secret.id), "github-token")
        self.assertEqual(secret.binding, EnvironmentBinding("GITHUB_TOKEN"))
        self.assertTrue(secret.required)

    def test_a_declared_config_input_carries_its_default_validation_and_guidance(self) -> None:
        config = _parsed().value.inputs[1]

        assert isinstance(config, ConfigInput)
        self.assertEqual(config.binding, CliArgumentBinding("--github-host"))
        self.assertEqual(config.default, "https://github.com")
        self.assertEqual(config.validation.kind, "url")
        self.assertEqual(config.validation.allowed_hosts, ("github.com",))
        self.assertEqual(config.guidance.example, "https://github.company")

    def test_the_guidance_a_secret_carries_says_where_to_get_one(self) -> None:
        secret = _parsed().value.inputs[0]

        assert isinstance(secret, SecretInput)
        self.assertEqual(secret.guidance.format_hint, "ghp_...")
        self.assertEqual(secret.guidance.obtain_from.label, "Create a GitHub token")

    def test_a_secret_cannot_declare_a_value_a_default_or_an_example(self) -> None:
        """§91: a secret input has no value field, and §156 forbids a plausible example.

        A manifest is reviewed by people, published, and read by every consumer. A field that could
        hold a credential is a field that eventually holds one.
        """

        for field, value in (
            ("value", "ghp_realtoken"),
            ("default", "ghp_realtoken"),
            ("example", "ghp_realtoken"),
        ):
            with self.subTest(field=field):
                refused = _parsed(inputs=[{**TOKEN, field: value}])

                self.assertIsInstance(refused, Err)
                self.assertIn(field, _reason(refused))

    def test_a_secret_whose_help_shows_an_example_credential_is_refused(self) -> None:
        refused = _parsed(
            inputs=[{**TOKEN, "help": {"label": "GitHub token", "example": "ghp_abc123"}}]
        )

        self.assertIsInstance(refused, Err)
        self.assertIn("example", _reason(refused))

    def test_two_inputs_cannot_claim_the_same_id(self) -> None:
        refused = _parsed(inputs=[TOKEN, {**HOST, "id": "github-token"}])

        self.assertIsInstance(refused, Err)
        self.assertIn("github-token", _reason(refused))

    def test_an_input_kind_this_build_does_not_know_is_refused_rather_than_guessed(self) -> None:
        refused = _parsed(inputs=[{**HOST, "kind": "variable"}])

        self.assertIsInstance(refused, Err)
        self.assertIn("secret", _reason(refused))

    def test_an_injection_this_build_cannot_deliver_is_refused(self) -> None:
        refused = _parsed(inputs=[{**HOST, "inject": {"type": "registry-key", "key": "x"}}])

        self.assertIsInstance(refused, Err)
        self.assertIn("registry-key", _reason(refused))

    def test_an_environment_variable_that_is_not_one_is_refused_by_the_binding_itself(self) -> None:
        refused = _parsed(
            inputs=[{**TOKEN, "inject": {"type": "environment", "variable": "github token"}}]
        )

        self.assertIsInstance(refused, Err)
        self.assertIn("upper-case", _reason(refused))


class DeclaredDependencyTest(unittest.TestCase):
    def test_a_requirements_descriptor_is_pointed_at_rather_than_restated(self) -> None:
        parsed = _parsed()

        self.assertEqual(parsed.value.dependencies, RequirementsFile("requirements.txt"))

    def test_a_locked_project_names_both_the_project_and_the_lock(self) -> None:
        parsed = _parsed(
            python={
                "dependencies": {
                    "type": "uv",
                    "pyproject": "pyproject.toml",
                    "lock": "uv.lock",
                }
            },
            payload={"include": ["server.py", "pyproject.toml", "uv.lock"]},
        )

        self.assertEqual(
            parsed.value.dependencies, PyProjectSpec("pyproject.toml", "uv.lock", "uv")
        )

    def test_a_bare_project_with_no_lock_is_installed_loose(self) -> None:
        parsed = _parsed(
            python={"dependencies": {"type": "pyproject", "pyproject": "pyproject.toml"}},
            payload={"include": ["server.py", "pyproject.toml"]},
        )

        self.assertEqual(parsed.value.dependencies, PyProjectSpec("pyproject.toml"))

    def test_a_resolver_no_installer_here_can_read_is_refused_rather_than_approximated(
        self,
    ) -> None:
        """A poetry lock is a real descriptor with no backend behind it in this build.

        Accepting it and installing the loose project instead would silently install versions
        nobody resolved, which is the one thing a lock exists to prevent.
        """

        refused = _parsed(
            python={
                "dependencies": {
                    "type": "poetry",
                    "pyproject": "pyproject.toml",
                    "lock": "poetry.lock",
                }
            }
        )

        self.assertIsInstance(refused, Err)
        self.assertIn("poetry", _reason(refused))

    def test_a_descriptor_outside_the_payload_is_refused(self) -> None:
        """§108: the descriptor must ship in the canonical payload.

        An artifact whose dependency list lives only in the source repository is installable today
        and uninstallable tomorrow.
        """

        compiled = compile_author_snapshot(
            _snapshot(
                _file("github/aart.json", json.dumps(_document(), sort_keys=True)),
                _file("github/server.py", "print()\n"),
            ),
            source_alias=SourceAlias("public"),
            source="https://example.test/github.git",
            revision="a" * 40,
        )

        self.assertIsInstance(compiled, Err)
        self.assertIn("requirements.txt", _reason(compiled))


class CompiledDeclarationTest(unittest.TestCase):
    def compile(self, **overrides: object):
        compiled = compile_author_snapshot(
            _snapshot(
                _file("github/aart.json", json.dumps(_document(**overrides), sort_keys=True)),
                _file("github/server.py", "print()\n"),
                _file("github/requirements.txt", "mcp==1.0.0\n"),
            ),
            source_alias=SourceAlias("public"),
            source="https://example.test/github.git",
            revision="a" * 40,
        )
        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        return compiled.value[0]

    def authoring(self, artifact) -> dict:
        for entry in artifact.canonical_entries:
            if str(entry.path) == "artifact.json":
                return json.loads(entry.content)["aart.authoring"]
        raise AssertionError("the compiled artifact has no manifest")

    def test_what_the_author_declared_reaches_the_compiled_artifact(self) -> None:
        """Declaration order survives too: it is the order somebody is asked for these values."""

        declared = self.authoring(self.compile())

        self.assertEqual(
            [item["id"] for item in declared["inputs"]], ["github-token", "github-host"]
        )
        self.assertEqual(declared["python"]["dependencies"]["path"], "requirements.txt")

    def test_changing_an_input_changes_the_artifact_it_identifies(self) -> None:
        """Inputs are part of what the artifact is, so they belong in its input digest.

        Two artifacts that ask for different things are not the same artifact at the same version,
        and a digest that ignored the difference would let one be substituted for the other.
        """

        before = self.compile()
        after = self.compile(
            inputs=[TOKEN, {**HOST, "inject": {"type": "cli-argument", "argument": "--host"}}]
        )

        self.assertNotEqual(before.input_digest, after.input_digest)

    def test_no_declaration_reaches_the_artifact_carrying_a_credential_shape(self) -> None:
        declared = json.dumps(self.authoring(self.compile()), sort_keys=True)

        self.assertIn("github-token", declared)
        self.assertNotIn("ghp_abc", declared)


if __name__ == "__main__":
    unittest.main()
