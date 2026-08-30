"""Manifest-first native authoring discovery and deterministic canonical compilation.

Every function operates over an already acquired immutable snapshot.  Filesystem/Git acquisition
stays outside this module; no repository-shape heuristic can create an artifact candidate here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Literal, cast

from agent_artifacts.domain.artifacts import (
    ArtifactFormat,
    ArtifactKind,
    ArtifactPackage,
    Compatibility,
)
from agent_artifacts.domain.artifacts import (
    Capability as ArtifactCapability,
)
from agent_artifacts.domain.artifacts import (
    Provenance as ArtifactProvenance,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity, SourceLocation
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.identifiers import (
    ArtifactKind as IdentityKind,
)
from agent_artifacts.domain.result import Err, Ok, Result

from .codes import AUTHOR_MANIFEST_INVALID, AUTHOR_PAYLOAD_INVALID, AUTHOR_TREE_INVALID
from .hashing import file_entry, sha256_bytes, tree_digest
from .json import JsonArray, JsonObject, JsonValue, canonical_json_bytes, parse_json
from .native_models import (
    PAYLOAD_FORMAT_BY_TYPE,
    ArtifactManifest,
    CompatibilitySpec,
    ImporterProvenance,
    InstallEffect,
    InstallSpec,
    OriginProvenance,
    PayloadSpec,
    Provenance,
)
from .native_schema import artifact_manifest_to_json, provenance_to_json
from .native_tree import (
    NativeArtifactPackage,
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
    compile_native_package,
)
from .paths import SafeRelativePath, parse_relative_path
from .semver import SemVer, parse_semver
from .yaml import parse_yaml

AuthorKind = Literal["skill", "guideline", "mcp", "hook", "memory"]

_MANIFEST_NAMES = frozenset({"aart.json", "aart.yaml"})
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_KIND_BY_VALUE: dict[AuthorKind, ArtifactKind] = {
    "skill": ArtifactKind.SKILL,
    "guideline": ArtifactKind.GUIDELINE,
    "mcp": ArtifactKind.MCP,
    "hook": ArtifactKind.HOOK,
    "memory": ArtifactKind.MEMORY,
}
_INSTALL_EFFECTS: dict[AuthorKind, tuple[InstallEffect, ...]] = {
    "skill": ("copy-tree",),
    "guideline": ("write-file",),
    "mcp": ("merge-json",),
    "hook": ("copy-tree", "merge-json"),
    "memory": ("managed-block",),
}
_COMPILER_ID = "aart-native-author"
_COMPILER_VERSION = SemVer(1, 0, 0)
_COMPILER_OPTIONS_DIGEST = sha256_bytes(b"AART-NATIVE-AUTHOR-COMPILER-V1\n")


class ComplianceLevel(str, Enum):
    AART_NATIVE = "aart-native"
    AART_COMPATIBLE = "aart-compatible"


@dataclass(frozen=True, slots=True)
class DiscoveredAuthorManifest:
    path: SafeRelativePath
    content: bytes


@dataclass(frozen=True, slots=True)
class AuthorManifest:
    schema: str
    name: str
    kind: AuthorKind
    version: SemVer
    summary: str
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    transport: str | None
    runtime: str | None
    runtime_version: str | None
    launch: str | None
    entrypoint: SafeRelativePath | None
    harnesses: tuple[str, ...]
    platforms: tuple[str, ...]
    compliance: ComplianceLevel
    canonical_intent: JsonObject


@dataclass(frozen=True, slots=True)
class CompiledAuthorArtifact:
    manifest_path: SafeRelativePath
    input_digest: ObjectDigest
    package: ArtifactPackage
    native_package: NativeArtifactPackage
    canonical_entries: tuple[SnapshotEntry, ...]
    compliance: ComplianceLevel


def _error(
    code: DiagnosticCode,
    message: str,
    *,
    path: str | None = None,
    pointer: str | None = None,
) -> Err:
    return Err(
        (
            Diagnostic(
                code,
                Severity.ERROR,
                message,
                SourceLocation(path=path, pointer=pointer),
            ),
        )
    )


def _validated_snapshot(snapshot: SourceSnapshot) -> Result[dict[str, SnapshotEntry]]:
    if not isinstance(snapshot.origin, SnapshotOrigin):
        return _error(AUTHOR_TREE_INVALID, "author snapshot origin is invalid")
    entries: dict[str, SnapshotEntry] = {}
    for entry in snapshot.entries:
        raw_path = str(entry.path)
        parsed = parse_relative_path(raw_path)
        if not isinstance(parsed, Ok) or parsed.value != entry.path:
            return _error(
                AUTHOR_TREE_INVALID,
                f"snapshot path is not canonical: {raw_path!r}",
                path=raw_path,
            )
        if raw_path in entries:
            return _error(
                AUTHOR_TREE_INVALID,
                f"duplicate snapshot path: {raw_path}",
                path=raw_path,
            )
        if not isinstance(entry.kind, SnapshotEntryKind):
            return _error(AUTHOR_TREE_INVALID, "snapshot entry kind is invalid", path=raw_path)
        if not isinstance(entry.content, bytes) or not isinstance(entry.executable, bool):
            return _error(AUTHOR_TREE_INVALID, "snapshot file metadata is invalid", path=raw_path)
        if entry.kind is SnapshotEntryKind.DIRECTORY and (entry.content or entry.executable):
            return _error(
                AUTHOR_TREE_INVALID,
                "snapshot directory has file metadata",
                path=raw_path,
            )
        entries[raw_path] = entry
    return Ok(entries)


def discover_author_manifests(
    snapshot: SourceSnapshot,
) -> Result[tuple[DiscoveredAuthorManifest, ...]]:
    """Find only exact supported manifest basenames, never repository heuristics."""

    validated = _validated_snapshot(snapshot)
    if isinstance(validated, Err):
        return validated
    discovered: list[DiscoveredAuthorManifest] = []
    roots: dict[tuple[str, ...], str] = {}
    for raw_path, entry in validated.value.items():
        if entry.path.parts[-1] not in _MANIFEST_NAMES:
            continue
        if entry.kind is not SnapshotEntryKind.FILE:
            return _error(
                AUTHOR_TREE_INVALID,
                "author manifest must be a regular file",
                path=raw_path,
            )
        root = entry.path.parts[:-1]
        previous = roots.get(root)
        if previous is not None:
            return _error(
                AUTHOR_TREE_INVALID,
                f"artifact boundary contains both {previous} and {entry.path.parts[-1]}",
                path=raw_path,
            )
        roots[root] = entry.path.parts[-1]
        discovered.append(DiscoveredAuthorManifest(entry.path, entry.content))
    return Ok(tuple(sorted(discovered, key=lambda item: str(item.path))))


def _object(value: JsonValue, label: str, *, path: str) -> Result[JsonObject]:
    if isinstance(value, JsonObject):
        return Ok(value)
    return _error(AUTHOR_MANIFEST_INVALID, f"{label} must be an object", path=path)


def _fields(
    value: JsonObject,
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    path: str,
    label: str,
    extensions: bool = False,
) -> Result[dict[str, JsonValue]]:
    fields = dict(value.entries)
    missing = sorted(required - fields.keys())
    if missing:
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"{label} is missing required field {missing[0]!r}",
            path=path,
        )
    unknown = sorted(
        key
        for key in fields.keys() - required - optional
        if not (extensions and key.startswith("x-"))
    )
    if unknown:
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"{label} contains unknown field {unknown[0]!r}",
            path=path,
        )
    return Ok(fields)


def _string(value: JsonValue, label: str, *, path: str) -> Result[str]:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
    ):
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"{label} must be a non-empty single-line string",
            path=path,
        )
    return Ok(value)


def _strings(
    value: JsonValue,
    label: str,
    *,
    path: str,
    allow_empty: bool,
) -> Result[tuple[str, ...]]:
    if not isinstance(value, JsonArray) or (not value.items and not allow_empty):
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"{label} must be {'an' if allow_empty else 'a non-empty'} array of strings",
            path=path,
        )
    result: list[str] = []
    for item in value.items:
        parsed = _string(item, f"{label} item", path=path)
        if isinstance(parsed, Err):
            return parsed
        result.append(parsed.value)
    return Ok(tuple(sorted(set(result))))


def _nested_type(
    value: JsonValue,
    label: str,
    *,
    path: str,
    optional: frozenset[str] = frozenset(),
) -> Result[tuple[str, dict[str, JsonValue], JsonObject]]:
    object_result = _object(value, label, path=path)
    if isinstance(object_result, Err):
        return object_result
    field_result = _fields(
        object_result.value,
        required=frozenset({"type"}),
        optional=optional,
        path=path,
        label=label,
        extensions=True,
    )
    if isinstance(field_result, Err):
        return field_result
    type_result = _string(field_result.value["type"], f"{label}.type", path=path)
    if isinstance(type_result, Err):
        return type_result
    if _SLUG_RE.fullmatch(type_result.value) is None:
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"{label}.type must be a lowercase slug",
            path=path,
        )
    return Ok((type_result.value, field_result.value, object_result.value))


def _parse_document(manifest: DiscoveredAuthorManifest) -> Result[JsonObject]:
    raw_path = str(manifest.path)
    if manifest.path.parts[-1] == "aart.json":
        parsed = parse_json(manifest.content, location=SourceLocation(path=raw_path))
        if isinstance(parsed, Err):
            return _error(
                AUTHOR_MANIFEST_INVALID,
                parsed.diagnostics[0].message,
                path=raw_path,
            )
    else:
        parsed = parse_yaml(manifest.content, path=raw_path)
    if isinstance(parsed, Err):
        return parsed
    return _object(parsed.value, "author manifest", path=raw_path)


def _validate_pattern(raw: str, *, path: str) -> Result[str]:
    if (
        raw.startswith("/")
        or "\\" in raw
        or any(ord(character) < 32 for character in raw)
        or any(part in {"", ".", ".."} for part in raw.split("/"))
    ):
        return _error(
            AUTHOR_PAYLOAD_INVALID,
            f"payload pattern cannot escape or ambiguously address its manifest root: {raw!r}",
            path=path,
        )
    return Ok(raw)


def parse_author_manifest(manifest: DiscoveredAuthorManifest) -> Result[AuthorManifest]:
    """Validate one syntax document into a frozen authoring representation."""

    raw_path = str(manifest.path)
    document_result = _parse_document(manifest)
    if isinstance(document_result, Err):
        return document_result
    root_result = _fields(
        document_result.value,
        required=frozenset({"schema", "artifact", "payload"}),
        optional=frozenset(
            {
                "transport",
                "runtime",
                "launch",
                "requirements",
                "inputs",
                "credentials",
                "compatibility",
                "install",
            }
        ),
        path=raw_path,
        label="author manifest",
        extensions=True,
    )
    if isinstance(root_result, Err):
        return root_result
    root = root_result.value
    schema_result = _string(root["schema"], "schema", path=raw_path)
    if isinstance(schema_result, Err):
        return schema_result

    artifact_object = _object(root["artifact"], "artifact", path=raw_path)
    if isinstance(artifact_object, Err):
        return artifact_object
    artifact_fields = _fields(
        artifact_object.value,
        required=frozenset({"name", "kind", "version"}),
        optional=frozenset({"summary"}),
        path=raw_path,
        label="artifact",
        extensions=True,
    )
    if isinstance(artifact_fields, Err):
        return artifact_fields
    raw_artifact = artifact_fields.value
    name = _string(raw_artifact["name"], "artifact.name", path=raw_path)
    kind = _string(raw_artifact["kind"], "artifact.kind", path=raw_path)
    version = _string(raw_artifact["version"], "artifact.version", path=raw_path)
    for parsed in (name, kind, version):
        if isinstance(parsed, Err):
            return parsed
    assert isinstance(name, Ok) and isinstance(kind, Ok) and isinstance(version, Ok)
    if _SLUG_RE.fullmatch(name.value) is None:
        return _error(
            AUTHOR_MANIFEST_INVALID,
            "artifact.name must be a lowercase slug",
            path=raw_path,
        )
    if kind.value not in _KIND_BY_VALUE:
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"unsupported artifact.kind {kind.value!r}",
            path=raw_path,
        )
    author_kind = kind.value
    if schema_result.value != f"aart.dev/{author_kind}/v1":
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"schema must be 'aart.dev/{author_kind}/v1' for artifact.kind {author_kind!r}",
            path=raw_path,
        )
    parsed_version = parse_semver(
        version.value,
        location=SourceLocation(path=raw_path, pointer="/artifact/version"),
    )
    if isinstance(parsed_version, Err):
        return _error(
            AUTHOR_MANIFEST_INVALID,
            parsed_version.diagnostics[0].message,
            path=raw_path,
        )
    summary = name.value.replace("-", " ").capitalize()
    if "summary" in raw_artifact:
        parsed_summary = _string(raw_artifact["summary"], "artifact.summary", path=raw_path)
        if isinstance(parsed_summary, Err):
            return parsed_summary
        summary = parsed_summary.value

    payload_object = _object(root["payload"], "payload", path=raw_path)
    if isinstance(payload_object, Err):
        return payload_object
    payload_fields = _fields(
        payload_object.value,
        required=frozenset({"include"}),
        optional=frozenset({"exclude"}),
        path=raw_path,
        label="payload",
    )
    if isinstance(payload_fields, Err):
        return payload_fields
    includes = _strings(
        payload_fields.value["include"], "payload.include", path=raw_path, allow_empty=False
    )
    if isinstance(includes, Err):
        return includes
    excludes: Result[tuple[str, ...]] = Ok(())
    if "exclude" in payload_fields.value:
        excludes = _strings(
            payload_fields.value["exclude"],
            "payload.exclude",
            path=raw_path,
            allow_empty=True,
        )
    if isinstance(excludes, Err):
        return excludes
    for pattern in (*includes.value, *excludes.value):
        safe = _validate_pattern(pattern, path=raw_path)
        if isinstance(safe, Err):
            return safe

    transport: str | None = None
    transport_object: JsonObject | None = None
    if "transport" in root:
        parsed_transport = _nested_type(root["transport"], "transport", path=raw_path)
        if isinstance(parsed_transport, Err):
            return parsed_transport
        transport, _transport_fields, transport_object = parsed_transport.value

    runtime: str | None = None
    runtime_version: str | None = None
    runtime_object: JsonObject | None = None
    if "runtime" in root:
        parsed_runtime = _nested_type(
            root["runtime"], "runtime", path=raw_path, optional=frozenset({"version"})
        )
        if isinstance(parsed_runtime, Err):
            return parsed_runtime
        runtime, runtime_fields, runtime_object = parsed_runtime.value
        if "version" in runtime_fields:
            parsed_runtime_version = _string(
                runtime_fields["version"], "runtime.version", path=raw_path
            )
            if isinstance(parsed_runtime_version, Err):
                return parsed_runtime_version
            runtime_version = parsed_runtime_version.value

    launch: str | None = None
    entrypoint: SafeRelativePath | None = None
    launch_object: JsonObject | None = None
    if "launch" in root:
        parsed_launch = _nested_type(
            root["launch"],
            "launch",
            path=raw_path,
            optional=frozenset({"entrypoint", "path"}),
        )
        if isinstance(parsed_launch, Err):
            return parsed_launch
        launch, launch_fields, launch_object = parsed_launch.value
        launch_location_fields = set(launch_fields) & {"entrypoint", "path"}
        if len(launch_location_fields) > 1:
            return _error(
                AUTHOR_MANIFEST_INVALID,
                "launch must declare only one of entrypoint or path",
                path=raw_path,
            )
        if launch_location_fields:
            location_field = next(iter(launch_location_fields))
            raw_entrypoint = _string(
                launch_fields[location_field], f"launch.{location_field}", path=raw_path
            )
            if isinstance(raw_entrypoint, Err):
                return raw_entrypoint
            parsed_entrypoint = parse_relative_path(
                raw_entrypoint.value,
                location=SourceLocation(path=raw_path, pointer="/launch/entrypoint"),
            )
            if isinstance(parsed_entrypoint, Err):
                return _error(
                    AUTHOR_MANIFEST_INVALID,
                    f"launch.{location_field} must be a safe path below the manifest root",
                    path=raw_path,
                )
            entrypoint = parsed_entrypoint.value

    compliance = ComplianceLevel.AART_NATIVE
    if author_kind == "mcp":
        if transport != "stdio":
            return _error(
                AUTHOR_MANIFEST_INVALID,
                "mcp/v1 requires stdio transport",
                path=raw_path,
            )
        if launch == "python":
            if runtime != "python" or runtime_version is None or entrypoint is None:
                return _error(
                    AUTHOR_MANIFEST_INVALID,
                    "Python MCP launch requires a versioned Python runtime and entrypoint",
                    path=raw_path,
                )
        elif launch == "external-script":
            if entrypoint is None:
                return _error(
                    AUTHOR_MANIFEST_INVALID,
                    "external-script MCP launch requires launch.path",
                    path=raw_path,
                )
            compliance = ComplianceLevel.AART_COMPATIBLE
        else:
            return _error(
                AUTHOR_MANIFEST_INVALID,
                "mcp/v1 launch.type must be python or external-script",
                path=raw_path,
            )

    harnesses: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    compatibility_object: JsonObject | None = None
    if "compatibility" in root:
        raw_compatibility = _object(root["compatibility"], "compatibility", path=raw_path)
        if isinstance(raw_compatibility, Err):
            return raw_compatibility
        compatibility_object = raw_compatibility.value
        compatibility_fields = _fields(
            compatibility_object,
            required=frozenset(),
            optional=frozenset({"harnesses", "platforms"}),
            path=raw_path,
            label="compatibility",
            extensions=True,
        )
        if isinstance(compatibility_fields, Err):
            return compatibility_fields
        if "harnesses" in compatibility_fields.value:
            parsed_harnesses = _strings(
                compatibility_fields.value["harnesses"],
                "compatibility.harnesses",
                path=raw_path,
                allow_empty=True,
            )
            if isinstance(parsed_harnesses, Err):
                return parsed_harnesses
            harnesses = parsed_harnesses.value
        if "platforms" in compatibility_fields.value:
            parsed_platforms = _strings(
                compatibility_fields.value["platforms"],
                "compatibility.platforms",
                path=raw_path,
                allow_empty=True,
            )
            if isinstance(parsed_platforms, Err):
                return parsed_platforms
            platforms = parsed_platforms.value

    intent_entries: list[tuple[str, JsonValue]] = [
        ("schema", schema_result.value),
        ("payload", payload_object.value),
    ]
    if transport_object is not None:
        intent_entries.append(("transport", transport_object))
    if runtime_object is not None:
        intent_entries.append(("runtime", runtime_object))
    if launch_object is not None:
        intent_entries.append(("launch", launch_object))
    if compatibility_object is not None:
        intent_entries.append(("compatibility", compatibility_object))

    return Ok(
        AuthorManifest(
            schema_result.value,
            name.value,
            author_kind,
            parsed_version.value,
            summary,
            includes.value,
            excludes.value,
            transport,
            runtime,
            runtime_version,
            launch,
            entrypoint,
            harnesses,
            platforms,
            compliance,
            JsonObject(tuple(intent_entries)),
        )
    )


def _glob_regex(pattern: str) -> re.Pattern[str]:
    pieces: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*" and index + 1 < len(pattern) and pattern[index + 1] == "*":
            index += 2
            if index < len(pattern) and pattern[index] == "/":
                pieces.append("(?:.*/)?")
                index += 1
            else:
                pieces.append(".*")
            continue
        if character == "*":
            pieces.append("[^/]*")
        elif character == "?":
            pieces.append("[^/]")
        else:
            pieces.append(re.escape(character))
        index += 1
    pieces.append("$")
    return re.compile("".join(pieces))


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(_glob_regex(pattern).fullmatch(path) is not None for pattern in patterns)


def _below(parts: tuple[str, ...], root: tuple[str, ...]) -> tuple[str, ...] | None:
    if parts[: len(root)] != root or len(parts) <= len(root):
        return None
    return parts[len(root) :]


def _selected_payload(
    entries: dict[str, SnapshotEntry],
    discovered: tuple[DiscoveredAuthorManifest, ...],
    source_manifest: DiscoveredAuthorManifest,
    manifest: AuthorManifest,
) -> Result[tuple[tuple[str, SnapshotEntry], ...]]:
    boundary = source_manifest.path.parts[:-1]
    nested_roots = tuple(
        item.path.parts[:-1]
        for item in discovered
        if item.path != source_manifest.path
        and len(item.path.parts[:-1]) > len(boundary)
        and item.path.parts[: len(boundary)] == boundary
    )
    selected: list[tuple[str, SnapshotEntry]] = []
    for entry in entries.values():
        relative_parts = _below(entry.path.parts, boundary)
        if relative_parts is None:
            continue
        if any(entry.path.parts[: len(nested_root)] == nested_root for nested_root in nested_roots):
            continue
        relative = "/".join(relative_parts)
        if relative in _MANIFEST_NAMES:
            continue
        if not _matches(relative, manifest.includes) or _matches(relative, manifest.excludes):
            continue
        if entry.kind is not SnapshotEntryKind.FILE:
            return _error(
                AUTHOR_PAYLOAD_INVALID,
                f"declared payload selects forbidden {entry.kind.value} entry {relative!r}",
                path=str(source_manifest.path),
            )
        selected.append((relative, entry))
    selected.sort(key=lambda item: item[0])
    if not selected:
        return _error(
            AUTHOR_PAYLOAD_INVALID,
            "declared payload selects no regular files",
            path=str(source_manifest.path),
        )
    if manifest.entrypoint is not None and str(manifest.entrypoint) not in {
        relative for relative, _entry in selected
    }:
        return _error(
            AUTHOR_PAYLOAD_INVALID,
            f"launch.entrypoint {manifest.entrypoint!s} is outside the declared payload",
            path=str(source_manifest.path),
        )
    if manifest.kind == "mcp" and any(relative == "mcp.json" for relative, _entry in selected):
        return _error(
            AUTHOR_PAYLOAD_INVALID,
            "mcp.json is reserved for the compiler-generated canonical descriptor",
            path=str(source_manifest.path),
        )
    return Ok(tuple(selected))


def _input_digest(
    source_manifest: DiscoveredAuthorManifest,
    selected: tuple[tuple[str, SnapshotEntry], ...],
) -> Result[ObjectDigest]:
    manifest_name = source_manifest.path.parts[-1]
    logical_manifest = parse_relative_path(f"manifest/{manifest_name}")
    assert isinstance(logical_manifest, Ok)
    records = [file_entry(logical_manifest.value, source_manifest.content)]
    for relative, entry in selected:
        path = parse_relative_path(f"payload/{relative}")
        assert isinstance(path, Ok)
        records.append(file_entry(path.value, entry.content, executable=entry.executable))
    digest = tree_digest(records)
    if isinstance(digest, Err):
        return _error(
            AUTHOR_PAYLOAD_INVALID,
            digest.diagnostics[0].message,
            path=str(source_manifest.path),
        )
    return digest


def _canonical_payload_entries(
    manifest: AuthorManifest,
    selected: tuple[tuple[str, SnapshotEntry], ...],
) -> Result[list[SnapshotEntry]]:
    entries: list[SnapshotEntry] = []
    for relative, source_entry in selected:
        path = parse_relative_path(f"payload/{relative}")
        assert isinstance(path, Ok)
        entries.append(
            SnapshotEntry(
                path.value,
                SnapshotEntryKind.FILE,
                source_entry.content,
                source_entry.executable,
            )
        )
    if manifest.kind == "mcp":
        assert manifest.entrypoint is not None
        if manifest.launch == "python":
            server_entries: tuple[tuple[str, JsonValue], ...] = (
                ("command", "${AART_RUNTIME_PYTHON}"),
                (
                    "args",
                    JsonArray((f"${{AART_PAYLOAD}}/{manifest.entrypoint}",)),
                ),
            )
        else:
            server_entries = (("command", f"${{AART_PAYLOAD}}/{manifest.entrypoint}"),)
        descriptor = JsonObject(
            (
                ("name", manifest.name),
                ("server", JsonObject(server_entries)),
            )
        )
        descriptor_path = parse_relative_path("payload/mcp.json")
        assert isinstance(descriptor_path, Ok)
        entries.append(
            SnapshotEntry(
                descriptor_path.value,
                SnapshotEntryKind.FILE,
                canonical_json_bytes(descriptor),
            )
        )
    return Ok(entries)


def _compile_one(
    source_manifest: DiscoveredAuthorManifest,
    manifest: AuthorManifest,
    selected: tuple[tuple[str, SnapshotEntry], ...],
    *,
    source_alias: SourceAlias,
    source: str,
    revision: str,
) -> Result[CompiledAuthorArtifact]:
    digest = _input_digest(source_manifest, selected)
    if isinstance(digest, Err):
        return digest
    payload_entries = _canonical_payload_entries(manifest, selected)
    if isinstance(payload_entries, Err):
        return payload_entries
    native_kind = manifest.kind
    payload_root = SafeRelativePath(("payload",))
    native_manifest = ArtifactManifest(
        1,
        ArtifactIdentity(cast(IdentityKind, manifest.kind), manifest.name),
        manifest.version,
        manifest.summary,
        PayloadSpec(payload_root, PAYLOAD_FORMAT_BY_TYPE[native_kind]),
        CompatibilitySpec(manifest.harnesses, manifest.platforms),
        InstallSpec(("project", "user"), ("copy",), _INSTALL_EFFECTS[manifest.kind]),
        extensions=(("aart.authoring", manifest.canonical_intent),),
    )
    native_provenance = Provenance(
        1,
        OriginProvenance(
            "git",
            source,
            revision,
            source_manifest.path,
            digest.value,
        ),
        ImporterProvenance(
            _COMPILER_ID,
            _COMPILER_VERSION,
            _COMPILER_OPTIONS_DIGEST,
        ),
        (),
    )
    manifest_path = parse_relative_path("artifact.json")
    provenance_path = parse_relative_path("provenance.json")
    assert isinstance(manifest_path, Ok) and isinstance(provenance_path, Ok)
    canonical_entries = [
        SnapshotEntry(
            manifest_path.value,
            SnapshotEntryKind.FILE,
            canonical_json_bytes(artifact_manifest_to_json(native_manifest)),
        ),
        *payload_entries.value,
        SnapshotEntry(
            provenance_path.value,
            SnapshotEntryKind.FILE,
            canonical_json_bytes(provenance_to_json(native_provenance)),
        ),
    ]
    ordered_entries = tuple(sorted(canonical_entries, key=lambda item: str(item.path)))
    native_package = compile_native_package(ordered_entries)
    if isinstance(native_package, Err):
        return native_package

    domain_kind = _KIND_BY_VALUE[manifest.kind]
    capabilities = tuple(
        ArtifactCapability(value)
        for value in (
            *((f"runtime/{manifest.runtime}",) if manifest.runtime is not None else ()),
            *((f"transport/{manifest.transport}",) if manifest.transport is not None else ()),
        )
    )
    package = ArtifactPackage(
        ArtifactCoordinate(
            source_alias,
            ArtifactIdentity(cast(IdentityKind, manifest.kind), manifest.name),
            str(manifest.version),
        ),
        domain_kind,
        ArtifactFormat(PAYLOAD_FORMAT_BY_TYPE[native_kind]),
        native_package.value.payload_digest,
        ArtifactProvenance(
            source,
            revision,
            str(source_manifest.path),
            digest.value,
            f"{_COMPILER_ID}/{_COMPILER_VERSION}",
        ),
        Compatibility(manifest.platforms, manifest.harnesses, manifest.runtime_version),
        capabilities,
        manifest.transport,
    )
    return Ok(
        CompiledAuthorArtifact(
            source_manifest.path,
            digest.value,
            package,
            native_package.value,
            ordered_entries,
            manifest.compliance,
        )
    )


def compile_author_snapshot(
    snapshot: SourceSnapshot,
    *,
    source_alias: SourceAlias,
    source: str,
    revision: str,
) -> Result[tuple[CompiledAuthorArtifact, ...]]:
    """Discover and compile every explicit authoring manifest in one acquired source."""

    if (
        not isinstance(source_alias, SourceAlias)
        or not source_alias.value
        or source_alias.value != source_alias.value.strip()
        or not source
        or source != source.strip()
        or _COMMIT_RE.fullmatch(revision) is None
    ):
        return _error(
            AUTHOR_TREE_INVALID,
            "author compilation requires a source alias, credential-free source, and pinned commit",
        )
    validated = _validated_snapshot(snapshot)
    if isinstance(validated, Err):
        return validated
    discovered = discover_author_manifests(snapshot)
    if isinstance(discovered, Err):
        return discovered
    compiled: list[CompiledAuthorArtifact] = []
    diagnostics: list[Diagnostic] = []
    for item in discovered.value:
        manifest = parse_author_manifest(item)
        if isinstance(manifest, Err):
            diagnostics.extend(manifest.diagnostics)
            continue
        selected = _selected_payload(validated.value, discovered.value, item, manifest.value)
        if isinstance(selected, Err):
            diagnostics.extend(selected.diagnostics)
            continue
        artifact = _compile_one(
            item,
            manifest.value,
            selected.value,
            source_alias=source_alias,
            source=source,
            revision=revision,
        )
        if isinstance(artifact, Err):
            diagnostics.extend(artifact.diagnostics)
        else:
            compiled.append(artifact.value)
    if diagnostics:
        return Err(tuple(diagnostics))
    return Ok(tuple(sorted(compiled, key=lambda item: str(item.manifest_path))))
