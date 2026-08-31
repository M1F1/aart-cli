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
    InputId,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.identifiers import (
    ArtifactKind as IdentityKind,
)
from agent_artifacts.domain.inputs import (
    CliArgumentBinding,
    ConfigInput,
    EnvironmentBinding,
    FileBinding,
    InputGuidance,
    InputValidation,
    ObtainFrom,
    ProcessBinding,
    RuntimeInput,
    SecretInput,
    StdinBinding,
)
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.launch import LaunchContract, Transport
from agent_artifacts.domain.python_runtime import (
    PyProjectSpec,
    PythonDependencySpec,
    RequirementsFile,
    spec_descriptor_path,
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
#: What an author may say about how a value reaches the running artifact. The names are the
#: §91 vocabulary; what each one can actually deliver is decided once, by the launcher generator.
_INJECTIONS: dict[str, str] = {
    "environment": "variable",
    "cli-argument": "argument",
    "file": "path",
    "stdin": "",
}
#: Dependency descriptors this build can install, and the lock format each one implies. A resolver
#: with no backend behind it is refused rather than approximated: installing the loose project
#: instead of the lock would install versions nobody resolved.
_DEPENDENCY_KINDS: dict[str, str | None] = {"requirements": None, "pyproject": None, "uv": "uv"}
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
    contract: LaunchContract | None
    inputs: tuple[RuntimeInput, ...]
    dependencies: PythonDependencySpec | None
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


def _ordered_strings(value: JsonValue, label: str, *, path: str) -> Result[tuple[str, ...]]:
    """A string array kept as written. Unlike `_strings`, order and repetition survive.

    Both matter for an argument vector: `--verbose --verbose` is not `--verbose`, and the position
    of a flag relative to a positional argument is the difference between two commands.
    """

    if not isinstance(value, JsonArray):
        return _error(AUTHOR_MANIFEST_INVALID, f"{label} must be an array of strings", path=path)
    result: list[str] = []
    for item in value.items:
        parsed = _string(item, f"{label} item", path=path)
        if isinstance(parsed, Err):
            return parsed
        result.append(parsed.value)
    return Ok(tuple(result))


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


def _built(build, label: str, *, path: str) -> Result:
    """Build a domain value, reporting what it refused rather than raising out of the parser.

    The rules a runtime input has to satisfy -- a secret with no value field, guidance with no
    plausible example credential, an environment variable that is one -- already live in the
    domain. Restating them here would give a manifest two sets of rules that could disagree.
    """

    try:
        return Ok(build())
    except ValueError as error:
        return _error(AUTHOR_MANIFEST_INVALID, f"{label} is invalid: {error}", path=path)


def _parse_obtain_from(value: JsonValue, *, path: str) -> Result[ObtainFrom]:
    parsed = _object(value, "help.obtain_from", path=path)
    if isinstance(parsed, Err):
        return parsed
    fields = _fields(
        parsed.value,
        required=frozenset({"label", "url"}),
        path=path,
        label="help.obtain_from",
        extensions=True,
    )
    if isinstance(fields, Err):
        return fields
    label = _string(fields.value["label"], "help.obtain_from.label", path=path)
    url = _string(fields.value["url"], "help.obtain_from.url", path=path)
    for item in (label, url):
        if isinstance(item, Err):
            return item
    assert isinstance(label, Ok) and isinstance(url, Ok)
    return _built(lambda: ObtainFrom(label.value, url.value), "help.obtain_from", path=path)


def _parse_guidance(value: JsonValue, *, path: str) -> Result[InputGuidance]:
    parsed = _object(value, "help", path=path)
    if isinstance(parsed, Err):
        return parsed
    fields = _fields(
        parsed.value,
        required=frozenset({"label"}),
        optional=frozenset(
            {"description", "example", "format_hint", "obtain_from", "validation_hint"}
        ),
        path=path,
        label="help",
        extensions=True,
    )
    if isinstance(fields, Err):
        return fields
    strings: dict[str, str | None] = {}
    for name in ("label", "description", "example", "format_hint", "validation_hint"):
        if name not in fields.value:
            strings[name] = None
            continue
        parsed_string = _string(fields.value[name], f"help.{name}", path=path)
        if isinstance(parsed_string, Err):
            return parsed_string
        strings[name] = parsed_string.value
    obtain: ObtainFrom | None = None
    if "obtain_from" in fields.value:
        parsed_obtain = _parse_obtain_from(fields.value["obtain_from"], path=path)
        if isinstance(parsed_obtain, Err):
            return parsed_obtain
        obtain = parsed_obtain.value
    return _built(
        lambda: InputGuidance(
            str(strings["label"]),
            strings["description"] or "",
            strings["example"],
            strings["format_hint"],
            obtain,
            strings["validation_hint"] or "",
        ),
        "help",
        path=path,
    )


def _parse_validation(value: JsonValue, *, path: str) -> Result[InputValidation]:
    parsed = _nested_type(
        value,
        "validation",
        path=path,
        optional=frozenset({"pattern", "allowed_hosts", "message"}),
    )
    if isinstance(parsed, Err):
        return parsed
    kind, fields, _object_value = parsed.value
    pattern: str | None = None
    if "pattern" in fields:
        parsed_pattern = _string(fields["pattern"], "validation.pattern", path=path)
        if isinstance(parsed_pattern, Err):
            return parsed_pattern
        pattern = parsed_pattern.value
    hosts: tuple[str, ...] = ()
    if "allowed_hosts" in fields:
        parsed_hosts = _strings(
            fields["allowed_hosts"], "validation.allowed_hosts", path=path, allow_empty=False
        )
        if isinstance(parsed_hosts, Err):
            return parsed_hosts
        hosts = parsed_hosts.value
    message = ""
    if "message" in fields:
        parsed_message = _string(fields["message"], "validation.message", path=path)
        if isinstance(parsed_message, Err):
            return parsed_message
        message = parsed_message.value
    return _built(lambda: InputValidation(kind, pattern, hosts, message), "validation", path=path)


def _parse_injection(value: JsonValue, *, path: str) -> Result[ProcessBinding]:
    """Which delivery an author asked for, refused by name when this build has no such delivery.

    The type is checked before the fields are, so an author who names an injection AART cannot
    perform is told that, rather than being told about a field that only looks unknown because
    the injection is.
    """

    parsed = _object(value, "inject", path=path)
    if isinstance(parsed, Err):
        return parsed
    kind = parsed.value.get("type")
    if not isinstance(kind, str) or kind not in _INJECTIONS:
        named = f" {kind!r}" if isinstance(kind, str) else ""
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"inject.type{named} is not an injection this build can deliver",
            path=path,
        )
    field = _INJECTIONS[kind]
    fields = _fields(
        parsed.value,
        required=frozenset({"type"} | ({field} if field else set())),
        path=path,
        label=f"inject.type {kind!r}",
        extensions=True,
    )
    if isinstance(fields, Err):
        return fields
    if not field:
        return _built(StdinBinding, "inject", path=path)
    parsed_field = _string(fields.value[field], f"inject.{field}", path=path)
    if isinstance(parsed_field, Err):
        return parsed_field
    setting = parsed_field.value
    builders = {
        "environment": lambda: EnvironmentBinding(setting),
        "cli-argument": lambda: CliArgumentBinding(setting),
        "file": lambda: FileBinding(setting),
    }
    return _built(builders[kind], f"inject.{field}", path=path)


