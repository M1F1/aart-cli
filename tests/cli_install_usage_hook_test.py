"""§212, D-516, B-249: a `consume` command puts the usage hook in place, as the TUI's start does.

Recording without asking is the build's (D-502) or the person's choice; before this, only the TUI's
start carried it out, so someone who only ran `consume install` recorded nothing. A wheel runs
nothing when it is installed, so a command's run is the first moment aart-cli can. Real commands
run here, in a temporary HOME and AART_CLI_HOME, so what is claimed is the file opencode loads.
"""

from __future__ import annotations

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from aart_cli import _default_usage, cli
from aart_cli.application.consumer_views import ConsumerSettings
from aart_cli.cli_parser import build_parser
from aart_cli.commands import usage
from aart_cli.domain.result import Ok
from aart_cli.io.consumer_settings import write_consumer_settings
from aart_cli.io.usage_hooks import harness_file, usage_hooked
from tests.configured_install_command_e2e_test import COORDINATE, _environment

#: Each command here runs in a temporary HOME and AART_CLI_HOME (`tests/conftest.py`).
RECORDS_USAGE = True

SAID = (
    "Recording which skills and MCPs opencode uses; "
    "`aart-cli consume usage disable --harness opencode` turns it off."
)


def _baked(value: str):
    """A build whose release baked `AART_CLI_DEFAULT_USAGE_HARNESSES=value`."""

    return mock.patch.object(_default_usage, "HARNESSES", value)


def _opencode(env) -> None:
    (env.home / ".config" / "opencode").mkdir(parents=True, exist_ok=True)


def _hooked(env) -> bool:
    return usage_hooked("opencode", user_home=str(env.home))


def _run(env, *argv: str) -> tuple[int, dict, str]:
    with contextlib.redirect_stderr(io.StringIO()) as said:
        code, payload = env.run(*argv)
    return code, payload, said.getvalue()


def _install(env) -> tuple[int, dict, str]:
    """A real install, review then apply; what both said on stderr."""

    _, review, reviewed = _run(env, "consume", "install", COORDINATE, "--profile", "claude")
    code, payload, said = _run(
        env,
        "consume",
        "install",
        COORDINATE,
        "--profile",
        "claude",
        "--expect",
        review["review_digest"],
        "--yes",
    )
    return code, payload, reviewed + said


class AConsumeCommandPutsTheHookInPlace(unittest.TestCase):
    def test_an_install_in_a_build_that_records_opencode_hooks_it_and_says_so(self) -> None:
        with _environment() as env, _baked("opencode"):
            _opencode(env)
            code, payload, said = _install(env)

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertTrue(_hooked(env))
            self.assertEqual(said.count(SAID), 1)

    def test_any_consume_command_is_the_first_moment_and_says_it_once(self) -> None:
        with _environment() as env, _baked("opencode"):
            _opencode(env)
            code, payload, said = _run(env, "consume", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertTrue(_hooked(env))
            self.assertEqual(said.count(SAID), 1)
            _, _, again = _run(env, "consume", "status", "--profile", "claude")
            self.assertNotIn("Recording", again)

    def test_a_build_that_records_nowhere_hooks_nothing(self) -> None:
        with _environment() as env, _baked(""):
            _opencode(env)
            code, payload, said = _install(env)

            self.assertEqual(code, 0, payload)
            self.assertFalse(_hooked(env))
            self.assertNotIn("Recording", said)

    def test_a_person_who_turned_it_off_is_not_overruled(self) -> None:
        with _environment() as env, _baked("opencode"):
            _opencode(env)
            written = write_consumer_settings(
                replace(ConsumerSettings(), artifact_usage=()), data_root=str(env.paths.data_root)
            )
            self.assertIsInstance(written, Ok)
            code, payload, said = _install(env)

            self.assertEqual(code, 0, payload)
            self.assertFalse(_hooked(env))
            self.assertNotIn("Recording", said)

    def test_the_choice_is_read_from_the_application_home_the_run_uses(self) -> None:
        with _environment() as env, _baked("opencode"):
            _opencode(env)
            elsewhere = env.root / "elsewhere"
            env.xdg["AART_CLI_HOME"] = str(elsewhere)
            written = write_consumer_settings(
                replace(ConsumerSettings(), artifact_usage=()), data_root=str(elsewhere)
            )
            self.assertIsInstance(written, Ok)
            _run(env, "consume", "status", "--profile", "claude")

            self.assertFalse(_hooked(env))

    def test_a_harness_not_on_this_machine_is_left_alone(self) -> None:
        with _environment() as env, _baked("opencode"):
            code, payload, said = _install(env)

            self.assertEqual(code, 0, payload)
            self.assertFalse(Path(harness_file("opencode", user_home=str(env.home))).exists())
            self.assertFalse((env.home / ".config" / "opencode").exists())
            self.assertNotIn("Recording", said)

    def test_a_failure_to_hook_never_fails_the_command(self) -> None:
        with (
            _environment() as env,
            _baked("opencode"),
            mock.patch.object(usage, "reconcile_usage_hooks", side_effect=OSError("read-only")),
        ):
            _opencode(env)
            code, payload, said = _install(env)

            self.assertEqual(code, 0, payload)
            self.assertNotIn("Recording", said)

    def test_only_a_consume_command_that_is_not_the_person_deciding_hooks(self) -> None:
        parser = build_parser()
        for argv, hooks in (
            (["consume", "list"], True),
            (["consume", "install", COORDINATE], True),
            (["consume", "update", "--offline"], True),
            (["consume", "telemetry", "status"], True),
            (["consume", "usage", "show"], False),
            (["consume", "usage", "disable", "--harness", "opencode"], False),
            (["maintain", "registry", "validate"], False),
        ):
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertEqual(cli._records_usage(args, cli._to_request(args)), hooks)


if __name__ == "__main__":
    unittest.main()
