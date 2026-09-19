"""`aart registry push` moves the reviewed commit, and never to the default branch (`D-228`).

164.7 stopped ending the maintainer's work at the local commit. The push is an action inside AART,
and the boundary it keeps is the branch: reviewed bytes go somewhere people can look at them, and
only a merge makes them the registry. This is the CLI half of that; the surface half is screen 45.
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from typing import Iterator

from agent_artifacts import cli
from agent_artifacts.commands import registry as registry_command
from agent_artifacts.io.registry_workspace import read_registry_workspace


def _git(root: pathlib.Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments), check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


@contextmanager
def _registry() -> Iterator[tuple[pathlib.Path, pathlib.Path, str]]:
    with tempfile.TemporaryDirectory() as temporary:
        base = pathlib.Path(temporary).resolve()
        remote = base / "remote.git"
        root = base / "registry"
        subprocess.run(
            ("git", "init", "--bare", "-b", "main", str(remote)), check=True, capture_output=True
        )
        root.mkdir()
        _git(root, "init", "-b", "main")
        _git(root, "config", "user.name", "AART Test")
        _git(root, "config", "user.email", "aart@example.invalid")
        initialized = _run(
            "registry",
            "init",
            "--source",
            str(root),
            "--source-id",
            "company-registry",
            "--display-name",
            "Company Registry",
            "--yes",
        )
        if initialized != 0:
            raise RuntimeError("canonical Registry fixture did not initialize")
        published = _run("registry", "publish", "--source", str(root), "--yes")
        if published != 0:
            raise RuntimeError("canonical Registry fixture did not publish")
        _git(root, "remote", "add", "origin", str(remote))
        _git(root, "push", "origin", "main")
        readme = root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8") + "\nReviewed update.\n", encoding="utf-8"
        )
        _git(root, "add", "README.md")
        _git(root, "commit", "-m", "Promote example@1.0.0")
        yield root, remote, _git(root, "rev-parse", "HEAD")


def _run(*arguments: str) -> int:
    parsed = cli.build_parser().parse_args(arguments)
    return registry_command.run(cli._to_request(parsed))


class RegistryPushCliTest(unittest.TestCase):
    def test_push_is_one_of_the_registry_actions(self) -> None:
        parser = cli.build_parser()
        parsed = parser.parse_args(
            ("registry", "push", "--source", "/tmp/registry", "--branch", "registry-update")
        )
        self.assertEqual("push", parsed.registry_action)
        self.assertEqual("registry-update", parsed.publication_branch)
        self.assertEqual("origin", parsed.publication_remote)

    def test_it_pushes_the_committed_revision_to_the_named_branch(self) -> None:
        with _registry() as (root, remote, revision):
            code = _run("registry", "push", "--source", str(root), "--branch", "registry-update")

            self.assertEqual(0, code)
            self.assertEqual(revision, _git(remote, "rev-parse", "refs/heads/registry-update"))

    def test_it_leaves_the_default_branch_where_it_was(self) -> None:
        with _registry() as (root, remote, revision):
            before = _git(remote, "rev-parse", "refs/heads/main")
            _run("registry", "push", "--source", str(root), "--branch", "registry-update")

            self.assertEqual(before, _git(remote, "rev-parse", "refs/heads/main"))
            self.assertNotEqual(before, revision)

    def test_pushing_to_the_default_branch_is_refused_by_the_command(self) -> None:
        with _registry() as (root, remote, revision):
            before = _git(remote, "rev-parse", "refs/heads/main")
            code = _run("registry", "push", "--source", str(root), "--branch", "main")

            self.assertNotEqual(0, code)
            self.assertEqual(before, _git(remote, "rev-parse", "refs/heads/main"))
            self.assertNotEqual(before, revision)

    def test_an_eligible_current_branch_is_the_only_target(self) -> None:
        with _registry() as (root, remote, revision):
            _git(root, "switch", "-c", "reviewed-change")

            code = _run("registry", "push", "--source", str(root), "--branch", "redirected-change")

            self.assertNotEqual(0, code)
            self.assertNotEqual(
                0,
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(remote),
                        "show-ref",
                        "--verify",
                        "refs/heads/redirected-change",
                    ),
                    capture_output=True,
                ).returncode,
            )

    def test_dirty_committed_bytes_are_not_push_ready(self) -> None:
        with _registry() as (root, remote, _revision):
            (root / "README.md").write_text("changed after review\n", encoding="utf-8")

            code = _run("registry", "push", "--source", str(root), "--branch", "registry-update")

            self.assertNotEqual(0, code)
            self.assertNotEqual(
                0,
                subprocess.run(
                    (
                        "git",
                        "-C",
                        str(remote),
                        "show-ref",
                        "--verify",
                        "refs/heads/registry-update",
                    ),
                    capture_output=True,
                ).returncode,
            )

    def test_a_checkout_with_nothing_committed_yet_is_refused_rather_than_pushed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            _git(root, "init", "-b", "main")

            self.assertNotEqual(
                0, _run("registry", "push", "--source", str(root), "--branch", "registry-update")
            )


class RegistryPushMovesNothingItDoesNotOwnTest(unittest.TestCase):
    """CP-26.18: the launch directory is a boundary, and the remote branch is only ever advanced.

    Each of these is stated against a real Git repository rather than a fake, because what is
    being claimed is what Git does -- an ordinary push refusing a rewrite, and a resolution that
    stops at a directory instead of walking up to the registry above it.
    """

    def test_an_existing_review_branch_is_advanced_by_an_ordinary_push(self) -> None:
        with _registry() as (root, remote, _revision):
            self.assertEqual(
                0, _run("registry", "push", "--source", str(root), "--branch", "registry-update")
            )
            readme = root / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8") + "\nSecond reviewed update.\n",
                encoding="utf-8",
            )
            _git(root, "add", "README.md")
            _git(root, "commit", "-m", "Promote example@1.1.0")
            second = _git(root, "rev-parse", "HEAD")

            self.assertEqual(
                0, _run("registry", "push", "--source", str(root), "--branch", "registry-update")
            )
            self.assertEqual(second, _git(remote, "rev-parse", "refs/heads/registry-update"))

    def test_a_diverged_review_branch_is_refused_rather_than_forced(self) -> None:
        with _registry() as (root, remote, _revision):
            self.assertEqual(
                0, _run("registry", "push", "--source", str(root), "--branch", "registry-update")
            )
            published = _git(remote, "rev-parse", "refs/heads/registry-update")
            _git(root, "reset", "--hard", "HEAD~1")
            readme = root / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8") + "\nA different reviewed update.\n",
                encoding="utf-8",
            )
            _git(root, "add", "README.md")
            _git(root, "commit", "-m", "Promote other@1.0.0")

            code = _run("registry", "push", "--source", str(root), "--branch", "registry-update")

            self.assertNotEqual(0, code)
            self.assertEqual(published, _git(remote, "rev-parse", "refs/heads/registry-update"))

    def test_resolution_stops_at_the_launch_directory_and_never_walks_up(self) -> None:
        with _registry() as (root, _remote, _revision):
            inside = root / "registry"
            self.assertTrue(inside.is_dir())

            self.assertIsNone(read_registry_workspace(str(inside)))

    def test_a_source_checkout_is_never_read_as_the_registry_it_sits_in(self) -> None:
        with _registry() as (root, _remote, _revision):
            source = root / "vendor-source"
            source.mkdir()
            (source / "aart-source.json").write_text("{}\n", encoding="utf-8")

            self.assertIsNone(read_registry_workspace(str(source)))

    def test_readiness_is_read_from_the_directory_each_time_it_is_asked(self) -> None:
        """Reopening AART derives the same answer, and a later commit moves it (`D-341`)."""

        with _registry() as (root, _remote, revision):
            first = read_registry_workspace(str(root))
            again = read_registry_workspace(str(root))
            assert first is not None and again is not None
            self.assertEqual(first, again)
            self.assertTrue(first.push_ready, first.push_blockers)
            self.assertEqual(revision, first.revision)

            readme = root / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8") + "\nA later promotion.\n", encoding="utf-8"
            )
            _git(root, "add", "README.md")
            _git(root, "commit", "-m", "Promote later@1.0.0")

            later = read_registry_workspace(str(root))
            assert later is not None
            self.assertTrue(later.push_ready, later.push_blockers)
            self.assertEqual(_git(root, "rev-parse", "HEAD"), later.revision)
            self.assertNotEqual(first.revision, later.revision)


if __name__ == "__main__":
    unittest.main()
