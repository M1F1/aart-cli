"""Strict schema-v1 parsing and canonical serialization for configuration."""

from __future__ import annotations

import posixpath
import re
from typing import Callable, TypeVar

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import SourceAlias, SourceId
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.capabilities import Capability, parse_capability
from aart_cli.protocol.json import (
    JsonArray,
    JsonObject,
    JsonValue,
    canonical_json_bytes,
    parse_json,
)
from aart_cli.protocol.schema import validate_object_fields

from .model import (
    TRUST_CLASSES,
    CompanyReviewedSource,
    ConfiguredSource,
    OrganizationPolicy,
    SourceKind,
    SyncMode,
    SyncSettings,
    UserConfiguration,
    git_location_parts,
    git_origin_key,
)

CONFIG_INVALID = DiagnosticCode("config-invalid")
POLICY_INVALID = DiagnosticCode("policy-invalid")
_ALIAS_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_HOST_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)$")
T = TypeVar("T")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _document(data: bytes | str, code: DiagnosticCode) -> Result[JsonObject]:
    parsed = parse_json(data)
    if isinstance(parsed, Err):
        return parsed
    if not isinstance(parsed.value, JsonObject):
        return _error(code, "configuration document must be a JSON object")
    return Ok(parsed.value)


def _validated(
    value: JsonObject,
    code: DiagnosticCode,
    *,
    required: frozenset[str] = frozenset(),
    optional: frozenset[str] = frozenset(),
) -> Result[dict[str, JsonValue]]:
    result = validate_object_fields(value, required=required, optional=optional)
    if isinstance(result, Err):
        return result
    return Ok(dict(result.value.entries))


def _object(value: JsonValue, code: DiagnosticCode, label: str) -> Result[JsonObject]:
    if not isinstance(value, JsonObject):
        return _error(code, f"{label} must be an object")
    return Ok(value)


def _string(value: JsonValue, code: DiagnosticCode, label: str) -> Result[str]:
    if not isinstance(value, str) or not value or value != value.strip():
        return _error(code, f"{label} must be a non-empty string without outer whitespace")
    if "\n" in value or "\r" in value:
        return _error(code, f"{label} must be one line")
    return Ok(value)


def _boolean(value: JsonValue, code: DiagnosticCode, label: str) -> Result[bool]:
    if not isinstance(value, bool):
        return _error(code, f"{label} must be a boolean")
    return Ok(value)


def _integer(value: JsonValue, code: DiagnosticCode, label: str) -> Result[int]:
    if not isinstance(value, int) or isinstance(value, bool):
        return _error(code, f"{label} must be an integer")
    return Ok(value)


def _enum(
    value: JsonValue,
    enum_type: Callable[[str], T],
    code: DiagnosticCode,
    label: str,
) -> Result[T]:
    parsed = _string(value, code, label)
    if isinstance(parsed, Err):
        return parsed
    try:
        return Ok(enum_type(parsed.value))
    except ValueError:
        return _error(code, f"{label} has an unsupported value")


def _alias(value: JsonValue, code: DiagnosticCode, label: str) -> Result[SourceAlias]:
    parsed = _string(value, code, label)
    if isinstance(parsed, Err):
        return parsed
    if _ALIAS_RE.fullmatch(parsed.value) is None:
        return _error(code, f"{label} must be a lowercase slug")
    return Ok(SourceAlias(parsed.value))


def _alias_array(
    value: JsonValue, code: DiagnosticCode, label: str
) -> Result[tuple[SourceAlias, ...]]:
    if not isinstance(value, JsonArray):
        return _error(code, f"{label} must be an array")
    aliases: list[SourceAlias] = []
    for item in value.items:
        parsed = _alias(item, code, f"{label} item")
        if isinstance(parsed, Err):
            return parsed
        aliases.append(parsed.value)
    if len(set(aliases)) != len(aliases):
        return _error(code, f"{label} must not contain duplicate aliases")
    return Ok(tuple(sorted(aliases)))


def _safe_ref(raw: str) -> bool:
    components = raw.split("/")
    forbidden = ("..", "@{", "\\", "~", "^", ":", "?", "*", "[")
    return (
        raw != "@"
        and not raw.startswith(("-", "/"))
        and not raw.endswith(("/", "."))
        and "//" not in raw
        and not any(part.startswith(".") or part.endswith(".lock") for part in components)
        and not any(value in raw for value in forbidden)
        and not any(character.isspace() or ord(character) < 32 for character in raw)
    )


