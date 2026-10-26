"""INV-297: Marketplace leads with what an offer is; its other columns are one key away.

A colleague of the owner found Marketplace's seven columns overwhelming to read and to move
through. By default a row now says only which offer it is, as `name@version`, and what it is, under
Type. `d` adds Registry, Upstream, Status, Scope, Harnesses and Configuration after them, and `d`
again takes them away, without touching the selection, the search or the cursor (§196).
"""

from __future__ import annotations

import datetime as dt
import os
import re
import unittest
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import tui
from aart_cli.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    marketplace_cells,
)
from aart_cli.domain.result import Ok
from aart_cli.tui_marketplace_rows import _HEADINGS, render_marketplace_rows

_DETAILS = ("Registry", "Upstream", "Status", "Scope", "Harnesses", "Configuration")
_CELL = st.text(alphabet="abcdefghijklmnopqrstuvwxyz/@.-0123456789", min_size=1, max_size=24)


def _marketplace(**fields) -> ConsumerUiState:
    return ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE), **fields)


class TheRowSaysWhatTheOfferIs(unittest.TestCase):
    def test_artifact_is_name_and_version_and_type_is_the_kind(self) -> None:
        for key, expected in (
            ("company/skill/review@1.2.0", ("review@1.2.0", "Skill")),
            ("company/mcp/airflow@1.0.0", ("airflow@1.0.0", "MCP")),
            ("lab/guideline/style@2.0.0", ("style@2.0.0", "Guideline")),
            ("lab/hook/pre-commit@0.1.0", ("pre-commit@0.1.0", "Hook")),
            ("lab/memory/notes@1.0.0", ("notes@1.0.0", "Memory")),
            ("lab/plugin/tools@3.0.0", ("tools@3.0.0", "Plugin")),
        ):
            with self.subTest(key=key):
                cells = marketplace_cells(key, (), ())
                self.assertEqual(cells[:2], expected)
                self.assertEqual(cells[2], key.partition("/")[0])

    def test_the_headings_put_type_second_and_the_details_after_it(self) -> None:
        self.assertEqual(_HEADINGS, ("Artifact", "Type", *_DETAILS))


class OnlyArtifactAndTypeUntilDetailsAreAskedFor(unittest.TestCase):
    @given(
        st.lists(st.tuples(*(_CELL for _ in _HEADINGS)), min_size=1, max_size=10),
        st.integers(min_value=6 + 24 + 2 + 24, max_value=200),
    )
    def test_without_details_no_other_column_is_drawn(self, rows, width) -> None:
        keys = [f"offer-{index}" for index in range(len(rows))]

        drawn = render_marketplace_rows(
            rows, current=keys[0], selected=(), width=width, keys=keys, details=False
        )

        self.assertEqual(drawn[0].split(), ["Artifact", "Type"])
        self.assertEqual([line[6:].split() for line in drawn[2:]], [list(row[:2]) for row in rows])
        for heading in _DETAILS:
            self.assertNotIn(heading, drawn[0])

    @given(
        st.lists(st.tuples(*(_CELL for _ in _HEADINGS)), min_size=1, max_size=10),
        st.integers(min_value=6 + 8 * 24 + 7 * 2, max_value=260),
    )
    def test_with_details_every_column_is_drawn_after_artifact_and_type(self, rows, width) -> None:
        keys = [f"offer-{index}" for index in range(len(rows))]

        drawn = render_marketplace_rows(
            rows, current=keys[0], selected=(), width=width, keys=keys, details=True
        )

        self.assertEqual(drawn[0].split(), list(_HEADINGS))
        self.assertEqual([line[6:].split() for line in drawn[2:]], [list(row) for row in rows])

    def test_a_narrow_window_never_offers_a_detail_it_was_not_asked_for(self) -> None:
        drawn = render_marketplace_rows(
            (("review@1.2.0", "Skill", "company", "", "not installed", "", "claude", ""),),
            current="review@1.2.0",
            selected=(),
            width=20,
            details=False,
        )

        self.assertEqual(drawn[0].split(), ["Artifact"])
        self.assertEqual(drawn[2], "> [ ] review@1.2.0")
        self.assertIn("Widen the window to see: Type.", " ".join(drawn))
        for heading in _DETAILS:
            self.assertNotIn(heading, "\n".join(drawn))


