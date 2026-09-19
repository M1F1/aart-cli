"""Strict parsers and canonical projections for registry protocol v1 documents."""

from __future__ import annotations

import re
from typing import Iterable, cast

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity, SourceLocation
from aart_cli.domain.identifiers import ArtifactIdentity, SourceId
from aart_cli.domain.result import Err, Ok, Result

from .capabilities import Capability, parse_capability
from .codes import (
    REGISTRY_ENTRY_INVALID,
    REGISTRY_INVALID,
)
from .json import JsonArray, JsonObject, JsonValue, parse_json
from .native_models import (
    PAYLOAD_FORMAT_BY_TYPE,
)
from .registry_models import (
    RegistryManifest,
    ReviewRecord,
    ReviewStatus,
    ServiceAdvertisement,
)
from .schema import validate_object_fields
from .semver import SemVer, VersionBounds, parse_semver, version_bounds

_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SCP_GIT_RE = re.compile(r"^git@[A-Za-z0-9.-]+:[^\s?#]+$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_TYPES = frozenset(PAYLOAD_FORMAT_BY_TYPE)
_SCOPES = frozenset({"project", "user"})
_MODES = frozenset({"copy", "symlink"})
_EFFECTS = frozenset({"copy-tree", "write-file", "merge-json", "managed-block"})
_REVIEW_STATUSES = frozenset({"approved", "pending", "rejected"})


def _location(path: str, pointer: str | None = None) -> SourceLocation:
    return SourceLocation(path=path, pointer=pointer)


def _error(
    code: DiagnosticCode,
    message: str,
    *,
    path: str,
    pointer: str | None = None,
) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message, _location(path, pointer)),))


def _document(data: bytes | str, code: DiagnosticCode, *, path: str) -> Result[JsonObject]:
    parsed = parse_json(data, location=_location(path))
    if isinstance(parsed, Err):
        return parsed
    if not isinstance(parsed.value, JsonObject):
        return _error(code, "protocol document must be an object", path=path)
    return Ok(parsed.value)


def _object(value: JsonValue, code: DiagnosticCode, label: str, *, path: str) -> Result[JsonObject]:
    if isinstance(value, JsonObject):
        return Ok(value)
    return _error(code, f"{label} must be an object", path=path)


def _field(value: JsonObject, name: str) -> JsonValue:
    return dict(value.entries)[name]


def _extensions(value: JsonObject, known: frozenset[str]) -> tuple[tuple[str, JsonValue], ...]:
    return tuple((key, item) for key, item in value.entries if key not in known)


def _string(
    value: JsonValue,
    code: DiagnosticCode,
    label: str,
    *,
    path: str,
    single_line: bool = True,
) -> Result[str]:
    if not isinstance(value, str):
        return _error(code, f"{label} must be a string", path=path)
    if not value or value != value.strip():
        return _error(code, f"{label} must be non-empty without surrounding whitespace", path=path)
    if single_line and ("\n" in value or "\r" in value):
        return _error(code, f"{label} must be one line", path=path)
    return Ok(value)


def _integer(value: JsonValue, code: DiagnosticCode, label: str, *, path: str) -> Result[int]:
    if isinstance(value, int) and not isinstance(value, bool):
        return Ok(value)
    return _error(code, f"{label} must be an integer", path=path)


def _strings(
    value: JsonValue,
    code: DiagnosticCode,
    label: str,
    *,
    path: str,
    allow_empty: bool,
) -> Result[tuple[str, ...]]:
    if not isinstance(value, JsonArray):
        return _error(code, f"{label} must be an array", path=path)
    if not allow_empty and not value.items:
        return _error(code, f"{label} must not be empty", path=path)
    result: list[str] = []
    for item in value.items:
        parsed = _string(item, code, f"{label} item", path=path)
        if isinstance(parsed, Err):
            return parsed
        result.append(parsed.value)
    return Ok(tuple(sorted(set(result))))


def _schema_version(value: JsonObject, code: DiagnosticCode, *, path: str) -> Result[int]:
    parsed = _integer(_field(value, "schema_version"), code, "schema_version", path=path)
    if isinstance(parsed, Err):
        return parsed
    if parsed.value != 1:
        return _error(code, f"unsupported schema_version {parsed.value}", path=path)
    return parsed


def _bounds(value: JsonValue, code: DiagnosticCode, *, path: str) -> Result[VersionBounds]:
    object_result = _object(value, code, "version bounds", path=path)
    if isinstance(object_result, Err):
        return object_result
    validated = validate_object_fields(
        object_result.value,
        required=frozenset(),
        optional=frozenset({"min_inclusive", "max_exclusive"}),
        location=_location(path),
    )
    if isinstance(validated, Err):
        return validated
    values = dict(validated.value.entries)
    minimum: SemVer | None = None
    maximum: SemVer | None = None
    if "min_inclusive" in values:
        raw = _string(values["min_inclusive"], code, "min_inclusive", path=path)
        if isinstance(raw, Err):
            return raw
        parsed = parse_semver(raw.value, location=_location(path, "/min_inclusive"))
        if isinstance(parsed, Err):
            return parsed
        minimum = parsed.value
    if "max_exclusive" in values:
        raw = _string(values["max_exclusive"], code, "max_exclusive", path=path)
        if isinstance(raw, Err):
            return raw
        parsed = parse_semver(raw.value, location=_location(path, "/max_exclusive"))
        if isinstance(parsed, Err):
            return parsed
        maximum = parsed.value
    return version_bounds(minimum, maximum, location=_location(path))


