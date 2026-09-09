"""`QA-012`/`B-086`: Codex is a measured harness, not an alias for Claude.

Every claim here was observed against Codex CLI 0.152.0 on the acceptance machine, and the last
test in this file re-runs that observation whenever a Codex is installed. That matters more than
usual: `domain/harness.py` exists to hold locations somebody looked at, and a table row whose only
evidence is another harness's layout is exactly what it refuses to carry.

How the rows below were measured, so the next person can repeat it rather than trust it:

    codex debug prompt-input          # renders the model-visible prompt, naming every skill root
    codex mcp list                    # names the servers Codex would start, and from where

Both read configuration and neither contacts the network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.harness import (
    McpEditor,
    Scope,
    delivery_destination,
    delivery_target,
    mcp_target,
    memory_target,
)

SKILL_DOCUMENT = """---
name: {name}
description: probe skill written by the AART test suite
---

body
"""


class CodexDeliveryTargetTest(unittest.TestCase):
    def test_a_project_skill_is_delivered_into_codex_own_skills_root(self) -> None:
        target = delivery_target("codex", Scope.PROJECT, ArtifactKind.SKILL)

        self.assertEqual(target.destination, ".codex/skills/<name>")
        self.assertIs(target.delivery, DeliveryKind.TREE)
        self.assertEqual(delivery_destination(target, "verification"), ".codex/skills/verification")

    def test_a_user_skill_is_delivered_into_the_codex_home_skills_root(self) -> None:
        target = delivery_target("codex", Scope.USER, ArtifactKind.SKILL)

        self.assertEqual(target.destination, ".codex/skills/<name>")
        self.assertIs(target.delivery, DeliveryKind.TREE)

    def test_codex_is_not_an_alias_for_claude(self) -> None:
        """The whole point of the slice. Two harnesses that read different directories are two
        harnesses, and installing into Claude's would install nothing Codex can see."""

        codex = delivery_target("codex", Scope.PROJECT, ArtifactKind.SKILL)
        claude = delivery_target("claude", Scope.PROJECT, ArtifactKind.SKILL)

        self.assertNotEqual(codex.destination, claude.destination)
        self.assertNotEqual(
            memory_target("codex", Scope.PROJECT).destination,
            memory_target("claude", Scope.PROJECT).destination,
        )

    def test_codex_documents_no_guideline_directory_of_its_own(self) -> None:
        """A measured absence. Codex reads skills and `AGENTS.md`; it names no separate guidelines
        location, and inventing one would deliver a file nothing reads."""

        with self.assertRaises(KeyError) as refused:
            delivery_target("codex", Scope.PROJECT, ArtifactKind.GUIDELINE)

        self.assertIn("codex", str(refused.exception))


class CodexMemoryTargetTest(unittest.TestCase):
    def test_project_instructions_are_the_repository_agents_file(self) -> None:
        self.assertEqual(memory_target("codex", Scope.PROJECT).destination, "AGENTS.md")

    def test_user_instructions_live_in_the_codex_home(self) -> None:
        self.assertEqual(memory_target("codex", Scope.USER).destination, ".codex/AGENTS.md")


class CodexUnmeasuredSurfaceTest(unittest.TestCase):
    def test_a_project_scope_mcp_registration_is_still_refused_by_name(self) -> None:
        """`codex mcp add` writes the global configuration and offers no project flag, and a
        project registration would be inert until the operator trusts the project. So there is no
        project row, and asking for one is refused rather than pointed at the user's file (D-196).
        """

        with self.assertRaises(KeyError) as refused:
            mcp_target("codex", Scope.PROJECT)

        self.assertIn("codex", str(refused.exception))

    def test_the_user_scope_row_delegates_rather_than_letting_aart_write_toml(self) -> None:
        """What B-096 was waiting for. AART still does not write this file -- Codex does."""

        target = mcp_target("codex", Scope.USER)

        self.assertIs(McpEditor.HARNESS_COMMAND, target.editor)
        self.assertEqual(".codex/config.toml", target.settings_file)


class CodexIsOfferedByThisMachineTest(unittest.TestCase):
    def test_the_machine_target_names_a_harness_measured_without_an_mcp_row(self) -> None:
        """`B-086`: harness selection came from `MCP_TARGETS` alone, so a harness AART can deliver
        Skills and instructions to was invisible until it also started a server. Codex is measured
        exactly that way, and the set the TUI offers is now every measured table's harness."""

        from agent_artifacts.tui import _canonical_marketplace_target

        target = _canonical_marketplace_target()

        self.assertIn("codex", target.profiles)
        self.assertIn("claude", target.profiles)
        self.assertEqual(tuple(sorted(target.profiles)), target.profiles)


@unittest.skipUnless(shutil.which("codex"), "Codex CLI is not installed on this machine")
class CodexObservationTest(unittest.TestCase):
    """Re-run the measurement the table above records, against the Codex that is installed here.

    Hermetic: a temporary `CODEX_HOME` and a temporary project, so the person's own Codex
    configuration is neither read for the verdict nor written to.
    """

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="aart-codex-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        # `user_root` stands in for the home directory, which is the root AART resolves a
        # user-scope harness path against. Codex reads its own home from `CODEX_HOME`, defaulting
        # to `~/.codex` -- so pointing it at `<user_root>/.codex` is what makes this a measurement
        # of the table's `.codex/...` destinations rather than of an arbitrary directory.
        self.user_root = self.root / "home"
        self.project = self.root / "project"
        for directory in (self.user_root / ".codex", self.project):
            directory.mkdir(parents=True)

    def _skill(self, root: Path, destination: str, name: str) -> None:
        skill = root / destination.replace("<name>", name)
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(SKILL_DOCUMENT.format(name=name), encoding="utf-8")

    def _prompt_input(self) -> str:
        environment = dict(os.environ, CODEX_HOME=str(self.user_root / ".codex"))
        completed = subprocess.run(
            ("codex", "debug", "prompt-input"),
            cwd=str(self.project),
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            self.skipTest(f"codex debug prompt-input is unavailable here: {completed.stderr[:200]}")
        return completed.stdout

    def test_the_measured_skill_roots_are_the_ones_codex_reads(self) -> None:
        project_target = delivery_target("codex", Scope.PROJECT, ArtifactKind.SKILL)
        user_target = delivery_target("codex", Scope.USER, ArtifactKind.SKILL)
        self._skill(self.project, project_target.destination, "aart-project-probe")
        self._skill(self.user_root, user_target.destination, "aart-user-probe")

        rendered = self._prompt_input()

        self.assertIn("aart-project-probe", rendered)
        self.assertIn("aart-user-probe", rendered)

    def test_the_measured_instruction_files_are_the_ones_codex_reads(self) -> None:
        project_memory = memory_target("codex", Scope.PROJECT)
        user_memory = memory_target("codex", Scope.USER)
        (self.project / project_memory.destination).write_text(
            "AART-PROJECT-INSTRUCTION-PROBE\n", encoding="utf-8"
        )
        user_file = self.user_root / user_memory.destination
        user_file.parent.mkdir(parents=True, exist_ok=True)
        user_file.write_text("AART-USER-INSTRUCTION-PROBE\n", encoding="utf-8")

        rendered = self._prompt_input()

        self.assertIn("AART-PROJECT-INSTRUCTION-PROBE", rendered)
        self.assertIn("AART-USER-INSTRUCTION-PROBE", rendered)


if __name__ == "__main__":
    unittest.main()
