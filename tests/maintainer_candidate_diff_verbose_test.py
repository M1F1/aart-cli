"""CP-23 task 03: Candidate Diff's bounded file diffs are its Verbose projection, behind `v`.

The operator found two ways to change how much screen 37 says -- `[v] Fast / Verbose` and a
screen-specific `[f] Files` -- plus a `d returns to summary` prompt that did nothing. D-250 makes
`v` the one presentation toggle on every screen, so Fast is the semantic summary with the changed
file list and Verbose adds the bounded, redacted file diffs. Neither projection changes which
Candidate is on screen or where the review stands.
"""

from __future__ import annotations

import builtins
import dataclasses
import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import ConsumerSession, PresentationProfile
from aart_cli.application.maintainer_views import (
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_candidates,
    project_maintainer_dashboard,
)
from aart_cli.tui_consumer import _reload, frame
from aart_cli.tui_layout import footer_start
from aart_cli.tui_maintainer import render_maintainer_candidate_diff
from tests.maintainer_candidate_shell_test import (
    _on,
    _projected_source,
    _scan,
    _shell,
    _views,
)

_FILES = "Bounded redacted file diffs:"
_SHOW = "Press v to view bounded redacted file diffs."
_HIDE = "Press v to hide the bounded redacted file diffs."
_REVIEW_HISTORY = (MaintainerScreen.CANDIDATES, MaintainerScreen.CANDIDATE_DETAILS)


def _statements(drawn: tuple[str, ...]) -> list[str]:
    """The status block's list items, each as its lines joined."""

    body = drawn[: footer_start(drawn)]
    items: list[list[str]] = []
    for line in body:
        if line.startswith("- "):
            items.append([line[2:]])
        elif line.startswith("  ") and items:
            items[-1].append(line.strip())
    return [" ".join(item) for item in items]


class CandidateDiffVerboseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = _shell(_views())
        self.candidate = next(
            item for item in _views().candidates or () if item.source_alias == "authors"
        )

    def _diff(self, profile: PresentationProfile = PresentationProfile.FAST) -> ConsumerUiState:
        state = dataclasses.replace(
            _on(MaintainerScreen.CANDIDATE_DIFF, focus=self.candidate.id),
            session=ConsumerSession(
                MaintainerScreen.CANDIDATE_DIFF, history=_REVIEW_HISTORY, profile=profile
            ),
        )
        return _reload(self.source, state, entering=True)

    def test_fast_is_the_summary_with_the_hint_as_its_own_last_statement(self) -> None:
        drawn = frame(self.source, self._diff())
        text = "\n".join(drawn)

        self.assertIn("Semantic changes:", text)
        self.assertIn("~ payload/server.py — modified", text)
        self.assertNotIn(_FILES, text)
        self.assertNotIn("print('new')", text)
        self.assertNotIn("Press f", text)
        self.assertNotIn("d returns", text)
        statements = _statements(drawn)
        self.assertEqual(statements[-1], _SHOW)
        self.assertNotIn(_SHOW, statements[-2])

    def test_verbose_adds_the_file_diffs_and_says_how_to_fold_them(self) -> None:
        drawn = frame(self.source, self._diff(PresentationProfile.VERBOSE))
        text = "\n".join(drawn)

        self.assertIn("Semantic changes:", text)
        self.assertIn(_FILES, text)
        self.assertIn("print('new')", text)
        self.assertEqual(_statements(drawn)[-1], _HIDE)
        self.assertNotIn(_SHOW, text)

    def test_the_footer_advertises_v_and_no_f(self) -> None:
        drawn = frame(self.source, self._diff())
        footer = "\n".join(drawn[footer_start(drawn) :])

        self.assertIn("[v] Fast / Verbose", footer)
        self.assertNotIn("[f]", footer)
        self.assertIsNone(key_event("f", self._diff()))

    def test_v_toggles_the_diffs_and_back_without_touching_the_review(self) -> None:
        fast = self._diff()
        verbose, first = reduce_consumer_ui(fast, key_event("v", fast))
        again, second = reduce_consumer_ui(verbose, key_event("v", verbose))

        self.assertIn(_FILES, "\n".join(frame(self.source, verbose)))
        self.assertEqual(frame(self.source, again), frame(self.source, fast))
        for toggled in (verbose, again):
            self.assertEqual(toggled.focus, self.candidate.id)
            self.assertIs(toggled.session.screen, MaintainerScreen.CANDIDATE_DIFF)
            self.assertEqual(toggled.session.history, _REVIEW_HISTORY)
            self.assertEqual(toggled.session.review_digest, fast.session.review_digest)
        self.assertEqual(
            {command.kind for command in (*first, *second)},
            {ConsumerUiCommandKind.PERSIST_SETTINGS},
        )

    def test_drawing_either_projection_opens_no_file(self) -> None:
        states = (self._diff(), self._diff(PresentationProfile.VERBOSE))
        original = builtins.open

        def refuse(*arguments, **keywords):
            raise AssertionError("drawing screen 37 opened a file")

        builtins.open = refuse  # type: ignore[assignment]
        try:
            for state in states:
                frame(self.source, state)
        finally:
            builtins.open = original

    @settings(max_examples=40, deadline=None)
    @given(presses=st.integers(min_value=0, max_value=7))
    def test_any_number_of_presses_shows_files_exactly_in_verbose(self, presses: int) -> None:
        state = self._diff()
        for _ in range(presses):
            state, _ = reduce_consumer_ui(state, key_event("v", state))

        shown = _FILES in "\n".join(frame(self.source, state))
        self.assertEqual(shown, presses % 2 == 1)
        self.assertEqual(state.session.profile is PresentationProfile.VERBOSE, shown)
        self.assertEqual(
            (state.focus, state.session.screen, state.session.history),
            (self.candidate.id, MaintainerScreen.CANDIDATE_DIFF, _REVIEW_HISTORY),
        )


