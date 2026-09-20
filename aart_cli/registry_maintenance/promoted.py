"""Reading the canonical Registry, for the commands that maintain it.

An initialized Registry has already chosen the canonical representation, even before its first
promotion. Approved versions add `registry/versions/<kind>/<name>/<version>.json`, a promotion
record, the two derived catalogs, and one package per *version* under
`artifacts/<kind>/<name>/<version>/`.

Maintenance commands that read only the first would refuse a healthy promoted registry by naming a
file at a path nothing writes (`QA-025`, `QA-032`, `B-057`). This module is the other half: it reads the approved
representation through the same authority a public consumer validates it with, so the two answers
cannot drift. It adds no third representation and writes nothing.
"""

from __future__ import annotations

from aart_cli.application.promotion import load_registry_versions
from aart_cli.domain.identifiers import ArtifactIdentity
from aart_cli.domain.registry import PromotionMode, RegistryArtifactVersion
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SourceSnapshot,
    compile_native_package,
)
from aart_cli.protocol.paths import SafeRelativePath
from aart_cli.protocol.registry_index import index_artifact_from_package
from aart_cli.protocol.registry_models import IndexArtifact, RegistryManifest

__all__ = [
    "APPROVED_VERSIONS_ROOT",
    "is_promoted_registry",
    "legacy_registry_paths",
    "promoted_registry_artifacts",
    "promoted_registry_versions",
]

#: Where the approved representation keeps its version records.
APPROVED_VERSIONS_ROOT = "registry/versions/"


def legacy_registry_paths(snapshot: SourceSnapshot) -> tuple[str, ...]:
    """Return paths that can only belong to the retired authoring-workspace representation."""

    retired: list[str] = []
    for entry in snapshot.entries:
        path = str(entry.path)
        parts = entry.path.parts
        if path in {"aart.lock.json", "aart.index.json"} or path.startswith("entries/"):
            retired.append(path)
        elif (
            len(parts) == 4
            and parts[0] == "artifacts"
            and parts[-1] in {"artifact.json", "provenance.json"}
        ):
            retired.append(path)
    return tuple(sorted(set(retired)))


def is_promoted_registry(snapshot: SourceSnapshot) -> bool:
    """Has this workspace chosen the canonical approved-Registry representation?

    A freshly initialized Registry has no version records yet, so the two root manifests identify
    that empty canonical state. Once a version record exists it remains decisive even if obsolete
    lock/index files also survive; that mixed checkout must be refused rather than mistaken for an
    old workspace and rebuilt through the retired branch.
    """

    paths = {str(entry.path) for entry in snapshot.entries}
    if any(path.startswith(APPROVED_VERSIONS_ROOT) for path in paths):
        return True
    if legacy_registry_paths(snapshot):
        return False
    return {"aart-cli-registry.json", "aart-cli-source.json"}.issubset(paths)


def promoted_registry_versions(
    snapshot: SourceSnapshot,
) -> Result[tuple[RegistryArtifactVersion, ...]]:
    """Every approved version, validated exactly as a public consumer validates it.

    `load_registry_versions` runs `validate_promoted_registry`, so this is not a parse: the records
    have to be canonical, the catalogs exactly derived, and each vendored package's canonical and
    object digests the ones its approval names.
    """

    return load_registry_versions(snapshot)


def _package_entries(
    snapshot: SourceSnapshot,
    prefix: tuple[str, ...],
) -> tuple[SnapshotEntry, ...]:
    """One published package, re-rooted at its own manifest so it compiles as what it is."""

    return tuple(
        SnapshotEntry(
            SafeRelativePath(entry.path.parts[len(prefix) :]),
            entry.kind,
            entry.content,
            entry.executable,
        )
        for entry in snapshot.entries
        if entry.path.parts[: len(prefix)] == prefix
        and len(entry.path.parts) > len(prefix)
        and entry.kind is SnapshotEntryKind.FILE
    )


def _version_prefix(version: RegistryArtifactVersion) -> tuple[str, ...]:
    identity: ArtifactIdentity = version.coordinate.artifact
    assert version.coordinate.version is not None
    return ("artifacts", identity.kind, identity.name, version.coordinate.version)


def promoted_registry_artifacts(
    snapshot: SourceSnapshot,
    manifest: RegistryManifest,
    versions: tuple[RegistryArtifactVersion, ...],
) -> Result[tuple[IndexArtifact, ...]]:
    """The registry's own content, compiled from the packages its approvals point at.

    Only vendored versions carry content here: a referenced approval deliberately leaves the bytes
    upstream, so this snapshot has no package to compile and the maintenance commands have nothing
    of the registry's own to check.  The object digest is the approval's, not a recomputation --
    `validate_promoted_registry` has already held the package to it.
    """

    artifacts: list[IndexArtifact] = []
    for version in versions:
        if version.mode is not PromotionMode.VENDORED:
            continue
        identity = version.coordinate.artifact
        entries = _package_entries(snapshot, _version_prefix(version))
        package = compile_native_package(entries, expected_identity=identity)
        if isinstance(package, Err):
            return package
        artifacts.append(
            index_artifact_from_package(
                package.value,
                source_id=manifest.registry_id,
                object_digest=version.object_digest,
            )
        )
    return Ok(tuple(artifacts))
