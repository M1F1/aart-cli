"""Screens 51 and 52: the Registry's Collections and the editor one version is defined on (D-430)."""

from __future__ import annotations

import string
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    COLLECTION_SAVE_ROW,
    CollectionDraft,
    ConsumerActionKind,
    ConsumerUiCommandKind,
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
    MaintainerCollectionView,
    MaintainerRegistryView,
    MaintainerScreen,
    MaintainerViews,
    MaintainerWorkingTreeState,
    MaintainerWorkingTreeView,
    collection_row,
    parse_collection_row,
    project_maintainer_dashboard,
    project_registry_workspace,
)
from aart_cli.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame

_NAMES = st.text(alphabet=string.ascii_lowercase + string.digits + "-", min_size=1, max_size=20)


def _registry() -> MaintainerRegistryView:
    return MaintainerRegistryView(
        "company",
        True,
        "a" * 40,
        "sha256:" + "b" * 64,
        3,
        (),
        MaintainerWorkingTreeView(MaintainerWorkingTreeState.UNOBSERVED, None),
        (),
        collections=(
            MaintainerCollectionView("starter", "1.0.1", "Notes and review.", ("mcp/notes@1.0.0",)),
        ),
        approved_artifacts=(("mcp/notes", "1.0.0"), ("skill/code-review", "2.0.0")),
    )


def _source() -> CanonicalScreenSource:
    views = MaintainerViews(
        project_maintainer_dashboard(()),
        (),
        registries=(_registry(),),
        registry_workspace_present=True,
        registry_workspace=project_registry_workspace("company", commit="abc1234"),
        registry_here=_registry(),
    )
    return CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
    )


def _opened(row: str) -> ConsumerUiState:
    state = ConsumerUiState(
        ConsumerSession(MaintainerScreen.COLLECTIONS),
        settings=ConsumerSettings().with_maintainer_mode(True),
        focus="company",
    )
    state = _reload(_source(), state, entering=True)
    cursor = state.rows.index(row)
    for _ in range(cursor):
        state, _commands = reduce_consumer_ui(state, key_event("down", state))
    detail = _source().detail(state)
    event = key_event("enter", state, detail=detail)
    assert event is not None
    opened, _commands = reduce_consumer_ui(state, event)
    return _reload(_source(), opened, entering=True)


def _press(state: ConsumerUiState, *keys: str) -> ConsumerUiState:
    for key in keys:
        event = key_event(key, state)
        assert event is not None, key
        state, _commands = reduce_consumer_ui(state, event)
    return state


class CollectionRowTest(unittest.TestCase):
    @given(_NAMES, _NAMES)
    def test_a_row_names_back_the_registry_and_collection_it_was_made_from(
        self, alias: str, name: str
    ) -> None:
        self.assertEqual(parse_collection_row(collection_row(alias, name)), (alias, name))

    @given(_NAMES)
    def test_the_new_row_is_never_read_as_a_collection_name(self, alias: str) -> None:
        self.assertEqual(parse_collection_row(collection_row(alias, None)), (alias, None))

    def test_a_row_without_both_halves_names_nothing(self) -> None:
        for row in ("company", "company/", "/starter", "company/a/b", ""):
            with self.subTest(row=row):
                self.assertIsNone(parse_collection_row(row))


class CollectionsScreenTest(unittest.TestCase):
    def test_51_lists_each_collection_then_a_new_one(self) -> None:
        state = _opened(collection_row("company", None))
        listed = _reload(
            _source(),
            ConsumerUiState(
                ConsumerSession(MaintainerScreen.COLLECTIONS),
                settings=ConsumerSettings().with_maintainer_mode(True),
                focus="company",
            ),
            entering=True,
        )

        self.assertEqual(listed.rows, ("company/starter", "company/+"))
        drawn = "\n".join(frame(_source(), listed))
        self.assertIn("starter", drawn)
        self.assertIn("1.0.1", drawn)
        self.assertIn("New Collection", drawn)
        self.assertIs(state.session.screen, MaintainerScreen.COLLECTION_EDITOR)

    def test_46k_reaches_51_with_o(self) -> None:
        state = _reload(
            _source(),
            ConsumerUiState(
                ConsumerSession(MaintainerScreen.REGISTRY_DETAILS),
                settings=ConsumerSettings().with_maintainer_mode(True),
            ),
            entering=True,
        )

        moved = _reload(_source(), _press(state, "o"), entering=True)

        self.assertIs(moved.session.screen, MaintainerScreen.COLLECTIONS)
        self.assertEqual(moved.rows, ("company/starter", "company/+"))


class CollectionEditorTest(unittest.TestCase):
    def test_an_existing_collection_opens_with_its_members_ticked_and_summary_drafted(
        self,
    ) -> None:
        state = _opened("company/starter")

        self.assertEqual(
            state.rows, ("summary", "mcp/notes", "skill/code-review", COLLECTION_SAVE_ROW)
        )
        self.assertEqual(state.selection, ("mcp/notes",))
        self.assertEqual(state.collection_draft.summary, "Notes and review.")

    def test_a_new_collection_opens_empty_with_a_name_row(self) -> None:
        state = _opened("company/+")

        self.assertEqual(state.rows[0], "name")
        self.assertEqual(state.selection, ())
        self.assertEqual(state.collection_draft, CollectionDraft())

    def test_letters_on_a_text_row_are_text_and_space_on_a_member_ticks_it(self) -> None:
        state = _press(_opened("company/+"), "q", "v", "down", "?", "down", " ")

        self.assertFalse(state.exited)
        self.assertEqual(state.collection_draft, CollectionDraft("qv", "?"))
        self.assertEqual(state.selection, ("mcp/notes",))
        self.assertIn("Leave out", " ".join(item.label for item in key_bindings(state)))

    def test_continue_requests_one_definition_carrying_the_draft_and_members(self) -> None:
        state = _press(_opened("company/starter"), "down", "down", " ", "down")
        self.assertEqual(state.current_row, COLLECTION_SAVE_ROW)

        event = key_event("enter", state)
        assert event is not None
        reviewing, commands = reduce_consumer_ui(state, event)

        self.assertIs(reviewing.session.screen, MaintainerScreen.REGISTRY_VALIDATION)
        (command,) = (
            item for item in commands if item.kind is ConsumerUiCommandKind.PREPARE_ACTION
        )
        self.assertIs(command.action, ConsumerActionKind.COLLECTION_DEFINE)
        self.assertEqual(command.focus, "company/starter")
        self.assertEqual(command.selection, ("mcp/notes", "skill/code-review"))
        assert command.collection_draft is not None
        self.assertEqual(command.collection_draft.summary, "Notes and review.")

    def test_the_editor_draws_what_is_ticked_with_its_approved_version(self) -> None:
        drawn = "\n".join(frame(_source(), _opened("company/starter")))

        self.assertIn("starter 1.0.1 in company", drawn)
        self.assertIn("[x] mcp/notes  1.0.0", drawn)
        self.assertIn("[ ] skill/code-review  2.0.0", drawn)


if __name__ == "__main__":
    unittest.main()
