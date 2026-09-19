"""Where the registry this project publishes has got to, read from the checkout itself.

`QA-098` asks screen 46 to say which branch the current snapshot sits on, whether the remote knows
that branch, and whether anything is waiting to be pushed. Every answer here comes from refs the
checkout already holds: drawing a frame does no network, so what the screen reports is this
checkout's knowledge of its remote and never a fresh fact about it.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from typing import Iterator

from aart_cli.application.maintainer_views import MaintainerPublicationState
from aart_cli.configuration.model import SourceKind
from aart_cli.configuration.policy import EffectiveConfiguration
from aart_cli.domain.result import Ok
from aart_cli.io.maintainer_views import read_maintainer_views
from aart_cli.io.registry_workspace import read_registry_workspace
from tests.marketplace_fixtures import configured_source, effective_configuration


def _git(root: pathlib.Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments), check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _manifest(registry_id: str = "manual-registry") -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "protocol_version": 1,
            "registry_id": registry_id,
            "display_name": "Manual Registry",
            "requires_aart": {"min_inclusive": "1.0.0", "max_exclusive": "2.0.0"},
            "required_capabilities": ["lockfile-v1", "registry-entry-v1"],
            "default_channel": "main",
            "services": {},
        }
    )


@contextmanager
def _workspace(*, marker: str | None = None) -> Iterator[pathlib.Path]:
    """A committed registry checkout with no remote at all, which is where a new one starts."""

    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary).resolve() / "registry"
        root.mkdir()
        _git(root, "init", "-b", "main")
        _git(root, "config", "user.name", "AART Test")
        _git(root, "config", "user.email", "aart@example.invalid")
        if marker is not None:
            (root / "aart-registry.json").write_text(marker, encoding="utf-8")
            _git(root, "add", "aart-registry.json")
            _git(root, "commit", "-m", "Initialize registry")
        yield root


def _publish(root: pathlib.Path) -> pathlib.Path:
    """Give the checkout an `origin` that already holds its branch, as a push would."""

    remote = root.parent / "remote.git"
    subprocess.run(
        ("git", "init", "--bare", "-b", "main", str(remote)), check=True, capture_output=True
    )
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "main")
    return remote


class RegistryWorkspaceReaderTest(unittest.TestCase):
    def test_a_project_that_is_not_a_registry_publishes_none(self) -> None:
        with _workspace() as root:
            self.assertIsNone(read_registry_workspace(str(root)))

    def test_a_relative_root_is_not_read_at_all(self) -> None:
        self.assertIsNone(read_registry_workspace("registry"))

    def test_the_registry_names_itself_and_the_snapshot_is_its_short_commit(self) -> None:
        with _workspace(marker=_manifest()) as root:
            view = read_registry_workspace(str(root))

            assert view is not None
            self.assertEqual("manual-registry", view.name)
            self.assertEqual(_git(root, "rev-parse", "--short", "HEAD"), view.commit)
            self.assertEqual("main", view.branch)

    def test_an_unreadable_marker_leaves_the_directory_to_name_it(self) -> None:
        with _workspace(marker="{not json") as root:
            view = read_registry_workspace(str(root))

            assert view is not None
            self.assertEqual(root.name, view.name)

    def test_a_checkout_no_remote_knows_of_is_unpublished(self) -> None:
        with _workspace(marker=_manifest()) as root:
            view = read_registry_workspace(str(root))

            assert view is not None
            self.assertIsNone(view.origin)
            self.assertIsNone(view.remote_branch)
            self.assertIs(MaintainerPublicationState.UNPUBLISHED, view.state)

    def test_a_pushed_branch_is_published_with_nothing_waiting(self) -> None:
        with _workspace(marker=_manifest()) as root:
            remote = _publish(root)

            view = read_registry_workspace(str(root))

            assert view is not None
            self.assertEqual(str(remote), view.origin)
            self.assertEqual("origin/main", view.remote_branch)
            self.assertEqual(0, view.unpushed)
            self.assertIs(MaintainerPublicationState.PUBLISHED, view.state)

    def test_commits_the_remote_has_not_got_are_counted_as_waiting(self) -> None:
        with _workspace(marker=_manifest()) as root:
            _publish(root)
            for index in range(2):
                (root / f"entry-{index}.json").write_text("{}\n", encoding="utf-8")
                _git(root, "add", f"entry-{index}.json")
                _git(root, "commit", "-m", f"Promote example@1.{index}.0")

            view = read_registry_workspace(str(root))

            assert view is not None
            self.assertEqual(2, view.unpushed)
            self.assertIs(MaintainerPublicationState.AHEAD, view.state)

    def test_a_detached_head_names_no_branch_anybody_could_push(self) -> None:
        with _workspace(marker=_manifest()) as root:
            _git(root, "checkout", "--detach", "HEAD")

            view = read_registry_workspace(str(root))

            assert view is not None
            self.assertIsNone(view.branch)
            self.assertIsNone(view.remote_branch)

    def test_a_registry_no_git_ever_touched_is_left_unobserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            (root / "aart-registry.json").write_text(_manifest(), encoding="utf-8")

            view = read_registry_workspace(str(root))

            assert view is not None
            self.assertIsNone(view.commit)
            self.assertIs(MaintainerPublicationState.UNOBSERVED, view.state)


class ProjectedRegistryWorkspaceTest(unittest.TestCase):
    """The projection carries it, because a renderer may not run Git to find it out itself."""

    def _effective(self) -> EffectiveConfiguration:
        registry = configured_source("company", SourceKind.REGISTRY_GIT)
        return effective_configuration((registry,), default_registry="company")

    def test_the_registry_this_project_publishes_reaches_the_views(self) -> None:
        with _workspace(marker=_manifest()) as root:
            composed = read_maintainer_views(
                self._effective(), data_root=str(root.parent / "data"), registry_root=str(root)
            )

            assert isinstance(composed, Ok), composed
            workspace = composed.value.registry_workspace
            assert workspace is not None
            self.assertEqual("manual-registry", workspace.name)
            self.assertIs(MaintainerPublicationState.UNPUBLISHED, workspace.state)

    def test_a_project_with_no_registry_checkout_carries_nothing(self) -> None:
        with _workspace() as root:
            composed = read_maintainer_views(
                self._effective(), data_root=str(root.parent / "data"), registry_root=str(root)
            )

            assert isinstance(composed, Ok), composed
            self.assertIsNone(composed.value.registry_workspace)


if __name__ == "__main__":
    unittest.main()
