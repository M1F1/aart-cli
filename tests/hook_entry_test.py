"""One hook's entry inside a settings file the harness and the user both own.

A hook is two things, and only one of them is a delivery. The script is placed in a directory of
its own, which `DeliverArtifact` already covers. The entry that makes the harness run it is a member
of a list inside `settings.json` -- beside every other hook, and beside whatever else the user
configured. Replacing that file would take away all of it (B-034).

The entry is modelled rather than templated. Only two shapes have been measured, both are here by
name, and building one from a `${...}` template would put an untyped renderer between what was
reviewed and what is written.
"""

from __future__ import annotations

import unittest

from agent_artifacts.domain.hooks import (
    HookEntry,
    HookEntryShape,
    hook_entry_at,
    hook_entry_to_json,
    merge_hook_entry,
    remove_hook_entry,
)
from agent_artifacts.domain.result import Err, Ok

PATH = "hooks.PreToolUse"
ENTRY = HookEntry(HookEntryShape.NESTED_COMMAND, "Bash", "/artifacts/lint/run.sh")
FLAT = HookEntry(HookEntryShape.FLAT_COMMAND, "Bash", "/artifacts/lint/run.sh")
SOMEBODY_ELSE = {"matcher": "Write", "hooks": [{"type": "command", "command": "/mine/check.sh"}]}


def _merged(document: dict, entry: HookEntry = ENTRY) -> dict:
    result = merge_hook_entry(document, PATH, entry)
    assert isinstance(result, Ok), getattr(result, "diagnostics", ())
    return result.value


class HookEntryShapeTest(unittest.TestCase):
    def test_claude_nests_the_command_under_the_matcher(self) -> None:
        self.assertEqual(
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "/artifacts/lint/run.sh"}],
            },
            hook_entry_to_json(ENTRY),
        )

    def test_tabnine_names_the_command_beside_the_matcher(self) -> None:
        self.assertEqual(
            {"matcher": "Bash", "command": "/artifacts/lint/run.sh"}, hook_entry_to_json(FLAT)
        )

    def test_a_command_must_be_absolute_because_the_harness_chooses_the_directory(self) -> None:
        with self.assertRaises(ValueError):
            HookEntry(HookEntryShape.NESTED_COMMAND, "Bash", "run.sh")


class MergeHookEntryTest(unittest.TestCase):
    def test_an_empty_settings_file_gains_the_list_and_the_entry(self) -> None:
        merged = _merged({})

        self.assertEqual([hook_entry_to_json(ENTRY)], merged["hooks"]["PreToolUse"])

    def test_what_somebody_else_configured_survives(self) -> None:
        merged = _merged({"hooks": {"PreToolUse": [SOMEBODY_ELSE]}, "model": "opus"})

        self.assertIn(SOMEBODY_ELSE, merged["hooks"]["PreToolUse"])
        self.assertEqual("opus", merged["model"])

    def test_another_event_in_the_same_file_is_left_alone(self) -> None:
        merged = _merged({"hooks": {"Stop": [SOMEBODY_ELSE]}})

        self.assertEqual([SOMEBODY_ELSE], merged["hooks"]["Stop"])

    def test_merging_twice_leaves_one_entry(self) -> None:
        once = _merged({})

        self.assertEqual(once, _merged(once))

    def test_the_source_document_is_not_mutated(self) -> None:
        document: dict = {"hooks": {"PreToolUse": [SOMEBODY_ELSE]}}

        _merged(document)

        self.assertEqual([SOMEBODY_ELSE], document["hooks"]["PreToolUse"])

    def test_a_list_that_is_not_a_list_is_refused_rather_than_replaced(self) -> None:
        self.assertIsInstance(
            merge_hook_entry({"hooks": {"PreToolUse": {"not": "a list"}}}, PATH, ENTRY), Err
        )

    def test_a_path_crossing_something_that_is_not_an_object_is_refused(self) -> None:
        self.assertIsInstance(merge_hook_entry({"hooks": "off"}, PATH, ENTRY), Err)

    def test_a_document_that_is_not_an_object_is_refused(self) -> None:
        self.assertIsInstance(merge_hook_entry([], PATH, ENTRY), Err)


class HookEntryAtTest(unittest.TestCase):
    def test_an_entry_that_is_there_is_found(self) -> None:
        found = hook_entry_at(_merged({}), PATH, ENTRY)

        self.assertIsInstance(found, Ok)
        self.assertEqual(hook_entry_to_json(ENTRY), found.value)

    def test_an_entry_that_is_not_there_is_absent_rather_than_an_error(self) -> None:
        found = hook_entry_at({"hooks": {"PreToolUse": [SOMEBODY_ELSE]}}, PATH, ENTRY)

        self.assertIsInstance(found, Ok)
        self.assertIsNone(found.value)

    def test_an_empty_document_has_no_entry(self) -> None:
        self.assertIsNone(hook_entry_at({}, PATH, ENTRY).value)

    def test_an_entry_somebody_edited_reads_back_as_the_edit(self) -> None:
        # Identity is the matcher and the command, so a changed `type` is the same entry, changed.
        document = _merged({})
        document["hooks"]["PreToolUse"][0]["hooks"][0]["type"] = "shell"

        self.assertEqual("shell", hook_entry_at(document, PATH, ENTRY).value["hooks"][0]["type"])

    def test_a_changed_command_is_a_different_entry_rather_than_a_changed_one(self) -> None:
        document = _merged({})
        document["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "/somewhere/else.sh"

        self.assertIsNone(hook_entry_at(document, PATH, ENTRY).value)


class RemoveHookEntryTest(unittest.TestCase):
    def test_removal_takes_the_entry_and_leaves_the_others(self) -> None:
        document = _merged({"hooks": {"PreToolUse": [SOMEBODY_ELSE]}})

        removed = remove_hook_entry(document, PATH, ENTRY)

        assert isinstance(removed, Ok)
        self.assertEqual([SOMEBODY_ELSE], removed.value["hooks"]["PreToolUse"])

    def test_removing_an_entry_that_is_not_there_converges(self) -> None:
        document = {"hooks": {"PreToolUse": [SOMEBODY_ELSE]}}

        removed = remove_hook_entry(document, PATH, ENTRY)

        assert isinstance(removed, Ok)
        self.assertEqual(document, removed.value)

    def test_removing_the_last_entry_leaves_the_empty_list_rather_than_the_users_file(self) -> None:
        removed = remove_hook_entry(_merged({"model": "opus"}), PATH, ENTRY)

        assert isinstance(removed, Ok)
        self.assertEqual([], removed.value["hooks"]["PreToolUse"])
        self.assertEqual("opus", removed.value["model"])

    def test_removing_from_a_file_that_never_had_the_list_converges(self) -> None:
        removed = remove_hook_entry({"model": "opus"}, PATH, ENTRY)

        assert isinstance(removed, Ok)
        self.assertEqual({"model": "opus"}, removed.value)

    def test_a_list_that_is_not_a_list_is_refused_on_the_way_out_too(self) -> None:
        self.assertIsInstance(remove_hook_entry({"hooks": {"PreToolUse": "off"}}, PATH, ENTRY), Err)


if __name__ == "__main__":
    unittest.main()
