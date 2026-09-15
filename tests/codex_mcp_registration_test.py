"""Registering an MCP server with Codex, by asking Codex to write its own configuration.

B-096 blocked this on a real constraint: Codex keeps servers as `[mcp_servers.<name>]` TOML
tables, `tomllib` reads only and only from 3.11 while `requires-python` is `>=3.10`, nothing in the
standard library writes TOML at any version, and INV-071 forbids a dependency. The objection was
never the syntax -- it was that a hand-rolled writer cannot promise to leave alone the comments,
ordering and unrelated tables that the JSON interpreter promises for every other harness.

What unblocked it is a measurement, not a workaround: `codex mcp add` and `codex mcp remove` keep
that promise. The live tests here are the measurement, run against the installed Codex; the rest
hold the routing and the refusals without needing it.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from agent_artifacts.domain.harness import (
    MCP_TARGETS,
    McpEditor,
    McpRegistration,
    McpTarget,
    Scope,
    mcp_target,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.harness import (
    HARNESS_EDITOR_MISSING,
    CodexServerEditor,
    LocalHarnessRegistry,
)

_LAUNCHER = "/usr/bin/true"


class CodexTargetTest(unittest.TestCase):
    def test_codex_keeps_its_servers_where_codex_writes_them(self) -> None:
        target = mcp_target("codex", Scope.USER)

        self.assertEqual(".codex/config.toml", target.settings_file)
        self.assertEqual("mcp_servers", target.server_map)

    def test_codex_does_not_write_its_own_settings_file(self) -> None:
        self.assertIs(McpEditor.HARNESS_COMMAND, mcp_target("codex", Scope.USER).editor)

    def test_there_is_no_project_row_because_codex_writes_no_project_server(self) -> None:
        # `codex mcp add` reports "Added global MCP server" and offers no project flag, and a
        # project registration would be inert until the operator trusts the project anyway.
        with self.assertRaises(KeyError):
            mcp_target("codex", Scope.PROJECT)

    def test_every_other_measured_harness_is_still_written_by_aart(self) -> None:
        """Delegation is the exception it was measured to be, not a new default."""

        delegated = {
            target.harness
            for target in MCP_TARGETS.values()
            if target.editor is McpEditor.HARNESS_COMMAND
        }

        self.assertEqual({"codex"}, delegated)

    def test_a_target_cannot_name_an_editor_that_is_not_one(self) -> None:
        with self.assertRaises(ValueError):
            McpTarget("codex", Scope.USER, ".codex/config.toml", "mcp_servers", editor="whoever")


class DelegationRoutingTest(unittest.TestCase):
    """The registry sends each target to whoever can write its file, and says so when it cannot."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        self.registry = LocalHarnessRegistry(str(self.root))

    def test_a_delegated_registration_never_writes_the_file_itself(self) -> None:
        """The refusal to hand-write TOML is the point; a fallback would defeat it."""

        registration = McpRegistration(
            mcp_target("codex", Scope.USER), "aart-probe", _LAUNCHER, ("--strict",)
        )
        editor = CodexServerEditor(str(self.root), executable="a-codex-that-is-not-installed")

        result = editor.register(registration)

        self.assertIsInstance(result, Err)
        self.assertEqual(HARNESS_EDITOR_MISSING, result.diagnostics[0].code)
        self.assertFalse((self.root / ".codex/config.toml").exists())

    def test_a_missing_editor_is_named_rather_than_reported_as_registered(self) -> None:
        editor = CodexServerEditor(str(self.root), executable="a-codex-that-is-not-installed")

        result = editor.registered(mcp_target("codex", Scope.USER))

        self.assertIsInstance(result, Err)
        self.assertIn("not on PATH", result.diagnostics[0].message)

    def test_a_harness_aart_writes_is_still_written_by_aart(self) -> None:
        registration = McpRegistration(
            mcp_target("opencode", Scope.PROJECT), "aart-probe", _LAUNCHER
        )

        receipt = self.registry.register(registration)

        self.assertIsInstance(receipt, Ok, getattr(receipt, "diagnostics", ()))
        self.assertTrue((self.root / "opencode.json").exists())

    def test_the_delegated_path_is_the_file_the_harness_owns(self) -> None:
        editor = CodexServerEditor(str(self.root))

        self.assertEqual(
            str(self.root / ".codex/config.toml"),
            editor.path_for(mcp_target("codex", Scope.USER)),
        )


