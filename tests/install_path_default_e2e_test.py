"""§173.7: after Install, a person chooses the Default path or the Custom one on screen 05p.

Default takes the harnesses, scope and Python installer from Settings and goes straight to what
still needs entering, or to Ready: 05 and 07a are never drawn. The harnesses are the Settings ones
that are detected and can host the artifact; with none in Settings, every detected one that can.
Custom is the §172 flow from 05. Settings keeps the default harnesses beside the default scope.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_views import (
    INSTALL_PATH_CUSTOM,
    ConsumerScreen,
    ConsumerSettings,
    HarnessTargetView,
    default_harness_row,
    pair_key,
    settings_from_data,
    settings_pairs,
    settings_to_data,
)
from aart_cli.domain.result import Ok
from aart_cli.io.consumer_settings import read_consumer_settings
from tests.configured_install_command_e2e_test import _environment
from tests.configured_update_command_e2e_test import AUTHORED_FOR_TWO_1_2_0, TWO_HARNESSES
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, ESCAPE, SPACE

# Tick the Skill on Marketplace, press Install, and take the row 05p's cursor is on.
_DEFAULT = (SPACE, ord("i"), ENTER)


def _delivered(env, harness: str):
    return env.project / f".{harness}/skills/code-review-company-project/SKILL.md"


def _with_settings(env, settings: ConsumerSettings):
    base = _actions(env)
    return type(base)(replace(base._context, settings=settings))  # noqa: SLF001


class DefaultPathTest(unittest.TestCase):
    def _install(self, settings: ConsumerSettings, *codes: int):
        with _environment(authored=AUTHORED_FOR_TWO_1_2_0) as env:
            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.MARKETPLACE, settings=settings),
                *codes,
                actions=_with_settings(env, settings),
            )
            delivered = {harness: _delivered(env, harness).exists() for harness in TWO_HARNESSES}
        return finished, terminal, delivered

    def test_default_installs_into_the_settings_harness_without_05_or_07a(self) -> None:
        settings = ConsumerSettings(default_harnesses=("opencode",))

        finished, terminal, delivered = self._install(settings, *_DEFAULT, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(delivered, {"claude": False, "opencode": True})
        path = terminal.screen_containing("/ Install Path")
        self.assertIn("Harnesses: opencode", path)
        self.assertIn("Scope: Project", path)
        self.assertEqual(terminal.screen_containing("/ Review Selection"), "", "05 drawn")
        self.assertEqual(terminal.screen_containing("/ Scope"), "", "07a drawn")

    def test_default_with_no_settings_harness_uses_every_one_that_can_host_it(self) -> None:
        finished, terminal, delivered = self._install(ConsumerSettings(), *_DEFAULT, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(delivered, {"claude": True, "opencode": True})
        self.assertEqual(terminal.screen_containing("/ Review Selection"), "")

    def test_default_takes_the_settings_scope(self) -> None:
        settings = ConsumerSettings(default_scope="user", default_harnesses=("claude",))
        with _environment(authored=AUTHORED_FOR_TWO_1_2_0) as env:
            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.MARKETPLACE, settings=settings),
                *_DEFAULT,
                ENTER,
                actions=_with_settings(env, settings),
            )
            in_home = (env.home / ".claude/skills").exists()
            in_project = _delivered(env, "claude").exists()

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertTrue(in_home, terminal.last)
        self.assertFalse(in_project)

    def test_a_settings_harness_that_cannot_host_it_is_named_and_05p_stays(self) -> None:
        settings = ConsumerSettings(default_harnesses=("codex",))

        finished, terminal, delivered = self._install(settings, *_DEFAULT)

        # §176: no silent jump to 05; 05p says which value does not fit, and Custom is next.
        self.assertIs(finished.session.screen, ConsumerScreen.INSTALL_PATH, terminal.last)
        self.assertEqual(delivered, {"claude": False, "opencode": False})
        self.assertIn("can't install with your Settings:", terminal.last)
        self.assertIn("harness codex", terminal.last)
        self.assertIn("Default (not available with these Settings)", terminal.last)
        self.assertIn("> Custom", terminal.last)
        self.assertEqual(finished.current_row, INSTALL_PATH_CUSTOM)
        self.assertIsNone(finished.action)

    def test_a_partial_fit_installs_nothing_rather_than_into_the_subset(self) -> None:
        settings = ConsumerSettings(default_harnesses=("opencode", "codex"))

        finished, terminal, delivered = self._install(settings, *_DEFAULT)

        # Before §176 this installed into opencode alone and said nothing about codex.
        self.assertIs(finished.session.screen, ConsumerScreen.INSTALL_PATH, terminal.last)
        self.assertEqual(delivered, {"claude": False, "opencode": False})
        self.assertIn("harness codex", terminal.last)
        self.assertNotIn("harness opencode", terminal.last)

    def test_custom_after_the_block_is_the_05_flow_and_installs_what_was_chosen(self) -> None:
        settings = ConsumerSettings(default_harnesses=("codex",))

        finished, terminal, _ = self._install(settings, *_DEFAULT, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.REVIEW_SELECTION, terminal.last)

    def test_default_again_checks_again_and_changes_nothing(self) -> None:
        settings = ConsumerSettings(default_harnesses=("codex",))

        finished, terminal, delivered = self._install(settings, *_DEFAULT, ord("k"), ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.INSTALL_PATH, terminal.last)
        self.assertEqual(delivered, {"claude": False, "opencode": False})
        self.assertIn("can't install with your Settings:", terminal.last)

    def test_custom_is_the_05_flow(self) -> None:
        finished, terminal, delivered = self._install(
            ConsumerSettings(default_harnesses=("opencode",)), SPACE, ord("i"), DOWN, ENTER
        )

        self.assertIs(finished.session.screen, ConsumerScreen.REVIEW_SELECTION, terminal.last)
        self.assertEqual(delivered, {"claude": False, "opencode": False})

    def test_back_from_05p_returns_to_the_marketplace_and_installs_nothing(self) -> None:
        finished, terminal, delivered = self._install(ConsumerSettings(), SPACE, ord("i"), ESCAPE)

        self.assertIs(finished.session.screen, ConsumerScreen.MARKETPLACE, terminal.last)
        self.assertEqual(delivered, {"claude": False, "opencode": False})


class DefaultHarnessSettingTest(unittest.TestCase):
    def test_settings_lists_each_detected_harness_and_keeps_what_was_turned_on(self) -> None:
        with _environment(authored=AUTHORED_FOR_TWO_1_2_0) as env:
            handler = _actions(env)
            rows = handler.source().rows(_at(ConsumerScreen.SETTINGS))
            at = rows.index(default_harness_row("opencode"))
            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.SETTINGS, rows=rows, cursor=at),
                ENTER,
                actions=handler,
            )
            stored = read_consumer_settings(str(env.paths.data_root))

        for harness in TWO_HARNESSES:
            self.assertIn(default_harness_row(harness), rows)
        self.assertEqual(finished.settings.default_harnesses, ("opencode",))
        self.assertIn("Default harness opencode: on", terminal.last)
        self.assertIsInstance(stored, Ok, stored)
        self.assertEqual(stored.value.default_harnesses, ("opencode",))

    def test_stored_harnesses_round_trip_and_a_bad_one_is_refused(self) -> None:
        settings = ConsumerSettings(default_harnesses=("opencode", "claude"))

        self.assertEqual(settings_from_data(settings_to_data(settings)), Ok(settings))
        for bad in (["claude", "claude"], ["a b"], "claude", [1]):
            with self.subTest(bad=bad):
                read = settings_from_data({"default_harnesses": bad})
                self.assertNotIsInstance(read, Ok)


_HARNESS = st.sampled_from(("claude", "codex", "opencode", "tabnine"))
_ARTIFACT = st.sampled_from(("company/mcp/github", "company/skill/review", "company/mcp/jira"))


class SettingsPairsPropertyTest(unittest.TestCase):
    @given(
        st.dictionaries(_HARNESS, st.sets(_ARTIFACT, min_size=1), max_size=4),
        st.lists(_HARNESS, unique=True, max_size=4),
    )
    def test_each_artifact_goes_exactly_into_the_settings_harnesses_that_host_it(
        self, hosted, chosen
    ) -> None:
        targets = tuple(
            HarnessTargetView(harness, tuple(sorted(artifacts)))
            for harness, artifacts in hosted.items()
        )

        pairs = settings_pairs(targets, tuple(chosen))

        expected = {
            pair_key(artifact, harness)
            for harness, artifacts in hosted.items()
            if not chosen or harness in chosen
            for artifact in artifacts
        }
        self.assertEqual(set(pairs), expected)
        self.assertEqual(len(set(pairs)), len(pairs))

    @given(st.lists(_HARNESS, unique=True, max_size=4))
    def test_stored_default_harnesses_read_back_as_chosen(self, chosen) -> None:
        settings = ConsumerSettings(default_harnesses=tuple(chosen))

        self.assertEqual(settings_from_data(settings_to_data(settings)), Ok(settings))
        for harness in chosen:
            toggled = settings.toggled(default_harness_row(harness))
            self.assertNotIn(harness, toggled.default_harnesses)
            self.assertEqual(
                toggled.toggled(default_harness_row(harness)).default_harnesses,
                (*toggled.default_harnesses, harness),
            )


if __name__ == "__main__":
    unittest.main()
