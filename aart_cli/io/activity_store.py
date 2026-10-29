"""Activity: finished actions and recorded artifact uses, in one SQLite database (§212).

The database is `state/activity.sqlite3` in the application home. It replaces a directory of one
JSON file per action, which every Activity screen opened and parsed in full: a query reads only
the newest actions, and a harness hook appends a use without reading anything.

SQLite is in the standard library, so this adds no runtime dependency. Every write waits for the
others, so the hooks of two harnesses and an aart-cli command can write at the same moment; the
journal becomes WAL as soon as no other connection holds the database.

This module imports only the domain. A harness hook runs it for every skill and MCP call, and
what it imports is what that call waits for.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from aart_cli.domain.artifact_usage import ArtifactUse, UsageCount, UsageKind
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result

__all__ = [
    "ACTIVITY_DATABASE",
    "ACTIVITY_UNREADABLE",
    "ACTIVITY_UNWRITABLE",
    "SCHEMA_VERSION",
    "ActivityDatabase",
]

ACTIVITY_DATABASE = "activity.sqlite3"
ACTIVITY_UNREADABLE = DiagnosticCode("activity-unreadable")
ACTIVITY_UNWRITABLE = DiagnosticCode("activity-unwritable")

#: `PRAGMA user_version`. A database another version wrote is reported, never rewritten.
SCHEMA_VERSION = 1

_SCHEMA = (
    "CREATE TABLE action ( id INTEGER PRIMARY KEY, moment TEXT NOT NULL, receipt BLOB NOT NULL)",
    "CREATE INDEX action_moment ON action (moment)",
    "CREATE TABLE artifact_use ("
    " id INTEGER PRIMARY KEY,"
    " moment TEXT NOT NULL,"
    " harness TEXT NOT NULL,"
    " kind TEXT NOT NULL,"
    " name TEXT NOT NULL,"
    " project TEXT NOT NULL)",
    "CREATE INDEX artifact_use_name ON artifact_use (harness, kind, name)",
)

#: How long a writer waits for another one before giving up, in seconds.
_BUSY_SECONDS = 5.0


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _write_ahead(connection: sqlite3.Connection) -> None:
    """Switch the journal to WAL when no other connection is using the database.

    Changing the journal mode does not wait for a busy database -- SQLite answers "database is
    locked" at once -- so a writer that loses that race keeps the rollback journal, which is just
    as correct, and a later writer switches it. WAL is kept in the file once set.
    """

    if connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
        return
    try:
        connection.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass


@dataclass(frozen=True, slots=True)
class ActivityDatabase:
    """The Activity database under one managed state root."""

    state_root: str

    def __post_init__(self) -> None:
        if not isinstance(self.state_root, str) or not self.state_root:
            raise ValueError("the Activity database needs a state root")

    @property
    def path(self) -> str:
        return str(Path(self.state_root) / ACTIVITY_DATABASE)

    def _open(self, *, create: bool) -> sqlite3.Connection | None:
        """A connection with the schema in place, or `None` when nothing was recorded yet."""

        path = Path(self.path)
        if not create and not path.exists():
            return None
        if create:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Created owner-only before SQLite opens it: SQLite would create it with the umask.
            os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
        connection = sqlite3.connect(path, timeout=_BUSY_SECONDS, isolation_level=None)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if not create:
                    connection.close()
                    return None
                connection.execute("BEGIN IMMEDIATE")
                # Another writer may have created it between the read and the lock.
                if connection.execute("PRAGMA user_version").fetchone()[0] == 0:
                    for statement in _SCHEMA:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.execute("COMMIT")
            elif version != SCHEMA_VERSION:
                raise sqlite3.DatabaseError(
                    f"its schema is version {version}; this aart-cli reads {SCHEMA_VERSION}"
                )
            if create:
                _write_ahead(connection)
        except BaseException:
            connection.close()
            raise
        return connection

    def record_action(self, moment: str, receipt: bytes) -> Result[str]:
        """Append one finished action. `moment` is UTC ISO-8601, which sorts as text."""

        try:
            connection = self._open(create=True)
            assert connection is not None
            with closing(connection):
                row = connection.execute(
                    "INSERT INTO action (moment, receipt) VALUES (?, ?)", (moment, receipt)
                ).lastrowid
        except (OSError, sqlite3.Error) as error:
            return _error(ACTIVITY_UNWRITABLE, f"cannot record the action in {self.path}: {error}")
        return Ok(f"{self.path}#action-{row}")

    def actions(self, *, limit: int | None = None) -> Result[tuple[bytes, ...]]:
        """The recorded receipts, newest first; `limit` bounds what is read."""

        if limit is not None and (not isinstance(limit, int) or limit < 0):
            raise ValueError("an action limit must be a whole number of records")
        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(())
            with closing(connection):
                rows = connection.execute(
                    "SELECT receipt FROM action ORDER BY moment DESC, id DESC LIMIT ?",
                    (-1 if limit is None else limit,),
                ).fetchall()
        except (OSError, sqlite3.Error) as error:
            return _error(ACTIVITY_UNREADABLE, f"cannot read Activity from {self.path}: {error}")
        return Ok(tuple(bytes(row[0]) for row in rows))

    def record_use(self, use: ArtifactUse, moment: str) -> Result[str]:
        """Append one artifact use: names and the moment only."""

        if not isinstance(use, ArtifactUse):
            raise ValueError("only an artifact use is recorded")
        try:
            connection = self._open(create=True)
            assert connection is not None
            with closing(connection):
                row = connection.execute(
                    "INSERT INTO artifact_use (moment, harness, kind, name, project)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (moment, use.harness, use.kind.value, use.name, use.project),
                ).lastrowid
        except (OSError, sqlite3.Error) as error:
            return _error(ACTIVITY_UNWRITABLE, f"cannot record the use in {self.path}: {error}")
        return Ok(f"{self.path}#use-{row}")

    def usage_counts(self) -> Result[tuple[UsageCount, ...]]:
        """How often each name was used in each harness, and when last."""

        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(())
            with closing(connection):
                rows = connection.execute(
                    "SELECT harness, kind, name, COUNT(*), MAX(moment) FROM artifact_use"
                    " GROUP BY harness, kind, name"
                ).fetchall()
            counts = tuple(
                UsageCount(harness, UsageKind(kind), name, uses, last)
                for harness, kind, name, uses, last in rows
            )
        except (OSError, sqlite3.Error, ValueError) as error:
            return _error(ACTIVITY_UNREADABLE, f"cannot read usage from {self.path}: {error}")
        return Ok(counts)

    def forget_uses(self, harness: str) -> Result[int]:
        """Delete every use recorded for one harness; the number deleted."""

        try:
            connection = self._open(create=False)
            if connection is None:
                return Ok(0)
            with closing(connection):
                deleted = connection.execute(
                    "DELETE FROM artifact_use WHERE harness = ?", (harness,)
                ).rowcount
        except (OSError, sqlite3.Error) as error:
            return _error(ACTIVITY_UNWRITABLE, f"cannot forget usage in {self.path}: {error}")
        return Ok(deleted)
