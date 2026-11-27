"""§218: which OpenCode user settings file an MCP server is written to, and how it moves there.

An OpenCode 2 a launcher starts reads `opencode.jsonc` when it exists and `opencode.json` only when
it does not (D-530). The registry writes the file every OpenCode reads, edits it without losing a
comment, takes this installation's server -- and nobody else's -- out of the file it no longer
belongs in, and reads a server left there as drift. A recorded installation is judged against the
file read now.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aart_cli.application.settings_relocation import relocated_receipt
from aart_cli.domain import jsonc
from aart_cli.domain.harness import (
    McpRegistration,
    Scope,
    chosen_settings_file,
    mcp_target,
    preferred_settings_path,
    registration_from_data,
    registration_to_data,
    sibling_settings_paths,
)
from aart_cli.domain.hooks import PluginEntry
from aart_cli.domain.identifiers import ObjectDigest
from aart_cli.domain.receipts import (
    ArtifactSettingsEntry,
    InstallationReceipt,
    PlacedArtifactReceipt,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.io.harness import LocalHarnessRegistry

JSONC = ".config/opencode/opencode.jsonc"
JSON = ".config/opencode/opencode.json"
LAUNCHER = "/home/a/.aart-cli/bin/github"
ANNOTATED = """{
  // my own settings
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "mine": { "type": "remote", "url": "https://example.test/mcp" }, // mine
  },
}
"""


def _user(settings_file: str = JSONC) -> McpRegistration:
    target = mcp_target("opencode", Scope.USER, exists=lambda path: path == settings_file)
    return McpRegistration(target, "github", LAUNCHER)


class ChoosingTheFileTest(unittest.TestCase):
    def test_jsonc_wins_json_is_kept_where_alone_and_jsonc_is_created_where_neither(self) -> None:
        def choose(*present: str) -> str:
            return chosen_settings_file("opencode", Scope.USER, JSON, lambda path: path in present)

        self.assertEqual(JSONC, choose(JSONC, JSON))
        self.assertEqual(JSONC, choose(JSONC))
        self.assertEqual(JSON, choose(JSON))
        self.assertEqual(JSONC, choose())

    def test_project_scope_and_other_harnesses_have_one_file(self) -> None:
        self.assertEqual(
            "opencode.json",
            mcp_target("opencode", Scope.PROJECT, exists=lambda _path: True).settings_file,
        )
        self.assertEqual(
            ".claude.json",
            mcp_target("claude", Scope.USER, exists=lambda _path: False).settings_file,
        )
        self.assertEqual((), sibling_settings_paths("opencode", "/p/opencode.json"))
        self.assertEqual((), sibling_settings_paths("claude", "/h/.claude.json"))
        self.assertEqual(
            ("/h/.config/opencode/opencode.json",),
            sibling_settings_paths("opencode", "/h/.config/opencode/opencode.jsonc"),
        )

    def test_a_receipt_names_either_user_file_and_nothing_else(self) -> None:
        for settings_file in (JSONC, JSON):
            data = registration_to_data(_user(settings_file))
            self.assertEqual(settings_file, data["settings_file"])
            parsed = registration_from_data(data)
            self.assertEqual(settings_file, parsed.target.settings_file)
        with self.assertRaisesRegex(ValueError, "opencode.jsonc or .config/opencode/opencode.json"):
            registration_from_data({**registration_to_data(_user()), "settings_file": "x.json"})


class RegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.registry = LocalHarnessRegistry(str(self.home))

    def _write(self, relative: str, text: str) -> Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _servers(self, relative: str) -> dict:
        path = self.home / relative
        return jsonc.loads(path.read_text(encoding="utf-8")).get("mcp", {}) if path.exists() else {}

    def test_a_server_goes_into_an_annotated_jsonc_with_every_comment_kept(self) -> None:
        path = self._write(JSONC, ANNOTATED)

        registered = self.registry.register(_user(), note="managed by aart-cli: company/mcp/github")

        self.assertIsInstance(registered, Ok, registered)
        text = path.read_text(encoding="utf-8")
        self.assertIn("// my own settings", text)
        self.assertIn("// mine", text)
        self.assertIn('    // managed by aart-cli: company/mcp/github\n    "github": {', text)
        self.assertEqual({"mine", "github"}, set(self._servers(JSONC)))
        self.assertEqual(LAUNCHER, self.registry.observed_command(_user()))

        removed = self.registry.unregister(_user().target, "github", command=LAUNCHER)

        self.assertIsInstance(removed, Ok, removed)
        self.assertEqual(ANNOTATED, path.read_text(encoding="utf-8"))

    def test_registering_takes_this_server_out_of_the_other_file_and_leaves_the_rest(self) -> None:
        ours = {"type": "local", "command": [LAUNCHER]}
        self._write(JSON, json.dumps({"mcp": {"github": ours, "mine": {"type": "remote"}}}))
        self._write(JSONC, "{}\n")

        registered = self.registry.register(_user())

        self.assertIsInstance(registered, Ok, registered)
        self.assertTrue(registered.value.changed)
        self.assertEqual({"github"}, set(self._servers(JSONC)))
        self.assertEqual({"mine"}, set(self._servers(JSON)))

    def test_a_broken_file_opencode_does_not_read_does_not_stop_the_install(self) -> None:
        self._write(JSON, "{ not json")
        self._write(JSONC, "{}\n")

        registered = self.registry.register(_user())

        self.assertIsInstance(registered, Ok, registered)
        self.assertEqual({"github"}, set(self._servers(JSONC)))
        self.assertEqual("{ not json", (self.home / JSON).read_text())
        self.assertIsInstance(
            self.registry.unregister(_user().target, "github", command=LAUNCHER), Ok
        )

    def test_a_same_named_server_somebody_else_wrote_is_not_ours_to_remove(self) -> None:
        theirs = {"type": "local", "command": ["/usr/local/bin/their-github"]}
        self._write(JSON, json.dumps({"mcp": {"github": theirs}}))

        self.assertIsInstance(self.registry.register(_user()), Ok)
        self.assertIsInstance(
            self.registry.unregister(_user().target, "github", command=LAUNCHER), Ok
        )

        self.assertEqual({"github": theirs}, self._servers(JSON))

    def test_a_server_also_or_only_in_the_other_file_reads_as_divergent(self) -> None:
        ours = {"type": "local", "command": [LAUNCHER]}
        self._write(JSON, json.dumps({"mcp": {"github": ours}}))
        self._write(JSONC, "{}\n")

        only = self.registry.observed_command(_user())
        self.assertIsNotNone(only)
        self.assertNotEqual(LAUNCHER, only)
        self.assertIn("only in", only)

        self._write(JSONC, json.dumps({"mcp": {"github": ours}}))
        also = self.registry.observed_command(_user())
        self.assertNotEqual(LAUNCHER, also)
        self.assertIn("also in", also)

        self._write(JSON, "{}\n")
        self.assertEqual(LAUNCHER, self.registry.observed_command(_user()))

    def test_a_comment_inside_a_value_that_must_be_rewritten_whole_is_refused_not_lost(
        self,
    ) -> None:
        path = self._write(JSONC, '{"mcp": {"mine": 1 /* keep */}}')

        refused = self.registry.register(_user())

        self.assertIsInstance(refused, Err)
        self.assertIn("losing a comment", refused.diagnostics[0].message)
        self.assertEqual('{"mcp": {"mine": 1 /* keep */}}', path.read_text())

    def test_strict_json_harnesses_still_refuse_comments(self) -> None:
        self._write(".claude.json", "{ // no\n}")
        target = mcp_target("claude", Scope.USER)

        refused = self.registry.register(McpRegistration(target, "github", LAUNCHER))

        self.assertIsInstance(refused, Err)
        self.assertIn("not valid JSON", refused.diagnostics[0].message)


class RelocationTest(unittest.TestCase):
    def _receipt(self, settings_file: str) -> InstallationReceipt:
        root = "/h/.config/opencode/aart-cli/mcp/company/github"
        return InstallationReceipt(
            "company/mcp/github",
            root,
            f"{root}/bin/github",
            ObjectDigest("sha256", "0" * 64),
            "/usr/bin/python3",
            registrations=(_user(settings_file),),
        )

    def test_a_receipt_naming_opencode_json_moves_once_jsonc_is_there(self) -> None:
        receipt = self._receipt(JSON)

        moved = relocated_receipt(receipt, root="/h", exists=lambda path: path.endswith(".jsonc"))
        kept = relocated_receipt(receipt, root="/h", exists=lambda path: path.endswith(".json"))

        self.assertEqual(JSONC, moved.registrations[0].target.settings_file)
        self.assertIs(receipt, kept)

    def test_a_plugin_entry_moves_with_its_reference_unchanged(self) -> None:
        entry = ArtifactSettingsEntry(
            "opencode",
            "/h/.config/opencode/opencode.json",
            "plugin",
            PluginEntry("./aart-cli/plugin/company/superpowers", "payload/index.js"),
        )
        receipt = PlacedArtifactReceipt(
            "company/plugin/superpowers",
            "/h/.config/opencode/aart-cli/plugin/company/superpowers",
            ObjectDigest("sha256", "1" * 64),
            settings=(entry,),
        )

        moved = relocated_receipt(receipt, root="/h", exists=lambda path: path.endswith(".jsonc"))

        (relocated,) = moved.settings
        self.assertEqual("/h/.config/opencode/opencode.jsonc", relocated.destination)
        self.assertEqual(entry.entry, relocated.entry)

    def test_a_project_file_is_never_moved(self) -> None:
        self.assertEqual(
            "/p/opencode.json",
            preferred_settings_path("opencode", "/p/opencode.json", lambda _path: True),
        )


if __name__ == "__main__":
    unittest.main()
