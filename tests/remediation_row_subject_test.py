"""`QA-080`: a remediation row names what it is about.

The operator saw `4 thing(s) need preparing first` over three rows reading
`configure harness (configuration mutation)` and one reading `configure credential`, and asked
*"jak mam skonfigurowac harness?? nie rozumiem"*. The rows were not wrong; they were
indistinguishable. Each one is about a different harness and the screen had that name in hand --
`ConfigureHarness` carries it, and `_summary` puts it in the Verbose line -- but the row a reader
sees in Fast dropped it.

`QA-078`'s narrowing removes most of the duplication by not planning setup for harnesses the
artifact was never installed into. This holds the other half: where several rows legitimately
remain, they say which is which. CP-23 task 08 reworded each row as the change AART will make
(D-258); the claim is unchanged.
"""

from __future__ import annotations

import dataclasses
import unittest

from aart_cli.application.consumer_views import PresentationProfile, RemediationView
from aart_cli.domain.result import Ok
from aart_cli.tui_consumer import render_remediation
from tests.consumer_flow_test import _begin


class RemediationRowNamesItsSubjectTest(unittest.TestCase):
    """One real plan view, with only its remediations swapped for the ones under test."""

    def _rows(self, *remediations: RemediationView) -> tuple[str, ...]:
        begun = _begin()
        assert isinstance(begun, Ok), getattr(begun, "diagnostics", ())
        view = dataclasses.replace(begun.value.plan, remediations=remediations)
        return render_remediation(view, PresentationProfile.FAST)

    def _harness(self, name: str) -> RemediationView:
        return RemediationView(
            "configure-harness",
            "configuration mutation",
            (f"{name}:project",),
            f"configure-harness: harness={name}",
        )

    def test_a_harness_row_says_which_harness(self) -> None:
        text = "\n".join(self._rows(self._harness("claude")))

        self.assertIn("claude", text)

    def test_rows_that_differ_only_by_subject_are_told_apart(self) -> None:
        rows = self._rows(
            self._harness("claude"), self._harness("codex"), self._harness("opencode")
        )
        named = [line for line in rows if "integration" in line]

        self.assertEqual(3, len(named))
        self.assertEqual(3, len(set(named)), named)

    def test_a_remediation_with_no_subject_still_reads_as_it_did(self) -> None:
        """Nothing gains a stray separator because its kind carries no identifying value."""

        plain = RemediationView(
            "configure-credential", "credential-mutation", ("keychain",), "configure-credential"
        )
        unknown = RemediationView("tune-cache", "local-mutation", ("keychain",), "tune-cache")

        rows = self._rows(plain, unknown)

        self.assertIn("  Store the credential it needs securely", rows)
        self.assertIn("  Tune cache", rows)


if __name__ == "__main__":
    unittest.main()
