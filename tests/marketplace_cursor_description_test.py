"""CP-23 task 07: the Marketplace row under the cursor is described from approved metadata.

Screen 02 listed ``key  summary`` rows and nothing else, so the only words about an offer were one
line a narrow terminal clips. The offer under the cursor is now the shared cursor description
(D-250, §167): its identity, where it comes from and its approved summary in full, drawn below the
list's rule in Verbose and collapsed by ``v`` in Fast. It is read from the already-projected
Registry offers -- nothing is fetched or opened to draw it -- and an offer with no usable summary
says so rather than borrowing words from anywhere else (D-257).
"""

from __future__ import annotations

import builtins
import dataclasses
import socket
import subprocess
import unittest
import urllib.request
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import ConsumerScreen, PresentationProfile
from aart_cli.domain.identifiers import ObjectDigest, SourceAlias
from aart_cli.domain.selection import Collection, CollectionCoordinate
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    MarketplaceCollectionEntry,
    MarketplaceEntry,
    _reload,
    frame,
)
from aart_cli.tui_layout import CONTENT_MEASURE, SECTION_RULE
from tests.consumer_marketplace_shell_test import COLLECTION, collection, member
from tests.consumer_marketplace_shell_test import screens as marketplace_screens
from tests.consumer_shell_test import _at

_LONG = (
    "Reviews a pull request against the team's written conventions, points at the exact lines "
    "that break them, proposes a smaller change where one exists and never pushes anything."
)
_FALLBACK = "No description was approved for this offer."


def _distinct():
    """The shell's Marketplace, each artifact carrying its own approved summary."""

    composed = marketplace_screens()
    marketplace = tuple(
        MarketplaceEntry(dataclasses.replace(entry.row, summary=f"Summary number {index}."))
        for index, entry in enumerate(composed.marketplace)
    )
    return dataclasses.replace(composed, marketplace=marketplace)


def _listed(
    composed=None, profile: PresentationProfile = PresentationProfile.VERBOSE, **fields
) -> tuple[CanonicalScreenSource, ConsumerUiState]:
    source = CanonicalScreenSource(_distinct() if composed is None else composed)
    state = _at(ConsumerScreen.MARKETPLACE, **fields)
    state = dataclasses.replace(state, session=dataclasses.replace(state.session, profile=profile))
    return source, _reload(source, state, entering=True)


def _on(state: ConsumerUiState, row: str) -> ConsumerUiState:
    return dataclasses.replace(state, cursor=state.rows.index(row))


def _entry(composed, key: str) -> MarketplaceEntry:
    return next(entry for entry in composed.marketplace if entry.key == key)


