"""The canonical shell's Marketplace is the configured one, read from disk.

Screens 02 to 04a were reachable but empty in the composed application: `_canonical_consumer_source`
read the machine and handed `screens_from` no offers at all, so a person opening the canonical shell
saw a Marketplace with nothing in it while their configured sources sat on disk beside it.

Reading offers is an effect, so it happens once at composition rather than inside a draw (D-051).
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from agent_artifacts.application.consumer_views import ConsumerScreen
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.identifiers import SourceId
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    read_consumer_offers,
    run_consumer_shell,
    screens_from,
)
from agent_artifacts.tui_marketplace import MarketplaceTarget
from tests.consumer_session_e2e_test import TODAY
from tests.consumer_shell_test import FakeTerminal, _at
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.registry_maintenance_fixtures import native_snapshot

TARGET = MarketplaceTarget(("claude",), "darwin", "project", "copy")


def _machine():
    from agent_artifacts.application.consumer_session import assemble_consumer_machine

    return assemble_consumer_machine((), today=TODAY)


class ComposedMarketplaceTest(unittest.TestCase):
    """One configured source, published the way sync publishes it, then browsed."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_root = str(pathlib.Path(temporary.name) / "data")
        self.source = configured_source("team", SourceKind.SOURCE_GIT)
        candidate = make_source_candidate(
            source_instance_id(self.source),
            self.source.alias,
            "a" * 40,
            native_snapshot(),
        )
        self.assertIsInstance(candidate, Ok, getattr(candidate, "diagnostics", ()))
        published = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(self.source)),
                ValidatedSourceCandidate(candidate.value, SourceId("reference-native-source")),
                90,
            )
        )
        self.assertIsInstance(published, Ok, getattr(published, "diagnostics", ()))
        self.effective = effective_configuration((self.source,))

    def _offers(self):
        read = read_consumer_offers(self.effective, data_root=self.data_root, target=TARGET)
        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        return read.value

    def test_the_composed_marketplace_offers_what_the_configured_source_published(self) -> None:
        offers = self._offers()

        self.assertTrue(offers.artifacts, "a configured source published artifacts")
        self.assertTrue(
            all(entry.row.source_alias == self.source.alias for entry in offers.artifacts)
        )

    def test_a_person_browsing_the_composed_shell_sees_those_offers(self) -> None:
        """Not a projection a test built: the rows come from the source store on disk."""

        offers = self._offers()
        source = CanonicalScreenSource(
            screens_from(_machine(), marketplace=offers.artifacts, collections=offers.collections)
        )

        state = run_consumer_shell(
            source, FakeTerminal(ord("q")), state=_at(ConsumerScreen.MARKETPLACE)
        )

        self.assertEqual(
            state.rows,
            (
                *(entry.row.key for entry in offers.artifacts),
                *(entry.key for entry in offers.collections),
            ),
        )

    def test_an_unversioned_collection_is_declined_by_name_rather_than_dropped(self) -> None:
        """A Collection is told apart from another by its version, and this source published none.

        Offering it would mean inventing that version; omitting it silently would read as a source
        that published no Collections at all.
        """

        offers = self._offers()

        self.assertEqual(offers.collections, ())
        self.assertTrue(offers.declined)
        self.assertTrue(all("without one" in reason for reason in offers.declined))

    def test_no_source_configured_is_an_empty_marketplace_rather_than_a_failure(self) -> None:
        read = read_consumer_offers(
            effective_configuration(()), data_root=self.data_root, target=TARGET
        )

        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        self.assertEqual(
            (read.value.artifacts, read.value.collections, read.value.declined), ((), (), ())
        )


if __name__ == "__main__":
    unittest.main()
