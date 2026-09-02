"""B-044: what the configured install seam leaves undone when an artifact declares setup.

An artifact can declare that placing its files is not the whole of installing it -- that a
configuration file has to be written, a credential stored, an MCP server registered -- by carrying
a `setup` reference and a declarative recipe in its package. The Product Specification names
performing that work as AART's, and screens 09 and 11 summarize a finished install as "configured
MCP servers, isolated environments ... securely stored credentials".

The configured canonical seam does not perform it. `complete_configured_installation` places the
payload, writes a receipt and returns; nothing between the confirmed review and the drawn success
consults the setup declaration. Both front ends reach installation through that one seam --
`aart marketplace install` for an approved RegistryGit coordinate, and the persistent shell's
action handler for every install it makes -- so both report a finished install of an artifact that
is not configured.

These tests characterize that. Every assertion below states what the two routes do today, and each
one is written so that closing B-044 breaks it: the recipe writes a file with a name nothing else
on the machine writes, and the assertion is that the file is not there. When the seam runs setup,
these invert rather than quietly keep passing.

Half of the original characterization has already inverted. Both routes reported the finished
install and said nothing at all about the setup they skipped; both now name it, which
`tests/configured_setup_report_test.py` owns and which those assertions were moved to rather than
weakened. What is characterized here is the part that remains: the work itself is still not done.

The legacy path is where setup does run, and it is reached only when a Selection is *not* an
approved registry coordinate (`commands/marketplace.py::_configured_registry_selection` returns
`None` for a direct or local source). That is why the gap was not visible from the setup engine's
own tests: SET01 proves the engine, and the engine is never asked.
"""

from __future__ import annotations

import datetime as dt
import json
import os
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


class ConfiguredInstallCommandSetupTest(unittest.TestCase):
    """`aart marketplace install`, for a coordinate the configured registry approved."""

    def test_an_artifact_that_declares_setup_installs_and_reports_success_unconfigured(
        self,
    ) -> None:
        with _declaring_setup() as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["session_status"], "succeeded")
            self.assertTrue(
                (env.project / ".claude/skills/code-review/SKILL.md").is_file(),
                "the Skill never reached the harness, so this proves nothing about setup",
            )
            # B-044. The declared setup did not run. The command now says so -- see
            # `configured_setup_report_test.py`, which owns that assertion -- but saying it is not
            # doing it, and the file the recipe writes is still not there.
            self.assertFalse((env.project / CONFIGURED).exists())

    def test_the_setup_command_cannot_reach_what_the_configured_seam_installed(self) -> None:
        """And the operator's remaining move does not work either.

        `aart marketplace setup` is the separate verb that runs a queued setup, so an install that
        skipped it would still be recoverable by hand. It is not: that command resolves through the
        legacy catalogue, which reads root manifests a promoted registry snapshot does not carry,
        so it refuses before it ever looks at what is installed.
        """

        with _declaring_setup() as env:
            env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")

            code, payload = env.run(
                "marketplace", "setup", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 1)
            self.assertFalse(payload["ok"])
            self.assertEqual(
                [item["message"] for item in payload["diagnostics"]],
                ["registry company has invalid root manifests"],
            )
            self.assertFalse((env.project / CONFIGURED).exists())


class ConsumerShellSetupTest(unittest.TestCase):
    """The persistent shell, installing the same artifact through the same seam."""

    def test_the_shell_draws_success_for_an_install_whose_setup_never_ran(self) -> None:
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
            # B-044. Success is drawn, the payload is placed, and the artifact is unconfigured.
            # The shell now names the outstanding setup on that screen (proven in
            # `configured_setup_report_test.py`); what it still does not do is perform it.
            self.assertFalse((env.project / CONFIGURED).exists())


if __name__ == "__main__":
    unittest.main()
