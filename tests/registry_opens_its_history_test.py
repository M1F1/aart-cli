"""§202, INV-303, INV-304, D-488, D-489: only the Registry here opens, and it holds the commands.

The owner, with a large terminal font, found screen 46 unreadable: the Recent promotions of one
Registry pushed the next one off the screen. The list now keeps each Registry to a few lines and acts
on nothing. The Registry in the directory aart-cli runs in is marked and opens as screen 46k, with
its promotions read from its checkout and every command that acts on it. Any other Registry says
where to run aart-cli to work on it.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
import unittest
from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    project_dashboard,
)
from aart_cli.application.maintainer_views import (
    REGISTRY_WORKSPACE_READY_ROW,
    REGISTRY_WORKSPACE_ROW,
    MaintainerRegistryView,
    MaintainerRegistryWorkspaceView,
    MaintainerScreen,
    project_registry_workspace,
)
from aart_cli.configuration.model import SourceKind
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Ok
from aart_cli.io.maintainer_views import read_maintainer_views
from aart_cli.protocol.native_tree import SnapshotEntryKind
from aart_cli.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from aart_cli.tui_maintainer import HERE
from tests import maintainer_bulk_promotion_test
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.registry_readable_promotions_test import ReadablePromotionsTest

_COMMANDS = {
    "c": MaintainerScreen.CANDIDATES,
    "b": MaintainerScreen.REGISTRY_REBUILD,
    "s": MaintainerScreen.REPOSITORY_SCAN,
    "u": MaintainerScreen.ADOPTED_ARTIFACTS,
    "o": MaintainerScreen.COLLECTIONS,
}
_WORKSPACE_ROWS = (REGISTRY_WORKSPACE_ROW, REGISTRY_WORKSPACE_READY_ROW)


def _company() -> MaintainerRegistryView:
    """A Registry with two promotions: `mcp/jira-mcp@2.3.0`, then `mcp/github-mcp@1.0.0`."""

    fixture = ReadablePromotionsTest()
    fixture.setUp()
    return fixture.view


def _workspace(name: str = "company", *, ready: bool = False) -> MaintainerRegistryWorkspaceView:
    return project_registry_workspace(
        name, commit="abc1234", push_blockers=() if ready else ("nothing to push",)
    )


def _source(
    *registries: MaintainerRegistryView,
    here: MaintainerRegistryView | None = None,
    workspace: MaintainerRegistryWorkspaceView | None = None,
    bulk: bool = False,
) -> CanonicalScreenSource:
    policy = EffectivePolicy()
    views = maintainer_bulk_promotion_test._views(
        policy, maintainer_bulk_promotion_test._scan(("github-mcp",))
    )
    views = replace(
        views,
        registries=registries,
        bulk_promotions=views.bulk_promotions if bulk else (),
        registry_workspace_present=workspace is not None,
        registry_workspace=workspace,
        registry_here=here,
    )
    return CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
    )


def _subscribed() -> tuple[MaintainerRegistryView, ...]:
    company = _company()
    return (company, replace(company, alias="team", transactions=company.transactions[1:]))


def _standing_in_company(*, ready: bool = False, bulk: bool = False) -> CanonicalScreenSource:
    """aart-cli runs in company's checkout, and company and team are subscribed."""

    return _source(*_subscribed(), here=_company(), workspace=_workspace(ready=ready), bulk=bulk)


def _on_list(source: CanonicalScreenSource, row: str = "") -> ConsumerUiState:
    state = _reload(
        source,
        ConsumerUiState(
            ConsumerSession(MaintainerScreen.REGISTRY),
            settings=ConsumerSettings().with_maintainer_mode(True),
        ),
        entering=True,
    )
    return replace(state, cursor=state.rows.index(row)) if row else state


def _press(source: CanonicalScreenSource, state: ConsumerUiState, key: str) -> ConsumerUiState:
    event = key_event(key, state, detail=source.detail(state))
    assert event is not None, (key, state.session.screen)
    moved, _commands = reduce_consumer_ui(state, event)
    return _reload(source, moved, entering=True)


def _legend(source: CanonicalScreenSource, state: ConsumerUiState) -> set[str]:
    return {binding.key for binding in key_bindings(state, detail=source.detail(state))}


def _drawn(source: CanonicalScreenSource, state: ConsumerUiState) -> str:
    return "\n".join(frame(source, state))


def _opened(source: CanonicalScreenSource) -> ConsumerUiState:
    state = _on_list(source)
    assert state.current_row in _WORKSPACE_ROWS, state.rows
    return _press(source, state, "enter")


