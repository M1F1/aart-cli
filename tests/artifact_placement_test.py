"""Where an installed artifact's own runtime lives.

An MCP artifact owns a tree: the payload copied out of the object store, the environment built for
it, and the interpreter inside that environment. Something has to decide where that tree goes, and
until now nothing did -- the only answer in the repository was a path typed into an end-to-end test.

Two properties decide it. It cannot live inside a harness's directory, because one artifact may
register with several harnesses and the tree is not any one of theirs. And it belongs beside the
manifest that records it, so an operator who finds one finds the other: the same two roots
`install_state_paths` already uses, one per scope.

Nothing here touches a filesystem. These are path decisions, and a path decision that consulted the
disk could give two answers on two machines for the same install.
"""

from __future__ import annotations

import unittest

from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ArtifactIdentity, SourceAlias
from agent_artifacts.domain.placement import artifact_root

PROJECT = "/work/project"
DATA = "/users/alice/.local/share/agent-artifacts"


def _coordinate(kind: str = "mcp", name: str = "github", version: str | None = "1.5.0"):
    return ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity(kind, name), version)


class ArtifactRootTest(unittest.TestCase):
    def test_a_project_artifact_lives_beside_the_manifest_that_records_it(self) -> None:
        self.assertEqual(
            artifact_root(_coordinate(), Scope.PROJECT, project_root=PROJECT, data_root=DATA),
            "/work/project/.agent-artifacts/runtimes/public/mcp/github",
        )

    def test_a_user_artifact_lives_under_the_data_root(self) -> None:
        self.assertEqual(
            artifact_root(_coordinate(), Scope.USER, project_root=PROJECT, data_root=DATA),
            f"{DATA}/runtimes/public/mcp/github",
        )

    def test_the_source_is_part_of_the_path(self) -> None:
        """Two sources may publish the same name, and they are not the same artifact."""

        mine = artifact_root(_coordinate(), Scope.PROJECT, project_root=PROJECT, data_root=DATA)
        theirs = artifact_root(
            ArtifactCoordinate(SourceAlias("team"), ArtifactIdentity("mcp", "github"), "1.5.0"),
            Scope.PROJECT,
            project_root=PROJECT,
            data_root=DATA,
        )

        self.assertNotEqual(mine, theirs)

    def test_the_version_is_not_part_of_the_path(self) -> None:
        """An update reconciles one installation; it does not install a second one beside it."""

        self.assertEqual(
            artifact_root(
                _coordinate(version="1.5.0"), Scope.PROJECT, project_root=PROJECT, data_root=DATA
            ),
            artifact_root(
                _coordinate(version="2.0.0"), Scope.PROJECT, project_root=PROJECT, data_root=DATA
            ),
        )

    def test_no_harness_appears_in_the_path(self) -> None:
        """One artifact may register with several harnesses; the tree is not any one of theirs."""

        root = artifact_root(_coordinate(), Scope.PROJECT, project_root=PROJECT, data_root=DATA)

        self.assertNotIn(".claude", root)
        self.assertNotIn(".tabnine", root)

    def test_a_relative_root_is_refused_rather_than_resolved_against_a_working_directory(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            artifact_root(_coordinate(), Scope.PROJECT, project_root="project", data_root=DATA)

    def test_a_climbing_root_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            artifact_root(_coordinate(), Scope.USER, project_root=PROJECT, data_root="/data/../etc")

    def test_it_refuses_anything_that_is_not_a_coordinate_and_a_scope(self) -> None:
        with self.assertRaises(ValueError):
            artifact_root("public/mcp/github", Scope.PROJECT, project_root=PROJECT, data_root=DATA)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            artifact_root(_coordinate(), "project", project_root=PROJECT, data_root=DATA)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
