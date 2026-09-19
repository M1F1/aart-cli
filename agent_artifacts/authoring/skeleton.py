"""The `aart author init` skeleton: every field the parser accepts, in one document.

The maintainer's requirement is that an author starts from the full accepted surface and deletes
down to what they need, rather than discovering fields by reading `protocol/authoring.py`. So the
skeleton carries every optional block, and the blocks that are not required are written out as
comments with a one-line explanation above them. `parse_yaml` strips comments, so the file parses
whether or not anything has been uncommented.

The risk this creates is a generator that drifts from the parser it mirrors. Nothing here defends
against that; `tests/author_skeleton_test.py` does, by reading the parser's own source and failing
until every name it finds appears here (CP-26.5 §1.5, D-327).

Three comment prefixes, because they mean three different things and a reader has to be able to
tell them apart:

* ``# `` -- a line of the document that is simply not enabled. Uncommenting every one of these
  yields exactly :attr:`AuthorSkeleton.full`, which parses.
* ``## `` -- prose. Never YAML.
* ``#? `` -- an alternative to a line above it, not an addition. Two of these uncommented together
  do not parse, which is why they are not part of ``full``.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_artifacts.domain.diagnostics import Diagnostic, Severity
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.authoring import DiscoveredAuthorManifest, parse_author_manifest
from agent_artifacts.protocol.codes import AUTHOR_MANIFEST_INVALID
from agent_artifacts.protocol.json import JsonArray, JsonObject, JsonValue
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.protocol.yaml import emit_yaml

PROSE_PREFIX = "## "
COMMENTED_YAML_PREFIX = "# "
ALTERNATIVE_PREFIX = "#? "

#: Kinds this build generates a skeleton for. The parser knows five; steps 9 and 12 add the rest.
GENERATED_KINDS = ("mcp",)

#: Where a generated manifest says it came from, for the diagnostics of the verification below.
SKELETON_MANIFEST_NAME = "aart.yaml"


@dataclass(frozen=True, slots=True)
class AuthorSkeleton:
    """One generated authoring workspace, as text rather than as files on a disk."""

    kind: str
    name: str
    #: The `aart.yaml` to write: `live` plus every other block as commented-out YAML.
    manifest: str
    #: What `manifest` parses to with its comments stripped.
    live: JsonObject
    #: The same document with every commented block enabled. Parses; see the module docstring.
    full: JsonObject
    payload: tuple[tuple[str, str], ...]


def _error(message: str) -> Err:
    return Err((Diagnostic(AUTHOR_MANIFEST_INVALID, Severity.ERROR, message),))


def _object(*entries: tuple[str, JsonValue]) -> JsonObject:
    return JsonObject(entries)


def _strings(*values: str) -> JsonArray:
    return JsonArray(tuple(values))


def _humanized(name: str) -> str:
    return name.replace("-", " ").capitalize()


def _mcp_document(name: str) -> tuple[JsonObject, tuple[str, ...]]:
    """Every block an `mcp` manifest may carry, live, plus the top-level keys that are optional.

    `mcp` is stricter than the schema: `parse_author_manifest` refuses it without stdio transport
    and a `python` or `external-script` launch, so those blocks are required *here* even though the
    root field set calls them optional. What the parser demands is what this document keeps live.
    """

    entrypoint = "payload/server.py"
    document = _object(
        ("schema", "aart.dev/mcp/v1"),
        (
            "artifact",
            _object(
                ("kind", "mcp"),
                ("name", name),
                ("summary", f"{_humanized(name)} MCP server."),
                ("version", "0.1.0"),
            ),
        ),
        (
            "payload",
            _object(
                ("exclude", _strings("payload/**/__pycache__/**")),
                ("include", _strings("payload/**")),
            ),
        ),
        ("transport", _object(("type", "stdio"))),
        ("runtime", _object(("type", "python"), ("version", "3.11"))),
        (
            "launch",
            _object(
                ("arguments", _strings("--stdio")),
                ("entrypoint", entrypoint),
                ("type", "python"),
            ),
        ),
        (
            "compatibility",
            _object(
                ("harnesses", _strings("claude-code")),
                ("platforms", _strings("darwin", "linux")),
            ),
        ),
        ("inputs", _inputs()),
        (
            "python",
            _object(
                (
                    "dependencies",
                    _object(("path", "payload/requirements.txt"), ("type", "requirements")),
                ),
            ),
        ),
    )
    # `summary`, `exclude` and `arguments` are optional inside blocks the parser requires, so they
    # are commented individually rather than with their parent.
    optional = ("compatibility", "inputs", "python")
    return document, optional


def _inputs() -> JsonArray:
    """Three inputs, because one cannot carry every field the parser accepts.

    A secret takes no `default` and no `validation` -- §91 keeps the confidential class free of any
    field a credential could be written into -- so the fields that only a config input has need a
    config input to sit in. And a validation is `pattern` or `url`, never both: `allowed_hosts`
    belongs to one and `pattern` to the other, so covering both takes two.
    """

    return JsonArray(
        (
            _object(
                ("help", _guidance()),
                ("id", "api-token"),
                ("inject", _object(("type", "environment"), ("variable", "SERVICE_API_TOKEN"))),
                ("kind", "secret"),
                ("required", True),
            ),
            _object(
                ("default", "https://example.invalid"),
                (
                    "help",
                    _object(
                        ("description", "Where this server reaches its provider."),
                        ("example", "https://example.invalid"),
                        ("label", "Base URL"),
                    ),
                ),
                ("id", "base-url"),
                ("inject", _object(("type", "environment"), ("variable", "SERVICE_BASE_URL"))),
                ("kind", "config"),
                ("required", False),
                (
                    "validation",
                    _object(
                        ("allowed_hosts", _strings("example.invalid")),
                        ("message", "The base URL must be on an allowed host."),
                        ("type", "url"),
                    ),
                ),
            ),
            _object(
                ("default", "default-project"),
                ("id", "project-slug"),
                ("inject", _object(("type", "cli-argument"), ("argument", "--project"))),
                ("kind", "config"),
                ("required", False),
                (
                    "validation",
                    _object(
                        ("message", "The project slug is lowercase letters, digits and hyphens."),
                        ("pattern", "^[a-z0-9-]+$"),
                        ("type", "pattern"),
                    ),
                ),
            ),
        )
    )


def _guidance() -> JsonObject:
    """What a person is told when AART asks for a secret.

    No `example`: §91 keeps the confidential class free of any field a real credential could be
    written into, and `parse_author_manifest` refuses a secret whose guidance carries one. The
    `example` field is covered by the config input below, where a sample value is just a sample.
    """

    return _object(
        ("description", "The token this server authenticates to its provider with."),
        ("format_hint", "A provider-issued access token, on one line."),
        ("label", "API token"),
        (
            "obtain_from",
            _object(
                ("label", "Provider settings"),
                ("url", "https://example.invalid/settings/tokens"),
            ),
        ),
        ("validation_hint", "Paste the token without surrounding quotes or whitespace."),
    )


#: Optional positions inside a block the parser requires: each is disabled on its own, because its
#: parent has to stay live.
_NESTED_OPTIONAL: tuple[tuple[str, str], ...] = (
    ("artifact", "summary"),
    ("launch", "arguments"),
    ("payload", "exclude"),
)

#: One line per optional position: what it is for, not what it contains.
_EXPLANATIONS: dict[str, str] = {
    "arguments": "Extra arguments the server is started with, after the entrypoint.",
    "compatibility": "Narrow the artifact to the harnesses and platforms it actually runs on.",
    "exclude": "Payload files to leave out of the package, applied after `include`.",
    "inputs": "Values AART collects from the installer and injects when the server runs.",
    "python": "How the payload's Python dependencies are resolved at install time.",
    "summary": "One line shown wherever the artifact is listed. Derived from the name if absent.",
}

#: Fields that cannot be live beside one that is, offered under the line each replaces. Two of
#: these uncommented together do not parse, which is why they are not part of `full`.
_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "python": (
        "## Or resolve from a project file instead, with `type: uv` when you ship a uv lock:",
        "#?   dependencies:",
        "#?     type: pyproject",
        "#?     pyproject: payload/pyproject.toml",
        "#?     lock: payload/uv.lock",
    ),
    "inputs": (
        "## An injection other than `environment` names its own field in place of `variable`.",
        "## Block form, because this YAML subset has no flow mappings -- enable one, not all three:",
        "#?     inject:",
        "#?       type: cli-argument",
        "#?       argument: --project",
        "#?     inject:",
        "#?       type: file",
        "#?       path: config/token",
        "#?     inject:",
        "#?       type: stdin",
    ),
}

#: Root keys `parse_author_manifest` accepts and builds nothing from. There is no shape to
#: generate for them, so they are named rather than invented.
_ACCEPTED_UNREAD: tuple[str, ...] = ("credentials", "install", "requirements")

_UNREAD_NOTE: tuple[str, ...] = (
    "## `parse_author_manifest` accepts these three at the top level and builds nothing from",
    "## them, so `null` is the whole of what this build would do with a value you wrote here:",
    *(f"#? {key}: null" for key in _ACCEPTED_UNREAD),
)


def _disabled(key: str, value: JsonValue) -> Result[tuple[str, ...]]:
    """One optional block as the lines it would occupy, so what is commented is the document.

    The text is produced by the emitter from the value itself rather than written out here, which
    is what makes `uncomment everything` yield exactly `full` instead of something that resembles
    it.
    """

    emitted = emit_yaml(_object((key, value)))
    if isinstance(emitted, Err):
        return emitted
    lines = [f"## {_EXPLANATIONS[key]}", *emitted.value.splitlines()]
    lines.extend(_ALTERNATIVES.get(key, ()))
    return Ok(tuple(lines))


def _without(document: JsonObject, *keys: str) -> JsonObject:
    return JsonObject(tuple(entry for entry in document.entries if entry[0] not in keys))


def _live_document(full: JsonObject, optional: tuple[str, ...]) -> JsonObject:
    live = _without(full, *optional)
    entries: list[tuple[str, JsonValue]] = []
    for key, value in live.entries:
        nested = tuple(field for owner, field in _NESTED_OPTIONAL if owner == key)
        if nested and isinstance(value, JsonObject):
            entries.append((key, _without(value, *nested)))
            continue
        entries.append((key, value))
    return JsonObject(tuple(entries))


def _anchored(
    live: JsonObject,
    full: JsonObject,
    optional: tuple[str, ...],
) -> Result[tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]]:
    """Where each disabled block goes: above the next live key, or below the block it ends in.

    Keys are written in one order, so a disabled block sits above the first live key that sorts
    after it. One that sorts after every live key in its mapping -- `artifact.summary` after
    `version` -- has no such key, and closes the block instead.
    """

    comments: dict[str, tuple[str, ...]] = {}
    trailing: dict[str, tuple[str, ...]] = {}

    def place(container: str, keys: tuple[str, ...], blocks: tuple[tuple[str, JsonValue], ...]):
        for key, value in blocks:
            rendered = _disabled(key, value)
            if isinstance(rendered, Err):
                return rendered
            following = [live_key for live_key in keys if live_key > key]
            if following:
                position = following[0] if not container else f"{container}.{following[0]}"
                comments[position] = (*comments.get(position, ()), *rendered.value)
            else:
                trailing[container] = (*trailing.get(container, ()), *rendered.value)
        return None

    failed = place(
        "",
        live.keys(),
        tuple((key, value) for key, value in full.entries if key in optional),
    )
    if failed is not None:
        return failed
    for owner, field in _NESTED_OPTIONAL:
        parent = full.get(owner)
        current = live.get(owner)
        if not isinstance(parent, JsonObject) or not isinstance(current, JsonObject):
            continue
        value = parent.get(field)
        if value is None:
            continue
        failed = place(owner, current.keys(), ((field, value),))
        if failed is not None:
            return failed
    return Ok((comments, trailing))


def author_skeleton(kind: str, name: str) -> Result[AuthorSkeleton]:
    """The `aart.yaml` and payload one `aart author init` writes, as text.

    Refuses before producing anything when the kind is not one this build generates or the name is
    not the slug `artifact.name` requires: a skeleton the parser would reject is worse than none,
    because the author's first check of it would blame their own edits for the refusal.
    """

    if kind not in GENERATED_KINDS:
        offered = ", ".join(GENERATED_KINDS)
        return _error(f"this build generates no {kind!r} skeleton yet; it generates {offered}")
    full, optional = _mcp_document(name)
    live = _live_document(full, optional)
    anchored = _anchored(live, full, optional)
    if isinstance(anchored, Err):
        return anchored
    comments, trailing = anchored.value
    header = (
        f"## {_humanized(name)}: an AART {kind} artifact.",
        "## Every field this build accepts is here. Disabled lines begin `# `; `##` is a note and",
        "## `#?` is an alternative to the line above it, not an addition. Delete what you do",
        "## not need and uncomment what you do.",
    )
    trailing[""] = (*trailing.get("", ()), *_UNREAD_NOTE)
    emitted = emit_yaml(live, comments={"": header, **comments}, trailing=trailing)
    if isinstance(emitted, Err):
        return emitted
    accepted = _verified(emitted.value)
    if isinstance(accepted, Err):
        return accepted
    return Ok(AuthorSkeleton(kind, name, emitted.value, live, full, _mcp_payload(full)))


def _verified(manifest: str) -> Result[None]:
    """The parser's own verdict on the generated text, before a file is offered to anybody.

    The name is the reason this exists. `artifact.name` has a rule, and a copy of that rule here
    would be one more thing to drift -- so the check is the parser reading the document AART would
    have written, which also catches an emitter that stopped producing what the parser reads.
    """

    path = parse_relative_path(SKELETON_MANIFEST_NAME)
    if isinstance(path, Err):  # pragma: no cover - a literal filename is always relative
        return path
    parsed = parse_author_manifest(DiscoveredAuthorManifest(path.value, manifest.encode()))
    if isinstance(parsed, Err):
        return parsed
    return Ok(None)


def _mcp_payload(full: JsonObject) -> tuple[tuple[str, str], ...]:
    """A payload the generated manifest actually describes: the entrypoint it declares, and a
    requirements file the dependency descriptor names."""

    launch = full.get("launch")
    assert isinstance(launch, JsonObject)
    entrypoint = launch.get("entrypoint")
    assert isinstance(entrypoint, str)
    return (
        (
            entrypoint,
            '"""An MCP server over stdio. Replace this with the real one."""\n'
            "\n"
            "\n"
            "def main() -> None:\n"
            '    raise SystemExit("this MCP server has not been written yet")\n'
            "\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    main()\n",
        ),
        ("payload/requirements.txt", "# One pinned requirement per line.\n"),
    )