def _local_path(location: JsonValue, label: str) -> Result[str]:
    """One absolute, already-normalized filesystem path, or a refusal naming what it is for.

    Normalizing it here instead would accept two spellings of one directory as two sources, and
    the second would take the first's place in a store keyed by what was written down.
    """

    parsed = _string(location, CONFIG_INVALID, label)
    if isinstance(parsed, Err):
        return parsed
    if not posixpath.isabs(parsed.value) or posixpath.normpath(parsed.value) != parsed.value:
        return _error(CONFIG_INVALID, f"{label} must be normalized and absolute")
    return parsed


def configured_source_from_input(
    alias: str,
    kind: SourceKind,
    location: str,
    ref: str | None = None,
) -> Result[ConfiguredSource]:
    """Parse one user-supplied source using the configuration schema's safety rules.

    A source entered through an interactive flow is enabled by default.  Call
    :func:`validate_configured_source` when preserving an existing source's
    enabled state.
    """

    if not isinstance(kind, SourceKind):
        return _error(CONFIG_INVALID, "source kind has an unsupported value")
    parsed_alias = _alias(alias, CONFIG_INVALID, "source alias")
    if isinstance(parsed_alias, Err):
        return parsed_alias
    if kind is SourceKind.REGISTRY_LOCAL:
        # The branch is named or the source is refused, with no default. A remote origin has one
        # obvious default and no other candidate; a checkout has a branch somebody happens to have
        # open, so guessing either `main` or HEAD installs content nobody selected (D-350).
        if ref is None:
            return _error(CONFIG_INVALID, "a local Registry checkout must name its branch")
        parsed_branch = _string(ref, CONFIG_INVALID, "registry branch")
        if isinstance(parsed_branch, Err):
            return parsed_branch
        if not _safe_ref(parsed_branch.value):
            return _error(CONFIG_INVALID, "registry branch is unsafe")
        parsed_root = _local_path(location, "local Registry path")
        if isinstance(parsed_root, Err):
            return parsed_root
        return Ok(
            ConfiguredSource(parsed_alias.value, kind, parsed_root.value, parsed_branch.value, True)
        )

    if kind is SourceKind.SOURCE_LOCAL:
        if ref is not None:
            return _error(CONFIG_INVALID, "local sources do not have Git refs")
        parsed_location = _local_path(location, "local source path")
        if isinstance(parsed_location, Err):
            return parsed_location
        return Ok(
            ConfiguredSource(
                parsed_alias.value,
                kind,
                parsed_location.value,
                None,
                True,
            )
        )

    parsed_location = _string(location, CONFIG_INVALID, "source URL")
    parsed_ref = _string(
        "main" if ref is None else ref,
        CONFIG_INVALID,
        "source ref",
    )
    if isinstance(parsed_location, Err):
        return parsed_location
    if isinstance(parsed_ref, Err):
        return parsed_ref
    if git_location_parts(parsed_location.value) is None:
        return _error(CONFIG_INVALID, "source URL must be a safe credential-free Git location")
    if not _safe_ref(parsed_ref.value):
        return _error(CONFIG_INVALID, "source ref is unsafe")
    return Ok(
        ConfiguredSource(
            parsed_alias.value,
            kind,
            parsed_location.value,
            parsed_ref.value,
            True,
        )
    )


def validate_configured_source(source: ConfiguredSource) -> Result[ConfiguredSource]:
    """Return a canonical, schema-safe configured source without serializing it."""

    if not isinstance(source, ConfiguredSource):
        return _error(CONFIG_INVALID, "configured source has an invalid value")
    if not isinstance(source.alias, SourceAlias):
        return _error(CONFIG_INVALID, "source alias has an invalid value")
    if not isinstance(source.kind, SourceKind):
        return _error(CONFIG_INVALID, "source kind has an unsupported value")
    if not isinstance(source.location, str):
        return _error(CONFIG_INVALID, "source location has an invalid value")
    if source.ref is not None and not isinstance(source.ref, str):
        return _error(CONFIG_INVALID, "source ref has an invalid value")
    if source.kind is not SourceKind.SOURCE_LOCAL and source.ref is None:
        return _error(CONFIG_INVALID, "Git sources require a ref")
    if not isinstance(source.enabled, bool):
        return _error(CONFIG_INVALID, "source enabled must be a boolean")

    parsed = configured_source_from_input(
        source.alias.value,
        source.kind,
        source.location,
        source.ref,
    )
    if isinstance(parsed, Err):
        return parsed
    return Ok(
        ConfiguredSource(
            parsed.value.alias,
            parsed.value.kind,
            parsed.value.location,
            parsed.value.ref,
            source.enabled,
        )
    )


