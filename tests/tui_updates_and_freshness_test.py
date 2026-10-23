"""CP-41: the TUI says when something newer is approved, and where to go for it.

Before this, nothing in the application computed update availability. `update_available` was set by
tests and by nothing else, so Updates was always empty, the Dashboard always counted `0 update`, and
a newer approved version was invisible in the TUI even after a sync. The TUI also read only the local
snapshot when it started, so a Collection a maintainer had just approved stayed invisible until
somebody happened to press `s` on Registries, while every CLI read under the default `sync.mode =
auto` had already fetched it. And a Registry row said `connected` whatever its snapshot's state.

Product Specification §82, §83, §165.11 and §194 (D-478).
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import tempfile
import unittest
from dataclasses import replace
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_session import ConsumerMachine, with_offered_versions
from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    InstalledArtifactView,
    LifecycleDriftView,
    RegistryView,
    installed_cells,
    project_dashboard,
    project_installed_collection,
)
from aart_cli.application.intents import InstalledHealth, MemberHealth
from aart_cli.configuration.model import SourceKind
from aart_cli.domain.identifiers import SourceId
from aart_cli.domain.result import Ok
from aart_cli.io.source_store import publish_source_snapshot
from aart_cli.sources.model import (
    HealthStatus,
    SourceHealth,
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    frame,
    offered_versions,
    read_consumer_offers,
    render_dashboard,
    render_registry,
    screens_from,
)
from aart_cli.tui_marketplace import MarketplaceTarget
from tests.configured_installation_draft_e2e_test import _published_registry
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.placed_installation_e2e_test import AUTHORED_SKILL

TARGET = MarketplaceTarget(("claude",), "darwin", "project", "copy")
TODAY = dt.date(2026, 10, 23)
READY_ACTIONS = ("details", "verify", "configure", "uninstall")


def _installed(
    coordinate: str = "company/skill/notes@1.0.0",
    *,
    harness: str = "claude",
    health: str = "ready",
    drift: tuple[LifecycleDriftView, ...] = (),
) -> InstalledArtifactView:
    return InstalledArtifactView(coordinate, health, (), drift, READY_ACTIONS, harness=harness)


def _machine(*views: InstalledArtifactView, collections=()) -> ConsumerMachine:
    return ConsumerMachine(
        project_dashboard(views, registry_count=1, recent_activity=("installed 1 artifact",)),
        views,
        collections,
    )


class AnInstallationIsAnUpdateWhenSomethingNewerIsOffered(unittest.TestCase):
    def test_a_ready_installation_with_a_newer_offer_is_an_update(self) -> None:
        machine = with_offered_versions(_machine(_installed()), {"company/skill/notes": "1.0.1"})

        (view,) = machine.installed
        self.assertEqual((view.health, view.available), ("update", "1.0.1"))
        self.assertIn("update", view.actions)
        self.assertEqual((machine.dashboard.ready_count, machine.dashboard.update_count), (0, 1))

    def test_the_same_or_an_older_offer_leaves_it_ready(self) -> None:
        for offered in ("1.0.0", "0.9.9", "1.0.0-rc.1"):
            with self.subTest(offered=offered):
                machine = with_offered_versions(
                    _machine(_installed()), {"company/skill/notes": offered}
                )
                self.assertEqual(machine.installed[0].health, "ready")
                self.assertEqual(machine.dashboard.update_count, 0)

    def test_an_offer_from_another_registry_is_not_this_installation_s(self) -> None:
        machine = with_offered_versions(_machine(_installed()), {"other/skill/notes": "9.0.0"})

        self.assertEqual(machine.installed[0].health, "ready")

    def test_a_problem_outranks_an_update(self) -> None:
        broken = _installed(
            health="attention", drift=(LifecycleDriftView("harness:claude", "missing", True),)
        )
        machine = with_offered_versions(_machine(broken), {"company/skill/notes": "2.0.0"})

        self.assertEqual(machine.installed[0].health, "attention")
        self.assertEqual(machine.dashboard.update_count, 0)

    def test_a_collection_with_a_member_to_update_reads_update(self) -> None:
        member = _installed()
        kit = project_installed_collection(
            "company/collection/kit@1.0.0", (MemberHealth(member.row, InstalledHealth.READY),)
        )
        machine = with_offered_versions(
            _machine(member, collections=(kit,)), {"company/skill/notes": "1.1.0"}
        )

        self.assertEqual(machine.collections[0].health, "update")

    def test_nothing_offered_leaves_the_machine_as_it_was(self) -> None:
        machine = _machine(_installed())

        self.assertIs(with_offered_versions(machine, {}), machine)

    @given(
        st.tuples(*(st.integers(0, 30),) * 3),
        st.tuples(*(st.integers(0, 30),) * 3),
    )
    def test_it_is_an_update_exactly_when_the_offer_is_newer(self, installed, offered) -> None:
        version = ".".join(map(str, installed))
        machine = with_offered_versions(
            _machine(_installed(f"company/skill/notes@{version}")),
            {"company/skill/notes": ".".join(map(str, offered))},
        )

        self.assertEqual(machine.installed[0].health == "update", offered > installed)


class TheUpdateIsShownWithTheVersionItMovesTo(unittest.TestCase):
    def test_the_health_cell_names_the_newer_version(self) -> None:
        view = replace(_installed(), health="update", available="1.0.1")

        self.assertEqual(installed_cells(view, "Update")[0], "Update → 1.0.1")

    def test_a_ready_row_says_only_ready(self) -> None:
        self.assertEqual(installed_cells(_installed(), "Ready")[0], "Ready")


class _PublishedRegistry(unittest.TestCase):
    """One real registry snapshot, published the way sync publishes it."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_root = str(pathlib.Path(temporary.name) / "data")
        self.registry = configured_source("company", SourceKind.REGISTRY_GIT)
        candidate = make_source_candidate(
            source_instance_id(self.registry),
            self.registry.alias,
            "a" * 40,
            _published_registry(AUTHORED_SKILL),
        )
        self.assertIsInstance(candidate, Ok, getattr(candidate, "diagnostics", ()))
        published = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(self.registry)),
                ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
                90,
            )
        )
        self.assertIsInstance(published, Ok, getattr(published, "diagnostics", ()))
        self.effective = effective_configuration((self.registry,), default_registry="company")

    def _offers(self, **observed):
        read = read_consumer_offers(
            self.effective, data_root=self.data_root, target=TARGET, **observed
        )
        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        return read.value


