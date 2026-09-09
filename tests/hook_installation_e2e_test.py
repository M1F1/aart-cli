"""A hook installed, measured, drifted and removed through the public command.

The last kind the canonical pipeline could not install at all, and the only one that is two things
at once. The script is delivered into a directory named for the artifact, which AART owns outright;
what makes the harness actually run it is one entry in one list inside `settings.json`, beside the
user's own configuration and beside every other hook they installed (B-034).

What is proven here is that both halves land together and come apart together, and that the half
inside somebody else's file stays exactly that: one entry, leaving the rest of the document -- other
hooks included -- as it was found.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tests.configured_install_command_e2e_test import _Environment

HOOK_MANIFEST = {
    "schema": "aart.dev/hook/v1",
    "artifact": {"name": "guard-bash", "kind": "hook", "version": "1.2.0"},
    "payload": {"include": ["hook.json", "run.sh"]},
    "compatibility": {"harnesses": ["claude"]},
}

DECLARATION = {
    "name": "guard-bash",
    "event": "PreToolUse",
    "matcher": "Bash",
    "command": "${SCRIPT_DIR}/run.sh",
}

SCRIPT = "#!/bin/sh\nexit 0\n"

AUTHORED_HOOK: tuple[tuple[str, str] | tuple[str, str, bool], ...] = (
    ("guard-bash/aart.json", json.dumps(HOOK_MANIFEST)),
    ("guard-bash/hook.json", json.dumps(DECLARATION)),
    ("guard-bash/run.sh", SCRIPT, True),
)

COORDINATE = "company/hook/guard-bash"

#: Something the user configured for themselves, and a hook they installed by hand.
EXISTING = {
    "permissions": {"allow": ["Read"]},
    "hooks": {
        "PreToolUse": [
            {"matcher": "Write", "hooks": [{"type": "command", "command": "/usr/local/bin/mine"}]}
        ]
    },
}


class HookInstallationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.env = _Environment(pathlib.Path(temporary.name).resolve())
        self.env.publish(AUTHORED_HOOK)
        self.settings = self.env.project / ".claude/settings.json"
        self.script = self.env.project / ".claude/hooks/guard-bash/run.sh"

    def _install(self) -> tuple[int, dict]:
        return self.env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")

    def _document(self) -> dict:
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def _entries(self) -> list:
        return self._document().get("hooks", {}).get("PreToolUse", [])

    def _write_existing(self) -> None:
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps(EXISTING, indent=2) + "\n", encoding="utf-8")

    def test_the_script_is_delivered_and_the_harness_is_told_to_run_it(self) -> None:
        code, payload = self._install()

        self.assertEqual(code, 0, payload)
        self.assertEqual(SCRIPT, self.script.read_text(encoding="utf-8"))
        self.assertEqual(
            [{"matcher": "Bash", "hooks": [{"type": "command", "command": str(self.script)}]}],
            self._entries(),
        )

    def test_the_delivered_script_is_executable_or_the_harness_could_not_run_it(self) -> None:
        code, payload = self._install()

        self.assertEqual(code, 0, payload)
        self.assertTrue(self.script.stat().st_mode & 0o100)

    def test_what_the_user_already_configured_survives_the_install(self) -> None:
        self._write_existing()

        code, payload = self._install()

        self.assertEqual(code, 0, payload)
        document = self._document()
        self.assertEqual({"allow": ["Read"]}, document["permissions"])
        self.assertIn(
            {"matcher": "Write", "hooks": [{"type": "command", "command": "/usr/local/bin/mine"}]},
            document["hooks"]["PreToolUse"],
            "installing one hook displaced a hook the user installed themselves",
        )
        self.assertEqual(2, len(self._entries()))

    def test_review_names_the_hook_and_writes_nothing(self) -> None:
        self._write_existing()

        code, payload = self.env.run("marketplace", "install", COORDINATE, "--profile", "claude")

        self.assertEqual(code, 0, payload)
        self.assertFalse(payload["finalized"])
        self.assertEqual(EXISTING, self._document(), "review wrote into the user's settings")
        self.assertFalse(self.script.exists())

    def test_installing_twice_leaves_one_entry(self) -> None:
        self._install()

        code, payload = self._install()

        self.assertEqual(code, 0, payload)
        self.assertEqual(1, len(self._entries()))

    def test_a_later_invocation_reports_it_installed_and_healthy(self) -> None:
        self._install()

        code, payload = self.env.run("marketplace", "status", "--profile", "claude")

        self.assertEqual(code, 0, payload)
        self.assertEqual([COORDINATE + "@1.2.0"], [item["key"] for item in payload["items"]])
        self.assertEqual("ready", payload["items"][0]["health"])

    def test_an_edited_entry_is_measured_as_drift_rather_than_reported_healthy(self) -> None:
        self._install()
        document = self._document()
        document["hooks"]["PreToolUse"][0]["hooks"][0]["type"] = "shell"
        self.settings.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

        code, payload = self.env.run("marketplace", "status", "--profile", "claude")

        self.assertEqual(code, 0, payload)
        self.assertNotEqual("ready", payload["items"][0]["health"])

    def test_another_hook_added_beside_it_is_not_drift(self) -> None:
        self._install()
        document = self._document()
        document["hooks"]["PreToolUse"].append(
            {"matcher": "Edit", "hooks": [{"type": "command", "command": "/usr/local/bin/other"}]}
        )
        self.settings.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

        code, payload = self.env.run("marketplace", "status", "--profile", "claude")

        self.assertEqual(code, 0, payload)
        self.assertEqual(
            "ready",
            payload["items"][0]["health"],
            "somebody installing a second hook was reported as drift in the first",
        )

    def test_uninstalling_takes_the_entry_and_the_script_and_leaves_the_rest(self) -> None:
        self._write_existing()
        self._install()

        code, payload = self.env.run(
            "marketplace", "uninstall", COORDINATE, "--profile", "claude", "--yes"
        )

        self.assertEqual(code, 0, payload)
        self.assertFalse(self.script.exists())
        document = self._document()
        self.assertEqual({"allow": ["Read"]}, document["permissions"])
        self.assertEqual(
            [
                {
                    "matcher": "Write",
                    "hooks": [{"type": "command", "command": "/usr/local/bin/mine"}],
                }
            ],
            document["hooks"]["PreToolUse"],
            "uninstalling took away more of the list than the one entry it owned",
        )


if __name__ == "__main__":
    unittest.main()
