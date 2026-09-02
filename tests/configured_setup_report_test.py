"""The configured seam says which installed artifact is still unconfigured.

B-044's first gate, on the route that does not have it. `tests/configured_setup_gap_test.py`
characterizes an install that reports success for an artifact whose declared setup never ran; on
the legacy route the same install at least *names* the setup it did not perform
(`marketplace_lifecycle_e2e_test.py::DeclaredSetupE2ETest`), so an operator knows there is work
left. The configured seam emitted no `setup` key and drew no line, so the omission was silent --
which is worse than not running setup, because nothing points at the outstanding work.

This is what the receipt's object identity (D-122) is first spent on. Setup is declared on the
package manifest, not on anything the installation plan carries, so saying "this artifact declares
setup" means going back to the immutable object the installation came from -- which is exactly the
thing the canonical receipt could not name until it recorded `object_digest`.

Reporting is not performing, and these tests hold that line: the configured file the recipe writes
is still absent afterwards. What changes is that the absence is now stated rather than hidden.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import ConsumerScreen, ConsumerSession
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    SourceAlias,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.tui_consumer import run_consumer_shell
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AuthoredSetup
from tests.configured_setup_gap_test import AUTHORED, CONFIGURED, COORDINATE, RECIPE
from tests.consumer_shell_test import ENTER, SPACE, FakeTerminal

TODAY = dt.date(2026, 9, 1)


def _declaring_setup():
    return _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE))


class ConfiguredInstallCommandReportTest(unittest.TestCase):
    def test_the_install_names_the_setup_it_did_not_run(self) -> None:
        with _declaring_setup() as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertEqual(
                payload["pending_setup"],
                [
                    {
                        "coordinate": "company/skill/code-review@1.2.0",
                        "object_digest": payload["pending_setup"][0]["object_digest"],
                        "recipe": "setup/installer.json",
                        "platforms": ["darwin"],
                        "manual": "SETUP.md",
                    }
                ],
            )
            # Still B-044: naming the work is not doing it.
            self.assertFalse((env.project / CONFIGURED).exists())

    def test_the_named_object_is_the_one_the_receipt_recorded(self) -> None:
        """The report is derived from the durable record, not from what the action believed.

        An install that reported a setup declaration read off the plan it just executed would be
        reporting its own intention back to itself. What is asserted here is that the object the
        report names is the object the receipt on disk names -- so the report is a statement about
        the machine, and it stays true for a reader that arrives afterwards.
        """

        with _declaring_setup() as env:
            _, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            store = LocalReceiptStore(str(pathlib.Path(env.paths.data_root) / "state"))
            record = store.record(
                ArtifactCoordinate(
                    SourceAlias("company"), ArtifactIdentity("skill", "code-review"), "1.2.0"
                )
            )
            self.assertIsInstance(record, Ok, getattr(record, "diagnostics", ()))
            assert isinstance(record, Ok)

            self.assertEqual(
                payload["pending_setup"][0]["object_digest"],
                str(record.value.receipt.object_digest),
            )

    def test_an_artifact_that_declares_no_setup_is_not_reported_as_pending(self) -> None:
        """The key is absent, not an empty list every install now carries."""

        with _environment() as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertNotIn("pending_setup", payload)

    def test_the_text_output_names_it_too(self) -> None:
        with _declaring_setup() as env:
            code, text = env.run_text(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, text)
            self.assertIn("setup", text.lower())
            self.assertIn("company/skill/code-review@1.2.0", text)


class ConsumerShellReportTest(unittest.TestCase):
    def test_the_shell_names_the_setup_that_did_not_run(self) -> None:
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
                any(any("etup" in line for line in frame) for frame in terminal.frames),
                "no drawn frame says the installed Skill is still unconfigured",
            )
            self.assertFalse((env.project / CONFIGURED).exists())


if __name__ == "__main__":
    unittest.main()
