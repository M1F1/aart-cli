"""CP-47: the TUI says when a Registry runs a newer aart-cli, and AART CLI Update says how (§211).

Home announces it and marks its entry, the footer adds it beside the running version, and the
screen shows the guidance `aart-cli upgrade --how` prints.
"""

from __future__ import annotations

import dataclasses
import unittest

from aart_cli.application.aart_cli_update import (
    AartCliUpdate,
    Installer,
    UpdateStep,
    upgrade_guidance,
)
from aart_cli.application.consumer_session import ConsumerMachine
from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    navigation_targets,
    project_activity,
    project_dashboard,
)
from aart_cli.runtime_contract import EXECUTABLE_VERSION
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    ConsumerScreens,
    _reload,
    frame,
    screens_from,
)
from aart_cli.tui_layout import lowercase_first
from tests.consumer_shell_test import TODAY

UPDATE = AartCliUpdate(
    "0.20.0",
    "0.21.0",
    "corp",
    Installer.PIPX,
    (
        UpdateStep(
            "Install it from the package index corp uses:",
            (
                "pipx install --force --index-url https://nexus.example.test/simple aart-cli==0.21.0",
            ),
        ),
    ),
)


def _drawn(
    screen: ConsumerScreen, update: AartCliUpdate | None, *, workspace: str = "/work/shop"
) -> str:
    dashboard = project_dashboard((), registry_count=1)
    source = CanonicalScreenSource(
        ConsumerScreens(
            dashboard
            if update is None
            else dataclasses.replace(
                dashboard, aart_cli_available=update.available, aart_cli_registry=update.registry
            ),
            (),
            project_activity((), today=TODAY),
            aart_cli_update=update,
        )
    )
    state = dataclasses.replace(
        ConsumerUiState(ConsumerSession(screen)),
        viewport_columns=120,
        viewport_rows=50,
        workspace=workspace,
    )
    return "\n".join(frame(source, _reload(source, state, entering=True)))


class HomeAnnouncesItTest(unittest.TestCase):
    def test_home_says_it_marks_the_entry_and_the_footer_adds_it(self) -> None:
        drawn = _drawn(ConsumerScreen.DASHBOARD, UPDATE)

        self.assertIn("● aart-cli 0.21.0 available (Registry corp) — open AART CLI Update", drawn)
        self.assertIn("AART CLI Update  ● 0.21.0", drawn)
        self.assertIn(f"aart-cli {EXECUTABLE_VERSION} (0.21.0 available)", drawn)

    def test_nothing_is_announced_when_nothing_is_newer(self) -> None:
        drawn = _drawn(ConsumerScreen.DASHBOARD, None)

        self.assertNotIn("available", drawn)
        self.assertIn("AART CLI Update", drawn)

    def test_the_entry_is_home_s_last(self) -> None:
        targets = navigation_targets(
            ConsumerScreen.DASHBOARD, maintainer_mode=False, author_mode=False
        )

        self.assertIs(targets[-1], ConsumerScreen.AART_CLI_UPDATE)

    def test_screens_from_carries_the_update_to_home(self) -> None:
        machine = ConsumerMachine(
            project_dashboard((), registry_count=0), activity=project_activity((), today=TODAY)
        )
        screens = screens_from(machine, aart_cli_update=UPDATE)

        self.assertIs(screens.aart_cli_update, UPDATE)
        self.assertEqual(
            (screens.dashboard.aart_cli_available, screens.dashboard.aart_cli_registry),
            ("0.21.0", "corp"),
        )


class TheScreenSaysHowTest(unittest.TestCase):
    def test_the_screen_shows_the_guidance(self) -> None:
        drawn = _drawn(ConsumerScreen.AART_CLI_UPDATE, UPDATE)

        self.assertIn("AART CLI Update", drawn)
        # A statement opens in lower case on a screen (D-386); the rest is drawn as it is.
        for line in upgrade_guidance(UPDATE):
            if line:
                said = line.strip()
                self.assertTrue(said in drawn or lowercase_first(said) in drawn, said)

    def test_the_screen_says_when_nothing_is_newer(self) -> None:
        drawn = _drawn(ConsumerScreen.AART_CLI_UPDATE, None)

        self.assertIn(
            f"no connected Registry runs an aart-cli newer than {EXECUTABLE_VERSION}.", drawn
        )


if __name__ == "__main__":
    unittest.main()
