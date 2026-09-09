"""The persistent application installs, repairs and removes on a real machine (B-025).

This is the evidence for the default terminal route. The shell under test is the one the curses
adapter runs -- only `draw` and `getch` are faked -- and the handler under it is the production
composition, acting on a temporary machine with a real configured registry, a real object store and
real receipts. Nothing between the keystroke and the file on disk is a double.

Three properties are what make the route safe to take.

A review writes nothing. Somebody can open an install, read it and walk away, and the machine is
untouched.

What is drawn afterwards was read back off the machine. The success screen and the Installed screen
come from a receipt store re-read after the effects finished, not from what the action believed it
did.

And a refusal is drawn rather than raised. A terminal application that threw on an artifact that
failed to resolve would take the session down with it, so the reason appears under the screen it
was asked from and the session stays where it was.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import pathlib
import shutil
import stat
import unittest
from unittest import mock

from agent_artifacts import tui
from agent_artifacts.application.consumer_ui import ConsumerUiState, opening_state
from agent_artifacts.application.consumer_views import (
    SETTING_ROWS,
    ConsumerScreen,
    ConsumerSession,
    PresentationProfile,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.tui_consumer import run_consumer_shell
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.consumer_shell_test import ENTER, SPACE, FakeTerminal

TODAY = dt.date(2026, 9, 1)
OFFERED = "company/skill/code-review@1.2.0"


def _delivered(env) -> pathlib.Path:
    return env.project / ".claude/skills/code-review/SKILL.md"


def _delete_delivery(env) -> None:
    """Lose the delivered tree the way it is actually lost, read-only modes and all."""

    tree = _delivered(env).parent
    for root, directories, files in os.walk(tree):
        for name in (*directories, *files):
            path = os.path.join(root, name)
            os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)
    os.chmod(tree, os.stat(tree).st_mode | stat.S_IWUSR)
    shutil.rmtree(tree)


def _actions(env):
    """The production composition, over this machine and nothing else."""

    with mock.patch.dict(os.environ, env.xdg, clear=False):
        composed = tui._canonical_consumer_actions(
            project=str(env.project), user_home=str(env.home), today=TODAY
        )
    assert isinstance(composed, Ok), composed
    return composed.value


class _Terminal(FakeTerminal):
    """The scripted terminal, and the answer to what a pending selection asks on the way out."""

    def __init__(self, *codes: int) -> None:
        super().__init__(*codes)
        self._codes.append(ord("y"))


def _at(screen: ConsumerScreen, **fields) -> ConsumerUiState:
    return ConsumerUiState(ConsumerSession(screen), **fields)


def _drive(env, state: ConsumerUiState, *codes: int, actions=None):
    handler = actions or _actions(env)
    terminal = _Terminal(*codes)
    with mock.patch.dict(os.environ, env.xdg, clear=False):
        finished = run_consumer_shell(
            handler.source(),
            terminal,
            state=state,
            action_handler=handler,
            settings_writer=handler.save_settings,
        )
    return finished, terminal, handler


#: Marketplace to installed, one screen at a time: review the selection, read what was inspected,
#: accept what has to be prepared first, then confirm the plan that was reviewed.
_INSTALL = (SPACE, ord("i"), ENTER, ENTER, ENTER, ENTER)


class ConsumerApplicationInstallTest(unittest.TestCase):
    def test_the_marketplace_offers_what_the_configured_registry_approved(self) -> None:
        with _environment() as env:
            _, terminal, _ = _drive(env, _at(ConsumerScreen.MARKETPLACE))

            self.assertIn(OFFERED, terminal.last)

    def test_a_review_names_the_plan_and_leaves_the_machine_alone(self) -> None:
        with _environment() as env:
            finished, terminal, _ = _drive(env, _at(ConsumerScreen.MARKETPLACE), SPACE, ord("i"))

            self.assertEqual(finished.session.screen, ConsumerScreen.REVIEW_SELECTION)
            self.assertTrue(finished.session.review_digest)
            self.assertTrue(terminal.screen_containing("will be installed"))
            self.assertFalse(
                _delivered(env).exists(), "reviewing an install wrote it to the harness"
            )

    def test_a_confirmed_install_places_the_artifact_and_draws_what_it_left(self) -> None:
        with _environment() as env:
            finished, terminal, handler = _drive(env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL)

            self.assertEqual(finished.session.screen, ConsumerScreen.SUCCESS)
            self.assertTrue(_delivered(env).exists(), "the Skill never reached the harness")
            self.assertTrue(terminal.screen_containing("AART / Installing"))
            self.assertTrue(terminal.screen_containing("AART / Success"))
            # Drawn from the machine as it was read afterwards, not from what the install intended.
            self.assertEqual(
                [item.coordinate for item in handler.source().screens.installed], [OFFERED]
            )

    def test_installing_the_same_offer_twice_converges_instead_of_installing_twice(self) -> None:
        with _environment() as env:
            _, _, handler = _drive(env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL)

            _drive(env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL, actions=handler)

            installed = handler.source().screens.installed
            self.assertEqual([item.coordinate for item in installed], [OFFERED])
            self.assertEqual(installed[0].health, "ready")


class ConsumerApplicationLifecycleTest(unittest.TestCase):
    def _installed(self, env):
        _, _, handler = _drive(env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL)
        assert _delivered(env).exists()
        return handler

    def test_verify_and_repair_puts_back_what_was_lost(self) -> None:
        with _environment() as env:
            handler = self._installed(env)
            _delete_delivery(env)

            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus=OFFERED),
                ord("r"),
                ENTER,
                actions=handler,
            )

            self.assertTrue(_delivered(env).exists(), "the repair never restored the delivery")
            self.assertEqual(finished.session.screen, ConsumerScreen.ACTIVITY_DETAILS)
            self.assertTrue(terminal.screen_containing("AART / Verify Repair"))

    def test_a_repair_review_measures_and_changes_nothing(self) -> None:
        with _environment() as env:
            handler = self._installed(env)
            _delete_delivery(env)

            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus=OFFERED),
                ord("r"),
                actions=handler,
            )

            self.assertEqual(finished.session.screen, ConsumerScreen.VERIFY_REPAIR)
            # The review names the one component that drifted, not the whole installation.
            self.assertTrue(
                terminal.screen_containing("Components changing: delivery:claude"), terminal.last
            )
            self.assertFalse(_delivered(env).exists(), "reviewing a repair carried it out")

    def test_uninstall_removes_only_this_artifact_and_forgets_the_record(self) -> None:
        with _environment() as env:
            handler = self._installed(env)
            neighbour = _delivered(env).parent.parent / "somebody-elses-skill"
            neighbour.mkdir()

            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus=OFFERED),
                ord("u"),
                ENTER,
                actions=handler,
            )

            self.assertTrue(terminal.screen_containing("AART / Uninstall Review"))
            self.assertEqual(finished.session.screen, ConsumerScreen.ACTIVITY_DETAILS)
            self.assertFalse(_delivered(env).exists(), "the Skill outlived its uninstall")
            self.assertTrue(neighbour.is_dir(), "the uninstall took a neighbour with it")
            self.assertEqual(handler.source().screens.installed, ())

    def test_an_uninstall_review_removes_nothing(self) -> None:
        with _environment() as env:
            handler = self._installed(env)

            finished, _, _ = _drive(
                env,
                _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus=OFFERED),
                ord("u"),
                actions=handler,
            )

            self.assertEqual(finished.session.screen, ConsumerScreen.UNINSTALL_REVIEW)
            self.assertTrue(_delivered(env).exists(), "reviewing a removal carried it out")


class ConsumerApplicationSettingsTest(unittest.TestCase):
    """Screen 28 keeps what it was told, or it is not a Settings screen (spec 161.10)."""

    def test_a_preference_survives_the_session_it_was_chosen_in(self) -> None:
        with _environment() as env:
            _, _, _ = _drive(
                env,
                _at(ConsumerScreen.SETTINGS, rows=SETTING_ROWS, cursor=3),
                ENTER,
            )

            # A second composition, reading the same machine from scratch, the way a later
            # `aart` on a terminal would.
            reopened = _actions(env)

            self.assertTrue(reopened.settings.maintainer_mode)
            self.assertIs(reopened.settings.profile, PresentationProfile.FAST)
            opened = dataclasses.replace(
                opening_state(reopened.settings),
                session=ConsumerSession(ConsumerScreen.SETTINGS),
            )
            _, terminal, _ = _drive(env, opened, actions=reopened)
            self.assertTrue(terminal.screen_containing("Maintainer Mode: on"), terminal.last)

    def test_the_chosen_scope_is_the_scope_the_next_install_lands_at(self) -> None:
        """Screen 28 offers `Default scope: Project/User`, so choosing User has to install into
        the user's home. A preference the application draws and then ignores is worse than one it
        never offered: the operator reads it as a promise about where their files went."""

        with _environment() as env:
            _drive(env, _at(ConsumerScreen.SETTINGS, rows=SETTING_ROWS, cursor=1), ENTER)
            chosen = _actions(env)
            self.assertEqual("user", chosen.settings.default_scope)

            _drive(env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL, actions=chosen)

            self.assertTrue(
                (env.home / ".claude/skills/code-review/SKILL.md").exists(),
                "the user-scope install never reached the user home",
            )
            self.assertFalse(
                _delivered(env).exists(), "a user-scope install wrote into the project"
            )

    def test_a_detail_level_chosen_with_v_reopens_at_that_level(self) -> None:
        with _environment() as env:
            _drive(env, _at(ConsumerScreen.ACTIVITY), ord("v"))

            reopened = _actions(env)
            opened = opening_state(reopened.settings)

            self.assertIs(reopened.settings.profile, PresentationProfile.VERBOSE)
            # The session opens at the stored level rather than rewriting it back to Fast.
            self.assertIs(opened.session.profile, PresentationProfile.VERBOSE)


class ConsumerApplicationRefusalTest(unittest.TestCase):
    def test_an_action_on_something_that_is_not_installed_is_drawn_not_raised(self) -> None:
        with _environment() as env:
            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus="company/skill/absent@9.9.9"),
                ord("u"),
            )

            self.assertTrue(finished.exited, "a refusal took the application down")
            # `QA-018`/`D-184`: the refusal is drawn on the screen the action was asked from, not
            # on a review that would go on offering to uninstall something that is not there.
            self.assertEqual(finished.session.screen, ConsumerScreen.INSTALLED_ARTIFACT_DETAILS)
            self.assertTrue(
                terminal.screen_containing("nothing canonical is installed here"),
                terminal.last,
            )
            self.assertIsNone(finished.session.review_digest)
            self.assertIsNone(finished.action)

    def test_an_offer_that_is_no_longer_there_is_refused_where_it_was_asked(self) -> None:
        """The registry moved on after the Marketplace was read, and the install is not guessed."""

        with _environment() as env:
            handler = _actions(env)
            env.publish(AUTHORED_MCP)

            finished, terminal, _ = _drive(
                env, _at(ConsumerScreen.MARKETPLACE), *_INSTALL, actions=handler
            )

            self.assertTrue(finished.exited, "a vanished offer took the application down")
            # Where it was asked is Artifact Details (`QA-018`/`D-184`) -- the screen the install
            # was requested from -- not the review of a plan that was never prepared.
            self.assertEqual(finished.session.screen, ConsumerScreen.ARTIFACT_DETAILS)
            self.assertIsNone(finished.session.review_digest)
            self.assertIsNone(finished.action)
            self.assertFalse(_delivered(env).exists())
            self.assertTrue(
                terminal.screen_containing("no approved published version of skill/code-review"),
                terminal.last,
            )


if __name__ == "__main__":
    unittest.main()
