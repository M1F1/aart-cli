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
import pathlib
import sys
import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession
from agent_artifacts.domain.result import Ok
from agent_artifacts.install_state.paths import install_state_paths
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
class ConfiguredReceiptVerbsTest(unittest.TestCase):
    """B-046: the setup run a configured install performed is one the receipt verbs can find.

    B-044 made the run happen; this is the other half of it being real. A setup run nobody can
    show, verify or undo is one the operator has to take on faith and cannot roll back, and until
    the receipt-backed locator existed that was exactly the state a configured install left behind:
    the effect on disk, the record under the data root, and `aart marketplace receipt show`
    answering that this scope has no installation state.

    Nothing here is a fixture. The install is the public command, the receipt is the one it wrote,
    and the record is the one the engine persisted -- so the pointer being followed is the one a
    real install produces, not one this test composed.
    """

    def _installed(self, env):
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
        self.assertEqual(payload["setup"]["configured"], 1)
        # The premise of B-046 in one line: this route writes no install-state manifest, so the
        # pointer the receipt verbs follow cannot be the manifest's.
        self.assertFalse(
            pathlib.Path(
                install_state_paths(
                    "project",
                    project_root=str(env.project),
                    user_home=str(env.home),
                    data_root=env.paths.data_root,
                ).destination_path
            ).exists()
        )
        return payload

    def test_show_finds_the_run_a_configured_install_performed(self) -> None:
        with _declaring_setup() as env:
            self._installed(env)

            code, text = env.run_text("marketplace", "receipt", "show", COORDINATE)

            self.assertEqual(code, 0, text)
            self.assertIn("Setup receipt", text)
            self.assertIn("status          configured", text)
            self.assertIn(COORDINATE, text)

    def test_verify_asks_the_filesystem_about_the_effect_the_install_applied(self) -> None:
        with _declaring_setup() as env:
            self._installed(env)

            code, text = env.run_text("marketplace", "receipt", "verify", COORDINATE)

            self.assertEqual(code, 0, text)
            self.assertIn("false=0", text)

            (env.project / CONFIGURED).unlink()
            code, text = env.run_text("marketplace", "receipt", "verify", COORDINATE)

            # A claim that is no longer true is a finding, and a finding must not report success.
            self.assertNotEqual(code, 0, text)
            self.assertIn("false=1", text)

    def test_undo_reviews_first_and_then_reverses_what_the_install_configured(self) -> None:
        with _declaring_setup() as env:
            self._installed(env)
            self.assertTrue((env.project / CONFIGURED).exists())

            code, text = env.run_text("marketplace", "receipt", "undo", COORDINATE)
            self.assertEqual(code, 0, text)
            self.assertIn("re-run with --yes to apply this exact undo", text)
            self.assertTrue(
                (env.project / CONFIGURED).exists(), "a review must not change anything"
            )

            code, text = env.run_text("marketplace", "receipt", "undo", COORDINATE, "--yes")

            self.assertEqual(code, 0, text)
            self.assertFalse((env.project / CONFIGURED).exists())

    def test_an_install_that_declined_setup_is_shown_as_cancelled_with_its_way_back(self) -> None:
        """Declining setup still records the attempt, and the record is what an operator needs.

        This was measured rather than assumed, and the measurement corrected the expectation: a
        configured install that is not given `--approve-setup-effects` writes a record whose
        status is `cancelled`, whose steps say the run applied no effect, and which carries the
        exact retry command. `receipt show` finding that is strictly better than the refusal a
        run-less installation gets, because the answer names the thing to do next instead of
        leaving the operator to work out that setup was ever declared.
        """

        with _declaring_setup() as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(code, 0, payload)
            self.assertFalse((env.project / CONFIGURED).exists())

            code, text = env.run_text("marketplace", "receipt", "show", COORDINATE)

            self.assertEqual(code, 0, text)
            self.assertIn("status          cancelled", text)
            self.assertIn("this run applied no effect", text)
            self.assertIn("--approve-setup-effects", text)

    def test_verify_makes_no_live_claim_about_a_run_that_applied_nothing(self) -> None:
        """A cancelled run licenses no claim, and reporting one would be the worst outcome here."""

        with _declaring_setup() as env:
            env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")

            code, text = env.run_text("marketplace", "receipt", "verify", COORDINATE)

            self.assertEqual(code, 0, text)
            self.assertIn("false=0", text)
            self.assertNotIn(CONFIGURED, text)


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
