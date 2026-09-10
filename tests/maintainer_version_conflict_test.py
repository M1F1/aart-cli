"""CP-14 screen 50 makes immutable coordinate/version conflicts explicit."""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_maintainer_provenance,
    project_maintainer_version_conflict,
)
from agent_artifacts.domain.candidates import CandidateState, assess_candidate
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.registry import PromotionMode, registry_version_from_candidate
from agent_artifacts.domain.result import Ok
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.maintainer_candidate_shell_test import _projected_source
from tests.maintainer_source_scan_test import _compiled, _digest


def _conflict():
    initial = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        _compiled(),
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(initial, Ok)
    ready = assess_candidate(initial.value.active[0].candidate)
    published = registry_version_from_candidate(
        ready,
        object_digest=_digest("2"),
        registry_snapshot=_digest("1"),
        mode=PromotionMode.VENDORED,
    )
    changed = reconcile_source_scan(
        SourceAlias("authors"),
        "b" * 40,
        _compiled(revision="b", server="print('different')\n"),
        previous=(),
        approved=(published,),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(changed, Ok)
    return changed.value, published


class PublishedCandidateSupersessionTest(unittest.TestCase):
    """`QA-062`: an author editing an already-published version must not crash Source Sync.

    Once a version is published, the next Sync records its Candidate as `promoted` -- the registry
    is the authority on that (`supersede_candidate` refuses to move a promoted Candidate for
    exactly that reason).  When the author then edits the payload without bumping the version,
    reconciliation used to supersede whatever the previous record was, promoted or not, and the
    domain refused with a `ValueError` that no boundary catches.  A published artifact getting an
    edit at the same version is an ordinary upstream event and the answer to it is already
    modelled: the new Candidate is `invalid` with `registry-version-immutable`, and the promoted
    record stays exactly what the registry says it is.
    """

    def _promoted(self):
        """One Source Sync over a version this registry has already published."""

        first = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(first, Ok)
        published = registry_version_from_candidate(
            assess_candidate(first.value.active[0].candidate),
            object_digest=_digest("2"),
            registry_snapshot=_digest("1"),
            mode=PromotionMode.VENDORED,
        )
        synced = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(published,),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(synced, Ok)
        return synced.value, published

    def test_the_published_candidate_really_is_promoted_after_a_plain_resync(self) -> None:
        scan, _ = self._promoted()

        self.assertEqual(scan.active[0].candidate.state, CandidateState.PROMOTED)

    def test_an_edit_at_a_published_version_is_refused_rather_than_raised(self) -> None:
        scan, published = self._promoted()

        changed = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            _compiled(revision="b", server="print('different')\n"),
            previous=scan.history,
            approved=(published,),
            target_registry=SourceAlias("company"),
        )

        self.assertIsInstance(changed, Ok)
        assert isinstance(changed, Ok)
        candidate = changed.value.active[0].candidate
        self.assertEqual(candidate.state, CandidateState.INVALID)
        self.assertIn("registry-version-immutable", tuple(item.code for item in candidate.findings))
        self.assertEqual(
            candidate.previous,
            scan.active[0].candidate.id,
            "the conflicting Candidate must name the published record it collides with",
        )

    def test_the_promoted_record_is_left_as_the_registry_states_it(self) -> None:
        """The history keeps the published fact; only the new Candidate carries the conflict."""

        scan, published = self._promoted()
        promoted_id = scan.active[0].candidate.id

        changed = reconcile_source_scan(
            SourceAlias("authors"),
            "b" * 40,
            _compiled(revision="b", server="print('different')\n"),
            previous=scan.history,
            approved=(published,),
            target_registry=SourceAlias("company"),
        )

        assert isinstance(changed, Ok)
        kept = next(
            bundle for bundle in changed.value.history if bundle.candidate.id == promoted_id
        )
        self.assertEqual(kept.candidate.state, CandidateState.PROMOTED)
        self.assertIsNone(kept.candidate.successor)


class MaintainerVersionConflictProjectionTest(unittest.TestCase):
    def test_exact_collision_names_both_digest_sets_and_requires_a_new_version(self) -> None:
        scan, published = _conflict()
        candidate = scan.active[0].candidate

        view = project_maintainer_version_conflict(scan.active[0], (published,))

        assert view is not None
        self.assertTrue(view.exact_evidence)
        self.assertEqual(view.coordinate, str(published.coordinate))
        self.assertEqual(view.published_candidate_id, published.candidate_id.value)
        self.assertEqual(view.published_input_digest, str(published.input_digest))
        self.assertEqual(view.published_payload_digest, str(published.payload_digest))
        self.assertEqual(view.published_canonical_digest, str(published.canonical_digest))
        self.assertEqual(
            view.candidate_input_digest, str(candidate.artifact.provenance.input_digest)
        )
        self.assertEqual(view.candidate_payload_digest, str(candidate.artifact.payload_digest))
        self.assertEqual(view.candidate_canonical_digest, str(candidate.canonical_digest))
        self.assertIn("new version", view.required_action.lower())

    def test_durable_conflict_remains_visible_when_registry_evidence_is_unavailable(self) -> None:
        scan, _ = _conflict()

        view = project_maintainer_version_conflict(scan.active[0], None)

        assert view is not None
        self.assertFalse(view.exact_evidence)
        self.assertIsNone(view.published_candidate_id)
        self.assertIn("unavailable", view.evidence_detail.lower())
        self.assertIn("new version", view.required_action.lower())

    def test_a_new_coordinate_without_a_conflict_has_no_conflict_screen(self) -> None:
        initial = reconcile_source_scan(
            SourceAlias("authors"),
            "a" * 40,
            _compiled(),
            previous=(),
            approved=(),
            target_registry=SourceAlias("company"),
        )
        assert isinstance(initial, Ok)

        self.assertIsNone(project_maintainer_version_conflict(initial.value.active[0], ()))


class MaintainerVersionConflictShellTest(unittest.TestCase):
    def test_provenance_enters_conflict_and_drawing_reads_nothing(self) -> None:
        scan, published = _conflict()
        bundle = scan.active[0]
        conflict = project_maintainer_version_conflict(bundle, (published,))
        assert conflict is not None
        source_view = _projected_source("authors", scan)
        views = MaintainerViews(
            project_maintainer_dashboard((source_view,)),
            (source_view,),
            project_maintainer_candidates((scan,)),
            provenances=(project_maintainer_provenance(bundle),),
            version_conflicts=(conflict,),
        )
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
        )
        provenance_state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.PROVENANCE),
            settings=ConsumerSettings().with_maintainer_mode(True),
            focus=bundle.candidate.id.value,
        )

        self.assertIs(source.detail(provenance_state), MaintainerScreen.VERSION_CONFLICT)
        state = _reload(
            source,
            dataclasses.replace(
                provenance_state,
                session=provenance_state.session.navigate(MaintainerScreen.VERSION_CONFLICT),
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
        self.assertIn("Published content", drawn)
        self.assertIn("must receive a new version", drawn)


if __name__ == "__main__":
    unittest.main()
