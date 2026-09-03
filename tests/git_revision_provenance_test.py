"""CP-17 step 2's provenance claims, held where the chain test cannot reach them.

D-148 makes the installed revision part of the reviewed plan and optional everywhere, so that
existing receipt bytes keep their canonical form.  Both halves are claims about inputs no
end-to-end run produces: the chain only ever builds one well-formed revision, and it cannot write
a receipt from before the field existed.

The two halves were measured separately rather than assumed together, and they came apart.
Deleting the `is_pinned_source_revision` clause from `ResolvedArtifact` left all 3,349 tests
passing -- the shape of a revision was held by nothing at all.  Removing the decoder's tolerance of
a missing key does turn `installation_transaction_receipt_test` red, so that half was already held,
but incidentally: by a round-trip whose name speaks of rebuilding an activity entry, over a fixture
that happens to carry no revision.  What is held by accident is not stated, and cannot be relied on
by whoever changes the encoder next.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_artifacts.application.consumer_views import (
    project_installation_receipt,
    receipt_detail_from_data,
    receipt_detail_to_data,
)
from agent_artifacts.domain.identifiers import is_pinned_source_revision
from agent_artifacts.domain.result import Ok
from tests.installation_proposal_test import _resolved
from tests.installation_transaction_receipt_test import MOMENT, _executed

# Deliberately not `"a" * 40`.  That string is the placeholder CP-17 exists to drive out of the
# chain, and a decode test that reused it could not tell a real value from the placeholder.
GIT_REVISION = "1a2b3c4d5e6f1a2b3c4d5e6f1a2b3c4d5e6f1a2b"
LOCAL_REVISION = "local:" + "9f" * 32

# `differing_executors` is suppressed for the reason `consumer_properties_test` records: the scoped
# mutation runner re-runs the same test method object from a fresh runner per mutant, and these
# properties are pure functions of generated input holding no state between executions.
SETTINGS = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=(HealthCheck.too_slow, HealthCheck.differing_executors),
)


class ResolvedRevisionProperties(unittest.TestCase):
    """A revision on a resolved artifact is a pinned Source revision or it is nothing."""

    @SETTINGS
    @given(st.text(max_size=64).filter(lambda value: not is_pinned_source_revision(value)))
    def test_no_unpinned_string_is_accepted_as_a_resolved_revision(self, value: str) -> None:
        with self.assertRaises(ValueError):
            replace(_resolved(), source_revision=value)

    @SETTINGS
    @given(st.sampled_from("0123456789abcdef"))
    def test_a_git_revision_of_the_right_shape_is_accepted_whatever_it_spells(
        self, character: str
    ) -> None:
        artifact = replace(_resolved(), source_revision=character * 40)

        self.assertEqual(artifact.source_revision, character * 40)

    def test_both_pinned_revision_kinds_and_an_absent_one_are_accepted(self) -> None:
        for value in (GIT_REVISION, LOCAL_REVISION, None):
            with self.subTest(revision=value):
                self.assertEqual(replace(_resolved(), source_revision=value).source_revision, value)

    def test_a_truncated_git_revision_is_refused_rather_than_padded(self) -> None:
        """The near-miss, which a shape check written as a prefix test would admit."""

        with self.assertRaises(ValueError):
            replace(_resolved(), source_revision=GIT_REVISION[:12])


class OlderReceiptProvenanceTest(unittest.TestCase):
    """A receipt written before D-148 reads back as unknown provenance, not as a guess."""

    def _receipt(self, revision: str | None):
        """A real executed transaction's receipt, which is the shape that has artifact rows.

        An Activity record does not: its receipt accounts for one action, not for the members of a
        transaction, so the row this test speaks about would not exist to speak about.
        """

        outcome, _ = _executed()
        base = project_installation_receipt(outcome, recorded_at=MOMENT)
        self.assertTrue(base.artifacts, "the fixture must carry an artifact row to speak about")
        return replace(
            base,
            artifacts=(replace(base.artifacts[0], source_revision=revision), *base.artifacts[1:]),
        )

    def _rows(self, data: dict[str, object]) -> list[dict[str, object]]:
        rows = data["artifacts"]
        assert isinstance(rows, list)
        return rows

    def _round_trip(self, data: dict[str, object]):
        parsed = receipt_detail_from_data(json.loads(json.dumps(data)))
        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        return parsed.value

    def test_a_receipt_carrying_a_revision_reads_it_back_unchanged(self) -> None:
        """The half that makes the next test's absence mean something (D-138)."""

        encoded = receipt_detail_to_data(self._receipt(GIT_REVISION))

        self.assertEqual(self._rows(encoded)[0]["source_revision"], GIT_REVISION)
        self.assertEqual(self._round_trip(encoded).artifacts[0].source_revision, GIT_REVISION)

    def test_a_receipt_from_before_the_field_existed_still_reads_back(self) -> None:
        encoded = receipt_detail_to_data(self._receipt(GIT_REVISION))
        del self._rows(encoded)[0]["source_revision"]

        self.assertIsNone(self._round_trip(encoded).artifacts[0].source_revision)

    def test_an_unknown_revision_is_omitted_rather_than_written_as_null(self) -> None:
        """Absent and null are the same answer to a reader and different bytes on disk."""

        encoded = receipt_detail_to_data(self._receipt(None))

        self.assertNotIn("source_revision", self._rows(encoded)[0])
        self.assertIsNone(self._round_trip(encoded).artifacts[0].source_revision)


if __name__ == "__main__":
    unittest.main()