def _source(value: JsonValue) -> Result[ConfiguredSource]:
    object_result = _object(value, CONFIG_INVALID, "source")
    if isinstance(object_result, Err):
        return object_result
    base = dict(object_result.value.entries)
    kind_result = _enum(base.get("kind"), SourceKind, CONFIG_INVALID, "source kind")
    if isinstance(kind_result, Err):
        return kind_result
    local = kind_result.value is SourceKind.SOURCE_LOCAL
    fields = _validated(
        object_result.value,
        CONFIG_INVALID,
        required=frozenset({"alias", "kind", "path" if local else "url", "enabled"}),
        optional=frozenset() if local else frozenset({"ref"}),
    )
    if isinstance(fields, Err):
        return fields
    alias = _alias(fields.value["alias"], CONFIG_INVALID, "source alias")
    enabled = _boolean(fields.value["enabled"], CONFIG_INVALID, "source enabled")
    if isinstance(alias, Err):
        return alias
    if isinstance(enabled, Err):
        return enabled
    if local:
        location = _string(fields.value["path"], CONFIG_INVALID, "source path")
        if isinstance(location, Err):
            return location
        return validate_configured_source(
            ConfiguredSource(alias.value, kind_result.value, location.value, None, enabled.value)
        )
    location = _string(fields.value["url"], CONFIG_INVALID, "source URL")
    ref = _string(fields.value.get("ref", "main"), CONFIG_INVALID, "source ref")
    if isinstance(location, Err):
        return location
    if isinstance(ref, Err):
        return ref
    return validate_configured_source(
        ConfiguredSource(alias.value, kind_result.value, location.value, ref.value, enabled.value)
    )


def _sources(value: JsonValue) -> Result[tuple[ConfiguredSource, ...]]:
    if not isinstance(value, JsonArray):
        return _error(CONFIG_INVALID, "sources must be an array")
    sources: list[ConfiguredSource] = []
    for item in value.items:
        result = _source(item)
        if isinstance(result, Err):
            return result
        sources.append(result.value)
    aliases = tuple(source.alias for source in sources)
    if len(set(aliases)) != len(aliases):
        return _error(CONFIG_INVALID, "source aliases must be unique")
    git_origins = tuple(
        (*git_origin_key(source.kind, source.location), source.ref or "")
        for source in sources
        if source.tracks_one_origin
    )
    if len(set(git_origins)) != len(git_origins):
        return _error(
            CONFIG_INVALID,
            "each Git source origin and ref pair must be unique",
        )
    return Ok(tuple(sources))


def _sync(value: JsonValue) -> Result[SyncSettings]:
    object_result = _object(value, CONFIG_INVALID, "sync")
    if isinstance(object_result, Err):
        return object_result
    fields = _validated(
        object_result.value,
        CONFIG_INVALID,
        optional=frozenset({"mode", "max_age_seconds"}),
    )
    if isinstance(fields, Err):
        return fields
    mode = _enum(fields.value.get("mode", "auto"), SyncMode, CONFIG_INVALID, "sync mode")
    age = _integer(fields.value.get("max_age_seconds", 900), CONFIG_INVALID, "sync max age")
    if isinstance(mode, Err):
        return mode
    if isinstance(age, Err):
        return age
    try:
        return Ok(SyncSettings(mode.value, age.value))
    except ValueError as error:
        return _error(CONFIG_INVALID, str(error))


