"""CP-23 task 14: Maintainer list screens draw rows, the cursor, and describe them only in Verbose.

The audit found the Maintainer lists breaking §167's shared frame the way the Consumer lists had:
Candidates drew its cursor inside a table gutter no reader of rows would recognise, Validation and
Bulk Promotion drew no cursor at all, Scan Result and Adopted Artifacts explained their keys in
prose among the rows, and Candidate Filters, Collection Candidates, Registry Maintainer and the scan
grew their rows when `v` was pressed instead of describing the row under the cursor.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import (
    MaintainerBulkPromotionView,
    MaintainerCandidateFilter,
    MaintainerScreen,
    MaintainerViews,
    MaintainerWorkingTreeState,
    MaintainerWorkingTreeView,
    project_maintainer_collection_candidate,
    project_maintainer_collection_validation,
    project_maintainer_dashboard,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    ConsumerScreens,
    _reload,
    compose_frame,
)
from agent_artifacts.tui_maintainer import (
    maintainer_bulk_promotion_status,
    maintainer_registry_detail,
    maintainer_registry_rows,
    render_maintainer_registry,
)
from tests import (
    maintainer_bulk_promotion_test,
    maintainer_candidate_filters_test,
    maintainer_collection_candidate_test,
    maintainer_registry_view_test,
    maintainer_validation_views_test,
)
from tests.consumer_shell_test import screens
from tests.frame_contract import frame_violations, key_violations, toggle_violations
from tests.maintainer_repository_adoption_test import _ADOPTED, _scan


def _on(source: CanonicalScreenSource, screen: MaintainerScreen, **fields) -> ConsumerUiState:
    state = ConsumerUiState(
        ConsumerSession(screen), settings=ConsumerSettings().with_maintainer_mode(True), **fields
    )
    return _reload(source, state, entering=True)


def _verbose(state: ConsumerUiState) -> ConsumerUiState:
    toggled, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE))
    return toggled


def _every_cursor(state: ConsumerUiState):
    yield state
    yield _verbose(state)
    for cursor in range(len(state.rows)):
        at = replace(state, cursor=cursor)
        yield at
        yield _verbose(at)


class _Contract(unittest.TestCase):
    def assertKeepsTheFrame(self, source: CanonicalScreenSource, state: ConsumerUiState) -> None:
        for drawn in _every_cursor(state):
            with self.subTest(
                screen=drawn.session.screen, cursor=drawn.cursor, profile=drawn.session.profile
            ):
                self.assertEqual(frame_violations(source, drawn), ())
                self.assertEqual(toggle_violations(source, drawn), ())
                self.assertEqual(key_violations(source, drawn), ())


class CandidatesAndFiltersTest(_Contract):
    def setUp(self) -> None:
        self.source = maintainer_candidate_filters_test._shell(
            maintainer_candidate_filters_test._views()
        )

    def test_35_candidates_is_a_table_of_cursor_rows_under_its_column_heading(self) -> None:
        state = _on(self.source, MaintainerScreen.CANDIDATES)

        self.assertKeepsTheFrame(self.source, state)
        self.assertTrue(self.source.actions(state)[1].startswith("> "))

    def test_53_filters_are_rows_and_what_they_leave_is_the_view_status(self) -> None:
        unfiltered = _on(self.source, MaintainerScreen.CANDIDATE_FILTERS)
        filtered = _on(
            self.source,
            MaintainerScreen.CANDIDATE_FILTERS,
            candidate_filter=MaintainerCandidateFilter(registries=("company",)),
        )

        for state in (unfiltered, filtered):
            self.assertKeepsTheFrame(self.source, state)
        self.assertIn("Showing 4 of 4 Candidates", self.source.status(unfiltered))

    def test_53_with_nothing_to_narrow_offers_no_toggle(self) -> None:
        source = maintainer_candidate_filters_test._shell(
            MaintainerViews(project_maintainer_dashboard(()), ())
        )

        self.assertKeepsTheFrame(source, _on(source, MaintainerScreen.CANDIDATE_FILTERS))


class ValidationTest(_Contract):
    def test_38_checks_are_cursor_rows_and_the_verdict_is_the_view_status(self) -> None:
        views = maintainer_validation_views_test._views(
            EffectivePolicy(required_checks=frozenset({"live-acceptance"}))
        )
        source = maintainer_validation_views_test._shell(views)
        assert views.candidates is not None

        state = _on(source, MaintainerScreen.VALIDATION, focus=views.candidates[0].id)

        self.assertKeepsTheFrame(source, state)


class CollectionCandidatesTest(_Contract):
    def test_51_describes_the_collection_under_the_cursor_rather_than_growing_its_row(self) -> None:
        module = maintainer_collection_candidate_test
        candidate = module._candidate(
            module._request("github", "^1"), module._request("jira", "^3")
        )
        views = MaintainerViews(
            project_maintainer_dashboard(()),
            (),
            collection_candidates=(project_maintainer_collection_candidate(candidate),),
            collection_validations=(
                project_maintainer_collection_validation(candidate, module._approved_marketplace()),
            ),
        )
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
        )

        self.assertKeepsTheFrame(source, _on(source, MaintainerScreen.COLLECTION_CANDIDATES))


class RegistryMaintainerTest(_Contract):
    def test_46_keeps_the_frame_on_every_registry_row(self) -> None:
        fixture = maintainer_registry_view_test.MaintainerRegistryShellTest()
        fixture.setUp()

        state = _on(fixture.source, MaintainerScreen.REGISTRY)

        self.assertKeepsTheFrame(fixture.source, state)

    def test_46_with_no_row_verbose_says_what_snapshots_are_for_as_the_view_status(self) -> None:
        fixture = maintainer_registry_view_test.MaintainerRegistryShellTest()
        fixture.setUp()
        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                maintainer=MaintainerViews(fixture.views.dashboard, fixture.views.sources),
            )
        )
        state = _on(source, MaintainerScreen.REGISTRY)
        assert not state.rows

        self.assertKeepsTheFrame(source, state)
        fast = compose_frame(source, state)
        verbose = compose_frame(source, _verbose(state))
        self.assertNotIn("- Connected Registry snapshots", fast.status)
        self.assertIn("- Connected Registry snapshots", verbose.status)
        self.assertEqual(verbose.described, ())

    def test_46_verbose_spells_out_the_digests_the_row_shortens(self) -> None:
        fixture = maintainer_registry_view_test.MaintainerRegistryShellTest()
        fixture.setUp()
        snapshot = fixture.view.snapshot
        assert snapshot is not None

        state = _verbose(_on(fixture.source, MaintainerScreen.REGISTRY))

        self.assertNotIn(snapshot, "\n".join(fixture.source.actions(state)))
        self.assertIn(f"Snapshot: {snapshot}", compose_frame(fixture.source, state).described)

    def test_46_registries_are_separated_and_the_working_tree_needs_a_workspace(self) -> None:
        fixture = maintainer_registry_view_test.MaintainerRegistryShellTest()
        fixture.setUp()
        company, other = fixture.view, replace(fixture.view, alias="other")

        rows = maintainer_registry_rows((company, other), cursor="other")
        without = maintainer_registry_rows((company,))
        no_workspace = maintainer_registry_rows((company,), registry_workspace_present=False)

        self.assertEqual(
            rows,
            (
                *render_maintainer_registry(company),
                "",
                *render_maintainer_registry(other, selected=True),
            ),
        )
        self.assertIn("    Working tree: matches the approved snapshot", without)
        self.assertEqual(no_workspace, render_maintainer_registry(company, show_working_tree=False))
        self.assertNotIn("    Working tree: matches the approved snapshot", no_workspace)

    def test_46_detail_spells_out_what_was_observed_and_only_that(self) -> None:
        fixture = maintainer_registry_view_test.MaintainerRegistryShellTest()
        fixture.setUp()
        view = fixture.view
        (promotion,) = view.transactions
        unobserved = replace(
            view,
            revision=None,
            working_tree=MaintainerWorkingTreeView(MaintainerWorkingTreeState.UNOBSERVED, None),
            transactions=(),
        )

        self.assertEqual(
            maintainer_registry_detail(view),
            (
                f"Revision: {view.revision}",
                f"Snapshot: {view.snapshot}",
                f"Working tree observed: {view.working_tree.digest}",
                f"Promotion {promotion.snapshot_after} ({promotion.mode})",
                *(f"  {candidate}" for candidate in promotion.candidate_ids),
            ),
        )
        self.assertEqual(
            maintainer_registry_detail(unobserved),
            ("Revision: none", f"Snapshot: {view.snapshot}"),
        )


class BulkPromotionTest(_Contract):
    def test_47_candidates_are_cursor_rows_and_refusals_are_the_view_status(self) -> None:
        module = maintainer_bulk_promotion_test
        scan = module._scan(("github-mcp", "jira-mcp"), flawed=frozenset({"jira-mcp"}))
        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                maintainer=module._views(EffectivePolicy(), scan),
            )
        )
        state = _on(source, MaintainerScreen.BULK_PROMOTION)

        self.assertKeepsTheFrame(source, state)
        self.assertKeepsTheFrame(source, replace(state, selection=state.rows))
        status = "\n".join(compose_frame(source, state).status)
        self.assertIn("Not promotable: mcp/jira-mcp", status)

    def test_47_status_says_why_nothing_can_be_promoted_and_is_silent_otherwise(self) -> None:
        empty = MaintainerBulkPromotionView("company", ())
        refused = MaintainerBulkPromotionView("company", (), refusals=("the registry is invalid",))
        module = maintainer_bulk_promotion_test
        offered = module._views(EffectivePolicy(), module._scan(("github-mcp",))).bulk_promotions

        self.assertEqual(
            maintainer_bulk_promotion_status(()), ("Bulk promotion has nothing composed yet.",)
        )
        self.assertEqual(
            maintainer_bulk_promotion_status((empty,)),
            ("company", "  No Candidate of this registry can be promoted right now."),
        )
        self.assertEqual(
            maintainer_bulk_promotion_status((refused,)), ("company", "  - the registry is invalid")
        )
        self.assertTrue(offered and all(view.candidates for view in offered))
        self.assertEqual(maintainer_bulk_promotion_status(offered), ())


class RepositoryAdoptionTest(_Contract):
    def test_46d_scan_result_rows_are_what_can_be_adopted(self) -> None:
        from agent_artifacts.io.consumer_actions import _project_repository_scan

        source = CanonicalScreenSource(
            ConsumerScreens(screens().dashboard, repository_scan=_project_repository_scan(_scan()))
        )
        state = _on(source, MaintainerScreen.SCAN_RESULT)

        self.assertKeepsTheFrame(source, state)
        self.assertKeepsTheFrame(source, replace(state, selection=state.rows))
        status = "\n".join(source.status(state))
        self.assertIn("skill/unfinished@1.0.0", status)

    def test_46f_adopted_artifacts_are_rows_with_no_key_prose(self) -> None:
        from agent_artifacts.io.consumer_actions import _project_adopted_artifact

        source = CanonicalScreenSource(
            ConsumerScreens(
                screens().dashboard, adopted_artifacts=(_project_adopted_artifact(_ADOPTED),)
            )
        )

        self.assertKeepsTheFrame(source, _on(source, MaintainerScreen.ADOPTED_ARTIFACTS))


if __name__ == "__main__":
    unittest.main()
