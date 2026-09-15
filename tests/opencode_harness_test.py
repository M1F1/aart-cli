"""`QA-011`/`B-085`: OpenCode is measured, and its MCP entry is written in OpenCode's own shape.

The dormant `profiles/builtin.py` names OpenCode, and `B-085` is explicit that it is not an
implementation to reconnect: its MCP projection predates the current contract, where a local server
is an object carrying `type` and a `command` *array* rather than a command string beside `args`.
Copying the old rows would have written a file OpenCode parses and then ignores.

How the rows below were measured against OpenCode 1.18.29, all offline:

    opencode debug skill     # lists every skill it found, with the file each came from
    opencode debug config    # prints the merged configuration, including `mcp`
    opencode debug paths     # names the config root the user-scope rows are relative to

`HOME` is honoured for all three, which is what lets the observation run against a temporary
directory instead of the person's own configuration.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.effects import DeliveryKind
from agent_artifacts.domain.harness import (
    McpRegistration,
    Scope,
    delivery_target,
    mcp_target,
    memory_target,
    registration_entry,
)

SKILL_DOCUMENT = """---
name: {name}
description: probe skill written by the AART test suite
---

body
"""


class OpenCodeTargetTest(unittest.TestCase):
    def test_skills_are_delivered_into_opencodes_own_directories(self) -> None:
        project = delivery_target("opencode", Scope.PROJECT, ArtifactKind.SKILL)
        user = delivery_target("opencode", Scope.USER, ArtifactKind.SKILL)

        self.assertEqual(project.destination, ".opencode/skills/<name>")
        self.assertEqual(user.destination, ".config/opencode/skills/<name>")
        self.assertIs(project.delivery, DeliveryKind.TREE)
        self.assertIs(user.delivery, DeliveryKind.TREE)

    def test_instructions_are_the_agents_file_at_each_scope(self) -> None:
        self.assertEqual(memory_target("opencode", Scope.PROJECT).destination, "AGENTS.md")
        self.assertEqual(
            memory_target("opencode", Scope.USER).destination, ".config/opencode/AGENTS.md"
        )

    def test_the_mcp_settings_files_are_the_ones_opencode_merges(self) -> None:
        project = mcp_target("opencode", Scope.PROJECT)
        user = mcp_target("opencode", Scope.USER)

        self.assertEqual(project.settings_file, "opencode.json")
        self.assertEqual(user.settings_file, ".config/opencode/opencode.json")
        self.assertEqual(project.server_map, "mcp")
        self.assertEqual(user.server_map, "mcp")


class OpenCodeRegistrationShapeTest(unittest.TestCase):
    def test_a_local_server_is_a_type_and_one_command_vector(self) -> None:
        """The whole reason this harness needed measuring rather than copying (`B-085`)."""

        entry = registration_entry(
            McpRegistration(
                mcp_target("opencode", Scope.PROJECT),
                "aart-demo",
                "/opt/aart/bin/demo",
                ("--stdio", "--quiet"),
            )
        )

        self.assertEqual(
            entry, {"command": ["/opt/aart/bin/demo", "--stdio", "--quiet"], "type": "local"}
        )

    def test_a_server_with_no_arguments_is_still_a_vector(self) -> None:
        entry = registration_entry(
            McpRegistration(mcp_target("opencode", Scope.USER), "aart-demo", "/opt/aart/bin/demo")
        )

        self.assertEqual(entry, {"command": ["/opt/aart/bin/demo"], "type": "local"})

    def test_claude_keeps_the_shape_claude_reads(self) -> None:
        """Two harnesses, two shapes. Introducing OpenCode's must not rewrite the incumbent's."""

        entry = registration_entry(
            McpRegistration(
                mcp_target("claude", Scope.PROJECT), "aart-demo", "/opt/aart/bin/demo", ("--stdio",)
            )
        )

        self.assertEqual(entry, {"args": ["--stdio"], "command": "/opt/aart/bin/demo"})


@unittest.skipUnless(shutil.which("opencode"), "OpenCode is not installed on this machine")
class OpenCodeObservationTest(unittest.TestCase):
    """Re-run the measurement, hermetically, against the OpenCode installed here."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="aart-opencode-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.user_root = self.root / "home"
        self.project = self.root / "project"
        for directory in (self.user_root, self.project):
            directory.mkdir(parents=True)

    def _run(self, *arguments: str) -> str:
        environment = dict(os.environ, HOME=str(self.user_root))
        for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            environment.pop(variable, None)
        completed = subprocess.run(
            ("opencode", *arguments),
            cwd=str(self.project),
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if completed.returncode != 0:
            self.skipTest(
                f"`opencode {' '.join(arguments)}` is unavailable: {completed.stderr[:200]}"
            )
        return completed.stdout

    def _write(self, root: Path, relative: str, content: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_the_measured_skill_directories_are_the_ones_opencode_scans(self) -> None:
        for root, scope, name in (
            (self.project, Scope.PROJECT, "aart-project-probe"),
            (self.user_root, Scope.USER, "aart-user-probe"),
        ):
            target = delivery_target("opencode", scope, ArtifactKind.SKILL)
            self._write(
                root,
                target.destination.replace("<name>", name) + "/SKILL.md",
                SKILL_DOCUMENT.format(name=name),
            )

        found = {item["name"] for item in json.loads(self._run("debug", "skill"))}

        self.assertIn("aart-project-probe", found)
        self.assertIn("aart-user-probe", found)

    def test_the_measured_settings_files_carry_the_servers_opencode_merges(self) -> None:
        for root, scope, server in (
            (self.project, Scope.PROJECT, "aart-project-server"),
            (self.user_root, Scope.USER, "aart-user-server"),
        ):
            target = mcp_target("opencode", scope)
            entry = registration_entry(
                McpRegistration(target, server, "/usr/bin/true", (f"--{scope.value}",))
            )
            self._write(
                root,
                target.settings_file,
                json.dumps({"$schema": "https://opencode.ai/config.json", "mcp": {server: entry}}),
            )

        merged = json.loads(self._run("debug", "config"))

        self.assertIn("aart-project-server", merged.get("mcp", {}))
        self.assertIn("aart-user-server", merged.get("mcp", {}))
        # Written in OpenCode's own shape, and read back unchanged: the vector survived the merge
        # rather than being reported as an unusable entry.
        self.assertEqual(
            merged["mcp"]["aart-project-server"],
            {"type": "local", "command": ["/usr/bin/true", "--project"]},
        )

    def test_the_documented_config_root_is_chosen_where_two_paths_both_work(self) -> None:
        """A measured surprise, recorded rather than smoothed over.

        This build also reads `~/.opencode/opencode.json`, which its own shipped documentation says
        it does not. Both paths work, so the table row is a choice: AART writes the one `opencode
        debug paths` reports as the config root, because that is the one that will still be read
        when the undocumented path stops being.
        """

        target = mcp_target("opencode", Scope.USER)
        self._write(
            self.user_root,
            ".opencode/opencode.json",
            json.dumps(
                {
                    "mcp": {
                        "undocumented-path-server": {"type": "local", "command": ["/usr/bin/true"]}
                    }
                }
            ),
        )

        merged = json.loads(self._run("debug", "config"))
        paths = self._run("debug", "paths")

        self.assertIn("undocumented-path-server", merged.get("mcp", {}))
        config_root = next(
            line.split(maxsplit=1)[1].strip()
            for line in paths.splitlines()
            if line.startswith("config ")
        )
        self.assertEqual(
            os.path.join(config_root, "opencode.json"),
            str(self.user_root / target.settings_file),
        )


if __name__ == "__main__":
    unittest.main()
