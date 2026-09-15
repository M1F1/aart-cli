"""CP-10 — harness registration: one measured target, merged without disturbing its neighbours."""

from __future__ import annotations

import json
import pathlib
import stat
import tempfile
import unittest

from agent_artifacts.domain.harness import (
    McpRegistration,
    McpTarget,
    Scope,
    mcp_target,
    registration_entry,
)
from agent_artifacts.domain.launch import Transport
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.harness import (
    HARNESS_SETTINGS_UNREADABLE,
    HARNESS_SETTINGS_UNUSABLE,
    LocalHarnessRegistry,
)

LAUNCHER = "/opt/agents/.tabnine/agent/aart/mcp/github/launch.sh"


def registration(server: str = "github", command: str = LAUNCHER) -> McpRegistration:
    return McpRegistration(mcp_target("tabnine", Scope.PROJECT), server, command)


class McpTargetTest(unittest.TestCase):
    def test_the_measured_tabnine_target_is_preserved(self):
        target = mcp_target("tabnine", Scope.PROJECT)
        self.assertEqual(target.settings_file, ".tabnine/agent/settings.json")
        self.assertEqual(target.server_map, "mcpServers")
        self.assertEqual(mcp_target("tabnine", Scope.USER).settings_file, "agent/settings.json")

    def test_the_measured_claude_target_is_preserved(self):
        self.assertEqual(mcp_target("claude", Scope.PROJECT).settings_file, ".mcp.json")

    def test_an_unmeasured_harness_is_not_invented(self):
        with self.assertRaises(KeyError):
            mcp_target("nonesuch", Scope.PROJECT)

    def test_a_registration_names_a_launcher_by_absolute_path(self):
        for bad in ("", "relative/launch.sh", "/with\nnewline"):
            with self.subTest(command=bad), self.assertRaises(ValueError):
                registration(command=bad)

    def test_the_entry_is_the_command_and_nothing_the_harness_did_not_ask_for(self):
        self.assertEqual(registration_entry(registration()), {"command": LAUNCHER})
        with_arguments = McpRegistration(
            mcp_target("tabnine", Scope.PROJECT), "github", LAUNCHER, ("--strict",)
        )
        self.assertEqual(
            registration_entry(with_arguments),
            {"args": ["--strict"], "command": LAUNCHER},
        )

    def test_a_target_only_accepts_a_transport_it_was_measured_with(self):
        with self.assertRaises(ValueError):
            McpTarget("tabnine", Scope.PROJECT, ".x.json", "mcpServers", frozenset())
        with self.assertRaises(ValueError):
            McpRegistration(
                mcp_target("tabnine", Scope.PROJECT),
                "github",
                LAUNCHER,
                transport="stdio",  # type: ignore[arg-type]
            )
        self.assertIn(Transport.STDIO, mcp_target("tabnine", Scope.PROJECT).transports)


class LocalHarnessRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = pathlib.Path(self._temporary.name)
        self.registry = LocalHarnessRegistry(str(self.root))
        self.settings = self.root / ".tabnine/agent/settings.json"

    def write_settings(self, data: object, mode: int = 0o644) -> None:
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        self.settings.chmod(mode)

    def read_settings(self) -> dict:
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def test_registering_into_a_missing_file_creates_it_with_only_this_server(self):
        result = self.registry.register(registration())
        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        self.assertEqual(self.read_settings(), {"mcpServers": {"github": {"command": LAUNCHER}}})
        self.assertEqual(result.value.path, str(self.settings))

    def test_registering_leaves_every_neighbouring_key_and_server_untouched(self):
        self.write_settings(
            {
                "telemetry": {"enabled": False},
                "hooks": {"BeforeTool": [{"matcher": "*", "command": "/bin/true"}]},
                "mcpServers": {"other": {"command": "/opt/other/launch.sh"}},
            }
        )
        self.registry.register(registration())
        data = self.read_settings()
        self.assertEqual(data["telemetry"], {"enabled": False})
        self.assertEqual(data["hooks"]["BeforeTool"][0]["command"], "/bin/true")
        self.assertEqual(data["mcpServers"]["other"], {"command": "/opt/other/launch.sh"})
        self.assertEqual(data["mcpServers"]["github"], {"command": LAUNCHER})

    def test_registering_the_same_thing_twice_changes_nothing_the_second_time(self):
        self.registry.register(registration())
        first = self.settings.read_bytes()
        second_result = self.registry.register(registration())
        self.assertIsInstance(second_result, Ok)
        self.assertEqual(self.settings.read_bytes(), first)
        self.assertFalse(second_result.value.changed)

    def test_re_registering_a_moved_launcher_replaces_only_that_entry(self):
        self.registry.register(registration())
        moved = "/opt/agents/.tabnine/agent/aart/mcp/github-2/launch.sh"
        result = self.registry.register(registration(command=moved))
        self.assertTrue(result.value.changed)
        self.assertEqual(self.read_settings()["mcpServers"], {"github": {"command": moved}})

    def test_an_existing_file_keeps_its_permissions(self):
        self.write_settings({"mcpServers": {}}, mode=0o600)
        self.registry.register(registration())
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)

    def test_a_settings_file_that_is_not_an_object_is_refused_rather_than_replaced(self):
        self.write_settings(["not", "an", "object"])
        before = self.settings.read_bytes()
        result = self.registry.register(registration())
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, HARNESS_SETTINGS_UNUSABLE)
        self.assertEqual(self.settings.read_bytes(), before)

    def test_a_server_map_that_is_not_an_object_is_refused_rather_than_clobbered(self):
        self.write_settings({"mcpServers": "everything"})
        result = self.registry.register(registration())
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, HARNESS_SETTINGS_UNUSABLE)
        self.assertEqual(self.read_settings()["mcpServers"], "everything")

    def test_unparseable_settings_are_reported_rather_than_discarded(self):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        result = self.registry.register(registration())
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, HARNESS_SETTINGS_UNREADABLE)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ not json")

    def test_unregistering_removes_one_server_and_keeps_the_rest(self):
        self.write_settings({"mcpServers": {"other": {"command": "/opt/other/launch.sh"}}})
        self.registry.register(registration())
        result = self.registry.unregister(mcp_target("tabnine", Scope.PROJECT), "github")
        self.assertIsInstance(result, Ok)
        self.assertTrue(result.value.changed)
        self.assertEqual(
            self.read_settings()["mcpServers"], {"other": {"command": "/opt/other/launch.sh"}}
        )

    def test_unregistering_something_absent_is_not_an_error_and_writes_nothing(self):
        result = self.registry.unregister(mcp_target("tabnine", Scope.PROJECT), "github")
        self.assertIsInstance(result, Ok)
        self.assertFalse(result.value.changed)
        self.assertFalse(self.settings.exists())

    def test_registered_servers_can_be_read_back_for_reconciliation(self):
        self.registry.register(registration("github"))
        self.registry.register(registration("gitlab", "/opt/agents/gitlab/launch.sh"))
        result = self.registry.registered(mcp_target("tabnine", Scope.PROJECT))
        self.assertEqual(result.value, ("github", "gitlab"))

    def test_a_registration_never_escapes_the_scope_root(self):
        """A climbing settings path cannot be built, so no interpreter has to defend against one."""

        for escaping in ("../outside/settings.json", "a/../../outside.json", "/etc/settings.json"):
            with self.subTest(settings_file=escaping), self.assertRaises(ValueError):
                McpTarget("tabnine", Scope.PROJECT, escaping, "mcpServers")
        self.assertTrue(
            self.registry.path_for(mcp_target("tabnine", Scope.PROJECT)).startswith(str(self.root))
        )

    def test_the_written_file_holds_the_launcher_path_and_no_value(self):
        self.registry.register(registration())
        written = self.settings.read_text(encoding="utf-8")
        self.assertIn(LAUNCHER, written)
        self.assertNotIn("token", written.lower())
        self.assertTrue(written.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
