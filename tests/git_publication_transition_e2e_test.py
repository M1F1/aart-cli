"""CP-19 step 8: merging into the consumer-visible branch is what publishes a promotion (QA-034).

A maintainer's promotion writes `promoted-local` and stops there, because publication is a Git
review and merge that AART deliberately does not perform (INV-241, INV-242).  Nothing afterwards
rewrites that record: the merge moves a commit, not the bytes inside it.  So the fixtures that
build a registry out of already-published records prove only that a consumer can read one; what is
proved here is the transition itself, over an actual branch, merge and public sync.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from aart_cli import cli
from aart_cli.application.promotion import (
    load_published_registry_versions,
    load_registry_versions,
)
from aart_cli.configuration.model import (
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from aart_cli.configuration.paths import Platform, resolve_config_paths
from aart_cli.configuration.schema import user_configuration_bytes
from aart_cli.domain.registry import PublicationStage
from aart_cli.domain.result import Ok
from aart_cli.protocol.native_tree import SnapshotEntry, SourceSnapshot
from aart_cli.sources.git import acquire_git_snapshot
from aart_cli.sources.model import GitSnapshotRequest
from tests.configured_installation_draft_e2e_test import _promoted_local_registries
from tests.configured_update_command_e2e_test import (
    AUTHORED_SKILL_1_3_0,
    UPDATED_SKILL_BODY,
)
from tests.git_backed_consumer_e2e_test import _git, _materialize
from tests.marketplace_fixtures import configured_source
from tests.placed_installation_e2e_test import AUTHORED_SKILL, SKILL_BODY
from tests.registry_maintenance_fixtures import empty_registry_snapshot

COORDINATE = "company/skill/code-review"
REVIEW_BRANCH = "qa/publish-v1"


def _promoted_local_registry(*authored) -> SourceSnapshot:
    """The registry exactly as the maintainer's own machine leaves it, markers and all."""

    markers = tuple(
        SnapshotEntry(
            entry.path,
            entry.kind,
            entry.content.replace(b"test-registry", b"company-registry"),
            entry.executable,
        )
        for entry in empty_registry_snapshot().entries
    )
    promoted = _promoted_local_registries(*authored)
    return SourceSnapshot(promoted.origin, (*markers, *promoted.entries))


