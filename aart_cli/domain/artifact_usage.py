"""Which installed skill or MCP a harness used, and how often (§212).

A harness tells its hook which tool it is about to call. Two of those calls are an artifact being
used: a skill being loaded, and a tool of an MCP server. This module turns what each harness hands
its hook into one `ArtifactUse`, and many recorded uses into a ranking a person can read.

Only names are kept. What the tool was called with is never read into a use: arguments carry
whatever the person or the model typed, and that can be a secret.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .receipts import InstallationReceipt, InstalledRecord
from .result import Err, Ok, Result

__all__ = [
    "USAGE_HARNESSES",
    "USAGE_HARNESSES_INVALID",
    "ArtifactUse",
    "InstalledName",
    "UsageCount",
    "UsageKind",
    "UsageRank",
    "installed_names",
    "parse_usage_harnesses",
    "rank_usage",
    "use_from_hook",
]

#: The harnesses whose hooks can say which tool runs. Tabnine and Vibe are absent: neither has a
#: hook that is told which tool is about to run (D-500).
USAGE_HARNESSES: tuple[str, ...] = ("claude", "opencode")

USAGE_HARNESSES_INVALID = DiagnosticCode("usage-harnesses-invalid")

#: A skill or tool name longer than this is not one a harness gave.
_MAX_NAME = 200
_MAX_PROJECT = 4096


def parse_usage_harnesses(raw: str) -> Result[tuple[str, ...]]:
    """`AART_CLI_DEFAULT_USAGE_HARNESSES`: where usage is recorded until somebody chooses otherwise.

    Harness names separated by commas, each one that can record, once; or `none`. Empty is `none`,
    because a release variable cannot be told unset from empty (D-502). Spaces around a name are
    the shell's and are dropped; nothing else is repaired.
    """

    value = raw.strip()
    if not value or value.lower() == "none":
        return Ok(())
    names = tuple(name.strip() for name in value.split(","))
    problem = ""
    for index, name in enumerate(names):
        if not name:
            problem = "an empty name"
        elif name not in USAGE_HARNESSES:
            problem = f"{name!r} cannot record artifact usage"
        elif name in names[:index]:
            problem = f"{name!r} twice"
        if problem:
            allowed = ", ".join(USAGE_HARNESSES)
            return Err(
                (
                    Diagnostic(
                        USAGE_HARNESSES_INVALID,
                        Severity.ERROR,
                        f"default usage harnesses {value!r} hold {problem}; use {allowed} or none",
                    ),
                )
            )
    return Ok(names)


class UsageKind(str, Enum):
    SKILL = "skill"
    MCP = "mcp"


def _name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > _MAX_NAME or not value.isprintable():
        return None
    return value


def _project(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or len(value) > _MAX_PROJECT
        or not value.isprintable()
    ):
        return ""
    return value


@dataclass(frozen=True, slots=True)
class ArtifactUse:
    """One call of a skill or an MCP tool, as the harness named it.

    `name` is a skill's name, or the MCP server's for Claude Code. opencode names a tool
    `<server>_<tool>` and does not say where the server ends, so its whole tool name is kept and
    the server is found when the uses are ranked against what is installed.
    """

    harness: str
    kind: UsageKind
    name: str
    project: str = ""

    def __post_init__(self) -> None:
        if (
            self.harness not in USAGE_HARNESSES
            or not isinstance(self.kind, UsageKind)
            or _name(self.name) != self.name
            or _project(self.project) != self.project
        ):
            raise ValueError("an artifact use is invalid")


def _claude(payload: Mapping[str, object]) -> ArtifactUse | None:
    tool = payload.get("tool_name")
    project = _project(payload.get("cwd"))
    if tool == "Skill":
        arguments = payload.get("tool_input")
        if not isinstance(arguments, Mapping):
            return None
        skill = _name(arguments.get("skill"))
        return None if skill is None else ArtifactUse("claude", UsageKind.SKILL, skill, project)
    if isinstance(tool, str) and tool.startswith("mcp__"):
        server = _name(tool[len("mcp__") :].split("__", 1)[0])
        return None if server is None else ArtifactUse("claude", UsageKind.MCP, server, project)
    return None


def _opencode(payload: Mapping[str, object]) -> ArtifactUse | None:
    tool = _name(payload.get("tool"))
    project = _project(payload.get("directory"))
    if tool == "skill":
        skill = _name(payload.get("skill"))
        return None if skill is None else ArtifactUse("opencode", UsageKind.SKILL, skill, project)
    # Every MCP tool is `<server>_<tool>`; opencode's own tools have no underscore.
    if tool is not None and "_" in tool.strip("_"):
        return ArtifactUse("opencode", UsageKind.MCP, tool, project)
    return None


def use_from_hook(harness: str, payload: object) -> ArtifactUse | None:
    """The artifact a hook's payload says is being used, or `None` when it names none."""

    if not isinstance(payload, Mapping):
        return None
    if harness == "claude":
        return _claude(payload)
    if harness == "opencode":
        return _opencode(payload)
    return None


