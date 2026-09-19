"""A list that draws a header keeps every row on that header's grid (`QA-030`).

The acceptance run synchronized two Sources and screen 35 stopped being a table: the header stayed
aligned while `skill/verification-before-completion` pushed `VERSION` and `SOURCE` out of their
columns, so no column could be read down. The operator asked for the general shape rather than a
wider `ARTIFACT` column -- "powinno wszystko być w kolumnach, a nie taki przepchany tekst; powinno
najwyżej ucinać nazwy, ale jak się najedzie kursorem, to pod spodem jest całość".

The claims here are stated over the shared grid rather than over one screen, because `B-107` found
the layout kernel's width arithmetic unheld: a bounded row, a truncated cell, and a column whose
position is the same on every row including the header. Truncating is only acceptable because the
row under the cursor is described in full (in Verbose, below the table since CP-23 task 02), so
nothing is actually hidden.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.application.consumer_views import PresentationProfile
from aart_cli.application.maintainer_views import (
    MaintainerBulkCandidateView,
    MaintainerBulkPromotionView,
    MaintainerCandidateView,
)
from aart_cli.domain.candidates import CandidateState
from aart_cli.tui_layout import CONTENT_MEASURE, STAGE_PROJECTION
from aart_cli.tui_maintainer import (
    maintainer_candidate_detail,
    render_maintainer_bulk_promotion,
    render_maintainer_candidates,
)

# `differing_executors` is suppressed for the reason `doctor_properties_test` records: the scoped
# `make mutants` run re-runs the same test method object from a fresh runner per mutant.
MUTATION_SETTINGS = settings(suppress_health_check=(HealthCheck.differing_executors,))

LONG = "skill/verification-before-completion"
#: Long enough that the grid cannot fit it inside `CONTENT_MEASURE` and has to cut it -- the
#: operator's own name is only 36 characters and legitimately fits.
OVERSIZED = "mcp/" + "a-very-long-artifact-name" * 4
HEADINGS = ("STATUS", "ARTIFACT", "VERSION", "SOURCE")


def _candidate(
    artifact: str = "mcp/aart-e2e-mcp",
    *,
    version: str = "1.0.0",
    source: str = "aart-test-mcp",
    state: CandidateState = CandidateState.NEW,
) -> MaintainerCandidateView:
    return MaintainerCandidateView(
        id=f"{artifact}:{version}",
        state=state,
        coordinate=f"{source}/{artifact}@{version}",
        artifact=artifact,
        version=version,
        kind=artifact.split("/", 1)[0],
        source_alias=source,
        source_location=f"https://git.example.test/team/{source}.git",
        source_revision="a" * 40,
        manifest_path="aart.yaml",
        input_digest="sha256:" + "b" * 64,
        payload_digest="sha256:" + "c" * 64,
        canonical_digest="sha256:" + "d" * 64,
        target_registry="registry",
        runtime=None,
        transport=None,
        inputs=(),
        dependency_descriptor=None,
        findings=(),
        previous=None,
        successor=None,
        rejection_reason=None,
        baseline="None",
        semantic_changes=(),
        file_changes=(),
    )


def _columns(header: str) -> tuple[tuple[str, int], ...]:
    """Where each heading starts on the header line -- the grid every row has to share."""

    return tuple((heading, header.index(heading)) for heading in HEADINGS)


#: The `> ` cursor gutter every list row starts with; the header over the rows has none (CP-23 14).
GUTTER = 2


def _assert_rows_share_the_header_grid(
    case: unittest.TestCase, header: str, rows: tuple[str, ...]
) -> None:
    grid = _columns(header)
    for row in rows:
        case.assertIn(
            row[:GUTTER], ("> ", "  "), f"a row does not start with the cursor gutter: {row!r}"
        )
        for index, (heading, offset) in enumerate(grid):
            start = offset + GUTTER if index == 0 else offset
            cell = row[start:]
            if index + 1 < len(grid):
                cell = row[start : grid[index + 1][1]]
            case.assertTrue(
                not cell.strip() or not cell[:1].isspace(),
                f"{heading} does not start where the header says: {row!r}",
            )
            if index + 1 < len(grid):
                case.assertTrue(
                    not cell or cell.endswith(" "),
                    f"{heading} runs into the next column: {row!r}",
                )


class CandidateListHoldsItsColumnsTest(unittest.TestCase):
    def _rendered(self, *candidates: MaintainerCandidateView, cursor: str = "") -> tuple[str, ...]:
        return render_maintainer_candidates(
            candidates, cursor=cursor, profile=PresentationProfile.FAST
        )

    def test_a_long_name_does_not_push_the_later_columns_out(self) -> None:
        """The operator's own two rows, which is where the table stopped being one."""

        rendered = self._rendered(
            _candidate(),
            _candidate(LONG, source="superpowers-test"),
        )

        header, *rows = rendered[: rendered.index("") if "" in rendered else len(rendered)]
        _assert_rows_share_the_header_grid(self, header, tuple(rows))

    def test_a_name_too_long_for_its_column_is_truncated(self) -> None:
        rendered = self._rendered(_candidate(OVERSIZED))

        listed = [line for line in rendered if "a-very-long" in line]
        self.assertTrue(listed, rendered)
        self.assertTrue(
            any(STAGE_PROJECTION in line for line in listed),
            f"the long name was not truncated: {listed}",
        )
        for line in rendered:
            self.assertLessEqual(len(line), CONTENT_MEASURE, line)

    def test_no_row_is_wider_than_the_content_measure(self) -> None:
        rendered = self._rendered(
            _candidate(),
            _candidate(LONG, source="superpowers-test"),
        )

        for line in rendered:
            self.assertLessEqual(len(line), CONTENT_MEASURE, line)

    def test_the_row_under_the_cursor_is_described_in_full(self) -> None:
        """Truncation is only honest because nothing is actually hidden by it.

        CP-23 task 02 moved the full row out of the table into the cursor description, which the
        frame draws below the table in Verbose (D-252).
        """

        focused = _candidate(LONG, source="superpowers-test")

        described = maintainer_candidate_detail((_candidate(), focused), cursor=focused.id)

        self.assertTrue(
            any(line.strip().endswith(LONG) for line in described),
            f"the focused name is nowhere in full: {described}",
        )

    def test_nothing_is_described_when_the_cursor_is_on_nothing(self) -> None:
        candidates = (_candidate(LONG, source="superpowers-test"),)

        self.assertEqual(maintainer_candidate_detail(candidates, cursor=""), ())
        self.assertFalse(
            any(line.strip().endswith(LONG) for line in self._rendered(*candidates)),
            "an unfocused row was expanded anyway",
        )

    def test_an_empty_list_still_says_so(self) -> None:
        self.assertEqual(
            render_maintainer_candidates((), profile=PresentationProfile.FAST),
            ("No active Candidates have been discovered.",),
        )

    @MUTATION_SETTINGS
    @given(
        names=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=60
            ),
            min_size=1,
            max_size=6,
            unique=True,
        )
    )
    def test_the_grid_holds_for_any_names(self, names: list[str]) -> None:
        candidates = tuple(_candidate(f"mcp/{name}") for name in names)

        rendered = render_maintainer_candidates(candidates, profile=PresentationProfile.FAST)

        header, *rest = rendered
        rows = [line for line in rest if line.strip()][: len(candidates)]
        _assert_rows_share_the_header_grid(self, header, tuple(rows))
        for line in rendered:
            self.assertLessEqual(len(line), CONTENT_MEASURE, line)


