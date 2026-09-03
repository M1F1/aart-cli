"""End to end: the global report finds a working copy nobody knew to ask about.

CP-15 step 4b proved that `aart marketplace receipt verify <coordinate>` names the working copy an
interrupted run left behind. That claim has a precondition buried in it: the operator must already
know which receipt to verify. Being interrupted is usually the reason they stopped watching, so the
one fact they cannot supply is the one the existing surface requires.

This drives `aart doctor` instead, which is told nothing. Every scenario runs the same real custom
entrypoint CP-15 step 4b used -- a shell script whose `apply` exits non-zero and whose `rollback`
then also exits non-zero, the one path in `_custom_apply` that raises without removing its run
directory -- so the working copy asserted on is one the engine really created and really failed to
clean up. Patching cleanup away would produce the same directory and prove nothing about when one
is actually left.

`LAF-61` governs what Doctor may then do about it: report, name, and leave. An inspection that
tidies away its own evidence is worse than none, because the second operator finds a clean machine
and no reason to doubt it.
"""

from __future__ import annotations

import os
import stat
import sys
import unittest
from pathlib import Path

from tests.interrupted_execution_e2e_test import (
    _environment_whose_rollback_fails,
    _working_copies,
)
from tests.marketplace_lifecycle_e2e_test import _COORDINATE

_SETUP = (
    "marketplace",
    "setup",
    _COORDINATE,
    "--profile",
    "claude",
    "--yes",
    "--authorize-untrusted-source",
    "--approve-setup-effects",
    "--authorize-custom-entrypoint",
)


def _runs_root(env) -> Path:
    return Path(env.paths.data_root, ".agent-artifacts", "setup-runs")


@unittest.skipUnless(
    sys.platform == "darwin",
    "the setup engine accepts only darwin recipes (setup.py:562), so applying one elsewhere is "
    "refused for the platform before any effect runs",
)
class DoctorOrphanedRunsE2ETest(unittest.TestCase):
    def _installed(self, env) -> None:
        code, payload = env.run(
            "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)

    def _interrupted(self, env) -> None:
        """Install, then run the custom setup that fails and cannot undo itself."""

        self._installed(env)
        env.run(*_SETUP)

    def test_a_machine_with_no_interrupted_run_reports_no_working_copy(self) -> None:
        """The baseline that makes the next test's finding mean something.

        Without this, "Doctor reports one working copy" would be consistent with Doctor reporting
        one unconditionally.
        """

        with _environment_whose_rollback_fails() as env:
            self._installed(env)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertIs(payload["orphaned_runs"]["readable"], True)
            self.assertEqual(payload["orphaned_runs"]["working_copies"], [])
            self.assertEqual(_working_copies(env), [])

    def test_doctor_finds_the_working_copy_without_being_told_any_receipt(self) -> None:
        """The whole point of the increment: no coordinate, no receipt, no plan hash is supplied."""

        with _environment_whose_rollback_fails() as env:
            self._interrupted(env)
            left = _working_copies(env)
            self.assertEqual(len(left), 1, left)

            _code, payload = env.run("doctor")

            found = payload["orphaned_runs"]["working_copies"]
            self.assertEqual(len(found), 1, found)
            # The identity of the directory, not merely that some path was reported: `LAF-66` was
            # exactly a path derived twice from two different roots.
            self.assertEqual(found[0]["path"], str(left[0]))

    def test_the_working_copy_is_tied_back_to_the_run_that_left_it(self) -> None:
        """A path with nothing to tie it to is a mystery directory, not evidence."""

        with _environment_whose_rollback_fails() as env:
            self._interrupted(env)

            _code, payload = env.run("doctor")
            shown, receipt = env.run(
                "marketplace", "receipt", "show", _COORDINATE, "--profile", "claude"
            )

            self.assertEqual(shown, 0, receipt)
            prefix = payload["orphaned_runs"]["working_copies"][0]["plan_hash_prefix"]
            self.assertEqual(prefix, receipt["receipt"]["plan_hash"][:16])

    def test_doctor_reports_the_working_copy_and_leaves_it_exactly_where_it_is(self) -> None:
        """`LAF-61`: reported, named, and not tidied away."""

        with _environment_whose_rollback_fails() as env:
            self._interrupted(env)
            left = _working_copies(env)
            before = sorted(path.name for path in left[0].rglob("*"))

            _code, payload = env.run("doctor")

            self.assertIn("orphaned_runs", payload)
            self.assertTrue(left[0].exists(), "the report removed its own evidence")
            self.assertEqual(sorted(path.name for path in left[0].rglob("*")), before)

    def test_the_human_report_names_the_working_copy_and_offers_no_deletion(self) -> None:
        with _environment_whose_rollback_fails() as env:
            self._interrupted(env)
            left = _working_copies(env)

            _code, output = env.run_text("doctor")

            self.assertIn("Interrupted runs:", output)
            self.assertIn(str(left[0]), output)
            self.assertIn("not removed", output)
            self.assertIn("does not delete", output)

    def test_a_stray_entry_beside_a_working_copy_does_not_hide_it(self) -> None:
        """The sweep skips what it cannot read as a run and keeps going.

        A run root holds whatever ends up in it. Scoped mutation found that `continue` and `break`
        were indistinguishable here, because one working copy alone can never show the difference:
        with `break`, anything sorting before the real directory hides it entirely. The stray names are all-zero
        hexadecimal on purpose, so they sort ahead of any real plan-hash prefix and a `break` would
        drop the working copy that follows them.
        """

        with _environment_whose_rollback_fails() as env:
            self._interrupted(env)
            runs = _runs_root(env)
            real = _working_copies(env)
            self.assertEqual(len(real), 1, real)
            (runs / "0000000000000000-not-a-directory").write_text("stray\n", encoding="utf-8")
            (runs / "0000000000000001nodash").mkdir()

            _code, payload = env.run("doctor")

            found = payload["orphaned_runs"]["working_copies"]
            self.assertEqual([item["path"] for item in found], [str(real[0])], found)

    def test_a_run_root_that_cannot_be_read_is_unknown_rather_than_empty(self) -> None:
        """ "Nothing is there" and "we could not look" are different answers.

        An operator told the first stops looking. This is the same distinction step 2 refused to
        collapse for the three offline capabilities.
        """

        with _environment_whose_rollback_fails() as env:
            self._interrupted(env)
            runs = _runs_root(env)
            self.assertTrue(runs.exists())
            original = stat.S_IMODE(runs.stat().st_mode)
            os.chmod(runs, 0o000)
            try:
                _code, payload = env.run("doctor")
            finally:
                os.chmod(runs, original)

            # `is False`, not merely falsey: in JSON the difference is `false` against `null`.
            self.assertIs(payload["orphaned_runs"]["readable"], False)
            self.assertEqual(payload["orphaned_runs"]["working_copies"], [])
            # Still there afterwards: an unreadable root is not a reason to touch anything.
            self.assertEqual(len(_working_copies(env)), 1)


if __name__ == "__main__":
    unittest.main()
