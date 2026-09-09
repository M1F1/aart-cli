"""The adapter that owns one entry of one list inside a settings file the harness reads.

The other half of a hook, and the half that reaches into a document holding the user's own
configuration and every other hook they installed. Like the managed-block interpreter, it cannot
prove ownership structurally -- the file is not AART's -- so it proves it the way every interpreter
that touches somebody else's path does (D-072): it is handed the entries it may write, and one it
was not given is refused rather than written.

What the tests here are really about is everything it must not do to a file it does not own: change
its permissions, follow a symlink out of the tree, displace an entry somebody else put there, or
improvise when the document is not what the harness expects.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

from agent_artifacts.domain.effects import (
    DeliverArtifact,
    DeliveryKind,
    MergeSettingsEntry,
    UnmergeSettingsEntry,
)
from agent_artifacts.domain.hooks import HookEntry, HookEntryShape
from agent_artifacts.domain.receipts import ArtifactSettingsEntry
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.execution import SettingsEntryInterpreter

ARTIFACT = "company/hook/guard-bash"
PATH = "hooks.PreToolUse"
COMMAND = "/opt/hooks/guard-bash/run.sh"
MINE = {"matcher": "Write", "hooks": [{"type": "command", "command": "/usr/local/bin/mine"}]}


class SettingsEntryInterpreterTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = pathlib.Path(self._temporary.name)
        self.destination = self.root / "project/.claude/settings.json"
        self.destination.parent.mkdir(parents=True)
        self.entry = HookEntry(HookEntryShape.NESTED_COMMAND, "Bash", COMMAND)
        self.owned = ArtifactSettingsEntry("claude", str(self.destination), PATH, self.entry)
        self.interpreter = SettingsEntryInterpreter(ARTIFACT, (self.owned,))

    def _effect(self, **overrides) -> MergeSettingsEntry:
        values = {
            "harness": "claude",
            "artifact": ARTIFACT,
            "destination": str(self.destination),
            "path": PATH,
            "entry": self.entry,
        }
        values.update(overrides)
        return MergeSettingsEntry(**values)

    def _document(self) -> dict:
        return json.loads(self.destination.read_text(encoding="utf-8"))

    def _entries(self) -> list:
        return self._document()["hooks"]["PreToolUse"]

    def _write(self, document: dict) -> None:
        self.destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def test_it_writes_the_entry_into_a_file_that_does_not_exist_yet(self) -> None:
        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Ok)
        self.assertEqual(
            [{"matcher": "Bash", "hooks": [{"type": "command", "command": COMMAND}]}],
            self._entries(),
        )

    def test_what_the_user_configured_survives(self) -> None:
        self._write({"permissions": {"allow": ["Read"]}, "hooks": {"PreToolUse": [MINE]}})

        self.interpreter.apply(self._effect())

        document = self._document()
        self.assertEqual({"allow": ["Read"]}, document["permissions"])
        self.assertIn(MINE, self._entries())
        self.assertEqual(2, len(self._entries()))

    def test_a_file_the_user_owns_keeps_the_mode_they_chose(self) -> None:
        self._write({})
        os.chmod(self.destination, 0o640)

        self.interpreter.apply(self._effect())

        self.assertEqual(0o640, os.stat(self.destination).st_mode & 0o777)

    def test_a_file_written_for_the_first_time_is_readable_by_the_harness(self) -> None:
        self.interpreter.apply(self._effect())

        self.assertEqual(0o644, os.stat(self.destination).st_mode & 0o777)

    def test_applying_it_twice_leaves_one_entry(self) -> None:
        self.interpreter.apply(self._effect())
        first = self.destination.read_text(encoding="utf-8")

        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Ok)
        self.assertEqual(first, self.destination.read_text(encoding="utf-8"))

    def test_an_empty_file_is_configured_rather_than_refused(self) -> None:
        self.destination.write_text("\n", encoding="utf-8")

        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Ok)
        self.assertEqual(1, len(self._entries()))

    def test_an_entry_this_interpreter_was_not_given_is_refused(self) -> None:
        other = HookEntry(HookEntryShape.NESTED_COMMAND, "Edit", COMMAND)

        applied = self.interpreter.apply(self._effect(entry=other))

        self.assertIsInstance(applied, Err)
        self.assertFalse(self.destination.exists())

    def test_a_path_this_interpreter_was_not_given_is_refused(self) -> None:
        applied = self.interpreter.apply(self._effect(path="hooks.Stop"))

        self.assertIsInstance(applied, Err)
        self.assertFalse(self.destination.exists())

    def test_a_destination_this_interpreter_was_not_given_is_refused(self) -> None:
        elsewhere = self.root / "project/.claude/other.json"

        applied = self.interpreter.apply(self._effect(destination=str(elsewhere)))

        self.assertIsInstance(applied, Err)
        self.assertFalse(elsewhere.exists())

    def test_another_artifacts_entry_is_refused(self) -> None:
        applied = self.interpreter.apply(self._effect(artifact="company/hook/other"))

        self.assertIsInstance(applied, Err)
        self.assertFalse(self.destination.exists())

    def test_a_delivery_is_not_this_interpreters_business(self) -> None:
        delivery = DeliverArtifact(
            "claude", ARTIFACT, "/tmp/source", str(self.destination), DeliveryKind.FILE
        )

        self.assertFalse(self.interpreter.supports(delivery))
        self.assertIsInstance(self.interpreter.apply(delivery), Err)

    def test_a_file_that_is_not_json_is_left_exactly_as_it_is(self) -> None:
        self.destination.write_text("{not json at all\n", encoding="utf-8")

        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Err)
        self.assertEqual("{not json at all\n", self.destination.read_text(encoding="utf-8"))

    def test_a_document_that_is_not_an_object_is_refused_rather_than_replaced(self) -> None:
        self.destination.write_text("[1, 2, 3]\n", encoding="utf-8")

        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Err)
        self.assertEqual("[1, 2, 3]\n", self.destination.read_text(encoding="utf-8"))

    def test_a_list_holding_something_else_is_refused_rather_than_displaced(self) -> None:
        self._write({"hooks": {"PreToolUse": "everything"}})

        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Err)
        self.assertEqual({"hooks": {"PreToolUse": "everything"}}, self._document())

    def test_a_symlinked_destination_is_refused_rather_than_followed(self) -> None:
        outside = self.root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        link = self.root / "project/.claude/linked.json"
        os.symlink(outside, link)
        interpreter = SettingsEntryInterpreter(
            ARTIFACT, (ArtifactSettingsEntry("claude", str(link), PATH, self.entry),)
        )

        applied = interpreter.apply(self._effect(destination=str(link)))

        self.assertIsInstance(applied, Err)
        self.assertEqual("{}\n", outside.read_text(encoding="utf-8"))

    def test_a_directory_where_the_settings_file_should_be_is_refused(self) -> None:
        directory = self.root / "project/.claude/directory.json"
        directory.mkdir()
        interpreter = SettingsEntryInterpreter(
            ARTIFACT, (ArtifactSettingsEntry("claude", str(directory), PATH, self.entry),)
        )

        applied = interpreter.apply(self._effect(destination=str(directory)))

        self.assertIsInstance(applied, Err)
        self.assertTrue(directory.is_dir())

    def test_an_interpreter_holding_no_entries_is_refused_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            SettingsEntryInterpreter(ARTIFACT, ())


class UnmergeSettingsEntryTest(SettingsEntryInterpreterTest):
    """The same rules, taking the entry back out."""

    def _effect(self, **overrides) -> UnmergeSettingsEntry:  # type: ignore[override]
        values = {
            "harness": "claude",
            "artifact": ARTIFACT,
            "destination": str(self.destination),
            "path": PATH,
            "entry": self.entry,
        }
        values.update(overrides)
        return UnmergeSettingsEntry(**values)

    def test_it_writes_the_entry_into_a_file_that_does_not_exist_yet(self) -> None:
        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Ok)
        self.assertFalse(self.destination.exists(), "removing an entry created the file to do it")

    def test_what_the_user_configured_survives(self) -> None:
        self._write({"permissions": {"allow": ["Read"]}, "hooks": {"PreToolUse": [MINE]}})

        self.interpreter.apply(self._effect())

        document = self._document()
        self.assertEqual({"allow": ["Read"]}, document["permissions"])
        self.assertEqual([MINE], self._entries())

    def test_a_file_the_user_owns_keeps_the_mode_they_chose(self) -> None:
        self._write({"hooks": {"PreToolUse": [self._written()]}})
        os.chmod(self.destination, 0o640)

        self.interpreter.apply(self._effect())

        self.assertEqual(0o640, os.stat(self.destination).st_mode & 0o777)

    def test_a_file_written_for_the_first_time_is_readable_by_the_harness(self) -> None:
        self._write({"hooks": {"PreToolUse": [self._written()]}})

        self.interpreter.apply(self._effect())

        self.assertEqual([], self._entries())

    def test_applying_it_twice_leaves_one_entry(self) -> None:
        self._write({"hooks": {"PreToolUse": [self._written()]}})
        self.interpreter.apply(self._effect())
        first = self.destination.read_text(encoding="utf-8")

        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Ok)
        self.assertEqual(first, self.destination.read_text(encoding="utf-8"))

    def test_an_empty_file_is_configured_rather_than_refused(self) -> None:
        self.destination.write_text("\n", encoding="utf-8")

        applied = self.interpreter.apply(self._effect())

        self.assertIsInstance(applied, Ok)
        self.assertEqual("\n", self.destination.read_text(encoding="utf-8"))

    def test_the_list_itself_is_left_for_the_harness_that_owns_it(self) -> None:
        self._write({"hooks": {"PreToolUse": [self._written()]}})

        self.interpreter.apply(self._effect())

        self.assertEqual([], self._document()["hooks"]["PreToolUse"])

    def _written(self) -> dict:
        return {"matcher": "Bash", "hooks": [{"type": "command", "command": COMMAND}]}


if __name__ == "__main__":
    unittest.main()
