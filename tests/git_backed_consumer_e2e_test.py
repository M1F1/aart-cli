"""CP-17: real Git output reaches public sync, Marketplace and an install receipt."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from agent_artifacts import cli
from agent_artifacts.configuration.model import (
    ReportingSettings,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.paths import Platform, resolve_config_paths
from agent_artifacts.configuration.schema import user_configuration_bytes
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.protocol.native_tree import SnapshotEntry, SnapshotEntryKind, SourceSnapshot
from agent_artifacts.sources.git import acquire_git_snapshot
from agent_artifacts.sources.model import GitSnapshotRequest
from tests.configured_installation_draft_e2e_test import _published_registries
from tests.configured_update_command_e2e_test import (
    AUTHORED_SKILL_1_3_0,
    UPDATED_SKILL_BODY,
)
from tests.marketplace_fixtures import configured_source
from tests.placed_installation_e2e_test import AUTHORED_SKILL, SKILL_BODY
from tests.registry_maintenance_fixtures import empty_registry_snapshot

COORDINATE = "company/skill/code-review"


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _materialize(root: Path, snapshot: SourceSnapshot) -> None:
    root.mkdir(exist_ok=True)
    for entry in snapshot.entries:
        target = root.joinpath(*entry.path.parts)
        if entry.kind is SnapshotEntryKind.DIRECTORY:
            target.mkdir(parents=True, exist_ok=True)
            continue
        if entry.kind is not SnapshotEntryKind.FILE:
            raise AssertionError(f"live registry contains {entry.kind.value}: {entry.path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(entry.content)
        target.chmod(0o700 if entry.executable else 0o600)


def _registry_snapshot(
    *authored: tuple[tuple[str, str] | tuple[str, str, bool], ...],
) -> SourceSnapshot:
    """Add the public workspace identity that promotion output does not yet carry (B-057).

    The authored trees are a parameter because a registry gains versions over time and each
    promotion rebinds the ones it retains. Publishing the second version means promoting both, in
    order, exactly as the maintainer side does -- not editing the first registry's bytes.
    """

    markers = tuple(
        SnapshotEntry(
            entry.path,
            entry.kind,
            entry.content.replace(b"test-registry", b"company-registry"),
            entry.executable,
        )
        for entry in empty_registry_snapshot().entries
    )
    published = _published_registries(*(authored or (AUTHORED_SKILL,)))
    return SourceSnapshot(published.origin, (*markers, *published.entries))


class _Environment:
    def __init__(
        self,
        root: Path,
        *authored: tuple[tuple[str, str] | tuple[str, str, bool], ...],
    ) -> None:
        self.root = root
        self.home = root / "home"
        self.project = root / "project"
        self.repository = root / "registry"
        self.home.mkdir()
        self.project.mkdir()
        _materialize(self.repository, _registry_snapshot(*authored))
        _git(self.repository, "init", "-b", "main")
        _git(self.repository, "config", "user.email", "test@example.invalid")
        _git(self.repository, "config", "user.name", "AART Test")
        _git(self.repository, "add", ".")
        _git(self.repository, "commit", "-m", "approved registry")
        self.head = _git(self.repository, "rev-parse", "HEAD")

        self.xdg = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
        }
        platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
        self.paths = resolve_config_paths(
            platform,
            home=str(self.home),
            xdg_config_home=self.xdg["XDG_CONFIG_HOME"],
            xdg_data_home=self.xdg["XDG_DATA_HOME"],
            xdg_cache_home=self.xdg["XDG_CACHE_HOME"],
        )
        self.source = configured_source("company", SourceKind.REGISTRY_GIT)
        configuration = UserConfiguration(
            1,
            (self.source,),
            self.source.alias,
            SyncSettings(),
            ReportingSettings(),
        )
        config_path = Path(self.paths.user_config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(user_configuration_bytes(configuration))
        self.transport_requests: list[GitSnapshotRequest] = []

    def publish(self, *authored: tuple[tuple[str, str] | tuple[str, str, bool], ...]) -> str:
        """Move the real upstream repository the way a reviewed merge does.

        The working tree is replaced rather than added to, because a promotion rewrites the
        registry's index and snapshot metadata; leaving the previous ones in place would publish a
        repository no maintainer could have produced.
        """

        for path in self.repository.iterdir():
            if path.name == ".git":
                continue
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        _materialize(self.repository, _registry_snapshot(*authored))
        _git(self.repository, "add", "-A")
        _git(self.repository, "commit", "-m", "approved registry update")
        self.head = _git(self.repository, "rev-parse", "HEAD")
        return self.head

    def _local_transport(self, request: GitSnapshotRequest):
        """Substitute the unavailable network, after the production verdict built its request."""

        self.transport_requests.append(request)
        self.assert_remote_request(request)
        return acquire_git_snapshot(
            replace(
                request,
                location=self.repository.as_uri(),
                allow_local_transport=True,
            )
        )

    def assert_remote_request(self, request: GitSnapshotRequest) -> None:
        if request.location != self.source.location or request.allow_local_transport:
            raise AssertionError(f"public sync weakened its transport request: {request!r}")

    def run(self, *argv: str, source_transport: bool = False):
        arguments = [*argv, "--json"]
        if argv[:2] == ("marketplace", "install"):
            arguments.extend(("--project", str(self.project)))
        output = io.StringIO()
        transport = (
            mock.patch(
                "agent_artifacts.sources.runtime.acquire_git_snapshot",
                side_effect=self._local_transport,
            )
            if source_transport
            else contextlib.nullcontext()
        )
        with (
            mock.patch.dict(os.environ, self.xdg, clear=False),
            contextlib.redirect_stdout(output),
            mock.patch("os.getcwd", return_value=str(self.project)),
            transport,
        ):
            code = cli.main(arguments)
        raw = output.getvalue()
        return code, (json.loads(raw) if raw.strip() else None)


class GitBackedConsumerE2ETest(unittest.TestCase):
    def test_public_sync_marketplace_and_install_receipt_keep_the_real_git_revision(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env = _Environment(Path(raw).resolve())

            sync_code, synchronized = env.run("source", "sync", source_transport=True)

            self.assertEqual(sync_code, 0, synchronized)
            self.assertNotEqual(env.head, "a" * 40)
            self.assertEqual(len(env.transport_requests), 1)
            self.assertEqual(synchronized["sources"][0]["resolved_revision"], env.head)

            list_code, marketplace = env.run("marketplace", "list")

            self.assertEqual(list_code, 0, marketplace)
            self.assertEqual(
                [item["coordinate"] for item in marketplace["artifacts"]],
                ["company/skill/code-review@1.2.0"],
            )
            self.assertEqual(marketplace["artifacts"][0]["source"]["resolved_revision"], env.head)

            install_code, installed = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(install_code, 0, installed)
            self.assertEqual(
                (env.project / ".claude/skills/code-review/SKILL.md").read_text(encoding="utf-8"),
                SKILL_BODY,
            )
            self.assertEqual(installed["receipt"]["artifacts"][0]["source_revision"], env.head)

            persisted = LocalReceiptStore(str(Path(env.paths.data_root) / "state")).actions()
            self.assertIsInstance(persisted, Ok, persisted)
            assert isinstance(persisted, Ok)
            self.assertEqual(persisted.value[0].artifacts[0].source_revision, env.head)

    def test_an_upstream_commit_is_offered_but_only_an_explicit_update_rebinds_it(self) -> None:
        """The seam CP-15 step 2 proved over a synthetic store, driven by a real Git commit.

        `source_upstream_movement_e2e_test` already holds that a sync offers rather than applies.
        What it cannot show is that the revision an operator is offered, reviews and ends up with is
        the one Git actually resolved, because every revision in it is a string the test chose.
        """

        with tempfile.TemporaryDirectory() as raw:
            env = _Environment(Path(raw).resolve())
            delivered = env.project / ".claude/skills/code-review/SKILL.md"
            env.run("source", "sync", source_transport=True)
            env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")
            installed_revision = env.head

            moved = env.publish(AUTHORED_SKILL, AUTHORED_SKILL_1_3_0)

            self.assertNotEqual(moved, installed_revision)

            sync_code, synchronized = env.run("source", "sync", source_transport=True)

            self.assertEqual(sync_code, 0, synchronized)
            self.assertEqual(synchronized["sources"][0]["resolved_revision"], moved)
            # The sync offered the commit and applied nothing: the delivered bytes are the ones
            # reviewed at install, and the record still names the revision they came from.
            self.assertEqual(delivered.read_text(encoding="utf-8"), SKILL_BODY)

            review_code, review = env.run(
                "marketplace", "update", COORDINATE, "--profile", "claude"
            )

            self.assertEqual(review_code, 0, review)
            self.assertFalse(review["finalized"])
            self.assertEqual(review["review"]["items"][0]["key"], "company/skill/code-review@1.3.0")
            self.assertEqual(delivered.read_text(encoding="utf-8"), SKILL_BODY)

            update_code, updated = env.run(
                "marketplace",
                "update",
                COORDINATE,
                "--profile",
                "claude",
                "--expect",
                review["review_digest"],
                "--yes",
            )

            self.assertEqual(update_code, 0, updated)
            self.assertTrue(updated["finalized"])
            self.assertEqual(delivered.read_text(encoding="utf-8"), UPDATED_SKILL_BODY)
            self.assertEqual(updated["receipt"]["artifacts"][0]["source_revision"], moved)

            # Both revisions are real, distinct and durable: the audit trail remembers the commit
            # each installation came from, which is the whole point of recording one.
            persisted = LocalReceiptStore(str(Path(env.paths.data_root) / "state")).actions()
            self.assertIsInstance(persisted, Ok, persisted)
            assert isinstance(persisted, Ok)
            recorded = [
                item.artifacts[0].source_revision for item in persisted.value if item.artifacts
            ]
            self.assertEqual(recorded[0], moved)
            self.assertIn(installed_revision, recorded)


if __name__ == "__main__":
    unittest.main()
