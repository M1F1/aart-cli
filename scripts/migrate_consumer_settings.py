#!/usr/bin/env python3
"""Rewrite aart-cli <= 0.8.x consumer settings so aart-cli 0.9.0+ can read them.

aart-cli 0.9.0 renamed the stored detail level: fast -> less-info, verbose -> more-info.
Without this, the TUI stops at start with
`consumer-settings-invalid: stored detail level must be less-info or more-info`.

Usage (stdlib only, Python 3.10+):

  python3 migrate_consumer_settings.py            dry run on $AART_CLI_HOME or ~/.aart-cli
  python3 migrate_consumer_settings.py --write    rewrites state/consumer-settings.json in place

Only `detail_level` is touched; the file holds preferences and nothing secret.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_VALUES = {"fast": "less-info", "verbose": "more-info"}


def main(argv: list[str]) -> int:
    if argv not in ([], ["--write"]):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    home = Path(os.environ.get("AART_CLI_HOME") or Path.home() / ".aart-cli")
    path = home / "state" / "consumer-settings.json"
    if not path.is_file():
        print(f"nothing to do: {path} does not exist")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print(f"error: {path} is not a JSON object", file=sys.stderr)
        return 1
    level = data.get("detail_level")
    if level not in _VALUES:
        print(f"nothing to do: detail_level is {level!r}")
        return 0
    data["detail_level"] = _VALUES[level]
    if argv:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{'rewrote' if argv else 'would rewrite'} {path}: detail_level {level} -> {_VALUES[level]}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
