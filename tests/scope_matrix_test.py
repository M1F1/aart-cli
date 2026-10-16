"""§172.5: screen 07a chooses a scope per artifact×harness pair, as a matrix of pairs by scopes.

Each row is one pair and each column one scope. A pair sits on exactly one scope, which starts on
the Settings default when that is offered and on the only offered scope otherwise. With more than
one pair an "All installations" row moves every pair that may go there at once.
"""

from __future__ import annotations

import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    ALL_INSTALLATIONS,
    choose_pair_scope,
    default_pair_scopes,
    pair_key,
    pair_scope_from_key,
    pair_scope_key,
    scope_choice_offered,
    scope_matrix_columns,
    scope_matrix_from_row,
    scope_matrix_rows,
)

GITHUB_CLAUDE = pair_key("company/mcp/github@1.5.0", "claude")
GITHUB_OPENCODE = pair_key("company/mcp/github@1.5.0", "opencode")
REVIEW_CLAUDE = pair_key("company/skill/code-review@1.0.0", "claude")
OFFERS = (
    (GITHUB_CLAUDE, ("project", "user")),
    (GITHUB_OPENCODE, ("project", "user")),
    (REVIEW_CLAUDE, ("user",)),
)


class TheScopeRowsTest(unittest.TestCase):
    def test_one_row_per_pair_and_an_all_row_only_when_there_are_several(self) -> None:
        rows = scope_matrix_rows(OFFERS)

        self.assertEqual(
            [scope_matrix_from_row(row) for row in rows],
            [
                (ALL_INSTALLATIONS, ("project", "user")),
                (GITHUB_CLAUDE, ("project", "user")),
                (GITHUB_OPENCODE, ("project", "user")),
                (REVIEW_CLAUDE, ("user",)),
            ],
        )
        self.assertEqual(scope_matrix_columns(rows), ("project", "user"))
        single = scope_matrix_rows(OFFERS[:1])
        self.assertEqual(len(single), 1)

    def test_a_row_that_is_not_a_scope_row_is_not_read_as_one(self) -> None:
        for row in ("scope:user", "pairs:x\tclaude", "scopes:nope\tuser", "scopes:*\tglobal"):
            with self.subTest(row=row):
                self.assertIsNone(scope_matrix_from_row(row))

    def test_there_is_a_choice_only_when_some_pair_has_two_scopes(self) -> None:
        self.assertTrue(scope_choice_offered(scope_matrix_rows(OFFERS)))
        self.assertFalse(scope_choice_offered(scope_matrix_rows(OFFERS[2:])))


class TheStartingScopeTest(unittest.TestCase):
    def test_each_pair_starts_on_the_default_when_offered_and_on_its_only_scope_otherwise(
        self,
    ) -> None:
        self.assertEqual(
            default_pair_scopes(OFFERS, "project"),
            (
                pair_scope_key(GITHUB_CLAUDE, "project"),
                pair_scope_key(GITHUB_OPENCODE, "project"),
                pair_scope_key(REVIEW_CLAUDE, "user"),
            ),
        )

    def test_a_choice_is_kept_and_one_for_a_pair_or_scope_no_longer_offered_is_dropped(
        self,
    ) -> None:
        chosen = (
            pair_scope_key(GITHUB_OPENCODE, "user"),
            pair_scope_key(REVIEW_CLAUDE, "project"),
            pair_scope_key(pair_key("company/mcp/gone@1.0.0", "claude"), "user"),
        )

        self.assertEqual(
            default_pair_scopes(OFFERS, "project", chosen),
            (
                pair_scope_key(GITHUB_CLAUDE, "project"),
                pair_scope_key(GITHUB_OPENCODE, "user"),
                pair_scope_key(REVIEW_CLAUDE, "user"),
            ),
        )


class ChoosingAScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = scope_matrix_rows(OFFERS)
        self.start = default_pair_scopes(OFFERS, "project")

    def test_a_pair_moves_to_the_scope_chosen_for_it_and_no_other_pair_moves(self) -> None:
        moved = choose_pair_scope(self.rows, self.start, self.rows[2], "user")

        self.assertEqual(
            set(moved),
            {
                pair_scope_key(GITHUB_CLAUDE, "project"),
                pair_scope_key(GITHUB_OPENCODE, "user"),
                pair_scope_key(REVIEW_CLAUDE, "user"),
            },
        )

    def test_a_scope_a_pair_is_not_offered_changes_nothing(self) -> None:
        self.assertEqual(
            choose_pair_scope(self.rows, self.start, self.rows[3], "project"), self.start
        )

    def test_the_all_row_moves_every_pair_that_may_go_there(self) -> None:
        moved = choose_pair_scope(self.rows, self.start, self.rows[0], "project")

        self.assertEqual(
            set(moved),
            {
                pair_scope_key(GITHUB_CLAUDE, "project"),
                pair_scope_key(GITHUB_OPENCODE, "project"),
                pair_scope_key(REVIEW_CLAUDE, "user"),
            },
        )

    @given(
        st.lists(st.tuples(st.integers(0, 3), st.sampled_from(("project", "user"))), max_size=12)
    )
    def test_every_pair_always_has_exactly_one_scope_it_is_offered(self, presses) -> None:
        offered = dict(OFFERS)
        chosen = self.start
        for row, scope in presses:
            chosen = choose_pair_scope(self.rows, chosen, self.rows[row], scope)
            held = [pair_scope_from_key(key) for key in chosen]
            self.assertEqual(sorted(pair for pair, _ in held), sorted(offered))  # type: ignore[misc]
            for pair, held_scope in held:  # type: ignore[misc]
                self.assertIn(held_scope, offered[pair])

    @given(st.sampled_from(("project", "user")))
    def test_a_pair_scope_key_reads_back(self, scope) -> None:
        self.assertEqual(
            pair_scope_from_key(pair_scope_key(GITHUB_CLAUDE, scope)), (GITHUB_CLAUDE, scope)
        )


class ContinuingFromTheScopeScreenTest(unittest.TestCase):
    def test_enter_goes_to_ready_only_once_the_plan_is_the_one_prepared_for_these_scopes(
        self,
    ) -> None:
        from dataclasses import replace

        from aart_cli.application.consumer_views import ConsumerScreen
        from tests.screen_cases import screen_cases

        case = next(item for item in screen_cases() if item.screen is ConsumerScreen.INSTALL_SCOPE)
        moved = choose_pair_scope(
            case.state.rows, case.state.pair_scopes, case.state.rows[1], "user"
        )

        self.assertIs(case.source.detail(case.state), ConsumerScreen.READY)
        # The choice is made but its plan is still being prepared: Ready would review the old one.
        self.assertIsNone(case.source.detail(replace(case.state, pair_scopes=moved)))


if __name__ == "__main__":
    unittest.main()