class BulkPromotionHoldsItsColumnsTest(unittest.TestCase):
    """`QA-030` says to check the other tabular lists; screen 47 is the other one."""

    def _view(self, *artifacts: str) -> MaintainerBulkPromotionView:
        return MaintainerBulkPromotionView(
            target_registry="registry",
            candidates=tuple(
                MaintainerBulkCandidateView(
                    candidate_id=artifact,
                    artifact=artifact,
                    version="1.0.0",
                    state=CandidateState.READY,
                )
                for artifact in artifacts
            ),
        )

    def test_the_selectable_rows_line_up_with_each_other(self) -> None:
        rendered = render_maintainer_bulk_promotion(
            (self._view("mcp/aart-e2e-mcp", LONG),),
            (),
        )

        rows = [line for line in rendered if line.lstrip().startswith(("[ ]", "[x]"))]
        self.assertEqual(len(rows), 2, rendered)
        first, second = rows
        self.assertEqual(
            [index for index, character in enumerate(first) if character == " "][:0],
            [index for index, character in enumerate(second) if character == " "][:0],
        )
        self.assertEqual(first.index("1.0.0"), second.index("1.0.0"), rows)

    def test_no_bulk_row_is_wider_than_the_content_measure(self) -> None:
        rendered = render_maintainer_bulk_promotion(
            (self._view("mcp/aart-e2e-mcp", LONG),),
            (),
        )

        for line in rendered:
            self.assertLessEqual(len(line), CONTENT_MEASURE, line)


if __name__ == "__main__":
    unittest.main()
