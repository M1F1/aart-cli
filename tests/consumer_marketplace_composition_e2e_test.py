"""The canonical shell's Marketplace is the configured registries, read from disk.

Screens 02 to 04a were reachable but empty in the composed application: composition read the
machine and handed `screens_from` no offers at all, so a person opening the canonical shell saw a
Marketplace with nothing in it while their configured registries sat on disk beside it.

Where the offers come from is INV-026: a Marketplace is a projection over configured *registries*,
and it does not redefine what a registry approved.  So an offer here is an approved published
version -- the same identity the configured install seam resolves against -- and a source that is
not a registry contributes its health and nothing else.  Offering more than that would advertise an
action the shell has to refuse afterwards.

Reading offers is an effect, so it happens once at composition rather than inside a draw (D-051).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import tempfile
import unittest

from agent_artifacts.application.consumer_views import ConsumerScreen
from agent_artifacts.application.promotion import (
    load_registry_versions,
    plan_registry_lifecycle,
    project_lifecycle_update,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.identifiers import SourceId
from agent_artifacts.domain.registry import PromotionMode, RegistryLifecycle
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
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
from tests.configured_installation_draft_e2e_test import (
    AUTHORED_MCP,
    _published_registries,
    _published_registry,
)
from tests.consumer_session_e2e_test import TODAY
from tests.consumer_shell_test import FakeTerminal, _at
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.placed_installation_e2e_test import AUTHORED_SKILL, SKILL_MANIFEST
from tests.registry_maintenance_fixtures import native_snapshot

TARGET = MarketplaceTarget(("claude",), "darwin", "project", "copy")
APPROVED = "company/skill/code-review@1.2.0"


def _at_version(version: str):
    """The same authored Skill, released again at a later version."""

    manifest = {**SKILL_MANIFEST, "artifact": {**SKILL_MANIFEST["artifact"], "version": version}}
    return tuple(
        (path, json.dumps(manifest)) if path.endswith("aart.json") else (path, content)
        for path, content in AUTHORED_SKILL
    )


def _machine():
    from agent_artifacts.application.consumer_session import assemble_consumer_machine

    return assemble_consumer_machine((), today=TODAY)


def _deprecated(snapshot: SourceSnapshot) -> SourceSnapshot:
    """The same registry, having since deprecated everything it approved.

    Deprecation goes through the real lifecycle path rather than an edited file, because what the
    consumer reads is a version record the registry rewrote, not a flag a test invented.
    """

    before = load_registry_versions(snapshot)
    assert isinstance(before, Ok), before
    after = tuple(
        dataclasses.replace(
            version,
            lifecycle=RegistryLifecycle.DEPRECATED,
            lifecycle_reason="superseded by the platform Skill",
        )
        for version in before.value
    )
    planned = plan_registry_lifecycle(snapshot, before.value, after)
    assert isinstance(planned, Ok), planned
    updated = project_lifecycle_update(snapshot, planned.value)
    assert isinstance(updated, Ok), updated
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, updated.value.entries)


class ComposedMarketplaceTest(unittest.TestCase):
    """One configured registry, published the way sync publishes it, then browsed."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_root = str(pathlib.Path(temporary.name) / "data")
        self.registry = configured_source("company", SourceKind.REGISTRY_GIT)
        self._publish(self.registry, _published_registry(AUTHORED_SKILL), "company-registry")
        self.effective = effective_configuration((self.registry,), default_registry="company")

    def _publish(self, source, snapshot: SourceSnapshot, declared: str) -> None:
        candidate = make_source_candidate(
            source_instance_id(source), source.alias, "a" * 40, snapshot
        )
        self.assertIsInstance(candidate, Ok, getattr(candidate, "diagnostics", ()))
        published = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(source)),
                ValidatedSourceCandidate(candidate.value, SourceId(declared)),
                90,
            )
        )
        self.assertIsInstance(published, Ok, getattr(published, "diagnostics", ()))

    def _offers(self, effective=None):
        read = read_consumer_offers(
            effective or self.effective, data_root=self.data_root, target=TARGET
        )
        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        return read.value

    def test_the_composed_marketplace_offers_what_the_configured_registry_approved(self) -> None:
        offers = self._offers()

        self.assertEqual([entry.row.key for entry in offers.artifacts], [APPROVED])
        self.assertEqual(offers.declined, ())

    def test_an_offer_carries_the_digests_the_registry_approved_it_under(self) -> None:
        """Not a row a test built: the identity is the one the install seam resolves against."""

        offers = self._offers()
        version = load_registry_versions(_published_registry(AUTHORED_SKILL))
        self.assertIsInstance(version, Ok, getattr(version, "diagnostics", ()))
        approved = version.value[0]
        row = offers.artifacts[0].row

        self.assertEqual(row.object_digest, str(approved.object_digest))
        self.assertEqual(row.payload_digest, str(approved.payload_digest))
        self.assertEqual(row.trust, "registry-reviewed")

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

    def test_a_deprecated_version_is_declined_by_name_rather_than_offered_silently(self) -> None:
        """The registry is steering people away from it and the row has nowhere to say so.

        Offering it anyway would be the Fast projection hiding material risk; dropping it without a
        word would read as a registry that approved nothing (B-037).
        """

        self._publish(
            self.registry,
            _deprecated(_published_registry(AUTHORED_SKILL)),
            "company-registry",
        )

        offers = self._offers()

        self.assertEqual(offers.artifacts, ())
        self.assertEqual(
            offers.declined,
            (f"{APPROVED}: deprecated by the registry, and this view cannot say so on the row",),
        )

    def test_a_referenced_version_is_declined_because_the_snapshot_holds_no_content(self) -> None:
        """INV-025: referenced mode is weaker, and the row is where that has to be visible.

        A referenced promotion writes a pointer instead of the payload, so this registry snapshot
        has nothing verified to install from. Offering the row anyway would advertise an install
        the seam beneath it refuses -- `configured_installation.py` will not materialise a
        referenced version -- and dropping it silently would read as a registry that approved
        nothing.
        """

        self._publish(
            self.registry,
            _published_registry(AUTHORED_SKILL, mode=PromotionMode.REFERENCED),
            "company-registry",
        )

        offers = self._offers()

        self.assertEqual(offers.artifacts, ())
        self.assertEqual(
            offers.declined,
            (f"{APPROVED}: referenced, so this registry snapshot holds no verified content",),
        )

    def test_a_row_stands_for_the_highest_approved_version_of_its_identity(self) -> None:
        """A row is an artifact, not a version list, and the graph keys one per identity.

        The highest approved SemVer is what an unconstrained request resolves to, so offering it is
        what makes what is browsed and what is installed the same thing. An older approved version
        is superseded rather than declined: it is still there, under the same row.
        """

        self._publish(
            self.registry,
            _published_registries(AUTHORED_SKILL, AUTHORED_MCP, _at_version("1.3.0")),
            "company-registry",
        )

        offers = self._offers()

        self.assertEqual(
            [entry.row.key for entry in offers.artifacts],
            ["company/mcp/github@1.5.0", "company/skill/code-review@1.3.0"],
        )
        self.assertEqual(offers.declined, ())

    def test_a_source_that_is_not_a_registry_is_configured_but_offers_nothing(self) -> None:
        """INV-026: a Marketplace projects registries. A Source is where content comes from."""

        native = configured_source("team", SourceKind.SOURCE_GIT)
        self._publish(native, native_snapshot(), "reference-native-source")

        offers = self._offers(
            effective_configuration((self.registry, native), default_registry="company")
        )

        self.assertEqual([str(entry.row.source_alias) for entry in offers.artifacts], ["company"])

    def test_no_source_configured_is_an_empty_marketplace_rather_than_a_failure(self) -> None:
        offers = self._offers(effective_configuration(()))

        self.assertEqual((offers.artifacts, offers.collections, offers.declined), ((), (), ()))


if __name__ == "__main__":
    unittest.main()
