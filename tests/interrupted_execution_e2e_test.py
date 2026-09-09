"""End to end: a run AART could not fully undo, and the evidence it leaves behind.

Product Specification 165.13 and 165.14 are one scenario read at two moments. First: *"AART does not
claim transaction atomicity beyond actual effect guarantees"* -- when compensation itself fails, the
outcome is partial and says so, rather than borrowing the vocabulary of a clean rollback. Then:
*"an interrupted operation is never resumed by blindly continuing from the next imperative
command"* -- the working copy the stopped run left is found, named and left exactly where it is, and
a retry re-inspects instead of picking up where the last one stopped.

Nothing here is simulated. The recipe carries a real custom entrypoint -- a shell script following
the plan/apply/verify/rollback protocol -- whose `apply` phase exits non-zero and whose `rollback`
phase then also exits non-zero. That is the one path in `_custom_apply` that raises without removing
its run directory, so the working copy this file asserts on is one the engine really created and
really failed to clean up. Patching the cleanup away would have produced the same directory and
proved nothing about when a directory is actually left.

Why this route and not the managed-block recipe of `verification_failure_e2e_test`: a run directory
is opened only by the two effects that need a working copy, `custom.install@1` and
`docker.build@1`. A recipe of ordinary file effects never creates one, so it can leave no orphan and
the `no-orphan-run-directory` claim answers `true` about a directory that was never made.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.marketplace_lifecycle_e2e_test import (
    _COORDINATE,
    _FIXTURE,
    _Environment,
)

#: The protocol AART invokes: `<script> <phase> --result <path>`, one JSON verdict per phase. `plan`
#: succeeds so the run reaches `apply`; `apply` fails so compensation is attempted; `rollback` fails
#: so compensation cannot complete. The header on line two is required of every custom entrypoint
#: (`setup.py::has_manual_setup_header`) and points at the manual route beside it.
_SCRIPT = """#!/bin/sh
# AART manual setup: see ../SETUP.md
phase="$1"
shift
result=""
while [ $# -gt 0 ]; do
  case "$1" in
    --result) result="$2"; shift 2 ;;
    *) shift ;;
  esac
done
case "$phase" in
  plan)
    printf '{"status":"planned","detail":"plan ok","reversible":true}' > "$result"
    exit 0 ;;
  apply) exit 7 ;;
  rollback) exit 9 ;;
  *) exit 0 ;;