def _ignored_reporting(
    value: JsonValue, code: DiagnosticCode, *, policy: bool = False
) -> Result[None]:
    """Validate the retired field's last accepted shape, then deliberately discard it.

    AART wrote this block into every configuration before CP-25.  Keeping it in the accepted field
    set is a compatibility boundary; returning no value is what makes that compatibility incapable
    of re-enabling the withdrawn behaviour.
    """

    label = "policy reporting" if policy else "reporting"
    object_result = _object(value, code, label)
    if isinstance(object_result, Err):
        return object_result
    fields = _validated(
        object_result.value,
        code,
        optional=frozenset(
            {"mode", "destination", "deny_public_destinations"}
            if policy
            else {"mode", "destination"}
        ),
    )
    if isinstance(fields, Err):
        return fields
    mode: str | None = None
    if "mode" in fields.value or not policy:
        parsed_mode = _string(fields.value.get("mode", "prompt"), code, f"{label} mode")
        if isinstance(parsed_mode, Err):
            return parsed_mode
        if parsed_mode.value not in {"disabled", "prompt", "automatic"}:
            return _error(code, f"{label} mode has an unsupported value")
        mode = parsed_mode.value
    if "destination" in fields.value:
        parsed = _alias(fields.value["destination"], code, f"{label} destination")
        if isinstance(parsed, Err):
            return parsed
    elif not policy and mode == "automatic":
        return _error(code, "automatic reporting requires an explicit destination")
    if policy and "deny_public_destinations" in fields.value:
        denied = _boolean(
            fields.value["deny_public_destinations"], code, "deny_public_destinations"
        )
        if isinstance(denied, Err):
            return denied
    return Ok(None)


def parse_user_configuration(data: bytes | str) -> Result[UserConfiguration]:
    document = _document(data, CONFIG_INVALID)
    if isinstance(document, Err):
        return document
    fields = _validated(
        document.value,
        CONFIG_INVALID,
        required=frozenset({"schema_version"}),
        optional=frozenset({"sources", "default_registry", "sync", "reporting"}),
    )
    if isinstance(fields, Err):
        return fields
    version = _integer(fields.value["schema_version"], CONFIG_INVALID, "schema_version")
    if isinstance(version, Err):
        return version
    if version.value != 1:
        return _error(CONFIG_INVALID, f"unsupported schema_version {version.value}")
    sources = _sources(fields.value.get("sources", JsonArray(())))
    sync = _sync(fields.value.get("sync", JsonObject(())))
    reporting = _ignored_reporting(fields.value.get("reporting", JsonObject(())), CONFIG_INVALID)
    if isinstance(sources, Err):
        return sources
    if isinstance(sync, Err):
        return sync
    if isinstance(reporting, Err):
        return reporting
    default_registry: SourceAlias | None = None
    if "default_registry" in fields.value and fields.value["default_registry"] is not None:
        parsed_default = _alias(
            fields.value["default_registry"], CONFIG_INVALID, "default registry"
        )
        if isinstance(parsed_default, Err):
            return parsed_default
        default_registry = parsed_default.value
    by_alias = {source.alias: source for source in sources.value}
    if default_registry is not None:
        default_source = by_alias.get(default_registry)
        if default_source is None or not default_source.enabled or not default_source.is_registry:
            return _error(CONFIG_INVALID, "default registry must name an enabled registry source")
    return Ok(UserConfiguration(1, sources.value, default_registry, sync.value))


def _source_json(source: ConfiguredSource) -> JsonObject:
    entries: list[tuple[str, JsonValue]] = [
        ("alias", source.alias.value),
        ("enabled", source.enabled),
        ("kind", source.kind.value),
    ]
    if source.kind is SourceKind.SOURCE_LOCAL:
        entries.append(("path", source.location))
    else:
        assert source.ref is not None
        entries.extend((("ref", source.ref), ("url", source.location)))
    return JsonObject(tuple(entries))


def user_configuration_bytes(configuration: UserConfiguration) -> bytes:
    entries: list[tuple[str, JsonValue]] = [
        ("schema_version", 1),
        ("sources", JsonArray(tuple(_source_json(source) for source in configuration.sources))),
        (
            "sync",
            JsonObject(
                (
                    ("max_age_seconds", configuration.sync.max_age_seconds),
                    ("mode", configuration.sync.mode.value),
                )
            ),
        ),
    ]
    if configuration.default_registry is not None:
        entries.append(("default_registry", configuration.default_registry.value))
    return canonical_json_bytes(JsonObject(tuple(entries)))


