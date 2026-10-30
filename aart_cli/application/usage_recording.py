"""Turning artifact usage on and off in a harness, as data (§212).

Usage is recorded only where the person turned it on, one harness at a time. Turning it on is two
things: the consent, kept in the consumer's Settings, and a hook in the harness's user
configuration that hands each skill and MCP call to aart-cli. This module decides what that hook
is and what the harness file looks like with and without it; `io.usage_hooks` reads and writes.

A hook aart-cli wrote is recognised by the script it runs, so turning usage off removes exactly
that and leaves every hook somebody else wrote where it was.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from dataclasses import dataclass

from aart_cli.domain.artifact_usage import USAGE_HARNESSES, UsageKind, UsageRank

__all__ = [
    "ArtifactUsageView",
    "CLAUDE_MATCHER",
    "HOOK_SCRIPT",
    "OPENCODE_PLUGIN_MARK",
    "UsageHook",
    "claude_settings_with",
    "claude_settings_without",
    "claude_usage_hooked",
    "opencode_plugin",
    "usage_disclosure",
    "usage_ranking_lines",
]

#: The script every usage hook runs, as it appears at the end of its path.
HOOK_SCRIPT = "aart_cli/io/usage_hook.py"

#: Claude Code calls a skill through the `Skill` tool and an MCP tool as `mcp__<server>__<tool>`.
CLAUDE_MATCHER = "Skill|mcp__.*"

#: The first line of the plugin file aart-cli writes for opencode; a file without it is not ours.
OPENCODE_PLUGIN_MARK = "// Written by aart-cli: records which skills and MCP tools opencode calls."


@dataclass(frozen=True, slots=True)
class UsageHook:
    """How one harness runs the usage hook: this interpreter, that script, this home."""

    harness: str
    python: str
    script: str
    home: str

    def __post_init__(self) -> None:
        if self.harness not in USAGE_HARNESSES:
            raise ValueError(f"artifact usage cannot be recorded in {self.harness}")
        for value in (self.python, self.script, self.home):
            if not isinstance(value, str) or not value.startswith("/") or "\n" in value:
                raise ValueError("a usage hook names absolute paths")
        if not self.script.endswith(HOOK_SCRIPT):
            raise ValueError(f"a usage hook runs {HOOK_SCRIPT}")

    @property
    def arguments(self) -> tuple[str, ...]:
        return (self.python, "-I", self.script, self.harness, self.home)

    @property
    def command(self) -> str:
        return shlex.join(self.arguments)


def _ours(entry: object) -> bool:
    if not isinstance(entry, Mapping):
        return False
    hooks = entry.get("hooks")
    return isinstance(hooks, list) and any(
        isinstance(hook, Mapping)
        and isinstance(hook.get("command"), str)
        and HOOK_SCRIPT in hook["command"]
        for hook in hooks
    )


def _pre_tool_use(document: Mapping[str, object]) -> list[object]:
    hooks = document.get("hooks", {})
    if not isinstance(hooks, Mapping):
        raise ValueError("its `hooks` is not an object")
    entries = hooks.get("PreToolUse", [])
    if not isinstance(entries, list):
        raise ValueError("its `hooks.PreToolUse` is not a list")
    return list(entries)


def claude_usage_hooked(document: Mapping[str, object]) -> bool:
    """Whether Claude Code's user settings run aart-cli's usage hook."""

    try:
        return any(_ours(entry) for entry in _pre_tool_use(document))
    except ValueError:
        return False


def _with_entries(document: Mapping[str, object], entries: list[object]) -> dict[str, object]:
    changed = dict(document)
    present = document.get("hooks", {})
    hooks: dict[str, object] = dict(present) if isinstance(present, Mapping) else {}
    if entries:
        hooks["PreToolUse"] = entries
    else:
        hooks.pop("PreToolUse", None)
    if hooks:
        changed["hooks"] = hooks
    else:
        changed.pop("hooks", None)
    return changed


def claude_settings_with(document: Mapping[str, object], hook: UsageHook) -> dict[str, object]:
    """The settings with exactly one usage hook, this one, after every other hook.

    Asynchronous, so Claude Code never waits for it: a record of a call is not worth slowing it.
    """

    if hook.harness != "claude":
        raise ValueError("Claude Code's settings take Claude Code's usage hook")
    entries = [entry for entry in _pre_tool_use(document) if not _ours(entry)]
    entries.append(
        {
            "matcher": CLAUDE_MATCHER,
            "hooks": [{"type": "command", "command": hook.command, "async": True, "timeout": 30}],
        }
    )
    return _with_entries(document, entries)


def claude_settings_without(document: Mapping[str, object]) -> dict[str, object]:
    """The settings with aart-cli's usage hook removed and everything else as it was."""

    entries = _pre_tool_use(document)
    kept = [entry for entry in entries if not _ours(entry)]
    if len(kept) == len(entries):
        return dict(document)
    return _with_entries(document, kept)


