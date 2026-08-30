"""CP-05 source scan reconciliation over CP-04 compiled author artifacts."""

from __future__ import annotations

import dataclasses
import json
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.domain.candidates import (
    CandidateState,
    assess_candidate,
    reject_candidate,
)
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.registry import PromotionMode, registry_version_from_candidate
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _compiled(
    *,
    revision: str = "a",
    server: str = "print('ready')\n",
    unrelated: str = "first",
    version: str = "1.0.0",
):
    manifest = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "github-mcp", "kind": "mcp", "version": version},
        "payload": {"include": ["server.py", "requirements.txt"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
        "compatibility": {"harnesses": ["codex"]},
    }
    snapshot = SourceSnapshot(
        SnapshotOrigin.IMMUTABLE_GIT,
        (
            _entry("github/aart.json", json.dumps(manifest)),
            _entry("github/server.py", server),
            _entry("github/requirements.txt", "dependency==1.0\n"),
            _entry("README.md", unrelated),
        ),
    )
    compiled = compile_author_snapshot(
        snapshot,
        source_alias=SourceAlias("authors"),
        source="https://git.example/servers.git",
        revision=revision * 40,
    )
    assert isinstance(compiled, Ok)
    return compiled.value


class MaintainerSourceScanTest(unittest.TestCase):
    def test_scan_creates_candidates_but_never_registry_mutations(self) -> None:
        approved = ()

        scanned = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=approved,
            target_registry=SourceAlias("company"),
        )

        self.assertIsInstance(scanned, Ok)
        assert isinstance(scanned, Ok)
        self.assertEqual(scanned.value.manifest_count, 1)
        self.assertEqual(scanned.value.active[0].candidate.state, CandidateState.NEW)
        self.assertEqual(scanned.value.registry_mutations, ())
        self.assertEqual(approved, ())

    def test_unrelated_revision_churn_preserves_the_exact_rejected_candidate(self) -> None:
        initial = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(initial, Ok)
        rejected = dataclasses.replace(
            initial.value.active[0],
            candidate=reject_candidate(
                initial.value.active[0].candidate,
                "Not approved for this trust domain",
            ),
        )

        rescanned = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            _compiled(revision="b", unrelated="changed outside artifact"),
            previous=(rejected,),
            approved=(),
            target_registry=SourceAlias("company"),
        )

        self.assertIsInstance(rescanned, Ok)
        assert isinstance(rescanned, Ok)
        self.assertEqual(rescanned.value.active, (rejected,))
        self.assertEqual(rescanned.value.active[0].candidate.state, CandidateState.REJECTED)

    @given(
        revision=st.text(alphabet="0123456789abcdef", min_size=1, max_size=1),
        unrelated=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789 ",
            min_size=0,
            max_size=80,
        ),
    )
    def test_rejection_is_stable_for_arbitrary_unselected_revision_churn(
        self,
        revision: str,
        unrelated: str,
    ) -> None:
        initial = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(initial, Ok)
        rejected = dataclasses.replace(
            initial.value.active[0],
            candidate=reject_candidate(initial.value.active[0].candidate, "Policy declined"),
        )

        rescanned = reconcile_source_scan(
            SourceAlias("authors"),
            revision * 40,
            _compiled(revision=revision, unrelated=unrelated),
            previous=(rejected,),
            approved=(),
            target_registry=SourceAlias("company"),
        )

        self.assertIsInstance(rescanned, Ok)
        assert isinstance(rescanned, Ok)
        self.assertEqual(rescanned.value.active, (rejected,))

    def test_changed_input_supersedes_history_and_reopens_review(self) -> None:
        initial = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(initial, Ok)
        rejected = dataclasses.replace(
            initial.value.active[0],
            candidate=reject_candidate(initial.value.active[0].candidate, "Needs revision"),
        )

        changed = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            _compiled(revision="b", server="print('changed')\n"),
            previous=(rejected,),
            approved=(),
            target_registry=SourceAlias("company"),
        )

        self.assertIsInstance(changed, Ok)
        assert isinstance(changed, Ok)
        self.assertEqual(changed.value.active[0].candidate.state, CandidateState.CHANGED)
        prior = next(
            item for item in changed.value.history if item.candidate.id == rejected.candidate.id
        )
        self.assertEqual(prior.candidate.state, CandidateState.SUPERSEDED)
        self.assertEqual(prior.candidate.successor, changed.value.active[0].candidate.id)

    def test_missing_manifest_marks_source_removed_without_touching_registry(self) -> None:
        initial = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(initial, Ok)

        missing = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            (),
            previous=initial.value.history,
            approved=(),
            target_registry=SourceAlias("company"),
        )

        self.assertIsInstance(missing, Ok)
        assert isinstance(missing, Ok)
        self.assertEqual(missing.value.active, ())
        self.assertEqual(missing.value.history[0].candidate.state, CandidateState.SOURCE_REMOVED)
        self.assertEqual(missing.value.registry_mutations, ())

    def test_published_coordinate_is_recognized_and_different_content_is_invalid(self) -> None:
        initial = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(initial, Ok)
        ready = dataclasses.replace(
            initial.value.active[0],
            candidate=assess_candidate(initial.value.active[0].candidate),
        )
        approved = registry_version_from_candidate(
            ready.candidate,
            registry_snapshot=_digest("1"),
            mode=PromotionMode.VENDORED,
        )

        same = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(approved,),
            target_registry=SourceAlias("company"),
        )
        conflict = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            _compiled(revision="b", server="print('different')\n"),
            previous=(),
            approved=(approved,),
            target_registry=SourceAlias("company"),
        )

        self.assertIsInstance(same, Ok)
        self.assertIsInstance(conflict, Ok)
        assert isinstance(same, Ok) and isinstance(conflict, Ok)
        self.assertEqual(same.value.active[0].candidate.state, CandidateState.PROMOTED)
        invalid = conflict.value.active[0].candidate
        self.assertEqual(invalid.state, CandidateState.INVALID)
        self.assertIn("registry-version-immutable", {item.code for item in invalid.findings})


if __name__ == "__main__":
    unittest.main()
