"""INV-282: the Collection editor filters its artifacts the way Marketplace filters offers.

A Registry with many approved artifacts listed every one of them on the editor, and the owner had
to scroll to each member. `/` on an artifact row opens the same filter Marketplace has. The
filter hides rows and never unticks one, so a Collection is assembled across several searches.
"""

from __future__ import annotations

import dataclasses
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    COLLECTION_SAVE_ROW,
    ConsumerActionKind,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
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
    MaintainerRegistryView,
    MaintainerScreen,
    MaintainerViews,
    MaintainerWorkingTreeState,
    MaintainerWorkingTreeView,
    collection_row,
    project_maintainer_dashboard,
)
from aart_cli.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame

_APPROVED = (
    ("guideline/python-style", "1.0.0"),
    ("mcp/notes", "1.0.0"),
    ("skill/code-lint", "1.1.0"),
    ("skill/code-review", "2.0.0"),
    ("skill/release-notes", "1.0.0"),
)
_TEXT_ROWS = ("name", "summary")


def _source() -> CanonicalScreenSource:
    registry = MaintainerRegistryView(
        "company",
        True,
        "a" * 40,
        "sha256:" + "b" * 64,
        len(_APPROVED),
        (),
        MaintainerWorkingTreeView(MaintainerWorkingTreeState.UNOBSERVED, None),
        (),
        approved_artifacts=_APPROVED,
    )
    views = MaintainerViews(project_maintainer_dashboard(()), (), registries=(registry,))
    return CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
    )


def _editor() -> ConsumerUiState:
    state = ConsumerUiState(
        ConsumerSession(MaintainerScreen.COLLECTION_EDITOR),
        settings=ConsumerSettings().with_maintainer_mode(True),
        focus=collection_row("company", None),
    )
    return _reload(_source(), state, entering=True)


def _press(state: ConsumerUiState, *keys: str) -> ConsumerUiState:
    """Each key as the shell takes it: the event, then the rows the screen now shows."""

    for key in keys:
        event = key_event(key, state)
        assert event is not None, key
        state, _commands = reduce_consumer_ui(state, event)
        state = _reload(_source(), state)
    return state


def _members(state: ConsumerUiState) -> tuple[str, ...]:
    return tuple(row for row in state.rows if row not in (*_TEXT_ROWS, COLLECTION_SAVE_ROW))


def _on(state: ConsumerUiState, row: str) -> ConsumerUiState:
    while state.current_row != row:
        state = _press(state, "down")
    return state


class CollectionEditorSearchTest(unittest.TestCase):
    def test_slash_on_an_artifact_row_filters_the_artifacts_and_keeps_the_form(self) -> None:
        state = _press(_on(_editor(), "mcp/notes"), "/", *"code")

        self.assertTrue(state.searching)
        self.assertEqual(_members(state), ("skill/code-lint", "skill/code-review"))
        self.assertEqual(state.rows[:2], _TEXT_ROWS)
        self.assertEqual(state.rows[-1], COLLECTION_SAVE_ROW)
        drawn = "\n".join(frame(_source(), state))
        self.assertIn("search: code_", drawn.lower())
        self.assertNotIn("mcp/notes", drawn)
        # The row under the cursor went; Space must tick the first match, not type into Name.
        self.assertEqual(state.current_row, "skill/code-lint")

    def test_slash_on_a_text_row_is_a_character_of_the_text(self) -> None:
        state = _press(_editor(), "a", "/", "b")

        self.assertFalse(state.searching)
        self.assertEqual(state.collection_draft.name, "a/b")
        self.assertNotIn("/", {item.key for item in key_bindings(state)})

    def test_the_legend_offers_search_on_an_artifact_row(self) -> None:
        state = _on(_editor(), "mcp/notes")

        self.assertIn(("/", "Search"), {(item.key, item.label) for item in key_bindings(state)})

    def test_ticks_hidden_by_the_filter_are_kept_counted_and_saved(self) -> None:
        state = _press(_on(_editor(), "mcp/notes"), " ", "/", *"review", "enter")
        state = _press(_on(state, "skill/code-review"), " ")

        self.assertEqual(_members(state), ("skill/code-review",))
        self.assertIn("2 selected", "\n".join(frame(_source(), state)))
        state = _press(_on(state, "name"), *"dev")
        state = _on(state, COLLECTION_SAVE_ROW)
        event = key_event("enter", state)
        assert event is not None
        _reviewing, commands = reduce_consumer_ui(state, event)
        (command,) = (
            item for item in commands if item.kind is ConsumerUiCommandKind.PREPARE_ACTION
        )
        self.assertIs(command.action, ConsumerActionKind.COLLECTION_DEFINE)
        self.assertEqual(set(command.selection), {"mcp/notes", "skill/code-review"})

    def test_esc_clears_an_applied_filter_and_stays_on_the_editor(self) -> None:
        state = _press(_editor(), *"dev")
        state = _press(_on(state, "mcp/notes"), "/", *"lint", "enter")
        self.assertEqual(_members(state), ("skill/code-lint",))

        cleared = _press(state, "escape")

        self.assertIs(cleared.session.screen, MaintainerScreen.COLLECTION_EDITOR)
        self.assertEqual(cleared.search, "")
        self.assertEqual(_members(cleared), tuple(item for item, _ in _APPROVED))
        self.assertEqual(cleared.collection_draft.name, "dev")
        leaving = key_event("escape", cleared)
        assert leaving is not None
        self.assertIs(leaving.kind, ConsumerUiEventKind.BACK)

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-/@.0123456789", max_size=6))
    def test_any_query_shows_exactly_the_artifacts_containing_it_in_order(self, query) -> None:
        state = dataclasses.replace(_on(_editor(), "mcp/notes"), search=query)

        rows = _source().rows(state)

        self.assertEqual(
            tuple(row for row in rows if row not in (*_TEXT_ROWS, COLLECTION_SAVE_ROW)),
            tuple(item for item, _ in _APPROVED if query.strip().lower() in item.lower()),
        )
        self.assertEqual(rows[:2], _TEXT_ROWS)
        self.assertEqual(rows[-1], COLLECTION_SAVE_ROW)


if __name__ == "__main__":
    unittest.main()
