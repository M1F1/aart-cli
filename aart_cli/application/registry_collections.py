"""Collections in the Registry: defined, bumped, packaged and read back (§173.3, D-430).

A Collection belongs to the Registry. The Maintainer names approved artifacts; each Collection
version pins the exact approved version of every member. What the Registry stores for a version is
one file, the canonical Collection document, always vendored, because the Registry is its only home.

A Collection changes in two ways, both through one reviewed Registry transaction: the Maintainer
changes its members or summary, or a promotion approves a new version of one of its members, which
publishes the Collection's next version in the same transaction (INV-266).
"""

from __future__ import annotations

from collections.abc import Iterable

from aart_cli.domain.collection_changes import RegistryCollectionChange
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import ArtifactIdentity, ObjectDigest, SourceAlias
from aart_cli.domain.registry import RegistryArtifactVersion, RegistryLifecycle
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.selection import (
    ArtifactRequest,
    Collection,
    CollectionCoordinate,
    CollectionMember,
    VersionConstraint,
    artifact_request_sort_key,
)
from aart_cli.protocol.authoring import collection_document, parse_collection_member
from aart_cli.protocol.hashing import sha256_bytes
from aart_cli.protocol.json import JsonArray, JsonObject, canonical_json_bytes, parse_json
from aart_cli.protocol.native_tree import SnapshotEntry, SnapshotEntryKind, SourceSnapshot
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.protocol.registry_versions import FIRST_REGISTRY_VERSION, next_registry_version
from aart_cli.protocol.semver import SemVer, parse_semver

#: The one file of a published Collection, under `artifacts/collection/<name>/<version>/`.
COLLECTION_PACKAGE_FILE = "collection.json"

REGISTRY_COLLECTION_INVALID = DiagnosticCode("registry-collection-invalid")

_COLLECTION = "collection"


def _error(message: str) -> Err:
    return Err((Diagnostic(REGISTRY_COLLECTION_INVALID, Severity.ERROR, message),))


def collection_package_prefix(name: str, version: str) -> str:
    return f"artifacts/collection/{name}/{version}/"


def _semver(raw: str | None) -> SemVer | None:
    parsed = parse_semver(raw or "")
    return parsed.value if isinstance(parsed, Ok) else None


def _highest(
    versions: Iterable[RegistryArtifactVersion],
    target_registry: SourceAlias,
    identity: ArtifactIdentity,
    *,
    published_only: bool,
) -> RegistryArtifactVersion | None:
    ranked = [
        (parsed, item)
        for item in versions
        if item.coordinate.source == target_registry
        and item.coordinate.artifact == identity
        and (not published_only or item.lifecycle is RegistryLifecycle.PUBLISHED)
        and (parsed := _semver(item.coordinate.version)) is not None
    ]
    return max(ranked, key=lambda pair: pair[0])[1] if ranked else None


def _canonical_digest(
    name: str, summary: str, version: str, members: tuple[ArtifactRequest, ...]
) -> ObjectDigest:
    return sha256_bytes(canonical_json_bytes(collection_document(name, summary, version, members)))


def _pinned(item: RegistryArtifactVersion) -> ArtifactRequest:
    assert item.coordinate.version is not None
    return ArtifactRequest(item.coordinate.artifact, VersionConstraint(item.coordinate.version))


def current_collection(
    approved: tuple[RegistryArtifactVersion, ...],
    snapshot: SourceSnapshot,
    target_registry: SourceAlias,
    name: str,
) -> Result[tuple[RegistryArtifactVersion, Collection] | None]:
    """The Collection's highest approved version and its document, or None for a new one."""

    try:
        identity = ArtifactIdentity("collection", name)
    except ValueError as error:
        return _error(f"Collection name {name!r} is invalid: {error}")
    record = _highest(approved, target_registry, identity, published_only=False)
    if record is None:
        return Ok(None)
    read = read_registry_collection(snapshot, record)
    if isinstance(read, Err):
        return read
    return Ok((record, read.value))


def _change(
    target_registry: SourceAlias,
    name: str,
    summary: str,
    current: RegistryArtifactVersion | None,
    members: tuple[ArtifactRequest, ...],
) -> RegistryCollectionChange:
    previous = None if current is None else _semver(current.coordinate.version)
    version = str(FIRST_REGISTRY_VERSION if previous is None else next_registry_version(previous))
    return RegistryCollectionChange(
        target_registry,
        name,
        summary,
        version,
        members,
        _canonical_digest(name, summary, version, members),
    )


def plan_collection_definition(
    approved: tuple[RegistryArtifactVersion, ...],
    snapshot: SourceSnapshot,
    *,
    target_registry: SourceAlias,
    name: str,
    summary: str | None,
    members: tuple[ArtifactIdentity, ...],
) -> Result[RegistryCollectionChange | None]:
    """The Collection's next version with these members, or None when nothing would change.

    Each member is pinned to its highest published version in the target Registry; a member the
    Registry has not approved is refused by name. `summary` None keeps the current one.
    """

    current = current_collection(approved, snapshot, target_registry, name)
    if isinstance(current, Err):
        return current
    record, collection = (None, None) if current.value is None else current.value
    if summary is None:
        if collection is None:
            return _error(f"a new Collection {name} needs a summary")
        summary = collection.summary
    if not members:
        return _error(f"Collection {name} needs at least one member")
    if len(set(members)) != len(members):
        return _error(f"Collection {name} names a member more than once")
    pinned: list[ArtifactRequest] = []
    for identity in members:
        if str(identity.kind) == _COLLECTION:
            return _error(f"a Collection cannot be a member of Collection {name}: {identity}")
        found = _highest(approved, target_registry, identity, published_only=True)
        if found is None:
            return _error(f"{identity} has no approved version in {target_registry}")
        pinned.append(_pinned(found))
    ordered = tuple(sorted(pinned, key=artifact_request_sort_key))
    if collection is not None and (
        collection.summary == summary
        and tuple(str(item.request) for item in collection.members)
        == tuple(str(item) for item in ordered)
    ):
        return Ok(None)
    try:
        return Ok(_change(target_registry, name, summary, record, ordered))
    except ValueError as error:
        return _error(f"Collection {name} is invalid: {error}")


