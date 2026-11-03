"""§213, B-253, D-514: telemetry is turned on and off in Settings, which says what that means.

The row says whether telemetry is on. On it, the status says where it sends, what it sends -- the
same words `consume telemetry enable` prints -- what waits, the last success and whether this
machine sends as a person or as automation. Enter turns it on with the address kept from before,
else the build's, or off; the outbox stays the one place the decision is kept.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import _default_telemetry, cli, tui
from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    SETTING_PURPOSE,
    SETTING_ROWS,
    TELEMETRY_ROW,
    TELEMETRY_UNMANAGED_ROW,
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from aart_cli.application.telemetry_settings import (
    TelemetryView,
    sent_as,
    telemetry_status,
    what_is_sent,
)
from aart_cli.domain.result import Ok
from aart_cli.io import telemetry_sync
from aart_cli.io.telemetry_store import TelemetryOutbox
from aart_cli.tui_consumer import render_settings

ADDRESS = "http://127.0.0.1:9"
KEPT = "http://localhost:8765"


def _status(view: TelemetryView, **sent: bool) -> str:
    return "\n".join(
        telemetry_status(
            view, unmanaged=sent.get("unmanaged", True), failures=sent.get("failures", True)
        )
    )


class TheRowTest(unittest.TestCase):
    def test_it_comes_first_under_telemetry_and_says_on_or_off(self) -> None:
        self.assertEqual(
            SETTING_ROWS.index(TELEMETRY_ROW) + 1, SETTING_ROWS.index(TELEMETRY_UNMANAGED_ROW)
        )
        for view, said in (
            (TelemetryView(enabled=True, endpoint=ADDRESS), "on"),
            (TelemetryView(endpoint=ADDRESS), "off"),
            (None, "off"),
        ):
            with self.subTest(said=said):
                drawn = "\n".join(
                    render_settings(ConsumerSettings(), focus=TELEMETRY_ROW, telemetry=view)
                )
                self.assertIn(
                    f"Telemetry\n> Telemetry: {said}\n  Uses of tools aart-cli did not install",
                    drawn,
                )
        self.assertIn("consume telemetry", SETTING_PURPOSE[TELEMETRY_ROW])

    def test_it_is_not_a_preference_settings_keeps(self) -> None:
        with self.assertRaises(ValueError):
            ConsumerSettings().toggled(TELEMETRY_ROW)


class TheStatusTest(unittest.TestCase):
    def test_on_it_says_where_what_what_waits_and_how_it_is_counted(self) -> None:
        said = _status(
            TelemetryView(
                enabled=True,
                endpoint=ADDRESS,
                client_id="c1",
                waiting=3,
                failures_waiting=2,
                last_success_at="2026-11-03T08:00:00+00:00",
            )
        )

        self.assertIn(f"On: sends to {ADDRESS}/api/v1/events/batch", said)
        for line in what_is_sent("c1", unmanaged=True, failures=True):
            self.assertIn(line, said)
        self.assertIn(
            "Waiting: 3 event(s), 2 failure(s); last sent 2026-11-03T08:00:00+00:00", said
        )
        self.assertIn(f"Sent as: {sent_as(False)}", said)
        self.assertIn("Enter turns it off", said)

    def test_off_it_says_where_turning_it_on_sends_or_that_nothing_is_named(self) -> None:
        offered = _status(TelemetryView(endpoint=ADDRESS, automated=True), failures=False)

        self.assertIn(f"Off. Enter turns it on, sending to {ADDRESS}/api/v1/events/batch", offered)
        for line in what_is_sent("", unmanaged=True, failures=False):
            self.assertIn(line, offered)
        self.assertIn("a random installation id", offered)
        self.assertIn("last sent never", offered)
        self.assertIn(f"Sent as: {sent_as(True)}", offered)
        self.assertIn("automation", sent_as(True))
        self.assertNotIn("automation", sent_as(False).split("(")[0])

        nothing = _status(TelemetryView())
        self.assertIn("names no telemetry server", nothing)
        self.assertIn("consume telemetry enable --endpoint", nothing)
        self.assertNotIn("Sent:", nothing)

    def test_what_is_sent_names_unmanaged_uses_and_failures_only_when_they_are(self) -> None:
        both = " ".join(what_is_sent("c1", unmanaged=True, failures=True))
        neither = " ".join(what_is_sent("c1", unmanaged=False, failures=False))

        self.assertIn("did not install", both)
        self.assertIn("each failure", both)
        self.assertNotIn("did not install", neither)
        self.assertNotIn("each failure", neither)
        self.assertIn("the installation id c1", both)

    @given(
        client_id=st.one_of(st.just(""), st.uuids().map(str)),
        unmanaged=st.booleans(),
        failures=st.booleans(),
    )
    def test_it_names_exactly_what_is_sent_and_never_what_is_not(
        self, client_id: str, unmanaged: bool, failures: bool
    ) -> None:
        said = " ".join(what_is_sent(client_id, unmanaged=unmanaged, failures=failures))

        self.assertIs("did not install" in said, unmanaged)
        self.assertIs("each failure" in said, failures)
        self.assertIs(f"the installation id {client_id}" in said, bool(client_id))
        self.assertIn("Never a project, path, argument, prompt, user or host name", said)

    def test_the_command_prints_the_same_words(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            out = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"HOME": home, "AART_CLI_HOME": home}),
                mock.patch.object(telemetry_sync, "spawn_sync", return_value=False),
                contextlib.redirect_stdout(out),
            ):
                self.assertEqual(
                    cli.main(["consume", "telemetry", "enable", "--endpoint", ADDRESS]), 0
                )
            setting = TelemetryOutbox(str(Path(home) / "state")).setting()
            assert isinstance(setting, Ok) and setting.value is not None
            for line in what_is_sent(setting.value.client_id, unmanaged=True, failures=True):
                self.assertIn(line, out.getvalue())

            out = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"HOME": home, "AART_CLI_HOME": home, "CI": "true"}),
                contextlib.redirect_stdout(out),
            ):
                cli.main(["consume", "telemetry", "status"])
            self.assertIn(f"sent as: {sent_as(True)}", out.getvalue())


class TheReducerTest(unittest.TestCase):
    def test_enter_on_the_row_runs_it_and_keeps_no_preference(self) -> None:
        state = ConsumerUiState(ConsumerSession(ConsumerScreen.SETTINGS))

        moved, commands = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SETTING, key=TELEMETRY_ROW)
        )

        self.assertEqual(
            commands,
            (
                ConsumerUiCommand(
                    ConsumerUiCommandKind.RUN_TELEMETRY, action=ConsumerActionKind.TELEMETRY
                ),
            ),
        )
        self.assertIs(moved.action, ConsumerActionKind.TELEMETRY)
        self.assertEqual(moved.settings, state.settings)

        done, followup = reduce_consumer_ui(
            moved,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED, action=ConsumerActionKind.TELEMETRY, text="on"
            ),
        )
        self.assertEqual(
            (done.action, done.session.screen, followup), (None, ConsumerScreen.SETTINGS, ())
        )

        elsewhere = ConsumerUiState(ConsumerSession(ConsumerScreen.ACTIVITY))
        self.assertEqual(
            reduce_consumer_ui(
                elsewhere, ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_SETTING, key=TELEMETRY_ROW)
            ),
            (elsewhere, ()),
        )


class TheTerminalTurnsItOnAndOffTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = temporary.name
        for patch in (
            mock.patch.dict(os.environ, {"HOME": self.home, "AART_CLI_HOME": self.home}),
            mock.patch.object(telemetry_sync, "spawn_sync", return_value=False),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.outbox = TelemetryOutbox(str(Path(self.home) / "state"))

    def _actions(self):
        composed = tui._canonical_consumer_actions(
            project=self.home, user_home=self.home, today=date(2026, 11, 3)
        )
        assert isinstance(composed, Ok), composed
        return composed.value

    def _toggle(self, actions):
        return actions.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.RUN_TELEMETRY, action=ConsumerActionKind.TELEMETRY
            )
        )

    def _setting(self):
        setting = self.outbox.setting()
        assert isinstance(setting, Ok)
        return setting.value

    def test_enter_turns_it_on_with_the_builds_address_then_off_and_the_choice_is_kept(
        self,
    ) -> None:
        with mock.patch.object(_default_telemetry, "ENDPOINT", ADDRESS):
            actions = self._actions()
            self.assertEqual(actions.source().screens.telemetry, TelemetryView(endpoint=ADDRESS))

            turned_on = self._toggle(actions)

            self.assertEqual(
                (turned_on.event.kind, turned_on.event.text),
                (ConsumerUiEventKind.ACTION_RECORDED, "on"),
            )
            self.assertEqual((self._setting().enabled, self._setting().endpoint), (True, ADDRESS))
            self.assertIn(
                f"Telemetry is on, sending to {ADDRESS}/api/v1/events/batch.",
                turned_on.source.screens.notice,
            )
            shown = turned_on.source.screens.telemetry
            self.assertEqual((shown.enabled, shown.client_id), (True, self._setting().client_id))

            turned_off = self._toggle(actions)

            self.assertEqual(turned_off.event.text, "off")
            self.assertFalse(self._setting().enabled)
            self.assertFalse(turned_off.source.screens.telemetry.enabled)
            self.assertIn("Telemetry is off", " ".join(turned_off.source.screens.notice))

    def test_turned_on_again_it_sends_where_it_sent_before(self) -> None:
        self.assertIsInstance(self.outbox.enable(KEPT, "c1"), Ok)
        self.assertIsInstance(self.outbox.disable(forget=False), Ok)
        with mock.patch.object(_default_telemetry, "ENDPOINT", ADDRESS):
            actions = self._actions()
            self.assertEqual(actions.source().screens.telemetry.endpoint, KEPT)

            self._toggle(actions)

        self.assertEqual((self._setting().endpoint, self._setting().client_id), (KEPT, "c1"))

    def test_with_no_address_anywhere_it_stays_off_and_says_how_to_give_one(self) -> None:
        actions = self._actions()

        refused = self._toggle(actions)

        self.assertIs(refused.event.kind, ConsumerUiEventKind.ACTION_FAILED)
        self.assertIn("--endpoint", " ".join(refused.source.screens.notice))
        self.assertIsNone(self._setting())

    def test_it_says_whether_this_machine_sends_as_automation(self) -> None:
        for environment, expected in (({"CI": "true"}, True), ({"CI": ""}, False)):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment):
                self.assertIs(self._actions().source().screens.telemetry.automated, expected)

    def test_what_waits_and_the_last_success_are_read_from_the_outbox_and_the_journal(
        self,
    ) -> None:
        from aart_cli.domain.failures import FailureKind
        from aart_cli.io.failure_journal import record_failure
        from tests.telemetry_sync_test import START, Clock, FakeServer, Home, _sync

        home = Home(self)
        with mock.patch.dict(os.environ, {"HOME": home.path, "AART_CLI_HOME": home.path}):
            self.home = home.path
            home.enable(ADDRESS)
            self.assertEqual(self._actions().source().screens.telemetry.last_success_at, "")
            home.use(2)
            _sync(home, FakeServer(), Clock())
            home.use(3)
            record_failure(home.path, FailureKind.ERROR, "consume.list", exit_code=1)

            shown = self._actions().source().screens.telemetry

        self.assertEqual(
            (shown.enabled, shown.endpoint, shown.waiting, shown.failures_waiting),
            (True, ADDRESS, 3, 1),
        )
        self.assertEqual(shown.last_success_at, START.isoformat())

    def test_the_shell_turns_it_on_from_the_row(self) -> None:
        from aart_cli.tui_consumer import run_consumer_shell
        from tests.consumer_shell_test import FakeTerminal

        with mock.patch.object(_default_telemetry, "ENDPOINT", ADDRESS):
            actions = self._actions()
            run_consumer_shell(
                actions.source(),
                FakeTerminal(10),
                state=ConsumerUiState(
                    ConsumerSession(ConsumerScreen.SETTINGS),
                    rows=SETTING_ROWS,
                    cursor=SETTING_ROWS.index(TELEMETRY_ROW),
                ),
                action_handler=actions,
                settings_writer=actions.save_settings,
            )

        self.assertTrue(self._setting().enabled)
