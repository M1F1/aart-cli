"""CP-46 step 11: Installed shows what an agent here reaches, and `a` shows every project (§210).

The owner: Installed listed every installation on the machine, other projects' included, though an
agent working here can use only the user's installations and this project's. So Installed and
Updates show those by default, say how many other projects' they leave out, and `a` shows every
project's installation until it is pressed again.
"""

from __future__ import annotations

import dataclasses
import os
import unittest
from unittest import mock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli import tui
from aart_cli.application.consumer_ui import (
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    InstalledArtifactView,
    OwnershipView,
    project_activity,
    project_dashboard,
    project_installed_collection,
    reached_from,
)
from aart_cli.application.intents import InstalledHealth, MemberHealth
from aart_cli.domain.result import Ok
from aart_cli.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.consumer_application_e2e_test import BothBackendsMeasured, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, RIGHT, SPACE, TODAY, UP
from tests.install_credentials_test import _install

HERE = "/work/clients/shop"
ELSEWHERE = "/work/clients/bank"


def _view(name: str, *, scope: str, root: str = "", health: str = "ready") -> InstalledArtifactView:
    coordinate = f"company/mcp/{name}@1.0.0"
    return InstalledArtifactView(
        coordinate,
        health,
        (OwnershipView("direct", coordinate),),
        (),
        ("details", "verify", "uninstall"),
        scope=scope,
        harness="opencode",
        root=root,
    )


SHOP = _view("shop", scope="project", root=HERE, health="update")
BANK = _view("bank", scope="project", root=ELSEWHERE, health="update")
NOTES = _view("notes", scope="user", root="/home/someone")
KIT = project_installed_collection(
    "company/collection/kit@1.0.0", (MemberHealth(BANK.row, InstalledHealth.UPDATE),)
)


def _state(
    screen: ConsumerScreen = ConsumerScreen.INSTALLED,
    *,
    installed: tuple[InstalledArtifactView, ...] = (SHOP, BANK, NOTES),
    project_root: str = HERE,
    **fields,
) -> tuple[CanonicalScreenSource, ConsumerUiState]:
    source = CanonicalScreenSource(
        ConsumerScreens(
            project_dashboard(installed, registry_count=1),
            installed,
            project_activity((), today=TODAY),
            installed_collections=(KIT,),
            project_root=project_root,
        )
    )
    state = dataclasses.replace(
        ConsumerUiState(ConsumerSession(screen)), viewport_columns=120, viewport_rows=40, **fields
    )
    return source, _reload(source, state, entering=True)


def _press(source: CanonicalScreenSource, state: ConsumerUiState, key: str) -> ConsumerUiState:
    event = key_event(key, state)
    assert event is not None, key
    pressed, _ = reduce_consumer_ui(state, event)
    return _reload(source, pressed)


class ReachedFromTest(unittest.TestCase):
    @given(
        st.sampled_from(("project", "user", "")),
        st.sampled_from((HERE, ELSEWHERE, "")),
        st.sampled_from((HERE, ELSEWHERE, "")),
    )
    def test_an_agent_here_reaches_the_user_s_and_this_project_s(
        self, scope: str, root: str, here: str
    ) -> None:
        view = _view("any", scope=scope, root=root)

        # A project's installation is reached only from that project. Where the session knows no
        # project, or the record names no scope, nothing can be said to be elsewhere.
        expected = scope != "project" or not here or root == here
        self.assertIs(reached_from(view, here), expected)


