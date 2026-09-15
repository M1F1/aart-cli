"""What a stored package still says about installing itself.

A manifest declares a runtime, a dependency descriptor and the inputs an artifact is started with.
Compilation carries those declarations into `artifact.json` as the `aart.authoring` extension, and
an install has to read them back -- from the package on disk, not from the author's repository,
which the machine doing the installing has never seen.

The load-bearing claim here is that the two directions agree, and they agree because they are the
same parser. A second grammar for reading what the first one wrote is the kind of thing that works
until an author uses a field the reader forgot.
"""

from __future__ import annotations

import json
import unittest
from typing import cast

from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.inputs import ConfigInput, SecretInput
from agent_artifacts.domain.install_description import (
    InstallDescription,
    install_description_to_data,
)
from agent_artifacts.domain.launch import LaunchContract, Transport
from agent_artifacts.domain.python_runtime import PyProjectSpec, RequirementsFile
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import (
    compile_author_snapshot,
    describe_installation,
    package_payload_root,
    read_install_description,
    read_package_description,
)
from agent_artifacts.protocol.native_schema import parse_artifact_manifest
from tests.authoring_compiler_test import _file, _snapshot
from tests.authoring_inputs_test import _document, _parsed


def _compiled(**overrides: object):
    entry = _file("github/aart.json", json.dumps(_document(**overrides), sort_keys=True))
    payload = (
        _file("github/server.py", "print('hi')\n"),
        _file("github/requirements.txt", "httpx==0.27.0\n"),
        _file("github/pyproject.toml", "[project]\nname='github-mcp'\n"),
        _file("github/uv.lock", "version = 1\n"),
        _file("github/SKILL.md", "---\nname: review\n---\n"),
    )
    compiled = compile_author_snapshot(
        _snapshot(entry, *payload),
        source_alias=SourceAlias("company"),
        source="https://github.company/company/registry.git",
        revision="a" * 40,
    )
    assert isinstance(compiled, Ok), getattr(compiled, "diagnostics", ())
    return compiled.value[0]


def _stored_description(**overrides: object):
    """Read the description the way a machine installing the artifact would: from the bytes."""

    compiled = _compiled(**overrides)
    manifest_entry = next(
        entry for entry in compiled.canonical_entries if str(entry.path) == "artifact.json"
    )
    parsed = parse_artifact_manifest(manifest_entry.content)
    assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
    extension = dict(parsed.value.extensions)["aart.authoring"]
    return read_install_description(extension, path="artifact.json")


def _without_authoring(entries):
    """The same tree, as some other importer that never wrote an authoring intent would leave it."""

    from agent_artifacts.protocol.json import JsonObject, canonical_json_bytes, parse_json
    from agent_artifacts.protocol.native_tree import SnapshotEntry

    rewritten = []
    for entry in entries:
        if str(entry.path) != "artifact.json":
            rewritten.append(entry)
            continue
        parsed = parse_json(entry.content)
        assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
        kept = JsonObject(
            tuple(item for item in parsed.value.entries if item[0] != "aart.authoring")
        )
        rewritten.append(
            SnapshotEntry(entry.path, entry.kind, canonical_json_bytes(kept), entry.executable)
        )
    return tuple(rewritten)


def _reason(result) -> str:
    return result.diagnostics[0].message


def _authored_description(**overrides: object):
    parsed = _parsed(**overrides)
    assert isinstance(parsed, Ok), getattr(parsed, "diagnostics", ())
    return describe_installation(parsed.value)


class DescribedInstallationTest(unittest.TestCase):
    def test_a_manifest_describes_the_installation_it_asks_for(self) -> None:
        description = _authored_description()

        self.assertEqual(description.contract, LaunchContract("server.py", Transport.STDIO))
        self.assertEqual(description.runtime, "python")
        self.assertEqual(description.runtime_version, ">=3.11")
        self.assertEqual(description.dependencies, RequirementsFile("requirements.txt"))
        self.assertEqual(
            [str(item.id) for item in description.inputs], ["github-token", "github-host"]
        )
        self.assertIsInstance(description.inputs[0], SecretInput)
        self.assertIsInstance(description.inputs[1], ConfigInput)

    def test_declared_launch_arguments_are_part_of_the_contract(self) -> None:
        description = _authored_description(
            launch={"type": "python", "entrypoint": "server.py", "arguments": ["--strict"]}
        )

        assert description is not None
        self.assertEqual(description.contract, LaunchContract("server.py", arguments=("--strict",)))

    def test_a_skill_with_nothing_to_start_describes_nothing_to_start(self) -> None:
        description = _authored_description(
            schema="aart.dev/skill/v1",
            artifact={"name": "review", "kind": "skill", "version": "1.0.0"},
            payload={"include": ["SKILL.md"]},
            transport=None,
            runtime=None,
            launch=None,
            inputs=None,
            python=None,
        )

        self.assertEqual(description, InstallDescription())


