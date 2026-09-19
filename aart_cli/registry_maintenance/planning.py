"""Pure registry entry, native promotion, and exact native-reference refresh planning."""

from __future__ import annotations

import re

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import ObjectDigest
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.capabilities import Capability, negotiate_capabilities
from aart_cli.protocol.hashing import sha256_bytes
from aart_cli.protocol.native_models import CollectionManifest, SourceManifest
from aart_cli.protocol.native_schema import (
    parse_collection_manifest,
    parse_source_manifest,
)
from aart_cli.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SourceSnapshot,
)
from aart_cli.protocol.paths import SafeRelativePath, parse_relative_path
from aart_cli.protocol.registry_index import validate_registry_graph
from aart_cli.protocol.registry_models import (
    IndexArtifact,
    RegistryManifest,
)
from aart_cli.protocol.registry_schema import (
    parse_registry_manifest,
)
from aart_cli.protocol.semver import SemVer
from aart_cli.sources.model import source_snapshot_digest

from .model import (
    RegistryChangeKind,
    RegistryFileChange,
    RegistryMutationPlan,
    registry_mutation_review_digest,
)
from .promoted import (
    is_promoted_registry,
    legacy_registry_paths,
    promoted_registry_artifacts,
    promoted_registry_versions,
)

REGISTRY_MAINTENANCE_INVALID = DiagnosticCode("registry-maintenance-invalid")
REGISTRY_MAINTENANCE_STALE = DiagnosticCode("registry-maintenance-stale")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _error(message: str, *, stale: bool = False) -> Err:
    return Err(
        (
            Diagnostic(
                REGISTRY_MAINTENANCE_STALE if stale else REGISTRY_MAINTENANCE_INVALID,
                Severity.ERROR,
                message,
            ),
        )
    )


def _snapshot_files(snapshot: SourceSnapshot) -> Result[dict[str, SnapshotEntry]]:
    digest = source_snapshot_digest(snapshot)
    if isinstance(digest, Err):
        return _error("registry workspace must be one inert canonical snapshot")
    return Ok({str(entry.path): entry for entry in snapshot.entries})


def _required_file(files: dict[str, SnapshotEntry], path: str) -> Result[SnapshotEntry]:
    entry = files.get(path)
    if entry is None or entry.kind is not SnapshotEntryKind.FILE:
        return _error(f"registry workspace requires {path}")
    return Ok(entry)


def _registry_manifest(files: dict[str, SnapshotEntry]) -> Result[RegistryManifest]:
    marker = _required_file(files, "aart-registry.json")
    if isinstance(marker, Err):
        return marker
    return parse_registry_manifest(marker.value.content)


def _registry_source_manifest(
    files: dict[str, SnapshotEntry],
    registry: RegistryManifest,
) -> Result[SourceManifest]:
    marker = _required_file(files, "aart-source.json")
    if isinstance(marker, Err):
        return marker
    source = parse_source_manifest(marker.value.content)
    if isinstance(source, Err):
        return source
    if source.value.source_id != registry.registry_id:
        return _error("registry and native source identities must match")
    return source


def _file_change(path: str, before: SnapshotEntry | None, content: bytes) -> RegistryFileChange:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    after_digest = sha256_bytes(content)
    before_digest = None if before is None else sha256_bytes(before.content)
    if before is None:
        kind = RegistryChangeKind.ADDED
    elif before.content == content and before.kind is SnapshotEntryKind.FILE:
        kind = RegistryChangeKind.UNCHANGED
    else:
        kind = RegistryChangeKind.CHANGED
    return RegistryFileChange(parsed.value, kind, content, before_digest, after_digest)


