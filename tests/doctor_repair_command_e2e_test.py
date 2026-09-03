"""CP-16: Doctor applies only one explicitly reviewed minimal reconciliation plan.

Every scenario enters through the real ``aart doctor`` command over a real canonical installation.
The review and finalize calls are deliberately separate: the first digest is authorization input
to the second, while the second still has to re-observe the machine before any effect runs.
"""

from __future__ import annotations

import unittest
from unittest import mock

from agent_artifacts.commands import doctor as doctor_command
from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.configured_repair_action_e2e_test import _delete_delivery
from tests.configured_uninstall_command_e2e_test import _delivered

INSTALLED_COORDINATE = "company/skill/code-review@1.2.0"


class DoctorRepairCommandE2ETest(unittest.TestCase):
    def _damaged(self, env) -> None:
        code, payload = env.run(
            "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)
        _delete_delivery(env)
        self.assertFalse(_delivered(env).exists())

    def _review(self, env) -> dict:
        code, payload = env.run("doctor", "--repair", INSTALLED_COORDINATE)
        self.assertEqual(code, 0, payload)
        return payload

    def test_repair_without_confirmation_is_a_complete_review_and_writes_nothing(self) -> None:
        with _environment() as env:
            self._damaged(env)

            payload = self._review(env)

            self.assertEqual(payload["operation"], "doctor.repair")
            self.assertFalse(payload["finalized"])
            self.assertEqual(payload["coordinate"], INSTALLED_COORDINATE)
            self.assertEqual(payload["scope"], "project")
            self.assertEqual(payload["review_digest"], payload["review"]["review_digest"])
            self.assertEqual(payload["review"]["artifact"], INSTALLED_COORDINATE)
            self.assertTrue(payload["review"]["steps"])
            self.assertEqual(
                {step["component"] for step in payload["review"]["steps"]},
                {"delivery:claude"},
            )
            self.assertNotIn("reinstall", str(payload).lower())
            self.assertFalse(_delivered(env).exists(), "review applied its own repair")

    def test_human_review_names_the_delta_digest_and_confirmation_boundary(self) -> None:
        with _environment() as env:
            self._damaged(env)

            code, output = env.run_text("doctor", "--repair", INSTALLED_COORDINATE)

            self.assertEqual(code, 0, output)
            self.assertIn(f"Review repair for {INSTALLED_COORDINATE}", output)
            self.assertIn("Components changing: delivery:claude", output)
            self.assertIn("Review identity: sha256:", output)
            self.assertIn("--yes and --expect", output)
            self.assertNotIn("reinstall", output.lower())
            self.assertFalse(_delivered(env).exists())

    def test_repair_requires_an_exact_installed_source_and_version(self) -> None:
        """Each half of "exact" is refused on its own, so neither half rests on the other."""

        with _environment() as env:
            self._damaged(env)

            for underspecified in ("skill/code-review@1.2.0", "company/skill/code-review"):
                with self.subTest(selector=underspecified):
                    code, payload = env.run("doctor", "--repair", underspecified)

                    self.assertNotEqual(code, 0, payload)
                    self.assertEqual(payload["operation"], "doctor.repair")
                    self.assertFalse(payload["finalized"])
                    self.assertEqual(payload["diagnostics"][0]["code"], "consumer-invalid")
                    self.assertIn("source-qualified", payload["diagnostics"][0]["message"])
                    self.assertFalse(_delivered(env).exists())

    def test_yes_without_the_digest_from_a_prior_review_is_refused(self) -> None:
        with _environment() as env:
            self._damaged(env)

            code, payload = env.run("doctor", "--repair", INSTALLED_COORDINATE, "--yes")

            self.assertNotEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            self.assertEqual(payload["operation"], "doctor.repair")
            self.assertEqual(payload["diagnostics"][0]["code"], "consumer-review-mismatch")
            self.assertIn("--expect", payload["diagnostics"][0]["message"])
            self.assertFalse(_delivered(env).exists(), "a refusal still repaired the machine")

    def test_confirmed_review_repairs_and_records_the_observed_delta(self) -> None:
        with _environment() as env:
            self._damaged(env)
            env.disable_source()
            review = self._review(env)

            code, payload = env.run(
                "doctor",
                "--repair",
                INSTALLED_COORDINATE,
                "--yes",
                "--expect",
                review["review_digest"],
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["finalized"])
            self.assertEqual(payload["review_digest"], review["review_digest"])
            self.assertEqual(payload["receipt"]["intent"], "repair")
            self.assertEqual(payload["receipt"]["artifact"], INSTALLED_COORDINATE)
            self.assertEqual(payload["receipt"]["outcome"], "succeeded")
            self.assertEqual(
                {step["component"] for step in payload["receipt"]["steps"]},
                {"delivery:claude"},
            )
            self.assertTrue(_delivered(env).exists())
            status, report = env.run("doctor")
            self.assertEqual(status, 0, report)
            self.assertEqual(report["summary"], {"ready": 1, "needs_attention": 0})

    def test_user_scope_is_selected_explicitly_and_repaired_in_its_own_harness_root(self) -> None:
        with _environment() as env:
            code, installed = env.run(
                "marketplace",
                "install",
                COORDINATE,
                "--profile",
                "claude",
                "--scope",
                "user",
                "--yes",
            )
            self.assertEqual(code, 0, installed)
            delivered = env.home / ".claude/skills/code-review/SKILL.md"
            self.assertTrue(delivered.exists())
            delivered.chmod(0o600)
            delivered.write_text("# user drift\n", encoding="utf-8")

            code, review = env.run("doctor", "--repair", INSTALLED_COORDINATE, "--scope", "user")
            self.assertEqual(code, 0, review)
            self.assertEqual(review["scope"], "user")
            code, completed = env.run(
                "doctor",
                "--repair",
                INSTALLED_COORDINATE,
                "--scope",
                "user",
                "--yes",
                "--expect",
                review["review_digest"],
            )

            self.assertEqual(code, 0, completed)
            self.assertTrue(completed["finalized"])
            self.assertNotEqual(delivered.read_text(encoding="utf-8"), "# user drift\n")
            self.assertFalse(_delivered(env).exists())

    def test_a_changed_plan_is_returned_instead_of_applying_the_old_digest(self) -> None:
        with _environment() as env:
            self._damaged(env)
            review = self._review(env)
            changed = _delivered(env)
            changed.parent.mkdir(parents=True)
            changed.write_text("# different drift\n", encoding="utf-8")

            code, payload = env.run(
                "doctor",
                "--repair",
                INSTALLED_COORDINATE,
                "--yes",
                "--expect",
                review["review_digest"],
            )

            self.assertNotEqual(code, 0, payload)
            self.assertFalse(payload["finalized"])
            self.assertEqual(payload["diagnostics"][0]["code"], "consumer-review-mismatch")
            self.assertEqual(payload["expected_review_digest"], review["review_digest"])
            self.assertNotEqual(payload["review_digest"], review["review_digest"])
            self.assertEqual(changed.read_text(encoding="utf-8"), "# different drift\n")

    def test_the_machine_is_reinspected_under_the_lease_before_execution(self) -> None:
        with _environment() as env:
            self._damaged(env)
            review = self._review(env)
            changed = _delivered(env)
            complete = doctor_command.complete_configured_repair

            def move_machine_after_command_review(prepared, **kwargs):
                changed.parent.mkdir(parents=True)
                changed.write_text("# moved after review\n", encoding="utf-8")
                return complete(prepared, **kwargs)

            with mock.patch.object(
                doctor_command,
                "complete_configured_repair",
                side_effect=move_machine_after_command_review,
            ):
                code, payload = env.run(
                    "doctor",
                    "--repair",
                    INSTALLED_COORDINATE,
                    "--yes",
                    "--expect",
                    review["review_digest"],
                )

            self.assertNotEqual(code, 0, payload)
            self.assertEqual(payload["diagnostics"][0]["code"], "execution-review-stale")
            self.assertIn("changed after Review", payload["diagnostics"][0]["message"])
            self.assertEqual(changed.read_text(encoding="utf-8"), "# moved after review\n")


if __name__ == "__main__":
    unittest.main()
