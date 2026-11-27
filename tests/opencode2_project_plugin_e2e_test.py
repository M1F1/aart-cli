"""OpenCode 2's project plugin through the public command (§171.3, §171.5, D-532).

Installed for OpenCode 2, a project plugin is `.opencode/plugins/<installed name>/index.js` and
nothing in `opencode.json`; it is reviewed as running code, measured, repaired and removed like any
delivery; and a plugin installed for OpenCode 1 stays as it was when the choice changes.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from dataclasses import replace
from unittest import mock

from aart_cli import cli
from aart_cli.application.consumer_views import ConsumerSettings
from aart_cli.domain.result import Ok
from aart_cli.io.consumer_settings import read_consumer_settings, write_consumer_settings
from aart_cli.io.receipt_store import LocalReceiptStore
from tests.configured_install_command_e2e_test import _Environment
from tests.plugin_installation_e2e_test import (
    AUTHORED,
    COORDINATE,
    ENTRY_MODULE,
    EXISTING,
    REFERENCE,
    TREE,
)

#: Where OpenCode 2 finds the fixture plugin: its installed name, under `.opencode/plugins/`.
LOADER = ".opencode/plugins/superpowers-company-project"
#: The module, as the loader imports it: out of `.opencode/plugins/<name>/`, into the tree.
IMPORTED = "../../aart-cli/plugin/company/superpowers/payload/.opencode/plugins/superpowers.js"


class OpenCode2ProjectPluginTest(unittest.TestCase):
    """The public command, with OpenCode 2 chosen the way a person chooses it."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.env = _Environment(pathlib.Path(temporary.name).resolve())
        self.env.publish(AUTHORED)
        self.settings = self.env.project / "opencode.json"
        self.loader = self.env.project / LOADER

    def _opencode(self, *argv: str) -> tuple[int, dict]:
        """`consume opencode`, which is a machine's setting and takes no `--project`."""

        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.env.xdg, clear=False),
            contextlib.redirect_stdout(output),
        ):
            code = cli.main(["consume", "opencode", *argv, "--json"])
        return code, json.loads(output.getvalue())

    def _choose(self, runtime: str) -> dict:
        code, payload = self._opencode(runtime)
        self.assertEqual(code, 0, payload)
        return payload

    def _install(self) -> dict:
        code, payload = self.env.run(
            "consume", "install", COORDINATE, "--profile", "opencode", "--yes"
        )
        self.assertEqual(code, 0, payload)
        return payload

    def _health(self) -> str:
        code, payload = self.env.run("consume", "status", "--profile", "opencode")
        self.assertEqual(code, 0, payload)
        return payload["items"][0]["health"]

    def _installed(self):
        records = LocalReceiptStore(self.env.paths.data_root + "/state").installations()
        self.assertIsInstance(records, Ok, records)
        return records.value

    def test_the_command_says_who_decided_and_keeps_a_choice(self) -> None:
        code, payload = self._opencode()
        self.assertEqual(code, 0, payload)
        self.assertEqual(
            {"opencode": 1, "decided_by": "build"},
            {key: payload[key] for key in ("opencode", "decided_by")},
        )

        self.assertEqual(2, self._choose("2")["opencode"])

        kept = read_consumer_settings(self.env.paths.data_root)
        self.assertEqual(Ok(replace(ConsumerSettings(), opencode_runtime=2)), kept)
        code, payload = self._opencode()
        self.assertEqual("you", payload["decided_by"])

    def test_the_plugin_is_a_loader_under_opencode_plugins_and_nothing_in_opencode_json(
        self,
    ) -> None:
        self.settings.write_text(json.dumps(EXISTING, indent=2) + "\n", encoding="utf-8")
        before = self.settings.read_bytes()
        self._choose("2")

        self._install()

        self.assertEqual(before, self.settings.read_bytes(), "opencode.json was written")
        self.assertEqual(["index.js"], sorted(path.name for path in self.loader.iterdir()))
        index = (self.loader / "index.js").read_text(encoding="utf-8")
        self.assertIn(f'from "{IMPORTED}"', index)
        self.assertNotIn(str(self.env.project), index)
        # The loader's import lands on the module the tree holds.
        self.assertTrue((self.loader / IMPORTED).resolve().is_file())
        self.assertFalse((self.env.project / TREE / "index.js").exists())
        (installed,) = self._installed()
        (delivery,) = installed.receipt.deliveries
        self.assertEqual(str(self.env.project / ENTRY_MODULE), delivery.loads)
        self.assertEqual((), installed.receipt.settings)
        self.assertEqual("ready", self._health())

    def test_review_says_it_runs_code_and_writes_nothing(self) -> None:
        self._choose("2")

        code, payload = self.env.run("consume", "install", COORDINATE, "--profile", "opencode")

        self.assertEqual(code, 0, payload)
        self.assertFalse(payload["finalized"])
        self.assertIn("high-risk-execution", json.dumps(payload))
        self.assertFalse(self.loader.exists())
        self.assertFalse((self.env.project / TREE).exists())

    def test_an_edited_loader_is_drift_a_repair_puts_back(self) -> None:
        self._choose("2")
        self._install()
        index = self.loader / "index.js"
        written = index.read_bytes()
        index.write_text('export default "other"\n', encoding="utf-8")

        self.assertNotEqual("ready", self._health())
        code, review = self.env.run("doctor", "--repair", COORDINATE + "@7.0.0")
        self.assertEqual(code, 0, review)
        self.assertEqual(
            {"delivery:opencode"}, {step["component"] for step in review["review"]["steps"]}
        )
        code, applied = self.env.run(
            "doctor",
            "--repair",
            COORDINATE + "@7.0.0",
            "--yes",
            "--expect",
            review["review_digest"],
        )

        self.assertEqual(code, 0, applied)
        self.assertEqual(written, index.read_bytes())
        self.assertEqual("ready", self._health())

    def test_uninstall_takes_the_loader_and_the_tree_and_leaves_opencode_json(self) -> None:
        self.settings.write_text(json.dumps(EXISTING, indent=2) + "\n", encoding="utf-8")
        before = self.settings.read_bytes()
        self._choose("2")
        self._install()

        code, payload = self.env.run(
            "consume", "uninstall", COORDINATE, "--profile", "opencode", "--yes"
        )

        self.assertEqual(code, 0, payload)
        self.assertFalse(self.loader.exists())
        self.assertFalse((self.env.project / TREE).exists())
        self.assertEqual(before, self.settings.read_bytes())
        self.assertEqual((), self._installed())

    def test_a_plugin_installed_for_opencode_1_stays_as_it_was_and_still_uninstalls(self) -> None:
        self._install()
        self.assertEqual([REFERENCE], json.loads(self.settings.read_text())["plugin"])

        self._choose("2")

        self.assertEqual([REFERENCE], json.loads(self.settings.read_text())["plugin"])
        self.assertFalse(self.loader.exists())
        self.assertEqual("ready", self._health())
        code, payload = self.env.run(
            "consume", "uninstall", COORDINATE, "--profile", "opencode", "--yes"
        )
        self.assertEqual(code, 0, payload)
        self.assertNotIn("plugin", json.loads(self.settings.read_text()))
        self.assertFalse((self.env.project / TREE).exists())

    def test_reinstalled_for_opencode_2_it_moves_out_of_opencode_json(self) -> None:
        self._install()
        self._choose("2")
        code, payload = self.env.run(
            "consume", "uninstall", COORDINATE, "--profile", "opencode", "--yes"
        )
        self.assertEqual(code, 0, payload)

        self._install()

        self.assertNotIn("plugin", json.loads(self.settings.read_text()))
        self.assertTrue((self.loader / "index.js").is_file())

    def test_a_user_plugin_stays_in_the_list_opencode_2_reads(self) -> None:
        self._choose("2")

        code, payload = self.env.run(
            "consume", "install", COORDINATE, "--profile", "opencode", "--scope", "user", "--yes"
        )

        self.assertEqual(code, 0, payload)
        user = self.env.home / ".config/opencode/opencode.jsonc"
        self.assertIn("plugin", user.read_text(encoding="utf-8"))
        self.assertFalse((self.env.home / ".config/opencode/plugins").exists())

    def test_opencode_1_is_what_an_unchosen_public_build_installs(self) -> None:
        self.assertIsInstance(
            write_consumer_settings(ConsumerSettings(), data_root=self.env.paths.data_root), Ok
        )

        self._install()

        self.assertEqual([REFERENCE], json.loads(self.settings.read_text())["plugin"])
        self.assertFalse((self.env.project / ".opencode/plugins").exists())


if __name__ == "__main__":
    unittest.main()