class CandidateDiffEvidenceIsBoundedAndRedactedTest(unittest.TestCase):
    def _candidate(self, server_before: str, server_after: str):
        first = _scan(alias="authors", revision="a" * 40, version="1.0.0", server=server_before)
        second = _scan(
            alias="authors",
            revision="b" * 40,
            version="1.1.0",
            server=server_after,
            previous=first.history,
        )
        return project_maintainer_candidates((second,))[0], second

    def test_a_credential_in_a_changed_file_is_redacted_in_verbose(self) -> None:
        planted = "x" * 24
        assignment = "pass" + "word = " + planted
        view, _ = self._candidate("print('old')\n", f"{assignment}\n")

        verbose = "\n".join(render_maintainer_candidate_diff(view, PresentationProfile.VERBOSE))

        self.assertIn(_FILES, verbose)
        self.assertNotIn(planted, verbose)
        self.assertIn("[redacted]", verbose)

    def test_a_long_diff_is_truncated_and_toggling_repeatedly_is_stable(self) -> None:
        before = "".join(f"print({n})\n" for n in range(400))
        after = "".join(f"print({n + 1})\n" for n in range(400))
        view, scan = self._candidate(before, after)
        projected = _projected_source("authors", scan)
        source = _shell(
            MaintainerViews(project_maintainer_dashboard((projected,)), (projected,), (view,))
        )
        state = _reload(
            source,
            dataclasses.replace(
                _on(MaintainerScreen.CANDIDATE_DIFF, focus=view.id),
                session=ConsumerSession(
                    MaintainerScreen.CANDIDATE_DIFF, profile=PresentationProfile.VERBOSE
                ),
            ),
            entering=True,
        )

        drawn = [frame(source, state)]
        for _ in range(4):
            state, _ = reduce_consumer_ui(state, key_event("v", state))
            drawn.append(frame(source, state))

        diff_lines = [line for line in drawn[0] if line.startswith(("    +print", "    -print"))]
        self.assertLessEqual(len(diff_lines), 200)
        self.assertEqual(drawn[0], drawn[2])
        self.assertEqual(drawn[2], drawn[4])
        self.assertEqual(drawn[1], drawn[3])
        self.assertNotEqual(drawn[0], drawn[1])