def _parse_input(value: JsonValue, *, path: str) -> Result[RuntimeInput]:
    parsed = _object(value, "input", path=path)
    if isinstance(parsed, Err):
        return parsed
    kind_value = parsed.value.get("kind")
    if kind_value not in ("secret", "config"):
        return _error(
            AUTHOR_MANIFEST_INVALID,
            "every input declares kind 'secret' or 'config'",
            path=path,
        )
    secret = kind_value == "secret"
    # A secret takes no `default` and no `value`: §91 keeps the confidential class free of any
    # field a real credential could be written into, and the omission is the enforcement.
    optional = frozenset({"required", "help"}) | (
        frozenset() if secret else frozenset({"default", "validation"})
    )
    fields = _fields(
        parsed.value,
        required=frozenset({"id", "kind", "inject"}),
        optional=optional,
        path=path,
        label=f"{kind_value} input",
        extensions=True,
    )
    if isinstance(fields, Err):
        return fields
    identifier = _string(fields.value["id"], "input.id", path=path)
    if isinstance(identifier, Err):
        return identifier
    binding = _parse_injection(fields.value["inject"], path=path)
    if isinstance(binding, Err):
        return binding
    required = True
    if "required" in fields.value:
        if not isinstance(fields.value["required"], bool):
            return _error(
                AUTHOR_MANIFEST_INVALID,
                f"input {identifier.value!r} required must be true or false",
                path=path,
            )
        required = bool(fields.value["required"])
    guidance: InputGuidance | None = None
    if "help" in fields.value:
        parsed_guidance = _parse_guidance(fields.value["help"], path=path)
        if isinstance(parsed_guidance, Err):
            return parsed_guidance
        guidance = parsed_guidance.value
    label = f"input {identifier.value!r}"
    if secret:
        return _built(
            lambda: SecretInput(InputId(identifier.value), binding.value, required, guidance),
            label,
            path=path,
        )
    validation: InputValidation | None = None
    if "validation" in fields.value:
        parsed_validation = _parse_validation(fields.value["validation"], path=path)
        if isinstance(parsed_validation, Err):
            return parsed_validation
        validation = parsed_validation.value
    default: str | None = None
    if "default" in fields.value:
        parsed_default = _string(fields.value["default"], "input.default", path=path)
        if isinstance(parsed_default, Err):
            return parsed_default
        default = parsed_default.value
    return _built(
        lambda: ConfigInput(
            InputId(identifier.value),
            binding.value,
            required,
            validation,
            guidance,
            default,
        ),
        label,
        path=path,
    )


