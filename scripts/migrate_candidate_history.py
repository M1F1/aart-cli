#!/usr/bin/env python3
"""Set aside Candidate history that aart-cli 0.10.0 cannot read, so the next Source Sync rebuilds it.

aart-cli <= 0.9.x could write `candidate-history/v2`, which carried Collection Candidates. 0.10.0
moved Collections into the Registry (D-430) and reads only `candidate-history/v1`, so such a file
stops the TUI with `candidate-history-invalid: Candidate history index fields are invalid`.

Candidate history is a local cache of Source Scans: nothing the Registry approved lives in it, and
a missing history is a valid state that the next `Sync` of that Source writes again.

Usage (stdlib only, Python 3.10+):

  python3 migrate_candidate_history.py            dry run on $AART_CLI_HOME or ~/.aart-cli
  python3 migrate_candidate_history.py --write    moves each unreadable history aside

Each affected `sources/<source>/candidates/` directory is moved, whole, to
`<home>-migration-backup/<timestamp>/sources/<source>/candidates/`; nothing is deleted.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

_FIELDS = {"active", "history", "manifest_count", "revision", "schema", "source_alias"}
_SCHEMA = "aart-cli.dev/candidate-history/v1"


def _readable(index: Path) -> bool:
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and set(data) == _FIELDS and data.get("schema") == _SCHEMA


def main(argv: list[str]) -> int:
    if argv not in ([], ["--write"]):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    home = Path(os.environ.get("AART_CLI_HOME") or Path.home() / ".aart-cli").resolve()
    sources = home / "sources"
    if not sources.is_dir():
        print(f"nothing to do: {sources} does not exist")
        return 0
    backup = Path(f"{home}-migration-backup") / time.strftime("%Y%m%dT%H%M%S")
    moved = 0
    for candidates in sorted(sources.glob("*/candidates")):
        index = candidates / "current.json"
        if candidates.is_symlink() or not candidates.is_dir() or not index.is_file():
            continue
        if _readable(index):
            continue
        target = backup / candidates.relative_to(home)
        moved += 1
        print(f"{'moved' if argv else 'would move'} {candidates} -> {target}")
        if argv:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(candidates), str(target))
    print(
        f"{moved} Candidate history(ies) {'moved aside' if argv else 'to move (dry run; add --write)'}"
    )
    if moved and argv:
        print(
            "next: open each Source in the Maintainer TUI and Sync it, or run `aart-cli source sync`"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
