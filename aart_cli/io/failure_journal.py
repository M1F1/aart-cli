"""The failure journal: `state/failures.sqlite3` (§215).

It keeps every failure aart-cli met -- in a command, the terminal application, a harness's usage
hook or the telemetry sender -- whether telemetry is on or not, the newest `MAX_KEPT`, each with
its own event id, the aart-cli version it happened in, and whether it waits, was sent, was
rejected or was skipped. `consume report` reads it; the telemetry sender sends what waits while
failures are sent.

`record_failure` is what a place that met a failure calls. It keeps only what
`domain.failures.failure_of` keeps -- never a message, an argument, a path or a value (INV-333) --
and it never raises and never writes to a stream, so what failed ends as it would have without it
(INV-335). A failure while recording one is dropped, never recorded.

`noting` and `note_diagnostics` collect the diagnostic codes a command reported, so the command's
error is recorded with them without the command passing them back.
"""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
import traceback
import uuid
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.failures import (
    JOURNAL_STATES,
    Failure,
    FailureKind,
    JournaledFailure,
    failure_of,
)
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.telemetry import contract_moment

from .telemetry_store import OutboxCounts, open_versioned

__all__ = [
    "FAILURES_DATABASE",
    "FAILURES_UNREADABLE",
    "FAILURES_UNWRITABLE",
    "MAX_KEPT",
    "FailureJournal",
    "WaitingFailure",
    "note_diagnostics",
    "noting",
    "record_failure",
]

FAILURES_DATABASE = "failures.sqlite3"
FAILURES_UNREADABLE = DiagnosticCode("failures-unreadable")
FAILURES_UNWRITABLE = DiagnosticCode("failures-unwritable")
MAX_KEPT = 500

SCHEMA_VERSION = 1

_SCHEMA = (
    "CREATE TABLE failure ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " event_id TEXT NOT NULL UNIQUE,"
    " occurred_at TEXT NOT NULL,"
    " version TEXT NOT NULL,"
    " kind TEXT NOT NULL,"
    " place TEXT NOT NULL,"
    # The contract's `failure` object, as it is sent.
    " document TEXT NOT NULL,"
    " state TEXT NOT NULL DEFAULT 'waiting',"
    " settled_at TEXT)",
    "CREATE INDEX failure_state ON failure (state, id)",
)

_SETTLED = ("sent", "rejected", "skipped")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class WaitingFailure:
    """A journaled failure waiting to be sent; `failure` is `None` when its row cannot be read
    back as one, which is never sent."""

    event_id: str
    occurred_at: str
    version: str
    failure: Failure | None


@dataclass(frozen=True, slots=True)
class FailureJournal:
    """The journal under one managed state root."""

    state_root: str

    def __post_init__(self) -> None:
        if not isinstance(self.state_root, str) or not self.state_root:
            raise ValueError("the failure journal needs a state root")

    @property
    def path(self) -> str:
        return str(Path(self.state_root) / FAILURES_DATABASE)

    def exists(self) -> bool:
        return Path(self.path).exists()

    def _open(self, *, create: bool) -> sqlite3.Connection | None:
        return open_versioned(Path(self.path), _SCHEMA, SCHEMA_VERSION, create=create)

    def record(self, failure: Failure, moment: str, version: str, event_id: str) -> Result[None]:
        """Keep `failure`, waiting, and only the newest `MAX_KEPT` of all."""

        try:
            connection = self._open(create=True)
            assert connection is not None
            with closing(connection):
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT OR IGNORE INTO failure (event_id, occurred_at, version, kind, place,"
                    " document) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        moment,
                        version,
                        failure.kind.value,
                        failure.place,
                        json.dumps(failure.document(), separators=(",", ":")),
                    ),
                )
                connection.execute(
                    "DELETE FROM failure WHERE id NOT IN"
                    " (SELECT id FROM failure ORDER BY id DESC LIMIT ?)",
                    (MAX_KEPT,),
                )
                connection.execute("COMMIT")
        except (OSError, sqlite3.Error) as error:
            return _error(FAILURES_UNWRITABLE, f"cannot record a failure in {self.path}: {error}")
        return Ok(None)

    def _rows(self, sql: str, parameters: tuple[object, ...]) -> Result[list[tuple]]:
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok([])
            with closing(connection):
                return Ok(connection.execute(sql, parameters).fetchall())
        except (OSError, sqlite3.Error) as error:
            return _error(FAILURES_UNREADABLE, f"cannot read failures from {self.path}: {error}")

    def waiting(self, *, limit: int) -> Result[tuple[WaitingFailure, ...]]:
        """The oldest waiting failures, at most `limit`."""

        rows = self._rows(
            "SELECT event_id, occurred_at, version, kind, place, document FROM failure"
            " WHERE state = 'waiting' ORDER BY id LIMIT ?",
            (limit,),
        )
        if isinstance(rows, Err):
            return rows
        return Ok(
            tuple(
                WaitingFailure(event_id, moment, version, _read(kind, place, document))
                for event_id, moment, version, kind, place, document in rows.value
            )
        )

    def entries(self, *, limit: int | None = None) -> Result[tuple[JournaledFailure, ...]]:
        """What the journal holds, newest first; a row that cannot be read back is left out."""

        rows = self._rows(
            "SELECT event_id, occurred_at, version, state, kind, place, document FROM failure"
            " ORDER BY id DESC LIMIT ?",
            (-1 if limit is None else limit,),
        )
        if isinstance(rows, Err):
            return rows
        kept: list[JournaledFailure] = []
        for event_id, moment, version, state, kind, place, document in rows.value:
            failure = _read(kind, place, document)
            if failure is not None and state in JOURNAL_STATES:
                kept.append(JournaledFailure(event_id, moment, version, state, failure))
        return Ok(tuple(kept))

    def settle(self, event_ids: tuple[str, ...], state: str, now: datetime) -> Result[int]:
        """Mark waiting failures sent, rejected or skipped; how many changed."""

        if state not in _SETTLED:
            raise ValueError("a failure is settled as sent, rejected or skipped")
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(0)
            with closing(connection):
                connection.execute("BEGIN IMMEDIATE")
                changed = 0
                for event_id in event_ids:
                    changed += connection.execute(
                        "UPDATE failure SET state = ?, settled_at = ?"
                        " WHERE event_id = ? AND state = 'waiting'",
                        (state, now.isoformat(), event_id),
                    ).rowcount
                connection.execute("COMMIT")
        except (OSError, sqlite3.Error) as error:
            return _error(FAILURES_UNWRITABLE, f"cannot record failures in {self.path}: {error}")
        return Ok(changed)

    def skip_waiting(self, now: datetime) -> Result[int]:
        """Mark every waiting failure skipped: failures are not sent (INV-336)."""

        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(0)
            with closing(connection):
                return Ok(
                    connection.execute(
                        "UPDATE failure SET state = 'skipped', settled_at = ?"
                        " WHERE state = 'waiting'",
                        (now.isoformat(),),
                    ).rowcount
                )
        except (OSError, sqlite3.Error) as error:
            return _error(FAILURES_UNWRITABLE, f"cannot record failures in {self.path}: {error}")

    def counts(self) -> Result[OutboxCounts]:
        rows = self._rows("SELECT state, COUNT(*) FROM failure GROUP BY state", ())
        if isinstance(rows, Err):
            return rows
        found = dict(rows.value)
        return Ok(
            OutboxCounts(
                found.get("waiting", 0),
                found.get("sent", 0),
                found.get("rejected", 0),
                found.get("skipped", 0),
            )
        )

    def forget(self) -> Result[None]:
        """Delete every failure the journal holds: telemetry's `--forget` (D-509)."""

        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(None)
            with closing(connection):
                connection.execute("PRAGMA secure_delete = ON")
                connection.execute("DELETE FROM failure")
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except (OSError, sqlite3.Error) as error:
            return _error(FAILURES_UNWRITABLE, f"cannot forget failures in {self.path}: {error}")
        return Ok(None)


