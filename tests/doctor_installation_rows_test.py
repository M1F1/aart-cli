"""Doctor addresses an installation, not an artifact (§169.3).

Opening Doctor raised `ValueError: consumer UI event is invalid` when one MCP was installed into two
harnesses and both needed attention. Doctor keyed its rows by coordinate, rows have to be distinct,
and the two installations made the same row twice. Installed and repair already address an
installation as `coordinate#harness`.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_views import (
    ConsumerScreen,
    LifecycleDriftView,
    project_activity,
    project_dashboard,
    project_doctor,
)
from aart_cli.tui_consumer import CanonicalScreenSource, ConsumerScreens, run_consumer_shell
from tests.consumer_shell_test import TODAY, FakeTerminal, _at, _Preferences, installed

COORDINATE = "public/mcp/jira@2.2.0"
DRIFT = (LifecycleDriftView("launcher", "missing", True),)


def _installations():
    broken = installed(COORDINATE, "broken", DRIFT)
    return (replace(broken, harness="claude"), replace(broken, harness="opencode"))


def _screens() -> ConsumerScreens:
    artifacts = _installations()
    return ConsumerScreens(
        project_dashboard(artifacts, registry_count=1),
        artifacts,
        project_activity((), today=TODAY),
        doctor=project_doctor(artifacts),
    )


class DoctorAddressesInstallationsTest(unittest.TestCase):
    def test_one_artifact_in_two_harnesses_is_two_issues(self) -> None:
        doctor = project_doctor(_installations())

        expected = (f"{COORDINATE}#claude", f"{COORDINATE}#opencode")
        self.assertEqual(doctor.issues, expected)
        self.assertEqual(doctor.repairable_issues, expected)

    def test_doctor_opens_on_each_installation_needing_attention(self) -> None:
        terminal = FakeTerminal()
        finished = run_consumer_shell(
            CanonicalScreenSource(_screens()),
            terminal,
            state=_at(ConsumerScreen.DOCTOR),
            settings_writer=_Preferences(),
        )

        self.assertIs(finished.session.screen, ConsumerScreen.DOCTOR)
        self.assertEqual(finished.rows, (f"{COORDINATE}#claude", f"{COORDINATE}#opencode"))
        doctor = terminal.screen_containing("/ Doctor")
        self.assertIn(f"⚠ {COORDINATE}#claude", doctor)
        self.assertIn(f"⚠ {COORDINATE}#opencode", doctor)
        self.assertEqual(doctor.count("launcher: missing"), 2, doctor)


if __name__ == "__main__":
    unittest.main()