class UpdatesListsInstallationsTheMarketplaceHasNewerVersionsOf(_PublishedRegistry):
    def _older(self, offers) -> tuple[InstalledArtifactView, str]:
        row = offers.artifacts[0].row
        return _installed(f"{row.source_alias}/{row.identity}@0.0.1"), row.version

    def test_the_offered_version_is_the_highest_per_artifact(self) -> None:
        offers = self._offers()
        row = offers.artifacts[0].row

        self.assertEqual(
            offered_versions(offers.artifacts)[f"{row.source_alias}/{row.identity}"], row.version
        )

    def test_updates_lists_the_installation_and_the_dashboard_counts_it(self) -> None:
        offers = self._offers()
        older, version = self._older(offers)

        screens = screens_from(
            _machine(older), marketplace=offers.artifacts, registries=offers.registries
        )

        self.assertEqual([item.row for item in screens.updatable], [older.row])
        self.assertEqual(screens.updatable[0].available, version)
        self.assertEqual(screens.dashboard.update_count, 1)

    def test_an_updates_row_is_the_installation_the_update_action_addresses(self) -> None:
        """The update action looks an installation up by its row (§169.3), never its coordinate."""

        offers = self._offers()
        older, _version = self._older(offers)
        source = CanonicalScreenSource(
            screens_from(
                _machine(older), marketplace=offers.artifacts, registries=offers.registries
            )
        )

        rows = source.rows(ConsumerUiState(ConsumerSession(ConsumerScreen.UPDATES)))

        self.assertEqual(rows, (older.row,))
        self.assertIn("#claude", rows[0])


class RegistryRowsSayWhenTheirSnapshotIsNotCurrent(unittest.TestCase):
    def _view(self, health: str, age: int | None = 7200) -> RegistryView:
        return RegistryView(
            "company",
            "connected",
            health,
            3,
            age,
            "registry-git",
            "https://git.example.test/registry.git",
            "main",
            "a" * 40,
            None,
            (),
        )

    def _drawn(self, health: str, age: int | None = 7200) -> str:
        return "\n".join(render_registry(self._view(health, age), ConsumerSettings().profile))

    def test_a_current_registry_adds_nothing_to_its_row(self) -> None:
        self.assertEqual(len(render_registry(self._view("healthy"), ConsumerSettings().profile)), 2)

    def test_newer_approved_content_on_the_origin_says_to_sync(self) -> None:
        drawn = self._drawn("not-synchronized")
        self.assertIn("newer approved content", drawn)
        self.assertIn("press s", drawn)

    def test_a_stale_snapshot_says_how_old_it_is(self) -> None:
        drawn = self._drawn("stale", 7200)
        self.assertIn("synced 2 h ago", drawn)
        self.assertIn("press s", drawn)

    def test_an_unreachable_origin_says_the_last_snapshot_is_shown(self) -> None:
        """§165.11: offline, and using the last synced snapshot."""

        drawn = self._drawn("could-not-check", 600)
        self.assertIn("could not reach", drawn)
        self.assertIn("synced 10 min ago", drawn)


