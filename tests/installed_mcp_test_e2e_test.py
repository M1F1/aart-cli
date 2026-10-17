"""D-395: the MCP test is asked for from Installed, for one or several installations.

The operator: *"w jaki sposob teraz w TUI moge sobie odpalic testy dla jednego lub wiecej mcp?"*.
The only TUI route was the offer on Success right after an install (§170.4); once past it, an
installed MCP could be tested from the command line alone. Installed now binds `[t] Test MCP` over
what is ticked, or the row under the cursor, and Installed Artifact Details over its one
installation (§170.4, INV-254). This walks the real shell over a machine with one MCP and one Skill
installed.
"""

from __future__ import annotations

import contextlib
import os
import unittest
from unittest import mock

from aart_cli.application.consumer_ui import ConsumerActionKind, ConsumerUiState
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.tui_consumer import run_consumer_shell
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import _published_registries
from tests.consumer_application_e2e_test import _actions, _Terminal
from tests.consumer_shell_test import DOWN, ENTER, SPACE, UP
from tests.installed_multi_uninstall_e2e_test import LINT_SKILL
from tests.post_install_mcp_test_test import _DECLARED, _manifest, _records, _Watched

MCP = "company/mcp/dummy@1.0.0"
SKILL = "company/skill/lint-review@1.0.0"


@contextlib.contextmanager
def _installed():
    """One MCP in opencode and claude, and one Skill in claude, installed from the command line."""

    def both(_authored, **keywords):
        return _published_registries(_manifest(_DECLARED), LINT_SKILL, **keywords)

    with mock.patch("tests.configured_install_command_e2e_test._published_registry", both):
        with _environment() as env:
            for coordinate, harnesses in ((MCP, ("opencode", "claude")), (SKILL, ("claude",))):
                profiles = [item for harness in harnesses for item in ("--profile", harness)]
                code, said = env.run("consume", "install", coordinate, *profiles, "--yes")
                assert code == 0, said
            yield env


class InstalledMcpTestTest(unittest.TestCase):
    def _walk(self, env, *codes: int):
        handler = _actions(env)
        watched = _Watched(env)
        handler._mcp_test = watched
        terminal = _Terminal(*codes)
        with mock.patch.dict(os.environ, env.xdg, clear=False):
            source = handler.source()
            empty = ConsumerUiState(ConsumerSession(ConsumerScreen.INSTALLED))
            state = ConsumerUiState(
                ConsumerSession(ConsumerScreen.INSTALLED), rows=source.rows(empty)
            )
            finished = run_consumer_shell(source, terminal, state=state, action_handler=handler)
        return finished, terminal, watched

    def _to(self, env, row: str) -> tuple[int, ...]:
        handler = _actions(env)
        with mock.patch.dict(os.environ, env.xdg, clear=False):
            rows = handler.source().rows(ConsumerUiState(ConsumerSession(ConsumerScreen.INSTALLED)))
        return (DOWN,) * rows.index(row)

    def test_the_row_under_the_cursor_is_reviewed_before_anything_runs(self) -> None:
        with _installed() as env:
            offered, terminal, watched = self._walk(
                env, *self._to(env, f"{MCP}#opencode"), ord("t")
            )

        self.assertIs(offered.session.screen, ConsumerScreen.MCP_TEST, terminal.last)
        self.assertIs(offered.action, ConsumerActionKind.MCP_TEST)
        self.assertIn(f"{MCP}#opencode: read_identity {{}}", terminal.last)
        self.assertNotIn(f"{MCP}#claude", terminal.last)
        self.assertIn("configured service", terminal.last)
        self.assertIsNone(watched.before_run)

    def test_two_ticked_installations_are_tested_together_and_change_nothing(self) -> None:
        with _installed() as env:
            down = self._to(env, f"{MCP}#claude")
            other = len(self._to(env, f"{MCP}#opencode")) - len(down)
            codes = (*down, SPACE, *((DOWN,) * other if other > 0 else ()), SPACE)
            assert other > 0, "the opencode row is drawn after the claude one"
            tested, terminal, watched = self._walk(env, *codes, ord("t"), ENTER)
            after = _records(env)

        self.assertIs(tested.session.screen, ConsumerScreen.MCP_TEST, terminal.last)
        self.assertIsNone(tested.action)
        self.assertEqual(terminal.last.count("✓"), 2, terminal.last)
        self.assertIn("mcp-startup-and-protocol", terminal.last)
        self.assertEqual(after, watched.before_run)

    def test_the_answer_returns_to_installed(self) -> None:
        with _installed() as env:
            back, terminal, _ = self._walk(
                env, *self._to(env, f"{MCP}#opencode"), ord("t"), ENTER, ENTER
            )

        self.assertIs(back.session.screen, ConsumerScreen.INSTALLED, terminal.last)

    def test_a_ticked_skill_is_refused_by_name_and_nothing_runs(self) -> None:
        with _installed() as env:
            mcp = self._to(env, f"{MCP}#opencode")
            skill = self._to(env, f"{SKILL}#claude")
            first, second = sorted((mcp, skill), key=len)
            codes = (*first, SPACE, *((DOWN,) * (len(second) - len(first))), SPACE, ord("t"))
            refused, terminal, watched = self._walk(env, *codes)

        self.assertIs(refused.session.screen, ConsumerScreen.INSTALLED, terminal.last)
        self.assertTrue(terminal.screen_containing(f"{SKILL}#claude is not an MCP"), terminal.last)
        self.assertIsNone(watched.before_run)

    def test_installed_artifact_details_tests_its_one_installation(self) -> None:
        with _installed() as env:
            offered, terminal, _ = self._walk(
                env, *self._to(env, f"{MCP}#claude"), ENTER, ord("t"), ENTER
            )

        self.assertIs(offered.session.screen, ConsumerScreen.MCP_TEST, terminal.last)
        self.assertIn(f"✓ {MCP}#claude", terminal.last)
        self.assertNotIn(f"{MCP}#opencode", terminal.last)

    def test_a_tick_left_on_the_list_does_not_reach_an_open_details_screen(self) -> None:
        with _installed() as env:
            ticked = self._to(env, f"{MCP}#opencode")
            opened = self._to(env, f"{MCP}#claude")
            moves = len(ticked) - len(opened)
            assert moves > 0, "the claude row is drawn before the opencode one"
            offered, terminal, _ = self._walk(env, *ticked, SPACE, *(UP,) * moves, ENTER, ord("t"))

        self.assertIs(offered.session.screen, ConsumerScreen.MCP_TEST, terminal.last)
        review = terminal.screen_containing("read_identity")
        self.assertIn(f"{MCP}#claude: read_identity", review)
        self.assertNotIn(f"{MCP}#opencode", review)


if __name__ == "__main__":  # pragma: no cover - unittest entry point
    unittest.main()
