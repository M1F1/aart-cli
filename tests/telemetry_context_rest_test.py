"""CP-62: the rest of contract revision 7 an install, update or removal says (§213, D-519).

An event says the TUI or the command line, how long the action took, the version an update
replaced, the package, how many inputs it asked for, and whether it came directly or with the
Collection somebody chose. A plugin's skill says how and where, never the plugin's package, inputs
or Collection. Nothing of this ever costs the event (INV-340).
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    OwnershipView,
    project_installation_receipt,
    receipt_detail_from_data,
    receipt_detail_to_data,
)
from aart_cli.application.installation_proposal import artifact_receipt_for
from aart_cli.application.receipt_recording import record_installation_transaction
from aart_cli.application.telemetry_events import lifecycle_events
from aart_cli.domain.artifact_usage import (
    ArtifactUse,
    InstalledName,
    UsageKind,
    session_from_hook,
    session_pseudonym,
    use_from_hook,
    use_scope,
)
from aart_cli.domain.result import Ok
from aart_cli.domain.telemetry import CONTEXT_FOR, EventContext, lifecycle_event, use_event
from aart_cli.io import telemetry_sync
from aart_cli.io.activity_store import ActivityDatabase
from aart_cli.io.telemetry_store import TelemetryOutbox
from aart_cli.io.usage_hook import record
from tests.installation_transaction_receipt_test import MOMENT as RECEIPT_MOMENT
from tests.receipt_recording_test import FakeStore
from tests.telemetry_context_test import CONTEXT_FIELDS, ID, MOMENT, VALUES, _owned

COLLECTION = "corp/collection/starter-kit@3.0.0"
#: Everything an install, update or removal can say, as the receipt hands it over.
HOW = {
    "harness": "opencode",
    "scope": "project",
    "interface": "cli",
    "duration_ms": 1500,
    "previous_version": "6.1.0",
    "package_digest": VALUES["package_digest"],
    "configuration_inputs": 2,
    "credential_inputs": 1,
    "via": "collection",
    "collection": "starter-kit",
    "collection_version": "3.0.0",
}


def _ids():
    drawn = iter(range(100))
    return lambda: f"00000000-0000-4000-8000-{next(drawn):012d}"


class WhatALifecycleEventSaysTest(unittest.TestCase):
    def test_an_update_says_everything_the_receipt_knows(self) -> None:
        event = lifecycle_event(ID, MOMENT, "update", "corp/mcp/jira@6.2.0", **HOW)

        assert event is not None
        self.assertEqual(event.context, EventContext(registry="corp", **HOW))  # type: ignore[arg-type]

    def test_an_install_and_a_removal_say_only_what_their_type_holds(self) -> None:
        installed = lifecycle_event(ID, MOMENT, "install", "corp/mcp/jira@6.2.0", **HOW)
        removed = lifecycle_event(ID, MOMENT, "uninstall", "corp/mcp/jira@6.2.0", **HOW)

        assert installed is not None and removed is not None
        self.assertNotIn("previous_version", installed.context.document())
        self.assertIn("package_digest", installed.context.document())
        for gone in ("previous_version", "package_digest", "configuration_inputs"):
            with self.subTest(field=gone):
                self.assertNotIn(gone, removed.context.document())
        self.assertEqual(removed.context.interface, "cli")
        self.assertEqual(removed.context.collection, "starter-kit")

    def test_the_registry_is_always_the_coordinate_s(self) -> None:
        event = lifecycle_event(ID, MOMENT, "install", "corp/mcp/jira@6.2.0", registry="other")

        assert event is not None
        self.assertEqual(event.context.registry, "corp")

    def test_a_collection_is_said_only_beside_via_collection(self) -> None:
        direct = lifecycle_event(
            ID, MOMENT, "install", "corp/mcp/jira@6.2.0", **(HOW | {"via": "direct"})
        )
        unnamed = lifecycle_event(
            ID, MOMENT, "install", "corp/mcp/jira@6.2.0", **(HOW | {"collection": None})
        )

        assert direct is not None and unnamed is not None
        self.assertEqual(direct.context.via, "direct")
        self.assertIsNone(direct.context.collection)
        self.assertIsNone(direct.context.collection_version)
        # A Collection nobody can name says neither it nor that it came with one.
        self.assertIsNone(unnamed.context.via)
        self.assertIsNone(unnamed.context.collection_version)

    def test_a_plugin_s_skill_says_how_and_where_but_not_the_plugin_s_package(self) -> None:
        event = lifecycle_event(
            ID, MOMENT, "update", "corp/plugin/superpowers@7.0.0", member="brainstorming", **HOW
        )

        assert event is not None
        self.assertEqual(
            (event.artifact_type, event.artifact_id), ("skill", "superpowers:brainstorming")
        )
        self.assertEqual(
            event.context,
            EventContext(
                harness="opencode",
                scope="project",
                registry="corp",
                interface="cli",
                duration_ms=1500,
                previous_version="6.1.0",
                via="plugin",
            ),
        )

    @given(
        st.sampled_from(("install", "update", "downgrade", "uninstall")),
        st.dictionaries(
            st.sampled_from(CONTEXT_FIELDS),
            st.one_of(
                st.none(),
                st.booleans(),
                st.integers(min_value=-10, max_value=10**9),
                st.text(max_size=80),
                st.sampled_from(tuple(VALUES.values()) + ("direct", "collection", "cli")),
            ),
        ),
        st.one_of(st.none(), st.sampled_from(("brainstorming", "x"))),
    )
    def test_what_it_says_of_where_and_how_never_costs_the_event(
        self, intent: str, said: dict, member: str | None
    ) -> None:
        event = lifecycle_event(
            ID, MOMENT, intent, "corp/plugin/superpowers@7.0.0", member=member, **said
        )

        assert event is not None
        # Whatever it says is something it was told, in a field its type holds.
        told = said | {"registry": "corp"} | ({} if member is None else {"via": "plugin"})
        for name, value in event.context.document().items():
            self.assertIn(event.event_type, CONTEXT_FOR[name])
            self.assertEqual(value, told[name])


class HowItCameTest(unittest.TestCase):
    def setUp(self) -> None:
        outcome, _ = _owned()
        self.receipt = project_installation_receipt(outcome, recorded_at=RECEIPT_MOMENT)

    def _sent(self, ownership: tuple[OwnershipView, ...], collections: tuple[str, ...]):
        first, *rest = self.receipt.artifacts
        assert self.receipt.selection is not None
        receipt = replace(
            self.receipt,
            artifacts=(replace(first, ownership=ownership), *rest),
            selection=replace(self.receipt.selection, collections=collections),
        )
        return lifecycle_events(receipt, _ids())[0].context

    def test_the_collection_somebody_chose_is_said_with_its_version(self) -> None:
        context = self._sent((OwnershipView("collection", COLLECTION),), (COLLECTION,))

        self.assertEqual(
            (context.via, context.collection, context.collection_version),
            ("collection", "starter-kit", "3.0.0"),
        )

    def test_an_artifact_picked_by_hand_is_direct_even_when_a_collection_owns_it(self) -> None:
        context = self._sent(
            (OwnershipView("collection", COLLECTION), OwnershipView("direct", "selection")), ()
        )

        self.assertEqual((context.via, context.collection), ("direct", None))

    def test_a_dependency_and_a_removal_say_neither(self) -> None:
        dependency = self._sent((OwnershipView("dependency", "corp/mcp/other@1.0.0"),), ())
        removal = lifecycle_events(replace(self.receipt, selection=None), _ids())[0].context

        self.assertIsNone(dependency.via)
        self.assertIsNone(removal.via)


class WhatTheTransactionRecordsTest(unittest.TestCase):
    def test_the_receipt_holds_the_package_counts_interface_and_duration(self) -> None:
        outcome, planned = _owned()
        first, second = planned
        recorded = record_installation_transaction(
            outcome,
            recorded_at=RECEIPT_MOMENT,
            store=FakeStore(),
            receipts=tuple((item.coordinate, artifact_receipt_for(item)) for item in planned),
            inputs=(((first.coordinate, first.owner), (2, 1)),),
            interface="tui",
            elapsed=lambda: 4321,
        )

        assert isinstance(recorded, Ok), getattr(recorded, "diagnostics", ())
        receipt = recorded.value.receipt
        by_coordinate = {item.coordinate: item for item in receipt.artifacts}
        mine = by_coordinate[str(first.coordinate)]
        other = by_coordinate[str(second.coordinate)]
        self.assertEqual((receipt.interface, receipt.duration_ms), ("tui", 4321))
        self.assertEqual(mine.package_digest, str(first.artifact.version.object_digest))
        self.assertEqual((mine.configuration_inputs, mine.credential_inputs), (2, 1))
        # The counts are the installation's own: another installation is not given them.
        self.assertEqual((other.configuration_inputs, other.credential_inputs), (None, None))
        self.assertEqual(receipt_detail_from_data(receipt_detail_to_data(receipt)), Ok(receipt))

        event = lifecycle_events(receipt, _ids())[0]
        self.assertEqual(
            {
                name: event.context.document().get(name)
                for name in (
                    "interface",
                    "duration_ms",
                    "package_digest",
                    "configuration_inputs",
                    "credential_inputs",
                )
            },
            {
                "interface": "tui",
                "duration_ms": 4321,
                "package_digest": str(first.artifact.version.object_digest),
                "configuration_inputs": 2,
                "credential_inputs": 1,
            },
        )

    def test_without_a_clock_or_an_interface_the_receipt_says_neither(self) -> None:
        outcome, planned = _owned()
        recorded = record_installation_transaction(
            outcome,
            recorded_at=RECEIPT_MOMENT,
            store=FakeStore(),
            receipts=tuple((item.coordinate, artifact_receipt_for(item)) for item in planned),
        )

        assert isinstance(recorded, Ok), getattr(recorded, "diagnostics", ())
        self.assertEqual(
            (recorded.value.receipt.interface, recorded.value.receipt.duration_ms), (None, None)
        )
        self.assertNotIn("interface", receipt_detail_to_data(recorded.value.receipt))


KEY = bytes(range(32))
UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
JIRA = "corp/mcp/jira-mcp"
#: Jira installed for the user in both harnesses, and for one project in opencode too.
INSTALLED = (
    InstalledName("opencode", UsageKind.MCP, "jira", JIRA, "2.0.1", None, "user"),
    InstalledName("opencode", UsageKind.MCP, "jira", JIRA, "2.0.1", None, "project", "/work/app"),
    InstalledName("claude", UsageKind.MCP, "jira", JIRA, "2.0.1", None, "user"),
    InstalledName(
        "opencode",
        UsageKind.SKILL,
        "notes",
        "corp/skill/notes",
        "1.0.0",
        None,
        "project",
        "/work/app",
    ),
)


class TheSessionTest(unittest.TestCase):
    def test_each_harness_s_session_is_read_from_its_own_field(self) -> None:
        self.assertEqual(session_from_hook("claude", {"session_id": "abc-1"}), "abc-1")
        self.assertEqual(session_from_hook("opencode", {"session": "ses_9"}), "ses_9")
        self.assertIsNone(session_from_hook("opencode", {"session_id": "abc-1"}))
        self.assertIsNone(session_from_hook("tabnine", {"session": "x"}))
        self.assertIsNone(session_from_hook("claude", {"session_id": 7}))

    @given(st.text(min_size=1, max_size=200).filter(lambda value: value.strip() == value))
    def test_a_pseudonym_is_a_uuid_stable_for_its_session_and_never_the_session(
        self, session: str
    ) -> None:
        if not session.isprintable():
            return
        pseudonym = session_pseudonym(KEY, "opencode", session)

        self.assertRegex(pseudonym, UUID)
        self.assertNotEqual(pseudonym, session)
        self.assertEqual(pseudonym, session_pseudonym(KEY, "opencode", session))
        self.assertNotEqual(pseudonym, session_pseudonym(KEY, "claude", session))
        self.assertNotEqual(pseudonym, session_pseudonym(bytes(32), "opencode", session))

    def test_two_sessions_are_two_pseudonyms_and_a_short_key_is_refused(self) -> None:
        self.assertNotEqual(
            session_pseudonym(KEY, "claude", "a"), session_pseudonym(KEY, "claude", "b")
        )
        with self.assertRaises(ValueError):
            session_pseudonym(KEY[:16], "claude", "a")

    def test_a_use_holds_only_a_pseudonym(self) -> None:
        with self.assertRaises(ValueError):
            ArtifactUse("claude", UsageKind.MCP, "jira", session="abc-1")


class WhatAUseSaysTest(unittest.TestCase):
    def test_a_use_in_the_project_an_installation_is_for_says_project(self) -> None:
        resolved = INSTALLED[0]

        self.assertEqual(use_scope(resolved, "/work/app", INSTALLED), "project")
        self.assertEqual(use_scope(resolved, "/work/app/src", INSTALLED), "project")
        self.assertEqual(use_scope(resolved, "/work/application", INSTALLED), "user")
        self.assertEqual(use_scope(resolved, "", INSTALLED), "user")

    def test_a_project_installation_elsewhere_says_no_scope(self) -> None:
        notes = INSTALLED[3]

        self.assertEqual(use_scope(notes, "/work/app", INSTALLED), "project")
        self.assertIsNone(use_scope(notes, "/work/other", INSTALLED))

    def test_an_opencode_use_says_its_tool_session_and_scope_but_not_its_project(self) -> None:
        pseudonym = session_pseudonym(KEY, "opencode", "ses_1")
        event = use_event(
            ID,
            MOMENT,
            "opencode",
            UsageKind.MCP,
            "jira_create_issue",
            INSTALLED,
            session=pseudonym,
            project="/work/app",
        )

        assert event is not None
        self.assertEqual(
            event.context,
            EventContext(scope="project", registry="corp", tool="create_issue", session=pseudonym),
        )
        self.assertNotIn("/work/app", json.dumps(event.document(revision=7)))

    def test_a_claude_code_use_says_the_tool_its_hook_named(self) -> None:
        use = use_from_hook("claude", {"tool_name": "mcp__jira__create_issue", "cwd": "/work"})
        assert use is not None

        event = use_event(ID, MOMENT, "claude", use.kind, use.name, INSTALLED, tool=use.tool)
        unmanaged = use_event(
            ID, MOMENT, "claude", UsageKind.MCP, "github", INSTALLED, unmanaged=True, tool="search"
        )

        assert event is not None and unmanaged is not None
        self.assertEqual(
            event.context, EventContext(scope="user", registry="corp", tool="create_issue")
        )
        self.assertEqual(unmanaged.context, EventContext(tool="search"))


class TheHookKeepsAPseudonymTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.home, True)
        self.state = str(Path(self.home) / "state")

    def _record(self, harness: str, **payload: object) -> None:
        self.assertTrue(record(harness, self.home, json.dumps(payload).encode()))

    def test_a_session_is_kept_as_one_pseudonym_and_its_id_is_nowhere(self) -> None:
        raw = "6f1d2c3b-aaaa-4bbb-8ccc-0123456789ab"
        for _ in range(2):
            self._record("claude", tool_name="mcp__jira__create_issue", session_id=raw, cwd="/w")
        self._record("claude", tool_name="mcp__jira__search", session_id="another", cwd="/w")

        rows = ActivityDatabase(self.state).use_rows()
        assert isinstance(rows, Ok)
        uses = [use for _, _, use in rows.value]
        self.assertEqual([use.tool for use in uses], ["create_issue", "create_issue", "search"])
        self.assertEqual(uses[0].session, uses[1].session)
        self.assertNotEqual(uses[0].session, uses[2].session)
        self.assertRegex(uses[0].session, UUID)
        stored = b"".join(path.read_bytes() for path in Path(self.state).iterdir())
        self.assertNotIn(raw.encode(), stored)
        self.assertNotIn(b"another", stored)

    def test_without_a_session_a_use_is_still_recorded(self) -> None:
        self._record("opencode", tool="skill", skill="notes", directory="/w")

        rows = ActivityDatabase(self.state).use_rows()
        assert isinstance(rows, Ok)
        self.assertEqual(rows.value[0][2].session, "")

    def test_an_older_database_gains_the_columns_and_keeps_its_uses(self) -> None:
        Path(self.state).mkdir()
        path = Path(self.state) / "activity.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.executescript(
                "CREATE TABLE action (id INTEGER PRIMARY KEY, moment TEXT NOT NULL,"
                " receipt BLOB NOT NULL);"
                "CREATE TABLE artifact_use (id INTEGER PRIMARY KEY, moment TEXT NOT NULL,"
                " harness TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,"
                " project TEXT NOT NULL);"
                "INSERT INTO artifact_use (moment, harness, kind, name, project)"
                " VALUES ('2026-11-01T00:00:00+00:00', 'claude', 'skill', 'notes', '/w');"
                "PRAGMA user_version = 1;"
            )
        connection.close()

        self._record("opencode", tool="jira_search", directory="/w", session="ses_1")

        rows = ActivityDatabase(self.state).use_rows()
        assert isinstance(rows, Ok)
        self.assertEqual(
            [(use.name, use.session != "") for _, _, use in rows.value],
            [("notes", False), ("jira_search", True)],
        )

    def test_the_outbox_keeps_a_use_s_session_tool_and_project_to_send(self) -> None:
        outbox = TelemetryOutbox(self.state)
        self.assertIsInstance(outbox.enable("http://127.0.0.1:9", CLIENT_ID), Ok)
        with mock.patch.object(telemetry_sync, "spawn_sync", return_value=False):
            self._record("claude", tool_name="mcp__jira__create_issue", session_id="s", cwd="/w/p")

        waiting = outbox.waiting(limit=10)
        assert isinstance(waiting, Ok)
        (item,) = waiting.value
        self.assertEqual((item.name, item.tool, item.project), ("jira", "create_issue", "/w/p"))
        self.assertRegex(item.session, UUID)


CLIENT_ID = "0b6f4d1e-8f8a-4a43-9a52-2f0f5d0f6a11"


if __name__ == "__main__":
    unittest.main()
