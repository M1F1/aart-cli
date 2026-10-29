"""CP-48: the usage hook as a harness runs it, and how it is put in place and removed (§212).

The hook runs by path with `-I`, from whatever project the harness works in, so these tests start
it exactly so -- from a directory holding modules that would shadow the standard library and the
package if the project were on the import path.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aart_cli.application.usage_recording import (
    CLAUDE_MATCHER,
    HOOK_SCRIPT,
    OPENCODE_PLUGIN_MARK,
    UsageHook,
    claude_settings_with,
    claude_settings_without,
    claude_usage_hooked,
    opencode_plugin,
)
from aart_cli.domain.artifact_usage import ArtifactUse, UsageKind
from aart_cli.domain.result import Err, Ok
from aart_cli.io import usage_hook
from aart_cli.io.activity_store import ActivityDatabase
from aart_cli.io.usage_hooks import (
    harness_file,
    read_artifact_usage,
    reconcile_usage_hooks,
    running_usage_hook,
    set_usage_hook,
    usage_hooked,
)

_SECRET = "hook-argument-never-kept"


def _uses(home: Path) -> list[tuple[str, ...]]:
    path = home / "state" / "activity.sqlite3"
    if not path.exists():
        return []
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT harness, kind, name, project FROM artifact_use ORDER BY id"
        ).fetchall()


class TheHookAsAHarnessRunsItTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        root = Path(self._temporary.name)
        self.home = root / "aart-home"
        self.project = root / "project"
        # A project whose modules would replace the standard library and the package, if the
        # hook put the directory it is started from on the import path.
        (self.project / "aart_cli").mkdir(parents=True)
        (self.project / "aart_cli" / "__init__.py").write_text("raise SystemExit(7)\n")
        (self.project / "json.py").write_text("raise SystemExit(8)\n")
        (self.project / "sqlite3.py").write_text("raise SystemExit(9)\n")

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _run(self, harness: str, payload: bytes) -> subprocess.CompletedProcess[bytes]:
        hook = running_usage_hook(harness, data_root=str(self.home))
        return subprocess.run(
            hook.arguments,
            input=payload,
            cwd=self.project,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(self.project)},
            timeout=60,
        )

    def test_a_claude_skill_call_is_recorded_by_name_only(self) -> None:
        payload = {
            "tool_name": "Skill",
            "tool_input": {"skill": "code-review", "args": _SECRET},
            "cwd": str(self.project),
        }

        ran = self._run("claude", json.dumps(payload).encode())

        self.assertEqual((ran.returncode, ran.stdout), (0, b""), ran.stderr)
        self.assertEqual(_uses(self.home), [("claude", "skill", "code-review", str(self.project))])
        database = (self.home / "state" / "activity.sqlite3").read_bytes()
        self.assertNotIn(_SECRET.encode(), database)

    def test_an_opencode_mcp_call_is_recorded(self) -> None:
        ran = self._run("opencode", json.dumps({"tool": "jira_search", "directory": "/w"}).encode())

        self.assertEqual((ran.returncode, ran.stdout), (0, b""), ran.stderr)
        self.assertEqual(_uses(self.home), [("opencode", "mcp", "jira_search", "/w")])

    def test_anything_it_cannot_read_records_nothing_and_still_exits_0(self) -> None:
        for payload in (b"", b"not json", b"[]", json.dumps({"tool_name": "Bash"}).encode()):
            with self.subTest(payload=payload):
                ran = self._run("claude", payload)
                self.assertEqual((ran.returncode, ran.stdout), (0, b""))
        self.assertEqual(_uses(self.home), [])

    def test_an_unwritable_home_still_exits_0(self) -> None:
        self.home.parent.mkdir(exist_ok=True)
        self.home.write_text("a file where the home should be")

        ran = self._run(
            "claude", json.dumps({"tool_name": "Skill", "tool_input": {"skill": "s"}}).encode()
        )

        self.assertEqual((ran.returncode, ran.stdout), (0, b""))

    def test_many_agents_at_once_on_a_new_home_lose_no_use(self) -> None:
        # Agents and their subagents call tools in parallel, so many hooks start in the same
        # moment -- here before any database exists, so they also race to create it.
        payload = json.dumps({"tool_name": "Skill", "tool_input": {"skill": "s"}}).encode()
        hooks = [
            subprocess.Popen(
                running_usage_hook(harness, data_root=str(self.home)).arguments,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.project,
            )
            for harness in ("claude",) * 32
        ]
        for hook in hooks:
            assert hook.stdin is not None
            hook.stdin.write(payload)
            hook.stdin.close()

        self.assertEqual([hook.wait(60) for hook in hooks], [0] * 32)
        self.assertEqual(len(_uses(self.home)), 32)

    def test_a_hook_that_fails_inside_still_exits_0(self) -> None:
        with (
            mock.patch.object(usage_hook, "record", side_effect=RuntimeError("anything")),
            mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}"))),
        ):
            self.assertEqual(usage_hook.main(["claude", str(self.home)]), 0)


_HOOK = UsageHook("claude", "/usr/bin/python3", f"/site/{HOOK_SCRIPT}", "/home/me/.aart-cli")


class ClaudeSettingsTest(unittest.TestCase):
    def test_the_hook_is_added_after_every_other_one_and_runs_without_blocking(self) -> None:
        theirs = {"matcher": "Bash", "hooks": [{"type": "command", "command": "guard.sh"}]}
        document = {"model": "x", "hooks": {"PreToolUse": [theirs], "Stop": []}}

        changed = claude_settings_with(document, _HOOK)

        self.assertEqual(changed["model"], "x")
        self.assertEqual(changed["hooks"]["Stop"], [])  # type: ignore[index]
        entries = changed["hooks"]["PreToolUse"]  # type: ignore[index]
        self.assertEqual(entries[0], theirs)
        self.assertEqual(entries[1]["matcher"], CLAUDE_MATCHER)
        self.assertEqual(
            entries[1]["hooks"],
            [{"type": "command", "command": _HOOK.command, "async": True, "timeout": 30}],
        )
        self.assertEqual(document["hooks"]["PreToolUse"], [theirs])

    def test_adding_twice_keeps_one_and_a_moved_aart_cli_replaces_its_own(self) -> None:
        moved = UsageHook("claude", "/opt/python", f"/other/{HOOK_SCRIPT}", "/home/me/.aart-cli")

        twice = claude_settings_with(claude_settings_with({}, _HOOK), moved)

        entries = twice["hooks"]["PreToolUse"]  # type: ignore[index]
        self.assertEqual(len(entries), 1)
        self.assertIn("/opt/python", entries[0]["hooks"][0]["command"])

    def test_removing_takes_only_aart_cli_s_and_tidies_what_it_emptied(self) -> None:
        theirs = {"matcher": "Bash", "hooks": [{"type": "command", "command": "guard.sh"}]}

        self.assertEqual(claude_settings_without(claude_settings_with({"a": 1}, _HOOK)), {"a": 1})
        kept = claude_settings_without(
            claude_settings_with({"hooks": {"PreToolUse": [theirs]}}, _HOOK)
        )
        self.assertEqual(kept, {"hooks": {"PreToolUse": [theirs]}})
        self.assertFalse(claude_usage_hooked(kept))

    def test_settings_whose_hooks_are_not_the_documented_shape_are_refused(self) -> None:
        for document in ({"hooks": []}, {"hooks": {"PreToolUse": {}}}):
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    claude_settings_with(document, _HOOK)
                self.assertFalse(claude_usage_hooked(document))


class OpencodePluginTest(unittest.TestCase):
    def test_the_plugin_hands_over_names_only(self) -> None:
        plugin = opencode_plugin(
            UsageHook("opencode", "/usr/bin/python3", f"/site/{HOOK_SCRIPT}", "/h")
        )

        self.assertTrue(plugin.startswith(OPENCODE_PLUGIN_MARK))
        self.assertIn('"tool.execute.before"', plugin)
        self.assertIn("JSON.stringify({ tool, skill, directory })", plugin)
        self.assertNotIn("JSON.stringify(output", plugin)
        self.assertIn(
            json.dumps(["/usr/bin/python3", "-I", f"/site/{HOOK_SCRIPT}", "opencode", "/h"]), plugin
        )


class PuttingItInPlaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        root = Path(self._temporary.name)
        self.user_home = str(root / "home")
        self.data_root = str(root / "aart")
        Path(self.user_home).mkdir()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_claude_on_and_off_keeps_the_rest_of_its_settings(self) -> None:
        settings = Path(harness_file("claude", user_home=self.user_home))
        settings.parent.mkdir()
        settings.write_text(json.dumps({"theme": "dark"}))

        self.assertIsInstance(
            set_usage_hook("claude", True, user_home=self.user_home, data_root=self.data_root), Ok
        )
        self.assertTrue(usage_hooked("claude", user_home=self.user_home))
        self.assertEqual(json.loads(settings.read_text())["theme"], "dark")

        set_usage_hook("claude", False, user_home=self.user_home, data_root=self.data_root)
        self.assertEqual(json.loads(settings.read_text()), {"theme": "dark"})

    def test_settings_that_are_not_json_are_refused_and_left_byte_for_byte(self) -> None:
        settings = Path(harness_file("claude", user_home=self.user_home))
        settings.parent.mkdir()
        settings.write_bytes(b"{ // a comment\n}")

        written = set_usage_hook("claude", True, user_home=self.user_home, data_root=self.data_root)

        self.assertIsInstance(written, Err)
        self.assertEqual(settings.read_bytes(), b"{ // a comment\n}")

    def test_opencode_s_plugin_is_written_and_removed_but_a_foreign_one_is_kept(self) -> None:
        plugin = Path(harness_file("opencode", user_home=self.user_home))

        set_usage_hook("opencode", True, user_home=self.user_home, data_root=self.data_root)
        self.assertTrue(usage_hooked("opencode", user_home=self.user_home))
        set_usage_hook("opencode", False, user_home=self.user_home, data_root=self.data_root)
        self.assertFalse(plugin.exists())

        plugin.write_text("// somebody's own plugin\n")
        refused = set_usage_hook(
            "opencode", False, user_home=self.user_home, data_root=self.data_root
        )
        self.assertIsInstance(refused, Err)
        self.assertEqual(plugin.read_text(), "// somebody's own plugin\n")

    def test_by_default_only_a_present_default_harness_is_hooked(self) -> None:
        (Path(self.user_home) / ".claude").mkdir()
        self.assertEqual(
            reconcile_usage_hooks(
                ("opencode",), user_home=self.user_home, data_root=self.data_root
            ),
            (),
        )
        self.assertFalse(usage_hooked("claude", user_home=self.user_home))
        self.assertFalse((Path(self.user_home) / ".config").exists())

        (Path(self.user_home) / ".config" / "opencode").mkdir(parents=True)
        self.assertEqual(
            reconcile_usage_hooks(
                ("opencode",), user_home=self.user_home, data_root=self.data_root
            ),
            ("opencode",),
        )
        self.assertEqual(
            reconcile_usage_hooks(
                ("opencode",), user_home=self.user_home, data_root=self.data_root
            ),
            (),
        )

    def test_a_harness_turned_off_loses_its_hook(self) -> None:
        (Path(self.user_home) / ".config" / "opencode").mkdir(parents=True)
        reconcile_usage_hooks(("opencode",), user_home=self.user_home, data_root=self.data_root)

        reconcile_usage_hooks((), user_home=self.user_home, data_root=self.data_root)

        self.assertFalse(usage_hooked("opencode", user_home=self.user_home))

    def test_the_view_ranks_what_was_recorded(self) -> None:
        ActivityDatabase(str(Path(self.data_root) / "state")).record_use(
            ArtifactUse("opencode", UsageKind.SKILL, "s"), "2026-10-28T10:00:00+00:00"
        )

        view = read_artifact_usage(data_root=self.data_root, user_home=self.user_home)

        self.assertEqual([(item.artifact, item.uses) for item in view.ranking], [("s", 1)])
        self.assertEqual(view.hooked, ())


class TheRunningHookTest(unittest.TestCase):
    def test_it_is_this_interpreter_and_this_package_s_script(self) -> None:
        hook = running_usage_hook("claude", data_root="relative/home")

        self.assertEqual(hook.python, sys.executable)
        self.assertTrue(Path(hook.script).is_file())
        self.assertTrue(hook.home.startswith("/"))

    def test_python_is_never_found_through_the_path(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": ""}):
            self.assertTrue(running_usage_hook("claude", data_root="/h").python.startswith("/"))


if __name__ == "__main__":
    unittest.main()