class TheListIsShortTest(unittest.TestCase):
    def test_the_list_names_no_promotion_and_counts_them(self) -> None:
        source = _standing_in_company()

        drawn = _drawn(source, _on_list(source))

        self.assertNotIn("Recent promotions", drawn)
        self.assertNotIn("mcp/jira-mcp@2.3.0", drawn)
        self.assertNotIn("Snapshot:", drawn)
        self.assertIn("company  ✓ Valid", drawn)
        self.assertIn("team  ✓ Valid", drawn)
        self.assertIn("Promotions recorded: 2", drawn)
        self.assertIn("Promotions recorded: 1", drawn)

    def test_the_registry_here_is_marked_and_no_other_is(self) -> None:
        source = _standing_in_company()

        lines = _drawn(source, _on_list(source)).splitlines()

        marked = [line for line in lines if HERE in line and not line.startswith("- ")]
        self.assertEqual(marked, [f"> company  abc1234  {HERE}"])

    def test_verbose_on_the_list_spells_out_digests_but_names_no_promotion(self) -> None:
        source = _standing_in_company()
        state = _on_list(source, "team")
        verbose = replace(
            state, session=replace(state.session, profile=PresentationProfile.MORE_INFO)
        )

        drawn = _drawn(source, verbose)

        self.assertIn(f"Snapshot: {_company().snapshot}", drawn)
        self.assertNotIn("Promotion 1", drawn)
        self.assertNotIn("mcp/jira-mcp@2.3.0", drawn)

    @settings(max_examples=25, deadline=None)
    @given(st.integers(min_value=1, max_value=12))
    def test_the_list_does_not_grow_with_a_registry_s_history(self, repeats: int) -> None:
        """However many promotions a Registry records, its rows on the list are as many."""

        company = _company()
        longer = replace(company, transactions=company.transactions * repeats)
        short = _drawn(_source(company), _on_list(_source(company))).splitlines()
        long = _drawn(_source(longer), _on_list(_source(longer))).splitlines()

        self.assertEqual(len(long), len(short))
        self.assertEqual(
            [line for line in long if line not in short],
            [f"    Promotions recorded: {2 * repeats}"] if repeats > 1 else [],
        )


class TheListActsOnNothingTest(unittest.TestCase):
    def test_no_command_is_offered_or_taken_on_any_row(self) -> None:
        source = _standing_in_company(ready=True)
        for row in _on_list(source).rows:
            state = _on_list(source, row)
            with self.subTest(row=row):
                self.assertEqual(_legend(source, state) & {*_COMMANDS, "p", "n"}, set())
                for key in (*_COMMANDS, "p", "n"):
                    pressed = key_event(key, state, detail=source.detail(state))
                    self.assertTrue(pressed is None or pressed.screen is None, (key, pressed))

    def test_another_registry_does_not_open_and_says_where_to_run(self) -> None:
        source = _standing_in_company()
        state = _on_list(source, "team")

        self.assertIsNone(source.detail(state))
        self.assertNotIn("Enter", _legend(source, state))
        self.assertIn(
            "- to work on team, run aart-cli in its Registry checkout.", _drawn(source, state)
        )

    def test_the_subscription_of_the_registry_here_points_to_its_row(self) -> None:
        source = _standing_in_company()
        state = _on_list(source, "company")

        self.assertIsNone(source.detail(state))
        self.assertIn(
            f"company is the Registry in this directory: open it from the row {HERE}.",
            _drawn(source, state),
        )

    def test_initialize_is_offered_only_where_no_registry_is_here(self) -> None:
        nowhere = _source(*_subscribed())
        state = _on_list(nowhere, "team")

        self.assertIn("n", _legend(nowhere, state))
        self.assertIs(_press(nowhere, state, "n").session.screen, MaintainerScreen.REGISTRY_INIT)
        for row in state.rows:
            self.assertIsNone(nowhere.detail(_on_list(nowhere, row)))


class EnterOpensTheRegistryHereTest(unittest.TestCase):
    def test_enter_opens_the_registry_here_with_its_promotions(self) -> None:
        source = _standing_in_company()

        opened = _opened(source)
        drawn = _drawn(source, opened)

        self.assertIs(opened.session.screen, MaintainerScreen.REGISTRY_DETAILS)
        self.assertTrue(drawn.startswith("AART / Registry / This Registry"), drawn.splitlines()[0])
        self.assertIn(f"> company  abc1234  {HERE}", drawn)
        self.assertIn("Recent promotions (newest first):", drawn)
        self.assertIn("mcp/jira-mcp@2.3.0", drawn)
        self.assertNotIn("team", drawn)

    def test_the_history_shown_is_the_checkout_s_not_a_subscription_s(self) -> None:
        here = replace(_company(), transactions=_company().transactions[:1])
        source = _source(*_subscribed(), here=here, workspace=_workspace())

        drawn = _drawn(source, _opened(source))

        self.assertIn("mcp/jira-mcp@2.3.0", drawn)
        self.assertNotIn("mcp/github-mcp@1.0.0", drawn)

    def test_verbose_gives_where_it_stands_and_every_digest(self) -> None:
        source = _standing_in_company()
        opened = _opened(source)
        verbose = replace(
            opened, session=replace(opened.session, profile=PresentationProfile.MORE_INFO)
        )

        drawn = _drawn(source, verbose)

        self.assertIn(_company().transactions[0].snapshot_after, drawn)
        self.assertIn("Push unavailable:", drawn)


