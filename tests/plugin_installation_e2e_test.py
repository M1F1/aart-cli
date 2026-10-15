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

from aart_cli.domain.harness import Scope
from aart_cli.domain.hooks import PluginEntry
from aart_cli.domain.receipts import ArtifactSettingsEntry, PlacedArtifactReceipt
from aart_cli.io.configured_setup import _effect_proofs
from aart_cli.protocol.hashing import sha256_bytes
from tests.configured_install_command_e2e_test import _Environment

MANIFEST = {
    "schema": "aart-cli.dev/plugin/v1",
    "artifact": {"name": "superpowers", "kind": "plugin", "version": "7.0.0"},
    "payload": {"include": [".opencode/plugins/superpowers.js", "skills/**"]},
    "plugin": {"entry": ".opencode/plugins/superpowers.js"},
    "compatibility": {"harnesses": ["opencode"]},
}

MODULE = "export const Plugin = async () => ({});\nexport default Plugin;\n"

AUTHORED: tuple[tuple[str, str] | tuple[str, str, bool], ...] = (
    ("superpowers/aart-cli.json", json.dumps(MANIFEST)),
    ("superpowers/.opencode/plugins/superpowers.js", MODULE),
    ("superpowers/skills/brainstorming/SKILL.md", "---\nname: brainstorming\n---\n"),
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
        return self.env.run("marketplace", "install", COORDINATE, "--profile", "opencode", *extra)

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
            "marketplace", "uninstall", COORDINATE, "--profile", "opencode", "--yes"
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

        code, payload = self.env.run("marketplace", "status", "--profile", "opencode")
        self.assertEqual(code, 0, payload)
        self.assertEqual([COORDINATE + "@7.0.0"], [item["key"] for item in payload["items"]])
        self.assertEqual("ready", payload["items"][0]["health"])

        self.settings.write_text(json.dumps({"plugin": []}) + "\n", encoding="utf-8")
        code, payload = self.env.run("marketplace", "status", "--profile", "opencode")

        self.assertEqual(code, 0, payload)
        self.assertNotEqual("ready", payload["items"][0]["health"])

    def test_a_harness_nobody_measured_a_plugin_list_for_is_refused_by_name(self) -> None:
        manifest = dict(MANIFEST, compatibility={"harnesses": ["opencode", "claude"]})
        other = self.env.project.parent / "other"
        other.mkdir()
        env = _Environment(other)
        env.publish((("superpowers/aart-cli.json", json.dumps(manifest)), *AUTHORED[1:]))

        code, payload = env.run("marketplace", "install", COORDINATE, "--profile", "claude")

        self.assertNotEqual(code, 0, payload)
        self.assertIn("plugin target", json.dumps(payload))


class APluginIsSetupEvidenceTest(unittest.TestCase):
    """Setup completion reads an installation's effects; a plugin's only one is its entry.

    Measured live on 2026-10-15: with deliveries and merges the only effects read, a plugin
    install reported `setup completion is unavailable`, because its receipt proved nothing.
    """

    def test_the_entry_is_proved_as_one_member_of_the_list(self) -> None:
        receipt = PlacedArtifactReceipt(
            COORDINATE,
            f"/p/{TREE}",
            sha256_bytes(b"payload"),
            settings=(
                ArtifactSettingsEntry(
                    "opencode", "/p/opencode.json", "plugin", PluginEntry(REFERENCE)
                ),
            ),
        )
        host = SimpleNamespace(scope=Scope.PROJECT, project_root="/p")

        (proof,) = _effect_proofs(receipt, profile="opencode", host=host)  # type: ignore[arg-type]

        self.assertEqual(
            ("merge-json", "opencode.json", "plugin", "list"),
            (proof.kind, proof.destination, proof.json_path, proof.merge_mode),
        )
        self.assertEqual((), _effect_proofs(receipt, profile="claude", host=host))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
