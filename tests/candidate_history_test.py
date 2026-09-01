"""Durable CP-14 Candidate history preserves exact compiled objects and lifecycle state."""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.application.candidate_history import (
    parse_source_scan,
    serialize_source_scan,
)
from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.domain.candidates import CandidateState, assess_candidate, reject_candidate
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from tests.maintainer_source_scan_test import _compiled


def _ready_scan():
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        _compiled(),
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok)
    active = scanned.value.active[0]
    ready = CandidateBundle(assess_candidate(active.candidate), active.artifact)
    return dataclasses.replace(scanned.value, active=(ready,), history=(ready,))


class CandidateHistorySerializationTest(unittest.TestCase):
    def test_round_trip_preserves_candidate_state_and_exact_compiled_object(self) -> None:
        scan = _ready_scan()

        serialized = serialize_source_scan(scan)

        self.assertIsInstance(serialized, Ok)
        assert isinstance(serialized, Ok)
        restored = parse_source_scan(serialized.value.index, serialized.value.objects)
        self.assertEqual(restored, Ok(scan))
        self.assertEqual(len(serialized.value.objects), 1)

    def test_superseded_and_rejected_history_remains_auditable(self) -> None:
        first = _ready_scan()
        rejected = dataclasses.replace(
            first.active[0],
            candidate=reject_candidate(first.active[0].candidate, "Policy declined"),
        )
        changed = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            _compiled(revision="b", server="print('changed')\n"),
            previous=(rejected,),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(changed, Ok)

        serialized = serialize_source_scan(changed.value)
        assert isinstance(serialized, Ok)
        restored = parse_source_scan(serialized.value.index, serialized.value.objects)

        self.assertIsInstance(restored, Ok)
        assert isinstance(restored, Ok)
        self.assertEqual(
            {bundle.candidate.state for bundle in restored.value.history},
            {CandidateState.CHANGED, CandidateState.SUPERSEDED},
        )
        self.assertEqual(len(serialized.value.objects), 2)

    def test_missing_compiled_object_is_a_refusal_not_an_empty_history(self) -> None:
        serialized = serialize_source_scan(_ready_scan())
        assert isinstance(serialized, Ok)

        restored = parse_source_scan(serialized.value.index, ())

        self.assertIsInstance(restored, Err)
        assert isinstance(restored, Err)
        self.assertIn("compiled object is missing", restored.diagnostics[0].message)

    def test_scan_revision_cannot_be_rebound_around_candidate_provenance(self) -> None:
        serialized = serialize_source_scan(_ready_scan())
        assert isinstance(serialized, Ok)
        tampered = serialized.value.index.replace(b'"aaaaaaaa', b'"bbbbbbbb', 1)

        restored = parse_source_scan(tampered, serialized.value.objects)

        self.assertIsInstance(restored, Err)

    def test_active_candidate_must_be_the_exact_record_retained_in_history(self) -> None:
        inconsistent = dataclasses.replace(_ready_scan(), history=())

        serialized = serialize_source_scan(inconsistent)

        self.assertIsInstance(serialized, Err)


if __name__ == "__main__":
    unittest.main()
