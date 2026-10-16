"""§172.2: screen 05 chooses harnesses per artifact, as a matrix of artifacts by harnesses.

Each row is one artifact and each column one harness. A cell is ticked, unticked, or `–` where that
artifact cannot go into that harness. With more than one artifact an "All artifacts" row ticks or
unticks a whole column at once, over the artifacts that column can host. The choice is a set of
artifact×harness pairs, and each pair becomes one installation.
"""

from __future__ import annotations

import unittest
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
)
from aart_cli.application.consumer_views import (
    ALL_ARTIFACTS,
    ConsumerScreen,
    ConsumerSession,
    HarnessTargetView,
    matrix_columns,
    matrix_from_row,
    matrix_rows,
    pair_choice_problems,
    pair_from_key,
    pair_key,
    toggle_matrix_cell,
)
from aart_cli.domain.result import Ok
from aart_cli.io.receipt_store import LocalReceiptStore

GITHUB = "company/mcp/github@1.5.0"
JIRA = "company/mcp/jira@2.0.0"
REVIEW = "company/skill/code-review@1.0.0"
TARGETS = (
    HarnessTargetView("claude", (GITHUB, JIRA)),
    HarnessTargetView("opencode", (GITHUB, JIRA, REVIEW)),
    HarnessTargetView("tabnine", (GITHUB,)),
)


class TheMatrixRowsTest(unittest.TestCase):
    def test_one_row_per_artifact_and_an_all_row_only_when_there_are_several(self) -> None:
        rows = matrix_rows(TARGETS)

        self.assertEqual(
            [matrix_from_row(row) for row in rows],
            [
                (ALL_ARTIFACTS, ("claude", "opencode", "tabnine")),
                (GITHUB, ("claude", "opencode", "tabnine")),
                (JIRA, ("claude", "opencode")),
                (REVIEW, ("opencode",)),
            ],
        )
        self.assertEqual(matrix_columns(rows), ("claude", "opencode", "tabnine"))
        single = matrix_rows((HarnessTargetView("claude", (GITHUB,)),))
        self.assertEqual([matrix_from_row(row) for row in single], [(GITHUB, ("claude",))])

    def test_a_row_that_is_not_a_matrix_row_is_not_read_as_one(self) -> None:
        self.assertIsNone(matrix_from_row("target:claude"))
        self.assertIsNone(matrix_from_row("scope:user"))


class TickingCellsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = matrix_rows(TARGETS)

    def test_a_cell_ticks_and_unticks_one_pair(self) -> None:
        ticked = toggle_matrix_cell(self.rows, (), self.rows[2], "claude")
        self.assertEqual(ticked, (pair_key(JIRA, "claude"),))
        self.assertEqual(toggle_matrix_cell(self.rows, ticked, self.rows[2], "claude"), ())

    def test_a_cell_the_artifact_cannot_go_into_changes_nothing(self) -> None:
        self.assertEqual(toggle_matrix_cell(self.rows, (), self.rows[3], "tabnine"), ())

    def test_the_all_row_ticks_a_column_over_what_it_can_host_then_clears_it(self) -> None:
        ticked = toggle_matrix_cell(
            self.rows, (pair_key(GITHUB, "claude"),), self.rows[0], "claude"
        )
        self.assertEqual(set(ticked), {pair_key(GITHUB, "claude"), pair_key(JIRA, "claude")})
        self.assertEqual(toggle_matrix_cell(self.rows, ticked, self.rows[0], "claude"), ())

    def test_the_all_row_leaves_other_columns_alone(self) -> None:
        kept = (pair_key(REVIEW, "opencode"),)
        ticked = toggle_matrix_cell(self.rows, kept, self.rows[0], "tabnine")
        self.assertEqual(set(ticked), {pair_key(REVIEW, "opencode"), pair_key(GITHUB, "tabnine")})

    @given(st.lists(st.tuples(st.integers(0, 3), st.integers(0, 2)), max_size=12))
    def test_every_ticked_pair_is_one_the_matrix_offers(self, presses) -> None:
        columns = matrix_columns(self.rows)
        offered = {
            pair_key(artifact, harness)
            for artifact, harnesses in map(matrix_from_row, self.rows[1:])  # type: ignore[misc]
            for harness in harnesses
        }
        pairs: tuple[str, ...] = ()
        for row, column in presses:
            pairs = toggle_matrix_cell(self.rows, pairs, self.rows[row], columns[column])
            self.assertLessEqual(set(pairs), offered)
            self.assertEqual(len(set(pairs)), len(pairs))


