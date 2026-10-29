"""The telemetry outbox: `state/telemetry.sqlite3` (§213).

It holds whether telemetry is on, the server's address and the installation id; every event
recorded while it is on, waiting until a server acknowledges it; and when the last
synchronisation succeeded, was attempted, and may next start.

It exists only once a person turned telemetry on, so a harness hook on a machine where it never
was costs one `stat`. An event is recorded by one statement that also checks telemetry is on, so
an event recorded while it is being turned off is either before or after, never half of each.

Like the Activity database this imports only the domain: a hook runs it for every recorded use.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aart_cli.domain.artifact_usage import ArtifactUse, UsageKind
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.telemetry import SyncState, TelemetryEvent

__all__ = [
    "TELEMETRY_DATABASE",
    "TELEMETRY_LOCK",
    "TELEMETRY_UNREADABLE",
    "TELEMETRY_UNWRITABLE",
    "OutboxCounts",
    "TelemetryOutbox",
    "TelemetrySetting",
    "WaitingEvent",
]

TELEMETRY_DATABASE = "telemetry.sqlite3"
TELEMETRY_LOCK = "telemetry.lock"
TELEMETRY_UNREADABLE = DiagnosticCode("telemetry-unreadable")
TELEMETRY_UNWRITABLE = DiagnosticCode("telemetry-unwritable")

SCHEMA_VERSION = 1

_SCHEMA = (
    "CREATE TABLE setting ("
    " id INTEGER PRIMARY KEY CHECK (id = 1),"
    " enabled INTEGER NOT NULL,"
    " endpoint TEXT NOT NULL,"
    " client_id TEXT NOT NULL)",
    "CREATE TABLE event ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " event_id TEXT NOT NULL UNIQUE,"
    " occurred_at TEXT NOT NULL,"
    # A use is kept as the harness named it and attributed when it is sent; an action's event
    # is kept whole.
    " harness TEXT,"
    " kind TEXT,"
    " name TEXT,"
    " event_type TEXT,"
    " artifact_id TEXT,"
    " artifact_type TEXT,"
    " artifact_version TEXT,"
    " state TEXT NOT NULL DEFAULT 'waiting',"
    " settled_at TEXT)",
    "CREATE INDEX event_state ON event (state, id)",
    "CREATE TABLE sync ("
    " id INTEGER PRIMARY KEY CHECK (id = 1),"
    " last_success_at TEXT,"
    " last_attempt_at TEXT,"
    " next_retry_at TEXT,"
    " failures INTEGER NOT NULL DEFAULT 0,"
    " paused TEXT)",
    "INSERT INTO sync (id) VALUES (1)",
)

_SETTLED = ("sent", "rejected", "skipped")
_BUSY_SECONDS = 5.0
_ON = "(SELECT enabled FROM setting WHERE id = 1) = 1"


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _moment(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


@dataclass(frozen=True, slots=True)
class TelemetrySetting:
    enabled: bool
    endpoint: str
    client_id: str


@dataclass(frozen=True, slots=True)
class OutboxCounts:
    waiting: int = 0
    sent: int = 0
    rejected: int = 0
    skipped: int = 0


@dataclass(frozen=True, slots=True)
class WaitingEvent:
    """An event waiting to be sent: a use to attribute, or an action's event as it will be sent."""

    event_id: str
    occurred_at: str
    harness: str | None = None
    kind: UsageKind | None = None
    name: str | None = None
    event: TelemetryEvent | None = None