class TheObservedHealthReachesTheRegistryRow(_PublishedRegistry):
    def _observed(self, status: HealthStatus) -> dict:
        from aart_cli.io.source_store import read_current_source
        from aart_cli.sources.model import CurrentSourceRequest

        paths = source_store_paths(self.data_root, source_instance_id(self.registry))
        current = read_current_source(CurrentSourceRequest(paths, self.registry.alias))
        self.assertIsInstance(current, Ok)
        return {self.registry.alias: SourceHealth(status, 30, current.value)}

    def test_without_an_observation_the_local_snapshot_answers(self) -> None:
        # The fixture's snapshot was published at epoch 90, so by its own age it is stale.
        (registry,) = self._offers().registries
        self.assertEqual((registry.availability, registry.health), ("connected", "stale"))

    def test_an_observed_origin_ahead_of_the_snapshot_is_drawn_on_the_row(self) -> None:
        offers = self._offers(observed=self._observed(HealthStatus.NOT_SYNCHRONIZED))

        (registry,) = offers.registries
        self.assertEqual(
            (registry.availability, registry.health), ("connected", "not-synchronized")
        )
        # What the snapshot approved is still offered: an origin ahead of it takes nothing away.
        self.assertTrue(offers.artifacts)

    def test_an_unreachable_origin_keeps_the_last_snapshot_connected(self) -> None:
        offers = self._offers(observed=self._observed(HealthStatus.CHECK_UNAVAILABLE))

        (registry,) = offers.registries
        self.assertEqual((registry.availability, registry.health), ("connected", "could-not-check"))
        self.assertTrue(offers.artifacts)


class TheMenuAndTheDashboardPointAtWhatIsNew(_PublishedRegistry):
    def _frame(self, *, update: bool, settings: ConsumerSettings | None = None, health="healthy"):
        offers = self._offers()
        registries = tuple(replace(item, health=health) for item in offers.registries)
        row = offers.artifacts[0].row
        version = "0.0.1" if update else row.version
        source = CanonicalScreenSource(
            screens_from(
                _machine(_installed(f"{row.source_alias}/{row.identity}@{version}")),
                marketplace=offers.artifacts,
                registries=registries,
            )
        )
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.DASHBOARD), settings=settings or ConsumerSettings()
        )
        return "\n".join(frame(source, replace(state, rows=source.rows(state))))

    def test_the_updates_entry_carries_a_count_when_there_is_one(self) -> None:
        drawn = self._frame(update=True)
        self.assertIn("Updates  ● 1", drawn)
        self.assertIn("1 update available — open Updates", drawn)

    def test_nothing_is_marked_when_nothing_is_newer(self) -> None:
        drawn = self._frame(update=False)
        self.assertNotIn("●", drawn)

    def test_turning_off_show_available_updates_hides_the_marks_not_the_list(self) -> None:
        """§161.10's switch governs the announcement; Updates itself still lists them."""

        drawn = self._frame(update=True, settings=ConsumerSettings(show_updates=False))
        self.assertNotIn("●", drawn)
        self.assertIn("1 update", drawn)

    def test_a_registry_with_newer_content_marks_registries(self) -> None:
        drawn = self._frame(update=False, health="not-synchronized")
        self.assertIn("Registries  ● 1 to sync", drawn)
        self.assertIn("1 registry has newer content — open Registries and press s", drawn)

    def test_the_counts_agree_in_number(self) -> None:
        view = replace(
            project_dashboard((), registry_count=2), update_count=2, registries_to_sync=2
        )
        drawn = "\n".join(render_dashboard(view))
        self.assertIn("2 updates available", drawn)
        self.assertIn("2 registries have newer content", drawn)


class TheApplicationLooksAtEachRegistryWhenItStarts(unittest.TestCase):
    """§194: the TUI observes its registries under `sync.mode` before it draws, as the CLI does."""

    def _compose(self, env, **kwargs):
        from aart_cli import tui

        composed = tui._canonical_consumer_actions(
            project=str(env.project), user_home=str(env.home), today=TODAY, **kwargs
        )
        self.assertIsInstance(composed, Ok, composed)
        return composed.value

    def test_each_registry_is_observed_and_announced_before_the_screen_is_taken(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        said: list[str] = []
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            with mock.patch(
                "aart_cli.io.configured_offers.observe_configured_source",
                side_effect=lambda source, **_: SourceHealth(
                    HealthStatus.CHECK_UNAVAILABLE, None, None
                ),
            ) as observe:
                actions = self._compose(env, observe=said.append)

        aliases = sorted(call.args[0].alias.value for call in observe.call_args_list)
        self.assertTrue(aliases)
        self.assertEqual(len(said), len(aliases))
        for alias, line in zip(aliases, sorted(said), strict=True):
            self.assertIn(alias, line)
        self.assertTrue(
            all(item.health == "could-not-check" for item in actions._context.offers.registries)
        )

    def test_without_observe_nothing_is_fetched(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            with mock.patch("aart_cli.io.configured_offers.observe_configured_source") as observe:
                self._compose(env)

        observe.assert_not_called()

    def test_the_launch_observes(self) -> None:
        from aart_cli import tui

        with (
            mock.patch.object(tui, "_seed_first_run"),
            mock.patch.object(tui, "_announce"),
            mock.patch.object(tui, "_curses_supported", return_value=False),
            mock.patch.object(tui, "_canonical_consumer_actions") as compose,
            mock.patch.object(tui, "run_consumer_text"),
        ):
            tui.run()

        self.assertIsNotNone(compose.call_args.kwargs.get("observe"))


if __name__ == "__main__":
    unittest.main()