def _parse_inputs(value: JsonValue, *, path: str) -> Result[tuple[RuntimeInput, ...]]:
    """Declaration order is kept: it is the order somebody is asked for these values."""

    if not isinstance(value, JsonArray):
        return _error(AUTHOR_MANIFEST_INVALID, "inputs must be an array", path=path)
    inputs: list[RuntimeInput] = []
    seen: set[str] = set()
    for item in value.items:
        parsed = _parse_input(item, path=path)
        if isinstance(parsed, Err):
            return parsed
        identifier = str(parsed.value.id)
        if identifier in seen:
            return _error(
                AUTHOR_MANIFEST_INVALID,
                f"input {identifier!r} is declared more than once",
                path=path,
            )
        seen.add(identifier)
        inputs.append(parsed.value)
    return Ok(tuple(inputs))


def _parse_dependencies(value: JsonValue, *, path: str) -> Result[PythonDependencySpec]:
    """Which descriptor an artifact points at, and the lock its resolver wrote, if any.

    §108: AART reuses the Python ecosystem's descriptors rather than inventing one. The type is
    checked first here too, so a resolver this build has no backend for is refused by name instead
    of being approximated by installing the loose project the lock was written to prevent.
    """

    parsed = _object(value, "python.dependencies", path=path)
    if isinstance(parsed, Err):
        return parsed
    kind = parsed.value.get("type")
    if not isinstance(kind, str) or kind not in _DEPENDENCY_KINDS:
        named = f" {kind!r}" if isinstance(kind, str) else ""
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"python.dependencies.type{named} names a resolver no installer here can read",
            path=path,
        )
    lock_format = _DEPENDENCY_KINDS[kind]
    if kind == "requirements":
        required = frozenset({"type", "path"})
    elif lock_format is None:
        required = frozenset({"type", "pyproject"})
    else:
        required = frozenset({"type", "pyproject", "lock"})
    fields = _fields(
        parsed.value,
        required=required,
        path=path,
        label=f"a {kind} descriptor",
        extensions=True,
    )
    if isinstance(fields, Err):
        return fields
    named_paths = {}
    for name in required - {"type"}:
        parsed_path = _string(fields.value[name], f"python.dependencies.{name}", path=path)
        if isinstance(parsed_path, Err):
            return parsed_path
        named_paths[name] = parsed_path.value
    if kind == "requirements":
        return _built(
            lambda: RequirementsFile(named_paths["path"]), "python.dependencies", path=path
        )
    return _built(
        lambda: PyProjectSpec(named_paths["pyproject"], named_paths.get("lock"), lock_format),
        "python.dependencies",
        path=path,
    )