def _optional_strings(
    fields: dict[str, JsonValue],
    name: str,
    validator: Callable[[str], bool],
) -> Result[tuple[str, ...] | None]:
    if name not in fields:
        return Ok(None)
    value = fields[name]
    if not isinstance(value, JsonArray):
        return _error(POLICY_INVALID, f"{name} must be an array")
    values: list[str] = []
    for item in value.items:
        parsed = _string(item, POLICY_INVALID, f"{name} item")
        if isinstance(parsed, Err):
            return parsed
        normalized = parsed.value.casefold() if name == "allowed_git_hosts" else parsed.value
        if not validator(normalized):
            return _error(POLICY_INVALID, f"{name} contains an unsafe value")
        values.append(normalized)
    return Ok(tuple(sorted(set(values))))


def _company_reviewed_source(value: JsonValue) -> Result[CompanyReviewedSource]:
    object_result = _object(value, POLICY_INVALID, "company-reviewed source")
    if isinstance(object_result, Err):
        return object_result
    fields = _validated(
        object_result.value,
        POLICY_INVALID,
        required=frozenset({"source_id", "git_host", "repository"}),
    )
    if isinstance(fields, Err):
        return fields
    source_id = _string(fields.value["source_id"], POLICY_INVALID, "company source ID")
    host = _string(fields.value["git_host"], POLICY_INVALID, "company Git host")
    repository = _string(
        fields.value["repository"],
        POLICY_INVALID,
        "company repository",
    )
    if isinstance(source_id, Err):
        return source_id
    if isinstance(host, Err):
        return host
    if isinstance(repository, Err):
        return repository
    try:
        return Ok(CompanyReviewedSource(SourceId(source_id.value), host.value, repository.value))
    except ValueError as error:
        return _error(POLICY_INVALID, str(error))


def _company_reviewed_sources(value: JsonValue) -> Result[tuple[CompanyReviewedSource, ...]]:
    if not isinstance(value, JsonArray):
        return _error(POLICY_INVALID, "company_reviewed_sources must be an array")
    sources: list[CompanyReviewedSource] = []
    for item in value.items:
        parsed = _company_reviewed_source(item)
        if isinstance(parsed, Err):
            return parsed
        sources.append(parsed.value)
    ordered = tuple(sorted(set(sources)))
    if len(ordered) != len(sources):
        return _error(POLICY_INVALID, "company_reviewed_sources must not contain duplicates")
    return Ok(ordered)


