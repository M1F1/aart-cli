"""Screen 21 lists the configured sources, and says why a native Source offers nothing.

Screen 21 was reachable but empty in the composed application, for the same reason screens 02–04a
once were: nothing on the composition path ever projected the configured sources into
``ConsumerScreens.registries``.  So a person opening the canonical shell saw no registries at all,
and the dashboard said "0 registries", while their configured registries sat on disk beside it.

The second half is B-038.  Under INV-026 a Marketplace projects configured *registries*, so an
enabled ``SourceKind.SOURCE_GIT`` or ``SOURCE_LOCAL`` contributes its health and offers nothing.
Listing it with a bare "0 artifacts" and an advertised sync that "refreshes Marketplace
availability" describes an emptiness as a fault and an action that cannot have that effect.  A
Source is where content comes from; a registry is what approves it, and the row has to say so.
"""

from __future__ import annotations

import builtins
import datetime as dt
import os
import pathlib
import tempfile
import unittest

from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    PresentationProfile,
    project_registries,
)
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
    frame,
    read_consumer_offers,
    render_registry,
    run_consumer_shell,
    screens_from,
)
from agent_artifacts.tui_marketplace import MarketplaceTarget
from tests.configured_installation_draft_e2e_test import _published_registry
from tests.consumer_marketplace_composition_e2e_test import _machine
from tests.consumer_shell_test import FakeTerminal, _at
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.placed_installation_e2e_test import AUTHORED_SKILL
from tests.registry_maintenance_fixtures import native_snapshot

TARGET = MarketplaceTarget(("claude",), "darwin", "project", "copy")
TODAY = dt.date(2026, 9, 1)


class ConfiguredRegistriesScreenTest(unittest.TestCase):
    """One registry and one authoring Source, published the way sync publishes them."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_root = str(pathlib.Path(temporary.name) / "data")
        self.registry = configured_source("company", SourceKind.REGISTRY_GIT)
        self.native = configured_source("authors", SourceKind.SOURCE_GIT)
        self._publish(self.registry, _published_registry(AUTHORED_SKILL), "company-registry")
        self._publish(self.native, native_snapshot(), "authors-source")
        self.effective = effective_configuration(
            (self.registry, self.native), default_registry="company"
        )

    def _publish(self, source, snapshot, declared: str) -> None:
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

    def _offers(self):
        read = read_consumer_offers(self.effective, data_root=self.data_root, target=TARGET)
        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        return read.value

    # -- the projection ------------------------------------------------------ #

    def test_the_projection_decides_which_rows_are_registries_rather_than_the_renderer(
        self,
    ) -> None:
        """A renderer that split `kind` on a string would re-derive this once per screen."""

        offers = self._offers()
        rows = {item.alias: item for item in offers.registries}

        self.assertEqual(sorted(rows), ["authors", "company"])
        self.assertTrue(rows["company"].is_registry)
        self.assertFalse(rows["authors"].is_registry)

    def test_a_local_source_is_not_a_registry_either(self) -> None:
        local = configured_source("workspace", SourceKind.SOURCE_LOCAL)
        rows = project_registries(
            self._catalog(effective_configuration((local,), default_registry=None))
        )

        self.assertEqual([item.is_registry for item in rows], [False])

    def _catalog(self, effective):
        from agent_artifacts.io.configured_offers import read_configured_marketplace

        read = read_configured_marketplace(effective, data_root=self.data_root)
        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        return read.value.catalog

    # -- what the row says --------------------------------------------------- #

    def test_a_native_source_row_says_why_it_offers_nothing_and_advertises_no_sync(self) -> None:
        offers = self._offers()
        native = next(item for item in offers.registries if item.alias == "authors")

        drawn = "\n".join(render_registry(native, PresentationProfile.FAST))

        self.assertIn("authoring Source", drawn)
        self.assertIn("promotes", drawn)
        self.assertNotIn("sync", drawn.lower())
        self.assertEqual(native.actions, ("details",))

    def test_a_registry_row_is_unchanged_and_still_separates_sync_from_update(self) -> None:
        offers = self._offers()
        registry = next(item for item in offers.registries if item.alias == "company")

        drawn = "\n".join(render_registry(registry, PresentationProfile.FAST))

        self.assertIn("does not update installed artifacts", drawn)
        self.assertNotIn("authoring Source", drawn)
        self.assertEqual(registry.actions, ("details", "sync"))

    # -- the composed shell -------------------------------------------------- #

    def test_screen_21_lists_the_configured_sources_in_the_composed_shell(self) -> None:
        """Not a projection a test built: the rows come from the source store on disk."""

        offers = self._offers()
        source = CanonicalScreenSource(
            screens_from(_machine(), marketplace=offers.artifacts, registries=offers.registries)
        )

        state = run_consumer_shell(
            source, FakeTerminal(ord("q")), state=_at(ConsumerScreen.REGISTRIES)
        )

        self.assertEqual(state.rows, ("add-registry", "company", "authors"))

    def test_the_dashboard_counts_registries_rather_than_every_configured_source(self) -> None:
        """ "2 registries" over one registry and one authoring Source would be a false count."""

        offers = self._offers()
        screens = screens_from(
            _machine(), marketplace=offers.artifacts, registries=offers.registries
        )

        self.assertEqual(screens.dashboard.registry_count, 1)

    def test_the_production_composition_puts_them_on_screen_21(self) -> None:
        """The composed application, not `screens_from` called by a test.

        Screen 21 was reachable and empty here: nothing on the composition path ever projected the
        configured sources, so `machine.registries` stayed the empty default it is assembled with.
        """

        from unittest import mock

        from agent_artifacts import tui
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env:
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project), user_home=str(env.home), today=TODAY
                )
                self.assertIsInstance(composed, Ok, composed)
                state = run_consumer_shell(
                    composed.value.source(),
                    FakeTerminal(ord("q")),
                    state=_at(ConsumerScreen.REGISTRIES),
                )

            self.assertEqual(state.rows, ("add-registry", "company"))
            self.assertEqual(composed.value.source().screens.dashboard.registry_count, 1)

    def test_drawing_screen_21_opens_no_file(self) -> None:
        offers = self._offers()
        source = CanonicalScreenSource(
            screens_from(_machine(), marketplace=offers.artifacts, registries=offers.registries)
        )
        state = run_consumer_shell(
            source, FakeTerminal(ord("q")), state=_at(ConsumerScreen.REGISTRIES)
        )
        opened: list[str] = []
        real_open = builtins.open

        def _record(file, *args, **kwargs):  # type: ignore[no-untyped-def]
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        builtins.open = _record  # noqa: A001 - narrow, restored immediately below
        try:
            drawn = "\n".join(frame(source, state))
        finally:
            builtins.open = real_open

        self.assertEqual(opened, [])
        self.assertIn("company", drawn)


if __name__ == "__main__":
    unittest.main()
