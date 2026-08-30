"""CP-13 screens 02–04a in the persistent application: browse, open, preview, customize.

The Marketplace lists artifacts and Collections together, so Enter has to open the right screen for
whichever one the cursor is on.  Customizing is the multi-select the shell already has: the rows of
a Collection preview are its members, and Space on them is what makes a selection custom.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    project_dashboard,
)
from agent_artifacts.domain.identifiers import ArtifactIdentity, ObjectDigest, SourceAlias
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    Collection,
    CollectionCoordinate,
    CollectionMember,
    VersionConstraint,
)
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    ConsumerScreens,
    MarketplaceCollectionEntry,
    MarketplaceEntry,
    run_consumer_shell,
)
from agent_artifacts.tui_marketplace import MarketplaceTarget, project_marketplace_rows
from tests.consumer_shell_test import ENTER, SPACE, UP, FakeTerminal, _at
from tests.tui_marketplace_test import _catalog

COLLECTION = CollectionCoordinate(SourceAlias("company"), "developer", "1.0.0")


def member(kind: str, name: str) -> CollectionMember:
    return CollectionMember(
        ArtifactRequest(
            ArtifactIdentity(kind, name), VersionConstraint("1.0.0"), SourceAlias("company")
        )
    )


def collection() -> Collection:
    return Collection(
        COLLECTION,
        "Everything a developer needs on day one",
        (member("skill", "review"), member("mcp", "database")),
        ObjectDigest("sha256", "d" * 64),
    )


def screens() -> ConsumerScreens:
    rows = project_marketplace_rows(
        _catalog(), MarketplaceTarget(("claude",), "darwin", "project", "copy")
    )
    return ConsumerScreens(
        project_dashboard((), registry_count=2),
        marketplace=tuple(MarketplaceEntry(row) for row in rows),
        collections=(MarketplaceCollectionEntry(collection()),),
    )


def drive(*codes: int, state=None):
    """Drive the shell, answering the quit prompt a ticked Collection makes it ask."""

    terminal = FakeTerminal(*codes, ord("q"), ord("y"))
    return run_consumer_shell(CanonicalScreenSource(screens()), terminal, state=state), terminal


class MarketplaceShellTest(unittest.TestCase):
    def keys(self) -> tuple[str, ...]:
        return tuple(entry.row.key for entry in screens().marketplace)

    def test_the_marketplace_lists_every_available_artifact_and_collection(self):
        state, terminal = drive(state=_at(ConsumerScreen.MARKETPLACE))

        self.assertEqual(state.rows, (*self.keys(), str(COLLECTION)))
        self.assertIn(self.keys()[0], terminal.last)
        self.assertIn("Everything a developer needs", terminal.last)

    def test_enter_on_an_artifact_opens_its_details_rather_than_a_collection(self):
        state, terminal = drive(ENTER, state=_at(ConsumerScreen.MARKETPLACE))

        self.assertEqual(state.session.screen, ConsumerScreen.ARTIFACT_DETAILS)
        self.assertIn(self.keys()[0], terminal.last)
        self.assertIn("Actions: select, install, verbose.", terminal.last)

    def test_enter_on_a_collection_opens_the_preview_rather_than_artifact_details(self):
        state, terminal = drive(UP, ENTER, state=_at(ConsumerScreen.MARKETPLACE))

        self.assertEqual(state.session.screen, ConsumerScreen.COLLECTION_PREVIEW)
        self.assertIn("2 artifacts", terminal.last)
        self.assertIn("2 / 2 selected", terminal.last)

    def test_a_collection_preview_lists_its_members_as_the_rows_it_is_about(self):
        state, _ = drive(UP, ENTER, state=_at(ConsumerScreen.MARKETPLACE))

        self.assertEqual(state.rows, ("company/mcp/database@1.0.0", "company/skill/review@1.0.0"))

    def test_deselecting_a_member_makes_the_selection_custom_with_its_own_identity(self):
        exact, _ = drive(UP, ENTER, state=_at(ConsumerScreen.MARKETPLACE))
        custom, terminal = drive(UP, ENTER, SPACE, ENTER, state=_at(ConsumerScreen.MARKETPLACE))

        self.assertEqual(custom.session.screen, ConsumerScreen.COLLECTION_CUSTOMIZE)
        self.assertIn("1 / 2 selected", terminal.last)
        self.assertIn("Warning: Custom selection", terminal.last)
        source = CanonicalScreenSource(screens())
        self.assertNotEqual(
            source.collection(str(COLLECTION), custom.selection).semantic_identity,
            source.collection(str(COLLECTION), exact.selection).semantic_identity,
        )

    def test_reselecting_every_member_is_the_exact_collection_again(self):
        source = CanonicalScreenSource(screens())
        members = source.collection(str(COLLECTION), ()).members

        view = source.collection(str(COLLECTION), tuple(reversed(members)))

        self.assertTrue(view.exact)
        self.assertEqual(view.selected, members)


if __name__ == "__main__":
    unittest.main()
