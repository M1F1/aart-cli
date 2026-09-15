"""CP-06 published-registry aggregation and Selection resolution."""

from __future__ import annotations

import itertools
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.marketplace_resolution import (
    ARTIFACT_AMBIGUOUS,
    ARTIFACT_REVOKED,
    CROSS_REGISTRY_DENIED,
    VERSION_CONFLICT,
    ApprovedMarketplaceArtifact,
    ApprovedRegistrySnapshot,
    RegistryTrust,
    ResolutionPolicy,
    aggregate_approved_marketplace,
    resolve_selection,
)
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.registry import (
    PromotionMode,
    PublicationStage,
    RegistryArtifactVersion,
    RegistryLifecycle,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    Collection,
    CollectionCoordinate,
    CollectionMember,
    OwnershipKind,
    VersionConstraint,
)


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _version(
    source: str,
    name: str,
    version: str,
    *,
    snapshot_character: str,
    payload_character: str,
    publication: PublicationStage = PublicationStage.PUBLISHED,
    lifecycle: RegistryLifecycle = RegistryLifecycle.PUBLISHED,
) -> RegistryArtifactVersion:
    warning = None if lifecycle is RegistryLifecycle.PUBLISHED else "Security lifecycle finding"
    return RegistryArtifactVersion(
        ArtifactCoordinate(SourceAlias(source), ArtifactIdentity("mcp", name), version),
        CandidateId("1" * 64),
        _digest("2"),
        _digest(payload_character),
        _digest(payload_character),
        _digest(payload_character),
        _digest(snapshot_character),
        PromotionMode.VENDORED,
        publication,
        lifecycle,
        warning,
    )


def _artifact(
    source: str,
    name: str,
    version: str,
    *,
    snapshot_character: str,
    payload_character: str,
    dependencies: tuple[ArtifactRequest, ...] = (),
    publication: PublicationStage = PublicationStage.PUBLISHED,
    lifecycle: RegistryLifecycle = RegistryLifecycle.PUBLISHED,
) -> ApprovedMarketplaceArtifact:
    return ApprovedMarketplaceArtifact(
        _version(
            source,
            name,
            version,
            snapshot_character=snapshot_character,
            payload_character=payload_character,
            publication=publication,
            lifecycle=lifecycle,
        ),
        dependencies,
    )


def _snapshot(
    alias: str,
    character: str,
    artifacts: tuple[ApprovedMarketplaceArtifact, ...],
    collections: tuple[Collection, ...] = (),
) -> ApprovedRegistrySnapshot:
    return ApprovedRegistrySnapshot(
        SourceAlias(alias),
        _digest(character),
        RegistryTrust.REGISTRY_REVIEWED,
        artifacts,
        collections,
    )


def _request(
    name: str,
    constraint: str = "*",
    source: str | None = None,
) -> ArtifactRequest:
    return ArtifactRequest(
        ArtifactIdentity("mcp", name),
        VersionConstraint(constraint),
        None if source is None else SourceAlias(source),
    )


def _marketplace(*snapshots: ApprovedRegistrySnapshot):
    result = aggregate_approved_marketplace(snapshots)
    assert isinstance(result, Ok), result
    return result.value


class ApprovedMarketplaceAggregationTest(unittest.TestCase):
    def test_only_published_versions_cross_the_marketplace_trust_boundary(self) -> None:
        published = _artifact(
            "company", "github", "1.0.0", snapshot_character="a", payload_character="b"
        )
        local = _artifact(
            "company",
            "jira",
            "1.0.0",
            snapshot_character="a",
            payload_character="c",
            publication=PublicationStage.PROMOTED_LOCAL,
        )

        marketplace = _marketplace(_snapshot("company", "a", (local, published)))

        self.assertEqual(
            tuple(item.version.coordinate.artifact.name for item in marketplace.artifacts),
            ("github",),
        )

    def test_registry_snapshot_identity_and_trust_remain_visible_metadata(self) -> None:
        artifact = _artifact(
            "company", "github", "1.0.0", snapshot_character="a", payload_character="b"
        )

        marketplace = _marketplace(_snapshot("company", "a", (artifact,)))

        self.assertEqual(marketplace.registries[0].snapshot, _digest("a"))
        self.assertEqual(marketplace.registries[0].trust, RegistryTrust.REGISTRY_REVIEWED)
        self.assertEqual(marketplace.artifacts[0].version.registry_snapshot, _digest("a"))


