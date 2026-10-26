"""D-393: several installations ticked on Installed are uninstalled by one reviewed removal.

The operator: *"w installed daj mozliwosc zaznaczania wielu artefaktow np do uninstall"*. Installed
could only uninstall from one artifact's details, one at a time. This walks the real shell over a
real machine with two Skills installed, ticks both, and reads back that one confirmation removed
both trees and both records.
"""

from __future__ import annotations

import contextlib
import json
import os
import unittest
from unittest import mock

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.tui_consumer import run_consumer_shell
from tests.configured_install_command_e2e_test import COORDINATE, _environment
from tests.configured_installation_draft_e2e_test import _published_registries
from tests.configured_update_command_e2e_test import AUTHORED_FOR_TWO_1_2_0, TWO_HARNESSES
from tests.consumer_application_e2e_test import _actions, _Terminal
from tests.consumer_shell_test import DOWN, ENTER, ESCAPE, SPACE
from tests.placed_installation_e2e_test import AUTHORED_SKILL

SECOND = "company/skill/lint-review"
_LINT_MANIFEST = {
    "schema": "aart-cli.dev/skill/v1",
    "artifact": {"name": "lint-review", "kind": "skill"},
    "payload": {"include": ["SKILL.md"]},
    "compatibility": {"harnesses": ["claude"]},
}
LINT_SKILL = (
    ("lint-review/aart-cli.json", json.dumps(_LINT_MANIFEST)),
    ("lint-review/SKILL.md", "# Lint review\n\nName the rule a line breaks.\n"),
)


@contextlib.contextmanager
def _two_skills():
    """The configured registry approving both Skills, one promotion each, as a registry grows."""

    def both(_authored, **keywords):
        return _published_registries(AUTHORED_SKILL, LINT_SKILL, **keywords)

    with mock.patch("tests.configured_install_command_e2e_test._published_registry", both):
        with _environment() as env:
            yield env


def _delivered(env, name: str, harness: str = "claude"):
    return env.project / f".{harness}/skills/{name}-company-project/SKILL.md"


