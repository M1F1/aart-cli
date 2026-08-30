"""CP-05 pure Candidate and approved Registry lifecycle contracts."""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.domain.artifacts import (
    ArtifactFormat,
    ArtifactKind,
    ArtifactPackage,
    Compatibility,
    Provenance,
)
from agent_artifacts.domain.candidates import (
    CandidateFinding,
    CandidateState,
    FindingSeverity,
    approve_candidate,
    assess_candidate,
    make_candidate,
    mark_candidate_promoted,
    reject_candidate,
    semantic_candidate_diff,
    supersede_candidate,
)
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryLifecycle,
    deprecate_registry_version,
    publish_registry_version,
    registry_version_from_candidate,
    revoke_registry_version,
)


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _package(
    *,
    version: str = "1.0.0",
    input_character: str = "a",
    payload_character: str = "b",
) -> ArtifactPackage:
    return ArtifactPackage(
        ArtifactCoordinate(
            SourceAlias("authors"),
            ArtifactIdentity("mcp", "github-mcp"),
            version,
        ),
        ArtifactKind.MCP,
        ArtifactFormat("aart-mcp-v1"),
        _digest(payload_character),
        Provenance(
            "https://git.example/servers.git",
            "c" * 40,
            "github/aart.yaml",
            _digest(input_character),
            "aart-native-author/1.0.0",
        ),
        Compatibility(("linux",), ("codex",), ">=3.11"),
        protocol="stdio",
    )


class CandidateLifecycleTest(unittest.TestCase):
    def test_candidate_identity_is_input_stable_and_values_are_frozen(self) -> None:
        left = make_candidate(_package(), _digest("d"), SourceAlias("company"))
        right = make_candidate(_package(), _digest("d"), SourceAlias("company"))

        self.assertEqual(left, right)
        self.assertEqual(left.state, CandidateState.NEW)
        self.assertRegex(left.id.value, r"^[0-9a-f]{64}$")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            left.state = CandidateState.READY  # type: ignore[misc]

    def test_validation_distinguishes_ready_warning_invalid_and_manual_approval(self) -> None:
        candidate = make_candidate(_package(), _digest("d"), SourceAlias("company"))
        warning = CandidateFinding("security-note", FindingSeverity.WARNING, "Review finding")
        error = CandidateFinding("schema-invalid", FindingSeverity.ERROR, "Manifest invalid")

        self.assertEqual(assess_candidate(candidate).state, CandidateState.READY)
        self.assertEqual(
            assess_candidate(candidate, findings=(warning,)).state,
            CandidateState.WARNING,
        )
        self.assertEqual(
            assess_candidate(candidate, findings=(error, warning)).state,
            CandidateState.INVALID,
        )
        approval = assess_candidate(candidate, manual_approval_required=True)
        self.assertEqual(approval.state, CandidateState.APPROVAL_REQUIRED)
        self.assertEqual(approve_candidate(approval).state, CandidateState.READY)

    def test_rejection_superseding_and_promotion_are_explicit_transitions(self) -> None:
        candidate = assess_candidate(
            make_candidate(_package(), _digest("d"), SourceAlias("company"))
        )
        changed = make_candidate(
            _package(version="1.1.0", input_character="e"),
            _digest("f"),
            SourceAlias("company"),
            previous=candidate.id,
        )

        rejected = reject_candidate(candidate, "Not approved for this registry")
        self.assertEqual(rejected.state, CandidateState.REJECTED)
        self.assertEqual(rejected.rejection_reason, "Not approved for this registry")
        superseded = supersede_candidate(candidate, changed.id)
        self.assertEqual(superseded.state, CandidateState.SUPERSEDED)
        self.assertEqual(superseded.successor, changed.id)
        promoted = mark_candidate_promoted(candidate, _digest("1"))
        self.assertEqual(promoted.state, CandidateState.PROMOTED)
        self.assertEqual(promoted.registry_snapshot, _digest("1"))

    def test_semantic_diff_precedes_file_diff_and_is_deterministic(self) -> None:
        before = make_candidate(_package(), _digest("d"), SourceAlias("company"))
        after = make_candidate(
            _package(version="1.1.0", input_character="e", payload_character="f"),
            _digest("1"),
            SourceAlias("company"),
            previous=before.id,
        )

        changes = semantic_candidate_diff(before, after)

        self.assertEqual(
            tuple(item.field for item in changes), tuple(sorted(item.field for item in changes))
        )
        self.assertEqual(
            {item.field for item in changes},
            {"artifact_input_digest", "canonical_digest", "payload_digest", "version"},
        )

    def test_registry_payload_is_immutable_while_lifecycle_and_publication_evolve(self) -> None:
        candidate = assess_candidate(
            make_candidate(_package(), _digest("d"), SourceAlias("company"))
        )
        local = registry_version_from_candidate(
            candidate,
            registry_snapshot=_digest("1"),
            mode=PromotionMode.VENDORED,
        )
        published = publish_registry_version(local, _digest("2"))
        deprecated = deprecate_registry_version(
            published,
            reason="A newer version is available",
            replacement="company/mcp/github-mcp@1.1.0",
        )
        revoked = revoke_registry_version(
            deprecated,
            reason="Security review requires attention",
            replacement="company/mcp/github-mcp@1.1.1",
        )

        self.assertEqual(local.publication, PublicationStage.PROMOTED_LOCAL)
        self.assertEqual(published.publication, PublicationStage.PUBLISHED)
        self.assertEqual(deprecated.lifecycle, RegistryLifecycle.DEPRECATED)
        self.assertEqual(revoked.lifecycle, RegistryLifecycle.REVOKED)
        immutable_fields = ("coordinate", "input_digest", "payload_digest", "canonical_digest")
        for field in immutable_fields:
            self.assertEqual(getattr(local, field), getattr(revoked, field))
        self.assertEqual(local.mode, PromotionMode.VENDORED)


if __name__ == "__main__":
    unittest.main()
