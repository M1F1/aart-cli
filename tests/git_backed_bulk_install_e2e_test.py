"""CP-17 step 5: more than one artifact, out of one real commit, in one confirmed run.

Every other Git-backed test in this slice installs a single artifact. What is unproven there is
that a run installing several of them keeps each one's kind straight -- an MCP server that has to
be built into a runtime and a Skill that only has to be placed where a harness reads it are
different installations, and a bulk run that treated them alike would either build a runtime for
the Skill or place the server's files and never make it startable.

`CollectionsAreReachableTest` covers the Collection half: an approved Collection is offered by the
configured Marketplace.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.git_backed_consumer_e2e_test import _Environment
from tests.git_backed_runtime_e2e_test import AUTHORED_SERVER
from tests.mcp_stdio_e2e_test import speak
from tests.placed_installation_e2e_test import AUTHORED_SKILL

#: A Collection naming both members, authored without a version like any source manifest.
AUTHORED_STARTER: tuple[tuple[str, str], ...] = (
    (
        "collections/starter/aart-cli.json",
        json.dumps(
            {
                "schema": "aart-cli.dev/collection/v1",
                "name": "starter",
                "summary": "Notes and code review.",
                "artifacts": ["mcp/notes@^1", "skill/code-review@^1"],
            }
        ),
    ),
)

SERVER = "company/mcp/notes"
SKILL = "company/skill/code-review"


class _Chain(unittest.TestCase):
    def _synchronized(self, raw: str):
        env = _Environment(Path(raw).resolve(), AUTHORED_SKILL, AUTHORED_SERVER)
        code, synchronized = env.run("source", "sync", source_transport=True)
        self.assertEqual(0, code, synchronized)
        return env, synchronized["sources"][0]["resolved_revision"]


class BulkInstallFromOneCommitTest(_Chain):
    def _install_both(self, env):
        code, installed = env.run(
            "marketplace", "install", SERVER, SKILL, "--profile", "claude", "--yes"
        )
        self.assertEqual(0, code, installed)
        return installed

    def test_one_run_installs_both_and_each_gets_the_installation_its_kind_needs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._synchronized(raw)

            installed = self._install_both(env)

            self.assertEqual(
                [(item["key"], item["status"]) for item in installed["items"]],
                [
                    ("company/mcp/notes@1.0.0", "completed"),
                    ("company/skill/code-review@1.2.0", "completed"),
                ],
            )
            effects = {
                artifact["coordinate"]: [step["effect"] for step in artifact["steps"]]
                for artifact in installed["receipt"]["artifacts"]
            }
            # The server is built; the Skill is placed. Neither gets the other's installation.
            self.assertEqual(
                effects["company/mcp/notes@1.0.0"],
                ["copy-tree", "create-python-environment", "write-file", "configure-harness"],
            )
            self.assertNotIn(
                "create-python-environment", effects["company/skill/code-review@1.2.0"]
            )
            self.assertNotIn("write-file", effects["company/skill/code-review@1.2.0"])

    def test_both_carry_the_same_real_commit_into_one_receipt(self) -> None:
        """One run, one commit: a bulk install must not resolve its members independently."""

        with tempfile.TemporaryDirectory() as raw:
            env, head = self._synchronized(raw)

            installed = self._install_both(env)

            revisions = {
                artifact["coordinate"]: artifact["source_revision"]
                for artifact in installed["receipt"]["artifacts"]
            }
            self.assertEqual(
                revisions,
                {"company/mcp/notes@1.0.0": head, "company/skill/code-review@1.2.0": head},
            )

    def test_the_server_installed_beside_a_skill_still_starts(self) -> None:
        """The claim the effect list cannot make: the runtime built in a bulk run really runs."""

        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._synchronized(raw)
            self._install_both(env)

            launcher = env.project / ".claude/aart-cli/mcp/company/notes/launch.sh"
            replies = speak(str(launcher), [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])

            self.assertEqual("aart-e2e-github", replies[0]["result"]["serverInfo"]["name"])

    def test_doctor_reports_both_installations_ready(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._synchronized(raw)
            self._install_both(env)

            code, report = env.run("doctor")

            self.assertEqual(0, code, report)
            self.assertTrue(report["ok"])
            self.assertEqual(
                sorted((item["coordinate"], item["health"]) for item in report["items"]),
                [
                    ("company/mcp/notes@1.0.0", "ready"),
                    ("company/skill/code-review@1.2.0", "ready"),
                ],
            )


class CollectionsAreReachableTest(_Chain):
    """An approved Collection is offered by the configured Marketplace (§173.3, B-067 layer 3).

    The Registry here approved both members and then a Collection naming them, through the same
    promotion transaction Maintainer approval runs; nothing in this test hands the Marketplace a
    Collection it did not read from the synchronized commit.
    """

    def _synchronized_with_collection(self, raw: str):
        env = _Environment(Path(raw).resolve(), AUTHORED_SKILL, AUTHORED_SERVER, AUTHORED_STARTER)
        code, synchronized = env.run("source", "sync", source_transport=True)
        self.assertEqual(0, code, synchronized)
        return env

    def test_the_marketplace_offers_the_approved_collection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env = self._synchronized_with_collection(raw)

            code, listed = env.run("marketplace", "list")

            self.assertEqual(0, code, listed)
            self.assertEqual(
                sorted(item["coordinate"] for item in listed["artifacts"]),
                ["company/mcp/notes@1.0.0", "company/skill/code-review@1.2.0"],
            )
            (collection,) = listed["collections"]
            self.assertEqual("company/collection/starter@1.0.0", collection["coordinate"])

    def test_its_members_are_the_exact_versions_their_rows_offer(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env = self._synchronized_with_collection(raw)

            _, listed = env.run("marketplace", "list")

            (collection,) = listed["collections"]
            self.assertEqual(
                ["company/mcp/notes@1.0.0", "company/skill/code-review@1.2.0"],
                collection["members"],
            )

    def test_a_collection_whose_member_moved_past_its_constraint_is_not_offered(self) -> None:
        """The member's row now offers 2.0.0, which `^1` excludes (§173.4).

        Offering the Collection would install a version it never named, so it is declined until a
        new Collection version is approved.
        """

        skill = [list(item) for item in AUTHORED_SKILL]
        manifest = json.loads(skill[0][1])
        manifest["artifact"]["x-fixture-version"] = "2.0.0"
        skill[0][1] = json.dumps(manifest)
        skill[1][1] += "\nA second major version.\n"
        moved = tuple(tuple(item) for item in skill)
        with tempfile.TemporaryDirectory() as raw:
            env = _Environment(
                Path(raw).resolve(), AUTHORED_SKILL, AUTHORED_SERVER, AUTHORED_STARTER, moved
            )
            code, synchronized = env.run("source", "sync", source_transport=True)
            self.assertEqual(0, code, synchronized)

            code, listed = env.run("marketplace", "list")

            self.assertEqual(0, code, listed)
            self.assertEqual([], listed["collections"])
            self.assertIn(
                "company/skill/code-review@2.0.0",
                [item["coordinate"] for item in listed["artifacts"]],
            )

    def test_installing_the_collection_installs_every_member_in_one_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env = self._synchronized_with_collection(raw)

            code, installed = env.run(
                "marketplace",
                "install",
                "company/collection/starter",
                "--profile",
                "claude",
                "--yes",
            )

            self.assertEqual(0, code, installed)
            self.assertEqual(
                sorted(item["coordinate"] for item in installed["receipt"]["artifacts"]),
                ["company/mcp/notes@1.0.0", "company/skill/code-review@1.2.0"],
            )

    def test_an_exact_collection_version_selects_that_version(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env = self._synchronized_with_collection(raw)

            code, installed = env.run(
                "marketplace",
                "install",
                "company/collection/starter@1.0.0",
                "--profile",
                "claude",
                "--yes",
            )

            self.assertEqual(0, code, installed)
            self.assertEqual(2, len(installed["receipt"]["artifacts"]))

    def test_an_unapproved_collection_version_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env = self._synchronized_with_collection(raw)

            code, refused = env.run(
                "marketplace",
                "install",
                "company/collection/starter@9.0.0",
                "--profile",
                "claude",
                "--yes",
            )

            self.assertNotEqual(0, code, refused)
            code, listed = env.run("doctor")
            self.assertEqual(0, code, listed)
            self.assertEqual([], listed["items"])

    def test_a_harness_that_cannot_host_every_member_installs_none_of_them(self) -> None:
        """A Collection is one artifact on 05 (D-422): no member is installed without the rest."""

        with tempfile.TemporaryDirectory() as raw:
            env = self._synchronized_with_collection(raw)

            code, refused = env.run(
                "marketplace",
                "install",
                "company/collection/starter",
                "--profile",
                "codex",
                "--yes",
            )

            self.assertNotEqual(0, code, refused)
            code, listed = env.run("doctor")
            self.assertEqual(0, code, listed)
            self.assertEqual([], listed["items"])

    def test_a_registry_that_approved_no_collection_offers_none(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._synchronized(raw)

            code, listed = env.run("marketplace", "list")

            self.assertEqual(0, code, listed)
            self.assertEqual([], listed["collections"])
