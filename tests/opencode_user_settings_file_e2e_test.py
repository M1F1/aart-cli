"""§218 end to end: a user installation lands in the OpenCode settings file every OpenCode reads.

An OpenCode 2 that a launcher starts with `OPENCODE_CONFIG` reads one user file: `opencode.jsonc`
when it exists, else `opencode.json`. OpenCode 1.x creates an empty `opencode.jsonc` the first time
it runs, so most people have one -- and aart-cli wrote `opencode.json`, which such an OpenCode never
reads: the MCP servers and plugins installed for the user were installed and invisible (D-530).

Driven through the public command against an isolated home, with the plugin fixture of §171: the
plugin kind needs no interpreter or credential, and it is written by the same settings-file
choice, the same JSONC editor and the same sibling clean-up as an MCP server.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from aart_cli.domain import jsonc
from aart_cli.domain.result import Ok
from aart_cli.io.receipt_store import LocalReceiptStore
from tests.configured_install_command_e2e_test import _Environment
from tests.plugin_installation_e2e_test import AUTHORED, COORDINATE

SCHEMA = "https://opencode.ai/config.json"
#: What OpenCode 1.x writes the first time it runs.
OPENCODES_OWN = '{\n  "$schema": "https://opencode.ai/config.json"\n}\n'
ANNOTATED = """// my own settings
{
  "$schema": "https://opencode.ai/config.json",
  /* the model I use */
  "model": "anthropic/claude", // keep this
  "plugin": [
    "opencode-wakatime", // timing
  ],
}
"""
NOTE = "// managed by aart-cli: "


class OpenCodeUserSettingsFileTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.env = _Environment(pathlib.Path(temporary.name).resolve())
        self.env.publish(AUTHORED)
        self.config = self.env.home / ".config/opencode"
        self.jsonc = self.config / "opencode.jsonc"
        self.json = self.config / "opencode.json"

    def _run(self, *arguments: str) -> dict:
        code, payload = self.env.run(*arguments)
        self.assertEqual(code, 0, payload)
        return payload

    def _install(self) -> dict:
        return self._run(
            "consume", "install", COORDINATE, "--profile", "opencode", "--scope", "user", "--yes"
        )

    def _write(self, path: pathlib.Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _plugins(self, path: pathlib.Path) -> list[str]:
        if not path.exists():
            return []
        return jsonc.loads(path.read_text(encoding="utf-8")).get("plugin", [])

    def _ours(self, path: pathlib.Path) -> list[str]:
        return [item for item in self._plugins(path) if "aart-cli" in item]

    def _destinations(self) -> list[str]:
        records = LocalReceiptStore(
            str(pathlib.Path(self.env.xdg["AART_CLI_HOME"]) / "state")
        ).installations()
        self.assertIsInstance(records, Ok, records)
        return [entry.destination for record in records.value for entry in record.receipt.settings]

    def _health(self) -> str:
        payload = self._run("consume", "status", "--profile", "opencode", "--scope", "user")
        (item,) = payload["items"]
        return item["health"]

    def test_with_neither_file_it_creates_opencode_jsonc_and_says_what_manages_the_entry(
        self,
    ) -> None:
        self._install()

        self.assertFalse(self.json.exists())
        text = self.jsonc.read_text(encoding="utf-8")
        (entry,) = self._ours(self.jsonc)
        self.assertIn(f"{NOTE}", text)
        self.assertLess(text.index(NOTE), text.index(entry))
        self.assertEqual([str(self.jsonc)], self._destinations())
        self.assertEqual("ready", self._health())

    def test_opencodes_own_empty_file_is_the_one_written(self) -> None:
        self._write(self.jsonc, OPENCODES_OWN)

        self._install()

        self.assertEqual(SCHEMA, jsonc.loads(self.jsonc.read_text())["$schema"])
        self.assertEqual(1, len(self._ours(self.jsonc)))
        self.assertFalse(self.json.exists())

    def test_every_comment_the_person_wrote_survives_install_and_uninstall(self) -> None:
        self._write(self.jsonc, ANNOTATED)

        self._install()
        installed = self.jsonc.read_text(encoding="utf-8")
        for comment in ("// my own settings", "/* the model I use */", "// keep this", "// timing"):
            self.assertIn(comment, installed)
        self.assertEqual("opencode-wakatime", self._plugins(self.jsonc)[0])
        self.assertEqual(1, len(self._ours(self.jsonc)))

        self._run(
            "consume", "uninstall", COORDINATE, "--profile", "opencode", "--scope", "user", "--yes"
        )

        self.assertEqual(ANNOTATED, self.jsonc.read_text(encoding="utf-8"))

    def test_where_only_opencode_json_is_there_it_is_written_without_a_note(self) -> None:
        self._write(self.json, json.dumps({"$schema": SCHEMA}, indent=2) + "\n")

        self._install()

        self.assertFalse(self.jsonc.exists())
        self.assertEqual(1, len(self._ours(self.json)))
        self.assertNotIn("aart-cli:", self.json.read_text().replace("/aart-cli/", ""))
        json.loads(self.json.read_text())  # still strict JSON

    def test_an_entry_left_in_opencode_json_is_moved_by_a_reviewed_repair(self) -> None:
        self._write(self.json, json.dumps({"$schema": SCHEMA, "plugin": ["mine"]}, indent=2))
        self._install()
        self.assertEqual(1, len(self._ours(self.json)))
        # OpenCode 1.x ran once: from now on a launcher passes only this file.
        self._write(self.jsonc, OPENCODES_OWN)

        self.assertNotEqual("ready", self._health())
        review = self._run("doctor", "--repair", COORDINATE + "@7.0.0", "--scope", "user")
        self.assertEqual(
            ["mine", *self._ours(self.json)], self._plugins(self.json), "a review wrote"
        )
        self._run(
            "doctor",
            "--repair",
            COORDINATE + "@7.0.0",
            "--scope",
            "user",
            "--yes",
            "--expect",
            review["review_digest"],
        )

        self.assertEqual(1, len(self._ours(self.jsonc)))
        self.assertEqual(["mine"], self._plugins(self.json))
        self.assertIn(NOTE, self.jsonc.read_text())
        self.assertEqual([str(self.jsonc)], self._destinations())
        self.assertEqual("ready", self._health())

    def test_doctor_says_which_file_opencode_reads_and_how_to_move_the_entry(self) -> None:
        self._write(self.json, json.dumps({"plugin": ["mine"]}, indent=2))
        self._install()
        self._write(self.jsonc, OPENCODES_OWN)

        code, payload = self.env.run("doctor")
        self.assertNotEqual(0, code)
        (move,) = payload["settings_files"]
        self.assertEqual(
            (str(self.json), str(self.jsonc), "opencode", "user"),
            (move["recorded"], move["read"], move["harness"], move["scope"]),
        )
        _code, text = self.env.run_text("doctor")
        self.assertIn("written in ~/.config/opencode/opencode.json\n", text)
        self.assertIn("opencode reads ~/.config/opencode/opencode.jsonc instead", text)
        self.assertIn(f"aart-cli doctor --repair {COORDINATE}@7.0.0 --scope user", text)

    def test_doctor_is_silent_about_settings_files_when_nothing_is_misplaced(self) -> None:
        self._install()

        _code, payload = self.env.run("doctor")
        _code, text = self.env.run_text("doctor")

        self.assertEqual([], payload["settings_files"])
        self.assertNotIn("Settings files", text)

    def test_an_entry_still_in_both_files_is_drift_and_the_repair_keeps_one(self) -> None:
        self._install()
        (ours,) = self._ours(self.jsonc)
        self._write(self.json, json.dumps({"plugin": ["mine", ours]}, indent=2))

        self.assertNotEqual("ready", self._health())
        review = self._run("doctor", "--repair", COORDINATE + "@7.0.0", "--scope", "user")
        self._run(
            "doctor",
            "--repair",
            COORDINATE + "@7.0.0",
            "--scope",
            "user",
            "--yes",
            "--expect",
            review["review_digest"],
        )

        self.assertEqual(["mine"], self._plugins(self.json))
        self.assertEqual([ours], self._ours(self.jsonc))
        self.assertEqual("ready", self._health())

    def test_a_symlinked_opencode_json_without_the_entry_is_left_alone(self) -> None:
        dotfiles = self.env.home / "dotfiles/opencode.json"
        self._write(dotfiles, json.dumps({"plugin": ["mine"]}))
        self._write(self.jsonc, OPENCODES_OWN)
        self.json.symlink_to(dotfiles)

        self._install()
        self._run(
            "consume", "uninstall", COORDINATE, "--profile", "opencode", "--scope", "user", "--yes"
        )

        self.assertTrue(self.json.is_symlink())
        self.assertEqual(json.dumps({"plugin": ["mine"]}), dotfiles.read_text())
        self.assertEqual([], self._plugins(self.jsonc))

    def test_uninstalling_an_entry_recorded_in_opencode_json_cleans_both_files(self) -> None:
        self._write(self.json, json.dumps({"plugin": ["mine"]}, indent=2))
        self._install()
        self._write(self.jsonc, OPENCODES_OWN)

        self._run(
            "consume", "uninstall", COORDINATE, "--profile", "opencode", "--scope", "user", "--yes"
        )

        self.assertEqual(["mine"], self._plugins(self.json))
        self.assertEqual(OPENCODES_OWN, self.jsonc.read_text(encoding="utf-8"))
        self.assertEqual([], self._destinations())


if __name__ == "__main__":
    unittest.main()