def parse_organization_policy(data: bytes | str) -> Result[OrganizationPolicy]:
    document = _document(data, POLICY_INVALID)
    if isinstance(document, Err):
        return document
    fields = _validated(
        document.value,
        POLICY_INVALID,
        required=frozenset({"schema_version"}),
        optional=frozenset(
            {
                "recommended_sources",
                "required_sources",
                "allowed_git_hosts",
                "allowed_repository_prefixes",
                "allow_direct_sources",
                "minimum_trust_for_user_scope",
                "allowed_setup_capabilities",
                "allow_custom_setup_entrypoints",
                "company_reviewed_sources",
                "reporting",
            }
        ),
    )
    if isinstance(fields, Err):
        return fields
    version = _integer(fields.value["schema_version"], POLICY_INVALID, "schema_version")
    if isinstance(version, Err):
        return version
    if version.value != 1:
        return _error(POLICY_INVALID, f"unsupported schema_version {version.value}")
    recommended = _alias_array(
        fields.value.get("recommended_sources", JsonArray(())),
        POLICY_INVALID,
        "recommended_sources",
    )
    required = _alias_array(
        fields.value.get("required_sources", JsonArray(())), POLICY_INVALID, "required_sources"
    )
    hosts = _optional_strings(
        fields.value, "allowed_git_hosts", lambda raw: bool(_HOST_RE.fullmatch(raw))
    )
    prefixes = _optional_strings(
        fields.value,
        "allowed_repository_prefixes",
        lambda raw: (
            raw.endswith("/")
            and not raw.startswith("/")
            and posixpath.normpath(raw.removesuffix("/")) == raw.removesuffix("/")
            and all(part not in {"", ".", ".."} for part in raw.removesuffix("/").split("/"))
        ),
    )
    if isinstance(recommended, Err):
        return recommended
    if isinstance(required, Err):
        return required
    if isinstance(hosts, Err):
        return hosts
    if isinstance(prefixes, Err):
        return prefixes
    allow_direct: bool | None = None
    allow_custom: bool | None = None
    minimum_trust: str | None = None
    capabilities: tuple[Capability, ...] | None = None
    company_sources = _company_reviewed_sources(
        fields.value.get("company_reviewed_sources", JsonArray(()))
    )
    if isinstance(company_sources, Err):
        return company_sources
    if "allow_direct_sources" in fields.value:
        parsed_direct = _boolean(
            fields.value["allow_direct_sources"], POLICY_INVALID, "allow_direct_sources"
        )
        if isinstance(parsed_direct, Err):
            return parsed_direct
        allow_direct = parsed_direct.value
    if "allow_custom_setup_entrypoints" in fields.value:
        parsed_custom = _boolean(
            fields.value["allow_custom_setup_entrypoints"],
            POLICY_INVALID,
            "allow_custom_setup_entrypoints",
        )
        if isinstance(parsed_custom, Err):
            return parsed_custom
        allow_custom = parsed_custom.value
    if "minimum_trust_for_user_scope" in fields.value:
        parsed_trust = _string(
            fields.value["minimum_trust_for_user_scope"],
            POLICY_INVALID,
            "minimum_trust_for_user_scope",
        )
        if isinstance(parsed_trust, Err):
            return parsed_trust
        if parsed_trust.value not in TRUST_CLASSES:
            return _error(POLICY_INVALID, "minimum trust value is unsupported")
        minimum_trust = parsed_trust.value
    if "allowed_setup_capabilities" in fields.value:
        raw_capabilities = fields.value["allowed_setup_capabilities"]
        if not isinstance(raw_capabilities, JsonArray):
            return _error(POLICY_INVALID, "allowed_setup_capabilities must be an array")
        parsed_capabilities: list[Capability] = []
        for item in raw_capabilities.items:
            raw = _string(item, POLICY_INVALID, "allowed setup capability")
            if isinstance(raw, Err):
                return raw
            parsed_capability = parse_capability(raw.value)
            if isinstance(parsed_capability, Err):
                return parsed_capability
            parsed_capabilities.append(parsed_capability.value)
        capabilities = tuple(sorted(set(parsed_capabilities)))
    reporting = _ignored_reporting(
        fields.value.get("reporting", JsonObject(())), POLICY_INVALID, policy=True
    )
    if isinstance(reporting, Err):
        return reporting
    try:
        return Ok(
            OrganizationPolicy(
                1,
                recommended.value,
                required.value,
                hosts.value,
                prefixes.value,
                allow_direct,
                minimum_trust,
                capabilities,
                allow_custom,
                company_sources.value,
            )
        )
    except ValueError as error:
        return _error(POLICY_INVALID, str(error))


def organization_policy_bytes(policy: OrganizationPolicy) -> bytes:
    entries: list[tuple[str, JsonValue]] = [
        (
            "company_reviewed_sources",
            JsonArray(
                tuple(
                    JsonObject(
                        (
                            ("git_host", source.git_host),
                            ("repository", source.repository),
                            ("source_id", source.source_id.value),
                        )
                    )
                    for source in policy.company_reviewed_sources
                )
            ),
        ),
        (
            "recommended_sources",
            JsonArray(tuple(item.value for item in policy.recommended_sources)),
        ),
        ("required_sources", JsonArray(tuple(item.value for item in policy.required_sources))),
        ("schema_version", 1),
    ]
    optional_arrays = (
        ("allowed_git_hosts", policy.allowed_git_hosts),
        ("allowed_repository_prefixes", policy.allowed_repository_prefixes),
        ("allowed_setup_capabilities", policy.allowed_setup_capabilities),
    )
    for name, values in optional_arrays:
        if values is not None:
            entries.append((name, JsonArray(tuple(str(item) for item in values))))
    for name, value in (
        ("allow_direct_sources", policy.allow_direct_sources),
        ("minimum_trust_for_user_scope", policy.minimum_trust_for_user_scope),
        ("allow_custom_setup_entrypoints", policy.allow_custom_setup_entrypoints),
    ):
        if value is not None:
            entries.append((name, value))
    return canonical_json_bytes(JsonObject(tuple(entries)))
