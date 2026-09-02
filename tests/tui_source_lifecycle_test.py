"""SL-1/SL-6: synchronizing and removing a source from both human front-ends.

The dead end this covers is concrete: a subscribed origin whose managed snapshot no longer
matches what the origin declares refuses every read path, and before these operations existed the
only way out was hand-editing configuration and deleting cache directories.  The interface now
owns both halves — refresh the snapshot, or end the subscription — and both front-ends dispatch
exactly the requests the CLI does.
"""

from __future__ import annotations

import curses
import unittest

from agent_artifacts import tui
from agent_artifacts.application.sources import SourceAdoptionOutcome
from agent_artifacts.configuration.model import (
    ConfiguredSource,
    OrganizationPolicy,
    SourceKind,
    UserConfiguration,
    default_user_configuration,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias, SourceId
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.sources.model import (
    CurrentSource,
    HealthStatus,
    SourceHealth,
    SourceIdentityTransition,
    SourceSyncOutcome,
    SyncDisposition,
    make_source_candidate,
    source_instance_id,
)
from agent_artifacts.tui_layout import CONTENT_MEASURE
from agent_artifacts.tui_sources import (
    build_source_stage,
    plan_source_removal,
    render_source_removal_review,
    render_source_stage,
    render_source_sync_outcome,
    render_source_sync_review,
)
from tests.tui_wizard_curses_test import Screen


def _unwrap(result):
    assert isinstance(result, Ok), result
    return result.value


def _registry(alias: str = "registry") -> ConfiguredSource:
    return ConfiguredSource(
        SourceAlias(alias),
        SourceKind.REGISTRY_GIT,
        f"https://git.example.test/team/{alias}.git",
        "main",
        True,
    )


def _configuration(*sources: ConfiguredSource, default: str | None = None) -> UserConfiguration:
    baseline = default_user_configuration()
    return UserConfiguration(
        baseline.schema_version,
        sources,
        None if default is None else SourceAlias(default),
        baseline.sync,
        baseline.reporting,
    )


def _view(configuration: UserConfiguration, policy: OrganizationPolicy | None = None):
    return _unwrap(
        build_source_stage(
            configuration,
            policy or OrganizationPolicy(1),
            {},
            first_run=False,
        )
    )


def _outcome(
    source: ConfiguredSource,
    disposition: SyncDisposition = SyncDisposition.PUBLISHED,
) -> SourceSyncOutcome:
    snapshot = SourceSnapshot(
        SnapshotOrigin.IMMUTABLE_GIT,
        (
            SnapshotEntry(
                _unwrap(parse_relative_path("file.txt")),
                SnapshotEntryKind.FILE,
                b"content",
            ),
        ),
    )
    candidate = _unwrap(
        make_source_candidate(
            source_instance_id(source),
            source.alias,
            "a" * 40,
            snapshot,
        )
    )
    return SourceSyncOutcome(
        disposition,
        CurrentSource(candidate, SourceId("team-registry"), 100, "/managed/snapshot"),
    )


_TRANSITION = SourceIdentityTransition(
    SourceId("team-registry"),
    SourceId("renamed-registry"),
    "a" * 40,
    "b" * 40,
    ObjectDigest("sha256", "c" * 64),
    ObjectDigest("sha256", "d" * 64),
)


def _adoption(
    source: ConfiguredSource,
    *,
    finalized: bool = False,
) -> SourceAdoptionOutcome:
    """What the runtime reports for a review (nothing published) or a finalize."""

    return SourceAdoptionOutcome(_TRANSITION, finalized, _outcome(source).current)


def _scripted(answers):
    values = iter(answers)

    def read(_prompt=""):
        try:
            return next(values)
        except StopIteration:
            raise EOFError from None

    return read


class SourceLifecyclePlanningTests(unittest.TestCase):
    """The planner and its review text are pure, and the CLI and TUI share both."""

    def test_removal_clears_a_default_registry_it_owned_and_keeps_the_others(self) -> None:
        keep = _registry("keep")
        drop = _registry("drop")
        view = _view(_configuration(keep, drop, default="drop"))

        planned = _unwrap(plan_source_removal(view, SourceAlias("drop")))

        self.assertTrue(planned.cleared_default)
        self.assertEqual(planned.after.sources, (keep,))
        self.assertIsNone(planned.after.default_registry)

    def test_removal_keeps_a_default_registry_owned_by_another_source(self) -> None:
        keep = _registry("keep")
        drop = _registry("drop")
        view = _view(_configuration(keep, drop, default="keep"))

        planned = _unwrap(plan_source_removal(view, SourceAlias("drop")))

        self.assertFalse(planned.cleared_default)
        self.assertEqual(planned.after.default_registry, SourceAlias("keep"))

    def test_an_organization_required_alias_cannot_be_unsubscribed(self) -> None:
        required = _registry("company")
        policy = OrganizationPolicy(1, required_sources=(SourceAlias("company"),))
        view = _view(_configuration(required, default="company"), policy)

        refused = plan_source_removal(view, SourceAlias("company"))

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertIn("policy owner", refused.diagnostics[0].remediation[0])

    def test_an_unconfigured_alias_is_refused_by_naming_the_listing_command(self) -> None:
        view = _view(_configuration(_registry()))

        refused = plan_source_removal(view, SourceAlias("absent"))

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertIn("aart source list", refused.diagnostics[0].remediation[0])

    def test_the_removal_review_promises_installed_artifacts_are_kept(self) -> None:
        view = _view(_configuration(_registry(), default="registry"))
        planned = _unwrap(plan_source_removal(view, SourceAlias("registry")))

        review = "\n".join(render_source_removal_review(planned))

        self.assertIn("delete its managed snapshot", review)
        self.assertIn("keeps: every installed artifact", review)
        self.assertIn("clear the default registry", review)

    def test_the_sync_review_separates_availability_from_installed_files(self) -> None:
        view = _view(_configuration(_registry()))

        review = "\n".join(render_source_sync_review(view.rows[0]))

        self.assertIn("registry", review)
        self.assertIn("become installable", review)
        self.assertIn("keeps: every installed artifact", review)

    def test_the_three_sync_results_are_distinguishable_in_words(self) -> None:
        source = _registry()
        published = render_source_sync_outcome(source.alias, _outcome(source))
        unchanged = render_source_sync_outcome(
            source.alias, _outcome(source, SyncDisposition.UNCHANGED)
        )
        retained = render_source_sync_outcome(
            source.alias, _outcome(source, SyncDisposition.RETAINED)
        )

        self.assertIn("snapshot updated", published[0])
        self.assertIn("already current", unchanged[0])
        self.assertIn("keeping the last good snapshot", retained[0])

    def test_origin_mismatch_and_a_failed_comparison_have_distinct_source_rows(self) -> None:
        source = _registry()
        current = _outcome(source).current
        unavailable = Diagnostic(
            DiagnosticCode("source-unavailable"),
            Severity.ERROR,
            "origin could not be reached",
        )
        mismatched = _unwrap(
            build_source_stage(
                _configuration(source),
                OrganizationPolicy(1),
                {
                    source.alias: SourceHealth(
                        HealthStatus.NOT_SYNCHRONIZED,
                        10,
                        current,
                    )
                },
            )
        )
        unchecked = _unwrap(
            build_source_stage(
                _configuration(source),
                OrganizationPolicy(1),
                {
                    source.alias: SourceHealth(
                        HealthStatus.CHECK_UNAVAILABLE,
                        10,
                        current,
                        (unavailable,),
                    )
                },
            )
        )

        self.assertIn("health: not-synchronized", "\n".join(render_source_stage(mismatched)))
        self.assertIn("health: could-not-check", "\n".join(render_source_stage(unchecked)))


class _Runtime:
    """The imperative source boundary, recorded so both front-ends can be held to it."""

    def __init__(self, view, *, sync=None, removal=None, review=None, adoption=None):
        self.view = view
        self.sync_result = sync
        self.removal_result = removal if removal is not None else Ok(object())
        self.review_result = review
        self.adoption_result = adoption if adoption is not None else review
        self.synced: list[SourceAlias] = []
        self.removed: list[str] = []
        self.resubscribed: list[tuple] = []
        self.reloads = 0

    def run_sync(self, alias):
        self.synced.append(alias)
        return self.sync_result

    def run_resubscribe(self, alias, expected):
        self.resubscribed.append((alias, expected))
        return self.review_result if expected is None else self.adoption_result

    def finalize_removal(self, request):
        self.removed.append(request.source.alias.value)
        if isinstance(self.removal_result, Ok):
            self.view = _view(request.after)
        return self.removal_result

    def load(self):
        self.reloads += 1
        return Ok(
            tui._RuntimeSourceStage(
                self.view,
                lambda _request: Ok(object()),
                lambda _request: Ok(object()),
                self.finalize_removal,
                self.run_sync,
                self.run_resubscribe,
            )
        )


class SourceRefusalWayOutTests(unittest.TestCase):
    """A refused source operation must state its way out on the screen that refused it.

    This is the failure the whole stage exists to end: an origin that re-declared its identity
    refuses every sync, and a notice that shows only the refusal leaves the user exactly where
    they were before these operations existed.
    """

    IDENTITY_CHANGE = Err(
        (
            tui.Diagnostic(
                tui.DiagnosticCode("source-invalid"),
                tui.Severity.ERROR,
                "resolved source changed its declared source identity",
                remediation=(
                    "review the origin, then run `aart source remove --alias registry` and add "
                    "it again to subscribe to the new identity",
                ),
            ),
        )
    )

    def test_the_curses_notice_keeps_remediation_and_wraps_instead_of_truncating(self) -> None:
        lines = tui._source_flow_diagnostics(self.IDENTITY_CHANGE)

        joined = " ".join(line.strip() for line in lines)
        self.assertIn("changed its declared source identity", joined)
        self.assertIn("aart source remove --alias registry", joined)
        self.assertNotIn("…", joined)
        for line in lines:
            self.assertLessEqual(len(line), CONTENT_MEASURE)


class SourceLifecycleCursesTests(unittest.TestCase):
    """The curses front-end binds the same three operations to s, i, and r on the Sources list."""

    def test_the_sources_list_advertises_and_returns_every_maintenance_action(self) -> None:
        for key, kind in ((ord("s"), "sync"), (ord("i"), "resubscribe"), (ord("r"), "remove")):
            with self.subTest(kind=kind):
                screen = Screen((key,), height=16, width=110)

                event = tui._curses_multiselect(
                    curses,
                    screen,
                    "Sources",
                    ("registry — health: current",),
                    wizard=True,
                    allow_add=True,
                    allow_source_maintenance=True,
                )

                assert not isinstance(event, tuple)
                self.assertEqual(event.kind, kind)
                self.assertEqual(event.selected, (0,))
                bar = [value for row, _column, value in screen.lines if row == screen.height - 1][0]
                self.assertIn("s=sync", bar)
                self.assertIn("i=resubscribe", bar)
                self.assertIn("r=remove", bar)

    def test_a_list_without_source_maintenance_never_binds_those_keys(self) -> None:
        screen = Screen((ord("s"), ord("r"), 10), height=16, width=110)

        picked = tui._curses_multiselect(curses, screen, "Artifacts", ("one",), wizard=True)

        self.assertEqual(picked.kind, "confirm")
        bar = [value for row, _column, value in screen.lines if row == screen.height - 1][0]
        self.assertNotIn("s=sync", bar)

    def test_the_curses_sources_stage_reports_the_cursor_row_for_maintenance(self) -> None:
        view = _view(_configuration(_registry("first"), _registry("second")))
        screen = Screen((curses.KEY_DOWN, ord("r")), height=20, width=110)

        event, selection, error = tui._curses_source_event(
            curses,
            screen,
            tui.WizardSession(current="source"),
            view,
        )

        self.assertEqual(event.kind, "remove")
        self.assertIsNone(selection)
        self.assertIsNone(error)
        row = tui._selected_source_row(view, event.selected)
        assert row is not None
        self.assertEqual(row.source.alias, SourceAlias("second"))

    def test_the_no_source_row_is_not_a_maintenance_target(self) -> None:
        view = _view(_configuration(_registry()))

        self.assertIsNone(tui._selected_source_row(view, (len(view.rows),)))

    def test_the_curses_removal_screen_plans_and_reviews_before_returning(self) -> None:
        view = _view(_configuration(_registry(), default="registry"))
        session = tui.WizardSession(current="source")
        screen = Screen((10,), height=24, width=110)

        request = tui._curses_source_removal(curses, screen, session, view, view.rows[0])

        assert not isinstance(request, tui.WizardInput)
        self.assertEqual(request.source.alias, SourceAlias("registry"))
        self.assertTrue(request.cleared_default)
        rendered = "\n".join(value for _row, _column, value in screen.history)
        self.assertIn("Source removal review:", rendered)
        self.assertIn("enter=remove", rendered)

    def test_the_curses_removal_screen_can_be_declined(self) -> None:
        view = _view(_configuration(_registry()))
        screen = Screen((ord("n"),), height=24, width=110)

        request = tui._curses_source_removal(
            curses,
            screen,
            tui.WizardSession(current="source"),
            view,
            view.rows[0],
        )

        self.assertIsInstance(request, tui.WizardInput)
        assert isinstance(request, tui.WizardInput)
        self.assertEqual(request.kind, "back")

    def test_the_curses_resubscribe_screen_resolves_the_origin_then_reviews(self) -> None:
        source = _registry()
        view = _view(_configuration(source))
        runtime = _Runtime(view, review=Ok(_adoption(source)))
        screen = Screen((10,), height=24, width=110)

        request = tui._curses_source_resubscription(
            curses,
            screen,
            tui.WizardSession(current="source"),
            view,
            view.rows[0],
            runtime.run_resubscribe,
        )

        assert not isinstance(request, tui.WizardInput)
        # Review resolves the origin exactly once, and never with an expected transition: a curses
        # screen cannot finalize something it has not yet drawn.
        self.assertEqual(runtime.resubscribed, [(SourceAlias("registry"), None)])
        self.assertEqual(request.transition, _TRANSITION)
        rendered = "\n".join(value for _row, _column, value in screen.history)
        self.assertIn("Source resubscription review:", rendered)
        self.assertIn("team-registry -> renamed-registry", rendered)
        self.assertIn("enter=resubscribe", rendered)

    def test_the_curses_resubscribe_screen_can_be_declined(self) -> None:
        source = _registry()
        view = _view(_configuration(source))
        runtime = _Runtime(view, review=Ok(_adoption(source)))
        screen = Screen((ord("n"),), height=24, width=110)

        request = tui._curses_source_resubscription(
            curses,
            screen,
            tui.WizardSession(current="source"),
            view,
            view.rows[0],
            runtime.run_resubscribe,
        )

        self.assertIsInstance(request, tui.WizardInput)
        assert isinstance(request, tui.WizardInput)
        self.assertEqual(request.kind, "back")
        self.assertEqual([expected for _alias, expected in runtime.resubscribed], [None])

    def test_the_curses_sync_screen_reviews_before_returning_the_row(self) -> None:
        view = _view(_configuration(_registry()))
        screen = Screen((10,), height=24, width=110)

        reviewed = tui._curses_source_sync(
            curses,
            screen,
            tui.WizardSession(current="source"),
            view.rows[0],
        )

        self.assertIs(reviewed, view.rows[0])
        rendered = "\n".join(value for _row, _column, value in screen.history)
        self.assertIn("Source sync review:", rendered)
        self.assertIn("enter=sync", rendered)


if __name__ == "__main__":
    unittest.main()
