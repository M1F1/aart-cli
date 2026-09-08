"""Screen 21 can refresh a connected registry, and refreshing is not updating.

Add Registry fetches the first approved snapshot, so the first Marketplace install is complete.
After maintainers merge a newer registry commit the consumer has to observe it before Updates can
offer anything, and screen 21 offered no way to ask: `s` was interpreted only on Maintainer
authoring Sources, so the row's own advertised `sync` action was unreachable from the application
that draws it (B-084/QA-010).

Product Specification 161.7 states the boundary this file exists to hold: **registry sync is not
artifact update**.  Sync may discover `github-mcp 1.6`; an installed `1.5` stays untouched until a
separate update plan is accepted.  A refresh that quietly moved installed artifacts would be the
one thing screen 21 must never do.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import tempfile
import unittest
from unittest import mock

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.identifiers import SourceId
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.consumer_actions import RegistryConnectionSnapshot
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
    screens_from,
)
from agent_artifacts.tui_marketplace import MarketplaceTarget
from tests.configured_installation_draft_e2e_test import _published_registry
from tests.consumer_marketplace_composition_e2e_test import _machine
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.placed_installation_e2e_test import AUTHORED_SKILL
from tests.registry_maintenance_fixtures import native_snapshot

TARGET = MarketplaceTarget(("claude",), "darwin", "project", "copy")
TODAY = dt.date(2026, 9, 1)


def _state(screen: ConsumerScreen, **changes) -> ConsumerUiState:
    return ConsumerUiState(ConsumerSession(screen), **changes)


class RegistryRefreshInteractionTest(unittest.TestCase):
    """What the keys mean, decided by the one reducer rather than by a screen."""

    def test_a_focused_registry_row_offers_a_real_refresh_route(self) -> None:
        state = _state(ConsumerScreen.REGISTRIES, rows=("add-registry", "company"), cursor=1)

        event = key_event("s", state)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.REQUEST_ACTION)
        self.assertIs(event.action, ConsumerActionKind.REGISTRY_SYNC)

        reviewed, commands = reduce_consumer_ui(state, event)
        self.assertIs(reviewed.session.screen, ConsumerScreen.REGISTRY_SYNC)
        self.assertIs(reviewed.action, ConsumerActionKind.REGISTRY_SYNC)
        self.assertEqual(commands[0].focus, "company")

    def test_the_add_row_is_not_a_registry_and_refuses_to_be_refreshed(self) -> None:
        """`add-registry` is a button the list draws, not a subscription that can be fetched."""

        state = _state(ConsumerScreen.REGISTRIES, rows=("add-registry", "company"), cursor=0)

        event = key_event("s", state)
        self.assertIsNone(event)

    def test_refresh_is_not_offered_where_there_is_no_row_under_the_cursor(self) -> None:
        state = _state(ConsumerScreen.REGISTRIES)

        self.assertIsNone(key_event("s", state))

    def test_enter_on_the_review_confirms_rather_than_navigating_onward(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REGISTRY_SYNC, review_digest="d" * 64),
            action=ConsumerActionKind.REGISTRY_SYNC,
        )

        event = key_event("enter", state)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.CONFIRM_ACTION)

    def test_the_maintainer_source_sync_key_is_untouched(self) -> None:
        """One key means what the screen it was pressed on is about; 31 keeps its own action."""

        from agent_artifacts.application.consumer_views import ConsumerSettings
        from agent_artifacts.application.maintainer_views import MaintainerScreen

        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.SOURCES),
            settings=ConsumerSettings().with_maintainer_mode(True),
            rows=("authors",),
            cursor=0,
        )

        event = key_event("s", state)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.action, ConsumerActionKind.SOURCE_SYNC)


class RegistryRefreshReviewTest(unittest.TestCase):
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

    def test_the_review_names_the_registry_and_the_ref_it_will_fetch(self) -> None:
        offers = self._offers()
        source = CanonicalScreenSource(screens_from(_machine(), registries=offers.registries))
        state = _state(
            ConsumerScreen.REGISTRY_SYNC,
            focus="company",
            action=ConsumerActionKind.REGISTRY_SYNC,
        )

        drawn = "\n".join(frame(source, state))

        self.assertIn("company", drawn)
        self.assertIn(self.registry.ref or "", drawn)
        # 161.7's boundary, said where the operator decides, not only in a document.
        self.assertIn("not", drawn.lower())
        self.assertIn("update", drawn.lower())


class RegistryRefreshCompositionTest(unittest.TestCase):
    """The composed application, and the canonical transaction it is obliged to use."""

    def _composed(self, env):
        from agent_artifacts import tui

        composed = tui._canonical_consumer_actions(
            project=str(env.project), user_home=str(env.home), today=TODAY
        )
        self.assertIsInstance(composed, Ok, composed)
        return composed.value

    def test_the_composed_action_calls_the_canonical_sync_transaction(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        for alias in ("company", "platform-ai"):
            with self.subTest(alias=alias):
                with _environment() as env, mock.patch.dict(env.xdg, clear=False):
                    actions = self._composed(env)
                    refresher = actions._registry_refresh
                    self.assertIsNotNone(refresher)
                    with mock.patch(
                        "agent_artifacts.commands.source.sync_configured_sources",
                        return_value=Ok(()),
                    ) as synchronize:
                        refreshed = refresher(alias)  # type: ignore[misc]

                self.assertIsInstance(refreshed, Ok, refreshed)
                request = synchronize.call_args.args[0]
                # Two aliases, because with one the alias is provably free to be a constant: the
                # environment's own registry is the value a hardcoded closure would match.
                self.assertEqual(request.source_alias, alias)
                self.assertEqual(request.source_action, "sync")

    def test_a_refusal_leaves_the_previously_offered_marketplace_standing(self) -> None:
        """Last-known-good: a failed fetch must not take away what is already approved."""

        from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            actions = self._composed(env)
            before = actions._context.offers
            actions._registry_refresh = lambda alias: Err(
                (
                    Diagnostic(
                        DiagnosticCode("source-sync-failed"),
                        Severity.ERROR,
                        "the registry origin could not be reached",
                    ),
                )
            )
            prepared = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REGISTRY_SYNC,
                    focus="company",
                )
            )
            completed = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REGISTRY_SYNC,
                    review_digest=prepared.event.review_digest,
                )
            )

        self.assertIn("could not be reached", "\n".join(completed.source.screens.notice))
        self.assertIs(actions._context.offers, before)

    def test_a_refresh_never_moves_an_installed_artifact(self) -> None:
        """161.7: sync may discover a newer version; installed content stays where it is."""

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            actions = self._composed(env)
            installed_before = actions.source().screens.installed
            calls: list[str] = []

            def refresh(alias: str):
                calls.append(alias)
                return Ok(
                    RegistryConnectionSnapshot(
                        actions._context.effective,
                        actions._context.offers,
                        actions._context.maintainer,
                    )
                )

            actions._registry_refresh = refresh
            prepared = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REGISTRY_SYNC,
                    focus="company",
                )
            )
            self.assertTrue(prepared.event.review_digest)
            completed = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REGISTRY_SYNC,
                    review_digest=prepared.event.review_digest,
                )
            )

        self.assertEqual(calls, ["company"])
        self.assertEqual(completed.source.screens.installed, installed_before)

    def test_an_authoring_source_row_is_refused_before_the_transaction(self) -> None:
        """INV-199: a Source holds Candidates a maintainer promotes, not Marketplace availability.

        Offering the refresh there would advertise an effect the row cannot have, so the refusal
        is made where the action is prepared rather than left to the renderer to hide.
        """

        from dataclasses import replace

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            actions = self._composed(env)
            called: list[str] = []
            actions._registry_refresh = lambda alias: called.append(alias)  # type: ignore[assignment,func-returns-value]
            registry = actions._context.offers.registries[0]
            authoring = replace(
                registry,
                alias="authors",
                kind="source-git",
                is_registry=False,
                actions=("details",),
            )
            actions._context = replace(
                actions._context,
                offers=replace(
                    actions._context.offers,
                    registries=(registry, authoring),
                ),
            )

            prepared = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REGISTRY_SYNC,
                    focus="authors",
                )
            )

        self.assertEqual(called, [])
        self.assertEqual(prepared.event.review_digest, "")
        notice = "\n".join(prepared.source.screens.notice)
        self.assertIn("authoring Source", notice)
        self.assertIn("not a registry", notice)

    def test_an_unreviewed_execution_is_refused(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            actions = self._composed(env)
            called: list[str] = []
            actions._registry_refresh = lambda alias: called.append(alias)  # type: ignore[assignment,func-returns-value]

            completed = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REGISTRY_SYNC,
                    review_digest="f" * 64,
                )
            )

        self.assertEqual(called, [])
        self.assertTrue(completed.source.screens.notice)


class RegistryRefreshNavigationTest(unittest.TestCase):
    def test_the_refresh_review_is_a_lettered_sub_screen_of_twenty_one(self) -> None:
        self.assertTrue(ConsumerScreen.REGISTRY_SYNC.value.startswith("21"))

    def test_the_result_returns_to_the_registry_list(self) -> None:
        from agent_artifacts.application.consumer_ui import _ACTION_RESULT

        self.assertIs(
            _ACTION_RESULT[(ConsumerActionKind.REGISTRY_SYNC, ConsumerScreen.REGISTRY_SYNC)],
            ConsumerScreen.REGISTRIES,
        )

    def test_the_review_screen_is_reachable_from_the_registry_list(self) -> None:
        from agent_artifacts.application.consumer_views import navigation_targets

        self.assertIn(
            ConsumerScreen.REGISTRY_SYNC,
            navigation_targets(ConsumerScreen.REGISTRIES),
        )


if __name__ == "__main__":
    unittest.main()


_ = ConsumerUiEvent
