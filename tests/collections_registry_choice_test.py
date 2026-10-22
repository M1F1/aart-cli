"""INV-284: Collections say which Registry they belong to.

With two Registries on the Registry screen, `o` opened the Collections of the Registry under the
cursor, but nothing on the way said which one. The owner could not tell where a Collection would
be added. Collections and the Collection Editor now name their Registry and where saving writes,
and `o` is offered only on a Registry row.
"""

from __future__ import annotations

import unittest

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
    registries = (
        _registry("company", (("mcp/notes", "1.0.0"),)),
        _registry("team", (("skill/code-review", "2.0.0"),)),
    )
    views = MaintainerViews(project_maintainer_dashboard(()), (), registries=registries)
    return CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
    )


def _on_registry(row: str) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(MaintainerScreen.REGISTRY),
        settings=ConsumerSettings().with_maintainer_mode(True),
        rows=("company", "team", REGISTRY_WORKSPACE_ROW),
        cursor=("company", "team", REGISTRY_WORKSPACE_ROW).index(row),
    )


def _press(state: ConsumerUiState, key: str) -> ConsumerUiState:
    event = key_event(key, state, detail=_source().detail(state))
    assert event is not None, key
    moved, _commands = reduce_consumer_ui(state, event)
    return _reload(_source(), moved, entering=True)


class CollectionsRegistryChoiceTest(unittest.TestCase):
    def test_o_opens_the_collections_of_the_registry_under_the_cursor_and_says_so(self) -> None:
        opened = _press(_on_registry("team"), "o")

        self.assertIs(opened.session.screen, MaintainerScreen.COLLECTIONS)
        drawn = "\n".join(frame(_source(), opened)).lower()
        self.assertIn("collections of registry team", drawn)
        self.assertNotIn("registry company", drawn)
        self.assertIn("checkout aart-cli was started in", drawn)

    def test_the_editor_names_its_registry_and_where_saving_writes(self) -> None:
        opened = _press(_on_registry("team"), "o")
        self.assertEqual(opened.current_row, collection_row("team", None))

        editing = _press(opened, "enter")

        drawn = "\n".join(frame(_source(), editing))
        self.assertIn("new collection in team", drawn.lower())
        self.assertIn("checkout aart-cli was started in", drawn)
        self.assertIn("skill/code-review", drawn)
        self.assertNotIn("mcp/notes", drawn)

    def test_o_is_offered_only_on_a_registry_row(self) -> None:
        for row in ("company", "team"):
            with self.subTest(row=row):
                self.assertIn("o", {item.key for item in key_bindings(_on_registry(row))})
        workspace = _on_registry(REGISTRY_WORKSPACE_ROW)
        self.assertNotIn("o", {item.key for item in key_bindings(workspace)})
        self.assertIsNone(key_event("o", workspace))


if __name__ == "__main__":
    unittest.main()
