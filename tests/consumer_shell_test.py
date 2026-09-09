"""CP-13 — the persistent consumer application, driven headlessly through its own loop.

The loop under test is the one the curses adapter runs.  Only `draw` and `getch` are faked, so
everything the shell decides -- what a key means, which rows a screen shows, when they reload --
is the same code a person drives at a terminal.
"""

from __future__ import annotations

import datetime as dt
import unittest

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ActivityRecord,
    ConsumerScreen,
    ConsumerSettings,
    InstalledArtifactView,
    LifecycleDriftView,
    OwnershipView,
    PresentationProfile,
    project_activity,
    project_dashboard,
    project_doctor,
    project_receipt_detail,
)
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    ConsumerScreens,
    frame,
    run_consumer_shell,
)
from tests.consumer_activity_test import lifecycle_outcome

ESCAPE, ENTER, BACKSPACE, SLASH = 27, 10, 263, ord("/")
QUESTION = ord("?")
UP, DOWN, SPACE = 259, 258, 32
TODAY = dt.date(2026, 8, 31)


def installed(coordinate: str, health: str, drift: tuple[LifecycleDriftView, ...] = ()):
    actions = ("details", "verify", "configure", "uninstall")
    return InstalledArtifactView(
        coordinate,
        health,
        (OwnershipView("direct", coordinate),),
        drift,
        actions if health == "ready" else ("details", "verify", "repair", "uninstall"),
    )


def screens() -> ConsumerScreens:
    artifacts = (
        installed("public/mcp/github@1.6.0", "ready"),
        installed(
            "public/mcp/jira@2.2.0", "broken", (LifecycleDriftView("launcher", "missing", True),)
        ),
    )
    records = (
        ActivityRecord("2026-08-31T14:32:00Z", lifecycle_outcome()),
        ActivityRecord("2026-08-30T16:02:00Z", lifecycle_outcome()),
    )
    return ConsumerScreens(
        project_dashboard(artifacts, registry_count=2),
        artifacts,
        project_activity(records, today=TODAY),
        doctor=project_doctor(artifacts),
        receipts=tuple(project_receipt_detail(item) for item in records),
    )


class FakeTerminal:
    """One scripted terminal: it draws into a list and reads the keys it was given."""

    def __init__(self, *codes: int) -> None:
        self.frames: list[tuple[str, ...]] = []
        self._codes = list(codes) + [ord("q")]

    def draw(self, lines: tuple[str, ...]) -> None:
        self.frames.append(lines)

    def key(self) -> int:
        return self._codes.pop(0)

    @property
    def last(self) -> str:
        return "\n".join(self.frames[-1])

    def screen_containing(self, needle: str) -> str:
        return next(("\n".join(frame) for frame in self.frames if needle in "\n".join(frame)), "")


class _Preferences:
    """Where this shell keeps a changed preference, so the test can read what it was told."""

    def __init__(self) -> None:
        self.kept: list[ConsumerSettings] = []

    def __call__(self, settings: ConsumerSettings) -> None:
        self.kept.append(settings)


def drive(*codes: int, state: ConsumerUiState | None = None, preferences=None):
    source = CanonicalScreenSource(screens())
    terminal = FakeTerminal(*codes)
    finished = run_consumer_shell(
        source,
        terminal,
        state=state,
        settings_writer=_Preferences() if preferences is None else preferences,
    )
    return finished, terminal


