"""CP-14 screens 38-40 project a validation run and the policy that judged it.

The subject of screen 39 is not a check and not a Candidate but both at once, so the row identity
these screens navigate by is the pair. Keeping it a parsed typed value rather than a renderer's
string split is what lets screens 39 and 40 be opened directly and still know what they are about.
"""

from __future__ import annotations

import builtins
import dataclasses
import json
import unittest

from agent_artifacts.application.candidate_validation import (
    ValidationCheck,
    validate_candidate,
)
from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    KeyBinding,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    project_dashboard,
)
from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    MaintainerValidationRowId,
    MaintainerViews,
    parse_validation_row,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_maintainer_policy_review,
    project_maintainer_source,
    project_maintainer_validation,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from agent_artifacts.tui_maintainer import (
    render_maintainer_policy_review,
    render_maintainer_validation,
    render_maintainer_validation_check,
)
from tests.marketplace_fixtures import configured_source, source_state

_UNGUIDED_SECRET = {
    "id": "github-token",
    "kind": "secret",
    "inject": {"type": "environment", "variable": "GITHUB_TOKEN"},
}


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _scan(*, inputs: list[dict[str, object]] | None = None):
    manifest: dict[str, object] = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "github-mcp", "kind": "mcp", "version": "1.0.0"},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    if inputs is not None:
        manifest["inputs"] = inputs
    compiled = compile_author_snapshot(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry("github/aart.json", json.dumps(manifest, sort_keys=True)),
                _entry("github/server.py", "print('x')\n"),
            ),
        ),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value


def _bundle(**kwargs: object) -> CandidateBundle:
    return _scan(**kwargs).active[0]  # type: ignore[arg-type]


def _views(policy: EffectivePolicy, *, inputs: list[dict[str, object]] | None = None):
    scan = _scan(inputs=inputs)
    configured = configured_source("authors", SourceKind.SOURCE_GIT)
    health = source_state(
        configured, "author-source", display_order=0, resolved_revision=scan.revision
    ).health
    sources = (project_maintainer_source(configured, health, scan),)
    return MaintainerViews(
        project_maintainer_dashboard(sources),
        sources,
        project_maintainer_candidates((scan,)),
        tuple(project_maintainer_validation(bundle, policy=policy) for bundle in scan.active),
    )


def _shell(views: MaintainerViews) -> CanonicalScreenSource:
    return CanonicalScreenSource(
        ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
    )


def _on(screen: MaintainerScreen, *, focus: str = "") -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        focus=focus,
    )


class ValidationRowIdentityTest(unittest.TestCase):
    def test_a_validation_row_is_the_candidate_and_the_check_together(self) -> None:
        row = MaintainerValidationRowId("a" * 64, ValidationCheck.SECRET_METADATA)

        self.assertEqual(str(row), f"{'a' * 64}:secret-metadata")
        self.assertEqual(parse_validation_row(str(row)), row)

    def test_anything_that_is_not_a_validation_row_parses_to_nothing(self) -> None:
        for value in ("", "a" * 64, f"{'a' * 64}:no-such-check", "not-an-id:policy", "::"):
            with self.subTest(value=value):
                self.assertIsNone(parse_validation_row(value))


class ValidationProjectionTest(unittest.TestCase):
    def test_screen_38_lists_every_named_check_with_its_own_outcome(self) -> None:
        view = project_maintainer_validation(_bundle(), policy=EffectivePolicy())

        self.assertEqual(
            [item.check for item in view.checks],
            [item.value for item in ValidationCheck],
        )
        self.assertEqual(view.check("manifest-schema").label, "Manifest schema")
        self.assertEqual(view.check("special-files").label, "No symlinks / special files")
        self.assertEqual(view.check("live-acceptance").outcome, "not-run")
        self.assertEqual(view.artifact, "mcp/github-mcp")
        self.assertEqual(view.version, "1.0.0")

    def test_warnings_and_errors_keep_separate_counts(self) -> None:
        warned = project_maintainer_validation(
            _bundle(inputs=[_UNGUIDED_SECRET]), policy=EffectivePolicy()
        )
        failed = project_maintainer_validation(
            _bundle(), policy=EffectivePolicy(allowed_runtimes=frozenset({"node"}))
        )

        self.assertEqual((warned.error_count, warned.warning_count), (0, 2))
        self.assertIs(warned.state, CandidateState.WARNING)
        self.assertEqual(failed.error_count, 1)
        self.assertIs(failed.state, CandidateState.INVALID)

    def test_a_failing_check_carries_its_actionable_paths_and_values(self) -> None:
        view = project_maintainer_validation(
            _bundle(), policy=EffectivePolicy(allowed_runtimes=frozenset({"node"}))
        )

        detail = view.check("policy").details[0]
        self.assertEqual(detail.declared, "python")
        self.assertEqual(detail.expected, "node")
        self.assertTrue(detail.message)

    def test_a_required_check_is_marked_required_on_the_row_it_applies_to(self) -> None:
        view = project_maintainer_validation(
            _bundle(),
            policy=EffectivePolicy(required_checks=frozenset({"live-acceptance"})),
        )

        self.assertTrue(view.check("live-acceptance").required)
        self.assertFalse(view.check("policy").required)
        self.assertEqual(view.unmet_requirements, ("live-acceptance",))
        self.assertIs(view.state, CandidateState.APPROVAL_REQUIRED)


