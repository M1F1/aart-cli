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

import contextlib
import io
import json
import os
import pathlib
import shlex
import shutil
import tempfile
import unittest
from unittest import mock

from aart_cli import cli
from aart_cli.application.consumer_ui import ConsumerScreen
from aart_cli.domain import jsonc
from aart_cli.domain.result import Ok
from aart_cli.io.receipt_store import LocalReceiptStore
from tests.configured_install_command_e2e_test import _Environment
from tests.configured_installation_draft_e2e_test import _published_registries
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import ENTER
from tests.plugin_installation_e2e_test import AUTHORED, COORDINATE, MANIFEST, MODULE

HELPERS = "company/plugin/helpers"
#: A second plugin beside superpowers, so one repair can be asked to move two.
HELPERS_TREE = (
    (
        "helpers/aart-cli.json",
        json.dumps(
            {
                **MANIFEST,
                "artifact": {"name": "helpers", "kind": "plugin", "x-fixture-version": "1.0.0"},
                "payload": {"include": [".opencode/plugins/superpowers.js"]},
            }
        ),
    ),
    ("helpers/.opencode/plugins/superpowers.js", MODULE),
)

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

    def _with_stderr(self, *argv: str) -> tuple[int, str, str]:
        """A command as a person types it, without `--project`: its stdout and its stderr."""

        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(os.environ, self.env.xdg, clear=False),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            mock.patch("os.getcwd", return_value=str(self.env.project)),
        ):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def _two_misplaced(self) -> None:
        with mock.patch(
            "tests.configured_install_command_e2e_test._published_registry",
            lambda _authored, **keywords: _published_registries(AUTHORED, HELPERS_TREE, **keywords),
        ):
            self.env.publish(AUTHORED)
        self._write(self.json, json.dumps({"$schema": SCHEMA, "plugin": ["mine"]}, indent=2))
        for coordinate in (COORDINATE, HELPERS):
            self._run(
                "consume",
                "install",
                coordinate,
                "--profile",
                "opencode",
                "--scope",
                "user",
                "--yes",
            )
        # OpenCode 1.x ran once: from now on a launcher passes only this file.
        self._write(self.jsonc, OPENCODES_OWN)

    def test_the_same_two_commands_move_every_misplaced_entry_for_everybody(self) -> None:
        self._two_misplaced()

        # Any consume command says so, on stderr, with the command; its --json stays a document.
        code, out, err = self._with_stderr("consume", "list", "--json")
        self.assertEqual(0, code, err)
        json.loads(out)
        self.assertIn("OpenCode does not load 2 MCP servers or plugins aart-cli installed", err)
        self.assertIn("Review moving them: aart-cli doctor --repair-settings", err)

        code, review, err = self._with_stderr("doctor", "--repair-settings")
        self.assertEqual(0, code, err)
        self.assertTrue(
            review.rstrip("\n").endswith(
                "Reviewed only; nothing changed. To apply exactly this:\n"
                "  aart-cli doctor --repair-settings --yes"
            ),
            review,
        )
        self.assertEqual(2, len(self._ours(self.json)), "a review wrote")

        code, applied, err = self._with_stderr("doctor", "--repair-settings", "--yes")

        self.assertEqual(0, code, applied + err)
        self.assertEqual(2, len(self._ours(self.jsonc)))
        self.assertEqual(["mine"], self._plugins(self.json))
        self.assertEqual([str(self.jsonc)] * 2, self._destinations())
        code, out, err = self._with_stderr("consume", "list")
        self.assertEqual("", err, "the notice outlived the repair")
        code, again, _err = self._with_stderr("doctor", "--repair-settings", "--yes")
        self.assertEqual(0, code)
        self.assertIn("Nothing to move", again)

    def test_nothing_misplaced_means_no_notice(self) -> None:
        self._install()

        code, _out, err = self._with_stderr("consume", "list")

        self.assertEqual(0, code)
        self.assertNotIn("does not load", err)

    def test_repair_settings_names_no_artifact(self) -> None:
        self._two_misplaced()

        code, out, _err = self._with_stderr(
            "doctor", "--repair-settings", "--repair", COORDINATE + "@7.0.0", "--yes"
        )

        self.assertNotEqual(0, code)
        self.assertIn("names no artifact", out)
        self.assertEqual(2, len(self._ours(self.json)), "a refused repair wrote")

    def test_a_named_repair_review_ends_with_the_exact_command_that_applies_it(self) -> None:
        self._write(self.json, json.dumps({"$schema": SCHEMA}, indent=2))
        self._install()
        self._write(self.jsonc, OPENCODES_OWN)
        named = COORDINATE + "@7.0.0"
        code, _out, _err = self._with_stderr(
            "doctor", "--repair", named, "--scope", "user", "--yes"
        )
        self.assertNotEqual(0, code, "a named repair applied without the reviewed digest")

        code, review, err = self._with_stderr("doctor", "--repair", named, "--scope", "user")
        self.assertEqual(0, code, err)
        command = review.rstrip("\n").rsplit("\n", 1)[1].strip()
        argv = shlex.split(command)
        self.assertEqual(
            ["aart-cli", "doctor", "--repair", named, "--scope", "user", "--yes", "--expect"],
            argv[:-1],
        )
        code, applied, err = self._with_stderr(*argv[1:])

        self.assertEqual(0, code, applied + err)
        self.assertEqual(1, len(self._ours(self.jsonc)))

    def test_the_tui_doctor_moves_every_misplaced_entry_with_one_key_and_enter(self) -> None:
        self._two_misplaced()
        handler = _actions(self.env)

        reviewed, terminal, handler = _drive(
            self.env, _at(ConsumerScreen.DOCTOR), ord("m"), actions=handler
        )
        self.assertEqual(ConsumerScreen.VERIFY_REPAIR, reviewed.session.screen)
        self.assertEqual(2, len(self._ours(self.json)), "a review wrote")

        finished, terminal, handler = _drive(
            self.env, _at(ConsumerScreen.DOCTOR), ord("m"), ENTER, actions=_actions(self.env)
        )

        self.assertEqual(ConsumerScreen.ACTIVITY_DETAILS, finished.session.screen, terminal.last)
        self.assertEqual(2, len(self._ours(self.jsonc)))
        self.assertEqual(["mine"], self._plugins(self.json))
        self.assertEqual([str(self.jsonc)] * 2, self._destinations())

    def test_the_tui_doctor_says_what_is_misplaced_and_which_key_moves_it(self) -> None:
        self._two_misplaced()

        _finished, terminal, _handler = _drive(self.env, _at(ConsumerScreen.DOCTOR))

        self.assertTrue(
            terminal.screen_containing("opencode does not load 2 installations"), terminal.last
        )
        self.assertTrue(terminal.screen_containing("Press m to move them all"), terminal.last)

    def test_the_tui_doctor_has_nothing_to_move_when_nothing_is_misplaced(self) -> None:
        self._install()

        finished, terminal, _handler = _drive(self.env, _at(ConsumerScreen.DOCTOR), ord("m"))

        self.assertEqual(ConsumerScreen.DOCTOR, finished.session.screen)
        self.assertFalse(terminal.screen_containing("Press m to move"), terminal.last)
        self.assertTrue(terminal.screen_containing("nothing to move"), terminal.last)

    def test_a_doctor_that_finds_misplaced_entries_exits_1_and_is_no_failure(self) -> None:
        self._two_misplaced()
        journaled: list[tuple[str, str]] = []
        with mock.patch(
            "aart_cli.commands.report.record_in_application_home",
            lambda _home, kind, place, **_keywords: journaled.append((kind, place)),
        ):
            code, _out, _err = self._with_stderr("doctor")
            self.assertEqual(1, code)
            self.assertEqual([], journaled, "a finding was journaled as a failure")
            # A command that did fail still is.
            code, _out, _err = self._with_stderr(
                "doctor", "--repair-settings", "--yes", "--expect", "sha256:" + "0" * 64
            )

        self.assertNotEqual(0, code)
        self.assertEqual([("error", "doctor")], journaled)

    def test_the_move_review_says_from_where_to_where_and_nothing_alarming(self) -> None:
        self._two_misplaced()

        code, review, _err = self._with_stderr("doctor", "--repair-settings")
        self.assertEqual(0, code)
        code, applied, _err = self._with_stderr("doctor", "--repair-settings", "--yes")

        self.assertEqual(0, code, applied)
        for text in (review, applied):
            self.assertNotIn("Risks:", text)
            self.assertNotIn("sha256:", text)
            self.assertIn(
                "opencode: from ~/.config/opencode/opencode.json to "
                "~/.config/opencode/opencode.jsonc",
                text,
            )
            self.assertIn(f"- {COORDINATE}@7.0.0", text)
            self.assertIn(f"- {HELPERS}@1.0.0", text)
        self.assertIn("nothing is installed or removed", review)
        self.assertIn("Moved 2 installations:", applied)

    def test_a_move_that_also_repairs_something_else_is_confirmed_by_its_digest(self) -> None:
        self._two_misplaced()
        payload = self.config / "aart-cli/plugin/company/helpers/payload"
        for path in (payload, *payload.rglob("*")):
            path.chmod(0o755 if path.is_dir() else 0o644)
        shutil.rmtree(payload)

        code, review, _err = self._with_stderr("doctor", "--repair-settings")
        self.assertEqual(0, code, review)
        self.assertNotIn("nothing is installed or removed", review)
        self.assertIn("Components changing: payload", review)
        command = review.rstrip("\n").rsplit("\n", 1)[1].strip()
        self.assertTrue(
            command.startswith("aart-cli doctor --repair-settings --yes --expect sha256:")
        )

        code, _out, _err = self._with_stderr("doctor", "--repair-settings", "--yes")
        self.assertNotEqual(0, code, "a wider repair applied without its reviewed digest")
        self.assertFalse(payload.exists())
        self.assertEqual(2, len(self._ours(self.json)), "a refused repair wrote")

    def test_the_tui_says_on_the_dashboard_what_opencode_does_not_load(self) -> None:
        self._two_misplaced()

        _finished, terminal, _handler = _drive(self.env, _at(ConsumerScreen.DASHBOARD))
        self.assertTrue(
            terminal.screen_containing(
                "● opencode does not load 2 installations — open Doctor and press m"
            ),
            terminal.last,
        )
        self.assertTrue(terminal.screen_containing("Doctor  ● 2 to move"), terminal.last)

        _reviewed, terminal, _handler = _drive(self.env, _at(ConsumerScreen.DOCTOR), ord("m"))
        self.assertTrue(terminal.screen_containing("Enter moves them."), terminal.last)
        self.assertFalse(terminal.screen_containing("Risks:"), terminal.last)
        self.assertFalse(terminal.screen_containing("sha256:"), terminal.last)

        self._with_stderr("doctor", "--repair-settings", "--yes")
        _finished, terminal, _handler = _drive(self.env, _at(ConsumerScreen.DASHBOARD))
        self.assertFalse(terminal.screen_containing("does not load"), terminal.last)
        self.assertFalse(terminal.screen_containing("to move"), terminal.last)

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

    def test_a_key_the_install_added_goes_with_the_uninstall_byte_for_byte(self) -> None:
        self._write(self.jsonc, OPENCODES_OWN)

        self._install()
        self.assertIn('"plugin"', self.jsonc.read_text(encoding="utf-8"))
        self._run(
            "consume", "uninstall", COORDINATE, "--profile", "opencode", "--scope", "user", "--yes"
        )

        self.assertEqual(OPENCODES_OWN, self.jsonc.read_text(encoding="utf-8"))

    def test_one_reviewed_repair_moves_every_named_entry(self) -> None:
        with mock.patch(
            "tests.configured_install_command_e2e_test._published_registry",
            lambda _authored, **keywords: _published_registries(AUTHORED, HELPERS_TREE, **keywords),
        ):
            self.env.publish(AUTHORED)
        self._write(self.json, json.dumps({"$schema": SCHEMA}, indent=2) + "\n")
        for coordinate in (COORDINATE, HELPERS):
            self._run(
                "consume",
                "install",
                coordinate,
                "--profile",
                "opencode",
                "--scope",
                "user",
                "--yes",
            )
        self._write(self.jsonc, OPENCODES_OWN)

        _code, text = self.env.run_text("doctor")
        named = (f"{HELPERS}@1.0.0", f"{COORDINATE}@7.0.0")
        self.assertIn("Move them all: aart-cli doctor --repair-settings", text)
        review = self._run("doctor", "--repair", *named, "--scope", "user")
        self.assertEqual(list(named), review["coordinates"])
        self.assertEqual(2, len(self._ours(self.json)), "a review wrote")
        code, refused = self.env.run(
            "doctor",
            "--repair",
            *named,
            "--scope",
            "user",
            "--yes",
            "--expect",
            "sha256:" + "0" * 64,
        )
        self.assertNotEqual(0, code, refused)
        for one in named:
            alone = self._run("doctor", "--repair", one, "--scope", "user")["review_digest"]
            code, refused = self.env.run(
                "doctor", "--repair", *named, "--scope", "user", "--yes", "--expect", alone
            )
            self.assertNotEqual(0, code, f"the review of {one} alone confirmed both")
        self.assertEqual(2, len(self._ours(self.json)), "a refused confirmation wrote")

        applied = self._run(
            "doctor",
            "--repair",
            *named,
            "--scope",
            "user",
            "--yes",
            "--expect",
            review["review_digest"],
        )

        self.assertTrue(all(item["ok"] for item in applied["results"]), applied)
        self.assertEqual(2, len(self._ours(self.jsonc)))
        self.assertEqual(json.dumps({"$schema": SCHEMA}, indent=2) + "\n", self.json.read_text())

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
        self.assertIn("Move them all: aart-cli doctor --repair-settings\n", text)

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
        self.assertEqual(OPENCODES_OWN, self.jsonc.read_text(encoding="utf-8"))

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
