"""The skills a plugin carries, which are installed with it (§214).

A plugin registers skills from its own tree: superpowers adds its `skills/` directory to opencode's
configuration. Those skills are the plugin's members. A harness discovers a skill under its
directory's name, so that is the member's name; nothing is parsed out of the document.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["SKILL_DOCUMENT", "PluginMember", "plugin_members"]

SKILL_DOCUMENT = "SKILL.md"


@dataclass(frozen=True, slots=True)
class PluginMember:
    """One skill a plugin carries: its name, and its directory relative to the payload root."""

    name: str
    path: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not isinstance(self.path, str)
            or not self.name
            or "/" in self.name
            or not self.name.isprintable()
            or self.path.startswith("/")
            or any(part in {"", ".", ".."} for part in self.path.split("/"))
            or self.path.rpartition("/")[2] != self.name
        ):
            raise ValueError("a plugin member is a skill directory inside the payload")


def plugin_members(paths: Iterable[str]) -> tuple[PluginMember, ...]:
    """The members a payload's files make, in name order (INV-329).

    `paths` are the payload's files relative to its root. Each directory holding a `SKILL.md` is a
    member; one at the root has no name and is none. A name two directories carry is left out:
    which of them the harness loads is its choice, so a use of that name cannot be attributed.
    """

    holding = {
        directory
        for directory, _, document in (path.rpartition("/") for path in paths)
        if document == SKILL_DOCUMENT and directory
    }
    named = Counter(directory.rpartition("/")[2] for directory in holding)
    return tuple(
        sorted(
            (
                PluginMember(directory.rpartition("/")[2], directory)
                for directory in holding
                if named[directory.rpartition("/")[2]] == 1
            ),
            key=lambda member: member.name,
        )
    )