class _PublicationLab:
    """One registry repository whose `main` a consumer reads and whose branch awaits review."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.project = root / "project"
        self.repository = root / "registry"
        self.home.mkdir()
        self.project.mkdir()

        self._write(AUTHORED_SKILL)
        _git(self.repository, "init", "-b", "main")
        _git(self.repository, "config", "user.email", "test@example.invalid")
        _git(self.repository, "config", "user.name", "AART Test")
        _git(self.repository, "add", "-A")
        _git(self.repository, "commit", "-m", "promote code-review 1.2.0")

        # The second promotion is where a real maintainer leaves it: committed on its own branch,
        # pushed for review, and not yet part of what any consumer is configured to read.
        _git(self.repository, "checkout", "-b", REVIEW_BRANCH)
        self._write(AUTHORED_SKILL, AUTHORED_SKILL_1_3_0)
        _git(self.repository, "add", "-A")
        _git(self.repository, "commit", "-m", "promote code-review 1.3.0")
        _git(self.repository, "checkout", "main")
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
        configuration = UserConfiguration(1, (self.source,), self.source.alias, SyncSettings())
        config_path = Path(self.paths.user_config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(user_configuration_bytes(configuration))

    def _write(self, *authored) -> None:
        for path in list(self.repository.iterdir()) if self.repository.exists() else ():
            if path.name == ".git":
                continue
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        _materialize(self.repository, _promoted_local_registry(*authored))

    def merge_the_review_branch(self) -> str:
        """What a reviewer does in the Git host, and the only publication step there is."""

        _git(self.repository, "merge", "--no-ff", "-m", "Merge registry review", REVIEW_BRANCH)
        self.head = _git(self.repository, "rev-parse", "HEAD")
        return self.head

    def version_record(self, version: str) -> dict:
        path = self.repository / "registry/versions/skill/code-review" / f"{version}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _local_transport(self, request: GitSnapshotRequest):
        if request.location != self.source.location or request.allow_local_transport:
            raise AssertionError(f"public sync weakened its transport request: {request!r}")
        return acquire_git_snapshot(
            replace(request, location=self.repository.as_uri(), allow_local_transport=True)
        )

    def run(self, *argv: str, source_transport: bool = False):
        arguments = [*argv, "--json"]
        if argv[:2] == ("marketplace", "install"):
            arguments.extend(("--project", str(self.project)))
        output = io.StringIO()
        transport = (
            mock.patch(
                "aart_cli.sources.runtime.acquire_git_snapshot",
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


class GitPublicationTransitionE2ETest(unittest.TestCase):
    def test_a_merged_promotion_is_offered_and_installable_without_being_relabeled(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = _PublicationLab(Path(raw).resolve())

            code, synchronized = lab.run("source", "sync", source_transport=True)
            self.assertEqual(code, 0, synchronized)
            self.assertEqual(synchronized["sources"][0]["resolved_revision"], lab.head)

            code, before = lab.run("marketplace", "list")

            self.assertEqual(code, 0, before)
            # The promotion on `main` is what this consumer was configured to read, so it is
            # published to them -- and the one still awaiting review is not.
            self.assertEqual(
                [item["coordinate"] for item in before["artifacts"]],
                ["company/skill/code-review@1.2.0"],
            )

            merged = lab.merge_the_review_branch()
            code, resynchronized = lab.run("source", "sync", source_transport=True)

            self.assertEqual(code, 0, resynchronized)
            self.assertEqual(resynchronized["sources"][0]["resolved_revision"], merged)

            code, after = lab.run("marketplace", "list")

            self.assertEqual(code, 0, after)
            self.assertEqual(
                [item["coordinate"] for item in after["artifacts"]],
                ["company/skill/code-review@1.3.0"],
            )

            code, installed = lab.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, installed)
            self.assertEqual(
                (lab.project / ".claude/skills/code-review/SKILL.md").read_text(encoding="utf-8"),
                UPDATED_SKILL_BODY,
            )
            self.assertEqual(installed["receipt"]["artifacts"][0]["source_revision"], merged)

            # The merge published the promotion by making it reachable. It did not, and could not,
            # edit the record the maintainer wrote and reviewers approved.
            self.assertEqual(lab.version_record("1.3.0")["publication"], "promoted-local")
            self.assertEqual(lab.version_record("1.2.0")["publication"], "promoted-local")

    def test_an_unreviewed_promotion_is_not_installable_from_the_configured_branch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            lab = _PublicationLab(Path(raw).resolve())
            delivered = lab.project / ".claude/skills/code-review/SKILL.md"
            lab.run("source", "sync", source_transport=True)

            code, refused = lab.run(
                "marketplace", "install", f"{COORDINATE}@1.3.0", "--profile", "claude", "--yes"
            )

            self.assertNotEqual(code, 0, refused)
            self.assertFalse(delivered.exists())

            # The version that is on the configured branch installs from the same command, so the
            # refusal above is review not having happened, not the lab being broken.
            code, installed = lab.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, installed)
            self.assertEqual(delivered.read_text(encoding="utf-8"), SKILL_BODY)


class PublishedRegistryVersionLoaderTest(unittest.TestCase):
    """The two readings of one snapshot: the maintainer's workspace and a consumer's branch."""

    def test_a_consumer_read_publishes_what_a_maintainer_read_leaves_local(self) -> None:
        snapshot = _promoted_local_registry(AUTHORED_SKILL)

        local = load_registry_versions(snapshot)
        published = load_published_registry_versions(snapshot)

        self.assertIsInstance(local, Ok, local)
        self.assertIsInstance(published, Ok, published)
        assert isinstance(local, Ok) and isinstance(published, Ok)
        self.assertEqual(
            [item.publication for item in local.value],
            [PublicationStage.PROMOTED_LOCAL],
        )
        self.assertEqual(
            [item.publication for item in published.value],
            [PublicationStage.PUBLISHED],
        )
        self.assertEqual(
            [replace(item, publication=PublicationStage.PUBLISHED) for item in local.value],
            list(published.value),
        )

    def test_an_unreadable_registry_is_still_refused_rather_than_published(self) -> None:
        broken = _promoted_local_registry(AUTHORED_SKILL)
        entries = tuple(
            SnapshotEntry(entry.path, entry.kind, b"{", entry.executable)
            if str(entry.path).startswith("registry/versions/")
            else entry
            for entry in broken.entries
        )

        loaded = load_published_registry_versions(SourceSnapshot(broken.origin, entries))

        self.assertNotIsInstance(loaded, Ok, loaded)


if __name__ == "__main__":
    unittest.main()