class ItsCommandsAreThereTest(unittest.TestCase):
    def test_every_command_acting_on_it_is_offered_and_opens_its_screen(self) -> None:
        source = _standing_in_company()
        opened = _opened(source)
        legend = _legend(source, opened)

        self.assertNotIn("n", legend)
        self.assertNotIn("p", legend)
        for key, target in _COMMANDS.items():
            with self.subTest(key=key):
                self.assertIn(key, legend)
                self.assertIs(_press(source, opened, key).session.screen, target)

    def test_push_is_offered_when_it_is_ready(self) -> None:
        source = _standing_in_company(ready=True)
        opened = _opened(source)

        self.assertIn("p", _legend(source, opened))
        self.assertIs(_press(source, opened, "p").session.screen, MaintainerScreen.REGISTRY_PUSH)

    def test_o_opens_the_collections_of_the_registry_here(self) -> None:
        source = _standing_in_company()

        drawn = _drawn(source, _press(source, _opened(source), "o"))

        self.assertIn("collections of Registry company", drawn)
        self.assertNotIn("team", drawn)

    def test_enter_opens_bulk_promotion_only_when_ready_candidates_wait(self) -> None:
        waiting = _standing_in_company(bulk=True)
        idle = _standing_in_company()

        self.assertIs(
            _press(waiting, _opened(waiting), "enter").session.screen,
            MaintainerScreen.BULK_PROMOTION,
        )
        self.assertIsNone(idle.detail(_opened(idle)))


class BackKeepsTheRegistryTest(unittest.TestCase):
    def test_esc_returns_to_the_list_on_the_registry_here(self) -> None:
        source = _standing_in_company()

        back = _press(source, _opened(source), "escape")

        self.assertIs(back.session.screen, MaintainerScreen.REGISTRY)
        self.assertIn(back.current_row, _WORKSPACE_ROWS)

    def test_esc_from_a_command_returns_to_the_registry_here(self) -> None:
        source = _standing_in_company()
        for key in _COMMANDS:
            with self.subTest(key=key):
                back = _press(source, _press(source, _opened(source), key), "escape")

                self.assertIs(back.session.screen, MaintainerScreen.REGISTRY_DETAILS)
                self.assertIn("Recent promotions", _drawn(source, back))


def _git(root: pathlib.Path, *arguments: str) -> None:
    subprocess.run(("git", "-C", str(root), *arguments), check=True, capture_output=True)


class TheCheckoutIsReadTest(unittest.TestCase):
    def test_the_registry_here_is_what_its_checkout_holds(self) -> None:
        """Read from disk, the promotions a checkout committed are the Registry here's history."""

        fixture = ReadablePromotionsTest()
        fixture.setUp()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve() / "registry"
            root.mkdir()
            for entry in fixture.registry.entries:
                path = root.joinpath(*str(entry.path).split("/"))
                if entry.kind is SnapshotEntryKind.DIRECTORY:
                    path.mkdir(parents=True, exist_ok=True)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(entry.content)
            marker = root / "aart-cli-registry.json"
            if not marker.exists():
                marker.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "protocol_version": 1,
                            "registry_id": "company",
                            "display_name": "Company",
                            "requires_aart": {"min_inclusive": "1.0.0", "max_exclusive": "2.0.0"},
                            "required_capabilities": ["lockfile-v1", "registry-entry-v1"],
                            "default_channel": "main",
                            "services": {},
                        }
                    ),
                    encoding="utf-8",
                )
            _git(root, "init", "-b", "main")
            _git(
                root,
                "-c",
                "user.name=AART Test",
                "-c",
                "user.email=aart@example.invalid",
                "add",
                ".",
            )
            _git(
                root,
                "-c",
                "user.name=AART Test",
                "-c",
                "user.email=aart@example.invalid",
                "commit",
                "-m",
                "promotions",
            )
            effective = effective_configuration(
                (configured_source("team", SourceKind.REGISTRY_GIT),), default_registry="team"
            )

            composed = read_maintainer_views(
                effective, data_root=str(root.parent / "data"), registry_root=str(root)
            )

        assert isinstance(composed, Ok), composed
        here = composed.value.registry_here
        assert here is not None
        self.assertEqual(here.alias, "company")
        self.assertEqual(
            [[item.artifact for item in step.versions] for step in here.transactions],
            [["mcp/jira-mcp@2.3.0"], ["mcp/github-mcp@1.0.0"]],
        )


if __name__ == "__main__":
    unittest.main()
