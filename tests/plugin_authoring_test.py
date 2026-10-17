"""§171.1–171.2: a plugin package names its entry module and carries everything it loads.

The manifest says which module the harness loads (`plugin.entry`), and the compiler holds the
three things that would otherwise surface only inside somebody's harness:
- the entry is a module the payload carries;
- the field belongs to a plugin and to nothing else;
- a plugin declaring runtime dependencies is refused, because AART fetches none, so it would
  install cleanly and then fail, or fetch packages, the first time it ran (INV-255).

Development-only declarations are not runtime dependencies, so they are accepted.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import compile_author_snapshot, package_plugin
from aart_cli.sources.local import read_local_snapshot
from aart_cli.sources.model import LocalSnapshotRequest, SnapshotLimits, source_instance_id
from tests.fixture_versions import with_fixture_versions

_MODULE = "export const Plugin = async () => ({});\nexport default Plugin;\n"
_PLUGIN_FIELD = object()


def _manifest(*, kind: str = "plugin", plugin: object = _PLUGIN_FIELD) -> str:
    document: dict[str, object] = {
        "schema": f"aart-cli.dev/{kind}/v1",
        "artifact": {"kind": kind, "name": "superpowers"},
        "payload": {"include": ["**"], "exclude": ["aart-cli.json"]},
    }
    if plugin is _PLUGIN_FIELD:
        document["plugin"] = {"entry": ".opencode/plugins/superpowers.js"}
    elif plugin is not None:
        document["plugin"] = plugin
    return json.dumps(document)


def _compile(root: Path):
    alias = SourceAlias("authors")
    configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(root), None, True)
    acquired = read_local_snapshot(
        LocalSnapshotRequest(source_instance_id(configured), alias, str(root), SnapshotLimits())
    )
    assert isinstance(acquired, Ok), getattr(acquired, "diagnostics", ())
    return with_fixture_versions(compile_author_snapshot)(
        acquired.value.snapshot,
        source_alias=alias,
        source="https://git.example.test/authors.git",
        revision="c" * 40,
    )


def _tree(root: Path, manifest: str, files: dict[str, str] | None = None) -> None:
    (root / "aart-cli.json").write_text(manifest, encoding="utf-8")
    for relative, text in (
        files
        if files is not None
        else {
            ".opencode/plugins/superpowers.js": _MODULE,
            "skills/brainstorming/SKILL.md": "---\nname: brainstorming\n---\n",
        }
    ).items():
        path = root / relative
        os.makedirs(path.parent, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _refusal(compiled) -> str:
    assert isinstance(compiled, Err), compiled
    return " ".join(item.message for item in compiled.diagnostics)


class APluginPackageNamesItsEntryTest(unittest.TestCase):
    def test_a_plugin_compiles_and_its_package_says_which_module_to_load(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _tree(Path(raw), _manifest())

            compiled = _compile(Path(raw))

            self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
            (artifact,) = compiled.value
            self.assertEqual("plugin", artifact.package.kind.value)
            packaged = package_plugin(artifact.canonical_entries)
            self.assertIsInstance(packaged, Ok, getattr(packaged, "diagnostics", ()))
            self.assertEqual(".opencode/plugins/superpowers.js", packaged.value.entry)

    def test_an_entry_the_payload_does_not_carry_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _tree(Path(raw), _manifest(plugin={"entry": "missing.js"}))

            self.assertIn("missing.js", _refusal(_compile(Path(raw))))

    def test_an_entry_that_is_not_a_module_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _tree(
                Path(raw),
                _manifest(plugin={"entry": "plugin.json"}),
                {"plugin.json": "{}", "index.js": _MODULE},
            )

            self.assertIn(".js, .mjs or .ts", _refusal(_compile(Path(raw))))

    def test_a_plugin_without_an_entry_and_an_entry_on_another_kind_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _tree(Path(raw), _manifest(plugin=None))

            self.assertIn("plugin.entry", _refusal(_compile(Path(raw))))
        with tempfile.TemporaryDirectory() as raw:
            _tree(Path(raw), _manifest(kind="skill"), {"SKILL.md": "---\nname: s\n---\n"})

            self.assertIn("only for a plugin", _refusal(_compile(Path(raw))))


class APluginTakesNoInputsTest(unittest.TestCase):
    def test_declared_inputs_are_refused_because_nothing_receives_them(self) -> None:
        manifest = json.loads(_manifest())
        manifest["inputs"] = [
            {
                "id": "api-token",
                "kind": "secret",
                "required": True,
                "inject": {"type": "environment", "variable": "TOKEN"},
            }
        ]
        with tempfile.TemporaryDirectory() as raw:
            _tree(Path(raw), json.dumps(manifest))

            self.assertIn("inputs are not valid for a plugin", _refusal(_compile(Path(raw))))


class APluginFetchesNothingTest(unittest.TestCase):
    def _with_package(self, package: dict[str, object]):
        with tempfile.TemporaryDirectory() as raw:
            _tree(
                Path(raw),
                _manifest(),
                {
                    ".opencode/plugins/superpowers.js": _MODULE,
                    "package.json": json.dumps(package),
                },
            )
            return _compile(Path(raw))

    def test_declared_runtime_dependencies_are_refused(self) -> None:
        for key in ("dependencies", "optionalDependencies"):
            with self.subTest(key=key):
                refusal = _refusal(self._with_package({key: {"left-pad": "^1.3.0"}}))

                self.assertIn(key, refusal)
                self.assertIn("fetches", refusal)

    def test_development_declarations_and_an_empty_list_are_not_dependencies(self) -> None:
        for package in (
            {"name": "superpowers", "main": ".opencode/plugins/superpowers.js"},
            {"devDependencies": {"@opencode-ai/plugin": "^1"}, "dependencies": {}},
        ):
            with self.subTest(package=package):
                self.assertIsInstance(self._with_package(package), Ok)


if __name__ == "__main__":
    unittest.main()
