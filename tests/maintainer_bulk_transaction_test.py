"""CP-14 step 5: the bulk promotion transaction screens 43–45 review and commit.

Bulk promotion has to be *one* transaction, which is exactly what a loop over single promotions
would not be: each iteration would take its own registry snapshot, write its own commit and be able
to half-succeed.  So the reviewed transaction carries a set of promotions rather than one, and every
recheck at confirmation time covers the whole set.
"""

from __future__ import annotations

import json
import unittest

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.application.maintainer_promotion import (
    PreparedCandidatePromotionTransaction,
    plan_promotion_transaction,
    prepare_candidate_promotion,
    prepare_promotion_transaction,
)
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.sources.model import source_snapshot_digest


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _scan(names, *, registry: str = "company"):
    entries: list[SnapshotEntry] = []
    for name in names:
        manifest = {
            "schema": "aart.dev/mcp/v1",
            "artifact": {"name": name, "kind": "mcp", "version": "1.0.0"},
            "payload": {"include": ["server.py"]},
            "transport": {"type": "stdio"},
            "runtime": {"type": "python", "version": ">=3.11"},
            "launch": {"type": "python", "entrypoint": "server.py"},
        }
        entries.append(_entry(f"{name}/aart.json", json.dumps(manifest, sort_keys=True)))
        entries.append(_entry(f"{name}/server.py", "print('x')\n"))
    compiled = compile_author_snapshot(
        SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, tuple(entries)),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias(registry),
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value


def _workspace() -> SourceSnapshot:
    return SourceSnapshot(SnapshotOrigin.LOCAL, ())


def _approved(alias: str = "company") -> ApprovedRegistryState:
    """The baseline a promotion is prepared against is the workspace it will be applied to."""

    digest = source_snapshot_digest(_workspace())
    assert isinstance(digest, Ok), digest
    return ApprovedRegistryState(SourceAlias(alias), "f" * 40, digest.value, ())


def _prepared(bundle: CandidateBundle, approved: ApprovedRegistryState):
    policy = EffectivePolicy()
    prepared = prepare_candidate_promotion(
        bundle,
        validate_candidate(bundle, policy=policy),
        policy,
        approved,
        mode=PromotionMode.VENDORED,
    )
    assert isinstance(prepared, Ok), prepared
    return prepared.value


class BulkTransactionPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.approved = _approved()
        self.scan = _scan(("github-mcp", "jira-mcp"))
        self.promotions = tuple(_prepared(item, self.approved) for item in self.scan.active)

    def test_two_candidates_plan_as_one_transaction_with_one_snapshot(self) -> None:
        planned = plan_promotion_transaction(self.promotions, _workspace())

        assert isinstance(planned, Ok), planned
        self.assertEqual(len(planned.value.audits), 2)
        self.assertEqual(len(planned.value.versions), 2)
        self.assertEqual(
            {str(item.registry_snapshot) for item in planned.value.versions},
            {str(planned.value.next_registry_snapshot)},
        )
        self.assertEqual(
            {str(item.registry_snapshot_after) for item in planned.value.audits},
            {str(planned.value.next_registry_snapshot)},
        )

    def test_a_bulk_transaction_is_not_either_of_its_single_transactions(self) -> None:
        """If the digests matched, promoting two would be indistinguishable from promoting one."""

        both = plan_promotion_transaction(self.promotions, _workspace())
        one = plan_promotion_transaction(self.promotions[:1], _workspace())

        assert isinstance(both, Ok) and isinstance(one, Ok)
        self.assertNotEqual(both.value.review_digest, one.value.review_digest)

    def test_candidates_of_two_registries_cannot_be_one_transaction(self) -> None:
        other = _scan(("other-mcp",), registry="partners")
        mixed = (*self.promotions, _prepared(other.active[0], _approved("partners")))

        planned = plan_promotion_transaction(mixed, _workspace())

        self.assertIsInstance(planned, Err)

    def test_an_empty_selection_is_refused_rather_than_planned(self) -> None:
        self.assertIsInstance(plan_promotion_transaction((), _workspace()), Err)


class BulkTransactionPrepareTest(unittest.TestCase):
    def setUp(self) -> None:
        self.approved = _approved()
        self.scan = _scan(("github-mcp", "jira-mcp"))
        self.policy = EffectivePolicy()

    def _transaction(self, bundles):
        return prepare_promotion_transaction(
            bundles,
            tuple(validate_candidate(item, policy=self.policy) for item in bundles),
            self.policy,
            self.approved,
            _workspace(),
            mode=PromotionMode.VENDORED,
        )

    def test_a_prepared_transaction_carries_every_promotion_it_would_apply(self) -> None:
        prepared = self._transaction(self.scan.active)

        assert isinstance(prepared, Ok), prepared
        self.assertIsInstance(prepared.value, PreparedCandidatePromotionTransaction)
        self.assertEqual(len(prepared.value.promotions), 2)
        self.assertEqual(len(prepared.value.plan.audits), 2)
        self.assertEqual(
            prepared.value.review_digest,
            prepared.value.plan.review_digest,
        )

    def test_one_candidate_still_prepares_the_same_transaction_it_always_did(self) -> None:
        single = self._transaction(self.scan.active[:1])

        assert isinstance(single, Ok), single
        self.assertEqual(len(single.value.promotions), 1)

    def test_a_workspace_that_does_not_match_the_baseline_is_refused(self) -> None:
        moved = SourceSnapshot(SnapshotOrigin.LOCAL, (_entry("artifacts/stray.txt", "x\n"),))

        prepared = prepare_promotion_transaction(
            self.scan.active,
            tuple(validate_candidate(item, policy=self.policy) for item in self.scan.active),
            self.policy,
            self.approved,
            moved,
            mode=PromotionMode.VENDORED,
        )

        self.assertIsInstance(prepared, Err)

    def test_a_refused_candidate_takes_the_whole_transaction_down_by_name(self) -> None:
        """One transaction succeeds or fails as one; a partly-promoted selection is not a thing."""

        flawed = _scan(("github-mcp",), registry="partners").active
        prepared = self._transaction((*self.scan.active, *flawed))

        self.assertIsInstance(prepared, Err)


if __name__ == "__main__":
    unittest.main()
