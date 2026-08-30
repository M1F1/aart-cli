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

from .launch import Transport

__all__ = [
    "MCP_TARGETS",
    "McpRegistration",
    "McpTarget",
    "Scope",
    "mcp_target",
    "registration_entry",
    "registration_to_data",
]

_SERVER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_STDIO = frozenset({Transport.STDIO})


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


def registration_entry(registration: McpRegistration) -> dict[str, object]:
    """The object a harness stores under its server name."""

    entry: dict[str, object] = {"command": registration.command}
    if registration.arguments:
        entry["args"] = list(registration.arguments)
    return dict(sorted(entry.items()))


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
