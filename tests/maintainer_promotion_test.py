"""CP-14 step 5: what a Maintainer confirms when promoting one reviewed Candidate.

Promotion is the first Maintainer action that writes approved registry state, so what it records
has to be the review that actually happened.  The evidence a promotion carries is a digest of the
validation run and of the policy that judged it, which is what makes an audit record answer "who
approved this, against which rules" rather than merely "this was promoted".
"""

from __future__ import annotations

import json
import unittest

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
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
from agent_artifacts.application.maintainer_promotion import (
    PreparedCandidatePromotion,
    effective_policy_digest,
    plan_candidate_promotion,
    prepare_candidate_promotion,
    promotion_evidence,
    validation_report_digest,
)
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_maintainer_promotion_review,
    project_maintainer_registry_diff,
    project_maintainer_source,
    project_maintainer_validation,
)
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias, source_revision_kind
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok
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
    render_maintainer_promotion_review,
    render_maintainer_registry_diff,
)
from tests.marketplace_fixtures import configured_source, source_state

_ARGV_SECRET = {
    "id": "github-token",
    "kind": "secret",
    "inject": {"type": "cli-argument", "argument": "--github-token"},
    "help": {
        "label": "GitHub token",
        "format_hint": "provider-issued token",
        "obtain_from": {"label": "GitHub Settings", "url": "https://github.example/settings"},
    },
}
_UNGUIDED_SECRET = {
    "id": "github-token",
    "kind": "secret",
    "inject": {"type": "environment", "variable": "GITHUB_TOKEN"},
}
_LOCAL_REVISION = "local:" + "1" * 64


def _entry(path: str, content: str) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content.encode())


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _scan(*, inputs: list[dict[str, object]] | None = None, revision: str = "a" * 40):
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
            SnapshotOrigin.IMMUTABLE_GIT
            if source_revision_kind(revision) == "git"
            else SnapshotOrigin.LOCAL,
            (
                _entry("github/aart.json", json.dumps(manifest, sort_keys=True)),
                _entry("github/server.py", "print('x')\n"),
            ),
        ),
        source_alias=SourceAlias("authors"),
        source=(
            "https://git.example/authors.git"
            if source_revision_kind(revision) == "git"
            else "/work/authors"
        ),
        revision=revision,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        revision,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value


def _bundle(
    *, inputs: list[dict[str, object]] | None = None, revision: str = "a" * 40
) -> CandidateBundle:
    return _scan(inputs=inputs, revision=revision).active[0]


def _registry() -> SourceSnapshot:
    """A registry workspace with nothing promoted into it yet."""

    return SourceSnapshot(SnapshotOrigin.LOCAL, ())


def _approved(alias: str = "company") -> ApprovedRegistryState:
    return ApprovedRegistryState(SourceAlias(alias), "f" * 40, _digest("e"), ())


def _prepared(
    *,
    inputs: list[dict[str, object]] | None = None,
    policy: EffectivePolicy | None = None,
    mode: PromotionMode = PromotionMode.VENDORED,
    approved: ApprovedRegistryState | None = None,
    revision: str = "a" * 40,
):
    judged = EffectivePolicy() if policy is None else policy
    bundle = _bundle(inputs=inputs, revision=revision)
    return prepare_candidate_promotion(
        bundle,
        validate_candidate(bundle, policy=judged),
        judged,
        _approved() if approved is None else approved,
        mode=mode,
    )


