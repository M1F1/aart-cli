"""End to end: the front door describes the report behind it.

CP-16 step 5. Steps 2, 4a, 4b and 4c each made a capability reachable from `aart doctor` that had
been sitting at a seam with no verb reporting it. The command's own `--help` still described the
step-1 report, so an operator was told about one of six sections and had no way to discover the
other five short of running it and reading the output.

A capability nobody can find is only marginally better than one nobody can reach, which is the same
argument the whole slice has been making one section at a time.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from agent_artifacts import cli


class DoctorHelpE2ETest(unittest.TestCase):
    def _help(self, *argv: str) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exit:
            cli.main([*argv, "--help"])
        self.assertEqual(exit.exception.code, 0)
        return output.getvalue().lower()

    def test_the_help_names_every_section_the_report_carries(self) -> None:
        text = self._help("doctor")

        for subject in (
            "drift",
            "offline",
            "interrupted",
            "activity",
            "credential",
            "configuration",
        ):
            with self.subTest(subject=subject):
                self.assertIn(subject, text)

    def test_the_help_says_the_report_alone_changes_nothing(self) -> None:
        """The safety half: an operator must be able to tell that running it is free."""

        text = self._help("doctor")

        self.assertIn("changes nothing", text)
        self.assertIn("--expect", text)

    def test_the_top_level_help_offers_doctor_as_the_way_in(self) -> None:
        """A section named only inside `doctor --help` is still undiscoverable from the top."""

        self.assertIn("doctor", self._help())


if __name__ == "__main__":
    unittest.main()