def collection_bumps(
    approved: tuple[RegistryArtifactVersion, ...],
    snapshot: SourceSnapshot,
    promoted: tuple[RegistryArtifactVersion, ...],
    *,
    defined: frozenset[str] = frozenset(),
) -> Result[tuple[RegistryCollectionChange, ...]]:
    """The next version of every Collection a promotion approves a newer member version for.

    Only a Collection's highest version is followed, and a member moves only to a version higher
    than the one it pins. Collections in `defined` are already changed by the same transaction.
    """

    bumps: list[RegistryCollectionChange] = []
    names = sorted(
        {
            (item.coordinate.source.value, item.coordinate.artifact.name)
            for item in approved
            if str(item.coordinate.artifact.kind) == _COLLECTION
        }
    )
    for registry, name in names:
        if name in defined:
            continue
        target = SourceAlias(registry)
        current = current_collection(approved, snapshot, target, name)
        if isinstance(current, Err):
            return current
        assert current.value is not None
        record, collection = current.value
        moved = False
        members: list[ArtifactRequest] = []
        for member in collection.members:
            pinned = _semver(str(member.request.version))
            newer = _highest(promoted, target, member.request.identity, published_only=True)
            newer_version = None if newer is None else _semver(newer.coordinate.version)
            if (
                newer is not None
                and newer_version is not None
                and (pinned is None or newer_version > pinned)
            ):
                members.append(_pinned(newer))
                moved = True
            else:
                members.append(member.request)
        if moved:
            bumps.append(
                _change(
                    target,
                    name,
                    collection.summary,
                    record,
                    tuple(sorted(members, key=artifact_request_sort_key)),
                )
            )
    return Ok(tuple(bumps))


def collection_validation_digest(change: RegistryCollectionChange) -> ObjectDigest:
    """What approval checked: the Collection's identity and each exact member it pins."""

    return sha256_bytes(
        canonical_json_bytes(
            JsonObject(
                (
                    ("collection", change.coordinate),
                    ("members", JsonArray(tuple(str(item) for item in change.members))),
                    ("schema", "aart-cli.dev/collection-validation/v2"),
                )
            )
        )
    )


def collection_package_entries(
    change: RegistryCollectionChange,
) -> Result[tuple[SnapshotEntry, ...]]:
    """The Collection's package: its canonical document, which must be what was reviewed."""

    content = canonical_json_bytes(
        collection_document(change.name, change.summary, change.version, change.members)
    )
    if sha256_bytes(content) != change.canonical_digest:
        return _error(f"Collection {change.name} does not match its reviewed canonical digest")
    path = parse_relative_path(COLLECTION_PACKAGE_FILE)
    assert isinstance(path, Ok)
    return Ok((SnapshotEntry(path.value, SnapshotEntryKind.FILE, content),))


def read_registry_collection(
    snapshot: SourceSnapshot, version: RegistryArtifactVersion
) -> Result[Collection]:
    """Read one approved Collection version back, refusing content its record does not name."""

    identity = version.coordinate.artifact
    if identity.kind != "collection" or version.coordinate.version is None:
        return _error(f"{version.coordinate} is not a Collection version")
    raw_path = collection_package_prefix(identity.name, version.coordinate.version)
    raw_path += COLLECTION_PACKAGE_FILE
    entry = next((item for item in snapshot.entries if str(item.path) == raw_path), None)
    if entry is None or entry.kind is not SnapshotEntryKind.FILE or entry.content is None:
        return _error(f"published Collection package is missing: {version.coordinate}")
    if sha256_bytes(entry.content) != version.canonical_digest:
        return _error(f"published Collection package digest is invalid: {version.coordinate}")
    parsed = parse_json(entry.content)
    if isinstance(parsed, Err) or not isinstance(parsed.value, JsonObject):
        return _error(f"published Collection package is not a JSON object: {version.coordinate}")
    document = parsed.value
    name, summary, raw_members = (
        document.get("name"),
        document.get("summary"),
        document.get("artifacts"),
    )
    if (
        name != identity.name
        or document.get("version") != version.coordinate.version
        or not isinstance(summary, str)
        or not isinstance(raw_members, JsonArray)
    ):
        return _error(f"published Collection package does not match its record: {raw_path}")
    members: list[CollectionMember] = []
    for raw in raw_members.items:
        if not isinstance(raw, str):
            return _error(f"published Collection member is not a request: {raw_path}")
        request = parse_collection_member(raw, path=raw_path)
        if isinstance(request, Err):
            return request
        members.append(CollectionMember(request.value))
    try:
        return Ok(
            Collection(
                CollectionCoordinate(
                    version.coordinate.source, identity.name, version.coordinate.version
                ),
                summary,
                tuple(sorted(members, key=lambda item: artifact_request_sort_key(item.request))),
                version.registry_snapshot,
            )
        )
    except ValueError as error:
        return _error(f"published Collection is invalid at {raw_path}: {error}")


__all__ = [
    "COLLECTION_PACKAGE_FILE",
    "collection_bumps",
    "collection_package_entries",
    "collection_package_prefix",
    "collection_validation_digest",
    "current_collection",
    "plan_collection_definition",
    "read_registry_collection",
]
