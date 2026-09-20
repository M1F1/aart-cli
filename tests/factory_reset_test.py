"""The CLI factory reset is explicit, bounded and never a project eraser (QA-052).

Since §169.2 the bound is one directory rather than three, which changes what "bounded" has to
mean. The home can now be anywhere the person points `AART_CLI_HOME`, so the plan names the entries
the tool writes inside it and never the directory itself -- otherwise a reset is one mistyped
variable away from deleting whatever that variable named.
"""

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
from aart_cli.configuration.paths import (
    MANAGED_HOME_ENTRIES,
    ConfigPaths,
    Platform,
    resolve_config_paths,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.model import Request


class FactoryResetPlanningTest(unittest.TestCase):
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_every_plan_names_the_managed_entries_and_the_lock_and_nothing_else(
        self, suffix: str
    ) -> None:
        home = f"/users/{suffix}"
        paths = resolve_config_paths(Platform.LINUX, home=home)

        planned = plan_factory_reset(paths, home=home)

        self.assertIsInstance(planned, Ok, planned)
        expected = sorted(
            [posixpath.join(paths.application_home, entry) for entry in MANAGED_HOME_ENTRIES]
            + [paths.user_config_file + ".lock"]
        )
        self.assertEqual(sorted(item.path for item in planned.value.targets), expected)

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_no_plan_ever_names_the_home_itself(self, suffix: str) -> None:
        """Removing the root would make an explicit home a way to delete an arbitrary directory."""

        home = f"/users/{suffix}"
        paths = resolve_config_paths(Platform.LINUX, home=home)

        planned = plan_factory_reset(paths, home=home)

        assert isinstance(planned, Ok), planned
        for target in planned.value.targets:
            self.assertNotEqual(target.path, paths.application_home)
            self.assertEqual(posixpath.dirname(target.path), paths.application_home)

    def test_the_two_platforms_plan_the_same_relative_set(self) -> None:
        home = "/Users/manual"
        darwin = plan_factory_reset(resolve_config_paths(Platform.DARWIN, home=home), home=home)
        linux = plan_factory_reset(resolve_config_paths(Platform.LINUX, home=home), home=home)

        assert isinstance(darwin, Ok) and isinstance(linux, Ok)
        self.assertEqual(
            tuple(item.path for item in darwin.value.targets),
            tuple(item.path for item in linux.value.targets),
        )

    def test_an_explicit_home_is_planned_wherever_it_is(self) -> None:
        paths = resolve_config_paths(
            Platform.LINUX, home="/users/manual", application_home="/runner/work/state"
        )

        planned = plan_factory_reset(paths, home="/users/manual")

        assert isinstance(planned, Ok), planned
        self.assertIn("/runner/work/state/objects", [item.path for item in planned.value.targets])
        self.assertTrue(
            all(item.path.startswith("/runner/work/state/") for item in planned.value.targets)
        )

    def test_a_home_nothing_owns_alone_is_refused(self) -> None:
        home = "/users/manual"
        refused = (
            resolve_config_paths(Platform.LINUX, home=home, application_home="/"),
            resolve_config_paths(Platform.LINUX, home=home, application_home=home),
        )

        for paths in refused:
            with self.subTest(application_home=paths.application_home):
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

    def test_a_target_that_would_escape_the_home_is_refused(self) -> None:
        home = "/users/manual"
        valid = resolve_config_paths(Platform.LINUX, home=home)
        escaping = ConfigPaths(
            valid.application_home,
            "/elsewhere/config.json",
            valid.data_root,
            valid.cache_root,
            valid.policy_file,
        )

        result = plan_factory_reset(escaping, home=home)

        self.assertIsInstance(result, Err, result)

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
        self.application_home = self.home / ".aart-cli"
        self.config = self.application_home / "config.json"
        self.lock = self.application_home / "config.json.lock"
        self.state = self.application_home / "state"
        self.cache = self.application_home / "cache"
        self.application_home.mkdir()
        self.config.write_text('{"sources": []}\n')
        self.lock.mkdir()
        self.state.mkdir()
        (self.state / "receipts.jsonl").write_text("state\n")
        self.cache.mkdir()
        (self.cache / "object").write_text("cache\n")

    def _run(
        self, answers: list[str], environment: dict[str, str] | None = None
    ) -> tuple[int, str]:
        from aart_cli.commands import reset

        output = io.StringIO()
        with (
            mock.patch.dict("os.environ", environment or {}, clear=False),
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
        self.assertFalse(self.state.exists())
        self.assertFalse(self.cache.exists())
        self.assertEqual(self.unrelated.read_text(), "mine\n")
        self.assertEqual((self.project / "AGENTS.md").read_text(), "project\n")
        self.assertIn("prompts=2", output)

    def test_what_the_tool_did_not_write_inside_its_own_home_survives(self) -> None:
        """The plan names entries, so a note somebody left in the home is not collateral."""

        theirs = self.application_home / "notes.md"
        theirs.write_text("mine\n")

        status, output = self._run(["RESET AART", "DELETE AART STATE"])

        self.assertEqual(status, 0, output)
        self.assertTrue(self.application_home.exists())
        self.assertEqual(theirs.read_text(), "mine\n")

    def test_an_explicit_home_is_the_one_that_is_reset(self) -> None:
        elsewhere = self.home.parent / "runner-state"
        (elsewhere / "state").mkdir(parents=True)
        (elsewhere / "state" / "receipts.jsonl").write_text("ci\n")

        status, output = self._run(
            ["RESET AART", "DELETE AART STATE"], {"AART_CLI_HOME": str(elsewhere)}
        )

        self.assertEqual(status, 0, output)
        self.assertFalse((elsewhere / "state").exists())
        self.assertTrue(self.state.exists(), "the default home was not the target")

    def test_cancelling_either_confirmation_changes_nothing(self) -> None:
        for answers in (["no"], ["RESET AART", "no"]):
            with self.subTest(answers=answers):
                status, output = self._run(list(answers))
                self.assertEqual(status, 0, output)
                self.assertTrue(self.config.exists())
                self.assertTrue(self.state.exists())
                self.assertTrue(self.cache.exists())

    def test_a_symlink_target_is_refused_before_any_deletion(self) -> None:
        real_cache = self.home.parent / "cache-owned-by-someone-else"
        real_cache.mkdir()
        self.cache.rename(real_cache / "moved")
        self.cache.symlink_to(real_cache, target_is_directory=True)

        status, output = self._run(["RESET AART", "DELETE AART STATE"])

        self.assertEqual(status, 1, output)
        self.assertTrue(self.config.exists())
        self.assertTrue(self.state.exists())
        self.assertTrue(self.cache.is_symlink())
        self.assertTrue((real_cache / "moved").exists())

    def test_a_symlinked_application_home_is_refused_before_any_deletion(self) -> None:
        external = self.home.parent / "home-owned-by-someone-else"
        self.application_home.rename(external)
        self.application_home.symlink_to(external, target_is_directory=True)

        status, output = self._run(["RESET AART", "DELETE AART STATE"])

        self.assertEqual(status, 1, output)
        self.assertTrue(self.application_home.is_symlink())
        self.assertTrue((external / "state" / "receipts.jsonl").exists())

    def test_end_of_input_cancels_without_changing_state(self) -> None:
        status, output = self._run([])

        self.assertEqual(status, 0, output)
        self.assertIn("cancelled", output.lower())
        self.assertTrue(self.config.exists())
        self.assertTrue(self.state.exists())


if __name__ == "__main__":
    unittest.main()