class DTogglesTheDetails(unittest.TestCase):
    def test_the_footer_says_what_d_does_next(self) -> None:
        def offered(state: ConsumerUiState) -> list[str]:
            return [item.label for item in key_bindings(state) if item.key == "d"]

        self.assertEqual(offered(_marketplace()), ["Details"])
        self.assertEqual(offered(_marketplace(marketplace_details=True)), ["Hide details"])

    @given(
        st.lists(st.sampled_from(("a", "b", "c", "d")), unique=True, min_size=1),
        st.data(),
        st.integers(min_value=1, max_value=4),
    )
    def test_d_toggles_and_leaves_selection_search_and_cursor_alone(
        self, rows, data, presses
    ) -> None:
        cursor = data.draw(st.integers(min_value=0, max_value=len(rows) - 1))
        selection = tuple(data.draw(st.lists(st.sampled_from(rows), unique=True)))
        state = _marketplace(rows=tuple(rows), cursor=cursor, selection=selection, search="b")

        for _ in range(presses):
            event = key_event("d", state)
            self.assertIsNotNone(event)
            state, _commands = reduce_consumer_ui(state, event)

        self.assertIs(state.marketplace_details, presses % 2 == 1)
        self.assertEqual(
            (state.rows, state.cursor, state.selection, state.search),
            (tuple(rows), cursor, selection, "b"),
        )

    def test_d_is_a_letter_while_searching(self) -> None:
        state = _marketplace(searching=True)

        event = key_event("d", state)

        self.assertIsNot(event.kind, ConsumerUiEventKind.TOGGLE_MARKETPLACE_DETAILS)

    def test_the_choice_holds_across_screens(self) -> None:
        state = _marketplace(marketplace_details=True)

        for event in (
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.INSTALLED),
            ConsumerUiEvent(ConsumerUiEventKind.BACK),
        ):
            state, _commands = reduce_consumer_ui(state, event)

        self.assertIs(state.session.screen, ConsumerScreen.MARKETPLACE)
        self.assertTrue(state.marketplace_details)

    def test_d_means_nothing_elsewhere(self) -> None:
        state = ConsumerUiState(ConsumerSession(ConsumerScreen.INSTALLED))

        self.assertIsNone(key_event("d", state))
        self.assertNotIn("d", [item.key for item in key_bindings(state)])


def _reader(*lines: str):
    pending = list(lines)

    def read(_prompt: str = "") -> str:
        if not pending:
            raise EOFError
        return pending.pop(0)

    return read


class ThePersonSeesTwoColumnsThenAll(unittest.TestCase):
    def test_the_application_opens_marketplace_brief_and_d_adds_the_details(self) -> None:
        """The production composition over a real Registry; only the terminal is scripted."""

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env:
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project), user_home=str(env.home), today=dt.date(2026, 9, 1)
                )
                self.assertIsInstance(composed, Ok, composed)
                brief: list[str] = []
                tui.run_consumer_text(composed.value, read=_reader(""), write=brief.append)
                detailed: list[str] = []
                tui.run_consumer_text(composed.value, read=_reader("", "d"), write=detailed.append)

        before = "\n".join(brief).rpartition("AART / Marketplace")[2]
        after = "\n".join(detailed).rpartition("AART / Marketplace")[2]
        self.assertRegex(before, r"\n\s+Artifact\s+Type\n")
        self.assertRegex(before, r"> \[ \] code-review@1\.2\.0\s+Skill\n")
        self.assertNotIn("company", before.partition("[d] Details")[0])
        self.assertIn("[d] Details", before)
        self.assertRegex(after, r"Artifact\s+Type\s+Registry\s+Upstream\s+Status\s+Scope")
        # A hundred columns wrap the Artifact cell, so its first line carries the version's start.
        self.assertRegex(after, r"> \[ \] code-review@1\.\S*\s+Skill\s+company\s+servers\s")
        self.assertIn("[d] Hide details", after)
        self.assertIsNone(re.search(r"skill/code-review", before + after))


if __name__ == "__main__":
    unittest.main()
