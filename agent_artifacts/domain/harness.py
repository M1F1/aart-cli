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
from .launch import Transport

__all__ = [
    "DELIVERY_TARGETS",
    "MCP_TARGETS",
    "DeliveryTarget",
    "McpRegistration",
    "McpTarget",
    "Scope",
    "delivery_destination",
    "delivery_target",
    "mcp_target",
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


@dataclass(frozen=True, slots=True)
class McpTarget:
    """One harness's MCP registration slot, relative to that scope's root."""

    harness: str
    scope: Scope
    settings_file: str
    server_map: str
    transports: frozenset[Transport] = _STDIO

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
}


def delivery_target(harness: str, scope: Scope, kind: ArtifactKind) -> DeliveryTarget:
    """The measured target for `kind` at `harness`, or `KeyError` if nobody has measured it.

    A `KeyError` here covers three different facts, and the message says which: a harness this
    build has never looked at, a kind that build documents no location for, and a kind that starts
    a process and is registered rather than delivered.
    """

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
    """The object a harness stores under its server name."""

    entry: dict[str, object] = {"command": registration.command}
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
