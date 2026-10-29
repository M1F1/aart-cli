"""CP-48: Activity is one SQLite database -- newest actions first, uses appended, both private (§212)."""

from __future__ import annotations

import multiprocessing
import os
import sqlite3
import stat
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from aart_cli.domain.artifact_usage import ArtifactUse, UsageKind
from aart_cli.domain.result import Err, Ok
from aart_cli.io.activity_store import (
    ACTIVITY_DATABASE,
    ACTIVITY_UNREADABLE,
    SCHEMA_VERSION,
    ActivityDatabase,
)


def _record_uses(state: str, harness: str, count: int) -> None:
    database = ActivityDatabase(state)
    for index in range(count):
        written = database.record_use(
            ArtifactUse(harness, UsageKind.SKILL, f"skill-{index % 3}"),
            f"2026-10-28T10:{index % 60:02d}:00+00:00",
        )
        assert isinstance(written, Ok), written


class ActionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.state = str(Path(self._temporary.name) / "state")
        self.database = ActivityDatabase(self.state)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_reading_before_anything_was_recorded_creates_nothing(self) -> None:
        self.assertEqual(self.database.actions(), Ok(()))
        self.assertEqual(self.database.usage_counts(), Ok(()))
        self.assertEqual(self.database.forget_uses("claude"), Ok(0))
        self.assertFalse(Path(self.state).exists())

    def test_newest_first_and_a_limit_reads_only_the_newest(self) -> None:
        for moment, receipt in (
            ("2026-10-27T09:00:00+00:00", b"b"),
            ("2026-10-28T09:00:00+00:00", b"c"),
            ("2026-10-26T09:00:00+00:00", b"a"),
        ):
            self.assertIsInstance(self.database.record_action(moment, receipt), Ok)

        self.assertEqual(self.database.actions(), Ok((b"c", b"b", b"a")))
        self.assertEqual(self.database.actions(limit=2), Ok((b"c", b"b")))
        self.assertEqual(self.database.actions(limit=0), Ok(()))

    def test_the_database_is_its_owner_s_alone(self) -> None:
        self.database.record_action("2026-10-28T09:00:00+00:00", b"{}")

        mode = stat.S_IMODE(os.stat(self.database.path).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(Path(self.database.path).name, ACTIVITY_DATABASE)

    def test_a_database_another_version_wrote_is_reported_and_left_alone(self) -> None:
        self.database.record_action("2026-10-28T09:00:00+00:00", b"{}")
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        before = Path(self.database.path).read_bytes()

        read = self.database.actions()

        self.assertIsInstance(read, Err)
        assert isinstance(read, Err)
        self.assertEqual(read.diagnostics[0].code, ACTIVITY_UNREADABLE)
        self.assertIsInstance(self.database.record_action("2026-10-28T09:00Z", b"{}"), Err)
        self.assertEqual(Path(self.database.path).read_bytes(), before)


class UsesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.state = str(Path(self._temporary.name) / "state")
        self.database = ActivityDatabase(self.state)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_uses_are_counted_per_harness_and_name_with_the_latest(self) -> None:
        for harness, name, moment in (
            ("claude", "github", "2026-10-27T10:00:00+00:00"),
            ("claude", "github", "2026-10-28T10:00:00+00:00"),
            ("opencode", "github_search", "2026-10-26T10:00:00+00:00"),
        ):
            self.database.record_use(ArtifactUse(harness, UsageKind.MCP, name), moment)

        counts = self.database.usage_counts()

        assert isinstance(counts, Ok)
        self.assertEqual(
            sorted((item.harness, item.name, item.uses, item.last_used) for item in counts.value),
            [
                ("claude", "github", 2, "2026-10-28T10:00:00+00:00"),
                ("opencode", "github_search", 1, "2026-10-26T10:00:00+00:00"),
            ],
        )

    def test_forgetting_one_harness_leaves_the_other(self) -> None:
        self.database.record_use(ArtifactUse("claude", UsageKind.SKILL, "s"), "2026-10-28T10:00Z")
        self.database.record_use(ArtifactUse("opencode", UsageKind.SKILL, "s"), "2026-10-28T10:00Z")

        self.assertEqual(self.database.forget_uses("claude"), Ok(1))

        counts = self.database.usage_counts()
        assert isinstance(counts, Ok)
        self.assertEqual([item.harness for item in counts.value], ["opencode"])

    def test_two_harnesses_writing_at_once_lose_nothing(self) -> None:
        # The hooks of two harnesses are separate processes that may write in the same moment,
        # including the first writes, which race to create the schema -- so the race is run on
        # several new databases rather than once.
        context = multiprocessing.get_context("spawn")
        for round_ in range(4):
            state = str(Path(self.state) / str(round_))
            writers = [
                context.Process(target=_record_uses, args=(state, harness, 20))
                for harness in ("claude", "opencode", "claude", "opencode")
            ]
            for writer in writers:
                writer.start()
            for writer in writers:
                writer.join(60)
                self.assertEqual(writer.exitcode, 0)

            counts = ActivityDatabase(state).usage_counts()
            assert isinstance(counts, Ok)
            self.assertEqual(sum(item.uses for item in counts.value), 80)

    def test_a_writer_creating_the_database_waits_for_one_that_holds_it(self) -> None:
        # Deterministic form of the race above: SQLite answers a journal-mode change on a busy
        # database at once, without waiting, so creating the database must only ever wait.
        Path(self.state).mkdir(parents=True)
        holder = sqlite3.connect(self.database.path, isolation_level=None, check_same_thread=False)
        holder.execute("BEGIN IMMEDIATE")
        release = threading.Timer(0.3, holder.execute, ("COMMIT",))
        release.start()
        try:
            written = self.database.record_use(
                ArtifactUse("claude", UsageKind.SKILL, "s"), "2026-10-28T10:00Z"
            )
        finally:
            release.join()
            holder.close()

        self.assertIsInstance(written, Ok)

    def test_the_journal_is_write_ahead_once_nobody_else_holds_it(self) -> None:
        self.database.record_use(ArtifactUse("claude", UsageKind.SKILL, "s"), "2026-10-28T10:00Z")

        with closing(sqlite3.connect(self.database.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")


if __name__ == "__main__":
    unittest.main()
