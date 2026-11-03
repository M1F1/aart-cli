"""CP-62: the rest of contract revision 7 an install, update or removal says (§213, D-519).

An event says the TUI or the command line, how long the action took, the version an update
replaced, the package, how many inputs it asked for, and whether it came directly or with the
Collection somebody chose. A plugin's skill says how and where, never the plugin's package, inputs
or Collection. Nothing of this ever costs the event (INV-340).
"""

from __future__ import annotations

import unittest
from dataclasses import replace

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
from aart_cli.domain.result import Ok
from aart_cli.domain.telemetry import CONTEXT_FOR, EventContext, lifecycle_event
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


if __name__ == "__main__":
    unittest.main()