class StoredDescriptionTest(unittest.TestCase):
    def test_what_the_author_declared_is_what_the_package_still_says(self) -> None:
        stored = _stored_description()

        self.assertIsInstance(stored, Ok)
        self.assertEqual(stored.value, _authored_description())

    def test_the_round_trip_survives_a_locked_pyproject_and_every_input_field(self) -> None:
        overrides = {
            "payload": {"include": ["server.py", "pyproject.toml", "uv.lock"]},
            "python": {
                "dependencies": {
                    "type": "uv",
                    "pyproject": "pyproject.toml",
                    "lock": "uv.lock",
                }
            },
        }
        stored = _stored_description(**overrides)

        self.assertIsInstance(stored, Ok)
        self.assertEqual(stored.value, _authored_description(**overrides))
        self.assertEqual(
            stored.value.dependencies, PyProjectSpec("pyproject.toml", "uv.lock", "uv")
        )

    def test_a_package_that_declares_nothing_installable_is_read_as_such(self) -> None:
        stored = _stored_description(
            schema="aart.dev/skill/v1",
            artifact={"name": "review", "kind": "skill", "version": "1.0.0"},
            payload={"include": ["SKILL.md"]},
            transport=None,
            runtime=None,
            launch=None,
            inputs=None,
            python=None,
        )

        self.assertIsInstance(stored, Ok)
        self.assertEqual(stored.value, InstallDescription())

    def test_an_extension_that_is_not_an_object_is_refused_rather_than_ignored(self) -> None:
        result = read_install_description("aart.authoring", path="artifact.json")

        self.assertIsInstance(result, Err)


class StoredPackageTest(unittest.TestCase):
    """Reading a whole package tree, the way anything holding one on disk would."""

    def test_a_package_tree_describes_the_installation_it_asks_for(self) -> None:
        described = read_package_description(_compiled().canonical_entries)

        self.assertIsInstance(described, Ok, getattr(described, "diagnostics", ()))
        self.assertEqual(described.value, _authored_description())

    def test_a_tree_with_no_artifact_manifest_is_refused(self) -> None:
        entries = tuple(
            entry for entry in _compiled().canonical_entries if str(entry.path) != "artifact.json"
        )

        described = read_package_description(entries)

        self.assertIsInstance(described, Err)
        self.assertIn("artifact.json", _reason(described))

    def test_a_package_no_aart_compiler_wrote_is_refused_rather_than_guessed(self) -> None:
        compiled = _compiled()
        stripped = _without_authoring(compiled.canonical_entries)

        described = read_package_description(stripped)

        self.assertIsInstance(described, Err)
        self.assertIn("does not say how it is installed", _reason(described))

    def test_the_payload_of_a_stored_package_is_where_the_compiler_put_it(self) -> None:
        self.assertEqual(
            package_payload_root("/var/lib/aart/objects/ab"), "/var/lib/aart/objects/ab/payload"
        )


class DescriptionRulesTest(unittest.TestCase):
    def test_a_dependency_descriptor_needs_a_runtime_to_install_into(self) -> None:
        with self.assertRaises(ValueError) as raised:
            InstallDescription(dependencies=RequirementsFile("requirements.txt"))

        self.assertIn("Python runtime", str(raised.exception))

    def test_a_runtime_version_without_a_runtime_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            InstallDescription(runtime_version=">=3.11")

    def test_one_input_may_not_be_declared_twice(self) -> None:
        parsed = _parsed()
        assert isinstance(parsed, Ok)
        declared = describe_installation(parsed.value).inputs

        with self.assertRaises(ValueError):
            InstallDescription(inputs=(declared[0], declared[0]))

    def test_the_projection_describes_the_secret_without_a_place_to_put_one(self) -> None:
        """The binding is a declaration and belongs here; a value never is, and has no field."""

        data = install_description_to_data(_authored_description())
        secret, config = cast(list[dict[str, object]], data["inputs"])

        self.assertEqual(
            sorted(data), ["dependencies", "inputs", "launch", "runtime", "runtime_version"]
        )
        self.assertEqual(secret["kind"], "secret")
        self.assertEqual(sorted(secret), ["binding", "guidance", "id", "kind", "required"])
        self.assertIn("default", config)
        self.assertEqual(data["runtime"], "python")


if __name__ == "__main__":
    unittest.main()
