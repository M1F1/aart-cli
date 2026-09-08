"""CP-14 step 1: the accepted Maintainer catalog behind one durable mode boundary."""

from __future__ import annotations

import unittest
from dataclasses import replace

from agent_artifacts.application.consumer_ui import (
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ApplicationScreen,
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    navigation_targets,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import (
    MAINTAINER_SCREENS,
    MaintainerScreen,
)
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    ConsumerScreens,
    _reload,
    frame,
    run_consumer_shell,
)

DOWN, ENTER, ESCAPE = 258, 10, 27


class _Terminal:
    def __init__(self, *codes: int) -> None:
        self.codes = list(codes)
        self.frames: list[tuple[str, ...]] = []

    def draw(self, lines: tuple[str, ...]) -> None:
        self.frames.append(lines)

    def key(self) -> int:
        return self.codes.pop(0)


def _reachable(*, maintainer_mode: bool) -> frozenset[ApplicationScreen]:
    """Every screen the shared forward graph exposes from the application Dashboard."""

    seen: set[ApplicationScreen] = {ConsumerScreen.DASHBOARD}
    frontier: list[ApplicationScreen] = [ConsumerScreen.DASHBOARD]
    while frontier:
        current = frontier.pop(0)
        for target in navigation_targets(current, maintainer_mode=maintainer_mode):
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    return frozenset(seen)


class MaintainerScreenCatalogTest(unittest.TestCase):
    def test_catalog_names_every_accepted_screen_30_through_53_once(self) -> None:
        """The 24 accepted screens, plus sub-screens that are numbered inside one of them.

        `31a`/`31b` are the Add Source form and its review (B-083) and `46a`/`46b` are the
        Initialize Registry form and its review (B-090), both spelled the way screen 21's own
        `21a`/`21b` addition pair already is. They extend the screen they belong to rather than
        adding a 25th destination, so the rule this states is that every catalog entry is one of
        the 24 accepted numbers or a lettered sub-screen of one of them -- never a new number.
        """

        numbered = tuple(
            screen for screen in MAINTAINER_SCREENS if screen.value.split("-", 1)[0].isdigit()
        )
        lettered = tuple(screen for screen in MAINTAINER_SCREENS if screen not in numbered)

        self.assertEqual(len(numbered), 24)
        self.assertEqual(
            tuple(int(screen.value.split("-", 1)[0]) for screen in numbered),
            tuple(range(30, 54)),
        )
        self.assertEqual(
            [screen.value for screen in lettered],
            ["31a-add-source", "31b-review-source", "46a-init-registry", "46b-review-init"],
        )
        for screen in lettered:
            prefix = screen.value.split("-", 1)[0]
            self.assertIn(int(prefix[:-1]), range(30, 54))
            self.assertTrue(prefix[-1].isalpha())
        self.assertEqual(MAINTAINER_SCREENS, tuple(MaintainerScreen))

    def test_every_maintainer_screen_is_reachable_only_when_the_mode_is_on(self) -> None:
        disabled = _reachable(maintainer_mode=False)
        enabled = _reachable(maintainer_mode=True)

        self.assertTrue(set(MAINTAINER_SCREENS).isdisjoint(disabled))
        self.assertTrue(set(MAINTAINER_SCREENS).issubset(enabled))


class MaintainerModeBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0))
        )

    def test_disabled_mode_refuses_even_a_forged_navigation_event(self) -> None:
        state = ConsumerUiState()

        unchanged, commands = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.DASHBOARD,
            ),
        )

        self.assertIs(unchanged, state)
        self.assertEqual(commands, ())

    def test_enabled_mode_enters_the_maintainer_area_through_the_shared_reducer(self) -> None:
        settings = ConsumerSettings().with_maintainer_mode(True)
        state = ConsumerUiState(settings=settings)

        entered, commands = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.DASHBOARD,
            ),
        )

        self.assertIs(entered.session.screen, MaintainerScreen.DASHBOARD)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.LOAD_SCREEN)
        self.assertIs(commands[0].screen, MaintainerScreen.DASHBOARD)

    def test_dashboard_draw_and_enter_obey_the_same_mode_boundary(self) -> None:
        disabled = _reload(self.source, ConsumerUiState(), entering=True)
        enabled = _reload(
            self.source,
            ConsumerUiState(settings=ConsumerSettings().with_maintainer_mode(True)),
            entering=True,
        )

        self.assertNotIn(MaintainerScreen.DASHBOARD.value, disabled.rows)
        self.assertNotIn("Maintainer Dashboard", "\n".join(frame(self.source, disabled)))
        self.assertEqual(enabled.rows[-1], MaintainerScreen.DASHBOARD.value)
        self.assertIn("Maintainer Dashboard", "\n".join(frame(self.source, enabled)))

        focused = replace(enabled, cursor=len(enabled.rows) - 1)
        event = key_event("enter", focused, detail=self.source.detail(focused))
        self.assertIsNotNone(event)
        assert event is not None
        entered, _ = reduce_consumer_ui(focused, event)
        self.assertIs(entered.session.screen, MaintainerScreen.DASHBOARD)

    def test_a_maintainer_screen_cannot_be_seeded_under_disabled_settings(self) -> None:
        with self.assertRaises(ValueError):
            ConsumerUiState(ConsumerSession(MaintainerScreen.DASHBOARD))

        with self.assertRaises(ValueError):
            ConsumerUiState(
                ConsumerSession(
                    ConsumerScreen.DASHBOARD,
                    history=(MaintainerScreen.DASHBOARD,),
                )
            )

    def test_real_shell_can_enable_the_mode_then_enter_the_maintainer_root(self) -> None:
        terminal = _Terminal(
            *(DOWN for _ in range(7)),
            ENTER,
            *(DOWN for _ in range(3)),
            ENTER,
            ESCAPE,
            *(DOWN for _ in range(8)),
            ENTER,
            ord("q"),
        )
        kept: list[ConsumerSettings] = []

        finished = run_consumer_shell(
            self.source,
            terminal,
            settings_writer=kept.append,
        )

        self.assertTrue(finished.exited)
        self.assertIs(finished.session.screen, MaintainerScreen.DASHBOARD)
        self.assertEqual([settings.maintainer_mode for settings in kept], [True])
        self.assertTrue(
            any("AART / Maintainer Dashboard" in "\n".join(lines) for lines in terminal.frames)
        )


if __name__ == "__main__":
    unittest.main()