class ApprovedMarketplaceResolutionTest(unittest.TestCase):
    def test_unqualified_multi_registry_collision_requires_explicit_source_even_for_same_digest(
        self,
    ) -> None:
        company = _snapshot(
            "company",
            "a",
            (
                _artifact(
                    "company", "github", "1.0.0", snapshot_character="a", payload_character="c"
                ),
            ),
        )
        platform = _snapshot(
            "platform",
            "b",
            (
                _artifact(
                    "platform", "github", "1.0.0", snapshot_character="b", payload_character="c"
                ),
            ),
        )
        marketplace = _marketplace(company, platform)

        ambiguous = resolve_selection(
            marketplace,
            ArtifactSelection((_request("github", "1.0.0"),)),
        )
        explicit = resolve_selection(
            marketplace,
            ArtifactSelection((_request("github", "1.0.0", "platform"),)),
        )

        assert isinstance(ambiguous, Err), ambiguous
        self.assertEqual(ambiguous.diagnostics[0].code, ARTIFACT_AMBIGUOUS)
        assert isinstance(explicit, Ok), explicit
        self.assertEqual(
            explicit.value.artifacts[0].version.coordinate.source, SourceAlias("platform")
        )

    def test_different_content_collision_is_never_resolved_by_registry_priority(self) -> None:
        marketplace = _marketplace(
            _snapshot(
                "company",
                "a",
                (
                    _artifact(
                        "company",
                        "github",
                        "1.0.0",
                        snapshot_character="a",
                        payload_character="c",
                    ),
                ),
            ),
            _snapshot(
                "platform",
                "b",
                (
                    _artifact(
                        "platform",
                        "github",
                        "1.0.0",
                        snapshot_character="b",
                        payload_character="d",
                    ),
                ),
            ),
        )

        result = resolve_selection(
            marketplace,
            ArtifactSelection((_request("github", "1.0.0"),)),
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, ARTIFACT_AMBIGUOUS)
        self.assertIn("company/mcp/github@1.0.0", result.diagnostics[0].message)
        self.assertIn("platform/mcp/github@1.0.0", result.diagnostics[0].message)

    def test_mixed_direct_and_exact_collection_selection_retains_all_ownership(self) -> None:
        github = _artifact(
            "company", "github", "2.4.1", snapshot_character="a", payload_character="b"
        )
        jira = _artifact("company", "jira", "3.2.0", snapshot_character="a", payload_character="c")
        coordinate = CollectionCoordinate(SourceAlias("company"), "data-engineer", "2.1.0")
        collection = Collection(
            coordinate,
            "Data Engineer Toolkit",
            (
                CollectionMember(_request("github", "^2", "company")),
                CollectionMember(_request("jira", "^3", "company")),
            ),
            _digest("a"),
        )
        marketplace = _marketplace(_snapshot("company", "a", (jira, github), (collection,)))

        result = resolve_selection(
            marketplace,
            ArtifactSelection((_request("github", "^2", "company"),), (coordinate,)),
        )

        assert isinstance(result, Ok), result
        self.assertEqual(
            tuple(item.version.coordinate.artifact.name for item in result.value.artifacts),
            ("github", "jira"),
        )
        github_result = result.value.artifacts[0]
        self.assertEqual(
            {reason.kind for reason in github_result.ownership},
            {OwnershipKind.DIRECT, OwnershipKind.COLLECTION},
        )
        self.assertEqual(result.value.selection.collections, (coordinate,))

    def test_highest_single_version_satisfying_every_owner_is_selected(self) -> None:
        versions = tuple(
            _artifact(
                "company", "github", version, snapshot_character="a", payload_character=character
            )
            for version, character in (("1.5.0", "b"), ("1.9.0", "c"), ("2.0.0", "d"))
        )
        marketplace = _marketplace(_snapshot("company", "a", versions))

        result = resolve_selection(
            marketplace,
            ArtifactSelection(
                (
                    _request("github", ">=1.5,<2", "company"),
                    _request("github", "^1", "company"),
                )
            ),
        )

        assert isinstance(result, Ok), result
        self.assertEqual(result.value.artifacts[0].version.coordinate.version, "1.9.0")
        self.assertEqual(len(result.value.artifacts), 1)

    def test_unsatisfiable_owner_constraints_fail_before_planning(self) -> None:
        marketplace = _marketplace(
            _snapshot(
                "company",
                "a",
                (
                    _artifact(
                        "company", "github", "1.9.0", snapshot_character="a", payload_character="b"
                    ),
                    _artifact(
                        "company", "github", "2.1.0", snapshot_character="a", payload_character="c"
                    ),
                ),
            )
        )

        result = resolve_selection(
            marketplace,
            ArtifactSelection(
                (
                    _request("github", ">=1.5,<2", "company"),
                    _request("github", ">=2,<3", "company"),
                )
            ),
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, VERSION_CONFLICT)
        self.assertIn(">=1.5,<2", result.diagnostics[0].message)
        self.assertIn(">=2,<3", result.diagnostics[0].message)

    def test_dependency_ownership_and_exact_edge_are_retained(self) -> None:
        dependency = _request("runtime", "^1")
        parent = _artifact(
            "company",
            "github",
            "2.0.0",
            snapshot_character="a",
            payload_character="b",
            dependencies=(dependency,),
        )
        runtime = _artifact(
            "company", "runtime", "1.4.0", snapshot_character="a", payload_character="c"
        )
        marketplace = _marketplace(_snapshot("company", "a", (runtime, parent)))

        result = resolve_selection(
            marketplace,
            ArtifactSelection((_request("github", "2.0.0", "company"),)),
        )

        assert isinstance(result, Ok), result
        resolved_parent, resolved_runtime = result.value.artifacts
        self.assertEqual(resolved_parent.dependencies, (resolved_runtime.version.coordinate,))
        self.assertEqual(
            {reason.kind for reason in resolved_runtime.ownership},
            {OwnershipKind.DEPENDENCY},
        )

    def test_cross_registry_dependency_is_denied_by_default_and_visible_when_allowed(self) -> None:
        parent = _artifact(
            "company",
            "github",
            "2.0.0",
            snapshot_character="a",
            payload_character="b",
            dependencies=(_request("runtime", "^1", "platform"),),
        )
        runtime = _artifact(
            "platform", "runtime", "1.4.0", snapshot_character="d", payload_character="c"
        )
        marketplace = _marketplace(
            _snapshot("company", "a", (parent,)),
            _snapshot("platform", "d", (runtime,)),
        )
        selection = ArtifactSelection((_request("github", "2.0.0", "company"),))

        denied = resolve_selection(marketplace, selection)
        allowed = resolve_selection(
            marketplace,
            selection,
            policy=ResolutionPolicy(allow_cross_registry=True),
        )

        assert isinstance(denied, Err), denied
        self.assertEqual(denied.diagnostics[0].code, CROSS_REGISTRY_DENIED)
        assert isinstance(allowed, Ok), allowed
        resolved_parent, resolved_runtime = allowed.value.artifacts
        self.assertEqual(resolved_parent.version.coordinate.source, SourceAlias("company"))
        self.assertEqual(resolved_runtime.version.coordinate.source, SourceAlias("platform"))
        self.assertEqual(resolved_runtime.version.registry_snapshot, _digest("d"))

    def test_unqualified_dependency_may_fall_back_across_registries_only_when_allowed(self) -> None:
        parent = _artifact(
            "company",
            "github",
            "2.0.0",
            snapshot_character="a",
            payload_character="b",
            dependencies=(_request("runtime", "^2"),),
        )
        old_local_runtime = _artifact(
            "company", "runtime", "1.9.0", snapshot_character="a", payload_character="c"
        )
        compatible_runtime = _artifact(
            "platform", "runtime", "2.1.0", snapshot_character="d", payload_character="e"
        )
        marketplace = _marketplace(
            _snapshot("company", "a", (parent, old_local_runtime)),
            _snapshot("platform", "d", (compatible_runtime,)),
        )
        selection = ArtifactSelection((_request("github", "2.0.0", "company"),))

        denied = resolve_selection(marketplace, selection)
        allowed = resolve_selection(
            marketplace,
            selection,
            policy=ResolutionPolicy(allow_cross_registry=True),
        )

        assert isinstance(denied, Err), denied
        self.assertEqual(denied.diagnostics[0].code, CROSS_REGISTRY_DENIED)
        assert isinstance(allowed, Ok), allowed
        runtime = next(
            item
            for item in allowed.value.artifacts
            if item.version.coordinate.artifact.name == "runtime"
        )
        self.assertEqual(runtime.version.coordinate.source, SourceAlias("platform"))

    def test_revoked_dependency_blocks_resolution_and_propagates_the_parent(self) -> None:
        parent = _artifact(
            "company",
            "github",
            "2.0.0",
            snapshot_character="a",
            payload_character="b",
            dependencies=(_request("runtime", "1.4.0"),),
        )
        revoked = _artifact(
            "company",
            "runtime",
            "1.4.0",
            snapshot_character="a",
            payload_character="c",
            lifecycle=RegistryLifecycle.REVOKED,
        )
        marketplace = _marketplace(_snapshot("company", "a", (revoked, parent)))

        result = resolve_selection(
            marketplace,
            ArtifactSelection((_request("github", "2.0.0", "company"),)),
        )

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].code, ARTIFACT_REVOKED)
        self.assertIn("company/mcp/github@2.0.0", result.diagnostics[0].message)

    @given(st.permutations(("1.0.0", "1.5.0", "1.9.0")))
    def test_registry_input_order_cannot_change_resolution(self, versions: tuple[str, ...]) -> None:
        artifacts = tuple(
            _artifact(
                "company",
                "github",
                version,
                snapshot_character="a",
                payload_character=character,
            )
            for version, character in zip(versions, itertools.cycle("bcd"))
        )
        marketplace = _marketplace(_snapshot("company", "a", artifacts))

        result = resolve_selection(
            marketplace,
            ArtifactSelection((_request("github", "^1", "company"),)),
        )

        assert isinstance(result, Ok), result
        self.assertEqual(result.value.artifacts[0].version.coordinate.version, "1.9.0")


if __name__ == "__main__":
    unittest.main()
