"""INV-284: Collections say which Registry they belong to.

With two Registries on the Registry screen, `o` opened the Collections of the Registry under the
cursor, but nothing on the way said which one. The owner could not tell where a Collection would
be added. Collections and the Collection Editor now name their Registry and where saving writes.
Since INV-304, `o` is offered only inside the Registry aart-cli runs in, so it is that one.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from aart_cli.application.maintainer_views import (
    REGISTRY_WORKSPACE_ROW,
    MaintainerRegistryView,
    MaintainerScreen,
    MaintainerViews,
    MaintainerWorkingTreeState,
    MaintainerWorkingTreeView,
    collection_row,
    project_maintainer_dashboard,
    project_registry_workspace,
)
from aart_cli.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame


def _registry(alias: str, approved: tuple[tuple[str, str], ...]) -> MaintainerRegistryView:
    return MaintainerRegistryView(
        alias,
        True,
        "a" * 40,
        "sha256:" + "b" * 64,
        len(approved),
        (),
        MaintainerWorkingTreeView(MaintainerWorkingTreeState.UNOBSERVED, None),
        (),
        approved_artifacts=approved,
    )


def _source() -> CanonicalScreenSource:
    """aart-cli runs in team's checkout, and company and team are subscribed."""

    team = _registry("team", (("skill/code-review", "2.0.0"),))
    views = MaintainerViews(
        project_maintainer_dashboard(()),
        (),
        registries=(_registry("company", (("mcp/notes", "1.0.0"),)), team),
        registry_workspace_present=True,
        registry_workspace=project_registry_workspace("team", commit="abc1234"),
        registry_here=team,
    )
    return CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
    )


def _on_registry(row: str) -> ConsumerUiState:
    state = _reload(
        _source(),
        ConsumerUiState(
            ConsumerSession(MaintainerScreen.REGISTRY),
            settings=ConsumerSettings().with_maintainer_mode(True),
        ),
        entering=True,
    )
    return replace(state, cursor=state.rows.index(row))


def _press(state: ConsumerUiState, key: str) -> ConsumerUiState:
    event = key_event(key, state, detail=_source().detail(state))
    assert event is not None, key
    moved, _commands = reduce_consumer_ui(state, event)
    return _reload(_source(), moved, entering=True)


def _here() -> ConsumerUiState:
    return _press(_on_registry(REGISTRY_WORKSPACE_ROW), "enter")


class CollectionsRegistryChoiceTest(unittest.TestCase):
    def test_o_opens_the_collections_of_the_registry_here_and_says_so(self) -> None:
        opened = _press(_here(), "o")

        self.assertIs(opened.session.screen, MaintainerScreen.COLLECTIONS)
        drawn = "\n".join(frame(_source(), opened)).lower()
        self.assertIn("collections of registry team", drawn)
        self.assertNotIn("registry company", drawn)
        self.assertIn("checkout aart-cli was started in", drawn)

    def test_the_editor_names_its_registry_and_where_saving_writes(self) -> None:
        opened = _press(_here(), "o")
        self.assertEqual(opened.current_row, collection_row("team", None))

        editing = _press(opened, "enter")

        drawn = "\n".join(frame(_source(), editing))
        self.assertIn("new collection in team", drawn.lower())
        self.assertIn("checkout aart-cli was started in", drawn)
        self.assertIn("skill/code-review", drawn)
        self.assertNotIn("mcp/notes", drawn)

    def test_o_is_offered_only_inside_the_registry_here(self) -> None:
        for row in ("company", "team", REGISTRY_WORKSPACE_ROW):
            with self.subTest(row=row):
                listed = _on_registry(row)
                self.assertNotIn("o", {item.key for item in key_bindings(listed)})
                self.assertIsNone(key_event("o", listed))
        self.assertIn("o", {item.key for item in key_bindings(_here())})


if __name__ == "__main__":
    unittest.main()