class PromotionEvidenceTest(unittest.TestCase):
    def test_the_same_run_and_policy_always_digest_the_same(self) -> None:
        bundle = _bundle()
        policy = EffectivePolicy(allowed_transports=frozenset({"stdio"}))
        first = validate_candidate(bundle, policy=policy)
        second = validate_candidate(bundle, policy=policy)

        self.assertEqual(validation_report_digest(first), validation_report_digest(second))
        self.assertEqual(effective_policy_digest(policy), effective_policy_digest(policy))

    def test_a_different_policy_is_a_different_digest(self) -> None:
        """An audit that could not tell two policies apart could not prove which one approved."""

        loose = EffectivePolicy()
        strict = EffectivePolicy(required_checks=frozenset({"live-acceptance"}))

        self.assertNotEqual(effective_policy_digest(loose), effective_policy_digest(strict))

    def test_a_different_outcome_is_a_different_report(self) -> None:
        clean = _bundle()
        warned = _bundle(inputs=[_UNGUIDED_SECRET])

        self.assertNotEqual(
            validation_report_digest(validate_candidate(clean, policy=EffectivePolicy())),
            validation_report_digest(validate_candidate(warned, policy=EffectivePolicy())),
        )

    def test_evidence_carries_the_warnings_the_maintainer_was_shown(self) -> None:
        bundle = _bundle(inputs=[_UNGUIDED_SECRET])
        validation = validate_candidate(bundle, policy=EffectivePolicy())

        evidence = promotion_evidence(validation, EffectivePolicy())

        assert isinstance(evidence, Ok), evidence
        self.assertEqual(
            evidence.value.validation_report_digest, validation_report_digest(validation)
        )
        self.assertTrue(evidence.value.warnings)
        # A warning in an audit that does not say which check raised it is not evidence of
        # anything a reader could go back and check.
        self.assertTrue(
            all(
                item.split(":")[0] in {result.check.value for result in validation.results}
                for item in evidence.value.warnings
            )
        )


class PreparePromotionTest(unittest.TestCase):
    def test_a_reviewable_promotion_binds_candidate_policy_and_registry(self) -> None:
        prepared = _prepared()

        assert isinstance(prepared, Ok), prepared
        self.assertIsInstance(prepared.value, PreparedCandidatePromotion)
        self.assertEqual(prepared.value.target_registry, SourceAlias("company"))
        self.assertIs(prepared.value.state, CandidateState.READY)
        self.assertTrue(str(prepared.value.review_digest).startswith("sha256:"))

    def test_a_candidate_an_error_refused_cannot_be_promoted(self) -> None:
        """Screens 38 to 40 already said why; promotion refuses on that evidence, not a new one."""

        prepared = _prepared(policy=EffectivePolicy(allowed_runtimes=frozenset({"node"})))

        assert isinstance(prepared, Err), prepared
        self.assertIn("invalid", " ".join(item.message for item in prepared.diagnostics).lower())

    def test_a_secret_the_process_table_would_expose_blocks_promotion(self) -> None:
        """The pipeline's teeth reach the write path: argv is readable by any other process."""

        prepared = _prepared(inputs=[_ARGV_SECRET])

        assert isinstance(prepared, Err), prepared
        self.assertIn("invalid", " ".join(item.message for item in prepared.diagnostics).lower())

    def test_a_candidate_policy_holds_for_approval_cannot_be_promoted(self) -> None:
        prepared = _prepared(policy=EffectivePolicy(required_checks=frozenset({"live-acceptance"})))

        assert isinstance(prepared, Err), prepared
        self.assertIn("approval", " ".join(item.message for item in prepared.diagnostics).lower())

    def test_a_warning_does_not_block_a_promotion_by_itself(self) -> None:
        """A warning is only blocking when a policy says so, which is what `required_checks` says."""

        prepared = _prepared(inputs=[_UNGUIDED_SECRET])

        assert isinstance(prepared, Ok), prepared
        self.assertIs(prepared.value.state, CandidateState.WARNING)
        self.assertTrue(prepared.value.evidence.warnings)

    def test_a_candidate_bound_for_another_registry_is_refused(self) -> None:
        prepared = _prepared(approved=_approved("other"))

        assert isinstance(prepared, Err), prepared
        self.assertIn("registry", " ".join(item.message for item in prepared.diagnostics).lower())

    def test_the_review_digest_covers_the_mode_and_the_registry_baseline(self) -> None:
        """Confirming a review must not apply a different transaction than the one reviewed."""

        vendored = _prepared(mode=PromotionMode.VENDORED)
        referenced = _prepared(mode=PromotionMode.REFERENCED)
        moved = _prepared(
            approved=ApprovedRegistryState(SourceAlias("company"), "b" * 40, _digest("c"), ())
        )

        assert isinstance(vendored, Ok) and isinstance(referenced, Ok) and isinstance(moved, Ok)
        self.assertNotEqual(vendored.value.review_digest, referenced.value.review_digest)
        self.assertNotEqual(vendored.value.review_digest, moved.value.review_digest)

    def test_a_validation_of_a_different_candidate_is_refused(self) -> None:
        other = _bundle(inputs=[_UNGUIDED_SECRET])

        prepared = prepare_candidate_promotion(
            _bundle(),
            validate_candidate(other, policy=EffectivePolicy()),
            EffectivePolicy(),
            _approved(),
            mode=PromotionMode.VENDORED,
        )

        assert isinstance(prepared, Err), prepared


