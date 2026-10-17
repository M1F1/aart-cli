"""Tabnine CLI at user scope reads `~/.tabnine/agent`, for every kind it documents (D-420).

Tabnine CLI documents user-level Agent Skills in `~/.tabnine/agent/skills/<name>/SKILL.md`, a
global `~/.tabnine/agent/TABNINE.md`, and MCP servers and hooks in `~/.tabnine/agent/settings.json`.
The user root is the home directory, so every path keeps `.tabnine/agent`. This build used to
write the MCP into `~/agent/settings.json`, which Tabnine never reads, and offered no user-scope
Skill, memory or hook at all.
"""

from __future__ import annotations

import json
import unittest

from tests.configured_install_command_e2e_test import _environment
from tests.installation_harness_choice_test import _AUTHORED_MCP, _AUTHORED_SKILL

_INSTALL = ("--profile", "tabnine", "--scope", "user", "--yes")


class TabnineUserScopeE2ETest(unittest.TestCase):
    def test_a_skill_goes_into_tabnines_user_skills_directory(self) -> None:
        with _environment(authored=_AUTHORED_SKILL) as env:
            code, payload = env.run("consume", "install", "company/skill/code-review", *_INSTALL)

            self.assertEqual(code, 0, payload)
            skill = env.home / ".tabnine/agent/skills/code-review-company-user/SKILL.md"
            self.assertTrue(skill.is_file(), payload)
            self.assertFalse((env.project / ".tabnine").exists())

    def test_an_mcp_is_registered_in_tabnines_user_settings(self) -> None:
        with _environment(authored=_AUTHORED_MCP) as env:
            code, payload = env.run("consume", "install", "company/mcp/dummy", *_INSTALL)

            self.assertEqual(code, 0, payload)
            settings = env.home / ".tabnine/agent/settings.json"
            servers = json.loads(settings.read_text(encoding="utf-8"))["mcpServers"]
            self.assertIn("dummy-company-user", servers)
            self.assertFalse((env.home / "agent").exists())


if __name__ == "__main__":
    unittest.main()