class PolicyReviewProjectionTest(unittest.TestCase):
    def test_screen_40_says_which_policy_decided_what(self) -> None:
        policy = EffectivePolicy(
            allowed_runtimes=frozenset({"python", "node"}),
            allowed_transports=frozenset({"stdio"}),
            required_checks=frozenset({"live-acceptance"}),
        )

        review = project_maintainer_policy_review(
            validate_candidate(_bundle(), policy=policy), _bundle(), policy=policy
        )

        self.assertIs(review.decision, CandidateState.APPROVAL_REQUIRED)
        self.assertEqual(review.required_checks, ("live-acceptance",))
        self.assertEqual(review.unmet_requirements, ("live-acceptance",))
        self.assertEqual(review.allowed_runtimes, ("node", "python"))
        self.assertIsNone(review.allowed_network_hosts)
        self.assertTrue(review.risk_ceiling)

    def test_an_undemanding_policy_blocks_nothing_and_says_so(self) -> None:
        review = project_maintainer_policy_review(
            validate_candidate(_bundle(), policy=EffectivePolicy()),
            _bundle(),
            policy=EffectivePolicy(),
        )

        self.assertIs(review.decision, CandidateState.READY)
        self.assertEqual(review.required_checks, ())
        self.assertEqual(review.blocking_findings, ())


class ValidationRenderingTest(unittest.TestCase):
    def test_the_check_list_shows_outcome_per_check_and_marks_what_policy_requires(self) -> None:
        view = project_maintainer_validation(
            _bundle(inputs=[_UNGUIDED_SECRET]),
            policy=EffectivePolicy(required_checks=frozenset({"live-acceptance"})),
        )

        drawn = "\n".join(render_maintainer_validation(view, PresentationProfile.FAST))

        self.assertIn("Manifest schema", drawn)
        self.assertIn("Secret metadata", drawn)
        self.assertIn("Live acceptance", drawn)
        self.assertIn("required", drawn)

    def test_a_check_detail_shows_the_declared_and_expected_values(self) -> None:
        view = project_maintainer_validation(
            _bundle(), policy=EffectivePolicy(allowed_runtimes=frozenset({"node"}))
        )

        drawn = "\n".join(
            render_maintainer_validation_check(view.check("policy"), PresentationProfile.FAST)
        )

        self.assertIn("declared: python", drawn)
        self.assertIn("expected: node", drawn)

    def test_policy_review_separates_what_is_allowed_from_what_is_required(self) -> None:
        policy = EffectivePolicy(
            allowed_transports=frozenset({"stdio"}),
            required_checks=frozenset({"live-acceptance"}),
        )
        review = project_maintainer_policy_review(
            validate_candidate(_bundle(), policy=policy), _bundle(), policy=policy
        )

        drawn = "\n".join(render_maintainer_policy_review(review, PresentationProfile.FAST))

        self.assertIn("Approval required", drawn)
        self.assertIn("stdio", drawn)
        self.assertIn("live-acceptance", drawn)


class ValidationShellTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = EffectivePolicy(required_checks=frozenset({"live-acceptance"}))
        self.views = _views(self.policy)
        self.source = _shell(self.views)
        assert self.views.candidates is not None
        self.candidate = self.views.candidates[0].id

    def test_screen_38_rows_are_candidate_and_check_pairs(self) -> None:
        state = _reload(
            self.source, _on(MaintainerScreen.VALIDATION, focus=self.candidate), entering=True
        )

        self.assertEqual(len(state.rows), len(ValidationCheck))
        parsed = parse_validation_row(state.rows[0])
        assert parsed is not None
        self.assertEqual(parsed.candidate_id, self.candidate)
        self.assertIs(parsed.check, ValidationCheck.MANIFEST_SCHEMA)

    def test_enter_on_a_check_opens_its_detail_and_keeps_the_candidate(self) -> None:
        listed = _reload(
            self.source, _on(MaintainerScreen.VALIDATION, focus=self.candidate), entering=True
        )
        row = next(item for item in listed.rows if item.endswith(":secret-metadata"))
        cursored = dataclasses.replace(listed, cursor=listed.rows.index(row))

        self.assertIs(self.source.detail(cursored), MaintainerScreen.VALIDATION_DETAILS)

        drawn = "\n".join(
            frame(
                self.source,
                _reload(
                    self.source,
                    _on(MaintainerScreen.VALIDATION_DETAILS, focus=row),
                    entering=True,
                ),
            )
        )
        self.assertIn("Secret metadata", drawn)

    def test_enter_on_validation_details_continues_to_policy(self) -> None:
        listed = _reload(
            self.source, _on(MaintainerScreen.VALIDATION, focus=self.candidate), entering=True
        )
        details, _ = reduce_consumer_ui(
            listed,
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.VALIDATION_DETAILS,
            ),
        )
        details = _reload(self.source, details, entering=True)

        self.assertIs(self.source.detail(details), MaintainerScreen.POLICY_REVIEW)
        self.assertIn(KeyBinding("Enter", "Policy"), key_bindings(details))
        self.assertEqual(
            key_event("enter", details, detail=self.source.detail(details)),
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.POLICY_REVIEW,
            ),
        )
        policy, _ = reduce_consumer_ui(
            details,
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.POLICY_REVIEW,
            ),
        )
        details_again, _ = reduce_consumer_ui(policy, ConsumerUiEvent(ConsumerUiEventKind.BACK))
        self.assertIs(details_again.session.screen, MaintainerScreen.VALIDATION_DETAILS)
        self.assertEqual(details_again.focus, details.focus)

    def test_enter_on_the_diff_continues_to_validation_in_either_profile(self) -> None:
        """CP-23 task 03: moving the file diffs behind `v` leaves the review's Enter path alone."""

        for profile in PresentationProfile:
            with self.subTest(profile=profile):
                diff = dataclasses.replace(
                    _on(MaintainerScreen.CANDIDATE_DIFF, focus=self.candidate),
                    session=ConsumerSession(
                        MaintainerScreen.CANDIDATE_DIFF,
                        history=(MaintainerScreen.CANDIDATES, MaintainerScreen.CANDIDATE_DETAILS),
                        profile=profile,
                    ),
                )
                event = key_event("enter", diff, detail=self.source.detail(diff))
                self.assertEqual(
                    event,
                    ConsumerUiEvent(
                        ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.VALIDATION
                    ),
                )
                assert event is not None
                validation, _ = reduce_consumer_ui(diff, event)
                self.assertIs(validation.session.screen, MaintainerScreen.VALIDATION)
                self.assertEqual(validation.focus, self.candidate)

    def test_back_from_validation_details_keeps_the_candidate_on_the_diff(self) -> None:
        diff = dataclasses.replace(
            _on(MaintainerScreen.CANDIDATE_DIFF, focus=self.candidate),
            session=ConsumerSession(
                MaintainerScreen.CANDIDATE_DIFF,
                history=(
                    MaintainerScreen.CANDIDATES,
                    MaintainerScreen.CANDIDATE_DETAILS,
                ),
            ),
        )
        validation, _ = reduce_consumer_ui(
            diff,
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.VALIDATION,
            ),
        )
        validation = _reload(self.source, validation, entering=True)
        details, _ = reduce_consumer_ui(
            validation,
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.VALIDATION_DETAILS,
            ),
        )
        details = _reload(self.source, details, entering=True)

        validation_again, _ = reduce_consumer_ui(details, ConsumerUiEvent(ConsumerUiEventKind.BACK))
        validation_again = _reload(self.source, validation_again, entering=True)
        diff_again, _ = reduce_consumer_ui(
            validation_again, ConsumerUiEvent(ConsumerUiEventKind.BACK)
        )
        diff_again = _reload(self.source, diff_again, entering=True)

        self.assertIs(diff_again.session.screen, MaintainerScreen.CANDIDATE_DIFF)
        self.assertEqual(diff_again.focus, self.candidate)
        self.assertNotIn("That Candidate is not available.", frame(self.source, diff_again))
        self.assertIn("- Semantic changes:", frame(self.source, diff_again))

    def test_back_from_any_validation_check_restores_the_bare_candidate_identity(self) -> None:
        # ValidationCheck is a finite closed enum, so exhaust every member instead of sampling it.
        for check in ValidationCheck:
            with self.subTest(check=check):
                row = str(MaintainerValidationRowId(self.candidate, check))
                validation = dataclasses.replace(
                    _on(MaintainerScreen.VALIDATION, focus=row),
                    session=ConsumerSession(
                        MaintainerScreen.VALIDATION,
                        history=(MaintainerScreen.CANDIDATE_DIFF,),
                    ),
                )

                diff, commands = reduce_consumer_ui(
                    validation, ConsumerUiEvent(ConsumerUiEventKind.BACK)
                )

                self.assertIs(diff.session.screen, MaintainerScreen.CANDIDATE_DIFF)
                self.assertEqual(diff.focus, self.candidate)
                self.assertEqual(len(commands), 1)

    def test_back_to_the_maintainer_dashboard_drops_the_candidate_focus(self) -> None:
        candidates = dataclasses.replace(
            _on(MaintainerScreen.CANDIDATES, focus=self.candidate),
            session=ConsumerSession(
                MaintainerScreen.CANDIDATES,
                history=(MaintainerScreen.DASHBOARD,),
            ),
        )

        dashboard, _ = reduce_consumer_ui(candidates, ConsumerUiEvent(ConsumerUiEventKind.BACK))

        self.assertIs(dashboard.session.screen, MaintainerScreen.DASHBOARD)
        self.assertEqual(dashboard.focus, "")

    def test_p_opens_the_policy_review_from_validation(self) -> None:
        validation = _on(MaintainerScreen.VALIDATION, focus=self.candidate)

        self.assertIn(KeyBinding("p", "Policy"), key_bindings(validation))
        self.assertEqual(
            key_event("p", validation),
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=MaintainerScreen.POLICY_REVIEW),
        )
        self.assertIsNone(key_event("p", _on(MaintainerScreen.SOURCES)))

    def test_the_policy_review_opens_from_a_candidate_or_from_a_check_row(self) -> None:
        by_candidate = "\n".join(
            frame(
                self.source,
                _reload(
                    self.source,
                    _on(MaintainerScreen.POLICY_REVIEW, focus=self.candidate),
                    entering=True,
                ),
            )
        )
        by_row = "\n".join(
            frame(
                self.source,
                _reload(
                    self.source,
                    _on(
                        MaintainerScreen.POLICY_REVIEW,
                        focus=f"{self.candidate}:live-acceptance",
                    ),
                    entering=True,
                ),
            )
        )

        self.assertIn("Approval required", by_candidate)
        self.assertEqual(by_candidate, by_row)

    def test_drawing_the_three_screens_opens_no_file(self) -> None:
        """A validation run is composed once, before the shell starts.

        If drawing could reach the filesystem, screen 38 could report a different verdict from the
        one screen 40 justifies, on the same Candidate, in the same session.
        """

        opened: list[object] = []
        real_open = builtins.open

        def _watched(*args: object, **kwargs: object):
            opened.append(args[0] if args else None)
            return real_open(*args, **kwargs)  # type: ignore[arg-type]

        row = f"{self.candidate}:secret-metadata"
        builtins.open = _watched  # type: ignore[assignment]
        try:
            for screen, focus in (
                (MaintainerScreen.VALIDATION, self.candidate),
                (MaintainerScreen.VALIDATION_DETAILS, row),
                (MaintainerScreen.POLICY_REVIEW, self.candidate),
            ):
                frame(
                    self.source,
                    _reload(self.source, _on(screen, focus=focus), entering=True),
                )
        finally:
            builtins.open = real_open  # type: ignore[assignment]

        self.assertEqual(opened, [])

    def test_a_candidate_with_no_composed_validation_refuses_instead_of_raising(self) -> None:
        without = _shell(
            MaintainerViews(self.views.dashboard, self.views.sources, self.views.candidates, None)
        )

        drawn = "\n".join(
            frame(
                without,
                _reload(
                    without,
                    _on(MaintainerScreen.VALIDATION, focus=self.candidate),
                    entering=True,
                ),
            )
        )

        self.assertIn("not available", drawn)


if __name__ == "__main__":
    unittest.main()
