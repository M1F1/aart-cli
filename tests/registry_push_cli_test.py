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
        _git(root, "add", ".")
        _git(root, "commit", "-m", "Initial registry")
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

    def test_a_checkout_with_nothing_committed_yet_is_refused_rather_than_pushed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            _git(root, "init", "-b", "main")

            self.assertNotEqual(
                0, _run("registry", "push", "--source", str(root), "--branch", "registry-update")
            )


if __name__ == "__main__":
    unittest.main()
