"""CP-17 step 5: more than one artifact, out of one real commit, in one confirmed run.

Every other Git-backed test in this slice installs a single artifact. What is unproven there is
that a run installing several of them keeps each one's kind straight -- an MCP server that has to
be built into a runtime and a Skill that only has to be placed where a harness reads it are
different installations, and a bulk run that treated them alike would either build a runtime for
the Skill or place the server's files and never make it startable.

The collection half of this step is a refusal rather than an installation, and
`CollectionsAreNotReachableTest` pins why.
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

            launcher = env.project / ".agent-artifacts/runtimes/company/mcp/notes/launch.sh"
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


class CollectionsAreNotReachableTest(_Chain):
    """A Collection cannot be installed through the CLI, and this is where that stops.

    `io/configured_selection.py` skips every approved version whose kind is `collection` and leaves
    `ApprovedRegistrySnapshot.collections` at its default, so the configured Marketplace the public
    verbs read carries none regardless of what a registry approved. The domain models Collections
    and the resolver has a code for missing ones; nothing on this path can ever populate them.

    Pinned rather than fixed because it is a capability question, not a defect in this slice's
    chain -- B-067 carries it. The value of the test is that the gap stays a refusal: it must not
    become a partial install of some members, and it must not silently succeed.
    """

    def test_the_marketplace_offers_no_collections_whatever_was_published(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._synchronized(raw)

            code, listed = env.run("marketplace", "list")

            self.assertEqual(0, code, listed)
            # Both members are offered, so the source really is carrying installable content.
            self.assertEqual(
                sorted(item["coordinate"] for item in listed["artifacts"]),
                ["company/mcp/notes@1.0.0", "company/skill/code-review@1.2.0"],
            )
            self.assertEqual([], listed["collections"])

    def test_installing_a_collection_is_refused_by_name_and_installs_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env, _ = self._synchronized(raw)

            code, refused = env.run(
                "marketplace",
                "install",
                "company/collection/starter",
                "--profile",
                "claude",
                "--yes",
            )

            self.assertEqual(1, code)
            self.assertFalse(refused["ok"])
            (diagnostic,) = refused["diagnostics"]
            self.assertEqual("collection-not-found", diagnostic["code"])
            # Nothing was installed, and no harness was touched on the way to the refusal.
            self.assertFalse((env.project / ".agent-artifacts/runtimes").exists())
            mcp = env.project / ".mcp.json"
            self.assertEqual(
                {}, json.loads(mcp.read_text()).get("mcpServers", {}) if mcp.exists() else {}
            )
