"""CP-16: ``aart doctor`` measures installed state and proposes only minimal repairs.

The fixture installs through the public configured-registry command and then changes the file a
harness actually reads.  Doctor therefore has to derive both the healthy answer and the drifted
answer from durable receipts plus a fresh machine observation; an executor verdict or a hand-built
view cannot satisfy these tests.
"""

from __future__ import annotations

import json
import pathlib
import unittest
from datetime import datetime, timedelta

from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.placed_installation_e2e_test import SKILL_MANIFEST

SECOND_COORDINATE = "company/skill/documentation"
SECOND_MANIFEST = {
    **SKILL_MANIFEST,
    "artifact": {**SKILL_MANIFEST["artifact"], "name": "documentation"},
}
SECOND_AUTHORED_SKILL: tuple[tuple[str, str], ...] = (
    ("documentation/aart.json", json.dumps(SECOND_MANIFEST)),
    ("documentation/SKILL.md", "# Documentation\n\nExplain the public contract.\n"),
    ("documentation/reference/style.md", "Prefer one observable example.\n"),
)


class DoctorCommandE2ETest(unittest.TestCase):
    def _install(self, env, coordinate: str) -> None:
        code, payload = env.run(
            "marketplace", "install", coordinate, "--profile", "claude", "--yes"
        )
        self.assertEqual(code, 0, payload)

    def _two_installations(self, env) -> None:
        self._install(env, COORDINATE)
        env.publish(SECOND_AUTHORED_SKILL)
        self._install(env, SECOND_COORDINATE)

    def test_a_healthy_machine_reports_every_installation_and_plans_nothing(self) -> None:
        """A non-empty healthy fixture is what makes an empty repair collection evidence."""

        with _environment() as env:
            self._two_installations(env)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["schema_version"], 1)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["operation"], "doctor")
            self.assertEqual(
                datetime.fromisoformat(payload["observed_at"]).utcoffset(), timedelta(0)
            )
            self.assertEqual(payload["summary"], {"ready": 2, "needs_attention": 0})
            self.assertEqual(
                {item["coordinate"] for item in payload["items"]},
                {"company/skill/code-review@1.2.0", "company/skill/documentation@1.2.0"},
            )
            self.assertTrue(payload["items"], "an empty machine would make no repairs vacuous")
            self.assertTrue(all(item["health"] == "ready" for item in payload["items"]))
            self.assertEqual(payload["repairs"], [])

    def test_one_drift_produces_one_plan_for_only_the_drifted_artifacts_components(self) -> None:
        """INV-194: Doctor reconciles the observed delta; it never means reinstall-all."""

        with _environment() as env:
            self._two_installations(env)
            changed = env.project / ".claude/skills/documentation/SKILL.md"
            changed.chmod(0o600)
            changed.write_text("# changed outside AART\n", encoding="utf-8")

            code, payload = env.run("doctor")

            self.assertNotEqual(code, 0, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["summary"], {"ready": 1, "needs_attention": 1})
            items = {item["coordinate"]: item for item in payload["items"]}
            self.assertEqual(items["company/skill/code-review@1.2.0"]["health"], "ready")
            drifted = items["company/skill/documentation@1.2.0"]
            self.assertEqual(drifted["health"], "attention")
            self.assertTrue(drifted["drift"])
            self.assertEqual(set(drifted["drift"][0]), {"component", "kind", "repairable"})
            self.assertEqual(drifted["drift"][0]["kind"], "divergent")
            self.assertTrue(drifted["drift"][0]["repairable"])

            self.assertEqual(len(payload["repairs"]), 1)
            repair = payload["repairs"][0]
            self.assertEqual(repair["artifact"], "company/skill/documentation@1.2.0")
            self.assertTrue(repair["steps"])
            self.assertEqual(
                {step["component"] for step in repair["steps"]},
                {item["component"] for item in drifted["drift"]},
            )
            self.assertNotIn("reinstall", json.dumps(payload).lower())

    def test_the_human_report_names_every_artifact_and_explains_the_drift(self) -> None:
        with _environment() as env:
            self._two_installations(env)
            changed = env.project / ".claude/skills/documentation/SKILL.md"
            changed.chmod(0o600)
            changed.write_text("# changed outside AART\n", encoding="utf-8")

            code, output = env.run_text("doctor")

            self.assertNotEqual(code, 0, output)
            self.assertIn("✓ company/skill/code-review@1.2.0", output)
            self.assertIn("⚠ company/skill/documentation@1.2.0", output)
            self.assertIn("delivery:claude", output)
            self.assertIn("divergent", output)
            self.assertIn("minimal reconciliation plans", output)
            self.assertNotIn("reinstall", output.lower())

    def test_environment_wide_means_project_and_user_installations(self) -> None:
        with _environment() as env:
            self._install(env, COORDINATE)
            env.publish(SECOND_AUTHORED_SKILL)
            code, installed = env.run(
                "marketplace",
                "install",
                SECOND_COORDINATE,
                "--profile",
                "claude",
                "--scope",
                "user",
                "--yes",
            )
            self.assertEqual(code, 0, installed)

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["summary"], {"ready": 2, "needs_attention": 0})
            self.assertEqual(
                {item["coordinate"] for item in payload["items"]},
                {"company/skill/code-review@1.2.0", "company/skill/documentation@1.2.0"},
            )

    def test_inspection_needs_no_source_or_marketplace_content(self) -> None:
        with _environment() as env:
            self._install(env, COORDINATE)
            env.disable_source()

            code, payload = env.run("doctor")

            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["summary"], {"ready": 1, "needs_attention": 0})
            self.assertEqual(payload["items"][0]["coordinate"], "company/skill/code-review@1.2.0")

    def test_an_unreadable_receipt_is_a_machine_readable_refusal_not_an_empty_machine(self) -> None:
        with _environment() as env:
            self._install(env, COORDINATE)
            receipts = list(
                (pathlib.Path(env.paths.data_root) / "state/installations").glob("*.json")
            )
            self.assertEqual(len(receipts), 1)
            receipts[0].write_text("{not-json", encoding="utf-8")

            code, payload = env.run("doctor")

            self.assertNotEqual(code, 0, payload)
            self.assertEqual(payload["schema_version"], 1)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["operation"], "doctor")
            self.assertEqual(len(payload["diagnostics"]), 1)
            self.assertEqual(payload["diagnostics"][0]["code"], "receipt-unreadable")
            self.assertEqual(payload["diagnostics"][0]["severity"], "error")
            self.assertIn("cannot read", payload["diagnostics"][0]["message"])

            text_code, output = env.run_text("doctor")
            self.assertNotEqual(text_code, 0, output)
            self.assertIn("error: cannot read", output)
            self.assertIn(receipts[0].name, output)


if __name__ == "__main__":
    unittest.main()
