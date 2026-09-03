"""B-044: configured installs perform declared setup through the shared engine.

The fixture first proved the shipped defect: both configured front ends placed a real promoted
artifact and reported success without running its declarative recipe. These acceptance assertions
are the inversion of that RED. Explicit CLI effect approval and terminal consent now write the
recipe's unique configuration file, while the separate setup command recovers an install whose
first offer was declined. The promoted fixture keeps every object and recipe digest derived by the
real transaction, so the tests cannot pass against hand-patched evidence.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession
from agent_artifacts.domain.result import Ok
from agent_artifacts.tui_consumer import run_consumer_shell
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AuthoredSetup, _published_registry
from tests.consumer_shell_test import ENTER, SPACE, FakeTerminal
from tests.placed_installation_e2e_test import SKILL_BODY, STYLE_BODY

COORDINATE = "company/skill/code-review"
TODAY = dt.date(2026, 9, 1)

#: The file the declared setup writes, and nothing else does. Its absence after a reported-finished
#: install is the whole of the defect, so it is named once and asserted against by name.
CONFIGURED = ".code-review.toml"

#: The same Skill as every other placement fixture, except that it says which platforms it runs on.
#: A setup declaration must name a subset of the artifact's platforms, and the setup engine supports
#: exactly `darwin`, so an artifact that declares no platforms at all cannot declare setup.
MANIFEST = {
    "schema": "aart.dev/skill/v1",
    "artifact": {"name": "code-review", "kind": "skill", "version": "1.2.0"},
    "payload": {"include": ["SKILL.md", "reference/style.md"]},
    "compatibility": {"harnesses": ["claude"], "platforms": ["darwin", "linux"]},
}

AUTHORED: tuple[tuple[str, str], ...] = (
    ("code-review/aart.json", json.dumps(MANIFEST)),
    ("code-review/SKILL.md", SKILL_BODY),
    ("code-review/reference/style.md", STYLE_BODY),
)

#: One managed block in one project file: the smallest setup that is unmistakably observable. It
#: needs no tool, no secret and no network, so nothing about the environment can explain the file
#: being absent except that the recipe was never run.
RECIPE = {
    "schema_version": 2,
    "protocol_version": 2,
    "artifact": "skill/code-review",
    "purpose": "Write the configuration file the Skill reads.",
    "platforms": ["darwin"],
    "help_urls": [{"label": "Setup help", "url": "https://example.test/code-review/setup"}],
    "required_tools": [],
    "capabilities": ["filesystem"],
    "inputs": [],
    "steps": [
        {
            "id": "config",
            "use": "file.managed-block@1",
            "with": {"file": CONFIGURED, "content": "enabled = true"},
        }
    ],
}


def _declaring_setup():
    """A machine whose configured registry approves one Skill that declares setup."""

    return _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE))


class DeclaredSetupFixtureTest(unittest.TestCase):
    """The guard that keeps every assertion below from passing for the wrong reason.

    Each test in this module proves a negative -- that a file the setup would have written is not
    there. A fixture that quietly failed to declare setup at all would satisfy every one of them,
    so what the registry approves is asserted first, from the published snapshot itself.
    """

    def test_the_approved_registry_carries_the_declaration_and_its_recipe(self) -> None:
        published = _published_registry(AUTHORED, setup=AuthoredSetup(RECIPE))
        entries = {str(entry.path): entry for entry in published.entries}
        root = "artifacts/skill/code-review/1.2.0"

        manifest = json.loads(entries[f"{root}/artifact.json"].content)

        self.assertEqual(
            manifest["setup"], {"recipe": "setup/installer.json", "platforms": ["darwin"]}
        )
        self.assertEqual(
            json.loads(entries[f"{root}/setup/installer.json"].content)["steps"][0]["with"]["file"],
            CONFIGURED,
        )
        self.assertIn(f"{root}/SETUP.md", entries)


@unittest.skipUnless(
    sys.platform == "darwin",
    "the setup engine accepts only darwin recipes (setup.py:562), so applying one elsewhere is "
    "refused for the platform before the effect this asserts on is reached",
)
class ConfiguredInstallCommandSetupTest(unittest.TestCase):
    """`aart marketplace install`, for a coordinate the configured registry approved."""

    def test_an_artifact_that_declares_setup_is_configured_after_explicit_effect_approval(
        self,
    ) -> None:
        with _declaring_setup() as env:
            code, payload = env.run(
                "marketplace",
                "install",
                COORDINATE,
                "--profile",
                "claude",
                "--yes",
                "--approve-setup-effects",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["session_status"], "succeeded")
            self.assertTrue(
                (env.project / ".claude/skills/code-review/SKILL.md").is_file(),
                "the Skill never reached the harness, so this proves nothing about setup",
            )
            self.assertTrue((env.project / CONFIGURED).exists())
            self.assertEqual(payload["setup"]["configured"], 1)

    def test_the_setup_command_recovers_a_configured_install_that_declined_setup(self) -> None:

        with _declaring_setup() as env:
            env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")

            code, payload = env.run(
                "marketplace",
                "setup",
                COORDINATE,
                "--profile",
                "claude",
                "--yes",
                "--approve-setup-effects",
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["setup"]["configured"], 1)
            self.assertTrue((env.project / CONFIGURED).exists())


@unittest.skipUnless(
    sys.platform == "darwin",
    "the setup engine accepts only darwin recipes (setup.py:562), so applying one elsewhere is "
    "refused for the platform before the effect this asserts on is reached",
)
class ConsumerShellSetupTest(unittest.TestCase):
    """The persistent shell, installing the same artifact through the same seam."""

    def test_the_shell_configures_the_install_after_terminal_consent(self) -> None:
        with _declaring_setup() as env:
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(
                    project=str(env.project), user_home=str(env.home), today=TODAY
                )
            self.assertIsInstance(composed, Ok, getattr(composed, "diagnostics", ()))
            assert isinstance(composed, Ok)
            handler = composed.value
            terminal = FakeTerminal(SPACE, ord("i"), ENTER, ENTER, ENTER, ENTER, ord("y"))

            with mock.patch.dict(os.environ, env.xdg, clear=False):
                finished = run_consumer_shell(
                    handler.source(),
                    terminal,
                    state=ConsumerUiState(ConsumerSession(ConsumerScreen.MARKETPLACE)),
                    action_handler=handler,
                    settings_writer=handler.save_settings,
                )

            self.assertEqual(finished.session.screen, ConsumerScreen.SUCCESS)
            self.assertTrue(
                (env.project / ".claude/skills/code-review/SKILL.md").is_file(),
                "the Skill never reached the harness, so this proves nothing about setup",
            )
            self.assertTrue((env.project / CONFIGURED).exists())


if __name__ == "__main__":
    unittest.main()