class PromotionReviewProjectionTest(unittest.TestCase):
    def test_a_promotable_candidate_reviews_with_the_digest_it_would_confirm(self) -> None:
        bundle = _bundle()
        policy = EffectivePolicy()
        prepared = _prepared()
        assert isinstance(prepared, Ok)

        view = project_maintainer_promotion_review(
            bundle,
            validate_candidate(bundle, policy=policy),
            policy,
            _approved(),
            mode=PromotionMode.VENDORED,
        )

        self.assertTrue(view.confirmable)
        self.assertEqual(view.review_digest, str(prepared.value.review_digest))
        self.assertEqual(view.target_registry, "company")
        self.assertEqual(view.refusals, ())

    def test_a_refused_candidate_reviews_as_the_reason_it_was_refused(self) -> None:
        """Screen 41 answers "can this be promoted"; "no, and here is why" is an answer."""

        bundle = _bundle()
        policy = EffectivePolicy(required_checks=frozenset({"live-acceptance"}))

        view = project_maintainer_promotion_review(
            bundle,
            validate_candidate(bundle, policy=policy),
            policy,
            _approved(),
            mode=PromotionMode.VENDORED,
        )

        self.assertFalse(view.confirmable)
        self.assertIsNone(view.review_digest)
        self.assertTrue(any("approval" in item.lower() for item in view.refusals))

    def test_an_unsynchronized_registry_is_a_refusal_not_a_crash(self) -> None:
        bundle = _bundle()

        view = project_maintainer_promotion_review(
            bundle,
            validate_candidate(bundle, policy=EffectivePolicy()),
            EffectivePolicy(),
            None,
            mode=PromotionMode.VENDORED,
        )

        self.assertFalse(view.confirmable)
        self.assertTrue(any("registry" in item.lower() for item in view.refusals))


class PromotionReviewRenderingTest(unittest.TestCase):
    def test_the_review_shows_what_would_be_written_and_against_which_baseline(self) -> None:
        bundle = _bundle()
        view = project_maintainer_promotion_review(
            bundle,
            validate_candidate(bundle, policy=EffectivePolicy()),
            EffectivePolicy(),
            _approved(),
            mode=PromotionMode.VENDORED,
        )

        drawn = "\n".join(render_maintainer_promotion_review(view, PresentationProfile.VERBOSE))

        self.assertIn("company", drawn)
        self.assertIn("vendored", drawn)
        self.assertIn("Review digest:", drawn)

    def test_a_refusal_is_drawn_instead_of_a_confirmable_review(self) -> None:
        bundle = _bundle()
        policy = EffectivePolicy(allowed_runtimes=frozenset({"node"}))
        view = project_maintainer_promotion_review(
            bundle,
            validate_candidate(bundle, policy=policy),
            policy,
            _approved(),
            mode=PromotionMode.VENDORED,
        )

        drawn = "\n".join(render_maintainer_promotion_review(view, PresentationProfile.FAST))

        self.assertIn("cannot be promoted", drawn)
        self.assertNotIn("Review digest:", drawn)


