"""The CLI factory reset is explicit, bounded and never a project eraser (QA-052)."""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import posixpath
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.factory_reset import plan_factory_reset
from aart_cli.configuration.paths import ConfigPaths, Platform, resolve_config_paths
from aart_cli.domain.result import Err, Ok
from aart_cli.model import Request


class FactoryResetPlanningTest(unittest.TestCase):
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_every_linux_plan_names_only_the_four_exact_aart_entries(self, suffix: str) -> None:
        home = f"/users/{suffix}"
        paths = resolve_config_paths(Platform.LINUX, home=home)

        planned = plan_factory_reset(paths, home=home)

        self.assertIsInstance(planned, Ok, planned)
        expected = (
            paths.user_config_file,
            paths.user_config_file + ".lock",
            paths.data_root,
            paths.cache_root,
        )
        self.assertEqual(tuple(item.path for item in planned.value.targets), expected)
        self.assertTrue(
            all(posixpath.commonpath((item.path, home)) == home for item in planned.value.targets)
        )

    def test_darwin_collapses_config_and_lock_inside_the_owned_data_root(self) -> None:
        home = "/Users/manual"
        paths = resolve_config_paths(Platform.DARWIN, home=home)

        planned = plan_factory_reset(paths, home=home)

        self.assertIsInstance(planned, Ok, planned)
        self.assertEqual(
            tuple(item.path for item in planned.value.targets),
            (paths.data_root, paths.cache_root),
        )

    def test_outside_or_merely_similar_paths_are_refused(self) -> None:
        home = "/users/manual"
        valid = resolve_config_paths(Platform.LINUX, home=home)
        invalid = (
            ConfigPaths(
                "/tmp/agent-artifacts/config.json",
                valid.data_root,
                valid.cache_root,
                valid.policy_file,
            ),
            ConfigPaths(
                f"{home}/.config/not-aart/config.json",
                valid.data_root,
                valid.cache_root,
                valid.policy_file,
            ),
            ConfigPaths(
                f"{home}/.config/agent-artifacts/not-config.json",
                valid.data_root,
                valid.cache_root,
                valid.policy_file,
            ),
            ConfigPaths(
                valid.user_config_file,
                f"{home}/.local/share/not-agent-artifacts",
                valid.cache_root,
                valid.policy_file,
            ),
        )

        for paths in invalid:
            result = plan_factory_reset(paths, home=home)
            self.assertIsInstance(result, Err, result)
            diagnostic = result.diagnostics[0]
            self.assertEqual(diagnostic.code.value, "factory-reset-invalid")
            self.assertEqual(diagnostic.severity.value, "error")
            self.assertTrue(diagnostic.message)
            self.assertEqual(
                diagnostic.remediation,
                ("correct the path environment before retrying factory reset",),
            )

    def test_review_identity_is_the_canonical_exact_target_digest(self) -> None:
        home = "/users/manual"
        paths = resolve_config_paths(Platform.LINUX, home=home)
        planned = plan_factory_reset(paths, home=home)
        self.assertIsInstance(planned, Ok, planned)
        identity = json.dumps(
            [{"path": target.path, "kind": target.kind.value} for target in planned.value.targets],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        self.assertEqual(
            planned.value.review_digest,
            "sha256:" + hashlib.sha256(identity).hexdigest(),
        )


class FactoryResetTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = pathlib.Path(temporary.name)
        self.home = root / "home"
        self.project = root / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.unrelated = self.home / "keep-me.txt"
        self.unrelated.write_text("mine\n")
        (self.project / "AGENTS.md").write_text("project\n")
        self.xdg = {
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
        }
        self.config = self.home / ".config" / "agent-artifacts" / "config.json"
        self.lock = self.home / ".config" / "agent-artifacts" / "config.json.lock"
        self.data = self.home / ".local" / "share" / "agent-artifacts"
        self.cache = self.home / ".cache" / "agent-artifacts"
        self.config.parent.mkdir(parents=True)
        self.config.write_text('{"sources": []}\n')
        self.lock.mkdir()
        self.data.mkdir(parents=True)
        (self.data / "receipts.jsonl").write_text("state\n")
        self.cache.mkdir(parents=True)
        (self.cache / "object").write_text("cache\n")

    def _run(self, answers: list[str]) -> tuple[int, str]:
        from aart_cli.commands import reset

        output = io.StringIO()
        with (
            mock.patch.dict("os.environ", self.xdg, clear=False),
            mock.patch.object(reset.sys, "platform", "linux"),
            mock.patch("builtins.input", side_effect=answers) as prompt,
            redirect_stdout(output),
        ):
            status = reset.run(Request("reset", user_home=str(self.home)))
        return status, output.getvalue() + f"\nprompts={prompt.call_count}"

    def test_reset_is_a_distinct_public_cli_command(self) -> None:
        from aart_cli import cli

        request = cli._to_request(cli.build_parser().parse_args(["reset"]))

        self.assertEqual(request.command, "reset")
        self.assertIn("reset", cli.DISPATCH)

    def test_two_exact_confirmations_restore_only_aart_owned_state(self) -> None:
        status, output = self._run(["RESET AART", "DELETE AART STATE"])

        self.assertEqual(status, 0, output)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.lock.exists())
        self.assertFalse(self.data.exists())
        self.assertFalse(self.cache.exists())
        self.assertEqual(self.unrelated.read_text(), "mine\n")
        self.assertEqual((self.project / "AGENTS.md").read_text(), "project\n")
        self.assertIn("prompts=2", output)

    def test_cancelling_either_confirmation_changes_nothing(self) -> None:
        for answers in (["no"], ["RESET AART", "no"]):
            with self.subTest(answers=answers):
                status, output = self._run(list(answers))
                self.assertEqual(status, 0, output)
                self.assertTrue(self.config.exists())
                self.assertTrue(self.data.exists())
                self.assertTrue(self.cache.exists())

    def test_a_symlink_target_is_refused_before_any_deletion(self) -> None:
        real_cache = self.cache.with_name("cache-owned-by-someone-else")
        self.cache.rename(real_cache)
        self.cache.symlink_to(real_cache, target_is_directory=True)

        status, output = self._run(["RESET AART", "DELETE AART STATE"])

        self.assertEqual(status, 1, output)
        self.assertTrue(self.config.exists())
        self.assertTrue(self.data.exists())
        self.assertTrue(self.cache.is_symlink())
        self.assertTrue(real_cache.exists())

    def test_a_symlinked_parent_is_refused_before_any_deletion(self) -> None:
        cache_parent = self.cache.parent
        external_cache = self.home.parent / "cache-owned-by-someone-else"
        cache_parent.rename(external_cache)
        cache_parent.symlink_to(external_cache, target_is_directory=True)

        status, output = self._run(["RESET AART", "DELETE AART STATE"])

        self.assertEqual(status, 1, output)
        self.assertTrue(self.config.exists())
        self.assertTrue(self.data.exists())
        self.assertTrue(cache_parent.is_symlink())
        self.assertTrue((external_cache / "agent-artifacts" / "object").exists())

    def test_end_of_input_cancels_without_changing_state(self) -> None:
        status, output = self._run([])

        self.assertEqual(status, 0, output)
        self.assertIn("cancelled", output.lower())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.data.exists())


if __name__ == "__main__":
    unittest.main()
