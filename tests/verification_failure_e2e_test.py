"""End to end: effects that applied, then a verification that failed.

Product Specification 165.12 makes two claims about this moment and they are separate. The first is
about the report -- successful effects followed by failed verification are *not reported as clean
success* -- and the second is about the evidence: the receipt records applied effects, the
verification result and the final health. A run can hold the first and drop the second, which is
exactly what writing this found.

The recipe here writes one managed block and then runs one command that exits non-zero. Both halves
are deliberate. The block is compensatable, so 165.13's "if all applied effects are safely
compensatable, the previous state may be restored" is the branch taken, and the file's absence
afterwards is what proves the restore ran. The failing command is `/usr/bin/false`, which needs no
network, no tool and no secret, so nothing about the machine can explain the failure except that
verification failed.

The payload is installed first and separately, because that is the shape 165.12 describes:
"github-mcp was installed, but verification failed". A failed setup verification must not
un-install what a different, already-completed transaction placed.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.marketplace_lifecycle_e2e_test import (
    _CONFIGURED,
    _COORDINATE,
    _FIXTURE,
    _RECIPE,
    _Environment,
)

#: The declared setup of `_environment_declaring_setup`, plus one verification that cannot pass.
#: `process` joins the capability list because the review names the capability each effect needs,
#: and a recipe that ran a command under `filesystem` alone would be the more serious bug.
_VERIFIED_RECIPE = {
    **_RECIPE,
    "capabilities": ["filesystem", "process"],
    "steps": [
        *_RECIPE["steps"],
        {"id": "verify", "use": "command.verify@1", "with": {"argv": ["/usr/bin/false"]}},
    ],
}


@contextlib.contextmanager
def _environment_whose_verification_fails():
    """`_environment_declaring_setup`, with the recipe swapped for one that fails its check.

    Copied rather than parameterized: the fixture in `marketplace_lifecycle_e2e_test` yields an
    environment and not the recipe, and threading a parameter through it would change a file this
    slice is not otherwise touching.
    """

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
            json.dumps(_VERIFIED_RECIPE, indent=2), encoding="utf-8"
        )
        (artifact / "SETUP.md").write_text(
            "Write `enabled = true` into .code-review.toml yourself.\n", encoding="utf-8"
        )
        machine = root / "machine"
        machine.mkdir()
        yield _Environment(machine, location)


@unittest.skipUnless(
    __import__("sys").platform == "darwin",
    "the setup engine accepts only darwin recipes (setup.py:562), so applying one elsewhere is "
    "refused for the platform before verification is ever reached",
)
class VerificationFailureE2ETest(unittest.TestCase):
    def _configured(self, env) -> tuple[int, dict]:
        """Install, then run the declared setup with both consents, and return setup's verdict."""

        code, payload = env.run(
            "marketplace", "install", _COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)
        return env.run(
            "marketplace",
            "setup",
            _COORDINATE,
            "--profile",
            "claude",
            "--yes",
            "--authorize-untrusted-source",
            "--approve-setup-effects",
        )

    def test_a_failed_verification_is_not_reported_as_clean_success(self) -> None:
        with _environment_whose_verification_fails() as env:
            code, payload = self._configured(env)

            self.assertNotEqual(code, 0)
            self.assertFalse(payload["ok"])
            setup = payload["setup"]
            self.assertEqual(setup["planning_failures"], [])
            self.assertEqual((setup["configured"], setup["incomplete"]), (0, 1))
            item = setup["items"][0]
            self.assertEqual(item["status"], "verification-failed")
            self.assertFalse(item["successful"])
            # The status is its own word. A verification that failed is not an apply that failed,
            # and an operator told the wrong one repairs the wrong thing.
            self.assertNotIn(item["status"], {"apply-failed-rolled-back", "cancelled", "failed"})

    def test_the_human_rendering_names_the_artifact_rather_than_only_a_count(self) -> None:
        with _environment_whose_verification_fails() as env:
            env.run("marketplace", "install", _COORDINATE, "--profile", "claude", "--yes")

            code, text = env.run_text(
                "marketplace",
                "setup",
                _COORDINATE,
                "--profile",
                "claude",
                "--yes",
                "--authorize-untrusted-source",
                "--approve-setup-effects",
            )

            self.assertNotEqual(code, 0)
            self.assertIn("code-review", text)
            self.assertIn("verification", text)
            # `configured=0` alone would be a clean-looking line. The retry is what makes the
            # rendering actionable rather than merely non-positive.
            self.assertIn("aart marketplace setup", text)

    def test_the_compensatable_effect_is_restored(self) -> None:
        with _environment_whose_verification_fails() as env:
            self._configured(env)

            # 165.13: all applied effects here are safely compensatable, so the previous state is
            # restored rather than left half-applied.
            self.assertFalse((env.project / _CONFIGURED).exists())

    def test_the_receipt_records_the_effects_that_applied_before_the_check_failed(self) -> None:
        """165.12's second half: applied effects, verification result *and* final health.

        This is the claim that was false. The run applied one managed-block effect, compensated it
        and persisted a record whose `steps` list was empty -- so the receipt said a verification
        failed and said nothing about what had already been done to the machine before it did.
        """

        with _environment_whose_verification_fails() as env:
            self._configured(env)

            code, payload = env.run(
                "marketplace", "receipt", "show", _COORDINATE, "--profile", "claude"
            )

            self.assertEqual(code, 0, payload)
            receipt = payload["receipt"]
            self.assertEqual(receipt["status"], "verification_failed")
            self.assertEqual(receipt["exit_status"], 1)
            steps = receipt["steps"]
            self.assertEqual([step["step_id"] for step in steps], ["config"])
            self.assertEqual([step["module"] for step in steps], ["file.managed-block@1"])

    def test_the_recorded_effects_make_no_claim_about_the_world_they_no_longer_hold(self) -> None:
        """Kept as evidence, not as a second undo recipe.

        A retained step that still read as live would be worse than dropping it: `receipt verify`
        would report a missing file as a broken installation, and `receipt undo` would offer to
        reverse a change that is already reversed -- deleting whatever a person put back in its
        place.
        """

        with _environment_whose_verification_fails() as env:
            self._configured(env)

            code, payload = env.run(
                "marketplace", "receipt", "show", _COORDINATE, "--profile", "claude"
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(
                [step["setup_disposition"] for step in payload["receipt"]["steps"]],
                ["compensated"],
            )
            # Nothing left to undo, so nothing is offered.
            self.assertEqual(payload["receipt"]["rollback_command"], "")

            verified, verification = env.run(
                "marketplace", "receipt", "verify", _COORDINATE, "--profile", "claude"
            )

            self.assertEqual(verified, 0, verification)
            claims = verification["verification"]
            self.assertEqual(claims["false"], 0)
            # The compensated step licenses no question about its former target.
            self.assertNotIn(
                _CONFIGURED, json.dumps(claims), "a compensated step must claim no live file"
            )

    def test_the_payload_a_different_transaction_placed_is_still_installed(self) -> None:
        with _environment_whose_verification_fails() as env:
            self._configured(env)

            code, payload = env.run("marketplace", "status", "--profile", "claude")

            self.assertEqual(code, 0, payload)
            self.assertEqual([item["status"] for item in payload["items"]], ["current"])


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
