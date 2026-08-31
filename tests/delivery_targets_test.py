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
    DeliveryTarget,
    Scope,
    delivery_destination,
    delivery_target,
)


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
        with self.assertRaises(KeyError):
            delivery_target("opencode", Scope.PROJECT, ArtifactKind.SKILL)

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