def _project_changes(
    snapshot: SourceSnapshot,
    changes: tuple[RegistryFileChange, ...],
) -> Result[SourceSnapshot]:
    files = _snapshot_files(snapshot)
    if isinstance(files, Err):
        return files
    output = dict(files.value)
    for change in changes:
        raw = str(change.path)
        before = output.get(raw)
        actual_digest = None
        if before is not None:
            if before.kind is not SnapshotEntryKind.FILE:
                return _error(f"registry mutation target is not a file: {raw}")
            actual_digest = sha256_bytes(before.content)
        if actual_digest != change.before_digest:
            return _error(f"registry mutation precondition changed: {raw}", stale=True)
        output[raw] = SnapshotEntry(
            change.path,
            SnapshotEntryKind.FILE,
            change.content,
        )
        for length in range(1, len(change.path.parts)):
            parent = SafeRelativePath(change.path.parts[:length])
            prior = output.get(str(parent))
            if prior is not None and prior.kind is not SnapshotEntryKind.DIRECTORY:
                return _error(f"registry mutation parent is not a directory: {parent}")
            output.setdefault(
                str(parent),
                SnapshotEntry(parent, SnapshotEntryKind.DIRECTORY),
            )
    return Ok(SourceSnapshot(snapshot.origin, tuple(output.values())))


def _workspace_digest(snapshot: SourceSnapshot) -> Result[ObjectDigest]:
    """Bind a reviewed mutation to the whole checkout it was reviewed against.

    The retired `registry_inputs_digest` hashed a declared subset -- the two markers plus
    `entries/`, `artifacts/` and `collections/` -- and excluded the files the authoring workspace
    generated so that rebuilding them would not invalidate a pending review. The approved
    representation generates nothing and keeps its approvals under `registry/`, which that subset
    never covered, so the same guard would have let a version record change between review and
    apply. Hashing the snapshot is what "the workspace did not move" actually means (CP-26.5).
    """

    digest = source_snapshot_digest(snapshot)
    if isinstance(digest, Err):
        return _error("registry workspace snapshot cannot be hashed")
    return digest


def _mutation_plan(
    snapshot: SourceSnapshot,
    desired_files: tuple[tuple[str, bytes], ...],
) -> Result[RegistryMutationPlan]:
    files = _snapshot_files(snapshot)
    if isinstance(files, Err):
        return files
    current_digest = _workspace_digest(snapshot)
    if isinstance(current_digest, Err):
        return current_digest
    changes = tuple(
        _file_change(path, files.value.get(path), content)
        for path, content in sorted(desired_files)
    )
    projected = _project_changes(snapshot, changes)
    if isinstance(projected, Err):
        return projected
    next_digest = _workspace_digest(projected.value)
    if isinstance(next_digest, Err):
        return next_digest
    return Ok(
        RegistryMutationPlan(
            current_digest.value,
            next_digest.value,
            changes,
            registry_mutation_review_digest(
                current_digest.value,
                next_digest.value,
                changes,
            ),
        )
    )


def project_registry_mutation(
    snapshot: SourceSnapshot,
    plan: RegistryMutationPlan,
) -> Result[SourceSnapshot]:
    current = _workspace_digest(snapshot)
    if isinstance(current, Err):
        return current
    if current.value != plan.expected_inputs_digest:
        return _error("registry inputs changed after review", stale=True)
    projected = _project_changes(snapshot, plan.changes)
    if isinstance(projected, Err):
        return projected
    next_digest = _workspace_digest(projected.value)
    if isinstance(next_digest, Err) or next_digest.value != plan.next_inputs_digest:
        return _error("registry mutation no longer produces the reviewed input digest", stale=True)
    return projected


