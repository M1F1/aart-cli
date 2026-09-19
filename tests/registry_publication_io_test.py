"""The concrete publication adapter pushes one reviewed commit and never touches the default."""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from typing import Iterator

from aart_cli.application.registry_publication import (
    PublicationOutcome,
    RegistryPublicationCommand,
)
from aart_cli.domain.identifiers import ObjectDigest, SourceAlias
from aart_cli.domain.publication import PublicationBranch
from aart_cli.domain.result import Err, Ok
from aart_cli.io.registry_publication import (
    publish_registry_commit,
    registry_remote_default_branch,
)

_DIGEST = ObjectDigest("sha256", "d" * 64)


def _git(root: pathlib.Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments), check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


@contextmanager
def _registry() -> Iterator[tuple[pathlib.Path, pathlib.Path, str]]:
    """A registry checkout on `main` with an `origin` bare remote that already holds it."""

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
        (root / "registry.json").write_text("{}\n", encoding="utf-8")
        _git(root, "add", "registry.json")
        _git(root, "commit", "-m", "Initial registry")
        _git(root, "remote", "add", "origin", str(remote))
        _git(root, "push", "origin", "main")
        (root / "registry.json").write_text('{"promoted": true}\n', encoding="utf-8")
        _git(root, "add", "registry.json")
        _git(root, "commit", "-m", "Promote example@1.0.0")
        yield root, remote, _git(root, "rev-parse", "HEAD")


def _command(revision: str, branch: str = "registry-update") -> RegistryPublicationCommand:
    return RegistryPublicationCommand(
        SourceAlias("company"), "origin", PublicationBranch(branch), revision, _DIGEST
    )


class PublishRegistryCommitTest(unittest.TestCase):
    def test_the_remote_default_branch_is_read_from_its_advertised_head(self) -> None:
        with _registry() as (root, _remote, _revision):
            resolved = registry_remote_default_branch(str(root), "origin")
            assert isinstance(resolved, Ok), resolved
            self.assertEqual("main", resolved.value)

    def test_a_reviewed_commit_reaches_a_new_remote_branch(self) -> None:
        with _registry() as (root, remote, revision):
            published = publish_registry_commit(str(root), _command(revision))
            assert isinstance(published, Ok), published
            self.assertEqual(PublicationOutcome.CREATED, published.value.outcome)
            self.assertEqual(revision, _git(remote, "rev-parse", "refs/heads/registry-update"))

    def test_the_default_branch_is_left_exactly_where_it_was(self) -> None:
        with _registry() as (root, remote, revision):
            before = _git(remote, "rev-parse", "refs/heads/main")
            published = publish_registry_commit(str(root), _command(revision))
            assert isinstance(published, Ok), published
            self.assertEqual(before, _git(remote, "rev-parse", "refs/heads/main"))
            self.assertNotEqual(before, revision)

    def test_publishing_to_the_remote_default_branch_is_refused_at_the_adapter(self) -> None:
        with _registry() as (root, remote, revision):
            refused = publish_registry_commit(str(root), _command(revision, branch="main"))
            assert isinstance(refused, Err)
            self.assertEqual(
                "registry-default-branch-publication", refused.diagnostics[0].code.value
            )
            self.assertNotEqual(revision, _git(remote, "rev-parse", "refs/heads/main"))

    def test_publishing_the_same_revision_twice_reports_that_nothing_moved(self) -> None:
        with _registry() as (root, revision_remote, revision):
            first = publish_registry_commit(str(root), _command(revision))
            assert isinstance(first, Ok), first
            second = publish_registry_commit(str(root), _command(revision))
            assert isinstance(second, Ok), second
            self.assertEqual(PublicationOutcome.ALREADY_CURRENT, second.value.outcome)

    def test_a_second_reviewed_commit_updates_the_same_branch(self) -> None:
        with _registry() as (root, remote, revision):
            assert isinstance(publish_registry_commit(str(root), _command(revision)), Ok)
            (root / "registry.json").write_text('{"promoted": 2}\n', encoding="utf-8")
            _git(root, "add", "registry.json")
            _git(root, "commit", "-m", "Promote example@1.1.0")
            second = _git(root, "rev-parse", "HEAD")
            published = publish_registry_commit(str(root), _command(second))
            assert isinstance(published, Ok), published
            self.assertEqual(PublicationOutcome.UPDATED, published.value.outcome)
            self.assertEqual(second, _git(remote, "rev-parse", "refs/heads/registry-update"))

    def test_a_history_rewrite_is_refused_rather_than_forced(self) -> None:
        with _registry() as (root, remote, revision):
            assert isinstance(publish_registry_commit(str(root), _command(revision)), Ok)
            _git(root, "reset", "--hard", "HEAD~1")
            (root / "registry.json").write_text('{"rewritten": true}\n', encoding="utf-8")
            _git(root, "add", "registry.json")
            _git(root, "commit", "-m", "Rewrite")
            rewritten = _git(root, "rev-parse", "HEAD")
            refused = publish_registry_commit(str(root), _command(rewritten))
            self.assertIsInstance(refused, Err)
            self.assertEqual(revision, _git(remote, "rev-parse", "refs/heads/registry-update"))

    def test_a_revision_the_checkout_does_not_hold_is_refused_before_the_remote(self) -> None:
        with _registry() as (root, remote, _revision):
            refused = publish_registry_commit(str(root), _command("e" * 40))
            assert isinstance(refused, Err)
            # Git would refuse the push too, with its own words.  The claim here is that AART
            # notices first and says which commit is missing, so the answer is about the registry
            # rather than about a refspec.
            self.assertEqual("registry-publication-failed", refused.diagnostics[0].code.value)
            self.assertIn("e" * 12, refused.diagnostics[0].message)
            self.assertEqual(
                "",
                _git(remote, "for-each-ref", "--format=%(refname)", "refs/heads/registry-update"),
            )

    def test_a_root_that_is_not_a_normalized_absolute_path_is_refused(self) -> None:
        with _registry() as (root, _remote, revision):
            for candidate in ("registry", f"{root}/", f"{root}/../{root.name}", ""):
                with self.subTest(root=candidate):
                    self.assertIsInstance(
                        publish_registry_commit(candidate, _command(revision)), Err
                    )

    def test_anything_but_a_prepared_command_is_refused(self) -> None:
        with _registry() as (root, _remote, revision):
            self.assertIsInstance(
                publish_registry_commit(str(root), "origin registry-update"),  # type: ignore[arg-type]
                Err,
            )

    def test_an_unknown_remote_is_refused(self) -> None:
        with _registry() as (root, _remote, revision):
            command = RegistryPublicationCommand(
                SourceAlias("company"),
                "elsewhere",
                PublicationBranch("registry-update"),
                revision,
                _DIGEST,
            )
            self.assertIsInstance(publish_registry_commit(str(root), command), Err)


if __name__ == "__main__":
    unittest.main()