def _read(kind: str, place: str, document: str) -> Failure | None:
    try:
        read = Failure.from_document(kind, place, json.loads(document))
    except (TypeError, ValueError):
        return None
    return read.value if isinstance(read, Ok) else None


# -- what a place that failed calls ----------------------------------------------------------------

_NOTED: ContextVar[list[str] | None] = ContextVar("aart_cli_noted_diagnostics", default=None)


@contextmanager
def noting() -> Iterator[list[str]]:
    """Collect, for what runs inside, the diagnostic codes `note_diagnostics` is given."""

    codes: list[str] = []
    token = _NOTED.set(codes)
    try:
        yield codes
    finally:
        _NOTED.reset(token)


def note_diagnostics(diagnostics: Iterable[Diagnostic]) -> None:
    """The codes of the diagnostics a command reports, for its failure; outside `noting`,
    nothing."""

    collected = _NOTED.get()
    if collected is None:
        return
    try:
        collected.extend(str(diagnostic.code) for diagnostic in diagnostics)
    except Exception:  # noqa: BLE001 -- recording never changes what failed
        pass


_PACKAGE = Path(__file__).resolve().parents[1]


def _frames(error: BaseException | None) -> list[tuple[str, str, int]]:
    """The frames of `error`'s traceback inside this package, outermost first, by module."""

    if error is None:
        return []
    frames: list[tuple[str, str, int]] = []
    for frame in traceback.extract_tb(error.__traceback__):
        try:
            relative = Path(os.path.abspath(frame.filename)).relative_to(_PACKAGE)
        except ValueError:
            continue
        if relative.suffix != ".py":
            continue
        parts = (_PACKAGE.name, *relative.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        frames.append((".".join(parts), frame.name, frame.lineno or 0))
    return frames


def _type_name(error: BaseException | None) -> str | None:
    if error is None:
        return None
    kind = type(error)
    module = getattr(kind, "__module__", "")
    return kind.__qualname__ if module == "builtins" else f"{module}.{kind.__qualname__}"


def _platform() -> str:
    if sys.platform == "darwin":
        return "darwin"
    return "linux" if sys.platform.startswith("linux") else "other"


def record_failure(
    home: str,
    kind: FailureKind,
    place: str,
    *,
    error: BaseException | None = None,
    exit_code: int | None = None,
    diagnostics: Iterable[str] = (),
    sync: bool = True,
    now: datetime | None = None,
) -> bool:
    """Journal a failure aart-cli met in the application `home`, and start a due synchronisation
    unless `sync` is false; whether it was journaled. Never raises, never writes to a stream."""

    try:
        from aart_cli.runtime_contract import EXECUTABLE_VERSION

        if not isinstance(home, str) or not home.startswith("/"):
            return False
        failure = failure_of(
            kind,
            place,
            _type_name(error),
            _frames(error),
            tuple(diagnostics),
            exit_code,
            platform.python_version(),
            _platform(),
        )
        if failure is None:
            return False
        moment = contract_moment(now or datetime.now(timezone.utc))
        kept = FailureJournal(str(Path(home) / "state")).record(
            failure, moment, str(EXECUTABLE_VERSION), str(uuid.uuid4())
        )
        if isinstance(kept, Err):
            return False
        if sync:
            from aart_cli.io.telemetry_sync import maybe_sync

            maybe_sync(home)
        return True
    except Exception:  # noqa: BLE001 -- recording never changes what failed
        return False
