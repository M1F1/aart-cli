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
    "RECORDER_ENVIRONMENT",
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


#: What the recorder the opencode plugin starts is given of opencode's environment, by name in
#: upper case: enough to run, to keep its locale and to send telemetry through the network the
#: person configured, and nothing opencode, its provider or a launcher holds (B-277).
RECORDER_ENVIRONMENT: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "TMPDIR",
    "SYSTEMROOT",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "CI",
    "AART_CLI_AUTOMATED",
)


def opencode_plugin(hook: UsageHook) -> str:
    """The plugin opencode loads from its plugins directory, which runs the usage hook.

    It hands over the tool's name, the MCP server it belongs to, a skill's name, the directory and
    opencode's session id, which the hook keeps only as a pseudonym, and which runtime delivered
    the call (1 or 2, by the hook it came through); never the call's arguments.
    Only `skill` and the tools of an MCP server opencode has start it: opencode names those
    `<server>_<tool>`, and asks for its servers -- `client.mcp.status()` on 1.x, `ctx.mcp.list()` on
    2 -- so a built-in or plugin tool with an underscore is not taken for one.

    The recorder is started detached and let go, so opencode exiting or stopping its process group
    does not take the last uses with it, and with only `RECORDER_ENVIRONMENT` of opencode's
    environment.

    One file serves both of opencode's plugin runtimes (D-520): its only export is the default
    definition, which OpenCode 1.x (from 1.18.29) loads through `server` and OpenCode 2 through
    `setup`. A second, named export would have 1.x load it twice. OpenCode 2 names the skill it
    loads `id`, 1.x `name`; either is the skill's directory, which is the name aart-cli installs.
    """

    if hook.harness != "opencode":
        raise ValueError("the opencode plugin runs opencode's usage hook")
    command = json.dumps(list(hook.arguments))
    kept = json.dumps(list(RECORDER_ENVIRONMENT))
    return f"""{OPENCODE_PLUGIN_MARK}
// Turn it off with `aart-cli consume usage disable --harness opencode`; that removes this file.
import {{ spawn }} from "node:child_process"

const COMMAND = {command}

// What the recorder is given of this environment; never opencode's, its provider's or a
// launcher's secrets.
const KEPT = new Set({kept})
const environment = () => {{
  const given = {{}}
  for (const [name, value] of Object.entries(process.env)) {{
    const upper = name.toUpperCase()
    if (typeof value === "string" && (KEPT.has(upper) || upper.startsWith("LC_"))) given[name] = value
  }}
  return given
}}

// opencode names an MCP tool `<server>_<tool>`, each part with anything but letters, digits, `_`
// and `-` made `_`. The longest server a tool fits is its own.
const serverOf = (tool, servers) => {{
  let found
  for (const name of servers) {{
    if (typeof name !== "string") continue
    const prefix = name.replace(/[^a-zA-Z0-9_-]/g, "_") + "_"
    if (tool.length > prefix.length && tool.startsWith(prefix)) {{
      if (found === undefined || name.length > found.length) found = name
    }}
  }}
  return found
}}

// The servers' names, asked for again when a tool fits none of those already known, since a
// server can be added while opencode runs.
const mcpServers = (list) => {{
  let known = []
  return async (tool) => {{
    let server = serverOf(tool, known)
    if (server !== undefined) return server
    try {{
      known = (await list()) ?? []
    }} catch {{
      return undefined
    }}
    return serverOf(tool, known)
  }}
}}

const hand = (payload) => {{
  const child = spawn(COMMAND[0], COMMAND.slice(1), {{
    detached: true,
    env: environment(),
    stdio: ["pipe", "ignore", "ignore"],
    windowsHide: true,
  }})
  child.on("error", () => {{}})
  child.stdin.on("error", () => {{}})
  child.stdin.end(JSON.stringify(payload))
  child.unref()
}}

// Names only: a skill's name, the server's, and nothing else the call was given. `runtime` is
// the hook that delivered the call -- 1.x's `tool.execute.before` or OpenCode 2's
// `ctx.tool.hook` -- since OpenCode 1.19 calls `setup` too.
const record = async (runtime, directory, called, args, sessionID, serverFor) => {{
  try {{
    const tool = String(called)
    const session = typeof sessionID === "string" ? sessionID : undefined
    if (tool === "skill") {{
      const named = args?.id ?? args?.name
      if (typeof named === "string") hand({{ tool, skill: named, directory, session, runtime }})
      return
    }}
    if (!tool.includes("_")) return
    const server = await serverFor(tool)
    if (server !== undefined) hand({{ tool, server, directory, session, runtime }})
  }} catch {{}}
}}

// OpenCode 1.x.
const server = async ({{ client, directory }}) => {{
  const serverFor = mcpServers(async () => Object.keys((await client.mcp.status())?.data ?? {{}}))
  return {{
    "tool.execute.before": async (input, output) => {{
      void record(1, directory, input?.tool, output?.args, input?.sessionID, serverFor)
    }},
  }}
}}

// OpenCode 2. A hook that throws fails the tool call, so this one never does; and setup returns
// nothing, because what it returns is taken as its cleanup.
async function setup(ctx) {{
  if (typeof ctx?.tool?.hook !== "function") return
  const directory = ctx.location?.directory ?? process.cwd()
  const serverFor = mcpServers(async () =>
    ((await ctx.mcp.list())?.data ?? []).map((item) => item?.name),
  )
  await ctx.tool.hook("execute.before", (event) => {{
    void record(2, directory, event?.tool, event?.input, event?.sessionID, serverFor)
  }})
}}

export default {{ id: "aart-cli-usage", server, setup }}
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
        "server's name, the tool, the project directory, a pseudonym of the session and the "
        "time.",
        "Never records what a tool is called with, prompts or answers.",
        (
            f"Kept on this machine, in {database}. Telemetry is on: each use of an artifact "
            f"aart-cli installed is sent to {telemetry_endpoint} as the artifact's name and "
            "version, the harness, the tool, the scope it reached, the session's pseudonym and "
            "the time, never the project; "
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
