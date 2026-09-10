"""Collection Candidates survive Source Sync as durable, auditable history."""

from __future__ import annotations

import dataclasses
import json
import unittest

from agent_artifacts.application.candidate_history import (
    parse_source_scan,
    serialize_source_scan,
    source_scan_object_digests,
)
from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.domain.candidates import CandidateId, CandidateState
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    SourceAlias,
)
from agent_artifacts.domain.registry import PromotionMode, RegistryArtifactVersion
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_source
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from tests.authoring_compiler_test import _file
from tests.maintainer_source_scan_test import _digest


def _snapshot(
    *,
    version: str = "2.1.0",
    member: str = "company/mcp/github@^2",
    include_second: bool = False,
):
    document = {
        "schema": "aart.dev/collection/v1",
        "name": "data-engineer",
        "version": version,
        "summary": "Approved data engineering tools.",
        "artifacts": [member],
    }
    files = [_file("collections/data-engineer/aart.json", json.dumps(document))]
    if include_second:
        second = {
            **document,
            "name": "platform-engineer",
            "summary": "Approved platform engineering tools.",
        }
        files.append(_file("collections/platform-engineer/aart.json", json.dumps(second)))
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, tuple(files))


def _compiled(revision: str, *, version: str = "2.1.0", include_second: bool = False):
    result = compile_author_source(
        _snapshot(version=version, include_second=include_second),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision=revision,
    )
    assert isinstance(result, Ok)
    return result.value