def _collections_without_index(
    files: dict[str, SnapshotEntry],
) -> Result[tuple[CollectionManifest, ...]]:
    marker = _required_file(files, "aart-source.json")
    if isinstance(marker, Err):
        return marker
    source = parse_source_manifest(marker.value.content)
    if isinstance(source, Err):
        return source
    collections: list[CollectionManifest] = []
    for root in source.value.collection_roots:
        prefix = f"{root}/"
        for path, item in sorted(files.items()):
            if not path.startswith(prefix) or item.kind is not SnapshotEntryKind.FILE:
                continue
            relative = path.removeprefix(prefix)
            if "/" in relative or not relative.endswith(".json"):
                return _error(f"collection files must be direct JSON children of {root}: {path}")
            parsed = parse_collection_manifest(item.content, path=path)
            if isinstance(parsed, Err):
                return parsed
            if parsed.value.name != relative.removesuffix(".json"):
                return _error(f"collection identity does not match its path: {path}")
            collections.append(parsed.value)
    identities = tuple(item.name for item in collections)
    if len(set(identities)) != len(identities):
        return _error("registry workspace contains duplicate collection identities")
    return Ok(tuple(sorted(collections, key=lambda item: item.name)))


def _native_registry_content(
    snapshot: SourceSnapshot,
    files: dict[str, SnapshotEntry],
    manifest: RegistryManifest,
    *,
    executable_version: SemVer,
    available_capabilities: tuple[Capability, ...],
) -> Result[tuple[tuple[IndexArtifact, ...], tuple[CollectionManifest, ...]]]:
    source = _registry_source_manifest(files, manifest)
    if isinstance(source, Err):
        return source
    if not manifest.requires_aart.allows(
        executable_version
    ) or not source.value.requires_aart.allows(executable_version):
        return _error("registry workspace is incompatible with this AART version")
    decision = negotiate_capabilities(
        tuple(
            sorted(set(manifest.required_capabilities) | set(source.value.required_capabilities))
        ),
        (),
        available_capabilities,
    )
    if decision.missing_required:
        missing = ", ".join(str(item) for item in decision.missing_required)
        return _error(f"registry workspace requires unavailable capabilities: {missing}")
    if is_promoted_registry(snapshot):
        # The approved representation keeps one package per *version*, so the native-source loader
        # -- which was the authoring workspace's reader -- would refuse it by naming a path nothing
        # writes.  Its approvals are read by the authority a public consumer uses.
        collections = _collections_without_index(files)
        if isinstance(collections, Err):
            return collections
        versions = promoted_registry_versions(snapshot)
        if isinstance(versions, Err):
            return versions
        owned = promoted_registry_artifacts(snapshot, manifest, versions.value)
        if isinstance(owned, Err):
            return owned
        # `requires` resolves inside one registry, and collection membership is derived rather than
        # declared.  Both rules lived in `build_registry_index`, which compiled the retired
        # workspace's catalog; deleting it took the approved representation's only check of them
        # with it.  The graph validator is representation-independent -- it reads `IndexArtifact`
        # values -- so it is bound here instead, which is where every maintainer command already
        # arrives (D-325, CP-26.5).
        graph = validate_registry_graph(owned.value, collections.value)
        if isinstance(graph, Err):
            return graph
        return Ok((graph.value, collections.value))
    # Not promoted, so either this Registry holds nothing yet or it is carrying the retired
    # authoring workspace.  The second case used to be compiled here by `load_native_source` over
    # unversioned `artifacts/<kind>/<name>/` packages and `entries/` reference records; no consumer
    # will install what that produced, so it is named rather than compiled (D-318, CP-26.5).
    retired = legacy_registry_paths(snapshot)
    if retired:
        return _error(
            "registry workspace carries the retired authoring-workspace representation: "
            + ", ".join(retired)
        )
    collections = _collections_without_index(files)
    if isinstance(collections, Err):
        return collections
    return Ok(((), collections.value))


def registry_native_content(
    snapshot: SourceSnapshot,
    files: dict[str, SnapshotEntry],
    manifest: RegistryManifest,
    *,
    executable_version: SemVer,
    available_capabilities: tuple[Capability, ...],
) -> Result[tuple[tuple[IndexArtifact, ...], tuple[CollectionManifest, ...]]]:
    """Compile registry-owned native packages and collections for maintainer commands."""

    return _native_registry_content(
        snapshot,
        files,
        manifest,
        executable_version=executable_version,
        available_capabilities=available_capabilities,
    )
