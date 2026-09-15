"""CP-23 task 12: Credential Action's permitted actions are rows, and each one does what it says.

Screen 24 printed `[ Verify ]` and `[ Replace ]` over a screen that held no rows, so the cursor had
nothing to stand on and Enter did nothing. Now the actions the record permits are the rows: Verify
asks the provider in place and changes nothing; Replace and Delete open a review (24a) that states
their consequences before anything runs. Delete is a row only for a reference nothing installed
uses, and the adapter refuses it for one that is used however it is asked for (INV-057).

The planning is `application.credential_lifecycle` and the effects run through the same
`CredentialEffectInterpreter` repair uses, so the provider prompts for a replacement on a terminal
lent to it and no value -- old or new -- passes through AART (INV-056, D-262). Every provider here
is a fake that records what it was asked; nothing touches a real Keychain.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import json
import os
import unittest
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    PresentationProfile,
    project_credential_record,
)
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.consumer_actions import LocalConsumerActions
from agent_artifacts.io.consumer_machine import read_consumer_machine
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.tui_consumer import CanonicalScreenSource, _reload, frame
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_install_flow_shell_test import _navigate, at, screens
from tests.consumer_session_test import coordinate, receipt
from tests.consumer_shell_test import DOWN, ENTER, ESCAPE
from tests.consumer_views_test import _credential_input

REFERENCE = "github-token@macos-keychain:github.com/work"
_ROW_ACTIONS = {
    "verify": ConsumerActionKind.CREDENTIAL_VERIFY,
    "set": ConsumerActionKind.CREDENTIAL_SET,
    "replace": ConsumerActionKind.CREDENTIAL_REPLACE,
    "delete": ConsumerActionKind.CREDENTIAL_DELETE,
}
_ENTER_LABELS = {
    "verify": "Verify",
    "set": "Review setup",
    "replace": "Review replacement",
    "delete": "Review deletion",
}


def _unused_source() -> CanonicalScreenSource:
    _, _, observation = _credential_input()
    return CanonicalScreenSource(
        dataclasses.replace(screens(), credentials=(project_credential_record(observation),))
    )


def _on_action(
    *, unused: bool = False, profile: PresentationProfile = PresentationProfile.FAST
) -> tuple[CanonicalScreenSource, ConsumerUiState]:
    source, state = at(ConsumerScreen.CREDENTIALS, profile)
    if unused:
        source = _unused_source()
        state = dataclasses.replace(
            state,
            session=ConsumerSession(ConsumerScreen.CREDENTIAL_DETAILS),
            focus=REFERENCE,
        )
        state = _reload(source, state, entering=True)
    else:
        state, _ = _navigate(source, state, ConsumerScreen.USER_INPUT_DETAILS)
        state, _ = _navigate(source, state, ConsumerScreen.CREDENTIAL_DETAILS)
    state, _ = _navigate(source, state, ConsumerScreen.CREDENTIAL_ACTION)
    return source, state


def _enter(source: CanonicalScreenSource, state: ConsumerUiState):
    event = key_event("enter", state, detail=source.detail(state))
    assert event is not None, "Enter means nothing on this row"
    moved, commands = reduce_consumer_ui(state, event)
    return _reload(
        source, moved, entering=moved.session.screen is not state.session.screen
    ), commands


def _moved(source: CanonicalScreenSource, state: ConsumerUiState, row: str) -> ConsumerUiState:
    # Bounded by the rows, so a missing row fails the test instead of looping on it.
    if row not in state.rows:
        raise AssertionError(f"{row!r} is not a row of {state.rows!r}")
    while state.current_row != row:
        state, _ = reduce_consumer_ui(state, ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down"))
    return state


class TheActionsAreRowsTest(unittest.TestCase):
    def test_a_credential_in_use_offers_verify_and_replace_as_rows(self) -> None:
        source, state = _on_action()

        self.assertEqual(state.rows, ("verify", "replace"))
        self.assertEqual(source.actions(state), ("> Verify", "  Replace"))
        self.assertEqual(state.focus, REFERENCE)

    def test_an_unused_credential_also_offers_delete(self) -> None:
        source, state = _on_action(unused=True)

        self.assertEqual(state.rows, ("verify", "replace", "delete"))
        self.assertIn("  Delete", source.actions(state))

    def test_no_action_is_printed_as_a_string_among_the_facts(self) -> None:
        for unused in (False, True):
            for profile in PresentationProfile:
                with self.subTest(unused=unused, profile=profile):
                    source, state = _on_action(unused=unused, profile=profile)
                    drawn = "\n".join(frame(source, state))
                    status = "\n".join(source.status(state))

                    self.assertNotIn("[ Verify ]", drawn)
                    self.assertNotIn("[ Replace ]", drawn)
                    self.assertNotIn("Actions:", status)
                    stated = {line.strip("-> ").strip() for line in status.splitlines()}
                    for label in ("Verify", "Replace", "Delete"):
                        self.assertNotIn(label, stated)

    def test_usage_and_consequences_stay_below_the_rows(self) -> None:
        source, state = _on_action()

        status = "\n".join(source.status(state))
        actions = "\n".join(source.actions(state))

        self.assertIn("public/mcp/github", status)
        self.assertIn("cannot be removed while", status)
        self.assertIn("never reads or shows", status)
        self.assertIn("macos-keychain", status)
        self.assertNotIn("public/mcp/github", actions)

    def test_an_unused_credential_says_nothing_uses_it(self) -> None:
        source, state = _on_action(unused=True)

        status = "\n".join(source.status(state))

        self.assertIn("Nothing installed uses it", status)
        self.assertNotIn("cannot be removed", status)

    def test_enter_says_what_the_row_under_the_cursor_does(self) -> None:
        source, state = _on_action(unused=True)

        for row in state.rows:
            with self.subTest(row=row):
                moved = _moved(source, state, row)
                legend = {
                    (item.key, item.label)
                    for item in key_bindings(moved, detail=source.detail(moved))
                }

                self.assertIn(("Enter", _ENTER_LABELS[row]), legend)
                self.assertEqual(
                    [item for item in legend if item[0] == "Enter"],
                    [("Enter", _ENTER_LABELS[row])],
                )

    def test_verbose_describes_the_row_and_fast_does_not(self) -> None:
        source, verbose = _on_action(unused=True, profile=PresentationProfile.VERBOSE)
        _, fast = _on_action(unused=True)

        for row, words in (
            ("verify", "nothing is changed"),
            ("replace", "asks for the new value"),
            ("delete", "cannot be undone"),
        ):
            with self.subTest(row=row):
                described = " ".join(source.description(_moved(source, verbose, row)))
                self.assertIn(words, described)
                fast_drawn = "\n".join(frame(source, _moved(source, fast, row)))
                self.assertNotIn(words, fast_drawn)

    @given(moves=st.lists(st.sampled_from(("up", "down")), max_size=12))
    def test_the_request_is_the_row_and_the_subject_is_still_the_reference(
        self, moves: list[str]
    ) -> None:
        source, state = _on_action(unused=True)
        for move in moves:
            state, _ = reduce_consumer_ui(
                state, ConsumerUiEvent(ConsumerUiEventKind.MOVE, text=move)
            )
        row = state.current_row

        moved, commands = _enter(source, state)

        self.assertIs(moved.session.screen, ConsumerScreen.CREDENTIAL_REVIEW)
        self.assertEqual(moved.focus, REFERENCE)
        prepare = next(
            item for item in commands if item.kind is ConsumerUiCommandKind.PREPARE_ACTION
        )
        self.assertIs(prepare.action, _ROW_ACTIONS[row])
        self.assertEqual(prepare.focus, REFERENCE)


def _reviewing(row: str) -> tuple[CanonicalScreenSource, ConsumerUiState]:
    source, state = _on_action(unused=True)
    state, _ = _enter(source, _moved(source, state, row))
    return source, state


def _prepared(state: ConsumerUiState, digest: str = "sha256:" + "b" * 64) -> ConsumerUiState:
    assert state.action is not None
    prepared, _ = reduce_consumer_ui(
        state,
        ConsumerUiEvent(
            ConsumerUiEventKind.ACTION_PREPARED, action=state.action, review_digest=digest
        ),
    )
    return prepared


class TheReviewTest(unittest.TestCase):
    def test_replace_states_who_is_affected_and_that_the_provider_asks(self) -> None:
        source, state = _on_action()
        state, _ = _enter(source, _moved(source, state, "replace"))
        state = _prepared(state)

        status = "\n".join(source.status(state))

        self.assertIn("Replace github-token in macos-keychain", status)
        self.assertIn("public/mcp/github", status)
        self.assertIn("asks for the new value", status)
        self.assertIn("never reads or shows", status)
        self.assertEqual(source.rows(state), ())
        self.assertIn(("Enter", "Confirm"), {(b.key, b.label) for b in key_bindings(state)})

    def test_delete_states_it_cannot_be_undone(self) -> None:
        source, state = _reviewing("delete")
        state = _prepared(state)

        status = "\n".join(source.status(state))

        self.assertIn("Delete github-token from macos-keychain", status)
        self.assertIn("cannot be undone", status)

    def test_escape_cancels_the_review_and_runs_nothing(self) -> None:
        for row in ("replace", "delete"):
            with self.subTest(row=row):
                _, state = _reviewing(row)
                state = _prepared(state)

                back, commands = reduce_consumer_ui(state, key_event("escape", state))

                self.assertIs(back.session.screen, ConsumerScreen.CREDENTIAL_ACTION)
                self.assertEqual(back.focus, REFERENCE)
                self.assertFalse(
                    any(item.kind is ConsumerUiCommandKind.EXECUTE_ACTION for item in commands)
                )

    def test_confirming_executes_the_reviewed_action_on_the_same_reference(self) -> None:
        for row in ("replace", "delete"):
            with self.subTest(row=row):
                _, state = _reviewing(row)
                state = _prepared(state, "sha256:" + "c" * 64)

                _, commands = reduce_consumer_ui(state, key_event("enter", state))

                (execute,) = commands
                self.assertIs(execute.kind, ConsumerUiCommandKind.EXECUTE_ACTION)
                self.assertIs(execute.action, _ROW_ACTIONS[row])
                self.assertEqual(execute.focus, REFERENCE)
                self.assertEqual(execute.review_digest, "sha256:" + "c" * 64)

    def test_a_finished_replacement_lands_on_the_credential_and_a_deletion_on_the_list(
        self,
    ) -> None:
        for row, landing in (
            ("replace", ConsumerScreen.CREDENTIAL_DETAILS),
            ("delete", ConsumerScreen.CREDENTIALS),
        ):
            with self.subTest(row=row):
                _, state = _reviewing(row)
                state = _prepared(state)

                done, _ = reduce_consumer_ui(
                    state,
                    ConsumerUiEvent(
                        ConsumerUiEventKind.ACTION_RECORDED, action=state.action, text=REFERENCE
                    ),
                )

                self.assertIs(done.session.screen, landing)
                self.assertIsNone(done.action)
                self.assertEqual(done.focus, REFERENCE)

    def test_verify_is_finished_once_prepared_and_enter_returns_to_the_credential(self) -> None:
        source, state = _reviewing("verify")
        state = _prepared(state)

        self.assertIsNone(state.action)
        status = "\n".join(source.status(state))
        self.assertIn("nothing was changed", status)
        legend = {(b.key, b.label) for b in key_bindings(state)}
        self.assertIn(("Enter", "Credential details"), legend)
        self.assertNotIn(("Enter", "Confirm"), legend)

        back, _ = _enter(source, state)

        self.assertIs(back.session.screen, ConsumerScreen.CREDENTIAL_DETAILS)
        self.assertEqual(back.focus, REFERENCE)


# -- the adapter, against fake providers --------------------------------------------------------- #


class _Journal:
    def __init__(self) -> None:
        self.entries: list[str] = []
        self.briefings: list[tuple[str, ...]] = []

    def handover(self, briefing=()):
        self.briefings.append(tuple(briefing))

        @contextlib.contextmanager
        def _lent():
            self.entries.append("released")
            try:
                yield
            finally:
                self.entries.append("restored")

        return _lent()


class _Provider:
    """A provider that records every call and never holds or returns a value."""

    provider = "macos-keychain"

    def __init__(self, journal: _Journal, *, state: ProviderState = ProviderState.AVAILABLE):
        self._journal = journal
        self._provider_state = state
        self.present = CredentialState.PRESENT
        self.after_store = CredentialState.PRESENT
        self.stored: list[tuple[object, bool]] = []

    def available(self) -> ProviderState:
        return self._provider_state

    def _observation(self, reference) -> Ok:
        known = self._provider_state is ProviderState.AVAILABLE
        state = self.present if known else CredentialState.UNKNOWN
        return Ok(CredentialObservation(reference, self._provider_state, state))

    def inspect(self, reference):
        self._journal.entries.append("inspected")
        return self._observation(reference)

    def store(self, reference, secret=None, *, replace=False):
        self._journal.entries.append("prompted")
        self.stored.append((secret, replace))
        self.present = self.after_store
        return self._observation(reference)

    def delete(self, reference):
        self._journal.entries.append("deleted")
        self.present = CredentialState.ABSENT
        return self._observation(reference)


class _Composed:
    def __init__(self, env, provider: _Provider, journal: _Journal) -> None:
        base = _actions(env)
        host = base._context.host
        recorded = LocalReceiptStore(host.state_root).record_installation(coordinate(), receipt())
        assert isinstance(recorded, Ok), recorded
        machine = read_consumer_machine(
            state_root=host.state_root,
            harness_root=host.harness_root,
            today=dt.date(2026, 9, 14),
            project_root=host.project_root,
            user_home=host.user_home,
            data_root=host.data_root,
            credential_providers=(provider,),
        )
        assert isinstance(machine, Ok), machine
        self.actions = LocalConsumerActions(
            dataclasses.replace(
                base._context, machine=machine.value, credential_providers=(provider,)
            ),
            terminal_handover=journal.handover,
        )

    def prepare(self, action: ConsumerActionKind, focus: str = REFERENCE):
        return self.actions.handle(
            ConsumerUiCommand(ConsumerUiCommandKind.PREPARE_ACTION, action=action, focus=focus)
        )

    def execute(self, action: ConsumerActionKind, digest: str, focus: str = REFERENCE):
        return self.actions.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.EXECUTE_ACTION,
                action=action,
                focus=focus,
                review_digest=digest,
            )
        )


class CredentialActionAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.journal = _Journal()
        self.provider = _Provider(self.journal)
        environment = _environment()
        self.env = environment.__enter__()
        self.addCleanup(environment.__exit__, None, None, None)
        patcher = mock.patch.dict(os.environ, self.env.xdg, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.composed = _Composed(self.env, self.provider, self.journal)
        self.journal.entries.clear()

    def _record(self, update):
        return update.source.screens.credential(REFERENCE)

    def test_verify_asks_the_provider_and_changes_nothing(self) -> None:
        self.provider.present = CredentialState.ABSENT

        update = self.composed.prepare(ConsumerActionKind.CREDENTIAL_VERIFY)

        self.assertIs(update.event.kind, ConsumerUiEventKind.ACTION_PREPARED)
        self.assertTrue(update.event.review_digest)
        self.assertIn("inspected", self.journal.entries)
        self.assertNotIn("prompted", self.journal.entries)
        self.assertNotIn("deleted", self.journal.entries)
        self.assertEqual(self._record(update).health, "absent")

    def test_preparing_a_replacement_touches_nothing_and_confirming_hands_over_the_terminal(
        self,
    ) -> None:
        prepared = self.composed.prepare(ConsumerActionKind.CREDENTIAL_REPLACE)

        self.assertTrue(prepared.event.review_digest)
        self.assertNotIn("prompted", self.journal.entries)

        self.journal.entries.clear()
        done = self.composed.execute(
            ConsumerActionKind.CREDENTIAL_REPLACE, prepared.event.review_digest
        )

        self.assertIs(
            done.event.kind, ConsumerUiEventKind.ACTION_RECORDED, done.source.screens.notice
        )
        self.assertEqual(done.event.text, REFERENCE)
        self.assertEqual(self.journal.entries[:3], ["released", "prompted", "restored"])
        self.assertIn("inspected", self.journal.entries[3:])
        # INV-056: the provider prompts; AART hands it no value and asks for none back.
        self.assertEqual(self.provider.stored, [(None, True)])
        self.assertTrue(any("Replaced github-token" in line for line in done.source.screens.notice))

    def test_an_absent_credential_is_set_by_the_provider_then_verified(self) -> None:
        self.provider.present = CredentialState.ABSENT
        prepared = self.composed.prepare(ConsumerActionKind.CREDENTIAL_SET)

        self.assertTrue(prepared.event.review_digest, prepared.source.screens.notice)
        self.assertNotIn("prompted", self.journal.entries)
        self.journal.entries.clear()
        done = self.composed.execute(
            ConsumerActionKind.CREDENTIAL_SET, prepared.event.review_digest
        )

        self.assertIs(done.event.kind, ConsumerUiEventKind.ACTION_RECORDED)
        self.assertEqual(self.provider.stored, [(None, False)])
        self.assertEqual(self.journal.entries[:3], ["released", "prompted", "restored"])
        self.assertIn("inspected", self.journal.entries[3:])
        self.assertTrue(any("Set github-token" in line for line in done.source.screens.notice))

    def test_a_replacement_the_provider_does_not_report_as_stored_is_not_a_success(self) -> None:
        self.provider.after_store = CredentialState.ABSENT
        prepared = self.composed.prepare(ConsumerActionKind.CREDENTIAL_REPLACE)

        done = self.composed.execute(
            ConsumerActionKind.CREDENTIAL_REPLACE, prepared.event.review_digest
        )

        self.assertIs(done.event.kind, ConsumerUiEventKind.ACTION_FAILED)
        self.assertIn("absent", "\n".join(done.source.screens.notice))
        self.assertEqual(self._record(done).health, "absent")

    def test_a_set_the_provider_does_not_report_as_stored_is_not_a_success(self) -> None:
        self.provider.present = CredentialState.ABSENT
        self.provider.after_store = CredentialState.ABSENT
        prepared = self.composed.prepare(ConsumerActionKind.CREDENTIAL_SET)

        done = self.composed.execute(
            ConsumerActionKind.CREDENTIAL_SET, prepared.event.review_digest
        )

        self.assertIs(done.event.kind, ConsumerUiEventKind.ACTION_FAILED)
        self.assertIn("absent", "\n".join(done.source.screens.notice))
        self.assertEqual(self._record(done).health, "absent")

    def test_a_confirmation_naming_another_plan_runs_nothing(self) -> None:
        self.composed.prepare(ConsumerActionKind.CREDENTIAL_REPLACE)

        done = self.composed.execute(ConsumerActionKind.CREDENTIAL_REPLACE, "sha256:" + "0" * 64)

        self.assertIs(done.event.kind, ConsumerUiEventKind.ACTION_FAILED)
        self.assertNotIn("prompted", self.journal.entries)

    def test_deleting_a_credential_in_use_is_refused_and_names_what_uses_it(self) -> None:
        update = self.composed.prepare(ConsumerActionKind.CREDENTIAL_DELETE)

        self.assertIs(update.event.kind, ConsumerUiEventKind.ACTION_PREPARED)
        self.assertFalse(update.event.review_digest)
        self.assertIn(str(coordinate()), "\n".join(update.source.screens.notice))
        self.assertNotIn("deleted", self.journal.entries)

    def test_an_unavailable_provider_refuses_a_replacement_before_any_prompt(self) -> None:
        journal = _Journal()
        provider = _Provider(journal, state=ProviderState.UNAVAILABLE)
        composed = _Composed(self.env, provider, journal)

        update = composed.prepare(ConsumerActionKind.CREDENTIAL_REPLACE)

        self.assertFalse(update.event.review_digest)
        self.assertIn("not available", "\n".join(update.source.screens.notice))
        self.assertNotIn("prompted", journal.entries)

    def test_a_reference_nothing_here_knows_is_refused(self) -> None:
        update = self.composed.prepare(
            ConsumerActionKind.CREDENTIAL_VERIFY, focus="other@macos-keychain:example.com/work"
        )

        self.assertFalse(update.event.review_digest)
        self.assertIn("other@macos-keychain", "\n".join(update.source.screens.notice))
        self.assertNotIn("prompted", self.journal.entries)

    def test_the_review_identity_is_the_plan_and_carries_no_value(self) -> None:
        first = self.composed.prepare(ConsumerActionKind.CREDENTIAL_REPLACE)
        again = self.composed.prepare(ConsumerActionKind.CREDENTIAL_REPLACE)
        verify = self.composed.prepare(ConsumerActionKind.CREDENTIAL_VERIFY)

        self.assertEqual(first.event.review_digest, again.event.review_digest)
        self.assertNotEqual(first.event.review_digest, verify.event.review_digest)


class CredentialActionShellE2ETest(unittest.TestCase):
    """The keys, the reducer, the adapter and the frames, together."""

    def _run(self, *codes: int, present: CredentialState = CredentialState.PRESENT):
        journal = _Journal()
        provider = _Provider(journal)
        provider.present = present
        with _environment() as env:
            with mock.patch.dict(os.environ, env.xdg, clear=False):
                composed = _Composed(env, provider, journal)
            journal.entries.clear()
            finished, terminal, _ = _drive(
                env, _at(ConsumerScreen.CREDENTIALS), *codes, actions=composed.actions
            )
        return finished, terminal, journal, provider

    def test_absent_credential_is_set_from_the_grouped_area_with_a_briefed_handover(self) -> None:
        _, terminal, journal, provider = self._run(
            ENTER,
            ENTER,
            ENTER,
            DOWN,
            ENTER,
            ENTER,
            present=CredentialState.ABSENT,
        )

        review = terminal.screen_containing("Set github-token")
        self.assertIn("asks for the new value", review)
        self.assertEqual(provider.stored, [(None, False)])
        self.assertLess(journal.entries.index("released"), journal.entries.index("prompted"))
        self.assertLess(journal.entries.index("prompted"), journal.entries.index("restored"))
        briefing = "\n".join(journal.briefings[-1])
        self.assertIn("github-token", briefing)
        self.assertIn("AART never sees or keeps it", briefing)

    def test_replace_is_reviewed_confirmed_and_lands_on_the_credential(self) -> None:
        _, terminal, journal, provider = self._run(ENTER, ENTER, ENTER, DOWN, ENTER, ENTER)

        review = terminal.screen_containing("/ Review Replacement")
        self.assertIn("public/mcp/github", review)
        self.assertIn("[Enter] Confirm", review)
        self.assertEqual(provider.stored, [(None, True)])
        self.assertIn("released", journal.entries)
        landed = terminal.screen_containing("Replaced github-token")
        self.assertIn("Credential Details", landed)

    def test_escape_from_the_review_leaves_the_credential_untouched(self) -> None:
        _, terminal, journal, provider = self._run(ENTER, ENTER, ENTER, DOWN, ENTER, ESCAPE)

        self.assertTrue(terminal.screen_containing("/ Review Replacement"))
        self.assertEqual(provider.stored, [])
        self.assertNotIn("released", journal.entries)
        self.assertIn("Credential Action", terminal.last)
        self.assertNotIn("Review Replacement", terminal.last)
        self.assertIn("github-token", terminal.last)

    def test_verify_reports_in_place_and_enter_goes_back_to_the_credential(self) -> None:
        _, terminal, journal, provider = self._run(ENTER, ENTER, ENTER, ENTER, ENTER)

        verified = terminal.screen_containing("nothing was changed")
        self.assertIn("/ Verification", verified)
        self.assertIn("[Enter] Credential details", verified)
        self.assertEqual(provider.stored, [])
        self.assertNotIn("released", journal.entries)
        self.assertIn("Credential Details", terminal.last)
        self.assertNotIn("Review Replacement", terminal.last)

    def test_no_frame_or_plan_ever_holds_a_value(self) -> None:
        _, terminal, _, _ = self._run(ENTER, ENTER, ENTER, DOWN, ENTER, ENTER)

        drawn = json.dumps(terminal.frames)
        for shape in ("password", "secret value", "0x"):
            self.assertNotIn(shape, drawn)


if __name__ == "__main__":
    unittest.main()
