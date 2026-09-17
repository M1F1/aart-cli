"""Refuse the narrow release gate to anything that is not release bookkeeping.

`INV-096` lets a release pull request be gated on what it changes rather than on everything, but
only while it changes nothing else. That condition has to be *checked*, because the thing the
workflow keys on -- a branch named `release-please--…` -- is not evidence. Anyone who can push can
push to that branch, and a gate that skips the test suite on the strength of a branch name is a way
into `main` rather than a gate.

So this reads the diff. The files the release engine is configured to rewrite are in scope; one
path outside them and the pull request is an ordinary change that has to be gated as one.

Used by `.github/workflows/pr-check.yml` before the narrow gate runs. `--files` reads the list on
stdin instead of asking git, which is how the tests drive it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Exactly what the release engine rewrites: the version literals in the three places that quote the
# release, and the changelog it generates.  `release_policy_test.py` holds that this list and
# `release-please-config.json` agree, so a fifth file added to the engine's config fails there
# rather than silently widening what may skip the suite.
IN_SCOPE = frozenset(
    {
        "pyproject.toml",
        "agent_artifacts/__init__.py",
        ".release-please-manifest.json",
        "CHANGELOG.md",
    }
)


def out_of_scope(changed: tuple[str, ...]) -> tuple[str, ...]:
    """The changed paths that are not release bookkeeping, in the order they arrived.

    An empty diff raises rather than returning nothing. Nothing changed is not a release pull
    request; it is a comparison that did not work -- a wrong base, an unfetched history -- and the
    narrow gate would then pass by proving that a tree nobody looked at is fine.
    """

    if not changed:
        raise ValueError(
            "no changed files: the base comparison produced nothing.\n"
            "A release pull request changes the version literals, so an empty diff means the\n"
            "comparison is wrong (an unfetched base, or the wrong ref), not that it is in scope."
        )
    return tuple(path for path in changed if path not in IN_SCOPE)


def changed_against(base: str) -> tuple[str, ...]:
    completed = subprocess.run(
        ("git", "diff", "--name-only", f"{base}...HEAD"),
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            f"git could not compare against {base!r}: {completed.stderr.strip()}\n"
            "The release job checks out with `fetch-depth: 0` so this comparison has history."
        )
    return tuple(line for line in completed.stdout.splitlines() if line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--base", help="base ref or sha the pull request is measured against")
    group.add_argument(
        "--files", action="store_true", help="read the changed paths on stdin, one per line"
    )
    arguments = parser.parse_args(argv)

    if arguments.files:
        changed = tuple(line.strip() for line in sys.stdin if line.strip())
    else:
        changed = changed_against(arguments.base)

    try:
        strays = out_of_scope(changed)
    except ValueError as error:
        print(f"release scope check failed: {error}", file=sys.stderr)
        return 2

    if strays:
        print(
            "release scope check failed: this pull request changes more than release bookkeeping,\n"
            "so it cannot be gated as a release. Out of scope:",
            file=sys.stderr,
        )
        for path in strays:
            print(f"  {path}", file=sys.stderr)
        print(
            "\nGate it as an ordinary change: take the commit off the release branch and open a\n"
            "pull request for it (INV-096).",
            file=sys.stderr,
        )
        return 1

    print(f"release scope OK: {len(changed)} file(s), all release bookkeeping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