def opencode_plugin(hook: UsageHook) -> str:
    """The plugin opencode loads from its plugins directory, which runs the usage hook.

    It hands over the tool's name, a skill's name, and the directory; never the call's arguments.
    Only `skill` and tools with an underscore -- MCP tools are `<server>_<tool>` -- start it.
    """

    if hook.harness != "opencode":
        raise ValueError("the opencode plugin runs opencode's usage hook")
    command = json.dumps(list(hook.arguments))
    return f"""{OPENCODE_PLUGIN_MARK}
// Turn it off with `aart-cli consume usage disable --harness opencode`; that removes this file.
import {{ spawn }} from "node:child_process"

const COMMAND = {command}

export const AartCliUsage = async ({{ directory }}) => ({{
  "tool.execute.before": async (input, output) => {{
    try {{
      const tool = String(input.tool)
      if (tool !== "skill" && !tool.includes("_")) return
      const skill = tool === "skill" ? output?.args?.name : undefined
      const child = spawn(COMMAND[0], COMMAND.slice(1), {{ stdio: ["pipe", "ignore", "ignore"] }})
      child.on("error", () => {{}})
      child.stdin.on("error", () => {{}})
      child.stdin.end(JSON.stringify({{ tool, skill, directory }}))
      child.unref()
    }} catch {{}}
  }},
}})
"""


_HARNESS_NAMES = {"claude": "Claude Code", "opencode": "opencode"}


@dataclass(frozen=True, slots=True)
class ArtifactUsageView:
    """What Settings and Activity say about artifact usage: where it goes, and what it shows."""

    database: str
    #: The file turning usage on changes, per harness that can record it.
    files: tuple[tuple[str, str], ...] = ()
    #: The harnesses whose hook is in place now.
    hooked: tuple[str, ...] = ()
    ranking: tuple[UsageRank, ...] = ()
    #: Where telemetry sends uses, when it is on; empty when nothing is sent (B-259).
    telemetry_endpoint: str = ""

    def file(self, harness: str) -> str:
        return dict(self.files).get(harness, "")


def usage_disclosure(
    harness: str, *, database: str, changed_file: str, telemetry_endpoint: str = ""
) -> tuple[str, ...]:
    """What turning usage on records, where, and what it changes: the consent asked for.

    `telemetry_endpoint` is where telemetry sends, empty while it is off: with it on, the uses of
    artifacts aart-cli installed leave this machine, and saying otherwise would be false (B-259).
    """

    if harness not in USAGE_HARNESSES:
        raise ValueError(f"artifact usage cannot be recorded in {harness}")
    name = _HARNESS_NAMES[harness]
    return (
        f"Records each skill {name} loads and each MCP tool it calls: the skill's or MCP "
        "server's name, the project directory and the time.",
        "Never records what a tool is called with, prompts or answers.",
        (
            f"Kept on this machine, in {database}. Telemetry is on: each use of an artifact "
            f"aart-cli installed is sent to {telemetry_endpoint} as the artifact's name and "
            "version, the harness and the time, never the project; "
            "`aart-cli consume telemetry disable` stops it."
            if telemetry_endpoint
            else f"Kept only on this machine, in {database}. Nothing is sent anywhere."
        ),
        f"Adds a hook to {changed_file}; turning it off removes it.",
    )


_KIND_NAMES = {UsageKind.SKILL: "Skill", UsageKind.MCP: "MCP"}


def usage_ranking_lines(ranking: tuple[UsageRank, ...], *, limit: int = 10) -> tuple[str, ...]:
    """The most used artifacts, one line each: uses, artifact, type, harness, last used."""

    lines = []
    for item in ranking[:limit]:
        named = item.artifact if item.installed else f"{item.artifact} (not installed by aart-cli)"
        lines.append(
            f"{item.uses:>5}  {named}  {_KIND_NAMES[item.kind]}  {item.harness}  "
            f"last {item.last_used[:16].replace('T', ' ')} UTC"
        )
    return tuple(lines)
