"""The `RegistryVersions` a Registry-bound compilation uses, built from approved state (D-424, D-425).

An approved version with the same input digest is that version: nothing changed. Anything else is
the next number after the highest approved version of that artifact in the target Registry, or
`1.0.0` for one it never approved. A dependency resolves to the highest published version its
constraint allows in the same Registry.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from aart_cli.domain.identifiers import ArtifactIdentity, ObjectDigest, SourceAlias
from aart_cli.domain.registry import RegistryArtifactVersion, RegistryLifecycle
from aart_cli.domain.result import Ok
from aart_cli.domain.selection import ArtifactRequest
from aart_cli.protocol.registry_versions import FIRST_REGISTRY_VERSION, next_registry_version
from aart_cli.protocol.semver import SemVer, parse_semver

from .marketplace_resolution import version_constraint_allows


def _parsed(versions: Iterable[str | None]) -> list[SemVer]:
    parsed = (parse_semver(item or "") for item in versions)
    return [item.value for item in parsed if isinstance(item, Ok)]


@dataclass(frozen=True, slots=True)
class ApprovedRegistryVersions:
    approved: tuple[RegistryArtifactVersion, ...]
    target_registry: SourceAlias

    def _of(self, identity: ArtifactIdentity) -> list[RegistryArtifactVersion]:
        return [
            item
            for item in self.approved
            if item.coordinate.source == self.target_registry
            and item.coordinate.artifact == identity
        ]

    def version(self, identity: ArtifactIdentity, input_digest: ObjectDigest) -> SemVer:
        mine = self._of(identity)
        unchanged = _parsed(
            item.coordinate.version for item in mine if item.input_digest == input_digest
        )
        if unchanged:
            return max(unchanged)
        known = _parsed(item.coordinate.version for item in mine)
        return next_registry_version(max(known)) if known else FIRST_REGISTRY_VERSION

    def resolve(self, request: ArtifactRequest) -> str | None:
        if request.source is not None and request.source != self.target_registry:
            return None
        allowed = [
            version
            for version in _parsed(
                item.coordinate.version
                for item in self._of(request.identity)
                if item.lifecycle is RegistryLifecycle.PUBLISHED
            )
            if version_constraint_allows(request.version, version)
        ]
        return str(max(allowed)) if allowed else None


__all__ = ["ApprovedRegistryVersions"]
