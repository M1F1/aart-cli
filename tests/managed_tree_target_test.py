"""Which directory of a harness's own AART may keep an installation's private files in.

`domain/installation_tree.py` holds the policy -- namespace, alias, name -- against a base it takes
as an argument, deliberately, so that the rule could be written before any harness fact was
measured (D-346). This is that fact, and it is the last thing standing between the policy and the
runtime: without a row here there is nowhere under the harness to put the payload, launcher,
runtime and configuration §169.3 says each installation owns separately.

Nothing here is a new observation. Every directory below is one an existing measured target for the
same harness and scope already names, and the test that says so is the guard against this table
quietly becoming a place where locations get invented.
"""

from __future__ import annotations

import unittest

from aart_cli.domain.harness import (
    DELIVERY_TARGETS,
    HOOK_TARGETS,
    MANAGED_TREE_TARGETS,
    MCP_TARGETS,
    MEMORY_TARGETS,
    ManagedTreeTarget,
    Scope,
    managed_tree_target,
)


def _measured_paths(harness: str, scope: Scope) -> set[str]:
    """Every path some other measured table gives for this harness at this scope."""

    paths = {
        target.settings_file
        for (name, target_scope), target in MCP_TARGETS.items()
        if name == harness and target_scope is scope
    }
    paths |= {
        target.destination
        for (name, target_scope), target in MEMORY_TARGETS.items()
        if name == harness and target_scope is scope
    }
    for (name, target_scope), hook in HOOK_TARGETS.items():
        if name == harness and target_scope is scope:
            paths |= {hook.scripts, hook.settings}
    paths |= {
        target.destination
        for (name, target_scope, _), target in DELIVERY_TARGETS.items()
        if name == harness and target_scope is scope
    }
    return paths


class ManagedTreeTargetTest(unittest.TestCase):
    def test_every_harness_this_build_can_place_into_has_somewhere_private(self) -> None:
        """A harness that can host an installation and has no managed root can host half of one.

        The payload, launcher, runtime and configuration are as much part of an installation as the
        file the harness reads, so a pair some other table names and this one does not would be an
        installation with nowhere to keep its own things.
        """

        placeable = (
            {pair for pair in MCP_TARGETS}
            | {pair for pair in MEMORY_TARGETS}
            | {pair for pair in HOOK_TARGETS}
            | {(harness, scope) for harness, scope, _ in DELIVERY_TARGETS}
        )

        self.assertEqual(placeable - set(MANAGED_TREE_TARGETS), set())

    def test_no_row_here_names_a_directory_nobody_measured(self) -> None:
        """The honesty guard. Every managed root is a directory some measured target for the same
        harness and scope already sits in, so this table records where files may go and never
        discovers a new place for them (D-346)."""

        for (harness, scope), target in MANAGED_TREE_TARGETS.items():
            with self.subTest(harness=harness, scope=scope.value):
                measured = _measured_paths(harness, scope)
                self.assertTrue(
                    any(path.startswith(f"{target.directory}/") for path in measured),
                    f"{target.directory} is under none of {sorted(measured)}",
                )

    def test_two_harnesses_sharing_a_scope_root_do_not_share_a_tree(self) -> None:
        """Project scope puts four harnesses in one directory, and §169.3 gives each installation
        its own files -- which it cannot have if two harnesses resolve to one root."""

        for scope in Scope:
            directories = [
                target.directory
                for (_, target_scope), target in MANAGED_TREE_TARGETS.items()
                if target_scope is scope
            ]
            with self.subTest(scope=scope.value):
                self.assertEqual(len(directories), len(set(directories)))

    def test_the_measured_rows_are_the_harnesses_own_directories(self) -> None:
        self.assertEqual(managed_tree_target("claude", Scope.PROJECT).directory, ".claude")
        self.assertEqual(managed_tree_target("claude", Scope.USER).directory, ".claude")
        self.assertEqual(managed_tree_target("tabnine", Scope.PROJECT).directory, ".tabnine")
        self.assertEqual(managed_tree_target("codex", Scope.USER).directory, ".codex")
        self.assertEqual(managed_tree_target("opencode", Scope.PROJECT).directory, ".opencode")
        self.assertEqual(managed_tree_target("opencode", Scope.USER).directory, ".config/opencode")

    def test_a_harness_nobody_measured_is_refused_by_name(self) -> None:
        with self.assertRaises(KeyError) as raised:
            managed_tree_target("cursor", Scope.PROJECT)

        self.assertIn("cursor", str(raised.exception))
        self.assertIn("project", str(raised.exception))


class ManagedTreeTargetShapeTest(unittest.TestCase):
    def test_a_managed_directory_must_stay_inside_its_scope_root(self) -> None:
        """The scope root is a project somebody else owns or the whole of a home directory, and a
        row that walked out of it would put an installation's private files anywhere at all."""

        for directory in ("/absolute", "../sibling", "a/../b", "", "a\nb", ".claude/"):
            with self.subTest(directory=directory):
                with self.assertRaises(ValueError):
                    ManagedTreeTarget("claude", Scope.PROJECT, directory)

    def test_a_row_is_about_one_measured_harness_at_one_scope(self) -> None:
        for harness, scope in (("Claude", Scope.PROJECT), ("", Scope.PROJECT), ("claude", "user")):
            with self.subTest(harness=harness, scope=scope):
                with self.assertRaises(ValueError):
                    ManagedTreeTarget(harness, scope, ".claude")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
