"""Strict canonical serialization for durable Source Scan and Candidate history.

Candidate lifecycle metadata is small, while each compiled artifact is already a canonical object
tree.  The index therefore references content-addressed ``ObjectCandidate`` envelopes instead of
embedding payload bytes.  Filesystem adapters decide where those two values live; this module only
round-trips typed application state and refuses any mismatch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from agent_artifacts.application.maintainer import CandidateBundle, SourceScan
from agent_artifacts.domain.artifacts import (
    ArtifactFormat,
    ArtifactKind,
    ArtifactPackage,
    Capability,
    Compatibility,
    Provenance,
    artifact_to_data,
)
from agent_artifacts.domain.candidates import (
    Candidate,
    CandidateFinding,
    CandidateId,
    CandidateState,
    FindingSeverity,
)
from agent_artifacts.domain.collection_candidates import (
    CollectionCandidate,
    collection_candidate_id_for,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.identifiers import ArtifactKind as IdentityKind
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ArtifactRequest, VersionConstraint
from agent_artifacts.domain.serialization import CanonicalValue, canonical_json_bytes
from agent_artifacts.protocol.authoring import CompiledAuthorArtifact, ComplianceLevel
from agent_artifacts.protocol.hashing import file_entry, tree_digest
from agent_artifacts.protocol.native_tree import SnapshotEntryKind, compile_native_package
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.store.model import ObjectCandidate, make_object_candidate

__all__ = [
    "CANDIDATE_HISTORY_INVALID",
    "SerializedSourceScan",
    "parse_source_scan",
    "source_scan_object_digests",
    "serialize_source_scan",
]

CANDIDATE_HISTORY_INVALID = DiagnosticCode("candidate-history-invalid")
_MAX_INDEX_BYTES = 16 * 1024 * 1024


def _error(message: str) -> Err:
    return Err((Diagnostic(CANDIDATE_HISTORY_INVALID, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class SerializedSourceScan:
    index: bytes
    objects: tuple[ObjectCandidate, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.index, bytes)
            or not self.index
            or len(self.index) > _MAX_INDEX_BYTES
            or any(not isinstance(item, ObjectCandidate) for item in self.objects)
            or len({item.digest for item in self.objects}) != len(self.objects)
        ):
            raise ValueError("serialized Candidate history is invalid")


def _digest(value: object, label: str) -> ObjectDigest:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a canonical SHA-256")
    algorithm, separator, digest = value.partition(":")
    parsed = ObjectDigest(algorithm, digest)
    if (
        separator != ":"
        or algorithm != "sha256"
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{label} must be a canonical SHA-256")
    return parsed


def _mapping(value: object, fields: frozenset[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields are invalid")
    return cast("dict[str, object]", value)


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character in value for character in "\r\n")
    ):
        raise ValueError(f"{label} must be one non-empty line")
    return value


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    result = tuple(_text(item, label) for item in value)
    if tuple(sorted(set(result))) != result:
        raise ValueError(f"{label} must be unique and sorted")
    return result


def _coordinate(value: object) -> ArtifactCoordinate:
    raw = _text(value, "artifact coordinate")
    parts = raw.split("/", 2)
    if len(parts) != 3 or "@" not in parts[2]:
        raise ValueError("artifact coordinate is invalid")
    name, version = parts[2].rsplit("@", 1)
    kind = parts[1]
    if kind not in {item.value for item in ArtifactKind}:
        raise ValueError("artifact coordinate kind is invalid")
    coordinate = ArtifactCoordinate(
        SourceAlias(_text(parts[0], "artifact source")),
        ArtifactIdentity(cast(IdentityKind, kind), _text(name, "artifact name")),
        _text(version, "artifact version"),
    )
    if str(coordinate) != raw:
        raise ValueError("artifact coordinate is not canonical")
    return coordinate


def _artifact(value: object) -> ArtifactPackage:
    data = _mapping(
        value,
        frozenset(
            {
                "capabilities",
                "compatibility",
                "coordinate",
                "format",
                "kind",
                "payload_digest",
                "protocol",
                "provenance",
            }
        ),
        "artifact",
    )
    compatibility = _mapping(
        data["compatibility"],
        frozenset({"harnesses", "platforms", "python"}),
        "artifact compatibility",
    )
    provenance = _mapping(
        data["provenance"],
        frozenset({"compiler", "input_digest", "manifest_path", "revision", "source"}),
        "artifact provenance",
    )
    python_value = compatibility["python"]
    if python_value is not None and not isinstance(python_value, str):
        raise ValueError("artifact Python compatibility must be text or null")
    protocol = data["protocol"]
    if protocol is not None and not isinstance(protocol, str):
        raise ValueError("artifact protocol must be text or null")
    package = ArtifactPackage(
        _coordinate(data["coordinate"]),
        ArtifactKind(_text(data["kind"], "artifact kind")),
        ArtifactFormat(_text(data["format"], "artifact format")),
        _digest(data["payload_digest"], "artifact payload digest"),
        Provenance(
            _text(provenance["source"], "artifact provenance source"),
            _text(provenance["revision"], "artifact provenance revision"),
            _text(provenance["manifest_path"], "artifact manifest path"),
            _digest(provenance["input_digest"], "artifact input digest"),
            _text(provenance["compiler"], "artifact compiler"),
        ),
        Compatibility(
            _strings(compatibility["platforms"], "artifact platforms"),
            _strings(compatibility["harnesses"], "artifact harnesses"),
            python_value,
        ),
        tuple(Capability(item) for item in _strings(data["capabilities"], "capabilities")),
        protocol,
    )
    if artifact_to_data(package) != data:
        raise ValueError("artifact metadata is not canonical")
    return package


def _finding_to_data(finding: CandidateFinding) -> dict[str, object]:
    return {
        "code": finding.code,
        "message": finding.message,
        "severity": finding.severity.value,
    }


def _bundle_to_data(bundle: CandidateBundle, object_digest: ObjectDigest) -> dict[str, object]:
    candidate = bundle.candidate
    return {
        "artifact": artifact_to_data(candidate.artifact),
        "candidate_id": candidate.id.value,
        "canonical_digest": str(candidate.canonical_digest),
        "compliance": bundle.artifact.compliance.value,
        "findings": [_finding_to_data(item) for item in candidate.findings],
        "input_digest": str(bundle.artifact.input_digest),
        "manifest_path": str(bundle.artifact.manifest_path),
        "object_digest": str(object_digest),
        "previous": None if candidate.previous is None else candidate.previous.value,
        "registry_snapshot": (
            None if candidate.registry_snapshot is None else str(candidate.registry_snapshot)
        ),
        "rejection_reason": candidate.rejection_reason,
        "state": candidate.state.value,
        "successor": None if candidate.successor is None else candidate.successor.value,
        "target_registry": candidate.target_registry.value,
    }


def _collection_to_data(candidate: CollectionCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.id.value,
        "canonical_digest": str(candidate.canonical_digest),
        "findings": [_finding_to_data(item) for item in candidate.findings],
        "input_digest": str(candidate.input_digest),
        "manifest_path": candidate.manifest_path,
        "members": [str(item) for item in candidate.members],
        "name": candidate.name,
        "previous": None if candidate.previous is None else candidate.previous.value,
        "source_alias": candidate.source_alias.value,
        "source_location": candidate.source_location,
        "source_revision": candidate.source_revision,
        "state": candidate.state.value,
        "successor": None if candidate.successor is None else candidate.successor.value,
        "summary": candidate.summary,
        "target_registry": candidate.target_registry.value,
        "version": candidate.version,
    }


def _validate_scan(scan: SourceScan) -> str | None:
    history_by_id = {bundle.candidate.id: bundle for bundle in scan.history}
    active_ids = tuple(bundle.candidate.id for bundle in scan.active)
    if len(history_by_id) != len(scan.history):
        return "Candidate history contains duplicate Candidate IDs"
    if len(set(active_ids)) != len(active_ids) or any(
        history_by_id.get(bundle.candidate.id) != bundle for bundle in scan.active
    ):
        return "active Candidates must be exact records retained in history"
    if tuple(sorted(scan.history, key=lambda item: item.candidate.id.value)) != scan.history:
        return "Candidate history records must be in canonical Candidate-ID order"
    if tuple(sorted(scan.active, key=lambda item: str(item.artifact.manifest_path))) != scan.active:
        return "active Candidates must be in canonical manifest-path order"
    if any(
        bundle.candidate.artifact.coordinate.source != scan.source_alias for bundle in scan.history
    ):
        return "Candidate history contains another Source alias"
    if any(
        bundle.candidate.artifact.provenance.revision != scan.revision for bundle in scan.active
    ):
        return "active Candidate history does not bind the Source Scan revision"
    collection_history_by_id = {item.id: item for item in scan.collection_history}
    collection_active_ids = tuple(item.id for item in scan.collection_active)
    if len(collection_history_by_id) != len(scan.collection_history):
        return "Collection Candidate history contains duplicate Candidate IDs"
    if len(set(collection_active_ids)) != len(collection_active_ids) or any(
        collection_history_by_id.get(item.id) != item for item in scan.collection_active
    ):
        return "active Collection Candidates must be exact records retained in history"
    if (
        tuple(sorted(scan.collection_history, key=lambda item: item.id.value))
        != scan.collection_history
    ):
        return "Collection Candidate history records must be in canonical Candidate-ID order"
    if (
        tuple(sorted(scan.collection_active, key=lambda item: item.manifest_path))
        != scan.collection_active
    ):
        return "active Collection Candidates must be in canonical manifest-path order"
    if any(item.source_alias != scan.source_alias for item in scan.collection_history):
        return "Collection Candidate history contains another Source alias"
    if any(item.source_revision != scan.revision for item in scan.collection_active):
        return "active Collection Candidate history does not bind the Source Scan revision"
    all_ids = {bundle.candidate.id for bundle in scan.history} | set(collection_history_by_id)
    if len(all_ids) != len(scan.history) + len(scan.collection_history):
        return "artifact and Collection Candidate IDs must be globally unique"
    return None


def serialize_source_scan(scan: SourceScan) -> Result[SerializedSourceScan]:
    if not isinstance(scan, SourceScan):
        return _error("Candidate history serialization needs a Source Scan")
    invalid = _validate_scan(scan)
    if invalid is not None:
        return _error(invalid)
    objects: dict[ObjectDigest, ObjectCandidate] = {}
    records = []
    for bundle in scan.history:
        stored = make_object_candidate(bundle.artifact.canonical_entries)
        if isinstance(stored, Err):
            return _error(
                f"candidate {bundle.candidate.id} does not form one canonical compiled object"
            )
        objects[stored.value.digest] = stored.value
        records.append(_bundle_to_data(bundle, stored.value.digest))
    data: dict[str, object] = {
        "active": [bundle.candidate.id.value for bundle in scan.active],
        "history": records,
        "manifest_count": scan.manifest_count,
        "revision": scan.revision,
        "schema": (
            "aart.dev/candidate-history/v2"
            if scan.collection_active or scan.collection_history
            else "aart.dev/candidate-history/v1"
        ),
        "source_alias": scan.source_alias.value,
    }
    if scan.collection_active or scan.collection_history:
        data["collection_active"] = [item.id.value for item in scan.collection_active]
        data["collection_history"] = [_collection_to_data(item) for item in scan.collection_history]
    content = canonical_json_bytes(cast(CanonicalValue, data))
    try:
        return Ok(
            SerializedSourceScan(
                content,
                tuple(sorted(objects.values(), key=lambda item: item.digest.value)),
            )
        )
    except ValueError as error:
        return _error(str(error))


_BUNDLE_FIELDS = frozenset(
    {
        "artifact",
        "candidate_id",
        "canonical_digest",
        "compliance",
        "findings",
        "input_digest",
        "manifest_path",
        "object_digest",
        "previous",
        "registry_snapshot",
        "rejection_reason",
        "state",
        "successor",
        "target_registry",
    }
)

_COLLECTION_FIELDS = frozenset(
    {
        "candidate_id",
        "canonical_digest",
        "findings",
        "input_digest",
        "manifest_path",
        "members",
        "name",
        "previous",
        "source_alias",
        "source_location",
        "source_revision",
        "state",
        "successor",
        "summary",
        "target_registry",
        "version",
    }
)


def _candidate_id(value: object, label: str) -> CandidateId:
    return CandidateId(_text(value, label))


def _optional_candidate_id(value: object, label: str) -> CandidateId | None:
    return None if value is None else _candidate_id(value, label)


def _findings(value: object) -> tuple[CandidateFinding, ...]:
    if not isinstance(value, list):
        raise ValueError("candidate findings must be a list")
    findings = []
    for raw in value:
        item = _mapping(
            raw,
            frozenset({"code", "message", "severity"}),
            "candidate finding",
        )
        findings.append(
            CandidateFinding(
                _text(item["code"], "candidate finding code"),
                FindingSeverity(_text(item["severity"], "candidate finding severity")),
                _text(item["message"], "candidate finding message"),
            )
        )
    return tuple(findings)


def _request(value: object) -> ArtifactRequest:
    raw = _text(value, "Collection member")
    coordinate, marker, constraint = raw.partition("@")
    parts = coordinate.split("/")
    if len(parts) == 3:
        source_raw, kind, name = parts
        source = SourceAlias(_text(source_raw, "Collection member Source"))
    elif len(parts) == 2:
        kind, name = parts
        source = None
    else:
        raise ValueError("Collection member coordinate is invalid")
    if kind not in {item.value for item in ArtifactKind}:
        raise ValueError("Collection member kind is invalid")
    request = ArtifactRequest(
        ArtifactIdentity(cast(IdentityKind, kind), _text(name, "Collection member name")),
        VersionConstraint(_text(constraint, "Collection member constraint") if marker else "*"),
        source,
    )
    if str(request) != raw:
        raise ValueError("Collection member is not canonical")
    return request


def _collection(value: object) -> CollectionCandidate:
    data = _mapping(value, _COLLECTION_FIELDS, "Collection Candidate history record")
    members_raw = data["members"]
    if not isinstance(members_raw, list):
        raise ValueError("Collection Candidate members must be a list")
    source_alias = SourceAlias(_text(data["source_alias"], "Collection Candidate Source alias"))
    manifest_path = _text(data["manifest_path"], "Collection Candidate manifest path")
    input_digest = _digest(data["input_digest"], "Collection Candidate input digest")
    target_registry = SourceAlias(
        _text(data["target_registry"], "Collection Candidate target registry")
    )
    candidate = CollectionCandidate(
        _candidate_id(data["candidate_id"], "Collection Candidate ID"),
        source_alias,
        _text(data["source_location"], "Collection Candidate Source location"),
        _text(data["source_revision"], "Collection Candidate Source revision"),
        manifest_path,
        input_digest,
        _digest(data["canonical_digest"], "Collection Candidate canonical digest"),
        target_registry,
        _text(data["name"], "Collection Candidate name"),
        _text(data["version"], "Collection Candidate version"),
        _text(data["summary"], "Collection Candidate summary"),
        tuple(_request(item) for item in members_raw),
        CandidateState(_text(data["state"], "Collection Candidate state")),
        _optional_candidate_id(data["previous"], "previous Collection Candidate ID"),
        _optional_candidate_id(data["successor"], "successor Collection Candidate ID"),
        _findings(data["findings"]),
    )
    if (
        candidate.id
        != collection_candidate_id_for(
            source_alias,
            manifest_path,
            input_digest,
            target_registry,
        )
        or _collection_to_data(candidate) != data
    ):
        raise ValueError("Collection Candidate history record is not canonical")
    return candidate


def _bundle(
    value: object,
    objects: dict[ObjectDigest, ObjectCandidate],
) -> CandidateBundle:
    data = _mapping(value, _BUNDLE_FIELDS, "Candidate history record")
    object_digest = _digest(data["object_digest"], "Candidate object digest")
    stored = objects.get(object_digest)
    if stored is None:
        raise ValueError(f"candidate compiled object is missing: {object_digest}")
    canonical_entries = tuple(
        entry for entry in stored.entries if entry.kind is SnapshotEntryKind.FILE
    )
    native = compile_native_package(canonical_entries)
    if isinstance(native, Err):
        raise ValueError("candidate compiled object is not a canonical native package")
    package = _artifact(data["artifact"])
    manifest_path = parse_relative_path(_text(data["manifest_path"], "candidate manifest path"))
    if isinstance(manifest_path, Err):
        raise ValueError("candidate manifest path is invalid")
    input_digest = _digest(data["input_digest"], "candidate input digest")
    compiled = CompiledAuthorArtifact(
        manifest_path.value,
        input_digest,
        package,
        native.value,
        canonical_entries,
        ComplianceLevel(_text(data["compliance"], "candidate compliance")),
    )
    if (
        str(compiled.manifest_path) != package.provenance.manifest_path
        or compiled.input_digest != package.provenance.input_digest
        or native.value.manifest.identity != package.coordinate.artifact
        or str(native.value.manifest.version) != package.coordinate.version
        or native.value.payload_digest != package.payload_digest
    ):
        raise ValueError("candidate compiled object and artifact metadata disagree")
    hashed = tree_digest(
        file_entry(entry.path, entry.content, executable=entry.executable)
        for entry in canonical_entries
        if str(entry.path) != "provenance.json"
    )
    canonical_digest = _digest(data["canonical_digest"], "Candidate canonical digest")
    if isinstance(hashed, Err) or hashed.value != canonical_digest:
        raise ValueError("candidate canonical digest does not bind its compiled object")
    registry_snapshot = data["registry_snapshot"]
    candidate = Candidate(
        _candidate_id(data["candidate_id"], "Candidate ID"),
        package,
        canonical_digest,
        SourceAlias(_text(data["target_registry"], "Candidate target registry")),
        CandidateState(_text(data["state"], "Candidate state")),
        _optional_candidate_id(data["previous"], "previous Candidate ID"),
        _optional_candidate_id(data["successor"], "successor Candidate ID"),
        _findings(data["findings"]),
        _optional_text(data["rejection_reason"], "Candidate rejection reason"),
        None
        if registry_snapshot is None
        else _digest(registry_snapshot, "Candidate registry snapshot"),
    )
    return CandidateBundle(candidate, compiled)


def source_scan_object_digests(index: bytes) -> Result[tuple[ObjectDigest, ...]]:
    """Return the exact compiled objects referenced by one canonical bounded index.

    Filesystem readers use this before loading object envelopes. Full record validation still
    happens in ``parse_source_scan``; this narrow pass only prevents an adapter from enumerating
    unrelated retained history or trusting paths supplied by serialized data.
    """

    if not isinstance(index, bytes) or not index or len(index) > _MAX_INDEX_BYTES:
        return _error("Candidate history index must be bounded bytes")
    try:
        decoded = json.loads(index.decode("utf-8"))
        if canonical_json_bytes(cast(CanonicalValue, decoded)) != index:
            raise ValueError("Candidate history index is not canonical JSON")
        if not isinstance(decoded, dict):
            raise ValueError("Candidate history index must be an object")
        schema = decoded.get("schema")
        fields = frozenset(
            {"active", "history", "manifest_count", "revision", "schema", "source_alias"}
        )
        if schema == "aart.dev/candidate-history/v2":
            fields |= frozenset({"collection_active", "collection_history"})
        data = _mapping(decoded, fields, "Candidate history index")
        if schema not in {
            "aart.dev/candidate-history/v1",
            "aart.dev/candidate-history/v2",
        }:
            raise ValueError("Candidate history schema is unsupported")
        history = data["history"]
        if not isinstance(history, list):
            raise ValueError("Candidate history records must be a list")
        digests = {
            _digest(
                _mapping(item, _BUNDLE_FIELDS, "Candidate history record")["object_digest"],
                "Candidate object digest",
            )
            for item in history
        }
        return Ok(tuple(sorted(digests, key=lambda item: item.value)))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return _error(f"Candidate history is invalid: {error}")


def parse_source_scan(
    index: bytes,
    objects: tuple[ObjectCandidate, ...],
) -> Result[SourceScan]:
    if not isinstance(index, bytes) or not index or len(index) > _MAX_INDEX_BYTES:
        return _error("Candidate history index must be bounded bytes")
    if any(not isinstance(item, ObjectCandidate) for item in objects):
        return _error("Candidate history objects are invalid")
    by_digest = {item.digest: item for item in objects}
    if len(by_digest) != len(objects):
        return _error("Candidate history contains duplicate compiled objects")
    try:
        decoded = json.loads(index.decode("utf-8"))
        if canonical_json_bytes(cast(CanonicalValue, decoded)) != index:
            raise ValueError("Candidate history index is not canonical JSON")
        if not isinstance(decoded, dict):
            raise ValueError("Candidate history index must be an object")
        schema = decoded.get("schema")
        fields = frozenset(
            {"active", "history", "manifest_count", "revision", "schema", "source_alias"}
        )
        if schema == "aart.dev/candidate-history/v2":
            fields |= frozenset({"collection_active", "collection_history"})
        data = _mapping(decoded, fields, "Candidate history index")
        if schema not in {
            "aart.dev/candidate-history/v1",
            "aart.dev/candidate-history/v2",
        }:
            raise ValueError("Candidate history schema is unsupported")
        history_data = data["history"]
        active_data = data["active"]
        manifest_count = data["manifest_count"]
        if not isinstance(history_data, list) or not isinstance(active_data, list):
            raise ValueError("Candidate history records and active IDs must be lists")
        if not isinstance(manifest_count, int) or isinstance(manifest_count, bool):
            raise ValueError("Candidate history manifest count must be an integer")
        history = tuple(_bundle(item, by_digest) for item in history_data)
        by_id = {bundle.candidate.id: bundle for bundle in history}
        if len(by_id) != len(history):
            raise ValueError("Candidate history contains duplicate Candidate IDs")
        active_ids = tuple(_candidate_id(item, "active Candidate ID") for item in active_data)
        if len(set(active_ids)) != len(active_ids) or any(item not in by_id for item in active_ids):
            raise ValueError("Candidate history active IDs are duplicated or missing")
        active = tuple(by_id[item] for item in active_ids)
        source_alias = SourceAlias(_text(data["source_alias"], "Source Scan alias"))
        revision = _text(data["revision"], "Source Scan revision")
        if any(bundle.candidate.artifact.coordinate.source != source_alias for bundle in history):
            raise ValueError("Candidate history contains another Source alias")
        if any(bundle.candidate.artifact.provenance.revision != revision for bundle in active):
            raise ValueError("active Candidate history does not bind the Source Scan revision")
        collection_history: tuple[CollectionCandidate, ...] = ()
        collection_active: tuple[CollectionCandidate, ...] = ()
        if schema == "aart.dev/candidate-history/v2":
            collection_history_data = data["collection_history"]
            collection_active_data = data["collection_active"]
            if not isinstance(collection_history_data, list) or not isinstance(
                collection_active_data, list
            ):
                raise ValueError("Collection Candidate history and active IDs must be lists")
            collection_history = tuple(_collection(item) for item in collection_history_data)
            collections_by_id = {item.id: item for item in collection_history}
            if len(collections_by_id) != len(collection_history):
                raise ValueError("Collection Candidate history contains duplicate Candidate IDs")
            collection_active_ids = tuple(
                _candidate_id(item, "active Collection Candidate ID")
                for item in collection_active_data
            )
            if len(set(collection_active_ids)) != len(collection_active_ids) or any(
                item not in collections_by_id for item in collection_active_ids
            ):
                raise ValueError("Collection Candidate active IDs are duplicated or missing")
            collection_active = tuple(collections_by_id[item] for item in collection_active_ids)
        scan = SourceScan(
            source_alias,
            revision,
            manifest_count,
            active,
            history,
            (),
            collection_active,
            collection_history,
        )
        canonical = serialize_source_scan(scan)
        if isinstance(canonical, Err) or canonical.value.index != index:
            raise ValueError("Candidate history index is not in canonical representation")
        return Ok(scan)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return _error(f"Candidate history is invalid: {error}")
