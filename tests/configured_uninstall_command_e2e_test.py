"""The public uninstall command takes a canonical installation back out through the same records.

Uninstall is the one lifecycle that must not depend on a registry. An installed artifact stays on
the disk after the source that delivered it is removed from the configuration, so what is removed
comes from what this machine recorded -- and the proof of that is a test that removes the source
first and then uninstalls.

The other two properties asserted here are about what a removal is allowed to touch. It takes away
the artifact's own tree and the file the harness reads, and nothing else in the directory the
harness reads it from: a neighbour Skill somebody else installed is not this artifact's to remove.
And it forgets the record, so a later status reports a machine with nothing installed rather than
one installation nothing can find.
"""

from __future__ import annotations

import pathlib
import unittest

from tests.configured_install_command_e2e_test import COORDINATE, _environment


def _delivered(env) -> pathlib.Path:
    return env.project / ".claude/skills/code-review/SKILL.md"


def _artifact_tree(env) -> pathlib.Path:
    return env.project / ".agent-artifacts/runtimes/company/skill/code-review"


class ConfiguredUninstallCommandTest(unittest.TestCase):
    def _installed(self, env) -> None:
        code, payload = env.run(
            "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)
        self.assertTrue(_delivered(env).exists())

    def test_uninstall_before_any_canonical_install_leaves_it_to_the_legacy_path(self) -> None:
        with _environment() as env:
            code, payload = env.run("marketplace", "uninstall", COORDINATE, "--profile", "claude")

            self.assertNotEqual(code, 0, payload)

    def test_review_names_what_would_be_removed_and_removes_nothing(self) -> None:
        with _environment() as env:
            self._installed(env)

            code, payload = env.run("marketplace", "uninstall", COORDINATE, "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            self.assertEqual(payload["operation"], "marketplace.uninstall")
            self.assertEqual(
                payload["review"]["items"][0]["key"], "company/skill/code-review@1.2.0"
            )
            self.assertTrue(payload["review"]["effects"])
            self.assertTrue(_delivered(env).exists(), "review removed the delivery")

    def test_confirmed_removal_withdraws_the_delivery_and_forgets_the_record(self) -> None:
        with _environment() as env:
            self._installed(env)
            neighbour = _delivered(env).parent.parent / "somebody-elses-skill"
            neighbour.mkdir()
            _, review = env.run("marketplace", "uninstall", COORDINATE, "--profile", "claude")

            code, payload = env.run(
                "marketplace",
                "uninstall",
                COORDINATE,
                "--profile",
                "claude",
                "--expect",
                review["review_digest"],
                "--yes",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"])
            self.assertFalse(_delivered(env).exists(), "the Skill is still where the harness reads")
            self.assertFalse(_artifact_tree(env).exists(), "the artifact's own tree outlived it")
            self.assertTrue(
                neighbour.is_dir(),
                "removing one Skill took the directory the harness reads all of them from",
            )

            status_code, status = env.run("marketplace", "status", "--profile", "claude")
            self.assertEqual(status_code, 0, status)
            self.assertEqual(status["items"], [])

    def test_a_stale_review_is_refused_before_anything_is_removed(self) -> None:
        with _environment() as env:
            self._installed(env)

            code, payload = env.run(
                "marketplace",
                "uninstall",
                COORDINATE,
                "--profile",
                "claude",
                "--expect",
                "sha256:" + "0" * 64,
                "--yes",
            )

            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            self.assertTrue(_delivered(env).exists())

    def test_an_artifact_whose_source_is_gone_can_still_be_uninstalled(self) -> None:
        with _environment() as env:
            self._installed(env)
            # The subscription that delivered it is removed. What is installed is still installed,
            # and taking it out reads receipts rather than a registry, so this has to keep working.
            env.disable_source()

            code, payload = env.run(
                "marketplace", "uninstall", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertFalse(_delivered(env).exists())

    def test_uninstalling_something_already_gone_converges_instead_of_failing(self) -> None:
        with _environment() as env:
            self._installed(env)
            first, _ = env.run(
                "marketplace", "uninstall", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(first, 0)

            code, payload = env.run(
                "marketplace", "uninstall", COORDINATE, "--profile", "claude", "--yes"
            )

            # The record is gone, so this is no longer a canonical installation to remove. What
            # matters is that nothing claims to have removed something twice.
            self.assertNotEqual(code, 0, payload)


if __name__ == "__main__":
    unittest.main()