def _slug(raw: str) -> bool:
    return _SLUG_RE.fullmatch(raw) is not None


def _safe_https_url(raw: str) -> bool:
    if not raw.startswith("https://"):
        return False
    authority = raw.removeprefix("https://").split("/", 1)[0]
    return (
        bool(authority)
        and "@" not in authority
        and "?" not in raw
        and "#" not in raw
        and not any(character.isspace() for character in raw)
    )


def _safe_git_url(raw: str) -> bool:
    return _SCP_GIT_RE.fullmatch(raw) is not None or _safe_https_url(raw)


def _safe_ref(raw: str) -> bool:
    forbidden = ("..", "@{", "\\", "~", "^", ":", "?", "*", "[")
    components = raw.split("/")
    return (
        bool(raw)
        and raw != "@"
        and not raw.startswith("-")
        and not raw.startswith("/")
        and not raw.endswith("/")
        and not raw.endswith(".")
        and "//" not in raw
        and not any(
            component.startswith(".") or component.endswith(".lock") for component in components
        )
        and not any(item in raw for item in forbidden)
        and not any(
            character.isspace() or ord(character) < 32 or ord(character) == 127 for character in raw
        )
    )


def _artifact_identity(
    raw_type: JsonValue, raw_name: JsonValue, *, path: str
) -> Result[ArtifactIdentity]:
    artifact_type = _string(raw_type, REGISTRY_ENTRY_INVALID, "type", path=path)
    name = _string(raw_name, REGISTRY_ENTRY_INVALID, "name", path=path)
    if isinstance(artifact_type, Err):
        return artifact_type
    if isinstance(name, Err):
        return name
    if artifact_type.value not in _ARTIFACT_TYPES or not _slug(name.value):
        return _error(REGISTRY_ENTRY_INVALID, "artifact identity is invalid", path=path)
    return Ok(ArtifactIdentity(artifact_type.value, name.value))


def _identity_key(raw: str, code: DiagnosticCode, *, path: str) -> Result[ArtifactIdentity]:
    parts = raw.split("/")
    if len(parts) != 2 or parts[0] not in _ARTIFACT_TYPES or not _slug(parts[1]):
        return _error(code, f"invalid artifact identity key: {raw!r}", path=path)
    return Ok(ArtifactIdentity(parts[0], parts[1]))


def _services(
    value: JsonValue, code: DiagnosticCode, *, path: str
) -> Result[tuple[ServiceAdvertisement, ...]]:
    parsed = _object(value, code, "services", path=path)
    if isinstance(parsed, Err):
        return parsed
    services: list[ServiceAdvertisement] = []
    for name, raw_service in parsed.value.entries:
        if _SERVICE_RE.fullmatch(name) is None:
            return _error(code, f"invalid service name: {name!r}", path=path)
        service_object = _object(raw_service, code, f"service {name}", path=path)
        if isinstance(service_object, Err):
            return service_object
        validated = validate_object_fields(
            service_object.value,
            required=frozenset({"kind"}),
            optional=frozenset({"repository"}),
            location=_location(path),
        )
        if isinstance(validated, Err):
            return validated
        kind = _string(_field(validated.value, "kind"), code, "service kind", path=path)
        if isinstance(kind, Err):
            return kind
        if not _slug(kind.value):
            return _error(code, "service kind must be a lowercase slug", path=path)
        repository: str | None = None
        if "repository" in validated.value.keys():
            raw_repository = _string(
                _field(validated.value, "repository"), code, "service repository", path=path
            )
            if isinstance(raw_repository, Err):
                return raw_repository
            if _REPOSITORY_RE.fullmatch(raw_repository.value) is None:
                return _error(
                    code, "service repository must be an owner/name coordinate", path=path
                )
            repository = raw_repository.value
        services.append(ServiceAdvertisement(name, kind.value, repository))
    return Ok(tuple(sorted(services, key=lambda service: service.name)))


def _review(value: JsonValue, code: DiagnosticCode, *, path: str) -> Result[ReviewRecord]:
    parsed = _object(value, code, "review", path=path)
    if isinstance(parsed, Err):
        return parsed
    validated = validate_object_fields(
        parsed.value,
        required=frozenset({"status", "policy"}),
        location=_location(path),
    )
    if isinstance(validated, Err):
        return validated
    status = _string(_field(validated.value, "status"), code, "review.status", path=path)
    policy = _string(_field(validated.value, "policy"), code, "review.policy", path=path)
    if isinstance(status, Err):
        return status
    if isinstance(policy, Err):
        return policy
    if status.value not in _REVIEW_STATUSES or not _slug(policy.value):
        return _error(code, "review record is invalid", path=path)
    return Ok(ReviewRecord(cast(ReviewStatus, status.value), policy.value))