@dataclass(frozen=True, slots=True)
class UsageCount:
    """How many times one name was used in one harness, and when last."""

    harness: str
    kind: UsageKind
    name: str
    uses: int
    last_used: str

    def __post_init__(self) -> None:
        if not isinstance(self.uses, int) or isinstance(self.uses, bool) or self.uses < 1:
            raise ValueError("a usage count is a positive number of uses")


@dataclass(frozen=True, slots=True)
class InstalledName:
    """The name a harness calls one installed artifact by."""

    harness: str
    kind: UsageKind
    name: str
    artifact: str


def installed_names(records: tuple[InstalledRecord, ...]) -> tuple[InstalledName, ...]:
    """Each installed skill's directory name and each MCP's server name, per harness."""

    names: set[InstalledName] = set()
    for record in records:
        artifact = f"{record.coordinate.source}/{record.coordinate.artifact}"
        receipt = record.receipt
        if isinstance(receipt, InstallationReceipt):
            for registration in receipt.registrations:
                names.add(
                    InstalledName(
                        registration.target.harness, UsageKind.MCP, registration.server, artifact
                    )
                )
        elif record.coordinate.artifact.kind == "skill":
            for delivery in receipt.deliveries:
                names.add(
                    InstalledName(
                        delivery.harness,
                        UsageKind.SKILL,
                        PurePosixPath(delivery.destination.rstrip("/")).name,
                        artifact,
                    )
                )
    return tuple(sorted(names, key=lambda item: (item.harness, item.kind.value, item.name)))


@dataclass(frozen=True, slots=True)
class UsageRank:
    """One line of the ranking: what was used, where, and how often.

    `artifact` is the installed artifact when aart-cli installed what was used, and `installed`
    says so; otherwise it is the name the harness used, which is all that is known about it.
    """

    artifact: str
    kind: UsageKind
    harness: str
    uses: int
    last_used: str
    installed: bool


def _resolve(count: UsageCount, names: tuple[InstalledName, ...]) -> InstalledName | None:
    candidates = [
        item for item in names if item.harness == count.harness and item.kind is count.kind
    ]
    exact = [item for item in candidates if item.name == count.name]
    if exact:
        return exact[0]
    if count.harness == "opencode" and count.kind is UsageKind.MCP:
        # opencode's tool is `<server>_<tool>`: the longest installed server it starts with.
        prefixed = [item for item in candidates if count.name.startswith(f"{item.name}_")]
        if prefixed:
            return max(prefixed, key=lambda item: len(item.name))
    return None


def rank_usage(
    counts: tuple[UsageCount, ...], names: tuple[InstalledName, ...]
) -> tuple[UsageRank, ...]:
    """The most used first: per artifact and harness, ties broken by the latest use, then name."""

    merged: dict[tuple[str, UsageKind, str, bool], tuple[int, str]] = {}
    for count in counts:
        resolved = _resolve(count, names)
        key = (
            count.name if resolved is None else resolved.artifact,
            count.kind,
            count.harness,
            resolved is not None,
        )
        uses, last = merged.get(key, (0, ""))
        merged[key] = (uses + count.uses, max(last, count.last_used))
    ranked = [
        UsageRank(artifact, kind, harness, uses, last, installed)
        for (artifact, kind, harness, installed), (uses, last) in merged.items()
    ]
    ranked.sort(key=lambda item: (item.artifact, item.harness))
    ranked.sort(key=lambda item: item.last_used, reverse=True)
    ranked.sort(key=lambda item: item.uses, reverse=True)
    return tuple(ranked)
