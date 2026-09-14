"""CP-23 task 02: the Candidates table is the rows, and the Candidate under the cursor is a description.

The operator reported the focused Candidate drawn inside the table's own block under an
`Under the cursor:` heading, in both profiles. The table is what the cursor moves over, so it is
the actions block alone; the four identity fields are what the cursor is on, which is the
``described`` block every other screen already uses -- shown in Verbose, collapsed in Fast (D-250).
"""

from __future__ import annotations

import dataclasses
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts import tui
from agent_artifacts.application.consumer_ui import (
    ConsumerUiCommandKind,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.tui_consumer import _reload, frame
from agent_artifacts.tui_layout import CONTENT_MEASURE, SECTION_RULE, footer_start
from agent_artifacts.tui_maintainer import (
    maintainer_candidate_detail,
    render_maintainer_candidates,
)
from tests.maintainer_candidate_filters_test import _on, _shell, _views
from tests.screen_skeleton_test import _Screen
from tests.tabular_list_columns_test import LONG, _candidate

_LABELS = ("Artifact", "Version", "Source", "Status")


def _labels(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(line.split()[0] for line in lines if line.startswith("  ") and line.strip())


class CandidatesScreenSeparatesTableFromDetailTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = _shell(_views())

    def _listed(self, profile: PresentationProfile, **fields):
        state = _on(MaintainerScreen.CANDIDATES, **fields)
        state = dataclasses.replace(
            state, session=dataclasses.replace(state.session, profile=profile)
        )
        return _reload(self.source, state, entering=True)

    def test_verbose_draws_the_focused_identity_below_its_own_rule(self) -> None:
        state = self._listed(PresentationProfile.VERBOSE)
        focused = next(item for item in _views().candidates if item.id == state.current_row)

        drawn = frame(self.source, state)

        self.assertNotIn("Under the cursor:", "\n".join(drawn))
        header = next(index for index, line in enumerate(drawn) if line.split()[:1] == ["STATUS"])
        self.assertEqual(drawn[header].split(), ["STATUS", "ARTIFACT", "VERSION", "SOURCE"])
        table_end = header + 1 + len(state.rows)
        self.assertEqual(drawn[table_end : table_end + 3], ("", SECTION_RULE, ""))
        described = drawn[table_end + 3 : table_end + 3 + len(_LABELS)]
        self.assertEqual(_labels(described), _LABELS)
        self.assertIn(focused.artifact, described[0])
        self.assertIn(focused.version, described[1])
        self.assertIn(focused.source_alias, described[2])

    def test_fast_draws_the_table_and_no_identity_block(self) -> None:
        drawn = "\n".join(frame(self.source, self._listed(PresentationProfile.FAST)))

        self.assertIn("ARTIFACT", drawn)
        self.assertNotIn("Under the cursor:", drawn)
        for label in _LABELS:
            self.assertNotRegex(drawn, rf"(?m)^  {label}\b")

    def test_v_collapses_and_restores_the_same_candidate(self) -> None:
        verbose = dataclasses.replace(self._listed(PresentationProfile.VERBOSE), cursor=1)
        expected = self.source.description(verbose)

        fast, fast_commands = reduce_consumer_ui(verbose, key_event("v", verbose))
        again, again_commands = reduce_consumer_ui(fast, key_event("v", fast))

        self.assertIs(fast.session.profile, PresentationProfile.FAST)
        self.assertIs(again.session.profile, PresentationProfile.VERBOSE)
        self.assertEqual((fast.current_row, again.current_row), (verbose.current_row,) * 2)
        fast_drawn = frame(self.source, fast)
        self.assertTrue(expected)
        self.assertFalse(any(line in fast_drawn for line in expected))
        self.assertEqual(frame(self.source, again), frame(self.source, verbose))
        # Toggling remembers the preference and does nothing else: no navigation, no action.
        self.assertEqual(
            {command.kind for command in (*fast_commands, *again_commands)},
            {ConsumerUiCommandKind.PERSIST_SETTINGS},
        )

    def test_moving_the_cursor_describes_the_new_row_from_the_other_source(self) -> None:
        state = self._listed(PresentationProfile.VERBOSE)
        views = {item.id: item for item in _views().candidates}
        seen_sources = set()
        for index in range(len(state.rows)):
            at = dataclasses.replace(state, cursor=index)
            described = self.source.description(at)
            candidate = views[at.current_row]
            self.assertIn(candidate.artifact, described[0])
            self.assertIn(candidate.source_alias, described[2])
            seen_sources.add(candidate.source_alias)
        self.assertEqual(seen_sources, {"authors", "vendors"})

    def test_filtering_describes_only_a_row_that_is_still_listed(self) -> None:
        state = self._listed(PresentationProfile.VERBOSE)

        narrowed = _reload(self.source, dataclasses.replace(state, search="jira"))
        emptied = _reload(self.source, dataclasses.replace(state, search="no-such-candidate"))

        self.assertEqual(len(narrowed.rows), 1)
        self.assertIn("jira", self.source.description(narrowed)[0])
        self.assertEqual(emptied.rows, ())
        self.assertEqual(self.source.description(emptied), ())
        drawn = "\n".join(frame(self.source, emptied))
        for label in _LABELS:
            self.assertNotRegex(drawn, rf"(?m)^  {label}\b")

    def test_a_row_the_search_excludes_is_not_described_before_the_rows_reload(self) -> None:
        """Rows and description read one filter, so a stale cursor cannot outlive the query."""

        state = self._listed(PresentationProfile.VERBOSE)
        typed = dataclasses.replace(state, search="jira")

        self.assertNotIn("jira", self.source.description(state)[0])
        self.assertEqual(self.source.description(typed), ())

    def test_a_narrow_short_terminal_clips_the_detail_and_keeps_the_keys(self) -> None:
        state = self._listed(PresentationProfile.VERBOSE)
        lines = frame(self.source, state)
        screen = _Screen(height=20, width=40)

        tui._CursesTerminal(screen).draw(lines)

        painted = [value for _, _, value in screen.written]
        keys = lines[footer_start(lines) :]
        self.assertEqual(painted[-len(keys) :], [line[:39] for line in keys])
        self.assertTrue(all(len(value) <= 39 for value in painted))
        self.assertLess(
            next(i for i, value in enumerate(painted) if value.split()[:1] == ["STATUS"]),
            next(i for i, value in enumerate(painted) if value.startswith("  Artifact")),
        )
        self.assertFalse(any(value.startswith("  Target registry") for value in painted))


class CandidateDetailProjectionTest(unittest.TestCase):
    def test_a_name_too_long_for_its_column_is_described_in_full_within_the_measure(self) -> None:
        focused = _candidate(LONG, source="superpowers-test")

        detail = maintainer_candidate_detail((_candidate(), focused), cursor=focused.id)
        table = render_maintainer_candidates(
            (_candidate(), focused), cursor=focused.id, profile=PresentationProfile.VERBOSE
        )

        self.assertIn(LONG, "".join(line.strip() for line in detail))
        self.assertTrue(all(len(line) <= CONTENT_MEASURE for line in (*detail, *table)))
        self.assertNotIn("Under the cursor:", table)

    def test_the_table_never_carries_detail_labels(self) -> None:
        focused = _candidate(LONG, source="superpowers-test")

        table = render_maintainer_candidates(
            (focused,), cursor=focused.id, profile=PresentationProfile.VERBOSE
        )

        self.assertEqual(len(table), 2)

    @given(
        names=st.lists(
            st.text(alphabet="abcdefghij-", min_size=1, max_size=40), unique=True, max_size=6
        ),
        cursor=st.text(alphabet="abcdefghij-/", max_size=45),
    )
    def test_detail_exists_exactly_when_the_cursor_names_a_listed_candidate(
        self, names: list[str], cursor: str
    ) -> None:
        candidates = tuple(_candidate(f"mcp/{name}") for name in names)
        ids = {item.id for item in candidates}
        pick = next(iter(sorted(ids)), cursor) if cursor == "" and ids else cursor

        detail = maintainer_candidate_detail(candidates, cursor=pick)
        table = render_maintainer_candidates(
            candidates, cursor=pick, profile=PresentationProfile.VERBOSE
        )

        if pick in ids:
            self.assertEqual(_labels(detail)[:4], _LABELS)
        else:
            self.assertEqual(detail, ())
        self.assertEqual(len(table), len(candidates) + 1 if candidates else 1)
