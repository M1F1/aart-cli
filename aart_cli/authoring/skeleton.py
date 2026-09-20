"""The `aart-cli author init` skeleton: every field the parser accepts, in one document.

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

import json
from collections.abc import Callable
from dataclasses import dataclass

from aart_cli.domain.diagnostics import Diagnostic, Severity
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.authoring import DiscoveredAuthorManifest, parse_author_manifest
from aart_cli.protocol.codes import AUTHOR_MANIFEST_INVALID
from aart_cli.protocol.json import JsonArray, JsonObject, JsonValue
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.protocol.yaml import emit_yaml

PROSE_PREFIX = "## "
COMMENTED_YAML_PREFIX = "# "
ALTERNATIVE_PREFIX = "#? "

#: Kinds this build generates a skeleton for: all five the parser accepts. Derived from the
#: blueprints at the foot of this module, so registering one is the whole of adding a kind.
GENERATED_KINDS: tuple[str, ...]

#: Where a generated manifest says it came from, for the diagnostics of the verification below.
SKELETON_MANIFEST_NAME = "aart-cli.yaml"

#: A payload path is relative to the manifest's own directory. The compiler places the author's
#: files under the package's `payload/` itself, so a `payload/` written here would arrive as
#: `payload/payload/`: the shipped example in `docs/examples/author-source` is the shape.
_REQUIREMENTS = "requirements.txt"


@dataclass(frozen=True, slots=True)
class PayloadFile:
    """One generated payload file. `executable` because a hook's script has to be.

    A hook declares `command: ${SCRIPT_DIR}/run.sh`, and `package_hook` refuses a package whose
    script is not executable -- "the harness could not run it". Compilation does not catch it, so
    an `init` that wrote the file unexecutable would hand the author a workspace that compiles,
    promotes and then refuses to install.
    """

    path: str
    content: str
    executable: bool = False


@dataclass(frozen=True, slots=True)
class AuthorSkeleton:
    """One generated authoring workspace, as text rather than as files on a disk."""

    kind: str
    name: str
    #: The `aart-cli.yaml` to write: `live` plus every other block as commented-out YAML.
    manifest: str
    #: What `manifest` parses to with its comments stripped.
    live: JsonObject
    #: The same document with every commented block enabled. Parses; see the module docstring.
    full: JsonObject
    payload: tuple[PayloadFile, ...]


@dataclass(frozen=True, slots=True)
class _Blueprint:
    """One kind's document, and which parts of it the generator writes out disabled.

    A kind is not a parameter on one document. An `mcp` is launched and a `skill` is copied into
    place, so what each one may meaningfully declare differs, and a single template with flags
    would have to encode that difference anyway -- less legibly, and in a place no author reads.
    """

    kind: str
    #: Every block this kind's skeleton carries, live.
    document: JsonObject
    #: Top-level keys written out disabled rather than live.
    optional: tuple[str, ...]
    #: `(owner, field)` positions disabled inside a block that has to stay live.
    nested_optional: tuple[tuple[str, str], ...]
    #: Lines closing the document: what the parser accepts here that this kind does not generate.
    notes: tuple[str, ...]
    payload: tuple[PayloadFile, ...]


def _error(message: str) -> Err:
    return Err((Diagnostic(AUTHOR_MANIFEST_INVALID, Severity.ERROR, message),))


def _object(*entries: tuple[str, JsonValue]) -> JsonObject:
    return JsonObject(entries)


def _strings(*values: str) -> JsonArray:
    return JsonArray(tuple(values))


def _humanized(name: str) -> str:
    return name.replace("-", " ").capitalize()


def _mcp_blueprint(name: str) -> _Blueprint:
    """Every block an `mcp` manifest may carry, live, plus the top-level keys that are optional.

    `mcp` is stricter than the schema: `parse_author_manifest` refuses it without stdio transport
    and a `python` or `external-script` launch, so those blocks are required *here* even though the
    root field set calls them optional. What the parser demands is what this document keeps live.
    """

    entrypoint = "server.py"
    document = _object(
        ("schema", "aart-cli.dev/mcp/v1"),
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
                ("exclude", _strings("**/__pycache__/**")),
                ("include", _strings(entrypoint, _REQUIREMENTS)),
            ),
        ),
        ("transport", _object(("type", "stdio"))),
        ("runtime", _object(("type", "python"), ("version", ">=3.11"))),
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
                    _object(("path", _REQUIREMENTS), ("type", "requirements")),
                ),
            ),
        ),
        (
            "smoke_test",
            _object(
                ("arguments", _object(("limit", 1))),
                ("expect", _object(("text_contains", "expected text"))),
                ("reaches_service", True),
                ("read_only", True),
                ("timeout_seconds", 15),
                ("tool", "get_current_user"),
            ),
        ),
    )
    # `summary`, `exclude` and `arguments` are optional inside blocks the parser requires, so they
    # are commented individually rather than with their parent.
    return _Blueprint(
        "mcp",
        document,
        optional=("compatibility", "inputs", "python", "smoke_test"),
        nested_optional=(("artifact", "summary"), ("launch", "arguments"), ("payload", "exclude")),
        notes=_UNREAD_NOTE,
        payload=_mcp_payload(entrypoint),
    )


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
                        ("description", "Where this artifact reaches its provider."),
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

    Worded for an artifact rather than for a server, because every generated kind shares these
    three inputs and a skill is not a server.

    No `example`: §91 keeps the confidential class free of any field a real credential could be
    written into, and `parse_author_manifest` refuses a secret whose guidance carries one. The
    `example` field is covered by the config input below, where a sample value is just a sample.
    """

    return _object(
        ("description", "The token this artifact authenticates to its provider with."),
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


#: One line per optional position: what it is for, not what it contains.
_EXPLANATIONS: dict[str, str] = {
    "arguments": "Extra arguments the server is started with, after the entrypoint.",
    "compatibility": "Narrow the artifact to the harnesses and platforms it actually runs on.",
    "exclude": "Payload files to leave out of the package, applied after `include`.",
    "inputs": "Values AART collects from the installer and keeps for this artifact.",
    "python": "How the payload's Python dependencies are resolved at install time.",
    "reaches_service": "Declares that this tool really reads the external service. With `expect`, it lets the service stage pass.",
    "smoke_test": "A reviewed read-only MCP tool call used by `aart-cli mcp test --harness <harness>`.",
    "summary": "One line shown wherever the artifact is listed. Derived from the name if absent.",
}

#: The explanation for a position whose purpose differs by kind. Read before `_EXPLANATIONS`.
_KIND_EXPLANATIONS: dict[tuple[str, str], str] = {
    ("mcp", "inputs"): "Values AART collects from the installer and injects when the server runs.",
}

#: Fields that cannot be live beside one that is, offered under the line each replaces. Two of
#: these uncommented together do not parse, which is why they are not part of `full`.
_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "python": (
        "## Or resolve from a project file instead, with `type: uv` when you ship a uv lock:",
        "#?   dependencies:",
        "#?     type: pyproject",
        "#?     pyproject: pyproject.toml",
        "#?     lock: uv.lock",
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
    "smoke_test": (
        "## Or check one deterministic field in structuredContent instead of text:",
        "#?   expect:",
        "#?     structured_path: user.login",
        "#?     equals: expected-login",
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

_SMOKE_NOT_GENERATED: tuple[str, ...] = (
    "## MCP-only smoke fields are not valid for this artifact kind:",
    "#? smoke_test:",
    "#?   arguments: null",
    "#?   expect:",
    "#?     equals: null",
    "#?     structured_path: field",
    "#?     text_contains: text",
    "#?   reaches_service: true",
    "#?   read_only: true",
    "#?   timeout_seconds: 15",
    "#?   tool: tool-name",
)


def _disabled(kind: str, key: str, value: JsonValue) -> Result[tuple[str, ...]]:
    """One optional block as the lines it would occupy, so what is commented is the document.

    The text is produced by the emitter from the value itself rather than written out here, which
    is what makes `uncomment everything` yield exactly `full` instead of something that resembles
    it.
    """

    emitted = emit_yaml(_object((key, value)))
    if isinstance(emitted, Err):
        return emitted
    lines = [f"## {_KIND_EXPLANATIONS.get((kind, key), _EXPLANATIONS[key])}"]
    lines.extend(emitted.value.splitlines())
    lines.extend(_ALTERNATIVES.get(key, ()))
    return Ok(tuple(lines))


def _without(document: JsonObject, *keys: str) -> JsonObject:
    return JsonObject(tuple(entry for entry in document.entries if entry[0] not in keys))


def _live_document(blueprint: _Blueprint) -> JsonObject:
    live = _without(blueprint.document, *blueprint.optional)
    entries: list[tuple[str, JsonValue]] = []
    for key, value in live.entries:
        nested = tuple(field for owner, field in blueprint.nested_optional if owner == key)
        if nested and isinstance(value, JsonObject):
            entries.append((key, _without(value, *nested)))
            continue
        entries.append((key, value))
    return JsonObject(tuple(entries))


def _anchored(
    live: JsonObject,
    blueprint: _Blueprint,
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
            rendered = _disabled(blueprint.kind, key, value)
            if isinstance(rendered, Err):
                return rendered
            following = [live_key for live_key in keys if live_key > key]
            if following:
                position = following[0] if not container else f"{container}.{following[0]}"
                comments[position] = (*comments.get(position, ()), *rendered.value)
            else:
                trailing[container] = (*trailing.get(container, ()), *rendered.value)
        return None

    full = blueprint.document
    failed = place(
        "",
        live.keys(),
        tuple((key, value) for key, value in full.entries if key in blueprint.optional),
    )
    if failed is not None:
        return failed
    for owner, field in blueprint.nested_optional:
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
    """The `aart-cli.yaml` and payload one `aart-cli author init` writes, as text.

    Refuses before producing anything when the kind is not one this build generates or the name is
    not the slug `artifact.name` requires: a skeleton the parser would reject is worse than none,
    because the author's first `aart-cli author check` would blame their own edits for it.
    """

    if kind not in _BLUEPRINTS:
        offered = ", ".join(GENERATED_KINDS)
        return _error(f"this build generates no {kind!r} skeleton yet; it generates {offered}")
    blueprint = _BLUEPRINTS[kind](name)
    full = blueprint.document
    live = _live_document(blueprint)
    anchored = _anchored(live, blueprint)
    if isinstance(anchored, Err):
        return anchored
    comments, trailing = anchored.value
    header = (
        f"## {_humanized(name)}: an AART {kind} artifact.",
        "## Every field this build accepts is here. Disabled lines begin `# `; `##` is a note and",
        "## `#?` is an alternative to the line above it, not an addition. Delete what you do",
        "## not need, uncomment what you do, then run `aart-cli author check`.",
    )
    trailing[""] = (*trailing.get("", ()), *blueprint.notes)
    emitted = emit_yaml(live, comments={"": header, **comments}, trailing=trailing)
    if isinstance(emitted, Err):
        return emitted
    accepted = _verified(emitted.value)
    if isinstance(accepted, Err):
        return accepted
    return Ok(AuthorSkeleton(kind, name, emitted.value, live, full, blueprint.payload))


#: What the parser accepts on a `skill` and this generator will not write for one. A skill is
#: delivered by copying its tree into place, so a launch makes the compiled package advertise a
#: protocol it does not speak; a dependency descriptor also needs its file added to `include`.
#: Named rather than silently absent, because hiding an accepted field is the drift §1.5 is about.
_SKILL_NOT_GENERATED: tuple[str, ...] = (
    "## A skill is installed by copying this tree into the harness, so nothing launches it and",
    "## these three are left to you. Declaring them makes the package advertise a protocol it",
    "## does not speak, which is rarely what a skill wants:",
    "#? transport:",
    "#?   type: stdio",
    "#? runtime:",
    "#?   type: python",
    '#?   version: ">=3.11"',
    "#? launch:",
    "#?   type: python",
    "#?   entrypoint: run.py",
    "#?   arguments:",
    '#?     - "--once"',
    "## Python dependencies likewise. Enabling this also means adding the file to `include`,",
    "## which is why it is offered rather than written out:",
    "#? python:",
    "#?   dependencies:",
    "#?     type: requirements",
    "#?     path: requirements.txt",
    "#?   dependencies:",
    "#?     type: pyproject",
    "#?     pyproject: pyproject.toml",
    "#?     lock: uv.lock",
)

_SKILL_DOCUMENT = "SKILL.md"


def _skill_blueprint(name: str) -> _Blueprint:
    """A skill is a tree of instructions, so its document is the artifact and its payload.

    `native_tree` refuses a skill package without `payload/SKILL.md`, which makes that file part of
    what `init` owes an author rather than something they discover from a promotion refusal.
    """

    document = _object(
        ("schema", "aart-cli.dev/skill/v1"),
        (
            "artifact",
            _object(
                ("kind", "skill"),
                ("name", name),
                ("summary", f"{_humanized(name)} skill."),
                ("version", "0.1.0"),
            ),
        ),
        (
            "payload",
            _object(
                ("exclude", _strings("**/.DS_Store")),
                ("include", _strings(_SKILL_DOCUMENT)),
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
    )
    return _Blueprint(
        "skill",
        document,
        optional=("compatibility", "inputs"),
        nested_optional=(("artifact", "summary"), ("payload", "exclude")),
        notes=(*_SKILL_NOT_GENERATED, *_SMOKE_NOT_GENERATED, *_UNREAD_NOTE),
        payload=_skill_payload(name),
    )


def _skill_payload(name: str) -> tuple[PayloadFile, ...]:
    """The one file a skill package requires, with the shape a harness reads."""

    title = _humanized(name)
    return (
        PayloadFile(
            _SKILL_DOCUMENT,
            f"# {title}\n"
            "\n"
            "One paragraph on what this skill is for and when an agent should reach for it.\n"
            "Replace everything below with the instructions the agent is to follow.\n"
            "\n"
            "## When to use it\n"
            "\n"
            "- The situation that calls for this skill.\n"
            "\n"
            "## How to use it\n"
            "\n"
            "1. The first step.\n"
            "2. The next one.\n",
        ),
    )


#: What the parser accepts on a document artifact and this generator will not write for one. A
#: guideline is written into a file and a memory is merged into a block somebody else owns, so
#: nothing launches either, and `native_tree` requires the payload to be *exactly one* Markdown
#: document -- which is why no dependency file can be offered for these two at all.
_DOCUMENT_NOT_GENERATED: tuple[str, ...] = (
    "## This artifact is delivered by writing its one document where the harness reads it, so",
    "## nothing launches it. The parser accepts these anyway; declaring them makes the compiled",
    "## package advertise a protocol it does not speak:",
    "#? transport:",
    "#?   type: stdio",
    "#? runtime:",
    "#?   type: python",
    '#?   version: ">=3.11"',
    "#? launch:",
    "#?   type: python",
    "#?   entrypoint: run.py",
    "#?   arguments:",
    '#?     - "--once"',
    "## `python:` is accepted and cannot be used here: every dependency descriptor names a file,",
    "## and this payload is exactly one Markdown document. A second file in it is refused",
    "## outright, so all three shapes are named rather than offered:",
    "#? python:",
    "#?   dependencies:",
    "#?     type: requirements",
    "#?     path: requirements.txt",
    "#?   dependencies:",
    "#?     type: pyproject",
    "#?     pyproject: pyproject.toml",
    "#?     lock: uv.lock",
)

#: The hook is launched by its own `hook.json`, so the launch block would be a second answer to a
#: question already answered -- and the payload it would name is the script the declaration names.
_HOOK_NOT_GENERATED: tuple[str, ...] = (
    "## A hook says what runs it in `hook.json`, not here, so these are left to you. `launch:`",
    "## in particular would be a second answer to a question the declaration already answers:",
    "#? transport:",
    "#?   type: stdio",
    "#? runtime:",
    "#?   type: python",
    '#?   version: ">=3.11"',
    "#? launch:",
    "#?   type: python",
    "#?   entrypoint: run.py",
    "#?   arguments:",
    '#?     - "--once"',
    "## Python dependencies, if the script is Python. Enabling this also means adding the file",
    "## to `include`, which is why it is offered rather than written out:",
    "#? python:",
    "#?   dependencies:",
    "#?     type: requirements",
    "#?     path: requirements.txt",
    "#?   dependencies:",
    "#?     type: pyproject",
    "#?     pyproject: pyproject.toml",
    "#?     lock: uv.lock",
)

_GUIDELINE_DOCUMENT = "GUIDELINE.md"
_MEMORY_DOCUMENT = "MEMORY.md"
_HOOK_DECLARATION = "hook.json"
_HOOK_SCRIPT = "run.sh"


def _document_blueprint(
    kind: str,
    name: str,
    *,
    document_name: str,
    summary: str,
    payload: tuple[PayloadFile, ...],
) -> _Blueprint:
    """A guideline and a memory differ in where they are delivered, not in what they declare.

    Both are one Markdown document: `native_tree` refuses either package unless the payload holds
    exactly one `.md` file and nothing else. So `include` names one file, and the closing note says
    why a second cannot be added rather than leaving an author to find out from a refusal.
    """

    return _Blueprint(
        kind,
        _object(
            ("schema", f"aart-cli.dev/{kind}/v1"),
            (
                "artifact",
                _object(
                    ("kind", kind),
                    ("name", name),
                    ("summary", summary),
                    ("version", "0.1.0"),
                ),
            ),
            (
                "payload",
                _object(
                    ("exclude", _strings("**/.DS_Store")),
                    ("include", _strings(document_name)),
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
        ),
        optional=("compatibility", "inputs"),
        nested_optional=(("artifact", "summary"), ("payload", "exclude")),
        notes=(*_DOCUMENT_NOT_GENERATED, *_SMOKE_NOT_GENERATED, *_UNREAD_NOTE),
        payload=payload,
    )


def _guideline_blueprint(name: str) -> _Blueprint:
    """A guideline: one document written where the harness reads its standing instructions."""

    return _document_blueprint(
        "guideline",
        name,
        document_name=_GUIDELINE_DOCUMENT,
        summary=f"{_humanized(name)} guideline.",
        payload=(
            PayloadFile(
                _GUIDELINE_DOCUMENT,
                f"# {_humanized(name)}\n"
                "\n"
                "The standing instruction this guideline carries, in the words an agent should\n"
                "read it in. Replace all of it.\n"
                "\n"
                "- One rule per line, stated as a rule rather than as advice.\n"
                "- Say what to do when two rules disagree.\n",
            ),
        ),
    )


def _memory_blueprint(name: str) -> _Blueprint:
    """A memory: one document merged into a managed block inside a file the user owns."""

    return _document_blueprint(
        "memory",
        name,
        document_name=_MEMORY_DOCUMENT,
        summary=f"{_humanized(name)} memory.",
        payload=(
            PayloadFile(
                _MEMORY_DOCUMENT,
                f"# {_humanized(name)}\n"
                "\n"
                "What an agent should already know before it starts. This body is merged into a\n"
                "managed region of a file the user also writes in, so keep it short and keep it\n"
                "true -- everything here is read on every turn.\n"
                "\n"
                "- One fact per line.\n",
            ),
        ),
    )


def _hook_blueprint(name: str) -> _Blueprint:
    """A hook is two things at once: a script AART delivers, and one entry in somebody else's file.

    The entry comes from `hook.json`, which the author writes -- unlike `mcp.json`, which is
    reserved for the compiler. `package_hook` reads the declaration, requires `command` to begin
    `${SCRIPT_DIR}/`, and requires the file it names to be in the payload and executable.
    """

    return _Blueprint(
        "hook",
        _object(
            ("schema", "aart-cli.dev/hook/v1"),
            (
                "artifact",
                _object(
                    ("kind", "hook"),
                    ("name", name),
                    ("summary", f"{_humanized(name)} hook."),
                    ("version", "0.1.0"),
                ),
            ),
            (
                "payload",
                _object(
                    ("exclude", _strings("**/.DS_Store")),
                    ("include", _strings(_HOOK_DECLARATION, _HOOK_SCRIPT)),
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
        ),
        optional=("compatibility", "inputs"),
        nested_optional=(("artifact", "summary"), ("payload", "exclude")),
        notes=(*_HOOK_NOT_GENERATED, *_SMOKE_NOT_GENERATED, *_UNREAD_NOTE),
        payload=_hook_payload(name),
    )


def _hook_payload(name: str) -> tuple[PayloadFile, ...]:
    """The declaration a harness is told about, and the script it names -- executable.

    `${SCRIPT_DIR}` is the one substitution a declaration may carry: it is where AART will have
    delivered the script on the installing machine, which the author has never seen.
    """

    declaration = json.dumps(
        {
            "name": name,
            "event": "PreToolUse",
            "matcher": "Bash",
            "command": f"${{SCRIPT_DIR}}/{_HOOK_SCRIPT}",
        },
        indent=2,
    )
    return (
        PayloadFile(_HOOK_DECLARATION, f"{declaration}\n"),
        PayloadFile(
            _HOOK_SCRIPT,
            "#!/bin/sh\n"
            "# Runs on every event this hook's `matcher` selects. Replace it.\n"
            "#\n"
            "# Exit non-zero to refuse whatever triggered it; exit 0 to let it through.\n"
            "exit 0\n",
            executable=True,
        ),
    )


#: Kind -> the blueprint for it. Registering one here is the whole of adding a generated kind.
_BLUEPRINTS: dict[str, Callable[[str], _Blueprint]] = {
    "guideline": _guideline_blueprint,
    "hook": _hook_blueprint,
    "mcp": _mcp_blueprint,
    "memory": _memory_blueprint,
    "skill": _skill_blueprint,
}

GENERATED_KINDS = tuple(sorted(_BLUEPRINTS))


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


def _mcp_payload(entrypoint: str) -> tuple[PayloadFile, ...]:
    """A payload the generated manifest actually describes: the entrypoint it declares, and a
    requirements file the dependency descriptor names."""

    return (
        PayloadFile(
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
        PayloadFile(_REQUIREMENTS, "# One pinned requirement per line.\n"),
    )
