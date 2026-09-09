"""Collection Candidates survive Source Sync as durable, auditable history."""

from __future__ import annotations

import json
import unittest

from agent_artifacts.application.candidate_history import (
    parse_source_scan,
    serialize_source_scan,
    source_scan_object_digests,
)
from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_source
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from tests.authoring_compiler_test import _file


def _snapshot(*, version: str = "2.1.0", member: str = "company/mcp/github@^2"):
    document = {
        "schema": "aart.dev/collection/v1",
        "name": "data-engineer",
        "version": version,
        "summary": "Approved data engineering tools.",
        "artifacts": [member],
    }
    return SourceSnapshot(
        SnapshotOrigin.IMMUTABLE_GIT,
        (_file("collections/data-engineer/aart.json", json.dumps(document)),),
    )


def _compiled(revision: str, *, version: str = "2.1.0"):
    result = compile_author_source(
        _snapshot(version=version),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision=revision,
    )
    assert isinstance(result, Ok)
    return result.value


def _scan(revision: str, *, version: str = "2.1.0", previous=()):
    compiled = _compiled(revision, version=version)
    result = reconcile_source_scan(
        SourceAlias("authors"),
        revision,
        compiled.artifacts,
        collections=compiled.collections,
        previous=(),
        previous_collections=previous,
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(result, Ok), result
    return result.value


class MaintainerCollectionHistoryTest(unittest.TestCase):
    def test_collection_manifest_creates_a_versioned_candidate_and_round_trips_durably(
        self,
    ) -> None:
        scan = _scan("a" * 40)

        self.assertEqual(scan.manifest_count, 1)
        self.assertEqual(scan.active, ())
        self.assertEqual(len(scan.collection_active), 1)
        candidate = scan.collection_active[0]
        self.assertEqual(candidate.name, "data-engineer")
        self.assertEqual(candidate.version, "2.1.0")
        self.assertEqual(candidate.state, CandidateState.NEW)

        serialized = serialize_source_scan(scan)
        self.assertIsInstance(serialized, Ok)
        assert isinstance(serialized, Ok)
        self.assertEqual(source_scan_object_digests(serialized.value.index), Ok(()))
        self.assertEqual(parse_source_scan(serialized.value.index, ()), Ok(scan))

    def test_changed_collection_supersedes_but_does_not_erase_the_previous_candidate(self) -> None:
        first = _scan("a" * 40)
        second = _scan(
            "b" * 40,
            version="2.2.0",
            previous=first.collection_history,
        )

        self.assertEqual(len(second.collection_history), 2)
        current = second.collection_active[0]
        prior = next(item for item in second.collection_history if item.id != current.id)
        self.assertEqual(current.state, CandidateState.CHANGED)
        self.assertEqual(current.previous, prior.id)
        self.assertEqual(prior.state, CandidateState.SUPERSEDED)
        self.assertEqual(prior.successor, current.id)

    def test_disappearing_collection_is_retained_as_source_removed(self) -> None:
        first = _scan("a" * 40)
        removed = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            (),
            collections=(),
            previous=(),
            previous_collections=first.collection_history,
            approved=(),
            target_registry=SourceAlias("company"),
        )

        self.assertIsInstance(removed, Ok)
        assert isinstance(removed, Ok)
        self.assertEqual(removed.value.collection_active, ())
        self.assertEqual(
            removed.value.collection_history[0].state,
            CandidateState.SOURCE_REMOVED,
        )


if __name__ == "__main__":
    unittest.main()