def _parse_python(value: JsonValue, *, path: str) -> Result[PythonDependencySpec]:
    parsed = _object(value, "python", path=path)
    if isinstance(parsed, Err):
        return parsed
    fields = _fields(
        parsed.value,
        required=frozenset({"dependencies"}),
        path=path,
        label="python",
        extensions=True,
    )
    if isinstance(fields, Err):
        return fields
    return _parse_dependencies(fields.value["dependencies"], path=path)


def _parse_launch(
    value: JsonValue, *, path: str
) -> Result[tuple[str, str | None, tuple[str, ...]]]:
    """The launch declaration: what starts it, which file, and the arguments it is always given."""

    parsed = _nested_type(
        value,
        "launch",
        path=path,
        optional=frozenset({"entrypoint", "path", "arguments"}),
    )
    if isinstance(parsed, Err):
        return parsed
    kind, fields, _object_value = parsed.value
    located = set(fields) & {"entrypoint", "path"}
    if len(located) > 1:
        return _error(
            AUTHOR_MANIFEST_INVALID,
            "launch must declare only one of entrypoint or path",
            path=path,
        )
    entrypoint: str | None = None
    if located:
        field = next(iter(located))
        raw = _string(fields[field], f"launch.{field}", path=path)
        if isinstance(raw, Err):
            return raw
        entrypoint = raw.value
    arguments: tuple[str, ...] = ()
    if "arguments" in fields:
        parsed_arguments = _ordered_strings(fields["arguments"], "launch.arguments", path=path)
        if isinstance(parsed_arguments, Err):
            return parsed_arguments
        arguments = parsed_arguments.value
    return Ok((kind, entrypoint, arguments))


def _launch_contract(
    entrypoint: str | None,
    transport: str | None,
    arguments: tuple[str, ...],
    *,
    path: str,
) -> Result[LaunchContract | None]:
    """The contract an artifact is started by, or nothing when it declares no way to start.

    Both directions of a manifest come through here, so what the compiler wrote and what an
    installer later reads back are the same value built by the same rules.
    """

    if entrypoint is None:
        return Ok(None)
    if transport is not None and transport not in {item.value for item in Transport}:
        return _error(
            AUTHOR_MANIFEST_INVALID,
            f"transport.type {transport!r} is not a transport this build can start",
            path=path,
        )
    chosen = Transport.STDIO if transport is None else Transport(transport)
    return _built(lambda: LaunchContract(entrypoint, chosen, arguments), "launch", path=path)


def describe_installation(manifest: AuthorManifest) -> InstallDescription:
    """What this manifest says an installation of the artifact needs.

    Total, because a manifest that parsed is a manifest whose contract was already built: the
    failure a launch declaration can have is reported when the manifest is read, not later when
    somebody is halfway through an install.
    """

    if not isinstance(manifest, AuthorManifest):
        raise ValueError("an install description is described from an author manifest")
    return InstallDescription(
        manifest.contract,
        manifest.runtime,
        manifest.runtime_version,
        manifest.inputs,
        manifest.dependencies,
    )


def read_install_description(intent: JsonValue, *, path: str) -> Result[InstallDescription]:
    """The install description a compiled package still carries, read from `aart.authoring`.

    The machine doing an installation has the package, not the author's repository, so what an
    install needs has to survive compilation and be readable back out of `artifact.json`. This
    reads it with the same parsers that wrote it -- a second grammar for reading what the first one
    wrote works until an author uses a field the reader forgot.

    Keys this function does not need are ignored rather than refused. The extension was written by
    a compiler that had already validated the whole manifest, and a reader that refused an
    unfamiliar key would make every later manifest field a breaking change for old installations.
    """

    parsed = _object(intent, "aart.authoring", path=path)
    if isinstance(parsed, Err):
        return parsed
    fields = dict(parsed.value.entries)

    transport: str | None = None
    if "transport" in fields:
        parsed_transport = _nested_type(fields["transport"], "transport", path=path)
        if isinstance(parsed_transport, Err):
            return parsed_transport
        transport = parsed_transport.value[0]

    runtime: str | None = None
    runtime_version: str | None = None
    if "runtime" in fields:
        parsed_runtime = _nested_type(
            fields["runtime"], "runtime", path=path, optional=frozenset({"version"})
        )
        if isinstance(parsed_runtime, Err):
            return parsed_runtime
        runtime, runtime_fields, _runtime_object = parsed_runtime.value
        if "version" in runtime_fields:
            parsed_version = _string(runtime_fields["version"], "runtime.version", path=path)
            if isinstance(parsed_version, Err):
                return parsed_version
            runtime_version = parsed_version.value

    entrypoint: str | None = None
    arguments: tuple[str, ...] = ()
    if "launch" in fields:
        parsed_launch = _parse_launch(fields["launch"], path=path)
        if isinstance(parsed_launch, Err):
            return parsed_launch
        _kind, entrypoint, arguments = parsed_launch.value
    contract = _launch_contract(entrypoint, transport, arguments, path=path)
    if isinstance(contract, Err):
        return contract

    inputs: tuple[RuntimeInput, ...] = ()
    if "inputs" in fields:
        parsed_inputs = _parse_inputs(fields["inputs"], path=path)
        if isinstance(parsed_inputs, Err):
            return parsed_inputs
        inputs = parsed_inputs.value

    dependencies: PythonDependencySpec | None = None
    if "python" in fields:
        parsed_python = _parse_python(fields["python"], path=path)
        if isinstance(parsed_python, Err):
            return parsed_python
        dependencies = parsed_python.value

    return _built(
        lambda: InstallDescription(contract.value, runtime, runtime_version, inputs, dependencies),
        "the install description",
        path=path,
    )