class ConsumerShellTest(unittest.TestCase):
    def test_the_application_opens_on_the_dashboard_and_leaves_when_asked(self):
        state, terminal = drive()

        self.assertTrue(state.exited)
        self.assertIn("AART / Dashboard", terminal.frames[0][0])
        self.assertIn("2 installed", terminal.last)

    def test_the_first_screen_explains_basic_navigation_without_already_knowing_help(self):
        """Manual acceptance found that `?` was the only place advertising `?` (B-077)."""

        _, terminal = drive()

        first = terminal.frames[0]
        legend = "\n".join(line for line in first if line.startswith("Keys"))
        self.assertIn("Enter Open", legend)
        self.assertNotIn("Space", legend)
        self.assertIn("↑/↓ Move", legend)
        self.assertIn("Esc Back", legend)
        self.assertIn("? Help", legend)
        self.assertIn("q Quit", legend)

    def test_dashboard_explains_the_navigation_row_under_the_cursor(self):
        _, terminal = drive(DOWN)

        marketplace = "\n".join(terminal.frames[0])
        installed = "\n".join(terminal.frames[1])
        self.assertIn("Browse and install", marketplace)
        self.assertIn("Marketplace", marketplace)
        self.assertIn("See what AART manages", installed)
        self.assertIn("Installed", installed)
        self.assertNotEqual(marketplace, installed)

    def test_a_machine_without_sources_opens_with_first_run_guidance(self):
        source = CanonicalScreenSource(ConsumerScreens(project_dashboard((), registry_count=0)))
        terminal = FakeTerminal()

        run_consumer_shell(source, terminal, settings_writer=_Preferences())

        first = "\n".join(terminal.frames[0])
        self.assertIn("Welcome to AART", first)
        self.assertIn("first run", first)
        self.assertIn("skills", first)
        self.assertIn("MCP servers", first)
        self.assertIn("No sources are configured", first)
        self.assertIn("SETUP REQUIRED", first)
        self.assertIn("→ Start here", first)
        self.assertIn("open Registries", first)
        self.assertIn("Add Registry", first)
        self.assertLess(first.index("Welcome to AART"), first.index("Navigation:"))

    def test_a_machine_with_something_installed_is_not_offered_first_run_guidance(self):
        """No source and one installation is not a first run, and must still count what is there.

        The guidance replaces the Dashboard body rather than joining it, so getting this condition
        wrong does not merely add a panel -- it takes the installed counts away from the person who
        has installations to see.
        """

        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard(
                    (installed("public/mcp/github@1.6.0", "ready"),), registry_count=0
                )
            )
        )
        terminal = FakeTerminal()

        run_consumer_shell(source, terminal, settings_writer=_Preferences())

        first = "\n".join(terminal.frames[0])
        self.assertNotIn("Welcome to AART", first)
        self.assertNotIn("SETUP REQUIRED", first)
        self.assertIn("1 installed", first)

    def test_the_empty_registries_screen_repeats_the_source_setup_step(self):
        source = CanonicalScreenSource(ConsumerScreens(project_dashboard((), registry_count=0)))

        lines = frame(source, _at(ConsumerScreen.REGISTRIES))

        rendered = "\n".join(lines)
        self.assertIn("No sources are configured", rendered)
        self.assertIn("Add Registry", rendered)
        self.assertIn("connect the first one", rendered)

    def test_moving_to_a_screen_loads_its_rows_and_draws_the_cursor(self):
        moved, terminal = drive(DOWN, state=_at(ConsumerScreen.INSTALLED))

        self.assertEqual(moved.rows, ("public/mcp/github@1.6.0", "public/mcp/jira@2.2.0"))
        self.assertEqual(moved.current_row, "public/mcp/jira@2.2.0")
        self.assertIn("> [ ] public/mcp/jira@2.2.0  broken", terminal.last)

    def test_a_filter_narrows_the_rows_the_screen_shows(self):
        state, terminal = drive(
            SLASH, *map(ord, "jira"), ENTER, state=_at(ConsumerScreen.INSTALLED)
        )

        self.assertEqual(state.rows, ("public/mcp/jira@2.2.0",))
        self.assertEqual(state.search, "jira")
        self.assertIn("Filter: jira", terminal.last)

    def test_the_help_screen_advertises_the_filter_key(self):
        """Carried from the removed wizard's `tui_search_test.py`.

        A filter nobody is told about is a filter nobody uses, and the wizard's status-bar test was
        the only thing anywhere that said the key is advertised. The canonical shell advertises it
        on the `?` help instead of in a permanent status bar, so that is where the assertion lands.
        """

        _, terminal = drive(QUESTION, state=_at(ConsumerScreen.INSTALLED))

        advertised = [line for line in terminal.last.splitlines() if "search" in line]
        self.assertEqual(len(advertised), 1, terminal.last)
        self.assertIn("/", advertised[0])

    def test_a_filter_that_matches_nothing_empties_the_screen_without_leaving_it(self):
        """Also carried: a query that answers nothing is a narrowing, not an exit.

        The wizard refused to confirm a hidden row and said nothing matched. The canonical shell has
        no such notice -- recorded in `BACKLOG.md` -- but the half that matters for safety holds
        here: no row is offered, so no row can be acted on, and the screen is still the one the
        person was on. (`exited` is not asserted: the fake terminal running out of keys ends the
        loop, so every drive finishes exited and the flag says nothing about the filter.)
        """

        state, terminal = drive(
            SLASH, *map(ord, "nothing-here"), ENTER, state=_at(ConsumerScreen.INSTALLED)
        )

        self.assertEqual(state.rows, ())
        self.assertEqual(state.current_row, "")
        self.assertEqual(state.session.screen, ConsumerScreen.INSTALLED)
        self.assertIn("Filter: nothing-here", terminal.last)

    def test_the_artifact_type_is_searchable_so_one_kind_can_be_listed_alone(self):
        """Carried: the wizard proved a query matches the type, not only the name.

        A person who wants to see what Skills they have types `skill`, and the reason that works
        is that the coordinate the row carries names its type. Nothing else asserts it, and a
        filter that quietly matched names only would answer this question with an empty screen.
        The fixture is local because the shared one holds a single kind.
        """

        mixed = (
            installed("public/mcp/github@1.6.0", "ready"),
            installed("public/skill/code-review@1.0.0", "ready"),
        )
        terminal = FakeTerminal(SLASH, *map(ord, "skill"), ENTER)
        state = run_consumer_shell(
            CanonicalScreenSource(
                ConsumerScreens(
                    project_dashboard(mixed, registry_count=1),
                    mixed,
                    project_activity((), today=TODAY),
                )
            ),
            terminal,
            state=_at(ConsumerScreen.INSTALLED),
            settings_writer=_Preferences(),
        )

        self.assertEqual(state.rows, ("public/skill/code-review@1.0.0",))

    def test_clearing_the_filter_brings_the_hidden_rows_back(self):
        state, _ = drive(
            SLASH, *map(ord, "jira"), ENTER, SLASH, ESCAPE, state=_at(ConsumerScreen.INSTALLED)
        )

        self.assertEqual(len(state.rows), 2)
        self.assertEqual(state.search, "")

    def test_enter_opens_the_detail_for_the_row_under_the_cursor(self):
        state, terminal = drive(DOWN, ENTER, state=_at(ConsumerScreen.INSTALLED))

        self.assertEqual(state.session.screen, ConsumerScreen.INSTALLED_ARTIFACT_DETAILS)
        drawn = terminal.screen_containing("Installed Artifact Details")
        self.assertIn("public/mcp/jira@2.2.0", drawn)
        self.assertIn("launcher", drawn)

    def test_a_receipt_is_reachable_from_the_timeline(self):
        state, terminal = drive(ENTER, state=_at(ConsumerScreen.ACTIVITY))

        self.assertEqual(state.session.screen, ConsumerScreen.ACTIVITY_DETAILS)
        self.assertIn("Receipt:", terminal.last)
        self.assertIn("Undo", terminal.last)

    def test_v_redraws_the_same_screen_with_more_disclosed(self):
        fast, terminal = drive(state=_at(ConsumerScreen.ACTIVITY))
        verbose, verbose_terminal = drive(ord("v"), state=_at(ConsumerScreen.ACTIVITY))

        self.assertIs(fast.session.profile, PresentationProfile.FAST)
        self.assertIs(verbose.session.profile, PresentationProfile.VERBOSE)
        self.assertNotIn("sha256:", terminal.last)
        self.assertIn("sha256:", verbose_terminal.last)

    def test_switching_detail_level_is_kept_rather_than_only_redrawn(self):
        """`v` and screen 28's Detail level are one preference, so `v` has to outlive the session."""

        preferences = _Preferences()

        verbose, _ = drive(ord("v"), state=_at(ConsumerScreen.ACTIVITY), preferences=preferences)

        self.assertIs(verbose.settings.profile, PresentationProfile.VERBOSE)
        self.assertEqual([item.profile for item in preferences.kept], [PresentationProfile.VERBOSE])

    def test_screen_28_moves_the_setting_under_the_cursor_and_keeps_it(self):
        preferences = _Preferences()

        state, terminal = drive(
            DOWN,
            DOWN,
            DOWN,
            ENTER,
            state=_at(ConsumerScreen.SETTINGS),
            preferences=preferences,
        )

        self.assertEqual(state.current_row, "maintainer-mode")
        self.assertTrue(state.settings.maintainer_mode)
        self.assertEqual([item.maintainer_mode for item in preferences.kept], [True])
        self.assertIn("> Maintainer Mode: on", terminal.last)
        # The other three controls are untouched: one keystroke moves one preference.
        self.assertIs(state.settings.profile, PresentationProfile.FAST)
        self.assertEqual(state.settings.default_scope, "project")
        self.assertTrue(state.settings.show_updates)

    def test_a_shell_with_nowhere_to_keep_a_preference_refuses_rather_than_forgetting_it(self):
        source = CanonicalScreenSource(screens())

        with self.assertRaises(ValueError):
            run_consumer_shell(source, FakeTerminal(ord("v")), state=_at(ConsumerScreen.SETTINGS))

    def test_help_is_drawn_over_the_screen_it_was_asked_for(self):
        state, terminal = drive(ord("?"), state=_at(ConsumerScreen.INSTALLED))

        helped = terminal.screen_containing("Fast/Verbose")
        self.assertIn("AART / Installed", helped)
        self.assertIn("public/mcp/github@1.6.0", helped)
        self.assertTrue(state.exited)

    def test_quitting_with_a_selection_draws_the_question_before_leaving(self):
        state, terminal = drive(SPACE, ord("q"), ord("n"), state=_at(ConsumerScreen.INSTALLED))

        self.assertTrue(state.exited)
        self.assertEqual(terminal.screen_containing("Discard 1 selected"), "")

    def test_a_detail_stays_about_the_row_it_was_opened_from(self):
        opened, _ = drive(DOWN, ENTER, ENTER, state=_at(ConsumerScreen.ACTIVITY))

        self.assertEqual(opened.session.screen, ConsumerScreen.RECEIPT_DETAILS)
        self.assertEqual(opened.focus, "2026-08-30T16:02:00+00:00")

    def test_going_back_stops_the_screen_being_about_anything(self):
        returned, terminal = drive(ENTER, ESCAPE, state=_at(ConsumerScreen.ACTIVITY))

        self.assertEqual(returned.session.screen, ConsumerScreen.ACTIVITY)
        self.assertEqual(returned.focus, "")
        self.assertEqual(returned.current_row, "2026-08-31T14:32:00+00:00")

    def test_a_screen_with_nothing_behind_it_says_so_rather_than_drawing_nothing(self):
        source = CanonicalScreenSource(ConsumerScreens(project_dashboard((), registry_count=0)))

        lines = frame(source, _at(ConsumerScreen.UPDATES))

        self.assertIn("AART / Updates", lines[0])
        self.assertIn("Nothing here yet.", "\n".join(lines))


def _at(screen: ConsumerScreen) -> ConsumerUiState:
    from agent_artifacts.application.consumer_ui import (
        ConsumerUiEvent,
        ConsumerUiEventKind,
        reduce_consumer_ui,
    )

    state, _ = reduce_consumer_ui(
        ConsumerUiState(), ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=screen)
    )
    return state


if __name__ == "__main__":
    unittest.main()
