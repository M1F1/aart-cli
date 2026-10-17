"""A Collection the Registry defines: its next version, members pinned exactly (§173.3, D-430).

A Collection is not authored in a Source. The Registry Maintainer names approved artifacts, and
each Collection version pins the exact approved version of every member. A new version is planned
when the Maintainer changes the Collection, or when a promotion approves a new version of one of
its members (INV-266).
"""

from __future__ import annotations

from dataclasses import dataclass

from .candidates import CandidateId
from .identifiers import ObjectDigest, SourceAlias
from .selection import ArtifactRequest, artifact_request_sort_key


def _safe_line(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n")
    ):
        raise ValueError(f"{label} must be one safe non-empty line")
    return value


@dataclass(frozen=True, slots=True)
class RegistryCollectionChange:
    """One Collection version a Registry transaction publishes.

    `canonical_digest` is the digest of the canonical document the Registry stores, and the
    change's identity is derived from it, so two changes with the same identity publish the same
    bytes.
    """

    target_registry: SourceAlias
    name: str
    summary: str
    version: str
    members: tuple[ArtifactRequest, ...]
    canonical_digest: ObjectDigest

    def __post_init__(self) -> None:
        _safe_line(self.name, "Collection name")
        _safe_line(self.summary, "Collection summary")
        _safe_line(self.version, "Collection version")
        if (
            not isinstance(self.target_registry, SourceAlias)
            or not self.target_registry.value
            or not isinstance(self.canonical_digest, ObjectDigest)
            or not self.members
            or any(
                not isinstance(item, ArtifactRequest)
                or item.source is not None
                or str(item.identity.kind) == "collection"
                for item in self.members
            )
            or len({item.identity for item in self.members}) != len(self.members)
        ):
            raise ValueError("Registry Collection change is invalid")
        object.__setattr__(
            self, "members", tuple(sorted(self.members, key=artifact_request_sort_key))
        )

    @property
    def id(self) -> CandidateId:
        """The change's identity in audit records: its canonical document's digest."""

        return CandidateId(self.canonical_digest.value)

    @property
    def coordinate(self) -> str:
        return f"{self.target_registry}/collection/{self.name}@{self.version}"


__all__ = ["RegistryCollectionChange"]