@unittest.skipUnless(shutil.which("codex"), "Codex is not installed on this machine")
class InstalledCodexWritesTheRegistrationTest(unittest.TestCase):
    """The measurement B-096 was waiting for, run against the installed Codex."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        (self.root / ".codex").mkdir()
        self.registry = LocalHarnessRegistry(str(self.root))
        self.target = mcp_target("codex", Scope.USER)
        self.config = self.root / self.target.settings_file

    def _registration(self, command: str = _LAUNCHER, *arguments: str) -> McpRegistration:
        return McpRegistration(self.target, "aart-probe", command, tuple(arguments))

    def _codex(self, *arguments: str) -> str:
        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(self.root / ".codex")
        completed = subprocess.run(
            ("codex", *arguments), capture_output=True, text=True, timeout=120, env=environment
        )
        # Deliberately a failure and not a skip. The class already skips when Codex is absent, so
        # a non-zero exit here means Codex is installed and unhappy -- most likely with a
        # configuration file this test just caused to be written. Skipping that hides the defect.
        self.assertEqual(
            0, completed.returncode, f"`codex {' '.join(arguments)}`: {completed.stderr[:400]}"
        )
        return completed.stdout

    def test_the_server_is_registered_and_codex_lists_it_back(self) -> None:
        receipt = self.registry.register(self._registration(_LAUNCHER, "--strict"))

        self.assertIsInstance(receipt, Ok, getattr(receipt, "diagnostics", ()))
        self.assertTrue(receipt.value.changed)
        listed = json.loads(self._codex("mcp", "list", "--json"))
        self.assertEqual(["aart-probe"], [entry["name"] for entry in listed])
        self.assertEqual(_LAUNCHER, listed[0]["transport"]["command"])
        self.assertEqual(["--strict"], listed[0]["transport"]["args"])

    def test_the_launcher_reads_back_for_the_reconciler(self) -> None:
        """What status compares against. Reading the TOML here would be reading what cannot parse."""

        registration = self._registration(_LAUNCHER, "--strict")
        self.registry.register(registration)

        self.assertEqual(_LAUNCHER, self.registry.observed_command(registration))

    def test_registering_what_is_already_there_changes_nothing(self) -> None:
        registration = self._registration(_LAUNCHER, "--strict")
        self.registry.register(registration)

        again = self.registry.register(registration)

        self.assertIsInstance(again, Ok, getattr(again, "diagnostics", ()))
        self.assertFalse(again.value.changed)

    def test_a_changed_launcher_replaces_the_one_codex_had(self) -> None:
        self.registry.register(self._registration(_LAUNCHER, "--strict"))

        replaced = self.registry.register(self._registration("/bin/echo", "--loose"))

        self.assertIsInstance(replaced, Ok, getattr(replaced, "diagnostics", ()))
        self.assertTrue(replaced.value.changed)
        listed = json.loads(self._codex("mcp", "list", "--json"))
        self.assertEqual("/bin/echo", listed[0]["transport"]["command"])
        self.assertEqual(["--loose"], listed[0]["transport"]["args"])

    def test_unregistering_removes_it_and_says_nothing_changed_the_second_time(self) -> None:
        self.registry.register(self._registration())

        removed = self.registry.unregister(self.target, "aart-probe")
        again = self.registry.unregister(self.target, "aart-probe")

        self.assertIsInstance(removed, Ok, getattr(removed, "diagnostics", ()))
        self.assertTrue(removed.value.changed)
        self.assertFalse(again.value.changed)
        self.assertEqual([], json.loads(self._codex("mcp", "list", "--json")))

    def test_what_the_operator_wrote_survives_being_registered_around(self) -> None:
        """The whole objection in B-096, measured: this is what a hand-rolled writer risks."""

        original = (
            "# a comment the operator wrote\n"
            'model = "gpt-5"\n'
            "\n"
            "[mcp_servers.theirs]\n"
            'command = "/opt/theirs"\n'
            "\n"
            "[tui]\n"
            'theme = "dark"\n'
        )
        self.config.write_text(original, encoding="utf-8")

        self.registry.register(self._registration(_LAUNCHER, "--strict"))
        self.registry.unregister(self.target, "aart-probe")

        self.assertEqual(original, self.config.read_text(encoding="utf-8"))

    def test_a_server_the_operator_registered_is_not_removed_by_ours(self) -> None:
        self.config.write_text('[mcp_servers.theirs]\ncommand = "/opt/theirs"\n', encoding="utf-8")
        self.registry.register(self._registration())

        self.registry.unregister(self.target, "aart-probe")

        listed = json.loads(self._codex("mcp", "list", "--json"))
        self.assertEqual(["theirs"], [entry["name"] for entry in listed])

    def test_a_server_nobody_registered_reads_back_as_nothing(self) -> None:
        self.assertIsNone(self.registry.observed_command(self._registration()))


if __name__ == "__main__":
    unittest.main()
