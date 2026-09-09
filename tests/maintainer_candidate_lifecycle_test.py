"""CP-14 screen 48 projects Candidate lifecycle from durable, exact evidence."""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
)
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.application.maintainer_views import (
    CandidateLifecyclePhase,
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_candidate_lifecycle,
    project_maintainer_candidates,
    project_maintainer_dashboard,
)
from agent_artifacts.application.promotion import (
    PromotionEvidence,
    load_registry_promotions,
    load_registry_versions,
    plan_bulk_promotion,
    project_promotion,
)
from agent_artifacts.domain.candidates import assess_candidate, mark_candidate_promoted
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.maintainer_candidate_shell_test import _projected_source
from tests.maintainer_candidate_views_test import _changed_scan, _compiled


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _promoted_registry(bundle: CandidateBundle):
    validation = validate_candidate(bundle, policy=EffectivePolicy())
    ready = CandidateBundle(
        assess_candidate(
            bundle.candidate,
            findings=validation.findings,
            manual_approval_required=validation.manual_approval_required,
        ),
        bundle.artifact,
    )
    empty = SourceSnapshot(SnapshotOrigin.LOCAL, ())
    planned = plan_bulk_promotion(
        empty,
        (ready,),
        evidence=((ready.candidate.id, PromotionEvidence(_digest("1"), _digest("2"))),),
        approved=(),
    )
    assert isinstance(planned, Ok), planned
    projected = project_promotion(empty, planned.value)
    assert isinstance(projected, Ok), projected
    versions = load_registry_versions(projected.value)
    audits = load_registry_promotions(projected.value)
    assert isinstance(versions, Ok), versions
    assert isinstance(audits, Ok), audits
    return versions.value, audits.value


class MaintainerCandidateLifecycleProjectionTest(unittest.TestCase):
    def test_promotion_requires_the_exact_registry_version_and_audit(self) -> None:
        scan = _changed_scan()
        bundle = scan.active[0]
        validation = validate_candidate(bundle, policy=EffectivePolicy())
        versions, audits = _promoted_registry(bundle)

        proven = project_maintainer_candidate_lifecycle(
            bundle,
            validation,
            history=scan.history,
            versions=versions,
            audits=audits,
        )
        missing_audit = project_maintainer_candidate_lifecycle(
            bundle,
            validation,
            history=scan.history,
            versions=versions,
            audits=(),
        )

        promoted = [
            item for item in proven.stages if item.phase is CandidateLifecyclePhase.PROMOTION
        ]
        unproven = [
            item for item in missing_audit.stages if item.phase is CandidateLifecyclePhase.PROMOTION
        ]
        self.assertEqual(promoted[-1].outcome, "promoted")
        self.assertIn(str(audits[0].registry_snapshot_after), promoted[-1].evidence or "")
        self.assertEqual(unproven[-1].outcome, "unverified")
        self.assertNotEqual(bundle.candidate.state.value, "promoted")

    def test_a_stored_promoted_state_without_registry_evidence_is_not_treated_as_promotion(
        self,
    ) -> None:
        scan = _changed_scan()
        bundle = scan.active[0]
        validation = validate_candidate(bundle, policy=EffectivePolicy())
        promoted = CandidateBundle(
            mark_candidate_promoted(
                assess_candidate(bundle.candidate, findings=validation.findings),
                _digest("9"),
            ),
            bundle.artifact,
        )

        view = project_maintainer_candidate_lifecycle(
            promoted,
            validation,
            history=tuple(
                promoted if item.candidate.id == promoted.candidate.id else item
                for item in scan.history
            ),
            versions=(),
            audits=(),
        )

        promotion = [
            item for item in view.stages if item.phase is CandidateLifecyclePhase.PROMOTION
        ]
        self.assertEqual(promotion[-1].outcome, "unverified")
        self.assertIn("registry", promotion[-1].detail.lower())

    def test_a_new_source_revision_returns_to_changed_after_the_prior_candidate_was_promoted(
        self,
    ) -> None:
        prior_scan = _changed_scan()
        prior = prior_scan.active[0]
        versions, audits = _promoted_registry(prior)
        current_scan = reconcile_source_scan(
            SourceAlias("authors"),
            "c" * 40,
            _compiled(
                revision="c",
                version="1.2.0",
                server="print('newer')\n",
                requirement="mcp==1.15.0\n",
            ),
            previous=prior_scan.history,
            approved=versions,
            target_registry=SourceAlias("company"),
        )
        assert isinstance(current_scan, Ok), current_scan
        current = current_scan.value.active[0]

        view = project_maintainer_candidate_lifecycle(
            current,
            validate_candidate(current, policy=EffectivePolicy()),
            history=current_scan.value.history,
            versions=versions,
            audits=audits,
        )

        phases = [(item.phase, item.outcome) for item in view.stages]
        self.assertIn((CandidateLifecyclePhase.PROMOTION, "promoted"), phases)
        self.assertIn((CandidateLifecyclePhase.SOURCE_CHANGE, "changed"), phases)
        self.assertEqual(
            phases[-2:],
            [
                (CandidateLifecyclePhase.VALIDATION, "ready"),
                (CandidateLifecyclePhase.PROMOTION, "not-promoted"),
            ],
        )
        self.assertEqual(view.current_candidate_id, current.candidate.id.value)


class MaintainerCandidateLifecycleShellTest(unittest.TestCase):
    def test_r_opens_screen_48_and_it_draws_without_machine_reads(self) -> None:
        scan = _changed_scan()
        bundle = scan.active[0]
        lifecycle = project_maintainer_candidate_lifecycle(
            bundle,
            validate_candidate(bundle, policy=EffectivePolicy()),
            history=scan.history,
            versions=(),
            audits=(),
        )
        projected_source = _projected_source("authors", scan)
        candidates = project_maintainer_candidates((scan,))
        views = MaintainerViews(
            project_maintainer_dashboard((projected_source,)),
            (projected_source,),
            candidates,
            lifecycles=(lifecycle,),
        )
        candidate = candidates[0]
        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                maintainer=dataclasses.replace(views, lifecycles=(lifecycle,)),
            )
        )
        detail = ConsumerUiState(
            ConsumerSession(MaintainerScreen.CANDIDATE_DETAILS),
            settings=ConsumerSettings().with_maintainer_mode(True),
            focus=candidate.id,
        )

        event = key_event("r", detail, detail=source.detail(detail))
        self.assertEqual(
            event,
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.CANDIDATE_LIFECYCLE,
            ),
        )
        state = _reload(
            source,
            dataclasses.replace(
                detail,
                session=detail.session.navigate(MaintainerScreen.CANDIDATE_LIFECYCLE),
            ),
            entering=True,
        )
        opened: list[str] = []
        real_open = open

        def _record(file, *args, **kwargs):  # type: ignore[no-untyped-def]
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        import builtins

        builtins.open = _record  # noqa: A001 - narrow, restored immediately below
        try:
            drawn = "\n".join(frame(source, state))
        finally:
            builtins.open = real_open

        self.assertEqual(opened, [])
        self.assertIn("Candidate lifecycle", drawn)
        self.assertIn("Validation", drawn)


if __name__ == "__main__":
    unittest.main()