class PromotionShellTest(unittest.TestCase):
    def setUp(self) -> None:
        policy = EffectivePolicy()
        scan = _scan()
        configured = configured_source("authors", SourceKind.SOURCE_GIT)
        health = source_state(
            configured, "author-source", display_order=0, resolved_revision=scan.revision
        ).health
        sources = (project_maintainer_source(configured, health, scan),)
        self.views = MaintainerViews(
            project_maintainer_dashboard(sources),
            sources,
            project_maintainer_candidates((scan,)),
            tuple(project_maintainer_validation(item, policy=policy) for item in scan.active),
            tuple(
                project_maintainer_promotion_review(
                    item,
                    validate_candidate(item, policy=policy),
                    policy,
                    _approved(),
                    mode=PromotionMode.VENDORED,
                )
                for item in scan.active
            ),
        )
        self.source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=self.views)
        )
        assert self.views.candidates is not None
        self.candidate = self.views.candidates[0].id

    def _on(self, screen: MaintainerScreen, focus: str) -> ConsumerUiState:
        return ConsumerUiState(
            ConsumerSession(screen),
            settings=ConsumerSettings().with_maintainer_mode(True),
            focus=focus,
        )

    def test_enter_on_the_policy_review_opens_the_promotion_review(self) -> None:
        state = self._on(MaintainerScreen.POLICY_REVIEW, self.candidate)

        self.assertIs(
            self.source.detail(_reload(self.source, state, entering=True)),
            MaintainerScreen.PROMOTION_REVIEW,
        )

    def test_the_promotion_review_opens_from_a_candidate_or_a_check_row(self) -> None:
        by_candidate = "\n".join(
            frame(
                self.source,
                _reload(
                    self.source,
                    self._on(MaintainerScreen.PROMOTION_REVIEW, self.candidate),
                    entering=True,
                ),
            )
        )
        by_row = "\n".join(
            frame(
                self.source,
                _reload(
                    self.source,
                    self._on(
                        MaintainerScreen.PROMOTION_REVIEW,
                        f"{self.candidate}:policy",
                    ),
                    entering=True,
                ),
            )
        )

        self.assertIn("Review digest:", by_candidate)
        self.assertEqual(by_candidate, by_row)

    def test_a_candidate_with_no_composed_promotion_refuses_instead_of_raising(self) -> None:
        without = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                maintainer=MaintainerViews(
                    self.views.dashboard,
                    self.views.sources,
                    self.views.candidates,
                    self.views.validations,
                    None,
                ),
            )
        )

        drawn = "\n".join(
            frame(
                without,
                _reload(
                    without,
                    self._on(MaintainerScreen.PROMOTION_REVIEW, self.candidate),
                    entering=True,
                ),
            )
        )

        self.assertIn("not available", drawn)


