#!/usr/bin/env python3
"""The pull request title is the release engine's input, so it is checked before it becomes one.

Under squash merge the title becomes the single commit on `main`, and that commit is what decides
whether the next release is a patch, a minor or a major.  A title the engine cannot classify does
not fail loudly at release time -- it classifies as nothing, and the change is quietly left out of
the release it belonged in.

    python scripts/conventional_title.py "feat(tui): add a screen"
    python scripts/conventional_title.py --json "$PR_TITLE"

This validates semantic change metadata.  It is not a version synchronization test: nothing here
knows or checks a version number.

The accepted types are read out of `release-please-config.json`.  That file already says which
types exist and what each one is called in the changelog; a second list here would be a second
policy, and the interesting question is not whether the two lists agree today.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "release-please-config.json"

# Conventional Commits 1.0.0: `<type>[(scope)][!]: <description>`, with no space anywhere the
# grammar does not put one.  The description must say something -- a title that is only a type is
# a classification with no change attached to it.
_TITLE_RE = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^()\s][^()]*)\))?"
    r"(?P<breaking>!)?"
    r": (?P<description>\S.*)$"
)
# INV-082, and the one place it is written as code.  Everything else is a change worth recording
# in the changelog and not a change in what the software promises.
_MINOR_TYPES = frozenset({"feat"})
_PATCH_TYPES = frozenset({"fix", "perf", "revert"})


def _accepted_types() -> tuple[str, ...]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    return tuple(sorted(str(section["type"]) for section in config["changelog-sections"]))


ACCEPTED_TYPES: tuple[str, ...] = _accepted_types()


@dataclass(frozen=True)
class ConventionalTitle:
    type: str
    scope: str | None
    breaking: bool
    description: str


def parse(title: str) -> ConventionalTitle | None:
    """The title's semantics, or `None` if it carries none the engine can read."""

    match = _TITLE_RE.fullmatch(title)
    if match is None or match.group("type") not in ACCEPTED_TYPES:
        return None
    return ConventionalTitle(
        type=match.group("type"),
        scope=match.group("scope"),
        breaking=match.group("breaking") is not None,
        description=match.group("description"),
    )


def semver_step(title: str) -> str:
    """Which part of the version this title moves: `major`, `minor`, `patch` or `none`.

    `none` is not a refusal.  A `chore` or a `ci` change is a real change that releases nothing,
    and saying so is the difference between "this does not move the version" and "this cannot be
    classified" -- which is what `parse` returning `None` means.
    """

    parsed = parse(title)
    if parsed is None:
        raise ValueError(f"not a conventional commit title: {title!r}")
    if parsed.breaking:
        return "major"
    if parsed.type in _MINOR_TYPES:
        return "minor"
    return "patch" if parsed.type in _PATCH_TYPES else "none"


def _refusal(title: str) -> str:
    listed = ", ".join(ACCEPTED_TYPES)
    return "\n".join(
        (
            f"pull request title is not a conventional commit: {title!r}",
            "",
            "Squash merge makes this title the one commit on `main`, and the release engine reads",
            "that commit to decide the next version. Shape it like one of these:",
            "",
            "    fix(tui): preserve selected artifact after refresh",
            "    feat(mcp): add isolated Python runtime",
            "    feat(registry)!: replace legacy source schema",
            "",
            f"The type is one of: {listed}",
            "A `!` before the colon means the change breaks something, and moves the major.",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("title", help="the pull request title to validate")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)

    parsed = parse(arguments.title)
    if parsed is None:
        if arguments.json:
            print(json.dumps({"accepted": False, "title": arguments.title}, sort_keys=True))
        print(_refusal(arguments.title), file=sys.stderr)
        return 1
    step = semver_step(arguments.title)
    if arguments.json:
        print(
            json.dumps(
                {
                    "accepted": True,
                    "type": parsed.type,
                    "scope": parsed.scope,
                    "breaking": parsed.breaking,
                    "semver_step": step,
                },
                sort_keys=True,
            )
        )
    else:
        print(f"conventional commit OK: {parsed.type} -> {step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
