"""CP-31 step 2: the Registry assigns versions by counting approved changes (§173.2, D-423, D-424).

A source manifest carries no version. Sync asks the Registry which version a manifest and its payload
are: the approved one with the same input digest when nothing changed, otherwise the next number
after the highest approved one. Patch counts to 5, minor to 3, then major.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.application.registry_versions import ApprovedRegistryVersions
from aart_cli.domain.candidates import CandidateId
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from aart_cli.domain.registry import RegistryArtifactVersion, RegistryContentMode, RegistryLifecycle
from aart_cli.domain.result import Ok
from aart_cli.domain.selection import ArtifactRequest, VersionConstraint
from aart_cli.protocol.registry_versions import FIRST_REGISTRY_VERSION, next_registry_version
from aart_cli.protocol.semver import SemVer, parse_semver

_REGISTRY = SourceAlias("company")
_GITHUB = ArtifactIdentity("mcp", "github")


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _approved(
    version: str,
    input_character: str,
    *,
    identity: ArtifactIdentity = _GITHUB,
    registry: SourceAlias = _REGISTRY,
    lifecycle: RegistryLifecycle = RegistryLifecycle.PUBLISHED,
) -> RegistryArtifactVersion:
    return RegistryArtifactVersion(
        ArtifactCoordinate(registry, identity, version),
        CandidateId("1" * 64),
        _digest(input_character),
        _digest("3"),
        _digest("3"),
        _digest("3"),
        _digest("4"),
        RegistryContentMode.SELF_CONTAINED,
        lifecycle=lifecycle,
        lifecycle_reason=None if lifecycle is RegistryLifecycle.PUBLISHED else "withdrawn",
    )


@dataclass(frozen=True)
class PinnedVersions:
    """Tells a compilation one fixed version, for tests about something other than numbering."""

    pinned: str

    def version(self, identity: ArtifactIdentity, input_digest: ObjectDigest) -> SemVer:
        parsed = parse_semver(self.pinned)
        assert isinstance(parsed, Ok)
        return parsed.value

    def resolve(self, request: ArtifactRequest) -> str | None:
        return None


_CORE = st.tuples(
    st.integers(min_value=0, max_value=40),
    st.integers(min_value=0, max_value=6),
    st.integers(min_value=0, max_value=8),
)


class NextRegistryVersionTest(unittest.TestCase):
    def test_the_owner_s_sequence(self) -> None:
        sequence = [FIRST_REGISTRY_VERSION]
        while len(sequence) < 25:
            sequence.append(next_registry_version(sequence[-1]))

        self.assertEqual(
            [str(item) for item in sequence],
            [
                *(f"1.0.{patch}" for patch in range(6)),
                *(f"1.1.{patch}" for patch in range(6)),
                *(f"1.2.{patch}" for patch in range(6)),
                *(f"1.3.{patch}" for patch in range(6)),
                "2.0.0",
            ],
        )

    def test_the_first_version_is_one_zero_zero(self) -> None:
        self.assertEqual(str(FIRST_REGISTRY_VERSION), "1.0.0")

    @settings(max_examples=200, deadline=None)
    @given(_CORE)
    def test_every_next_version_is_greater_and_stays_inside_the_limits(self, core) -> None:
        current = SemVer(*core)

        following = next_registry_version(current)

        self.assertGreater(following, current)
        self.assertLessEqual(following.patch, 5)
        self.assertLessEqual(following.minor, 3)
        self.assertEqual((following.prerelease, following.build), ((), ()))

    @settings(max_examples=200, deadline=None)
    @given(_CORE)
    def test_nothing_on_the_grid_is_skipped(self, core) -> None:
        major, minor, patch = core
        current = SemVer(major, min(minor, 3), min(patch, 5))

        following = next_registry_version(current)

        # The smallest on-grid version above `current`: no number a count could reach is jumped.
        between = [
            SemVer(major_, minor_, patch_)
            for major_ in (current.major, current.major + 1)
            for minor_ in range(4)
            for patch_ in range(6)
            if current < SemVer(major_, minor_, patch_) < following
        ]
        self.assertEqual(between, [])


class RegistryVersionAssignerTest(unittest.TestCase):
    def test_an_artifact_the_registry_has_never_approved_starts_at_one_zero_zero(self) -> None:
        assign = ApprovedRegistryVersions((), _REGISTRY)

        self.assertEqual(str(assign.version(_GITHUB, _digest("a"))), "1.0.0")

    def test_an_unchanged_manifest_and_payload_keep_the_version_they_have(self) -> None:
        approved = (_approved("1.0.0", "a"), _approved("1.0.1", "b"))
        assign = ApprovedRegistryVersions(approved, _REGISTRY)

        self.assertEqual(str(assign.version(_GITHUB, _digest("a"))), "1.0.0")
        self.assertEqual(str(assign.version(_GITHUB, _digest("b"))), "1.0.1")

    def test_a_change_is_the_next_number_after_the_highest_approved(self) -> None:
        approved = (_approved("1.0.5", "a"), _approved("1.0.2", "b"))
        assign = ApprovedRegistryVersions(approved, _REGISTRY)

        self.assertEqual(str(assign.version(_GITHUB, _digest("c"))), "1.1.0")

    def test_other_artifacts_and_other_registries_do_not_count(self) -> None:
        approved = (
            _approved("1.3.5", "a", identity=ArtifactIdentity("mcp", "jira")),
            _approved("1.2.0", "a", registry=SourceAlias("other")),
            _approved("1.0.3", "b"),
        )
        assign = ApprovedRegistryVersions(approved, _REGISTRY)

        self.assertEqual(str(assign.version(_GITHUB, _digest("a"))), "1.0.4")


def _request(constraint: str, *, source: str | None = None) -> ArtifactRequest:
    return ArtifactRequest(
        _GITHUB, VersionConstraint(constraint), None if source is None else SourceAlias(source)
    )


class DependencyResolutionTest(unittest.TestCase):
    def test_a_dependency_resolves_to_the_highest_published_version_it_allows(self) -> None:
        approved = (
            _approved("1.0.5", "a"),
            _approved("1.3.5", "b"),
            _approved("2.0.0", "c"),
            _approved("1.3.4", "d"),
        )
        versions = ApprovedRegistryVersions(approved, _REGISTRY)

        self.assertEqual(versions.resolve(_request("^1")), "1.3.5")
        self.assertEqual(versions.resolve(_request("^2")), "2.0.0")
        self.assertIsNone(versions.resolve(_request("^3")))

    def test_a_withdrawn_version_and_another_registry_never_resolve(self) -> None:
        approved = (
            _approved("1.0.0", "a"),
            _approved("1.0.1", "b", lifecycle=RegistryLifecycle.REVOKED),
        )
        versions = ApprovedRegistryVersions(approved, _REGISTRY)

        self.assertEqual(versions.resolve(_request("^1")), "1.0.0")
        self.assertEqual(versions.resolve(_request("^1", source="company")), "1.0.0")
        self.assertIsNone(versions.resolve(_request("^1", source="other")))


if __name__ == "__main__":
    unittest.main()