class PromotionPlanTest(unittest.TestCase):
    """The transaction a confirmed promotion would apply, planned once and never while drawing."""

    def test_a_reviewed_promotion_plans_the_registry_transaction_it_described(self) -> None:
        prepared = _prepared()
        assert isinstance(prepared, Ok), prepared

        planned = plan_candidate_promotion(prepared.value, _registry())

        assert isinstance(planned, Ok), planned
        paths = {str(change.path) for change in planned.value.changes}
        self.assertIn("registry/index.json", paths)
        self.assertIn("artifacts/mcp/github-mcp/1.0.0/artifact.json", paths)
        self.assertIs(planned.value.mode, PromotionMode.VENDORED)

    def test_the_plan_carries_the_evidence_the_review_bound(self) -> None:
        """The audit record must name the run that approved it, not a fresh one."""

        prepared = _prepared()
        assert isinstance(prepared, Ok), prepared

        planned = plan_candidate_promotion(prepared.value, _registry())

        assert isinstance(planned, Ok), planned
        audit = planned.value.audits[0]
        self.assertEqual(
            audit.validation_report_digest, prepared.value.evidence.validation_report_digest
        )
        self.assertEqual(
            audit.effective_policy_digest, prepared.value.evidence.effective_policy_digest
        )

    def test_a_local_source_plans_with_typed_snapshot_provenance(self) -> None:
        """A local snapshot is supported without passing it off as a Git commit."""

        prepared = _prepared(revision=_LOCAL_REVISION)
        assert isinstance(prepared, Ok), prepared

        planned = plan_candidate_promotion(prepared.value, _registry())

        assert isinstance(planned, Ok), planned
        provenance = planned.value.audits[0].source_provenance
        self.assertEqual(provenance.kind.value, "local-snapshot")
        self.assertIsNone(provenance.git_revision)
        assert provenance.local_snapshot_digest is not None
        self.assertEqual(provenance.local_snapshot_digest.value, "1" * 64)

    def test_a_different_mode_plans_a_different_transaction(self) -> None:
        vendored = _prepared(mode=PromotionMode.VENDORED)
        referenced = _prepared(mode=PromotionMode.REFERENCED)
        assert isinstance(vendored, Ok) and isinstance(referenced, Ok)

        first = plan_candidate_promotion(vendored.value, _registry())
        second = plan_candidate_promotion(referenced.value, _registry())

        assert isinstance(first, Ok), first
        assert isinstance(second, Ok), second
        self.assertNotEqual(first.value.review_digest, second.value.review_digest)


class RegistryDiffProjectionTest(unittest.TestCase):
    def test_screen_43_lists_what_the_transaction_would_write(self) -> None:
        bundle = _bundle()
        view = project_maintainer_registry_diff(
            bundle,
            validate_candidate(bundle, policy=EffectivePolicy()),
            EffectivePolicy(),
            _approved(),
            _registry(),
            mode=PromotionMode.VENDORED,
        )

        self.assertTrue(view.plannable)
        self.assertTrue(view.changed_paths)
        self.assertEqual(len(view.changes), min(view.changed_paths, 200))
        self.assertTrue(all(item.kind for item in view.changes))
        self.assertEqual(view.refusals, ())

    def test_a_refused_review_has_no_transaction_to_show(self) -> None:
        bundle = _bundle()
        policy = EffectivePolicy(allowed_runtimes=frozenset({"node"}))

        view = project_maintainer_registry_diff(
            bundle,
            validate_candidate(bundle, policy=policy),
            policy,
            _approved(),
            _registry(),
            mode=PromotionMode.VENDORED,
        )

        self.assertFalse(view.plannable)
        self.assertTrue(view.refusals)

    def test_a_local_source_has_a_reviewable_registry_transaction(self) -> None:
        bundle = _bundle(revision=_LOCAL_REVISION)

        view = project_maintainer_registry_diff(
            bundle,
            validate_candidate(bundle, policy=EffectivePolicy()),
            EffectivePolicy(),
            _approved(),
            _registry(),
            mode=PromotionMode.VENDORED,
        )

        self.assertTrue(view.plannable)
        self.assertTrue(view.plan_digest)
        self.assertFalse(view.refusals)

    def test_an_unreadable_registry_workspace_is_a_refusal(self) -> None:
        bundle = _bundle()

        view = project_maintainer_registry_diff(
            bundle,
            validate_candidate(bundle, policy=EffectivePolicy()),
            EffectivePolicy(),
            _approved(),
            None,
            mode=PromotionMode.VENDORED,
        )

        self.assertFalse(view.plannable)
        self.assertTrue(any("workspace" in item.lower() for item in view.refusals))

    def test_the_diff_renders_the_paths_and_the_transaction_digests(self) -> None:
        bundle = _bundle()
        view = project_maintainer_registry_diff(
            bundle,
            validate_candidate(bundle, policy=EffectivePolicy()),
            EffectivePolicy(),
            _approved(),
            _registry(),
            mode=PromotionMode.VENDORED,
        )

        drawn = "\n".join(render_maintainer_registry_diff(view, PresentationProfile.VERBOSE))

        self.assertIn("registry/index.json", drawn)
        self.assertIn("added", drawn)
        self.assertIn("Registry snapshot after:", drawn)


