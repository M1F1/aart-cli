"""Collections in the Registry: assessed, packaged and read back (§173.3, B-067 layers 1–2, D-427).

A Collection is approved the way an artifact is -- a Candidate, a version record, an audit record --
and what the Registry stores for it is one file: the canonical Collection document whose digest is
the Candidate's `canonical_digest`. It is always vendored, because there is no payload to refer to
elsewhere; the document is all of it.

Its members are its dependencies (D-425), so approval resolves each one against the target
Registry with the same `RegistryVersions` the version number came from. A member that resolves to
nothing blocks approval, and the finding names it.
"""

from __future__ import annotations

from dataclasses import replace

from aart_cli.domain.candidates import CandidateFinding, CandidateState, FindingSeverity
from aart_cli.domain.collection_candidates import CollectionCandidate
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import ObjectDigest
from aart_cli.domain.registry import RegistryArtifactVersion
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.selection import (
    Collection,
    CollectionCoordinate,
    CollectionMember,
    artifact_request_sort_key,
)
from aart_cli.protocol.authoring import collection_document, parse_collection_member
from aart_cli.protocol.hashing import sha256_bytes
from aart_cli.protocol.json import JsonArray, JsonObject, canonical_json_bytes, parse_json
from aart_cli.protocol.native_tree import SnapshotEntry, SnapshotEntryKind, SourceSnapshot
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.protocol.registry_versions import RegistryVersions

#: The one file of a published Collection, under `artifacts/collection/<name>/<version>/`.
COLLECTION_PACKAGE_FILE = "collection.json"

REGISTRY_COLLECTION_INVALID = DiagnosticCode("registry-collection-invalid")

#: A member the target Registry has no approved version for. Blocks approval (§173.3).
COLLECTION_MEMBER_UNRESOLVED = "collection-member-unresolved"

_TERMINAL = frozenset(
    {CandidateState.PROMOTED, CandidateState.SUPERSEDED, CandidateState.SOURCE_REMOVED}
)


def _error(message: str) -> Err:
    return Err((Diagnostic(REGISTRY_COLLECTION_INVALID, Severity.ERROR, message),))


def collection_package_prefix(name: str, version: str) -> str:
    return f"artifacts/collection/{name}/{version}/"


def assess_collection_candidate(
    candidate: CollectionCandidate, versions: RegistryVersions
) -> CollectionCandidate:
    """Ready when every member resolves in the target Registry; invalid, naming each, otherwise."""

    if candidate.state in _TERMINAL:
        raise ValueError("terminal Collection Candidate state cannot be reassessed")
    findings = tuple(
        CandidateFinding(
            COLLECTION_MEMBER_UNRESOLVED,
            FindingSeverity.ERROR,
            f"member {request} matches no approved version in {candidate.target_registry}",
        )
        for request in candidate.members
        if versions.resolve(request) is None
    )
    return replace(
        candidate,
        state=CandidateState.INVALID if findings else CandidateState.READY,
        findings=findings,
        successor=None,
    )


def collection_validation_digest(
    candidate: CollectionCandidate, versions: RegistryVersions
) -> ObjectDigest:
    """What approval checked: each member and the exact version it resolved to."""

    return sha256_bytes(
        canonical_json_bytes(
            JsonObject(
                (
                    ("candidate_id", candidate.id.value),
                    (
                        "members",
                        JsonArray(
                            tuple(
                                JsonArray((str(request), versions.resolve(request)))
                                for request in candidate.members
                            )
                        ),
                    ),
                    ("schema", "aart-cli.dev/collection-validation/v1"),
                )
            )
        )
    )


def collection_package_entries(
    candidate: CollectionCandidate,
) -> Result[tuple[SnapshotEntry, ...]]:
    """The Collection's package: its canonical document, which must be what was reviewed."""

    content = canonical_json_bytes(
        collection_document(candidate.name, candidate.summary, candidate.version, candidate.members)
    )
    if sha256_bytes(content) != candidate.canonical_digest:
        return _error(f"Collection {candidate.name} does not match its reviewed canonical digest")
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
    "COLLECTION_MEMBER_UNRESOLVED",
    "COLLECTION_PACKAGE_FILE",
    "assess_collection_candidate",
    "collection_package_entries",
    "collection_package_prefix",
    "collection_validation_digest",
    "read_registry_collection",
]
