"""The versions a Registry assigns: a count of approved changes (§173.2, D-423, D-424, D-425).

Source manifests carry no version. Compiling one asks a `RegistryVersions` two things: the exact
approved version each artifact dependency resolves to, and which version a manifest is, given the
digest of its manifest, its selected payload and those resolved dependencies. A Collection is such
an artifact and its members are its dependencies, so a member's new version is a change of the
Collection too, by the same rule and recursively.
"""

from __future__ import annotations

from typing import Protocol

from aart_cli.domain.identifiers import ArtifactIdentity, ObjectDigest
from aart_cli.domain.selection import ArtifactRequest

from .semver import SemVer

#: Patch counts up to this, then the next change raises the minor.
PATCH_LIMIT = 5
#: Minor counts up to this, then the next change raises the major.
MINOR_LIMIT = 3
FIRST_REGISTRY_VERSION = SemVer(1, 0, 0)


class RegistryVersions(Protocol):
    """What a compilation asks the Registry it compiles for."""

    def version(self, identity: ArtifactIdentity, input_digest: ObjectDigest) -> SemVer:
        """The version these exact inputs are: the approved one, or the next number."""
        ...

    def resolve(self, request: ArtifactRequest) -> str | None:
        """The exact approved version `request` resolves to, or None when nothing matches."""
        ...


def next_registry_version(current: SemVer) -> SemVer:
    """The version one approved change after `current`.

    A version off the grid -- one no count reaches, such as a minor above the limit -- is treated
    as the end of its own row, so its successor is back inside the limits.
    """

    if current.minor > MINOR_LIMIT:
        return SemVer(current.major + 1, 0, 0)
    if current.patch < PATCH_LIMIT:
        return SemVer(current.major, current.minor, current.patch + 1)
    if current.minor < MINOR_LIMIT:
        return SemVer(current.major, current.minor + 1, 0)
    return SemVer(current.major + 1, 0, 0)


class _NoRegistry:
    """For compiling with no Registry behind it (`author check`): everything is new, nothing
    resolves."""

    def version(self, identity: ArtifactIdentity, input_digest: ObjectDigest) -> SemVer:
        return FIRST_REGISTRY_VERSION

    def resolve(self, request: ArtifactRequest) -> str | None:
        return None


NO_REGISTRY: RegistryVersions = _NoRegistry()


__all__ = [
    "FIRST_REGISTRY_VERSION",
    "MINOR_LIMIT",
    "NO_REGISTRY",
    "PATCH_LIMIT",
    "RegistryVersions",
    "next_registry_version",
]