class PromotionModeStateTest(unittest.TestCase):
    """The promotion mode is typed state the shell holds, not something a screen recomputes.

    Both modes are composed once, so choosing one selects an already-projected review rather than
    projecting a new one while drawing.
    """

    def setUp(self) -> None:
        policy = EffectivePolicy()
        scan = _scan()
        configured = configured_source("authors", SourceKind.SOURCE_GIT)
        health = source_state(
            configured, "author-source", display_order=0, resolved_revision=scan.revision
        ).health
        sources = (project_maintainer_source(configured, health, scan),)
        self.views = MaintainerViews(
            project_maintainer_dashboard(sources),
            sources,
            project_maintainer_candidates((scan,)),
            tuple(project_maintainer_validation(item, policy=policy) for item in scan.active),
            tuple(
                project_maintainer_promotion_review(
                    item,
                    validate_candidate(item, policy=policy),
                    policy,
                    _approved(),
                    mode=mode,
                )
                for item in scan.active
                for mode in PromotionMode
            ),
        )
        self.source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=self.views)
        )
        assert self.views.candidates is not None
        self.candidate = self.views.candidates[0].id

    def _on(self, screen: MaintainerScreen, **fields) -> ConsumerUiState:
        return ConsumerUiState(
            ConsumerSession(screen),
            settings=ConsumerSettings().with_maintainer_mode(True),
            focus=self.candidate,
            **fields,
        )

    def test_both_modes_are_composed_so_neither_is_projected_while_drawing(self) -> None:
        for mode in PromotionMode:
            with self.subTest(mode=mode):
                review = self.views.promotion(self.candidate, mode)
                assert review is not None
                self.assertEqual(review.mode, mode.value)

    def test_the_review_a_screen_draws_follows_the_chosen_mode(self) -> None:
        vendored = "\n".join(
            frame(
                self.source,
                _reload(self.source, self._on(MaintainerScreen.PROMOTION_REVIEW), entering=True),
            )
        )
        referenced = "\n".join(
            frame(
                self.source,
                _reload(
                    self.source,
                    self._on(
                        MaintainerScreen.PROMOTION_REVIEW,
                        promotion_mode=PromotionMode.REFERENCED,
                    ),
                    entering=True,
                ),
            )
        )

        self.assertIn("Promotion mode: vendored", vendored)
        self.assertIn("Promotion mode: referenced", referenced)
        self.assertNotEqual(vendored, referenced)

    def test_m_toggles_the_mode_and_only_where_the_mode_is_the_question(self) -> None:
        state = self._on(MaintainerScreen.PROMOTION_MODE)

        self.assertEqual(
            key_event("m", state),
            ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROMOTION_MODE),
        )
        self.assertIsNone(key_event("m", self._on(MaintainerScreen.CANDIDATES)))

    def test_toggling_the_mode_changes_the_digest_that_would_be_confirmed(self) -> None:
        """A mode change must be a different review to confirm, not a relabelled one."""

        state = self._on(MaintainerScreen.PROMOTION_MODE)

        toggled, _ = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROMOTION_MODE)
        )

        self.assertIs(toggled.promotion_mode, PromotionMode.REFERENCED)
        before = self.views.promotion(self.candidate, state.promotion_mode)
        after = self.views.promotion(self.candidate, toggled.promotion_mode)
        assert before is not None and after is not None
        self.assertNotEqual(before.review_digest, after.review_digest)

    def test_enter_on_the_promotion_review_opens_the_mode_screen(self) -> None:
        state = _reload(self.source, self._on(MaintainerScreen.PROMOTION_REVIEW), entering=True)

        self.assertIs(self.source.detail(state), MaintainerScreen.PROMOTION_MODE)


if __name__ == "__main__":
    unittest.main()
