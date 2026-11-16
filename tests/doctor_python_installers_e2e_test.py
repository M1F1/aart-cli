"""§216: ``aart-cli doctor`` reports pip and uv as an install runs them, through the public command.

The first test runs the real probes against this interpreter, so the section is evidence of the
command's own wiring rather than of a hand-built view. The index check is replaced only where the
test needs a failure the machine running it does not have.
"""

from __future__ import annotations

import sys
import unittest
from unittest import mock

from aart_cli.application.python_installers import (
    IndexCheck,
    InstallerFailureKind,
    PythonInstallersReadiness,
    installer_failure,
)
from tests.configured_install_command_e2e_test import _environment


class DoctorPythonInstallersE2ETest(unittest.TestCase):
    def test_doctor_reports_this_interpreter_and_fetches_nothing_unless_asked(self) -> None:
        with _environment() as env:
            code, payload = env.run("doctor")
            _, text = env.run_text("doctor")

        self.assertEqual(code, 0, payload)
        section = payload["python_installers"]
        self.assertEqual(section["interpreter"], sys.executable)
        self.assertIsNone(section["pip"]["index"])
        self.assertIsNone(section["uv"]["index"])
        self.assertIn("Python installers (as aart-cli runs them)", text)
        self.assertIn("aart-cli doctor --check-index", text)

    def test_an_unreachable_index_fails_doctor_and_names_the_cause(self) -> None:
        failing = PythonInstallersReadiness(
            sys.executable,
            True,
            "24.2",
            None,
            pip_index=IndexCheck(
                False,
                installer_failure(
                    "WARNING: Retrying after SSLError(CERTIFICATE_VERIFY_FAILED)\n"
                    "ERROR: No matching distribution found for pip\n"
                ),
            ),
        )
        with (
            _environment() as env,
            mock.patch(
                "aart_cli.commands.doctor.read_python_installers", return_value=failing
            ) as read,
        ):
            code, payload = env.run("doctor", "--check-index")

        read.assert_called_once_with(check_index=True)
        self.assertNotEqual(code, 0)
        self.assertFalse(payload["ok"])
        failure = payload["python_installers"]["pip"]["index"]["failure"]
        self.assertEqual(failure["kind"], InstallerFailureKind.CERTIFICATE.value)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", failure["line"])


if __name__ == "__main__":
    unittest.main()