class InstalledMultiUninstallTest(unittest.TestCase):
    def _walk(self, env, *codes: int):
        handler = _actions(env)
        terminal = _Terminal(*codes)
        with mock.patch.dict(os.environ, env.xdg, clear=False):
            source = handler.source()
            empty = ConsumerUiState(ConsumerSession(ConsumerScreen.INSTALLED))
            state = ConsumerUiState(
                ConsumerSession(ConsumerScreen.INSTALLED), rows=source.rows(empty)
            )
            finished = run_consumer_shell(source, terminal, state=state, action_handler=handler)
        return finished, terminal, handler

    def _install(self, env, coordinate: str, *harnesses: str) -> None:
        profiles = (item for harness in harnesses for item in ("--profile", harness))
        code, installed = env.run("consume", "install", coordinate, *profiles, "--yes")
        self.assertEqual(code, 0, installed)

    def test_two_ticked_artifacts_are_removed_by_one_confirmation(self) -> None:
        with _two_skills() as env:
            for coordinate in (COORDINATE, SECOND):
                self._install(env, coordinate, "claude")
            for name in ("code-review", "lint-review"):
                self.assertTrue(_delivered(env, name).exists(), name)

            finished, terminal, handler = self._walk(env, SPACE, DOWN, SPACE, ord("u"), ENTER)

            review = terminal.screen_containing("/ Uninstall Review")
            self.assertIn("for 2 artifacts", review)
            self.assertIn(COORDINATE, review)
            self.assertIn(SECOND, review)
            for name in ("code-review", "lint-review"):
                self.assertFalse(_delivered(env, name).exists(), name)
            self.assertEqual(finished.session.screen, ConsumerScreen.ACTIVITY_DETAILS)
            self.assertEqual(handler.source().screens.installed, ())

    def test_u_without_a_tick_removes_the_row_under_the_cursor_only(self) -> None:
        with _two_skills() as env:
            for coordinate in (COORDINATE, SECOND):
                self._install(env, coordinate, "claude")

            _, terminal, handler = self._walk(env, DOWN, ord("u"), ENTER)

            self.assertNotIn("for 2 artifacts", terminal.screen_containing("/ Uninstall Review"))
            self.assertTrue(_delivered(env, "code-review").exists())
            self.assertFalse(_delivered(env, "lint-review").exists())
            self.assertEqual(len(handler.source().screens.installed), 1)

    def test_a_tick_left_behind_does_not_reach_the_details_being_read(self) -> None:
        with _two_skills() as env:
            for coordinate in (COORDINATE, SECOND):
                self._install(env, coordinate, "claude")

            # Tick code-review, then open lint-review's details and uninstall from there.
            _, terminal, _ = self._walk(env, SPACE, DOWN, ENTER, ord("u"), ENTER)

            self.assertNotIn("for 2 artifacts", terminal.screen_containing("/ Uninstall Review"))
            self.assertTrue(_delivered(env, "code-review").exists())
            self.assertFalse(_delivered(env, "lint-review").exists())

    def test_the_review_removes_nothing(self) -> None:
        with _two_skills() as env:
            for coordinate in (COORDINATE, SECOND):
                self._install(env, coordinate, "claude")

            finished, _, _ = self._walk(env, SPACE, DOWN, SPACE, ord("u"))

            self.assertIs(finished.session.screen, ConsumerScreen.UNINSTALL_REVIEW)
            for name in ("code-review", "lint-review"):
                self.assertTrue(_delivered(env, name).exists(), name)

    def test_one_artifact_in_two_harnesses_is_removed_by_one_confirmation(self) -> None:
        # B-183, now on the critical path: a Collection installed into two harnesses is removed
        # as one transaction (§173.6), so a removal is keyed by installation, as an install is.
        with _environment(authored=AUTHORED_FOR_TWO_1_2_0) as env:
            self._install(env, COORDINATE, *TWO_HARNESSES)

            finished, terminal, handler = self._walk(env, SPACE, DOWN, SPACE, ord("u"), ENTER)

            review = terminal.screen_containing("/ Uninstall Review")
            self.assertIn("for 2 artifacts", review)
            self.assertEqual(
                finished.session.screen, ConsumerScreen.ACTIVITY_DETAILS, terminal.last
            )
            for harness in TWO_HARNESSES:
                self.assertFalse(_delivered(env, "code-review", harness).exists(), harness)
            self.assertEqual(handler.source().screens.installed, ())

    def test_enter_after_the_receipt_returns_to_the_refreshed_installed_list(self) -> None:
        # D-400: *"jak wykonam uninstall w widoku installed to po kliknieciu enter na samym koncu
        # chce wrocic do widoku z zainstalowanymi paczkami"*. Enter opened the same receipt again.
        for key in (ENTER, ESCAPE):
            with self.subTest(key=key), _two_skills() as env:
                for coordinate in (COORDINATE, SECOND):
                    self._install(env, coordinate, "claude")

                finished, terminal, _ = self._walk(env, ord("u"), ENTER, key)

                self.assertIs(finished.session.screen, ConsumerScreen.INSTALLED, terminal.last)
                self.assertEqual(finished.session.history, (), finished.session.history)
                # §199: a row names the artifact as `name@version`.
                self.assertNotIn(f"{COORDINATE.rpartition('/')[2]}@", terminal.last)
                self.assertIn(f"{SECOND.rpartition('/')[2]}@", terminal.last)

    def test_an_uninstall_from_details_also_returns_to_installed(self) -> None:
        with _two_skills() as env:
            for coordinate in (COORDINATE, SECOND):
                self._install(env, coordinate, "claude")

            finished, terminal, _ = self._walk(env, ENTER, ord("u"), ENTER, ENTER)

            self.assertIs(finished.session.screen, ConsumerScreen.INSTALLED, terminal.last)
            self.assertIn(
                "[Enter] Back to Installed", terminal.screen_containing("/ Activity Details")
            )


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
