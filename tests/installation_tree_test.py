"""An installation's own tree lives under the harness that selected it, and owns nothing else.

§169.3 reverses what `domain/placement.py` assumed. The tree used to sit beside the receipt, on the
argument that one artifact may register with several harnesses and the tree is not any one of
theirs. The accepted contract is the opposite: each *installation* is its own owner, a second
harness is a second installation with its own tree, and a tree under the harness is what lets that
harness's own uninstall take its own files and nothing more.

This module holds the rule. Which directory each harness tolerates is measured per harness and
wired by CP-26.19; here the base is an argument, so the policy can be held without inventing a
harness fact (D-346).
"""

from __future__ import annotations

import unittest

from aart_cli.domain.identifiers import ArtifactCoordinate, ArtifactIdentity, SourceAlias
from aart_cli.domain.installation_tree import (
    MANAGED_TREE_DIRECTORY,
    installation_tree_root,
)

COMPANY = ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", "github"))
LOCAL = ArtifactCoordinate(SourceAlias("company-local"), ArtifactIdentity("mcp", "github"))


class InstallationTreeTest(unittest.TestCase):
    def test_the_tree_is_namespaced_alias_qualified_and_under_the_harness(self) -> None:
        self.assertEqual(
            installation_tree_root(COMPANY, harness_root="/work/project/.tabnine/agent"),
            "/work/project/.tabnine/agent/aart-cli/mcp/company/github",
        )
        self.assertEqual(
            installation_tree_root(COMPANY, harness_root="/users/alice/.claude"),
            "/users/alice/.claude/aart-cli/mcp/company/github",
        )

    def test_two_aliases_for_the_same_upstream_get_two_trees(self) -> None:
        """Byte-identical packages are still two installations, so they may not share a tree."""

        self.assertNotEqual(
            installation_tree_root(COMPANY, harness_root="/users/alice/.claude"),
            installation_tree_root(LOCAL, harness_root="/users/alice/.claude"),
        )

    def test_two_harness_roots_get_two_trees_for_the_same_coordinate(self) -> None:
        self.assertNotEqual(
            installation_tree_root(COMPANY, harness_root="/users/alice/.claude"),
            installation_tree_root(COMPANY, harness_root="/work/project/.tabnine/agent"),
        )

    def test_the_version_is_absent_because_an_update_reconciles_one_installation(self) -> None:
        versioned = ArtifactCoordinate(
            SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.5.0"
        )

        self.assertEqual(
            installation_tree_root(versioned, harness_root="/users/alice/.claude"),
            installation_tree_root(COMPANY, harness_root="/users/alice/.claude"),
        )

    def test_the_namespace_is_the_products_own(self) -> None:
        self.assertEqual(MANAGED_TREE_DIRECTORY, "aart-cli")
        self.assertIn(
            f"/{MANAGED_TREE_DIRECTORY}/",
            installation_tree_root(COMPANY, harness_root="/users/alice/.claude"),
        )


class InstallationTreeRefusalTest(unittest.TestCase):
    def test_a_harness_root_that_is_not_a_normalized_absolute_path_is_refused(self) -> None:
        for root in (
            "relative/.claude",
            "/users/alice/../alice/.claude",
            "/users/alice/.claude/",
            "",
            "/users/alice/.clau\nde",
        ):
            with self.subTest(harness_root=root):
                with self.assertRaises(ValueError):
                    installation_tree_root(COMPANY, harness_root=root)

    def test_an_alias_that_would_escape_the_managed_root_is_refused(self) -> None:
        """The alias is operator input; a `..` in it would place a tree outside the harness."""

        for alias in ("..", "a/b", "/absolute", ".", "", "a\nb", "a b"):
            with self.subTest(alias=alias):
                coordinate = ArtifactCoordinate(
                    SourceAlias(alias), ArtifactIdentity("mcp", "github")
                )
                with self.assertRaises(ValueError):
                    installation_tree_root(coordinate, harness_root="/users/alice/.claude")

    def test_an_artifact_name_that_would_escape_the_managed_root_is_refused(self) -> None:
        for name in ("..", "a/b", "/absolute", ".", "", "a\nb"):
            with self.subTest(name=name):
                coordinate = ArtifactCoordinate(
                    SourceAlias("company"), ArtifactIdentity("mcp", name)
                )
                with self.assertRaises(ValueError):
                    installation_tree_root(coordinate, harness_root="/users/alice/.claude")

    def test_something_that_is_not_a_coordinate_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            installation_tree_root("company/mcp/github", harness_root="/users/alice/.claude")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
