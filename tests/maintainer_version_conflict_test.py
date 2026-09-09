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
from agent_artifacts.domain.candidates import assess_candidate
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
