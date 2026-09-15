"""A memory artifact installed, measured, drifted, repaired and removed through the public command.

The last kind that could not be installed canonically at all. A Skill is delivered -- AART writes
the whole destination and owns every byte of it -- and every measured memory target is a file the
user writes in, so installing one means owning a delimited region of `CLAUDE.md` and leaving
everything around it exactly as it was (B-034).

What is proven here is the whole vertical: an authored memory package published to a configured
registry, resolved, reviewed, merged into a file that already holds the user's own notes, read back
from the durable record, measured as drift when somebody edits the block, and finally taken back
out leaving the user's file standing.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from agent_artifacts.domain.managed_blocks import managed_block_body
from tests.configured_install_command_e2e_test import _Environment

MEMORY_MANIFEST = {
    "schema": "aart.dev/memory/v1",
    "artifact": {"name": "house-style", "kind": "memory", "version": "1.2.0"},
    "payload": {"include": ["MEMORY.md"]},
    "compatibility": {"harnesses": ["claude"]},
}

MEMORY_BODY = "## House style\n\nName the failure, not the code.\n"

AUTHORED_MEMORY: tuple[tuple[str, str], ...] = (
    ("house-style/aart.json", json.dumps(MEMORY_MANIFEST)),
    ("house-style/MEMORY.md", MEMORY_BODY),
)

COORDINATE = "company/memory/house-style"
NOTES = "# Project notes\n\nSomething the user wrote themselves.\n"


class MergedInstallationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.env = _Environment(pathlib.Path(temporary.name).resolve())
        self.env.publish(AUTHORED_MEMORY)
        self.memory = self.env.project / "CLAUDE.md"

    def _install(self) -> tuple[int, dict]:
        return self.env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")

    def _text(self) -> str:
        return self.memory.read_text(encoding="utf-8")

    def test_the_body_lands_in_the_file_the_harness_reads(self) -> None:
        code, payload = self._install()

        self.assertEqual(code, 0, payload)
        self.assertEqual(MEMORY_BODY.strip(), managed_block_body(self._text(), "house-style").value)

    def test_what_the_user_already_wrote_survives_the_install(self) -> None:
        self.memory.write_text(NOTES, encoding="utf-8")

        code, payload = self._install()

        self.assertEqual(code, 0, payload)
        text = self._text()
        self.assertIn("Something the user wrote themselves.", text)
        self.assertTrue(
            text.index("Something the user wrote themselves.") < text.index("Name the failure"),
            "the block was written above the notes it was supposed to be appended after",
        )

    def test_review_names_the_merge_and_writes_nothing(self) -> None:
        self.memory.write_text(NOTES, encoding="utf-8")

        code, payload = self.env.run("marketplace", "install", COORDINATE, "--profile", "claude")

        self.assertEqual(code, 0, payload)
        self.assertFalse(payload["finalized"])
        self.assertEqual(NOTES, self._text(), "review wrote into the user's file")

    def test_installing_twice_leaves_one_block(self) -> None:
        self._install()
        first = self._text()

        code, payload = self._install()

        self.assertEqual(code, 0, payload)
        self.assertEqual(first, self._text())

    def test_a_later_invocation_reports_it_installed_and_healthy(self) -> None:
        self._install()

        code, payload = self.env.run("marketplace", "status", "--profile", "claude")

        self.assertEqual(code, 0, payload)
        self.assertEqual([COORDINATE + "@1.2.0"], [item["key"] for item in payload["items"]])
        self.assertEqual("ready", payload["items"][0]["health"])

    def test_an_edited_block_is_measured_as_drift_rather_than_reported_healthy(self) -> None:
        self._install()
        self.memory.write_text(
            self._text().replace("Name the failure, not the code.", "Somebody rewrote this."),
            encoding="utf-8",
        )

        code, payload = self.env.run("marketplace", "status", "--profile", "claude")

        self.assertEqual(code, 0, payload)
        self.assertNotEqual("ready", payload["items"][0]["health"])

    def test_a_note_the_user_added_beside_the_block_is_not_drift(self) -> None:
        self._install()
        self.memory.write_text(self._text() + "\nA thought I had later.\n", encoding="utf-8")

        code, payload = self.env.run("marketplace", "status", "--profile", "claude")

        self.assertEqual(code, 0, payload)
        self.assertEqual(
            "ready",
            payload["items"][0]["health"],
            "the user writing in their own file was reported as drift in the artifact",
        )

    def test_uninstalling_takes_the_block_and_leaves_the_users_file(self) -> None:
        self.memory.write_text(NOTES, encoding="utf-8")
        self._install()

        code, payload = self.env.run(
            "marketplace", "uninstall", COORDINATE, "--profile", "claude", "--yes"
        )

        self.assertEqual(code, 0, payload)
        self.assertTrue(self.memory.exists(), "uninstall deleted a file the user owns")
        text = self._text()
        self.assertIsNone(managed_block_body(text, "house-style").value)
        self.assertIn("Something the user wrote themselves.", text)


if __name__ == "__main__":
    unittest.main()
