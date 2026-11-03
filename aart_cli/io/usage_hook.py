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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aart_cli.domain.artifact_usage import ArtifactUse

#: A hook payload is one tool call. Claude Code includes the call's input, which is bounded by
#: what a model writes; anything past this is not read and records nothing.
_MAX_PAYLOAD = 1024 * 1024


def record(harness: str, home: str, payload: bytes, *, now: datetime | None = None) -> bool:
    """Record the use `payload` describes; whether one was recorded."""

    from dataclasses import replace

    from aart_cli.domain.artifact_usage import session_from_hook, session_pseudonym, use_from_hook
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
    database = ActivityDatabase(str(Path(home) / "state"))
    # The harness's session id is turned into this machine's pseudonym of it here and goes no
    # further; without a key the use is still recorded, without a session (D-519).
    session = session_from_hook(harness, document)
    if session is not None:
        key = database.session_key()
        if isinstance(key, Ok):
            use = replace(use, session=session_pseudonym(key.value, harness, session))
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    written = database.record_use(use, instant.isoformat())
    if isinstance(written, Ok):
        _telemetry(home, use, instant, written.value.rpartition("#")[2])
    return isinstance(written, Ok)


def _telemetry(home: str, use: ArtifactUse, instant: datetime, record: str) -> None:
    """Keep the use for the telemetry server when telemetry is on, and start a due sync (§213).

    Where telemetry was never turned on this is one `stat`. Nothing here can fail the hook.
    """

    from aart_cli.io.telemetry_store import TelemetryOutbox

    try:
        outbox = TelemetryOutbox(str(Path(home) / "state"))
        if not outbox.exists():
            return
        from aart_cli.domain.result import Ok
        from aart_cli.domain.telemetry import contract_moment
        from aart_cli.io.telemetry_sync import maybe_sync

        kept = outbox.record_use(use, contract_moment(instant), record)
        if isinstance(kept, Ok) and kept.value:
            maybe_sync(home)
    except Exception:  # noqa: BLE001 -- telemetry never fails what triggered it
        pass


def main(arguments: list[str]) -> int:
    try:
        if len(arguments) == 2:
            record(arguments[0], arguments[1], sys.stdin.buffer.read(_MAX_PAYLOAD + 1))
    except Exception as error:  # noqa: BLE001 -- a hook that fails would be the harness failing
        try:
            from aart_cli.domain.failures import FailureKind
            from aart_cli.io.failure_journal import record_failure

            record_failure(arguments[1], FailureKind.CRASH, "usage-hook", error=error)
        except Exception:  # noqa: BLE001 -- nor may its journal
            pass
    return 0


if __name__ == "__main__":
    # `-I` left the script's own directory off the path; the package is two levels up from here.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.exit(main(sys.argv[1:]))