class PairChoiceProblemsTest(unittest.TestCase):
    def test_every_artifact_needs_a_harness(self) -> None:
        problems = pair_choice_problems(TARGETS, (pair_key(GITHUB, "claude"),))

        self.assertEqual(
            problems,
            (
                f"Choose a harness for {JIRA}; it can go into claude, opencode.",
                f"Choose a harness for {REVIEW}; it can go into opencode.",
            ),
        )

    def test_nothing_ticked_says_so_once(self) -> None:
        self.assertEqual(pair_choice_problems(TARGETS, ()), ("Choose at least one harness.",))

    def test_a_pair_no_longer_offered_is_refused_by_name(self) -> None:
        pairs = (pair_key(GITHUB, "claude"), pair_key(JIRA, "claude"), pair_key(REVIEW, "tabnine"))

        problems = pair_choice_problems(TARGETS, (*pairs, pair_key(REVIEW, "opencode")))

        self.assertEqual(problems, (f"{REVIEW} cannot go into tabnine; untick it.",))

    def test_a_complete_choice_has_no_problems(self) -> None:
        pairs = (
            pair_key(GITHUB, "tabnine"),
            pair_key(JIRA, "claude"),
            pair_key(REVIEW, "opencode"),
        )
        self.assertEqual(pair_choice_problems(TARGETS, pairs), ())
        self.assertEqual(pair_choice_problems((), ()), ())

    @given(
        st.text(min_size=1, max_size=8).filter(lambda text: "\t" not in text and "\n" not in text)
    )
    def test_a_pair_key_reads_back(self, harness) -> None:
        self.assertEqual(pair_from_key(pair_key(GITHUB, harness)), (GITHUB, harness))


class TheArrowsMoveBetweenHarnessesTest(unittest.TestCase):
    def test_left_and_right_move_the_column_on_the_matrix_and_mean_nothing_elsewhere(self) -> None:
        on_matrix = ConsumerUiState(
            ConsumerSession(ConsumerScreen.REVIEW_SELECTION),
            rows=matrix_rows(TARGETS),
            action=ConsumerActionKind.INSTALL,
        )
        elsewhere = ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE), rows=("a",))

        for key in ("left", "right"):
            with self.subTest(key=key):
                moved = key_event(key, on_matrix)
                assert moved is not None
                self.assertIs(moved.kind, ConsumerUiEventKind.MOVE_COLUMN)
                # A key the shell can send is never an error, only a key with no meaning here.
                self.assertIsNone(key_event(key, elsewhere))


class EachTickedPairIsInstalledTest(unittest.TestCase):
    def test_two_artifacts_each_go_only_into_the_harness_ticked_for_them(self) -> None:
        from tests.configured_install_command_e2e_test import _environment
        from tests.configured_installation_draft_e2e_test import _published_registries
        from tests.consumer_application_e2e_test import _at, _drive
        from tests.consumer_shell_test import DOWN, ENTER, RIGHT, SPACE
        from tests.installation_harness_choice_test import _AUTHORED_MCP, _AUTHORED_SKILL

        def both(_authored, **keywords):
            return _published_registries(_AUTHORED_SKILL, _AUTHORED_MCP, **keywords)

        with (
            mock.patch("tests.configured_install_command_e2e_test._published_registry", both),
            _environment() as env,
        ):
            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.MARKETPLACE),
                SPACE,
                DOWN,
                SPACE,
                ord("i"),
                # Past "All artifacts" to the MCP's row, claude; then the Skill's row, opencode.
                DOWN,
                SPACE,
                DOWN,
                RIGHT,
                SPACE,
                ENTER,
                ENTER,
            )

            self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
            stored = LocalReceiptStore(str(env.paths.data_root) + "/state").installations()
            assert isinstance(stored, Ok), getattr(stored, "diagnostics", ())
            self.assertEqual(
                sorted(
                    (item.receipt.owner.artifact.name, item.receipt.owner.harness)
                    for item in stored.value
                ),
                [("code-review", "opencode"), ("dummy", "claude")],
            )
            self.assertFalse((env.project / ".claude/skills").exists())
            self.assertFalse((env.project / "opencode.json").exists())


if __name__ == "__main__":
    unittest.main()
