"""CP-14 screens 51–52 project versioned Collection Candidates over approved state."""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_collection_candidate,
    project_maintainer_collection_validation,
    project_maintainer_dashboard,
)
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.domain.collection_candidates import (
    CollectionCandidate,
    collection_candidate_id_for,
)
from agent_artifacts.domain.identifiers import ArtifactIdentity, ObjectDigest, SourceAlias
from agent_artifacts.domain.registry import PublicationStage
from agent_artifacts.domain.selection import ArtifactRequest, VersionConstraint
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.approved_marketplace_resolution_test import _artifact, _marketplace, _snapshot


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _request(name: str, constraint: str = "^1") -> ArtifactRequest:
    return ArtifactRequest(
        ArtifactIdentity("mcp", name),
        VersionConstraint(constraint),
        SourceAlias("company"),
    )


def _candidate(*members: ArtifactRequest) -> CollectionCandidate:
    source_alias = SourceAlias("authors")
    target = SourceAlias("company")
    input_digest = _digest("a")
    path = "collections/data-engineer/aart.yaml"
    return CollectionCandidate(
        collection_candidate_id_for(source_alias, path, input_digest, target),
        source_alias,
        "https://git.example/authors.git",
        "b" * 40,
        path,
        input_digest,
        _digest("c"),
        target,
        "data-engineer",
        "2.1.0",
        "Approved data engineering tools.",
        members or (_request("github"),),
        CandidateState.NEW,
    )


def _approved_marketplace():
    github = _artifact("company", "github", "1.4.0", snapshot_character="d", payload_character="1")
    jira = _artifact("company", "jira", "3.0.0", snapshot_character="d", payload_character="2")
    return _marketplace(_snapshot("company", "d", (github, jira)))


class MaintainerCollectionCandidateProjectionTest(unittest.TestCase):
    def test_collection_candidate_is_versioned_and_keeps_declarative_constraints(self) -> None:
        candidate = _candidate(_request("github", "^1"), _request("jira", "^3"))

        view = project_maintainer_collection_candidate(candidate)

        self.assertEqual(view.coordinate, "company/collection/data-engineer@2.1.0")
        self.assertEqual(view.state, CandidateState.NEW)
        self.assertEqual(view.source_alias, "authors")
        self.assertEqual(view.members, ("company/mcp/github@^1", "company/mcp/jira@^3"))

    def test_validation_resolves_every_member_only_to_approved_target_registry_versions(
        self,
    ) -> None:
        candidate = _candidate(_request("github", "^1"), _request("jira", "^3"))

        view = project_maintainer_collection_validation(candidate, _approved_marketplace())

        self.assertEqual(view.outcome, "ready")
        self.assertEqual(view.registry_snapshot, str(_digest("d")))
        self.assertEqual(
            tuple(item.resolved_coordinate for item in view.members),
            ("company/mcp/github@1.4.0", "company/mcp/jira@3.0.0"),
        )
        self.assertTrue(all(item.outcome == "approved" for item in view.members))

    def test_unpublished_or_incompatible_members_make_the_collection_invalid(self) -> None:
        local_only = _artifact(
            "company",
            "github",
            "1.4.0",
            snapshot_character="d",
            payload_character="1",
            publication=PublicationStage.PROMOTED_LOCAL,
        )
        marketplace = _marketplace(_snapshot("company", "d", (local_only,)))

        unpublished = project_maintainer_collection_validation(
            _candidate(_request("github", "^1")), marketplace
        )
        incompatible = project_maintainer_collection_validation(
            _candidate(_request("github", "^2")), _approved_marketplace()
        )

        self.assertEqual(unpublished.outcome, "invalid")
        self.assertEqual(incompatible.outcome, "invalid")
        self.assertTrue(all(item.resolved_coordinate is None for item in unpublished.members))
        self.assertIn("approved", " ".join(unpublished.diagnostics).lower())
        self.assertIn("constraint", " ".join(incompatible.diagnostics).lower())

    def test_another_registry_cannot_satisfy_the_target_registry_validation(self) -> None:
        team_request = ArtifactRequest(
            ArtifactIdentity("mcp", "github"), VersionConstraint("^1"), SourceAlias("team")
        )
        team = _artifact("team", "github", "1.4.0", snapshot_character="e", payload_character="1")
        marketplace = _marketplace(
            _snapshot("company", "d", ()),
            _snapshot("team", "e", (team,)),
        )

        view = project_maintainer_collection_validation(_candidate(team_request), marketplace)

        self.assertEqual(view.outcome, "invalid")
        self.assertIsNone(view.members[0].resolved_coordinate)


class MaintainerCollectionCandidateShellTest(unittest.TestCase):
    def test_screen_51_opens_screen_52_and_drawing_reads_nothing(self) -> None:
        candidate = _candidate(_request("github", "^1"), _request("jira", "^3"))
        row = project_maintainer_collection_candidate(candidate)
        validation = project_maintainer_collection_validation(candidate, _approved_marketplace())
        views = MaintainerViews(
            project_maintainer_dashboard(()),
            (),
            collection_candidates=(row,),
            collection_validations=(validation,),
        )
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
        )
        listing = ConsumerUiState(
            ConsumerSession(MaintainerScreen.COLLECTION_CANDIDATES),
            settings=ConsumerSettings().with_maintainer_mode(True),
        )
        listed = _reload(source, listing, entering=True)
        self.assertEqual(listed.rows, (candidate.id.value,))
        self.assertIs(source.detail(listed), MaintainerScreen.COLLECTION_VALIDATION)
        state = _reload(
            source,
            dataclasses.replace(
                listed,
                session=listed.session.navigate(MaintainerScreen.COLLECTION_VALIDATION),
                focus=candidate.id.value,
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
        self.assertIn("Collection validation", drawn)
        self.assertIn("company/mcp/github@1.4.0", drawn)


if __name__ == "__main__":
    unittest.main()
