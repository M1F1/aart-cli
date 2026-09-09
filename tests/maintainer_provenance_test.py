"""CP-14 screen 49 exposes typed, compiler-produced Candidate provenance."""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer import CandidateBundle
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_candidate_lifecycle,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_maintainer_provenance,
)
from agent_artifacts.application.promotion import PromotionSourceKind
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.maintainer_candidate_shell_test import _projected_source
from tests.maintainer_promotion_test import _LOCAL_REVISION, _scan


class MaintainerProvenanceProjectionTest(unittest.TestCase):
    def test_git_provenance_exposes_the_exact_importer_and_payload(self) -> None:
        bundle = _scan().active[0]

        view = project_maintainer_provenance(bundle)

        self.assertIs(view.source_kind, PromotionSourceKind.GIT_REVISION)
        self.assertEqual(view.source_url, "https://git.example/authors.git")
        self.assertEqual(view.git_revision, "a" * 40)
        self.assertIsNone(view.local_snapshot_digest)
        self.assertEqual(view.manifest_path, "github/aart.json")
        self.assertEqual(view.importer_id, "aart-native-author")
        self.assertEqual(view.importer_version, "1.0.0")
        self.assertEqual(
            view.payload_paths,
            ("payload/mcp.json", "payload/server.py"),
        )

    def test_local_provenance_keeps_a_snapshot_digest_out_of_the_git_field(self) -> None:
        bundle = _scan(revision=_LOCAL_REVISION).active[0]

        view = project_maintainer_provenance(bundle)

        self.assertIs(view.source_kind, PromotionSourceKind.LOCAL_SNAPSHOT)
        self.assertEqual(view.source_url, "/work/authors")
        self.assertIsNone(view.git_revision)
        self.assertEqual(view.local_snapshot_digest, "sha256:" + "1" * 64)

    def test_provenance_warnings_are_retained_and_domain_native_mismatch_is_refused(self) -> None:
        bundle = _scan().active[0]
        provenance = bundle.artifact.native_package.provenance
        assert provenance is not None
        native = dataclasses.replace(
            bundle.artifact.native_package,
            provenance=dataclasses.replace(provenance, warnings=("imported with warning",)),
        )
        warned = CandidateBundle(
            bundle.candidate,
            dataclasses.replace(bundle.artifact, native_package=native),
        )

        self.assertEqual(
            project_maintainer_provenance(warned).warnings,
            ("imported with warning",),
        )

        wrong_origin = dataclasses.replace(provenance.origin, url="https://wrong.example/source")
        mismatched = CandidateBundle(
            bundle.candidate,
            dataclasses.replace(
                bundle.artifact,
                native_package=dataclasses.replace(
                    bundle.artifact.native_package,
                    provenance=dataclasses.replace(provenance, origin=wrong_origin),
                ),
            ),
        )
        with self.assertRaises(ValueError):
            project_maintainer_provenance(mismatched)


class MaintainerProvenanceShellTest(unittest.TestCase):
    def test_screen_48_enters_screen_49_and_drawing_reads_nothing(self) -> None:
        scan = _scan()
        bundle = scan.active[0]
        lifecycle = project_maintainer_candidate_lifecycle(
            bundle,
            validate_candidate(bundle, policy=EffectivePolicy()),
            history=scan.history,
            versions=(),
            audits=(),
        )
        provenance = project_maintainer_provenance(bundle)
        source_view = _projected_source("authors", scan)
        views = MaintainerViews(
            project_maintainer_dashboard((source_view,)),
            (source_view,),
            project_maintainer_candidates((scan,)),
            lifecycles=(lifecycle,),
            provenances=(provenance,),
        )
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
        )
        lifecycle_state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.CANDIDATE_LIFECYCLE),
            settings=ConsumerSettings().with_maintainer_mode(True),
            focus=bundle.candidate.id.value,
        )

        self.assertIs(source.detail(lifecycle_state), MaintainerScreen.PROVENANCE)
        state = _reload(
            source,
            dataclasses.replace(
                lifecycle_state,
                session=lifecycle_state.session.navigate(MaintainerScreen.PROVENANCE),
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
        self.assertIn("Pinned Git revision", drawn)
        self.assertIn("aart-native-author 1.0.0", drawn)
        self.assertIn("payload/server.py", drawn)


if __name__ == "__main__":
    unittest.main()