class InstalledShowsWhatIsReachedHereTest(unittest.TestCase):
    def test_by_default_another_project_s_installation_is_left_out_and_counted(self) -> None:
        source, state = _state()

        self.assertEqual(state.rows, (SHOP.row, NOTES.row))
        drawn = "\n".join(frame(source, state))
        self.assertIn("1 installation in other projects is not shown", drawn)
        self.assertIn("[a] All projects", drawn)

    def test_a_shows_every_project_and_a_again_only_this_one(self) -> None:
        source, state = _state()

        everywhere = _press(source, state, "a")

        self.assertTrue(everywhere.installed_everywhere)
        self.assertEqual(everywhere.rows, (KIT.collection, BANK.row, SHOP.row, NOTES.row))
        drawn = "\n".join(frame(source, everywhere))
        self.assertIn("showing installations in every project", drawn.lower())
        self.assertIn("[a] This project", drawn)
        self.assertNotIn("not shown", drawn)

        back = _press(source, everywhere, "a")
        self.assertFalse(back.installed_everywhere)
        self.assertEqual(back.rows, state.rows)

    def test_updates_follows_the_same_toggle(self) -> None:
        source, state = _state(ConsumerScreen.UPDATES)

        self.assertEqual(state.rows, (SHOP.row,))
        self.assertEqual(_press(source, state, "a").rows, (SHOP.row, BANK.row))

    def test_updates_counts_only_the_updates_it_leaves_out(self) -> None:
        vault = _view("vault", scope="project", root=ELSEWHERE)
        source, state = _state(ConsumerScreen.UPDATES, installed=(SHOP, BANK, vault))

        self.assertIn(
            "1 installation in other projects is not shown", "\n".join(frame(source, state))
        )

    def test_nothing_is_said_when_nothing_is_left_out(self) -> None:
        source, state = _state(installed=(SHOP, NOTES))

        self.assertNotIn("other projects", "\n".join(frame(source, state)))

    def test_a_session_that_knows_no_project_leaves_nothing_out(self) -> None:
        _, state = _state(project_root="")

        self.assertEqual(state.rows, (KIT.collection, BANK.row, SHOP.row, NOTES.row))

    def test_the_footer_says_what_a_does_next(self) -> None:
        for screen in (ConsumerScreen.INSTALLED, ConsumerScreen.UPDATES):
            with self.subTest(screen=screen):
                state = ConsumerUiState(ConsumerSession(screen))
                offered = [item.label for item in key_bindings(state) if item.key == "a"]
                shown = dataclasses.replace(state, installed_everywhere=True)
                again = [item.label for item in key_bindings(shown) if item.key == "a"]
                self.assertEqual((offered, again), (["All projects"], ["This project"]))

    @given(st.integers(min_value=1, max_value=4))
    @settings(suppress_health_check=(HealthCheck.differing_executors,), max_examples=8)
    def test_a_toggles_installed_and_nothing_else(self, presses: int) -> None:
        source, state = _state()

        for _ in range(presses):
            state = _press(source, state, "a")

        self.assertIs(state.installed_everywhere, presses % 2 == 1)
        self.assertFalse(state.installed_details)
        self.assertFalse(state.marketplace_details)


class AnotherProjectSeesOnlyTheUserInstallationE2ETest(BothBackendsMeasured):
    """A real install, then Installed opened from another project over the same machine."""

    def test_another_project_sees_the_user_installation_and_a_shows_the_rest(self) -> None:
        seen: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

        def from_another_project(env, here) -> None:
            # Where it was installed, both are reached: one is the user's, one this project's.
            installed_here, _, _ = _drive(env, _at(ConsumerScreen.INSTALLED), actions=here)
            self.assertEqual(len(installed_here.rows), 2)
            other = env.project.parent / "another-project"
            other.mkdir()
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = tui._canonical_consumer_actions(  # noqa: SLF001
                    project=str(other), user_home=str(env.home), today=TODAY
                )
            assert isinstance(composed, Ok), composed
            handler = composed.value
            installed = handler.source().screens.installed
            by_harness = {item.harness: item.row for item in installed}
            default, _, _ = _drive(env, _at(ConsumerScreen.INSTALLED), actions=handler)
            everywhere, _, _ = _drive(env, _at(ConsumerScreen.INSTALLED), ord("a"), actions=handler)
            seen.append((default.rows, everywhere.rows))
            # Home counts what Installed lists here, so its numbers and the list agree.
            self.assertEqual(handler.source().screens.dashboard.installed_count, 1)
            self.assertEqual(default.rows, (by_harness["opencode"],))
            self.assertEqual(set(everywhere.rows), {by_harness["opencode"], by_harness["tabnine"]})

        # opencode goes to the user, tabnine stays in this project.
        finished, terminal, _, _, _ = _install(
            UP, ENTER, ENTER, scope=(DOWN, RIGHT, SPACE), after=from_another_project
        )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
