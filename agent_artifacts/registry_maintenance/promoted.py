"""Reading the registry a promotion writes, for the commands that maintain it.

Two registry representations exist during the migration and they are not interchangeable. The older
authoring workspace holds `entries/*.json` plus one unversioned package per artifact, and compiles
into `aart.lock.json` and `aart.index.json`. A promotion writes the approved representation the
Product Specification names: `registry/versions/<kind>/<name>/<version>.json`, its promotion record,
the two derived catalogs, and one package per *version* under `artifacts/<kind>/<name>/<version>/`.

The maintenance commands were written against the first and were handed the second by the first real
promotion, so every one of them refused a healthy registry by naming a file at a path nothing writes
any more (`QA-025`, `QA-032`, `B-057`). This module is the missing half: it reads the approved
representation through the same authority a public consumer validates it with, so the two answers
cannot drift. It adds no third representation and writes nothing.
"""

from __future__ import annotations

from agent_artifacts.application.promotion import load_registry_versions
from agent_artifacts.domain.identifiers import ArtifactIdentity
from agent_artifacts.domain.registry import PromotionMode, RegistryArtifactVersion
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SourceSnapshot,
    compile_native_package,
)
from agent_artifacts.protocol.paths import SafeRelativePath
from agent_artifacts.protocol.registry_index import index_artifact_from_package
from agent_artifacts.protocol.registry_models import IndexArtifact, RegistryManifest

__all__ = [
    "APPROVED_VERSIONS_ROOT",
    "is_promoted_registry",
    "promoted_registry_artifacts",
    "promoted_registry_versions",
]

#: Where the approved representation keeps its version records, and what identifies it as one.
APPROVED_VERSIONS_ROOT = "registry/versions/"


def is_promoted_registry(snapshot: SourceSnapshot) -> bool:
    """Does this workspace hold approved version records rather than authored entries?

    Presence of the records is the test rather than absence of the older files, because a checkout
    that carries both is the migration's real shape and its approvals are the part that decides
    what the registry publishes.
    """

    return any(str(entry.path).startswith(APPROVED_VERSIONS_ROOT) for entry in snapshot.entries)


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
