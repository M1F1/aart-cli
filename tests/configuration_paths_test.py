"""One home, the same on both platforms, and one thing the person running the command cannot move.

§169.2 replaced three roots and a platform branch with a single answer. These tests hold the two
halves of that: the home is `AART_CLI_HOME` if it is set and `<user-home>/.aart-cli` otherwise,
identically on macOS and Linux -- and machine policy is not in it, because an administrator writes
that and an environment variable must not be able to step around it.
"""

from __future__ import annotations

import unittest

from aart_cli.configuration.paths import (
    APPLICATION_HOME_DIRECTORY,
    APPLICATION_HOME_VARIABLE,
    MANAGED_HOME_ENTRIES,
    Platform,
    resolve_config_paths,
)


class ApplicationHomeTest(unittest.TestCase):
    def test_the_default_home_is_one_directory_under_the_injected_user_home(self) -> None:
        paths = resolve_config_paths(Platform.DARWIN, home="/fake/home")

        self.assertEqual(paths.application_home, "/fake/home/.aart-cli")
        self.assertEqual(paths.user_config_file, "/fake/home/.aart-cli/config.json")
        self.assertEqual(paths.data_root, "/fake/home/.aart-cli")
        self.assertEqual(paths.cache_root, "/fake/home/.aart-cli/cache")

    def test_macos_and_linux_resolve_the_same_relative_layout(self) -> None:
        """The layout used to depend on the machine, so the same installation had two shapes."""

        darwin = resolve_config_paths(Platform.DARWIN, home="/fake/home")
        linux = resolve_config_paths(Platform.LINUX, home="/fake/home")

        self.assertEqual(darwin.application_home, linux.application_home)
        self.assertEqual(darwin.user_config_file, linux.user_config_file)
        self.assertEqual(darwin.data_root, linux.data_root)
        self.assertEqual(darwin.cache_root, linux.cache_root)

    def test_an_explicit_home_is_taken_whole_and_does_not_look_at_the_user_home(self) -> None:
        """A CI job selects a private directory; nothing of it may land in the developer's home."""

        paths = resolve_config_paths(
            Platform.LINUX, home="/fake/home", application_home="/runner/work/aart-state"
        )

        self.assertEqual(paths.application_home, "/runner/work/aart-state")
        self.assertEqual(paths.user_config_file, "/runner/work/aart-state/config.json")
        self.assertEqual(paths.data_root, "/runner/work/aart-state")
        self.assertEqual(paths.cache_root, "/runner/work/aart-state/cache")
        for path in (paths.user_config_file, paths.data_root, paths.cache_root):
            self.assertNotIn("/fake/home", path)

    def test_a_home_that_is_not_a_normalized_absolute_path_is_refused_not_repaired(self) -> None:
        """Repairing it would write one job's state somewhere another job also resolved to."""

        for value in ("relative/state", "/runner/../runner/state", "/runner/state/", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    resolve_config_paths(Platform.LINUX, home="/fake/home", application_home=value)

    def test_an_unusable_user_home_is_refused_as_well(self) -> None:
        with self.assertRaises(ValueError):
            resolve_config_paths(Platform.LINUX, home="relative/home")

    def test_no_platform_or_xdg_root_survives_anywhere_in_the_resolved_paths(self) -> None:
        for platform in Platform:
            paths = resolve_config_paths(platform, home="/fake/home")
            for path in (
                paths.application_home,
                paths.user_config_file,
                paths.data_root,
                paths.cache_root,
            ):
                with self.subTest(platform=platform, path=path):
                    self.assertNotIn("Library", path)
                    self.assertNotIn(".config", path)
                    self.assertNotIn(".local/share", path)
                    self.assertNotIn(".cache/", path)


class MachinePolicyTest(unittest.TestCase):
    def test_policy_is_where_the_platform_puts_administrator_configuration(self) -> None:
        self.assertEqual(
            resolve_config_paths(Platform.DARWIN, home="/fake/home").policy_file,
            "/Library/Application Support/aart-cli/policy.json",
        )
        self.assertEqual(
            resolve_config_paths(Platform.LINUX, home="/fake/home").policy_file,
            "/etc/aart-cli/policy.json",
        )

    def test_choosing_an_application_home_does_not_move_machine_policy(self) -> None:
        """Otherwise the rule an administrator set is overruled by one environment variable."""

        moved = resolve_config_paths(
            Platform.LINUX, home="/fake/home", application_home="/runner/state"
        )
        default = resolve_config_paths(Platform.LINUX, home="/fake/home")

        self.assertEqual(moved.policy_file, default.policy_file)
        self.assertFalse(moved.policy_file.startswith("/runner/state"))


class ManagedEntriesTest(unittest.TestCase):
    def test_the_managed_entries_are_the_layout_the_specification_lists(self) -> None:
        self.assertEqual(
            MANAGED_HOME_ENTRIES,
            ("config.json", "objects", "sources", "state", "cache", "locks", "tmp"),
        )

    def test_the_named_constants_are_the_ones_the_rest_of_the_product_reads(self) -> None:
        self.assertEqual(APPLICATION_HOME_VARIABLE, "AART_CLI_HOME")
        self.assertEqual(APPLICATION_HOME_DIRECTORY, ".aart-cli")


if __name__ == "__main__":
    unittest.main()
