"""CP-21 step 7: an internal screen identifier is never a subject (`QA-077`).

The operator was told `authoring Source 31-sources is not configured and enabled`. `31-sources` is
`MaintainerScreen.SOURCES.value` -- a screen identifier being used as a Source alias, which is the
class of leak `QA-045` already closed once elsewhere. Nothing named the real Source, so there was
nothing to act on.

The cause is measurable rather than arguable: a dashboard's rows *are* screens, so carrying "the row
somebody was on" forward as what the next screen is about carries a destination where a subject
belongs.
"""

from __future__ import annotations

from unittest import TestCase

from aart_cli.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    is_screen_identifier,
)
from aart_cli.application.maintainer_views import MaintainerScreen

_SCREEN_VALUES = frozenset(
    {screen.value for screen in ConsumerScreen} | {screen.value for screen in MaintainerScreen}
)


def _navigate(state: ConsumerUiState, screen) -> ConsumerUiState:
    updated, _ = reduce_consumer_ui(
        state, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=screen)
    )
    return updated


class ScreenIdentifierIsNeverASubjectTest(TestCase):
    def _dashboard(self) -> ConsumerUiState:
        return ConsumerUiState(
            ConsumerSession(MaintainerScreen.DASHBOARD, history=(ConsumerScreen.DASHBOARD,)),
            settings=ConsumerSettings(maintainer_mode=True),
            rows=(MaintainerScreen.SOURCES.value, MaintainerScreen.CANDIDATES.value),
        )

    def test_opening_a_list_from_a_dashboard_carries_no_subject(self) -> None:
        opened = _navigate(self._dashboard(), MaintainerScreen.SOURCES)

        self.assertEqual(opened.focus, "")

    def test_the_identifier_does_not_survive_the_screen_loading_its_real_rows(self) -> None:
        opened = _navigate(self._dashboard(), MaintainerScreen.SOURCES)
        loaded, _ = reduce_consumer_ui(
            opened, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=("authors", "vendors"))
        )

        self.assertNotIn(loaded.focus, _SCREEN_VALUES)

    def test_no_dashboard_row_ever_becomes_the_focus_of_what_it_opens(self) -> None:
        for screen in (ConsumerScreen.DASHBOARD, MaintainerScreen.DASHBOARD):
            for target in _targets(screen):
                with self.subTest(screen=screen, target=target):
                    state = ConsumerUiState(
                        ConsumerSession(screen, history=()),
                        settings=ConsumerSettings(maintainer_mode=True),
                        rows=(target.value,),
                    )

                    self.assertEqual(_navigate(state, target).focus, "")

    def test_a_real_row_is_still_carried_forward_as_the_subject(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(
                MaintainerScreen.SOURCES,
                history=(ConsumerScreen.DASHBOARD, MaintainerScreen.DASHBOARD),
            ),
            settings=ConsumerSettings(maintainer_mode=True),
            rows=("authors", "vendors"),
        )

        self.assertEqual(_navigate(state, MaintainerScreen.SOURCE_DETAILS).focus, "authors")


class ScreenIdentifierPredicateTest(TestCase):
    def test_every_screen_value_is_recognised_as_one(self) -> None:
        for value in _SCREEN_VALUES:
            with self.subTest(value=value):
                self.assertTrue(is_screen_identifier(value))

    def test_an_alias_that_merely_looks_technical_is_not_one(self) -> None:
        for value in ("authors", "31-sources-of-truth", "sources", "", "company/mcp/notes@1.0.0"):
            with self.subTest(value=value):
                self.assertFalse(is_screen_identifier(value))


def _targets(screen):
    from aart_cli.application.consumer_views import navigation_targets

    return navigation_targets(screen, maintainer_mode=True)
