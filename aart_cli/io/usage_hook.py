"""What a harness runs before each tool call once artifact usage is turned on for it (§212).

    <python> -I <this file> <harness> <application home>

The harness gives the call on stdin as JSON. A skill or MCP call is recorded as one use in the
Activity database; any other call, and anything that cannot be read, records nothing.

The harness started this, so it must never be what fails: every outcome exits 0 with nothing on
stdout, which both harnesses read as "carry on". It is run by path with `-I` rather than as a
module, so the project the harness works in -- the current directory -- can put nothing on the
import path, and the package is found from where this file is.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

#: A hook payload is one tool call. Claude Code includes the call's input, which is bounded by
#: what a model writes; anything past this is not read and records nothing.
_MAX_PAYLOAD = 1024 * 1024


def record(harness: str, home: str, payload: bytes, *, now: datetime | None = None) -> bool:
    """Record the use `payload` describes; whether one was recorded."""

    from aart_cli.domain.artifact_usage import use_from_hook
    from aart_cli.domain.result import Ok
    from aart_cli.io.activity_store import ActivityDatabase

    if len(payload) > _MAX_PAYLOAD or not home.startswith("/"):
        return False
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    use = use_from_hook(harness, document)
    if use is None:
        return False
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    written = ActivityDatabase(str(Path(home) / "state")).record_use(use, moment)
    return isinstance(written, Ok)


def main(arguments: list[str]) -> int:
    try:
        if len(arguments) == 2:
            record(arguments[0], arguments[1], sys.stdin.buffer.read(_MAX_PAYLOAD + 1))
    except Exception:  # noqa: BLE001 -- a hook that fails would be the harness failing
        pass
    return 0


if __name__ == "__main__":
    # `-I` left the script's own directory off the path; the package is two levels up from here.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.exit(main(sys.argv[1:]))