def _declared_payload_files(manifest: AuthorManifest) -> tuple[str, ...]:
    """Every payload file the manifest points at and an installation would then need.

    §108 requires the descriptor and its lock to ship in the canonical payload: an artifact whose
    dependency list lives only in the source repository is installable today and uninstallable
    tomorrow. The entrypoint is here for the same reason -- a launcher that names a file the
    payload does not carry starts nothing.
    """

    files: list[str] = []
    if manifest.entrypoint is not None:
        files.append(str(manifest.entrypoint))
    spec = manifest.dependencies
    if spec is not None:
        files.append(spec_descriptor_path(spec))
        if isinstance(spec, PyProjectSpec) and spec.lock is not None:
            files.append(spec.lock)
    return tuple(files)


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
                "python",
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
    launch_arguments: tuple[str, ...] = ()
    if "launch" in root:
        parsed_launch = _parse_launch(root["launch"], path=raw_path)
        if isinstance(parsed_launch, Err):
            return parsed_launch
        launch, raw_entrypoint, launch_arguments = parsed_launch.value
        launch_object = cast(JsonObject, root["launch"])
        if raw_entrypoint is not None:
            parsed_entrypoint = parse_relative_path(
                raw_entrypoint,
                location=SourceLocation(path=raw_path, pointer="/launch/entrypoint"),
            )
            if isinstance(parsed_entrypoint, Err):
                return _error(
                    AUTHOR_MANIFEST_INVALID,
                    "launch entrypoint must be a safe path below the manifest root",
                    path=raw_path,
                )
            entrypoint = parsed_entrypoint.value

    contract = _launch_contract(
        None if entrypoint is None else str(entrypoint),
        transport,
        launch_arguments,
        path=raw_path,
    )
    if isinstance(contract, Err):
        return contract

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

    inputs: tuple[RuntimeInput, ...] = ()
    if "inputs" in root:
        parsed_inputs = _parse_inputs(root["inputs"], path=raw_path)
        if isinstance(parsed_inputs, Err):
            return parsed_inputs
        inputs = parsed_inputs.value

    dependencies: PythonDependencySpec | None = None
    if "python" in root:
        parsed_python = _parse_python(root["python"], path=raw_path)
        if isinstance(parsed_python, Err):
            return parsed_python
        dependencies = parsed_python.value

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
    # Kept as declared rather than as re-serialized domain values: what an artifact asks for is
    # part of what the artifact is, so it belongs byte-for-byte in the input digest.
    if inputs:
        intent_entries.append(("inputs", root["inputs"]))
    if dependencies is not None:
        intent_entries.append(("python", root["python"]))

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
            contract.value,
            inputs,
            dependencies,
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
    shipped = {relative for relative, _entry in selected}
    for needed in _declared_payload_files(manifest):
        if needed not in shipped:
            return _error(
                AUTHOR_PAYLOAD_INVALID,
                f"the manifest names {needed!r}, which the payload does not include",
                path=str(source_manifest.path),
            )
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
