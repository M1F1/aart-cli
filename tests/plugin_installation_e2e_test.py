"""§171: a plugin installed, measured, drifted and removed through the public command.

A plugin is the one kind whose files reach no directory the harness reads. Its tree stays in the
installation's private directory, exactly as reviewed, and what turns it on is one member of the
`plugin` list in `opencode.json`, spelled relative to that file (§171.3). So what is proven here is
that the two land together and come apart together, that the list keeps every plugin somebody
else put there (INV-257), and that the review says the registration runs code (INV-256).
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from aart_cli.domain.plugin_members import PluginMember
from aart_cli.domain.result import Ok
from aart_cli.io import telemetry_sync
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.io.telemetry_store import TelemetryOutbox
from aart_cli.io.usage_hook import record
from aart_cli.io.usage_hooks import read_artifact_usage
from tests.configured_install_command_e2e_test import _Environment
from tests.telemetry_sync_test import CLIENT, Clock, FakeServer, _sync


def _files(root: pathlib.Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


MANIFEST = {
    "schema": "aart-cli.dev/plugin/v1",
    "artifact": {"name": "superpowers", "kind": "plugin", "x-fixture-version": "7.0.0"},
    "payload": {"include": [".opencode/plugins/superpowers.js", "skills/**"]},
    "plugin": {"entry": ".opencode/plugins/superpowers.js"},
    "compatibility": {"harnesses": ["opencode"]},
}

MODULE = "export const Plugin = async () => ({});\nexport default Plugin;\n"

AUTHORED: tuple[tuple[str, str] | tuple[str, str, bool], ...] = (
    ("superpowers/aart-cli.json", json.dumps(MANIFEST)),
    ("superpowers/.opencode/plugins/superpowers.js", MODULE),
    ("superpowers/skills/brainstorming/SKILL.md", "---\nname: brainstorming\n---\n"),
    ("superpowers/skills/writing-plans/SKILL.md", "---\nname: writing-plans\n---\n"),
)

COORDINATE = "company/plugin/superpowers"
TREE = ".opencode/aart-cli/plugin/company/superpowers"
REFERENCE = f"./{TREE}/payload/.opencode/plugins/superpowers.js"

#: What the user configured for themselves: an npm plugin and a local one.
EXISTING = {
    "$schema": "https://opencode.ai/config.json",
    "plugin": ["opencode-wakatime", "./mine/plugin.ts"],
}


class PluginInstallationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.env = _Environment(pathlib.Path(temporary.name).resolve())
        self.env.publish(AUTHORED)
        self.settings = self.env.project / "opencode.json"

    def _install(self, *extra: str) -> tuple[int, dict]:
        return self.env.run("consume", "install", COORDINATE, "--profile", "opencode", *extra)

    def _document(self) -> dict:
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def _write_existing(self) -> None:
        self.settings.write_text(json.dumps(EXISTING, indent=2) + "\n", encoding="utf-8")

    def test_the_tree_stays_private_and_the_list_names_its_entry(self) -> None:
        code, payload = self._install("--yes")

        self.assertEqual(code, 0, payload)
        module = self.env.project / REFERENCE
        self.assertEqual(MODULE, module.read_text(encoding="utf-8"))
        self.assertTrue(
            (self.env.project / TREE / "payload/skills/brainstorming/SKILL.md").is_file()
        )
        self.assertEqual([REFERENCE], self._document()["plugin"])
        self.assertFalse(
            (self.env.project / ".opencode/plugins").exists(),
            "a plugin's files reached a directory OpenCode scans on its own",
        )

    def test_the_receipt_records_the_skills_it_carries_and_places_none_of_them(self) -> None:
        before = _files(self.env.root)

        code, payload = self._install("--yes")

        self.assertEqual(code, 0, payload)
        (record,) = self._installed()
        self.assertEqual(
            (
                PluginMember("brainstorming", "skills/brainstorming"),
                PluginMember("writing-plans", "skills/writing-plans"),
            ),
            record.receipt.members,
        )
        added = {
            path
            for path in _files(self.env.root) - before
            if path.startswith("project/") and not path.startswith(f"project/{TREE}/")
        }
        self.assertEqual({"project/opencode.json"}, added, "a member was placed outside its tree")

    def _installed(self):
        records = LocalReceiptStore(
            str(pathlib.Path(self.env.xdg["AART_CLI_HOME"]) / "state")
        ).installations()
        self.assertIsInstance(records, Ok, records)
        return records.value

    def test_review_says_it_runs_code_and_writes_nothing(self) -> None:
        self._write_existing()

        code, payload = self._install()

        self.assertEqual(code, 0, payload)
        self.assertFalse(payload["finalized"])
        self.assertIn("high-risk-execution", json.dumps(payload))
        self.assertEqual(EXISTING, self._document(), "review wrote into the user's settings")
        self.assertFalse((self.env.project / TREE).exists())

    def test_everybody_elses_plugins_survive_install_and_uninstall(self) -> None:
        self._write_existing()

        code, payload = self._install("--yes")
        self.assertEqual(code, 0, payload)
        self.assertEqual([*EXISTING["plugin"], REFERENCE], self._document()["plugin"])

        code, payload = self.env.run(
            "consume", "uninstall", COORDINATE, "--profile", "opencode", "--yes"
        )

        self.assertEqual(code, 0, payload)
        self.assertEqual(EXISTING, self._document())
        self.assertFalse((self.env.project / TREE).exists())

    def test_installing_twice_leaves_one_entry(self) -> None:
        self._install("--yes")

        code, payload = self._install("--yes")

        self.assertEqual(code, 0, payload)
        self.assertEqual([REFERENCE], self._document()["plugin"])

    def test_a_later_invocation_reports_it_healthy_and_a_removed_entry_as_not(self) -> None:
        self._install("--yes")

        code, payload = self.env.run("consume", "status", "--profile", "opencode")
        self.assertEqual(code, 0, payload)
        self.assertEqual([COORDINATE + "@7.0.0"], [item["key"] for item in payload["items"]])
        self.assertEqual("ready", payload["items"][0]["health"])

        self.settings.write_text(json.dumps({"plugin": []}) + "\n", encoding="utf-8")
        code, payload = self.env.run("consume", "status", "--profile", "opencode")

        self.assertEqual(code, 0, payload)
        self.assertNotEqual("ready", payload["items"][0]["health"])

    def test_status_names_the_members(self) -> None:
        self._install("--yes")

        code, payload = self.env.run("consume", "status", "--profile", "opencode")

        self.assertEqual(code, 0, payload)
        self.assertEqual(["brainstorming", "writing-plans"], payload["items"][0]["members"])

    def test_a_members_use_is_recorded_and_sent_as_the_plugins(self) -> None:
        self._install("--yes")
        home = self.env.xdg["AART_CLI_HOME"]
        state = str(pathlib.Path(home) / "state")
        enabled = TelemetryOutbox(state).enable("http://127.0.0.1:9", CLIENT)
        self.assertIsInstance(enabled, Ok, enabled)

        with mock.patch.object(telemetry_sync, "spawn_sync", return_value=False):
            for skill in ("brainstorming", "brainstorming", "their-own"):
                payload = {"tool": "skill", "skill": skill, "directory": "/work/p"}
                self.assertTrue(record("opencode", home, json.dumps(payload).encode()))

        ranking = read_artifact_usage(data_root=home, user_home=str(self.env.home)).ranking
        self.assertEqual(
            [("company/plugin/superpowers:brainstorming", 2, True), ("their-own", 1, False)],
            [(item.artifact, item.uses, item.installed) for item in ranking],
        )
        server = FakeServer()
        _sync_home = SimpleNamespace(path=home)
        _sync(_sync_home, server, Clock())  # type: ignore[arg-type]
        self.assertEqual(
            [("artifact.used", "skill", "superpowers:brainstorming", "7.0.0")] * 2,
            [
                (
                    event["event_type"],
                    event["artifact_type"],
                    event["artifact_id"],
                    event["artifact_version"],
                )
                for event in server.stored.values()
            ],
        )

    def test_a_harness_nobody_measured_a_plugin_list_for_is_refused_by_name(self) -> None:
        manifest = dict(MANIFEST, compatibility={"harnesses": ["opencode", "claude"]})
        other = self.env.project.parent / "other"
        other.mkdir()
        env = _Environment(other)
        env.publish((("superpowers/aart-cli.json", json.dumps(manifest)), *AUTHORED[1:]))

        code, payload = env.run("consume", "install", COORDINATE, "--profile", "claude")

        self.assertNotEqual(code, 0, payload)
        self.assertIn("plugin target", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