esac
"""

_RECIPE = {
    "schema_version": 2,
    "protocol_version": 2,
    "artifact": "skill/code-review",
    "purpose": "Run a custom protocol that fails and cannot undo itself.",
    "platforms": ["darwin"],
    "help_urls": [{"label": "Setup help", "url": "https://example.test/code-review/setup"}],
    "required_tools": [],
    # Both are required of a custom entrypoint, and the parser refuses the recipe without them:
    # running someone's script is `custom-code`, and running it at all is `process`.
    "capabilities": ["custom-code", "process"],
    "inputs": [],
    "steps": [{"id": "notice", "use": "restart.notice@1", "with": {"message": "Restart."}}],
    "custom_entrypoint": "install.sh",
}

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


@contextlib.contextmanager
def _environment_whose_rollback_fails():
    """The shared fixture source, copied and taught to carry the failing custom protocol."""

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw).resolve()
        location = root / "source"
        shutil.copytree(_FIXTURE, location)
        artifact = location / "artifacts" / "skill" / "code-review"
        manifest = json.loads((artifact / "artifact.json").read_text(encoding="utf-8"))
        manifest["setup"] = {"recipe": "setup/installer.json", "platforms": ["darwin"]}
        (artifact / "artifact.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (artifact / "setup").mkdir()
        (artifact / "setup" / "installer.json").write_text(
            json.dumps(_RECIPE, indent=2), encoding="utf-8"
        )
        script = artifact / "setup" / "install.sh"
        script.write_text(_SCRIPT, encoding="utf-8")
        script.chmod(0o755)
        (artifact / "SETUP.md").write_text(
            "Run the steps in setup/install.sh yourself.\n", encoding="utf-8"
        )
        machine = root / "machine"
        machine.mkdir()
        yield _Environment(machine, location)


def _working_copies(env) -> list[Path]:
    """Whatever is under the run root the engine writes into, which is not the project root."""

    runs = Path(env.paths.data_root, ".agent-artifacts", "setup-runs")
    return sorted(runs.iterdir()) if runs.exists() else []


def _orphan_claim(verification: dict) -> dict:
    claims = [
        claim for claim in verification["claims"] if claim["kind"] == "no-orphan-run-directory"
    ]
    assert len(claims) == 1, verification
    return claims[0]


@unittest.skipUnless(
    sys.platform == "darwin",
    "the setup engine accepts only darwin recipes (setup.py:562), so applying one elsewhere is "
    "refused for the platform before any effect runs",
)
class InterruptedExecutionE2ETest(unittest.TestCase):
    def _ran(self, env) -> tuple[int, dict]:
        """Install, then run the custom setup that fails and cannot undo itself."""

        code, payload = env.run(
            "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)
        return env.run(*_SETUP)

    def test_a_failure_whose_rollback_also_failed_is_not_called_rolled_back(self) -> None:
        """165.13: the claim matches the guarantee that was actually delivered.

        `apply-failed-rolled-back` and `rollback-incomplete` are two different promises about the
        machine. The first says the previous state is restored; the second says it may not be. An
        operator told the first when the second is true stops looking.
        """

        with _environment_whose_rollback_fails() as env:
            code, payload = self._ran(env)

            self.assertNotEqual(code, 0)
            self.assertEqual(payload["setup"]["planning_failures"], [])
            item = payload["setup"]["items"][0]
            self.assertEqual(item["status"], "rollback-incomplete")
            self.assertFalse(item["successful"])
            self.assertIn("rollback was incomplete", item["detail"])
            # A partial outcome that names no way forward is a dead end, not an audit.
            self.assertTrue(item["recovery"], item)

    def test_the_working_copy_the_failed_run_left_is_still_there(self) -> None:
        with _environment_whose_rollback_fails() as env:
            self._ran(env)

            self.assertEqual(len(_working_copies(env)), 1, _working_copies(env))

    def test_receipt_verify_finds_the_working_copy_and_names_the_real_one(self) -> None:
        """The public half of `LAF-66`, which is where that defect could still recur.

        `LAF-66` was one path derived in two places: the probe composed the run root from the
        project root while the engine composed it from the data root, so the claim answered `true`
        in every scope without ever looking where runs are made. `setup_verify_test` holds the
        writer and the probe together; the remaining seam is the command that hands the probe its
        root, and nothing drove that. So this asserts the *identity* of the directory named -- the
        one the engine actually created -- rather than only that some path was reported.
        """

        with _environment_whose_rollback_fails() as env:
            self._ran(env)
            left = _working_copies(env)
            self.assertEqual(len(left), 1, left)

            code, payload = env.run(
                "marketplace", "receipt", "verify", _COORDINATE, "--profile", "claude"
            )

            # A false claim is a finding, and a finding must not report success to CI.
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["verification"]["false"], 1)
            claim = _orphan_claim(payload["verification"])
            self.assertEqual(claim["status"], "false")
            self.assertIn(str(left[0]), claim["detail"])
            self.assertIn("not removed", claim["detail"])

            shown, receipt = env.run(
                "marketplace", "receipt", "show", _COORDINATE, "--profile", "claude"
            )
            self.assertEqual(shown, 0, receipt)
            # The claim's subject is the plan it belongs to, and the directory is named for it.
            self.assertTrue(
                left[0].name.startswith(receipt["receipt"]["plan_hash"][:16]), left[0].name
            )

    def test_the_receipt_of_a_custom_run_reads_back_as_json(self) -> None:
        """The evidence has to be readable, or none of the rest of this matters.

        A parsed record's steps are frozen recursively into `MappingProxyType`, and the receipt
        projection copied each step shallowly -- so every nested object stayed a proxy and
        `json.dumps` refused it. The custom setup protocol is the one that writes such a step, which
        made `aart marketplace receipt show --json` end in a `TypeError` traceback for exactly the
        run whose evidence is hardest to reconstruct by hand. Writing this file found it.
        """

        with _environment_whose_rollback_fails() as env:
            self._ran(env)

            code, payload = env.run(
                "marketplace", "receipt", "show", _COORDINATE, "--profile", "claude"
            )

            self.assertEqual(code, 0, payload)
            receipt = payload["receipt"]
            self.assertEqual(receipt["status"], "rollback_incomplete")
            # Round-trips, which is the whole claim: nothing in it is a live Python object.
            self.assertEqual(json.loads(json.dumps(receipt)), receipt)
            self.assertTrue(receipt["steps"], receipt)

    def test_verify_reports_the_working_copy_and_leaves_it_exactly_where_it_is(self) -> None:
        """`LAF-61`: reported, named, and not tidied away.

        Inspection that deletes its own evidence is worse than no inspection: the second operator
        to look finds a clean machine and no reason to distrust it.
        """

        with _environment_whose_rollback_fails() as env:
            self._ran(env)
            before = _working_copies(env)

            env.run("marketplace", "receipt", "verify", _COORDINATE, "--profile", "claude")

            self.assertEqual(_working_copies(env), before)

    def test_a_retry_replans_instead_of_resuming_where_the_last_run_stopped(self) -> None:
        """165.14: resume re-inspects and reconciles before constructing the remaining plan.

        Two things say it did. The review digest of the second run differs from the first, because
        the plan binds the record the first run persisted -- so a plan reviewed before that run
        cannot be replayed after it. And the protocol starts again from its first phase rather than
        from the step that failed, which is what the second working copy is: a fresh run, not a
        continuation of the one whose evidence is still sitting beside it.
        """

        with _environment_whose_rollback_fails() as env:
            first_code, first = self._ran(env)
            self.assertNotEqual(first_code, 0)

            second_code, second = env.run(*_SETUP)

            self.assertNotEqual(second_code, 0)
            self.assertNotEqual(
                first["setup"]["planned"][0]["review_digest"],
                second["setup"]["planned"][0]["review_digest"],
            )
            self.assertEqual(len(_working_copies(env)), 2, _working_copies(env))
            # Both are reported, so a retry hides neither its predecessor's evidence nor its own.
            code, payload = env.run(
                "marketplace", "receipt", "verify", _COORDINATE, "--profile", "claude"
            )
            self.assertNotEqual(code, 0)
            self.assertIn("2 working copy", _orphan_claim(payload["verification"])["detail"])


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
