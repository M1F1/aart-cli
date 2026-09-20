"""CP-26.20: a Registry read out of a repository already on this machine (D-350, B-143).

The author flow this exists for: commit the canonical artifact to a branch of a Registry
repository you have checked out, add that repository and that branch under an alias, install from
it exactly as from any Registry, and smoke-test the installation before anything is published
anywhere. Nothing about admission, projection, resolution or installation is special-cased for it;
what is special is the promise about which bytes it reads.

That promise is what this module holds. The repository here has three different answers in it at
once -- one branch's committed content, another branch's, and an uncommitted edit in the worktree
-- and only one of them may ever be installed: the committed content of the branch that was named.
The other two exist in the fixture precisely so that a reader who confuses them has a failing test
rather than a surprise.
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
from aart_cli.configuration.model import SyncSettings, UserConfiguration
from aart_cli.configuration.paths import Platform, resolve_config_paths
from aart_cli.configuration.schema import user_configuration_bytes
from aart_cli.sources.git import acquire_git_snapshot
from tests.configured_update_command_e2e_test import (
    AUTHORED_SKILL_1_3_0,
    UPDATED_SKILL_BODY,
    _authored,
)
from tests.git_backed_consumer_e2e_test import _git, _materialize, _registry_snapshot
from tests.placed_installation_e2e_test import AUTHORED_SKILL, SKILL_BODY, as_delivered

COORDINATE = "company/skill/code-review"
ALIAS = "local-registry"
BRANCH = "test/candidate"

#: The same Registry reached the ordinary way, under an alias of its own (D-350).
REMOTE_ALIAS = "company"
REMOTE_LOCATION = "https://registry.example.test/agents/registry.git"

#: What the worktree holds, committed to no branch. It is a whole extra Registry version, not a
#: stray character, so installing it would be unmistakable rather than a digest that looks wrong.
WORKTREE_BODY = "# Code review\n\nUncommitted: never install this.\n"

#: What the selected branch gains when a test advances it, so that adopting the successor and
#: failing to adopt one are told apart by the version offered rather than by a digest.
SUCCESSOR_BODY = "# Code review\n\nRead reference/style.md, then say what to change.\n"
AUTHORED_SKILL_1_4_0 = _authored("1.4.0", SUCCESSOR_BODY)


class _Checkout:
    """A real Registry repository with a branch, another branch, and a dirty worktree."""

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
        _git(self.repository, "add", ".")
        _git(self.repository, "commit", "-m", "approved registry")
        self.main = _git(self.repository, "rev-parse", "HEAD")

        _git(self.repository, "checkout", "-b", BRANCH)
        self._write(AUTHORED_SKILL_1_3_0)
        _git(self.repository, "add", "-A")
        _git(self.repository, "commit", "-m", "candidate under review")
        self.branch = _git(self.repository, "rev-parse", "HEAD")

        # Back where somebody works, with an edit they have not committed. Both halves matter: the
        # checked-out branch is not the selected one, and the files on disk are not any branch's.
        _git(self.repository, "checkout", "main")
        self.document = next(self.repository.rglob("payload/SKILL.md"))
        self.document.write_text(WORKTREE_BODY, encoding="utf-8")
        self.dirty = _git(self.repository, "status", "--porcelain")

        self.xdg = {"HOME": str(self.home), "AART_CLI_HOME": str(self.home / ".aart-cli")}
        platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
        self.paths = resolve_config_paths(
            platform, home=str(self.home), application_home=self.xdg["AART_CLI_HOME"]
        )
        config_path = Path(self.paths.user_config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(
            user_configuration_bytes(UserConfiguration(1, (), None, SyncSettings()))
        )

    def commit_to_branch(self, authored, message: str = "successor") -> str:
        """Move the selected branch on, leaving the checked-out branch and the worktree alone.

        A second worktree, not `git checkout`: the branch this fixture selects is deliberately not
        the one checked out, and the checked-out one deliberately has an uncommitted edit in it.
        Switching branches to commit would destroy both halves of what the tests here assert.
        """

        work = self.root / "advance"
        _git(self.repository, "worktree", "add", str(work), BRANCH)
        try:
            for path in work.iterdir():
                if path.name == ".git":
                    continue
                shutil.rmtree(path) if path.is_dir() else path.unlink()
            if authored is None:
                (work / "registry").mkdir()
                (work / "registry" / "versions").mkdir()
                (work / "registry" / "versions" / "not-a-version.json").write_text(
                    "{ not json", encoding="utf-8"
                )
            else:
                _materialize(work, _registry_snapshot(authored))
            _git(work, "add", "-A")
            _git(work, "commit", "-m", message)
            self.branch = _git(self.repository, "rev-parse", BRANCH)
        finally:
            _git(self.repository, "worktree", "remove", "--force", str(work))
        return self.branch

    def _write(self, authored) -> None:
        for path in self.repository.iterdir() if self.repository.exists() else ():
            if path.name == ".git":
                continue
            shutil.rmtree(path) if path.is_dir() else path.unlink()
        _materialize(self.repository, _registry_snapshot(authored))

    def add(self, *extra: str):
        return self.run(
            "source",
            "add",
            "--alias",
            ALIAS,
            "--kind",
            "registry-local",
            "--location",
            str(self.repository),
            "--ref",
            BRANCH,
            "--default",
            *extra,
        )

    def add_remote(self, alias: str = REMOTE_ALIAS):
        """The same Registry again, as an ordinary remote one, under an alias of its own.

        It is the same repository on purpose: D-350 allows a local checkout and a remote
        connection to one Registry to coexist *only* under distinct aliases, and the way to prove
        that is to have both of them answer for the same content at once.
        """

        return self.run(
            "source",
            "add",
            "--alias",
            alias,
            "--kind",
            "registry-git",
            "--location",
            REMOTE_LOCATION,
            "--ref",
            "main",
            source_transport=True,
        )

    def forget_the_default_registry(self) -> None:
        """Leave the configured registries in place and name none of them the default.

        `source add` makes the first registry the default, and a default registry is the answer to
        "which one did you mean" -- so a configuration that has none is the only one in which the
        question is still open. The schema has always allowed it; this reaches it the way a person
        editing their own configuration file would.
        """

        config_path = Path(self.paths.user_config_file)
        configuration = json.loads(config_path.read_text(encoding="utf-8"))
        configuration.pop("default_registry")
        config_path.write_text(json.dumps(configuration), encoding="utf-8")

    def _transport(self, request):
        """Stand in for the network the remote alias would otherwise need.

        Only for the remote one: the local alias reaches the same repository under the production
        verdict, and substituting its request would prove nothing about it.
        """

        if request.allow_local_transport:
            return acquire_git_snapshot(request)
        if request.location != REMOTE_LOCATION or request.ref_is_branch:
            raise AssertionError(f"remote sync weakened its transport request: {request!r}")
        return acquire_git_snapshot(
            replace(request, location=self.repository.as_uri(), allow_local_transport=True)
        )

    def run(self, *argv: str, source_transport: bool = False):
        arguments = [*argv, "--json"]
        if argv[:2] == ("marketplace", "install"):
            arguments.extend(("--project", str(self.project)))
        output = io.StringIO()
        transport = (
            mock.patch("aart_cli.sources.runtime.acquire_git_snapshot", side_effect=self._transport)
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

    #: What this installation is called where it was delivered: the artifact, the alias it was
    #: configured under, and the scope (§169.7). The alias is part of it, so a local checkout and a
    #: remote connection to one Registry deliver into directories of their own (D-350).
    DELIVERED_NAME = f"code-review-{ALIAS}-project"

    @property
    def delivered(self) -> Path:
        return self.project / f".claude/skills/{self.DELIVERED_NAME}/SKILL.md"

    def installations(self) -> list[Path]:
        """Every installation record this machine kept, one file per installation (§169.3)."""

        return sorted((self.home / ".aart-cli/state/installations").glob("*.json"))

    def heads(self) -> dict[str, str]:
        listed = _git(
            self.repository, "for-each-ref", "--format=%(refname:short)=%(objectname)", "refs/heads"
        )
        return dict(line.split("=", 1) for line in listed.splitlines() if line)

    def untouched(self, test: unittest.TestCase, *, branches: dict[str, str] | None = None) -> None:
        """The checkout is somebody's working repository, and reading it must not be felt.

        `branches` is what the repository's own history is expected to be, for the tests that moved
        it themselves; the default is that nothing moved. Reading a Registry never moves it either
        way -- that is the whole claim -- so a test that advanced or deleted a branch still asserts
        the rest of this, and says which change was its own.
        """

        test.assertEqual(_git(self.repository, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        test.assertEqual(_git(self.repository, "status", "--porcelain"), self.dirty)
        test.assertEqual(self.document.read_text(encoding="utf-8"), WORKTREE_BODY)
        test.assertEqual(
            self.heads(), {"main": self.main, BRANCH: self.branch} if branches is None else branches
        )


@contextlib.contextmanager
def _checkout():
    with tempfile.TemporaryDirectory() as raw:
        yield _Checkout(Path(raw).resolve())


class LocalRegistryCheckoutTest(unittest.TestCase):
    def test_adding_it_resolves_the_named_branch_to_its_exact_commit(self) -> None:
        with _checkout() as env:
            code, added = env.add()

            self.assertEqual(code, 0, added)
            self.assertEqual(added["source"]["kind"], "registry-local")
            self.assertEqual(added["source"]["ref"], BRANCH)
            self.assertEqual(added["sync"]["resolved_revision"], env.branch)
            self.assertNotEqual(env.branch, env.main)
            env.untouched(self)

    def test_it_reads_the_branch_that_was_named_and_not_the_one_checked_out(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)

            code, listed = env.run("marketplace", "list")

            self.assertEqual(code, 0, listed)
            # 1.3.0 is the candidate branch; 1.2.0 is what `main` holds and what the worktree was
            # built from. Offering either of those would be reading something nobody selected.
            self.assertEqual(
                [item["coordinate"] for item in listed["artifacts"]],
                [f"{ALIAS}/skill/code-review@1.3.0"],
            )

    def test_installing_from_it_delivers_the_committed_body_not_the_edited_one(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)

            code, installed = env.run(
                "marketplace",
                "install",
                f"{ALIAS}/skill/code-review",
                "--profile",
                "claude",
                "--yes",
            )

            self.assertEqual(code, 0, installed)
            delivered = env.delivered.read_text(encoding="utf-8")
            self.assertEqual(delivered, as_delivered(UPDATED_SKILL_BODY, env.DELIVERED_NAME))
            self.assertNotIn("Uncommitted", delivered)
            self.assertNotEqual(delivered, as_delivered(SKILL_BODY, env.DELIVERED_NAME))
            env.untouched(self)

    def _offered(self, env) -> list[str]:
        code, listed = env.run("marketplace", "list")
        self.assertEqual(code, 0, listed)
        return [item["coordinate"] for item in listed["artifacts"]]

    def test_an_advanced_branch_is_adopted_by_an_explicit_sync(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            before = env.branch
            successor = env.commit_to_branch(AUTHORED_SKILL_1_4_0)

            self.assertNotEqual(successor, before)
            code, synchronized = env.run("source", "sync", "--alias", ALIAS)

            self.assertEqual(code, 0, synchronized)
            self.assertEqual(synchronized["sources"][0]["resolved_revision"], successor)
            self.assertEqual(self._offered(env), [f"{ALIAS}/skill/code-review@1.4.0"])
            env.untouched(self)

    def test_a_deleted_branch_keeps_the_last_snapshot_that_validated(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            _git(env.repository, "branch", "-D", BRANCH)

            code, synchronized = env.run("source", "sync", "--alias", ALIAS)

            self.assertEqual(code, 1, synchronized)
            self.assertFalse(synchronized["sources"][0]["ok"])
            # The branch is gone, so there is nothing to advance to -- and nothing is lost either.
            self.assertEqual(self._offered(env), [f"{ALIAS}/skill/code-review@1.3.0"])
            env.untouched(self, branches={"main": env.main})

    def test_a_tag_named_like_the_branch_does_not_stand_in_for_it(self) -> None:
        """A branch was selected, so only that branch may answer for it (D-350).

        `registry-git` resolves an unqualified ref as a branch *or* a tag, which is the right
        reading of a ref somebody typed. Here it is the wrong one: the configured field is the
        branch, and a tag silently answering in its place is exactly the fallback that would turn
        "the branch you selected is gone" into "here is something else, installed".
        """

        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            _git(env.repository, "branch", "-D", BRANCH)
            _git(env.repository, "tag", BRANCH, "main")

            code, synchronized = env.run("source", "sync", "--alias", ALIAS)

            self.assertEqual(code, 1, synchronized)
            self.assertEqual(self._offered(env), [f"{ALIAS}/skill/code-review@1.3.0"])
            self.assertNotIn("@1.2.0", " ".join(self._offered(env)))
            env.untouched(self, branches={"main": env.main})

    def test_an_invalid_registry_on_the_branch_keeps_the_last_snapshot_that_validated(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            good = env.branch
            broken = env.commit_to_branch(None, "not a registry")

            code, synchronized = env.run("source", "sync", "--alias", ALIAS)

            self.assertEqual(code, 1, synchronized)
            self.assertNotEqual(broken, good)
            self.assertEqual(self._offered(env), [f"{ALIAS}/skill/code-review@1.3.0"])
            env.untouched(self)

    def test_the_same_registry_reached_both_ways_is_two_rows_under_two_aliases(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            code, added = env.add_remote()

            self.assertEqual(code, 0, added)
            # One repository, two connections, two names -- and each one offers what its own ref
            # holds: the candidate branch's 1.3.0 and `main`'s 1.2.0.
            self.assertEqual(
                sorted(self._offered(env)),
                [
                    f"{REMOTE_ALIAS}/skill/code-review@1.2.0",
                    f"{ALIAS}/skill/code-review@1.3.0",
                ],
            )

    def test_an_alias_qualified_install_takes_the_registry_it_names(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            self.assertEqual(env.add_remote()[0], 0)

            code, installed = env.run(
                "marketplace",
                "install",
                f"{REMOTE_ALIAS}/skill/code-review",
                "--profile",
                "claude",
                "--yes",
                source_transport=True,
            )

            self.assertEqual(code, 0, installed)
            # The alias picked the registry, and the registry picked the version: `main`'s 1.2.0,
            # not the candidate branch's 1.3.0 that the other alias offers for the same identity.
            delivered = env.project / f".claude/skills/code-review-{REMOTE_ALIAS}-project/SKILL.md"
            self.assertEqual(delivered.read_text(encoding="utf-8"), as_delivered(SKILL_BODY))
            self.assertFalse(env.delivered.exists())

    def test_an_unqualified_install_of_what_both_offer_is_refused_as_ambiguous(self) -> None:
        """With no default registry named, one identity offered twice is a question, not a pick.

        The default is deliberately left off: a configured default registry *is* the answer to
        this question, and a test that had one would be proving the default works rather than that
        an unqualified match across two aliases is ambiguous.
        """

        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            self.assertEqual(env.add_remote()[0], 0)
            env.forget_the_default_registry()

            code, installed = env.run(
                "marketplace",
                "install",
                "skill/code-review",
                "--profile",
                "claude",
                "--yes",
                source_transport=True,
            )

            self.assertNotEqual(code, 0, installed)
            rendered = json.dumps(installed)
            self.assertIn(ALIAS, rendered)
            self.assertIn(REMOTE_ALIAS, rendered)
            self.assertFalse(env.delivered.exists())

    def test_update_through_the_local_alias_converges_on_the_branch_successor(self) -> None:
        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            code, installed = env.run(
                "marketplace",
                "install",
                f"{ALIAS}/skill/code-review",
                "--profile",
                "claude",
                "--yes",
            )
            self.assertEqual(code, 0, installed)
            env.commit_to_branch(AUTHORED_SKILL_1_4_0)
            self.assertEqual(env.run("source", "sync", "--alias", ALIAS)[0], 0)

            code, updated = env.run(
                "marketplace",
                "update",
                f"{ALIAS}/skill/code-review",
                "--profile",
                "claude",
                "--yes",
            )

            self.assertEqual(code, 0, updated)
            self.assertEqual(updated["items"][0]["key"], f"{ALIAS}/skill/code-review@1.4.0")
            self.assertEqual(
                env.delivered.read_text(encoding="utf-8"),
                as_delivered(SUCCESSOR_BODY, env.DELIVERED_NAME),
            )
            env.untouched(self)

    def test_the_same_artifact_through_two_aliases_is_two_installations(self) -> None:
        """One harness, one scope, one artifact, two Registries -- and two of everything (§169.3).

        This is what keeps a candidate being tested from a checkout and the published one from the
        remote apart on one machine: not a warning, but two installations, each with its own tree,
        its own delivered name and its own key -- which is what its configuration and its
        credential are addressed by.
        """

        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            self.assertEqual(env.add_remote()[0], 0)

            for alias in (ALIAS, REMOTE_ALIAS):
                code, installed = env.run(
                    "marketplace",
                    "install",
                    f"{alias}/skill/code-review",
                    "--profile",
                    "claude",
                    "--yes",
                    source_transport=True,
                )
                self.assertEqual(code, 0, installed)

            code, status = env.run("marketplace", "status", "--profile", "claude")
            self.assertEqual(code, 0, status)
            self.assertEqual(
                sorted(item["key"] for item in status["items"]),
                [f"{REMOTE_ALIAS}/skill/code-review@1.2.0", f"{ALIAS}/skill/code-review@1.3.0"],
            )
            records = [json.loads(item.read_text(encoding="utf-8")) for item in env.installations()]
            self.assertEqual(
                sorted(item["receipt"]["owner"]["source"] for item in records),
                [REMOTE_ALIAS, ALIAS],
            )
            # Two trees and two delivered names, so neither installation can overwrite the other.
            self.assertEqual(len({item["receipt"]["root"] for item in records}), 2)
            deliveries = [item["receipt"]["deliveries"][0] for item in records]
            self.assertEqual(len({item["destination"] for item in deliveries}), 2)

    def test_what_it_was_installed_from_is_all_recorded(self) -> None:
        """Alias, branch, origin, commit and snapshot -- every one of them readable afterwards."""

        with _checkout() as env:
            self.assertEqual(env.add()[0], 0)
            code, installed = env.run(
                "marketplace",
                "install",
                f"{ALIAS}/skill/code-review",
                "--profile",
                "claude",
                "--yes",
            )
            self.assertEqual(code, 0, installed)

            code, listed = env.run("source", "list")
            self.assertEqual(code, 0, listed)
            source = listed["sources"][0]
            record = json.loads(env.installations()[0].read_text(encoding="utf-8"))

            # The installation names the alias and the exact commit it was built from; the alias
            # names the connection, and the connection names where and what was read.
            self.assertEqual(record["coordinate"]["source"], ALIAS)
            self.assertEqual(installed["receipt"]["artifacts"][0]["source_revision"], env.branch)
            self.assertEqual(source["alias"], ALIAS)
            self.assertEqual(source["kind"], "registry-local")
            self.assertEqual(source["location"], str(env.repository))
            self.assertEqual(source["ref"], BRANCH)
            self.assertEqual(source["resolved_revision"], env.branch)
            self.assertTrue(source["snapshot_digest"].startswith("sha256:"))

    def test_it_reaches_no_network_because_the_repository_has_no_remote_to_reach(self) -> None:
        """The strongest honest form of "performs no network operation".

        A claim about what a subprocess did not do cannot be made from inside this process. What
        can be shown is that there was nothing to do it to: the repository this reads has no
        configured remote and no URL anywhere in its configuration, so every object the snapshot
        is built from came off this filesystem.
        """

        with _checkout() as env:
            self.assertEqual(_git(env.repository, "remote"), "")

            code, added = env.add()

            self.assertEqual(code, 0, added)
            self.assertEqual(added["sync"]["resolved_revision"], env.branch)
            self.assertNotIn("://", json.dumps(added["source"]))


if __name__ == "__main__":
    unittest.main()