def _scan(
    revision: str,
    *,
    version: str = "2.1.0",
    previous=(),
    include_second: bool = False,
):
    compiled = _compiled(revision, version=version, include_second=include_second)
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

    def test_a_promoted_collection_record_is_not_superseded_by_a_later_scan(self) -> None:
        """`QA-062`: what the registry published is not this scan's to overwrite.

        The same rule the artifact path enforces, where the domain refuses outright. Nothing here
        raises, so without this the promoted record would quietly become `superseded` and the
        history would stop saying that the Collection was ever published.
        """

        first = _scan("a" * 40)
        published = dataclasses.replace(first.collection_active[0], state=CandidateState.PROMOTED)

        second = _scan("b" * 40, version="2.2.0", previous=(published,))

        kept = next(item for item in second.collection_history if item.id == published.id)
        self.assertEqual(kept.state, CandidateState.PROMOTED)
        self.assertIsNone(kept.successor)
        self.assertEqual(second.collection_active[0].previous, published.id)

    def test_registry_approval_refreshes_an_unchanged_collection_as_promoted(self) -> None:
        first = _scan("a" * 40)
        candidate = first.collection_active[0]
        approved = RegistryArtifactVersion(
            ArtifactCoordinate(
                SourceAlias("company"),
                ArtifactIdentity("collection", candidate.name),
                candidate.version,
            ),
            candidate.id,
            candidate.input_digest,
            _digest("1"),
            candidate.canonical_digest,
            _digest("2"),
            _digest("3"),
            PromotionMode.VENDORED,
        )
        compiled = _compiled("a" * 40)

        synced = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            compiled.artifacts,
            collections=compiled.collections,
            previous=(),
            previous_collections=first.collection_history,
            approved=(approved,),
            target_registry=SourceAlias("company"),
        )

        assert isinstance(synced, Ok)
        self.assertEqual(synced.value.collection_active[0].id, candidate.id)
        self.assertEqual(
            synced.value.collection_active[0].state,
            CandidateState.PROMOTED,
        )
        self.assertEqual(
            synced.value.collection_history[0].state,
            CandidateState.PROMOTED,
        )

    def test_registry_refresh_finds_the_current_collection_after_superseded_history(self) -> None:
        first = _scan("a" * 40)
        second = _scan(
            "b" * 40,
            version="2.2.0",
            previous=first.collection_history,
        )
        candidate = second.collection_active[0]
        superseded = next(
            item for item in second.collection_history if item.state is CandidateState.SUPERSEDED
        )
        approved = RegistryArtifactVersion(
            ArtifactCoordinate(
                SourceAlias("company"),
                ArtifactIdentity("collection", candidate.name),
                candidate.version,
            ),
            candidate.id,
            candidate.input_digest,
            _digest("1"),
            candidate.canonical_digest,
            _digest("2"),
            _digest("3"),
            PromotionMode.VENDORED,
        )
        compiled = _compiled("b" * 40, version="2.2.0")

        synced = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            compiled.artifacts,
            collections=compiled.collections,
            previous=(),
            previous_collections=(superseded, candidate),
            approved=(approved,),
            target_registry=SourceAlias("company"),
        )

        assert isinstance(synced, Ok)
        self.assertEqual(synced.value.collection_active[0].state, CandidateState.PROMOTED)

    def test_registry_refresh_continues_after_one_unchanged_collection(self) -> None:
        first = _scan("a" * 40, include_second=True)
        candidate = next(item for item in first.collection_active if item.name == "data-engineer")
        approved = RegistryArtifactVersion(
            ArtifactCoordinate(
                SourceAlias("company"),
                ArtifactIdentity("collection", candidate.name),
                candidate.version,
            ),
            candidate.id,
            candidate.input_digest,
            _digest("1"),
            candidate.canonical_digest,
            _digest("2"),
            _digest("3"),
            PromotionMode.VENDORED,
        )
        compiled = _compiled("a" * 40, include_second=True)

        synced = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            compiled.artifacts,
            collections=compiled.collections,
            previous=(),
            previous_collections=first.collection_history,
            approved=(approved,),
            target_registry=SourceAlias("company"),
        )

        assert isinstance(synced, Ok)
        self.assertEqual(
            {item.name: item.state for item in synced.value.collection_active},
            {
                "data-engineer": CandidateState.PROMOTED,
                "platform-engineer": CandidateState.NEW,
            },
        )

    def test_registry_approval_marks_a_newly_observed_collection_as_promoted(self) -> None:
        first = _scan("a" * 40)
        candidate = first.collection_active[0]
        approved = RegistryArtifactVersion(
            ArtifactCoordinate(
                SourceAlias("company"),
                ArtifactIdentity("collection", candidate.name),
                candidate.version,
            ),
            candidate.id,
            candidate.input_digest,
            _digest("1"),
            candidate.canonical_digest,
            _digest("2"),
            _digest("3"),
            PromotionMode.VENDORED,
        )
        compiled = _compiled("a" * 40)

        synced = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            compiled.artifacts,
            collections=compiled.collections,
            previous=(),
            previous_collections=(),
            approved=(approved,),
            target_registry=SourceAlias("company"),
        )

        assert isinstance(synced, Ok)
        self.assertEqual(synced.value.collection_active[0].state, CandidateState.PROMOTED)

    def test_collection_registry_refresh_requires_exact_published_content(self) -> None:
        first = _scan("a" * 40)
        candidate = first.collection_active[0]
        approved = RegistryArtifactVersion(
            ArtifactCoordinate(
                SourceAlias("company"),
                ArtifactIdentity("collection", candidate.name),
                candidate.version,
            ),
            CandidateId("f" * 64),
            candidate.input_digest,
            _digest("1"),
            candidate.canonical_digest,
            _digest("2"),
            _digest("3"),
            PromotionMode.VENDORED,
        )
        compiled = _compiled("a" * 40)

        synced = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            compiled.artifacts,
            collections=compiled.collections,
            previous=(),
            previous_collections=first.collection_history,
            approved=(approved,),
            target_registry=SourceAlias("company"),
        )

        assert isinstance(synced, Ok)
        refreshed = synced.value.collection_active[0]
        self.assertEqual(refreshed.state, CandidateState.INVALID)
        self.assertEqual(len(refreshed.findings), 1)
        self.assertEqual(refreshed.findings[0].code, "registry-version-immutable")
        self.assertEqual(refreshed.findings[0].severity.value, "error")
        self.assertEqual(
            refreshed.findings[0].message,
            "Published Collection coordinate/version already contains different canonical content",
        )

    def test_collection_registry_refresh_ignores_other_coordinates(self) -> None:
        first = _scan("a" * 40)
        candidate = first.collection_active[0]
        approved = RegistryArtifactVersion(
            ArtifactCoordinate(
                SourceAlias("company"),
                ArtifactIdentity("collection", candidate.name),
                candidate.version,
            ),
            candidate.id,
            candidate.input_digest,
            _digest("1"),
            candidate.canonical_digest,
            _digest("2"),
            _digest("3"),
            PromotionMode.VENDORED,
        )
        same_version_elsewhere = dataclasses.replace(
            approved,
            coordinate=ArtifactCoordinate(
                SourceAlias("other"),
                ArtifactIdentity("collection", "other"),
                candidate.version,
            ),
        )
        same_registry_other_coordinate = dataclasses.replace(
            approved,
            coordinate=ArtifactCoordinate(
                SourceAlias("company"),
                ArtifactIdentity("collection", "other"),
                "9.9.9",
            ),
        )
        compiled = _compiled("a" * 40)

        synced = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            compiled.artifacts,
            collections=compiled.collections,
            previous=(),
            previous_collections=first.collection_history,
            approved=(same_version_elsewhere, same_registry_other_coordinate),
            target_registry=SourceAlias("company"),
        )

        assert isinstance(synced, Ok)
        self.assertEqual(synced.value.collection_active, first.collection_active)

    def test_collection_registry_refresh_leaves_guarded_states_alone(self) -> None:
        first = _scan("a" * 40)
        candidate = first.collection_active[0]
        approved = RegistryArtifactVersion(
            ArtifactCoordinate(
                SourceAlias("company"),
                ArtifactIdentity("collection", candidate.name),
                candidate.version,
            ),
            candidate.id,
            candidate.input_digest,
            _digest("1"),
            candidate.canonical_digest,
            _digest("2"),
            _digest("3"),
            PromotionMode.VENDORED,
        )
        compiled = _compiled("a" * 40)

        for state in (
            CandidateState.REJECTED,
            CandidateState.SOURCE_REMOVED,
            CandidateState.PROMOTED,
        ):
            with self.subTest(state=state):
                prior = dataclasses.replace(candidate, state=state)
                synced = reconcile_source_scan(
                    SourceAlias("authors"),
                    "a" * 40,
                    compiled.artifacts,
                    collections=compiled.collections,
                    previous=(),
                    previous_collections=(prior,),
                    approved=(approved,),
                    target_registry=SourceAlias("company"),
                )

                assert isinstance(synced, Ok)
                self.assertEqual(synced.value.collection_active, (prior,))

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
