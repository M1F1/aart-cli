"""Where each harness reads each kind of artifact, measured rather than derived.

`MCP_TARGETS` is the pattern: every path here was observed in a real build and the comments say
which. A delivery written to a guessed path is worse than none, because the artifact looks installed
and the harness never reads it.

The one rule the type enforces beyond shape is that a destination names the artifact. Without it
every Skill for a harness would deliver to the same directory, and withdrawing one on uninstall
would take away the directory the harness reads all of them from.
"""

from __future__ import annotations

import unittest

from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.harness import (
    DELIVERY_TARGETS,
    HOOK_TARGETS,
    MEMORY_TARGETS,
    DeliveryTarget,
    MemoryTarget,
    Scope,
    delivery_destination,
    delivery_target,
    hook_event_path,
    hook_target,
    memory_target,
)
from agent_artifacts.domain.hooks import HookEntryShape
from agent_artifacts.domain.managed_blocks import BlockPosition


class DeliveryTargetTest(unittest.TestCase):
    def test_a_skill_is_a_tree_in_the_directory_the_harness_reads(self) -> None:
        target = delivery_target("claude", Scope.PROJECT, ArtifactKind.SKILL)
        self.assertEqual(DeliveryKind.TREE, target.delivery)
        self.assertEqual(".claude/skills/code-review", delivery_destination(target, "code-review"))

    def test_a_guideline_is_one_file_named_for_the_artifact(self) -> None:
        target = delivery_target("claude", Scope.PROJECT, ArtifactKind.GUIDELINE)
        self.assertEqual(DeliveryKind.FILE, target.delivery)
        self.assertEqual(
            ".claude/guidelines/house-style.md", delivery_destination(target, "house-style")
        )

    def test_user_scope_reads_guidelines_from_where_that_build_puts_them(self) -> None:
        target = delivery_target("claude", Scope.USER, ArtifactKind.GUIDELINE)
        self.assertEqual(
            ".claude/rules/house-style.md", delivery_destination(target, "house-style")
        )

    def test_a_harness_nobody_measured_is_named_rather_than_guessed(self) -> None:
        # Cursor is a real harness this repository has never measured, so it has no row.
        with self.assertRaises(KeyError):
            delivery_target("cursor", Scope.PROJECT, ArtifactKind.SKILL)

    def test_a_kind_this_harness_documents_no_location_for_is_refused(self) -> None:
        # Tabnine documents no user-global Agent Skills discovery location.
        with self.assertRaises(KeyError):
            delivery_target("tabnine", Scope.USER, ArtifactKind.SKILL)

    def test_a_kind_that_starts_a_process_is_not_delivered(self) -> None:
        with self.assertRaises(KeyError):
            delivery_target("claude", Scope.PROJECT, ArtifactKind.MCP)

    def test_every_measured_destination_names_the_artifact_it_delivers(self) -> None:
        for target in DELIVERY_TARGETS.values():
            self.assertIn("<name>", target.destination)

    def test_every_measured_target_is_keyed_by_what_it_says_it_is(self) -> None:
        for (harness, scope, kind), target in DELIVERY_TARGETS.items():
            self.assertEqual((harness, scope, kind), (target.harness, target.scope, target.kind))

    def test_a_shared_destination_is_refused_because_uninstall_would_take_it(self) -> None:
        with self.assertRaises(ValueError):
            DeliveryTarget(
                "claude", Scope.PROJECT, ArtifactKind.SKILL, ".claude/skills", DeliveryKind.TREE
            )

    def test_a_destination_that_escapes_its_scope_root_is_refused(self) -> None:
        for destination in ("/etc/<name>", "../<name>", ".claude/../../<name>"):
            with self.assertRaises(ValueError):
                DeliveryTarget(
                    "claude",
                    Scope.PROJECT,
                    ArtifactKind.SKILL,
                    destination,
                    DeliveryKind.TREE,
                )

    def test_a_name_that_would_escape_the_destination_is_refused(self) -> None:
        target = delivery_target("claude", Scope.PROJECT, ArtifactKind.SKILL)
        for name in ("../elsewhere", "a/b", ""):
            with self.assertRaises(ValueError):
                delivery_destination(target, name)


if __name__ == "__main__":
    unittest.main()