def _labels(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(line.split()[0] for line in lines if line.startswith("  ") and line.strip())


class FocusedOfferIsDescribedTest(unittest.TestCase):
    def test_verbose_draws_the_focused_artifact_below_the_list_rule(self) -> None:
        composed = _distinct()
        source, state = _listed(composed)
        focused = _entry(composed, state.current_row).row

        drawn = frame(source, state)
        described = source.description(state)

        self.assertEqual(
            _labels(described), ("Artifact", "Kind", "Version", "Source", "Description")
        )
        joined = "\n".join(described)
        for value in (focused.identity.name, focused.version, str(focused.source_alias)):
            self.assertIn(value, joined)
        self.assertIn(focused.summary, joined)
        last_row = max(index for index, line in enumerate(drawn) if line.startswith(("> ", "  [")))
        self.assertEqual(drawn[last_row + 1 : last_row + 4], ("", SECTION_RULE, ""))
        self.assertEqual(drawn[last_row + 4 : last_row + 4 + len(described)], described)

    def test_fast_draws_the_list_and_no_description(self) -> None:
        composed = _distinct()
        source, state = _listed(composed, PresentationProfile.FAST)

        drawn = "\n".join(frame(source, state))

        self.assertIn(state.current_row, drawn)
        for label in ("Artifact", "Kind", "Description"):
            self.assertNotRegex(drawn, rf"(?m)^  {label}\b")

    def test_v_collapses_and_restores_the_same_offer_and_does_nothing_else(self) -> None:
        source, verbose = _listed()
        verbose = dataclasses.replace(verbose, cursor=1)
        expected = source.description(verbose)

        fast, fast_commands = reduce_consumer_ui(verbose, key_event("v", verbose))
        again, again_commands = reduce_consumer_ui(fast, key_event("v", fast))

        self.assertTrue(expected)
        self.assertEqual((fast.current_row, again.current_row), (verbose.current_row,) * 2)
        self.assertFalse(any(line in frame(source, fast) for line in expected))
        self.assertEqual(frame(source, again), frame(source, verbose))
        self.assertEqual(
            {command.kind for command in (*fast_commands, *again_commands)},
            {ConsumerUiCommandKind.PERSIST_SETTINGS},
        )

    def test_moving_the_cursor_describes_each_offer_with_its_own_summary(self) -> None:
        composed = _distinct()
        source, state = _listed(composed)
        artifacts = [row for row in state.rows if row != str(COLLECTION)]

        described = [source.description(_on(state, row)) for row in artifacts]

        for row, lines in zip(artifacts, described, strict=True):
            self.assertIn(_entry(composed, row).row.summary, "\n".join(lines))
        self.assertEqual(len(set(described)), len(artifacts))

    def test_ticking_other_rows_leaves_the_description_on_the_cursor(self) -> None:
        source, state = _listed()
        first = source.description(state)

        ticked = dataclasses.replace(state, selection=state.rows[1:])

        self.assertEqual(source.description(ticked), first)

    def test_a_long_summary_is_described_in_full_within_the_measure(self) -> None:
        composed = _distinct()
        key = composed.marketplace[0].key
        long = dataclasses.replace(
            composed,
            marketplace=(
                MarketplaceEntry(dataclasses.replace(composed.marketplace[0].row, summary=_LONG)),
                *composed.marketplace[1:],
            ),
        )
        source, state = _listed(long)

        described = source.description(_on(state, key))

        self.assertGreater(len(described), 5)
        self.assertTrue(all(len(line) <= CONTENT_MEASURE for line in described), described)
        self.assertIn(" ".join(_LONG.split()), " ".join(" ".join(described).split()))

    def test_an_offer_without_a_usable_summary_says_so_and_invents_nothing(self) -> None:
        composed = _distinct()
        key = composed.marketplace[0].key
        blank = dataclasses.replace(
            composed,
            marketplace=(
                MarketplaceEntry(dataclasses.replace(composed.marketplace[0].row, summary=" ")),
                *composed.marketplace[1:],
            ),
        )
        source, state = _listed(blank)

        described = "\n".join(source.description(_on(state, key)))

        self.assertIn(_FALLBACK, described)
        for other in composed.marketplace[1:]:
            self.assertNotIn(other.row.summary, described)


class CollectionOffersAreDescribedTest(unittest.TestCase):
    def test_a_collection_row_is_described_as_the_collection_it_offers(self) -> None:
        source, state = _listed()

        described = source.description(_on(state, str(COLLECTION)))
        joined = "\n".join(described)

        self.assertEqual(
            _labels(described), ("Collection", "Version", "Source", "Includes", "Description")
        )
        self.assertIn(COLLECTION.name, joined)
        self.assertIn("2 artifacts", joined)
        self.assertIn(collection().summary, joined)

    def test_the_collection_count_is_the_collection_s_own(self) -> None:
        bigger = Collection(
            CollectionCoordinate(SourceAlias("company"), "platform", "2.0.0"),
            "The platform team's whole toolbox",
            (member("skill", "review"), member("mcp", "database"), member("skill", "deploy")),
            ObjectDigest("sha256", "e" * 64),
        )
        composed = dataclasses.replace(
            _distinct(), collections=(MarketplaceCollectionEntry(bigger),)
        )
        source, state = _listed(composed)

        joined = "\n".join(source.description(_on(state, str(bigger.coordinate))))

        self.assertIn("3 artifacts", joined)
        self.assertIn("The platform team's whole toolbox", joined)

    def test_the_collection_preview_it_opens_carries_no_marketplace_description(self) -> None:
        source, state = _listed()
        collection_row = _on(state, str(COLLECTION))

        event = key_event("enter", collection_row, detail=source.detail(collection_row))
        assert event is not None
        opened, _ = reduce_consumer_ui(collection_row, event)
        opened = _reload(source, opened, entering=True)

        self.assertIs(opened.session.screen, ConsumerScreen.COLLECTION_PREVIEW)
        self.assertEqual(source.description(opened), ())


class DescriptionFollowsTheFilteredListTest(unittest.TestCase):
    def test_search_describes_only_a_row_that_is_still_listed(self) -> None:
        source, state = _listed()

        narrowed = _reload(source, dataclasses.replace(state, search="database"))
        emptied = _reload(source, dataclasses.replace(state, search="no-such-offer"))

        self.assertEqual(narrowed.rows, ("team/mcp/database@1.0.0",))
        self.assertIn("database", "\n".join(source.description(narrowed)))
        self.assertEqual(emptied.rows, ())
        self.assertEqual(source.description(emptied), ())
        drawn = "\n".join(frame(source, emptied))
        self.assertNotRegex(drawn, r"(?m)^  (Artifact|Collection|Description)\b")

    def test_a_row_the_search_excludes_is_not_described_before_the_rows_reload(self) -> None:
        source, state = _listed()
        on_database = _on(state, "team/mcp/database@1.0.0")

        typed = dataclasses.replace(on_database, search="review")

        self.assertTrue(source.description(on_database))
        self.assertEqual(source.description(typed), ())

    @given(
        cursor=st.integers(min_value=0, max_value=3),
        search=st.sampled_from(
            ("", "review", "database", "team", "developer", "company", "zzz", "Summary number 1")
        ),
    )
    def test_a_description_exists_exactly_when_the_cursor_is_on_a_listed_offer(
        self, cursor: int, search: str
    ) -> None:
        source, state = _listed()
        # The rows are not reloaded, so the cursor may sit on a row the search has removed.
        moved = dataclasses.replace(state, cursor=cursor, search=search)
        listed = source.rows(moved)

        described = source.description(moved)

        self.assertEqual(len(state.rows), 4)
        if moved.current_row in listed:
            self.assertIn(moved.current_row.split("/")[-1].split("@")[0], "\n".join(described))
        else:
            self.assertEqual(described, ())


class DescribingReadsNothingTest(unittest.TestCase):
    def test_describing_and_drawing_open_no_file_process_or_socket(self) -> None:
        source, state = _listed()
        refused = AssertionError("rendering must not perform IO")

        with (
            mock.patch.object(builtins, "open", side_effect=refused),
            mock.patch.object(subprocess, "run", side_effect=refused),
            mock.patch.object(subprocess, "Popen", side_effect=refused),
            mock.patch.object(socket, "create_connection", side_effect=refused),
            mock.patch.object(urllib.request, "urlopen", side_effect=refused),
        ):
            for row in state.rows:
                on = _on(state, row)
                self.assertTrue(source.description(on))
                frame(source, on)


if __name__ == "__main__":
    unittest.main()