def parse_registry_manifest(
    data: bytes | str,
    *,
    path: str = "aart-registry.json",
) -> Result[RegistryManifest]:
    document = _document(data, REGISTRY_INVALID, path=path)
    if isinstance(document, Err):
        return document
    required = frozenset(
        {
            "schema_version",
            "protocol_version",
            "registry_id",
            "display_name",
            "requires_aart",
            "required_capabilities",
            "default_channel",
            "services",
        }
    )
    validated = validate_object_fields(
        document.value,
        required=required,
        allow_extensions=True,
        location=_location(path),
    )
    if isinstance(validated, Err):
        return validated
    value = validated.value
    schema = _schema_version(value, REGISTRY_INVALID, path=path)
    protocol = _integer(
        _field(value, "protocol_version"), REGISTRY_INVALID, "protocol_version", path=path
    )
    registry_id = _string(_field(value, "registry_id"), REGISTRY_INVALID, "registry_id", path=path)
    display_name = _string(
        _field(value, "display_name"), REGISTRY_INVALID, "display_name", path=path
    )
    bounds = _bounds(_field(value, "requires_aart"), REGISTRY_INVALID, path=path)
    capabilities = _strings(
        _field(value, "required_capabilities"),
        REGISTRY_INVALID,
        "required_capabilities",
        path=path,
        allow_empty=True,
    )
    channel = _string(
        _field(value, "default_channel"), REGISTRY_INVALID, "default_channel", path=path
    )
    services = _services(_field(value, "services"), REGISTRY_INVALID, path=path)
    for result in (
        schema,
        protocol,
        registry_id,
        display_name,
        bounds,
        capabilities,
        channel,
        services,
    ):
        if isinstance(result, Err):
            return result
    assert isinstance(schema, Ok)
    assert isinstance(protocol, Ok)
    assert isinstance(registry_id, Ok)
    assert isinstance(display_name, Ok)
    assert isinstance(bounds, Ok)
    assert isinstance(capabilities, Ok)
    assert isinstance(channel, Ok)
    assert isinstance(services, Ok)
    if protocol.value != 1:
        return _error(REGISTRY_INVALID, f"unsupported protocol_version {protocol.value}", path=path)
    if not _slug(registry_id.value):
        return _error(REGISTRY_INVALID, "registry_id must be a lowercase slug", path=path)
    if not _safe_ref(channel.value):
        return _error(REGISTRY_INVALID, "default_channel must be a safe Git ref", path=path)
    parsed_capabilities: list[Capability] = []
    for raw in capabilities.value:
        parsed = parse_capability(raw, location=_location(path))
        if isinstance(parsed, Err):
            return parsed
        parsed_capabilities.append(parsed.value)
    return Ok(
        RegistryManifest(
            schema.value,
            protocol.value,
            SourceId(registry_id.value),
            display_name.value,
            bounds.value,
            tuple(sorted(set(parsed_capabilities))),
            channel.value,
            services.value,
            _extensions(value, required),
        )
    )


def _json_object(entries: Iterable[tuple[str, JsonValue]]) -> JsonObject:
    return JsonObject(tuple(entries))


def _json_array(values: Iterable[JsonValue]) -> JsonArray:
    return JsonArray(tuple(values))


def _string_array(values: Iterable[object]) -> JsonArray:
    return _json_array(str(value) for value in values)


def _bounds_json(bounds: VersionBounds) -> JsonObject:
    entries: list[tuple[str, JsonValue]] = []
    if bounds.min_inclusive is not None:
        entries.append(("min_inclusive", str(bounds.min_inclusive)))
    if bounds.max_exclusive is not None:
        entries.append(("max_exclusive", str(bounds.max_exclusive)))
    return _json_object(entries)


def _services_json(services: Iterable[ServiceAdvertisement]) -> JsonObject:
    entries: list[tuple[str, JsonValue]] = []
    for service in services:
        service_entries: list[tuple[str, JsonValue]] = [("kind", service.kind)]
        if service.repository is not None:
            service_entries.append(("repository", service.repository))
        entries.append((service.name, _json_object(service_entries)))
    return _json_object(entries)


def _review_json(review: ReviewRecord) -> JsonObject:
    return _json_object((("status", review.status), ("policy", review.policy)))


def registry_manifest_to_json(manifest: RegistryManifest) -> JsonObject:
    entries: list[tuple[str, JsonValue]] = [
        ("schema_version", manifest.schema_version),
        ("protocol_version", manifest.protocol_version),
        ("registry_id", str(manifest.registry_id)),
        ("display_name", manifest.display_name),
        ("requires_aart", _bounds_json(manifest.requires_aart)),
        ("required_capabilities", _string_array(manifest.required_capabilities)),
        ("default_channel", manifest.default_channel),
        ("services", _services_json(manifest.services)),
    ]
    entries.extend(manifest.extensions)
    return _json_object(entries)
