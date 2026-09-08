"""Where a harness records the servers it can start, and what it records about each one.

A harness target is measured, not derived: every file path and map key here was observed in a real
build, and the comments say which. Nothing in this module invents a location for a harness nobody
has looked at, because a registration written to a guessed path is worse than none -- it looks
installed and never starts.

The registration itself is deliberately thin. A harness is told one absolute command and, at most,
the literal arguments that command needs. Everything that varies per installation has already been
resolved into the launcher, so the harness never learns a value and never has to be re-taught one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .artifacts import ArtifactKind
from .effects import DeliveryKind
from .hooks import HookEntryShape
from .launch import Transport
from .managed_blocks import BlockPosition

__all__ = [
    "DELIVERY_TARGETS",
    "McpEntryShape",
    "HOOK_TARGETS",
    "MCP_TARGETS",
    "MEMORY_TARGETS",
    "DeliveryTarget",
    "HookTarget",
    "McpRegistration",
    "McpTarget",
    "MemoryTarget",
    "Scope",
    "delivery_destination",
    "delivery_target",
    "hook_event_path",
    "hook_target",
    "mcp_target",
    "memory_target",
    "registration_entry",
    "registration_from_data",
    "registration_to_data",
]

_SERVER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_STDIO = frozenset({Transport.STDIO})
_NAME_SLOT = "<name>"
_DELIVERED_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class Scope(str, Enum):
    """Whose configuration a registration lands in."""

    PROJECT = "project"
    USER = "user"


class McpEntryShape(str, Enum):
    """How one harness spells the server it was given.

    Every harness here is told the same two things -- one absolute command and its literal
    arguments -- and disagrees only about how to write them down. That disagreement is not a
    detail: a registration written in another harness's shape parses and is then ignored, which
    looks installed and never starts. So the shape is measured beside the file it goes in, and a
    harness that spells it differently gets a member here rather than a translation somewhere else.
    """

    #: `{"command": "/path", "args": ["--flag"]}` -- Claude Code and Tabnine.
    COMMAND_WITH_ARGS = "command-with-args"
    #: `{"type": "local", "command": ["/path", "--flag"]}` -- OpenCode 1.18.29.
    TYPED_COMMAND_VECTOR = "typed-command-vector"


@dataclass(frozen=True, slots=True)
class McpTarget:
    """One harness's MCP registration slot, relative to that scope's root."""

    harness: str
    scope: Scope
    settings_file: str
    server_map: str
    transports: frozenset[Transport] = _STDIO
    entry_shape: McpEntryShape = McpEntryShape.COMMAND_WITH_ARGS

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or _SLUG_RE.fullmatch(self.harness) is None:
            raise ValueError("harness must be a canonical slug")
        if not isinstance(self.scope, Scope):
            raise ValueError("harness scope is invalid")
        if (
            not isinstance(self.settings_file, str)
            or not self.settings_file
            or self.settings_file.startswith("/")
            or any(part in ("", "..") for part in self.settings_file.split("/"))
            or any(character in self.settings_file for character in "\r\n")
        ):
            raise ValueError("harness settings file must stay inside its scope root")
        if not isinstance(self.server_map, str) or _SERVER_RE.fullmatch(self.server_map) is None:
            raise ValueError("harness server map key is invalid")
        if not isinstance(self.transports, frozenset) or not self.transports:
            raise ValueError("a harness target names at least one measured transport")
        if not isinstance(self.entry_shape, McpEntryShape):
            raise ValueError("a harness target names one measured entry shape")


@dataclass(frozen=True, slots=True)
class McpRegistration:
    """What one harness is told so it can start one installed artifact."""

    target: McpTarget
    server: str
    command: str
    arguments: tuple[str, ...] = ()
    transport: Transport = Transport.STDIO

    def __post_init__(self) -> None:
        if not isinstance(self.target, McpTarget):
            raise ValueError("registration needs a harness target")
        if not isinstance(self.server, str) or _SERVER_RE.fullmatch(self.server) is None:
            raise ValueError("harness server name is invalid")
        # Absolute, because the harness resolves it from a working directory nobody here controls.
        if (
            not isinstance(self.command, str)
            or not self.command.startswith("/")
            or any(character in self.command for character in "\r\n\x00")
        ):
            raise ValueError("registration command must be an absolute path")
        if not isinstance(self.arguments, tuple) or any(
            not isinstance(argument, str) or not argument or "\x00" in argument
            for argument in self.arguments
        ):
            raise ValueError("registration arguments are invalid")
        if not isinstance(self.transport, Transport):
            raise ValueError("registration transport is invalid")
        if self.transport not in self.target.transports:
            raise ValueError(
                f"{self.target.harness} was not measured with the {self.transport.value} transport"
            )


# Measured targets. The Tabnine entry is the one the target company build surfaced from
# settings.json; published documentation names mcp_servers.json for other builds, so do not move
# it without measuring the build in front of you.
MCP_TARGETS: dict[tuple[str, Scope], McpTarget] = {
    ("tabnine", Scope.PROJECT): McpTarget(
        "tabnine", Scope.PROJECT, ".tabnine/agent/settings.json", "mcpServers"
    ),
    ("tabnine", Scope.USER): McpTarget("tabnine", Scope.USER, "agent/settings.json", "mcpServers"),
    ("claude", Scope.PROJECT): McpTarget("claude", Scope.PROJECT, ".mcp.json", "mcpServers"),
    ("claude", Scope.USER): McpTarget("claude", Scope.USER, ".claude.json", "mcpServers"),
    # OpenCode 1.18.29, measured with `opencode debug config`, which prints the merged
    # configuration: a server written into the project's `opencode.json` and one written into
    # `~/.config/opencode/opencode.json` both come back under `mcp`, unchanged.
    #
    # That build reads `~/.opencode/opencode.json` too -- measured, and contradicting its own
    # shipped documentation, which says global config is "NOT `~/.opencode/`". Two paths work, so
    # the row is a choice rather than a discovery: it is the one `opencode debug paths` reports as
    # the config root and the one the build documents, which is the one that will still be read
    # when the undocumented path stops being.
    #
    # The entry shape is the reason this harness could not be copied from the dormant profile
    # registry (`B-085`): a local server here is an object with `type` and one `command` array, not
    # a command string beside `args`.
    ("opencode", Scope.PROJECT): McpTarget(
        "opencode",
        Scope.PROJECT,
        "opencode.json",
        "mcp",
        entry_shape=McpEntryShape.TYPED_COMMAND_VECTOR,
    ),
    ("opencode", Scope.USER): McpTarget(
        "opencode",
        Scope.USER,
        ".config/opencode/opencode.json",
        "mcp",
        entry_shape=McpEntryShape.TYPED_COMMAND_VECTOR,
    ),
}


def mcp_target(harness: str, scope: Scope) -> McpTarget:
    """The measured target for `harness` at `scope`, or `KeyError` if nobody has measured it."""

    try:
        return MCP_TARGETS[(harness, scope)]
    except KeyError:
        raise KeyError(
            f"no measured MCP target for harness {harness!r} at {scope.value} scope"
        ) from None


@dataclass(frozen=True, slots=True)
class DeliveryTarget:
    """Where one harness reads one kind of artifact from, relative to that scope's root.

    The counterpart of `McpTarget` for the kinds that start no process. A destination has to name
    the artifact it delivers: without `<name>` every Skill for a harness would be delivered to one
    directory, and withdrawing one on uninstall would take away the directory the harness reads all
    of them from.
    """

    harness: str
    scope: Scope
    kind: ArtifactKind
    destination: str
    delivery: DeliveryKind

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or _SLUG_RE.fullmatch(self.harness) is None:
            raise ValueError("harness must be a canonical slug")
        if not isinstance(self.scope, Scope) or not isinstance(self.kind, ArtifactKind):
            raise ValueError("delivery target scope or kind is invalid")
        if not isinstance(self.delivery, DeliveryKind):
            raise ValueError("delivery target shape is invalid")
        if (
            not isinstance(self.destination, str)
            or not self.destination
            or self.destination.startswith("/")
            or any(part in ("", "..") for part in self.destination.split("/"))
            or any(character in self.destination for character in "\r\n")
        ):
            raise ValueError("a delivery destination must stay inside its scope root")
        if _NAME_SLOT not in self.destination:
            raise ValueError(
                f"a {self.kind.value} destination must name the artifact it delivers, or "
                "uninstalling one would take away where the harness reads them all"
            )


#: Measured delivery locations, taken from the harness profiles this repository has observed.
#: Only the kinds that are installed purely by being placed appear here. A hook is a script plus an
#: entry merged into a settings file, and every measured memory target is a block merged into a
#: shared file: neither is a delivery, and both wait on a merge effect (B-034). The Product
#: Specification's own migration order is MCP, skills, guidelines/rules, memory, hooks.
DELIVERY_TARGETS: dict[tuple[str, Scope, ArtifactKind], DeliveryTarget] = {
    # Claude Code, project scope: `.claude/skills/<name>/` and `.claude/guidelines/`.
    ("claude", Scope.PROJECT, ArtifactKind.SKILL): DeliveryTarget(
        "claude", Scope.PROJECT, ArtifactKind.SKILL, ".claude/skills/<name>", DeliveryKind.TREE
    ),
    ("claude", Scope.PROJECT, ArtifactKind.GUIDELINE): DeliveryTarget(
        "claude",
        Scope.PROJECT,
        ArtifactKind.GUIDELINE,
        ".claude/guidelines/<name>.md",
        DeliveryKind.FILE,
    ),
    # Claude Code, user scope: guidelines are read from `rules/`, not `guidelines/`.
    ("claude", Scope.USER, ArtifactKind.SKILL): DeliveryTarget(
        "claude", Scope.USER, ArtifactKind.SKILL, ".claude/skills/<name>", DeliveryKind.TREE
    ),
    ("claude", Scope.USER, ArtifactKind.GUIDELINE): DeliveryTarget(
        "claude", Scope.USER, ArtifactKind.GUIDELINE, ".claude/rules/<name>.md", DeliveryKind.FILE
    ),
    # Tabnine, project scope. There is deliberately no user-scope Skill target: that build
    # documents no Agent Skills discovery location outside a project.
    ("tabnine", Scope.PROJECT, ArtifactKind.SKILL): DeliveryTarget(
        "tabnine",
        Scope.PROJECT,
        ArtifactKind.SKILL,
        ".tabnine/agent/skills/<name>",
        DeliveryKind.TREE,
    ),
    ("tabnine", Scope.PROJECT, ArtifactKind.GUIDELINE): DeliveryTarget(
        "tabnine",
        Scope.PROJECT,
        ArtifactKind.GUIDELINE,
        ".tabnine/guidelines/<name>.md",
        DeliveryKind.FILE,
    ),
    ("tabnine", Scope.USER, ArtifactKind.GUIDELINE): DeliveryTarget(
        "tabnine",
        Scope.USER,
        ArtifactKind.GUIDELINE,
        ".tabnine/guidelines/<name>.md",
        DeliveryKind.FILE,
    ),
    # Codex CLI 0.152.0, measured with `codex debug prompt-input`, which prints the skill roots it
    # is about to read. That build names four, in this order: `<project>/.codex/skills`,
    # `$CODEX_HOME/skills`, `$CODEX_HOME/skills/.system` (its own bundled skills) and
    # `<project>/.agents/skills`.
    #
    # Two of those are ours to write and two are not. `.system` belongs to the build. `.agents` is
    # the cross-vendor interop directory Codex also migrates other agents' installations from, so
    # an artifact placed there would be claimed by whichever harness looked at it last -- and this
    # is an installation the operator asked for by harness name. `.codex/skills` is Codex's own
    # first root, and it is the one measured here at both scopes: user scope resolves against the
    # home directory, which is what `$CODEX_HOME` defaults to.
    ("codex", Scope.PROJECT, ArtifactKind.SKILL): DeliveryTarget(
        "codex", Scope.PROJECT, ArtifactKind.SKILL, ".codex/skills/<name>", DeliveryKind.TREE
    ),
    ("codex", Scope.USER, ArtifactKind.SKILL): DeliveryTarget(
        "codex", Scope.USER, ArtifactKind.SKILL, ".codex/skills/<name>", DeliveryKind.TREE
    ),
    # OpenCode 1.18.29, measured with `opencode debug skill`, which lists every skill it found and
    # the file each came from. Project skills are `.opencode/skills/<name>/SKILL.md` and user skills
    # are `<config>/skills/<name>/SKILL.md`. That build also auto-loads `~/.claude/skills` and
    # `~/.agents/skills`, and both were observed working -- but those belong to other harnesses and
    # to the cross-vendor interop directory, and an installation asked for by harness name goes in
    # that harness's own directory.
    ("opencode", Scope.PROJECT, ArtifactKind.SKILL): DeliveryTarget(
        "opencode", Scope.PROJECT, ArtifactKind.SKILL, ".opencode/skills/<name>", DeliveryKind.TREE
    ),
    ("opencode", Scope.USER, ArtifactKind.SKILL): DeliveryTarget(
        "opencode",
        Scope.USER,
        ArtifactKind.SKILL,
        ".config/opencode/skills/<name>",
        DeliveryKind.TREE,
    ),
    # There is deliberately no OpenCode guideline row either: that build reads skills, agents,
    # commands and `AGENTS.md`, and documents no guidelines directory of its own.
    # There is deliberately no Codex guideline row. That build reads skills and `AGENTS.md` and
    # documents no separate guidelines directory, so a guideline delivered anywhere would be a file
    # nothing opens.
}


@dataclass(frozen=True, slots=True)
class MemoryTarget:
    """One harness's shared instruction file, relative to that scope's root.

    Deliberately not a `DeliveryTarget`. A delivery destination is required to name the artifact,
    because withdrawing one Skill must not take away the directory the harness reads them all from.
    A memory file is the opposite: every memory artifact for a harness writes into the same file the
    *user* also writes in, and each owns a delimited region of it (B-034). Naming the artifact in
    the path would be a file the harness never reads.
    """

    harness: str
    scope: Scope
    destination: str
    position: BlockPosition = BlockPosition.BOTTOM

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or _SLUG_RE.fullmatch(self.harness) is None:
            raise ValueError("harness must be a canonical slug")
        if not isinstance(self.scope, Scope) or not isinstance(self.position, BlockPosition):
            raise ValueError("memory target scope or position is invalid")
        if (
            not isinstance(self.destination, str)
            or not self.destination
            or self.destination.startswith("/")
            or any(part in ("", "..") for part in self.destination.split("/"))
            or any(character in self.destination for character in "\r\n")
        ):
            raise ValueError("a memory destination must stay inside its scope root")
        if _NAME_SLOT in self.destination:
            raise ValueError(
                "a memory destination is shared by every memory artifact for this harness, so it "
                "cannot name one of them"
            )


#: Measured shared instruction files, taken from the harness profiles this repository has observed.
#: A file here is the user's; an artifact installed into it owns one delimited block and nothing
#: else. Tabnine has no user-scope entry on purpose: that build documents a project-root
#: `TABNINE.md` and no always-loaded global instruction file, and inventing one would write a block
#: into a file nothing reads.
MEMORY_TARGETS: dict[tuple[str, Scope], MemoryTarget] = {
    # Claude Code: `CLAUDE.md` at the project root, `~/.claude/CLAUDE.md` for the user.
    ("claude", Scope.PROJECT): MemoryTarget("claude", Scope.PROJECT, "CLAUDE.md"),
    ("claude", Scope.USER): MemoryTarget("claude", Scope.USER, ".claude/CLAUDE.md"),
    # Tabnine: project-root `TABNINE.md`.
    ("tabnine", Scope.PROJECT): MemoryTarget("tabnine", Scope.PROJECT, "TABNINE.md"),
    # Codex CLI 0.152.0: `AGENTS.md` at the repository root and `$CODEX_HOME/AGENTS.md` for the
    # user, both measured by writing a marker into each and finding it in `codex debug
    # prompt-input`. The same measurement found that `$CODEX_HOME/instructions.md` -- the location
    # older Codex documentation names -- is *not* read by this build, which is why it is absent
    # here rather than listed as a second user file.
    ("codex", Scope.PROJECT): MemoryTarget("codex", Scope.PROJECT, "AGENTS.md"),
    ("codex", Scope.USER): MemoryTarget("codex", Scope.USER, ".codex/AGENTS.md"),
    # OpenCode 1.18.29: the shipped build walks up from the working directory to the worktree root
    # collecting `AGENTS.md`, and reads one more from its config root -- `<config>/AGENTS.md`, which
    # `opencode debug paths` reports as `~/.config/opencode`.
    ("opencode", Scope.PROJECT): MemoryTarget("opencode", Scope.PROJECT, "AGENTS.md"),
    ("opencode", Scope.USER): MemoryTarget("opencode", Scope.USER, ".config/opencode/AGENTS.md"),
}


@dataclass(frozen=True, slots=True)
class HookTarget:
    """Where one harness keeps a hook's script, and where it is told to run it.

    The one kind that is both halves at once. The script is delivered into a directory named for the
    artifact, which is an ordinary `DeliveryTarget` and is exposed as one; the entry that makes the
    harness run it is a member of a list inside a settings file the harness and the user share, and
    that is the half a delivery cannot express (B-034).

    `events` maps the event a package declares to the slot this build reads it from. It is a
    mapping rather than a fixed path because the two builds observed here spell the same event
    differently, and installing a `PreToolUse` hook into a `BeforeTool` slot is not a translation a
    reconciler can make later.
    """

    harness: str
    scope: Scope
    scripts: str
    settings: str
    events: tuple[tuple[str, str], ...]
    shape: HookEntryShape

    def __post_init__(self) -> None:
        if not isinstance(self.harness, str) or _SLUG_RE.fullmatch(self.harness) is None:
            raise ValueError("harness must be a canonical slug")
        if not isinstance(self.scope, Scope) or not isinstance(self.shape, HookEntryShape):
            raise ValueError("hook target scope or entry shape is invalid")
        for value, label in ((self.scripts, "script directory"), (self.settings, "settings file")):
            if (
                not isinstance(value, str)
                or not value
                or value.startswith("/")
                or any(part in ("", "..") for part in value.split("/"))
                or any(character in value for character in "\r\n")
            ):
                raise ValueError(f"a hook {label} must stay inside its scope root")
        if _NAME_SLOT not in self.scripts:
            raise ValueError(
                "a hook script directory must name the artifact it holds, or uninstalling one "
                "would take away where the harness reads them all"
            )
        if _NAME_SLOT in self.settings:
            raise ValueError("a hook settings file is shared, so it cannot name one artifact")
        if not self.events or any(
            not isinstance(item, tuple) or len(item) != 2 or not all(item) for item in self.events
        ):
            raise ValueError("a hook target maps at least one declared event to a measured slot")

    @property
    def scripts_target(self) -> DeliveryTarget:
        """The script half, as the ordinary delivery it is."""

        return DeliveryTarget(
            self.harness, self.scope, ArtifactKind.HOOK, self.scripts, DeliveryKind.TREE
        )


_CLAUDE_EVENTS = (
    ("PreToolUse", "hooks.PreToolUse"),
    ("PostToolUse", "hooks.PostToolUse"),
    ("Stop", "hooks.Stop"),
)

#: Measured hook locations. Tabnine has no user-scope entry on purpose: that build documents no
#: user-global hook discovery target, and inventing one would install a hook nothing ever runs.
HOOK_TARGETS: dict[tuple[str, Scope], HookTarget] = {
    ("claude", Scope.PROJECT): HookTarget(
        "claude",
        Scope.PROJECT,
        ".claude/hooks/<name>",
        ".claude/settings.json",
        _CLAUDE_EVENTS,
        HookEntryShape.NESTED_COMMAND,
    ),
    ("claude", Scope.USER): HookTarget(
        "claude",
        Scope.USER,
        ".claude/hooks/<name>",
        ".claude/settings.json",
        _CLAUDE_EVENTS,
        HookEntryShape.NESTED_COMMAND,
    ),
    # The observed Tabnine build spells the same three events its own way, and writes the command
    # beside the matcher rather than under it.
    ("tabnine", Scope.PROJECT): HookTarget(
        "tabnine",
        Scope.PROJECT,
        ".tabnine/agent/hooks/<name>",
        ".tabnine/agent/settings.json",
        (
            ("PreToolUse", "hooks.BeforeTool"),
            ("PostToolUse", "hooks.AfterTool"),
            ("Stop", "hooks.SessionEnd"),
        ),
        HookEntryShape.FLAT_COMMAND,
    ),
}


def hook_target(harness: str, scope: Scope) -> HookTarget:
    """The measured hook location for `harness`, or `KeyError` if nobody measured one."""

    try:
        return HOOK_TARGETS[(harness, scope)]
    except KeyError:
        raise KeyError(
            f"no measured hook target for harness {harness!r} at {scope.value} scope"
        ) from None


def hook_event_path(target: HookTarget, event: str) -> str:
    """Where `target`'s harness reads `event` from, or `KeyError` when it documents no slot.

    Refused by name rather than defaulted to the first slot: a hook installed into the wrong event
    runs at the wrong time, which is worse than one that refuses to install.
    """

    if not isinstance(target, HookTarget):
        raise ValueError("a hook event path needs a measured hook target")
    for declared, path in target.events:
        if declared == event:
            return path
    raise KeyError(f"harness {target.harness!r} documents no slot for the {event!r} event")


def memory_target(harness: str, scope: Scope) -> MemoryTarget:
    """The measured shared instruction file for `harness`, or `KeyError` if nobody measured one."""

    try:
        return MEMORY_TARGETS[(harness, scope)]
    except KeyError:
        raise KeyError(
            f"no measured memory file for harness {harness!r} at {scope.value} scope"
        ) from None


def delivery_target(harness: str, scope: Scope, kind: ArtifactKind) -> DeliveryTarget:
    """The measured target for `kind` at `harness`, or `KeyError` if nobody has measured it.

    A `KeyError` here covers three different facts, and the message says which: a harness this
    build has never looked at, a kind that build documents no location for, and a kind that starts
    a process and is registered rather than delivered.
    """

    if kind is ArtifactKind.HOOK:
        # A hook's script directory is measured beside the settings file and the event slots it
        # goes with, because those three are one fact about a build and would drift apart if a
        # second table held one of them. Delivering it is still an ordinary delivery.
        return hook_target(harness, scope).scripts_target
    try:
        return DELIVERY_TARGETS[(harness, scope, kind)]
    except KeyError:
        raise KeyError(
            f"no measured {kind.value} delivery target for harness {harness!r} at "
            f"{scope.value} scope"
        ) from None


def delivery_destination(target: DeliveryTarget, name: str) -> str:
    """`target`'s destination for one artifact, still relative to that scope's root."""

    if not isinstance(target, DeliveryTarget):
        raise ValueError("a delivery destination needs a measured target")
    if not isinstance(name, str) or _DELIVERED_NAME_RE.fullmatch(name) is None:
        # The name reaches a path, so it may not carry a separator or a parent reference: a
        # delivery whose name walked out of its directory would land somewhere nobody measured.
        raise ValueError(f"{name!r} is not a name an artifact can be delivered under")
    return target.destination.replace(_NAME_SLOT, name)


def registration_entry(registration: McpRegistration) -> dict[str, object]:
    """The object a harness stores under its server name, spelled the way that harness spells it."""

    if registration.target.entry_shape is McpEntryShape.TYPED_COMMAND_VECTOR:
        # One vector, command first. `type` is required by this shape, and `local` is the only
        # member of it a stdio registration can be.
        entry: dict[str, object] = {
            "command": [registration.command, *registration.arguments],
            "type": "local",
        }
        return dict(sorted(entry.items()))
    entry = {"command": registration.command}
    if registration.arguments:
        entry["args"] = list(registration.arguments)
    return dict(sorted(entry.items()))


def registration_from_data(data: object) -> McpRegistration:
    """Rebuild one registration from its own projection.

    The harness and scope are looked up in the measured table rather than trusted from the
    document, and the settings file has to be the one that table names.  A record claiming some
    other path is a record about a harness this build has never measured.
    """

    if not isinstance(data, dict):
        raise ValueError("a registration document must be a mapping")
    try:
        harness = data["harness"]
        scope = data["scope"]
        server = data["server"]
        command = data["command"]
        settings_file = data["settings_file"]
        transport = data["transport"]
        arguments = data.get("arguments", [])
    except KeyError as error:
        raise ValueError(f"registration document is missing {error.args[0]}") from None
    if (
        not isinstance(harness, str)
        or not isinstance(scope, str)
        or not isinstance(server, str)
        or not isinstance(command, str)
        or not isinstance(settings_file, str)
        or not isinstance(transport, str)
        or not isinstance(arguments, list)
        or any(not isinstance(item, str) for item in arguments)
    ):
        raise ValueError("registration document has an invalid field")
    try:
        target = mcp_target(harness, Scope(scope))
    except (KeyError, ValueError):
        raise ValueError(f"no measured MCP target for {harness} at {scope} scope") from None
    if target.settings_file != settings_file:
        raise ValueError(f"{harness} settings live at {target.settings_file}, not {settings_file}")
    return McpRegistration(target, server, command, tuple(arguments), Transport(transport))


def registration_to_data(registration: McpRegistration) -> dict[str, object]:
    return {
        "arguments": list(registration.arguments),
        "command": registration.command,
        "harness": registration.target.harness,
        "scope": registration.target.scope.value,
        "server": registration.server,
        "settings_file": registration.target.settings_file,
        "transport": registration.transport.value,
    }
