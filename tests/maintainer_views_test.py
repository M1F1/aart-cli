"""CP-14 screens 30–32 project canonical Source and Candidate state without IO."""

from __future__ import annotations

import dataclasses
import unittest

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    project_dashboard,
)
from aart_cli.application.maintainer import (
    CandidateBundle,
    SourceScan,
    reconcile_source_scan,
)
from aart_cli.application.maintainer_views import (
    UNBOUND_SCAN_DIAGNOSTIC,
    MaintainerScreen,
    MaintainerSourceStatus,
    MaintainerViews,
    project_maintainer_dashboard,
    project_maintainer_source,
)
from aart_cli.configuration.model import SourceKind
from aart_cli.domain.candidates import (
    CandidateFinding,
    CandidateState,
    FindingSeverity,
    assess_candidate,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Ok
from aart_cli.sources.model import HealthStatus, SourceHealth
from aart_cli.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from aart_cli.tui_maintainer import (
    render_maintainer_dashboard,
    render_maintainer_source,
    render_maintainer_sources,
)
from tests.maintainer_source_scan_test import _compiled
from tests.marketplace_fixtures import configured_source, source_state


def _scan(state: CandidateState = CandidateState.READY) -> SourceScan:
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        _compiled(),
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok)
    bundle = scanned.value.active[0]
    if state is CandidateState.READY:
        candidate = assess_candidate(bundle.candidate)
    elif state is CandidateState.INVALID:
        candidate = assess_candidate(
            bundle.candidate,
            findings=(
                CandidateFinding(
                    "manifest-schema",
                    FindingSeverity.ERROR,
                    "artifact version is missing",
                ),
            ),
        )
    else:
        candidate = dataclasses.replace(bundle.candidate, state=state)
    updated = CandidateBundle(candidate, bundle.artifact)
    return SourceScan(
        scanned.value.source_alias,
        scanned.value.revision,
        1,
        (updated,),
        (updated,),
    )


def _source(state: CandidateState = CandidateState.READY):
    configured = configured_source("authors", SourceKind.SOURCE_GIT)
    health = source_state(
        configured,
        "author-source",
        display_order=0,
        resolved_revision="a" * 40,
    ).health
    return project_maintainer_source(configured, health, _scan(state))


class MaintainerProjectionTest(unittest.TestCase):
    def test_dashboard_counts_sources_candidates_failures_and_ready(self) -> None:
        invalid = _source(CandidateState.INVALID)
        disabled_source = configured_source(
            "local-authors",
            SourceKind.SOURCE_LOCAL,
            enabled=False,
        )
        disabled = project_maintainer_source(
            disabled_source,
            SourceHealth(HealthStatus.MISSING, None, None),
        )

        dashboard = project_maintainer_dashboard(
            (invalid, disabled),
            recent_activity=("Synced authors", "Validation failed for github-mcp"),
        )

        self.assertEqual(dashboard.source_count, 2)
        self.assertEqual(dashboard.candidate_count, 1)
        self.assertEqual(dashboard.validation_failure_count, 1)
        self.assertEqual(dashboard.ready_count, 0)
        self.assertEqual(dashboard.recent_activity[0], "Synced authors")

    def test_source_projection_binds_configuration_health_and_one_matching_scan(self) -> None:
        source = _source()

        self.assertEqual(source.alias, "authors")
        self.assertEqual(source.location, "https://authors.example/agents/authors.git")
        self.assertEqual(source.branch, "main")
        self.assertEqual(source.revision, "a" * 40)
        self.assertEqual(source.manifest_count, 1)
        self.assertEqual(source.candidate_count, 1)
        self.assertEqual(source.ready_count, 1)
        self.assertEqual(source.invalid_count, 0)

    def test_a_scan_from_another_revision_is_projected_as_needing_a_sync(self) -> None:
        """CP-24.01: not Candidate data for this pin, so not projected as any -- and not fatal."""

        configured = configured_source("authors", SourceKind.SOURCE_GIT)
        health = source_state(
            configured,
            "author-source",
            display_order=0,
            resolved_revision="b" * 40,
        ).health

        projected = project_maintainer_source(configured, health, _scan())

        self.assertEqual(projected.status, MaintainerSourceStatus.ATTENTION)
        self.assertEqual(projected.manifest_count, 0)
        self.assertEqual(projected.candidate_count, 0)
        self.assertEqual(projected.target_registries, ())
        self.assertEqual(projected.diagnostics[-1], UNBOUND_SCAN_DIAGNOSTIC)

    def test_the_sync_remedy_is_added_to_the_source_own_diagnostics_not_instead_of_them(
        self,
    ) -> None:
        """Whatever health already had to say is still said, redacted, and said first."""

        configured = configured_source("authors", SourceKind.SOURCE_GIT)
        state = source_state(
            configured,
            "author-source",
            display_order=0,
            resolved_revision="b" * 40,
        )
        health = dataclasses.replace(
            state.health,
            diagnostics=(
                Diagnostic(
                    DiagnosticCode("source-stale"),
                    Severity.WARNING,
                    "snapshot for https://token@authors.example is older than the policy allows",
                ),
            ),
        )

        projected = project_maintainer_source(configured, health, _scan())

        self.assertEqual(len(projected.diagnostics), 2)
        self.assertNotIn("token", projected.diagnostics[0])
        self.assertEqual(projected.diagnostics[-1], UNBOUND_SCAN_DIAGNOSTIC)

    def test_a_scan_carrying_another_source_alias_is_still_a_programming_error(self) -> None:
        """Stale history is a state the Maintainer can repair; misfiled history is a defect."""

        configured = configured_source("mirrors", SourceKind.SOURCE_GIT)
        health = source_state(
            configured,
            "mirror-source",
            display_order=0,
            resolved_revision="a" * 40,
        ).health

        with self.assertRaises(ValueError):
            project_maintainer_source(configured, health, _scan())


class MaintainerRenderingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = _source()
        self.dashboard = project_maintainer_dashboard(
            (self.source,),
            recent_activity=("Synced authors",),
        )

    def test_fast_dashboard_and_source_list_are_outcome_oriented(self) -> None:
        dashboard = "\n".join(render_maintainer_dashboard(self.dashboard, PresentationProfile.FAST))
        sources = "\n".join(
            render_maintainer_sources(
                (self.source,),
                cursor="authors",
                profile=PresentationProfile.FAST,
            )
        )

        self.assertIn("Sources: 1", dashboard)
        self.assertIn("Candidates: 1", dashboard)
        self.assertIn("Ready for promotion: 1", dashboard)
        self.assertIn("> authors", sources)
        self.assertIn("Synced", sources)
        self.assertIn("1 manifest", sources)

    def test_verbose_source_detail_discloses_the_full_pinned_revision(self) -> None:
        fast = "\n".join(render_maintainer_source(self.source, PresentationProfile.FAST))
        verbose = "\n".join(render_maintainer_source(self.source, PresentationProfile.VERBOSE))

        self.assertIn("https://authors.example/agents/authors.git", fast)
        self.assertIn("branch: main", fast)
        self.assertNotIn("a" * 40, fast)
        self.assertIn("a" * 40, verbose)

    def test_screen_30_and_sources_are_reachable_bodies_in_the_shared_source(self) -> None:
        screens = ConsumerScreens(
            project_dashboard((), registry_count=0),
            maintainer=MaintainerViews(self.dashboard, (self.source,)),
        )
        source = CanonicalScreenSource(screens)
        settings = ConsumerSettings().with_maintainer_mode(True)
        dashboard = _reload(
            source,
            ConsumerUiState(ConsumerSession(MaintainerScreen.DASHBOARD), settings=settings),
            entering=True,
        )

        self.assertIn("Sources: 1", "\n".join(frame(source, dashboard)))
        self.assertNotIn("not available yet", "\n".join(frame(source, dashboard)))

        sources = _reload(
            source,
            dataclasses.replace(
                dashboard,
                session=dashboard.session.navigate(MaintainerScreen.SOURCES),
            ),
            entering=True,
        )
        self.assertEqual(sources.rows, ("authors",))
        self.assertIn("> authors", "\n".join(frame(source, sources)))
        details = _reload(
            source,
            dataclasses.replace(
                sources,
                session=sources.session.navigate(MaintainerScreen.SOURCE_DETAILS),
                focus="authors",
            ),
            entering=True,
        )
        self.assertIn("branch: main", "\n".join(frame(source, details)))


if __name__ == "__main__":
    unittest.main()