@dataclass(frozen=True, slots=True)
class TelemetryOutbox:
    """The outbox under one managed state root."""

    state_root: str

    def __post_init__(self) -> None:
        if not isinstance(self.state_root, str) or not self.state_root:
            raise ValueError("the telemetry outbox needs a state root")

    @property
    def path(self) -> str:
        return str(Path(self.state_root) / TELEMETRY_DATABASE)

    @property
    def lock_path(self) -> str:
        return str(Path(self.state_root) / TELEMETRY_LOCK)

    def exists(self) -> bool:
        return Path(self.path).exists()

    def _open(self, *, create: bool) -> sqlite3.Connection | None:
        path = Path(self.path)
        if not create and not path.exists():
            return None
        if create:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
        connection = sqlite3.connect(path, timeout=_BUSY_SECONDS, isolation_level=None)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if not create:
                    connection.close()
                    return None
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("PRAGMA user_version").fetchone()[0] == 0:
                    for statement in _SCHEMA:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.execute("COMMIT")
            elif version != SCHEMA_VERSION:
                raise sqlite3.DatabaseError(
                    f"its schema is version {version}; this aart-cli reads {SCHEMA_VERSION}"
                )
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                try:
                    connection.execute("PRAGMA journal_mode=WAL")
                except sqlite3.OperationalError:
                    pass
        except BaseException:
            connection.close()
            raise
        return connection

    # -- consent ---------------------------------------------------------------------------------

    def setting(self) -> Result[TelemetrySetting | None]:
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(None)
            with closing(connection):
                row = connection.execute(
                    "SELECT enabled, endpoint, client_id FROM setting WHERE id = 1"
                ).fetchone()
        except (OSError, sqlite3.Error) as error:
            return _error(TELEMETRY_UNREADABLE, f"cannot read telemetry from {self.path}: {error}")
        return Ok(None if row is None else TelemetrySetting(bool(row[0]), row[1], row[2]))

    def enable(self, endpoint: str, new_client_id: str) -> Result[TelemetrySetting]:
        """Turn telemetry on for `endpoint`, keeping the installation id when there is one."""

        try:
            connection = self._open(create=True)
            assert connection is not None
            with closing(connection):
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute("SELECT client_id FROM setting WHERE id = 1").fetchone()
                client_id = new_client_id if row is None else row[0]
                connection.execute(
                    "INSERT OR REPLACE INTO setting (id, enabled, endpoint, client_id)"
                    " VALUES (1, 1, ?, ?)",
                    (endpoint, client_id),
                )
                # Turning it on again ends a pause: the person has just said where to send.
                connection.execute("UPDATE sync SET next_retry_at = NULL, paused = NULL")
                connection.execute("COMMIT")
        except (OSError, sqlite3.Error) as error:
            return _error(TELEMETRY_UNWRITABLE, f"cannot turn telemetry on in {self.path}: {error}")
        return Ok(TelemetrySetting(True, endpoint, client_id))

    def disable(self, *, forget: bool) -> Result[str]:
        """Stop recording and sending; `forget` also deletes the outbox and the installation id."""

        if forget:
            try:
                for suffix in ("", "-wal", "-shm", "-journal"):
                    Path(self.path + suffix).unlink(missing_ok=True)
                Path(self.lock_path).unlink(missing_ok=True)
            except OSError as error:
                return _error(TELEMETRY_UNWRITABLE, f"cannot delete {self.path}: {error}")
            return Ok(self.path)
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(self.path)
            with closing(connection):
                connection.execute("UPDATE setting SET enabled = 0")
        except (OSError, sqlite3.Error) as error:
            return _error(
                TELEMETRY_UNWRITABLE, f"cannot turn telemetry off in {self.path}: {error}"
            )
        return Ok(self.path)

    # -- recording -------------------------------------------------------------------------------

    def record_use(self, use: ArtifactUse, moment: str, event_id: str) -> Result[bool]:
        """Keep one use for sending, when telemetry is on; whether it was kept."""

        if not self.exists():
            return Ok(False)
        return self._insert(
            "INSERT INTO event (event_id, occurred_at, harness, kind, name)"
            f" SELECT ?, ?, ?, ?, ? WHERE {_ON}",
            (event_id, moment, use.harness, use.kind.value, use.name),
        )

    def record_events(self, events: tuple[TelemetryEvent, ...]) -> Result[bool]:
        """Keep an action's events for sending, when telemetry is on; whether they were kept."""

        if not events or not self.exists():
            return Ok(False)
        return self._insert(
            "INSERT INTO event (event_id, occurred_at, event_type, artifact_id, artifact_type,"
            f" artifact_version) SELECT ?, ?, ?, ?, ?, ? WHERE {_ON}",
            *(
                (
                    event.event_id,
                    event.occurred_at,
                    event.event_type,
                    event.artifact_id,
                    event.artifact_type,
                    event.artifact_version,
                )
                for event in events
            ),
        )

    def _insert(self, statement: str, *rows: tuple[object, ...]) -> Result[bool]:
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(False)
            with closing(connection):
                connection.execute("BEGIN IMMEDIATE")
                kept = 0
                for row in rows:
                    kept += connection.execute(statement, row).rowcount
                connection.execute("COMMIT")
        except (OSError, sqlite3.Error) as error:
            return _error(TELEMETRY_UNWRITABLE, f"cannot record telemetry in {self.path}: {error}")
        return Ok(kept > 0)

    # -- sending ---------------------------------------------------------------------------------

    def waiting(self, *, limit: int) -> Result[tuple[WaitingEvent, ...]]:
        """The oldest waiting events, at most `limit`."""

        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(())
            with closing(connection):
                rows = connection.execute(
                    "SELECT event_id, occurred_at, harness, kind, name, event_type, artifact_id,"
                    " artifact_type, artifact_version FROM event WHERE state = 'waiting'"
                    " ORDER BY id LIMIT ?",
                    (limit,),
                ).fetchall()
        except (OSError, sqlite3.Error) as error:
            return _error(TELEMETRY_UNREADABLE, f"cannot read telemetry from {self.path}: {error}")
        waiting: list[WaitingEvent] = []
        for event_id, moment, harness, kind, name, event_type, artifact, kind_of, version in rows:
            if event_type is None:
                waiting.append(WaitingEvent(event_id, moment, harness, UsageKind(kind), name))
            else:
                event = TelemetryEvent(
                    event_id, moment, event_type, "aart_cli", artifact, kind_of, version
                )
                waiting.append(WaitingEvent(event_id, moment, event=event))
        return Ok(tuple(waiting))

    def settle(self, event_ids: tuple[str, ...], state: str, now: datetime) -> Result[int]:
        """Mark waiting events sent, rejected or skipped; how many changed."""

        if state not in _SETTLED:
            raise ValueError("an event is settled as sent, rejected or skipped")
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(0)
            with closing(connection):
                connection.execute("BEGIN IMMEDIATE")
                changed = 0
                for event_id in event_ids:
                    changed += connection.execute(
                        "UPDATE event SET state = ?, settled_at = ?"
                        " WHERE event_id = ? AND state = 'waiting'",
                        (state, now.isoformat(), event_id),
                    ).rowcount
                connection.execute("COMMIT")
        except (OSError, sqlite3.Error) as error:
            return _error(TELEMETRY_UNWRITABLE, f"cannot record telemetry in {self.path}: {error}")
        return Ok(changed)

    def counts(self) -> Result[OutboxCounts]:
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(OutboxCounts())
            with closing(connection):
                rows = dict(connection.execute("SELECT state, COUNT(*) FROM event GROUP BY state"))
        except (OSError, sqlite3.Error) as error:
            return _error(TELEMETRY_UNREADABLE, f"cannot read telemetry from {self.path}: {error}")
        return Ok(
            OutboxCounts(
                rows.get("waiting", 0),
                rows.get("sent", 0),
                rows.get("rejected", 0),
                rows.get("skipped", 0),
            )
        )

    def sync_state(self) -> Result[SyncState]:
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(SyncState())
            with closing(connection):
                row = connection.execute(
                    "SELECT last_success_at, last_attempt_at, next_retry_at, failures, paused"
                    " FROM sync WHERE id = 1"
                ).fetchone()
            return Ok(SyncState(_moment(row[0]), _moment(row[1]), _moment(row[2]), row[3], row[4]))
        except (OSError, sqlite3.Error, ValueError, TypeError) as error:
            return _error(TELEMETRY_UNREADABLE, f"cannot read telemetry from {self.path}: {error}")

    def save_sync_state(self, state: SyncState) -> Result[None]:
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(None)
            with closing(connection):
                connection.execute(
                    "UPDATE sync SET last_success_at = ?, last_attempt_at = ?, next_retry_at = ?,"
                    " failures = ?, paused = ? WHERE id = 1",
                    (
                        _text(state.last_success_at),
                        _text(state.last_attempt_at),
                        _text(state.next_retry_at),
                        state.failures,
                        state.paused,
                    ),
                )
        except (OSError, sqlite3.Error) as error:
            return _error(TELEMETRY_UNWRITABLE, f"cannot record telemetry in {self.path}: {error}")
        return Ok(None)