class MemoryTargetTest(unittest.TestCase):
    """Where each harness reads a shared instruction file, and why it is not a delivery.

    Every measured memory location is a file the user writes in, so the artifact owns a region of
    it rather than the file. That is the whole reason these live in their own table: a
    `DeliveryTarget` is required to name the artifact in its destination, and this one deliberately
    must not -- two memory artifacts for one harness share the file and each owns its own block.
    """

    def test_claude_reads_project_memory_from_the_file_at_the_project_root(self) -> None:
        target = memory_target("claude", Scope.PROJECT)
        self.assertEqual("CLAUDE.md", target.destination)

    def test_claude_reads_user_memory_from_inside_its_own_directory(self) -> None:
        self.assertEqual(".claude/CLAUDE.md", memory_target("claude", Scope.USER).destination)

    def test_tabnine_reads_project_memory_from_its_own_file(self) -> None:
        self.assertEqual("TABNINE.md", memory_target("tabnine", Scope.PROJECT).destination)

    def test_tabnine_documents_no_user_memory_file_so_none_is_invented(self) -> None:
        with self.assertRaises(KeyError):
            memory_target("tabnine", Scope.USER)

    def test_a_harness_nobody_measured_is_named_rather_than_guessed(self) -> None:
        with self.assertRaises(KeyError):
            memory_target("cursor", Scope.PROJECT)

    def test_a_block_is_appended_by_default_so_what_the_user_wrote_stays_on_top(self) -> None:
        self.assertEqual(BlockPosition.BOTTOM, memory_target("claude", Scope.PROJECT).position)

    def test_every_measured_memory_file_is_shared_rather_than_named_for_one_artifact(self) -> None:
        for target in MEMORY_TARGETS.values():
            self.assertNotIn("<name>", target.destination)

    def test_a_memory_destination_cannot_escape_its_scope_root(self) -> None:
        with self.assertRaises(ValueError):
            MemoryTarget("claude", Scope.PROJECT, "../CLAUDE.md")

    def test_a_shared_file_is_named_once_however_many_artifacts_write_into_it(self) -> None:
        # Which region each artifact owns is decided by `managed_blocks`, from the artifact's own
        # name. The target answers only where the file is.
        self.assertEqual(
            memory_target("claude", Scope.PROJECT), memory_target("claude", Scope.PROJECT)
        )


class HookTargetTest(unittest.TestCase):
    """Where each harness keeps a hook's script, and where it is told to run it.

    A hook is the one kind that is both: the script is delivered into a directory named for the
    artifact, and the entry that runs it is one member of a list in a settings file the harness and
    the user share. The table therefore carries both halves, plus the abstract-to-measured event
    mapping, because the same `PreToolUse` a package declares is spelled `BeforeTool` by one of the
    two builds this repository has observed.
    """

    def test_claude_keeps_a_hooks_script_in_a_directory_named_for_the_artifact(self) -> None:
        target = hook_target("claude", Scope.PROJECT)
        self.assertEqual(".claude/hooks/lint", delivery_destination(target.scripts_target, "lint"))

    def test_claude_is_told_about_the_hook_in_its_settings_file(self) -> None:
        self.assertEqual(".claude/settings.json", hook_target("claude", Scope.PROJECT).settings)

    def test_claude_nests_the_command_under_the_matcher(self) -> None:
        self.assertEqual(HookEntryShape.NESTED_COMMAND, hook_target("claude", Scope.PROJECT).shape)

    def test_tabnine_spells_the_same_event_by_its_own_name(self) -> None:
        self.assertEqual(
            "hooks.BeforeTool", hook_event_path(hook_target("tabnine", Scope.PROJECT), "PreToolUse")
        )
        self.assertEqual(
            "hooks.PreToolUse", hook_event_path(hook_target("claude", Scope.PROJECT), "PreToolUse")
        )

    def test_tabnine_names_the_command_beside_the_matcher(self) -> None:
        self.assertEqual(HookEntryShape.FLAT_COMMAND, hook_target("tabnine", Scope.PROJECT).shape)

    def test_an_event_this_harness_documents_no_slot_for_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            hook_event_path(hook_target("claude", Scope.PROJECT), "BeforeEverything")

    def test_tabnine_documents_no_user_hook_target_so_none_is_invented(self) -> None:
        with self.assertRaises(KeyError):
            hook_target("tabnine", Scope.USER)

    def test_a_harness_nobody_measured_is_named_rather_than_guessed(self) -> None:
        with self.assertRaises(KeyError):
            hook_target("cursor", Scope.PROJECT)

    def test_a_measured_harness_whose_hooks_are_unmeasured_gets_no_hook_row(self) -> None:
        # OpenCode's skills, memory and MCP were measured; its hook event model was not, and a
        # harness being present in one table is not permission to guess it into another.
        with self.assertRaises(KeyError):
            hook_target("opencode", Scope.PROJECT)

    def test_every_measured_hook_script_directory_names_the_artifact(self) -> None:
        for target in HOOK_TARGETS.values():
            self.assertIn("<name>", target.scripts)
