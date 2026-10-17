#!/usr/bin/env python3
"""Remove `artifact.version` from author manifests so aart-cli 0.10.0 accepts them.

aart-cli 0.10.0 assigns every version in the Registry (CP-31 step 2, D-423). A source manifest that
still names one is refused: `artifact.version is not written in a source manifest`.

Usage (run in an author repository checkout; stdlib only, Python 3.10+):

  python3 migrate_author_manifests.py REPO           dry run: lists what would change
  python3 migrate_author_manifests.py REPO --write   rewrites the manifests in place

Only committed `aart-cli.yaml` / `aart-cli.json` files are touched, and only the `version` key
directly under `artifact`. `runtime.version` and every other field stay. Nothing is committed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_NAMES = ("aart-cli.yaml", "aart-cli.json")
_TOP = re.compile(r"^[A-Za-z_][\w.-]*\s*:")


def _yaml(text: str) -> str | None:
    """Drop the `version:` line inside the top-level `artifact:` block, or None if there is none."""

    lines = text.splitlines(keepends=True)
    inside = False
    indent: str | None = None
    for index, line in enumerate(lines):
        if _TOP.match(line):
            inside = line.split(":", 1)[0].strip() == "artifact"
            indent = None
            continue
        if not inside or not line.strip() or line.lstrip().startswith("#"):
            continue
        current = line[: len(line) - len(line.lstrip())]
        if indent is None:
            indent = current
        if current == indent and re.match(r"version\s*:", line.lstrip()):
            return "".join(lines[:index] + lines[index + 1 :])
    return None


def _json(text: str) -> str | None:
    data = json.loads(text)
    artifact = data.get("artifact") if isinstance(data, dict) else None
    if not isinstance(artifact, dict) or "version" not in artifact:
        return None
    del artifact["version"]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2) or (len(argv) == 2 and argv[1] != "--write"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    write = len(argv) == 2
    try:
        listed = subprocess.run(
            ("git", "-C", str(root), "ls-files", "-z"), check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        print(f"error: {root} is not a Git checkout", file=sys.stderr)
        return 2
    changed = 0
    for raw in sorted(item for item in listed.decode("utf-8").split("\0") if item):
        if Path(raw).name not in _NAMES:
            continue
        path = root / raw
        text = path.read_text(encoding="utf-8")
        try:
            new = _json(text) if raw.endswith(".json") else _yaml(text)
        except ValueError as error:
            print(f"error: {raw}: {error}", file=sys.stderr)
            return 1
        if new is None:
            continue
        changed += 1
        print(("rewrote " if write else "would rewrite ") + raw)
        if write:
            path.write_text(new, encoding="utf-8")
    print(f"{changed} manifest(s) {'rewritten' if write else 'to rewrite (dry run; add --write)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
