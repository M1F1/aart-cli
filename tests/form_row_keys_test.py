"""CP-23 task 14: a form's keys follow the row under the cursor (D-269).

The audit drew every form and pressed every key its legend offered. On a text field `v`, `?` and
`q` were typed, as §167 requires, while the legend still offered Fast / Verbose, Help and Quit; on
Continue they did nothing at all, so a form was the one place Help and Quit could not be reached.
Backspace was offered on rows that hold no text and Space on rows it does not toggle.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    CONFIG_CONTINUE_ROW,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from aart_cli.application.maintainer_views import MaintainerScreen
from aart_cli.tui_consumer import CanonicalScreenSource, frame
from tests.configuration_edit_test import _key, _source_and_state
from tests.consumer_shell_test import screens
from tests.frame_contract import (
    frame_violations,
    key_violations,
    literal_violations,
    toggle_violations,
)
from tests.install_time_config_form_test import InstallTimeConfigFormRenderingTest
from tests.install_time_config_form_test import _state as _install_form

#: The rows of each simple form that hold typed text, and the one row Space toggles, if any.
TEXT_ROWS = {
    ConsumerScreen.REGISTRY_ADD: ({"alias", "url", "ref"}, "default"),
    MaintainerScreen.SOURCE_ADD: ({"alias", "location", "ref"}, "kind"),
    MaintainerScreen.REGISTRY_INIT: ({"id", "name", "reporting"}, "commit"),
    MaintainerScreen.REPOSITORY_SCAN: ({"url", "ref"}, None),
}


def _simple_forms():
    source = CanonicalScreenSource(screens())
    for screen, (text, toggle) in TEXT_ROWS.items():
        state = ConsumerUiState(
            ConsumerSession(screen), settings=ConsumerSettings().with_maintainer_mode(True)
        )
        rows = source.rows(state)
        for cursor, row in enumerate(rows):
            yield source, replace(state, rows=rows, cursor=cursor), row in text, row == toggle


def _configuration_forms():
    # With a projected field and a credential beside it, so the form has everything it can draw.
    install = InstallTimeConfigFormRenderingTest._source(None)  # type: ignore[arg-type]
    for cursor in (0, 1):
        yield install, replace(_install_form(), cursor=cursor), cursor == 0, False
    source, state = _source_and_state()
    state, _ = _key(source, state, "enter")
    state, _ = _key(source, state, "enter")
    for cursor, row in enumerate(state.rows):
        yield source, replace(state, cursor=cursor), row != CONFIG_CONTINUE_ROW, False


def _every_form_row():
    yield from _simple_forms()
    yield from _configuration_forms()


def _advertised(source, state) -> set[str]:
    return {item.key for item in key_bindings(state, detail=source.detail(state))}


class AFormRowOffersOnlyWhatItTakesTest(unittest.TestCase):
    def test_every_key_a_form_row_advertises_does_something_there(self) -> None:
        for source, state, _, _ in _every_form_row():
            with self.subTest(screen=state.session.screen, row=state.current_row):
                self.assertEqual(key_violations(source, state), ())

    def test_on_a_text_field_the_universal_letters_are_typed_and_not_advertised(self) -> None:
        for source, state, text, _ in _every_form_row():
            if not text:
                continue
            with self.subTest(screen=state.session.screen, row=state.current_row):
                self.assertEqual(literal_violations(source, state), ())
                self.assertTrue({"Type", "Backspace"} <= _advertised(source, state))

    def test_off_a_text_field_the_universal_letters_are_commands_again(self) -> None:
        commands = {
            "v": ConsumerUiEventKind.TOGGLE_PROFILE,
            "?": ConsumerUiEventKind.HELP,
            "q": ConsumerUiEventKind.QUIT,
        }
        for source, state, text, _ in _every_form_row():
            if text:
                continue
            with self.subTest(screen=state.session.screen, row=state.current_row):
                advertised = _advertised(source, state)
                self.assertFalse({"Type", "Backspace"} & advertised)
                for letter, kind in commands.items():
                    self.assertIn(letter, advertised)
                    event = key_event(letter, state, detail=source.detail(state))
                    self.assertIsNotNone(event)
                    self.assertIs(event.kind, kind)  # type: ignore[union-attr]

    def test_space_is_offered_only_on_the_row_it_toggles(self) -> None:
        for source, state, _, toggle in _every_form_row():
            with self.subTest(screen=state.session.screen, row=state.current_row):
                self.assertEqual("Space" in _advertised(source, state), toggle)

    def test_the_drawn_legend_is_the_one_the_row_offers(self) -> None:
        source, state, _, _ = next(_simple_forms())
        field = frame(source, state)
        connect = frame(source, replace(state, cursor=len(state.rows) - 1))

        self.assertIn("[Type] Edit   [Backspace] Delete   [Enter] Next", field)
        self.assertNotIn("[q] Quit", "\n".join(field))
        self.assertIn("[?] Help", "\n".join(connect))
        self.assertNotIn("[Backspace]", "\n".join(connect))


class AFormIsDrawnInTheSharedFrameTest(unittest.TestCase):
    """§167: a form's fields are its rows; what it explains is the state of the view."""

    def test_every_form_row_keeps_the_frame_in_both_profiles(self) -> None:
        for source, state, _, _ in _every_form_row():
            verbose, _ = reduce_consumer_ui(
                replace(state, cursor=len(state.rows) - 1),
                ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE),
            )
            for drawn in (state, replace(verbose, cursor=state.cursor)):
                with self.subTest(
                    screen=state.session.screen,
                    row=state.current_row,
                    profile=drawn.session.profile,
                ):
                    self.assertEqual(frame_violations(source, drawn), ())
                    self.assertEqual(toggle_violations(source, drawn), ())


class PastingIntoAFormTest(unittest.TestCase):
    def test_every_form_takes_pasted_text_on_a_field(self) -> None:
        """The shell reads a paste whole on every form; Add Source used to refuse it outright."""

        for source, state, text, _ in _every_form_row():
            if not text:
                continue
            with self.subTest(screen=state.session.screen, row=state.current_row):
                event = key_event("pasted-value", state, detail=source.detail(state))
                self.assertIsNotNone(event)
                self.assertTrue(event.text.endswith("pasted-value"))  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
