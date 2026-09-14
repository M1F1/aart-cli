"""The terminal is handed to whoever prompts for a credential, and taken back (`QA-081`)."""

from __future__ import annotations

import contextlib
import sys
import unittest

from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import (
    DeleteCredential,
    ReplaceCredential,
    StoreCredential,
    VerifyCredential,
)
from agent_artifacts.domain.identifiers import InputId
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.execution import CredentialEffectInterpreter


def _reference(name: str) -> CredentialReference:
    return CredentialReference(InputId(name), CredentialProviderRef("macos-keychain", "aart", name))


class _Journal:
    """One ordered record of what happened, because the fault was an ordering fault."""

    def __init__(self) -> None:
        self.entries: list[str] = []

    def handover(self):
        @contextlib.contextmanager
        def _held():
            self.entries.append("released")
            try:
                yield
            finally:
                self.entries.append("restored")

        return _held()


class _Provider:
    provider = "macos-keychain"

    def __init__(self, journal: _Journal, outcome: str = "ok") -> None:
        self._journal = journal
        self._outcome = outcome

    def store(self, reference, secret=None, *, replace=False):
        self._journal.entries.append("prompted")
        if self._outcome == "raise":
            raise OSError("the prompt could not run")
        if self._outcome == "err":
            return Err(
                (Diagnostic(DiagnosticCode("EXEC01"), Severity.ERROR, "Keychain write failed"),)
            )
        return Ok(
            CredentialObservation(reference, ProviderState.AVAILABLE, CredentialState.PRESENT)
        )

    def inspect(self, reference):
        self._journal.entries.append("inspected")
        return Ok(
            CredentialObservation(reference, ProviderState.AVAILABLE, CredentialState.PRESENT)
        )

    def delete(self, reference):
        self._journal.entries.append("deleted")
        return Ok(CredentialObservation(reference, ProviderState.AVAILABLE, CredentialState.ABSENT))


class CredentialTerminalHandoverTest(unittest.TestCase):
    """`QA-081`: `security` prints its prompt on the terminal curses is still drawing on.

    The provider running its own prompt is the invariant, not the defect: this process never sees
    the value (161.8/161.9, INV-206/INV-207).  What was missing is that the drawn screen was never
    released, so the prompt landed on top of the footer -- the operator's `[q] Quitpassword data
    for new item:`.  These tests hold the ordering, which is the whole of the fix.
    """

    def setUp(self) -> None:
        self.journal = _Journal()
        self.reference = _reference("dummy-token")

    def _interpreter(self, outcome: str = "ok") -> CredentialEffectInterpreter:
        return CredentialEffectInterpreter(
            _Provider(self.journal, outcome),
            (self.reference,),
            interactive_store=True,
            terminal_handover=self.journal.handover,
        )

    def test_the_screen_is_released_before_the_prompt_and_taken_back_after(self) -> None:
        applied = self._interpreter().apply(StoreCredential(str(self.reference), "macos-keychain"))

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertEqual(["released", "prompted", "restored"], self.journal.entries)

    def test_a_replacement_hands_the_screen_over_too(self) -> None:
        applied = self._interpreter().apply(
            ReplaceCredential(str(self.reference), "macos-keychain")
        )

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertEqual(["released", "prompted", "restored"], self.journal.entries)

    def test_a_refused_write_still_gives_the_screen_back(self) -> None:
        """A failure the operator has to read is a failure they have to be able to see."""

        applied = self._interpreter("err").apply(
            StoreCredential(str(self.reference), "macos-keychain")
        )

        self.assertIsInstance(applied, Err)
        self.assertEqual(["released", "prompted", "restored"], self.journal.entries)

    def test_a_prompt_that_raises_still_gives_the_screen_back(self) -> None:
        with self.assertRaises(OSError):
            self._interpreter("raise").apply(StoreCredential(str(self.reference), "macos-keychain"))

        self.assertEqual(["released", "prompted", "restored"], self.journal.entries)

    def test_reading_and_removing_a_credential_never_disturb_the_screen(self) -> None:
        """Only an effect that needs a person needs the terminal; the rest are AART's own work."""

        interpreter = self._interpreter()
        for effect in (
            VerifyCredential(str(self.reference), "macos-keychain"),
            DeleteCredential(str(self.reference), "macos-keychain"),
        ):
            with self.subTest(effect=type(effect).__name__):
                self.journal.entries.clear()
                applied = interpreter.apply(effect)
                self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
                self.assertNotIn("released", self.journal.entries)

    def test_without_an_adapter_to_hand_the_screen_to_the_prompt_still_runs(self) -> None:
        """The CLI has no drawn screen to release, and must not need one to store a value."""

        interpreter = CredentialEffectInterpreter(
            _Provider(self.journal), (self.reference,), interactive_store=True
        )

        applied = interpreter.apply(StoreCredential(str(self.reference), "macos-keychain"))

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertEqual(["prompted"], self.journal.entries)


class CursesHandoverTest(unittest.TestCase):
    """The curses half: what the adapter actually does to the terminal while it is lent out."""

    def setUp(self) -> None:
        from agent_artifacts import tui

        self.tui = tui
        self.calls: list[str] = []

        class _Curses:
            def __init__(self, calls: list[str]) -> None:
                self._calls = calls

            def def_prog_mode(self) -> None:
                self._calls.append("remembered")

            def endwin(self) -> None:
                self._calls.append("ended")

            def reset_prog_mode(self) -> None:
                self._calls.append("resumed")

        class _Screen:
            def __init__(self, calls: list[str]) -> None:
                self._calls = calls

            def clear(self) -> None:
                self._calls.append("cleared")

            def refresh(self) -> None:
                self._calls.append("refreshed")

        original = sys.modules.get("curses")
        sys.modules["curses"] = _Curses(self.calls)  # type: ignore[assignment]

        def _restore() -> None:
            if original is None:
                del sys.modules["curses"]
            else:
                sys.modules["curses"] = original

        self.addCleanup(_restore)
        self.screen = _Screen(self.calls)

    def test_an_unbound_loan_lends_nothing(self) -> None:
        """The text terminal and the CLI have no drawn screen, and must not need one."""

        with self.tui._CursesHandover()():
            self.calls.append("prompted")

        self.assertEqual(["prompted"], self.calls)

    def test_a_bound_loan_gives_the_terminal_up_and_repaints_after(self) -> None:
        loan = self.tui._CursesHandover()
        loan.bind(self.screen)

        with loan():
            self.calls.append("prompted")

        self.assertEqual(
            ["remembered", "ended", "prompted", "resumed", "cleared", "refreshed"], self.calls
        )

    def test_a_prompt_that_raises_still_leaves_curses_holding_the_terminal(self) -> None:
        loan = self.tui._CursesHandover()
        loan.bind(self.screen)

        with self.assertRaises(OSError):
            with loan():
                raise OSError("the prompt could not run")

        self.assertEqual(["remembered", "ended", "resumed", "cleared", "refreshed"], self.calls)


class HandoverReachesTheInterpreterTest(unittest.TestCase):
    """The loan is only worth composing if it survives the whole way to the prompt (`QA-081`).

    Four hops separate the screen from `security`, and every one of them already carries
    `interactive_credentials` -- the flag that says a person will be present.  The loan travels
    beside it, and this holds that the route is unbroken end to end, because a loan dropped at any
    hop is a loan that silently does nothing.
    """

    def test_every_hop_from_the_composed_actions_to_the_interpreter_carries_it(self) -> None:
        import inspect

        from agent_artifacts.io.configured_installation_action import (
            complete_configured_installation,
        )
        from agent_artifacts.io.consumer_actions import LocalConsumerActions
        from agent_artifacts.io.installation_execution import interpreters_for

        for function, parameter in (
            (LocalConsumerActions.__init__, "terminal_handover"),
            (complete_configured_installation, "credential_handover"),
            (interpreters_for, "credential_handover"),
            (CredentialEffectInterpreter.__init__, "terminal_handover"),
        ):
            with self.subTest(hop=function.__qualname__):
                self.assertIn(parameter, inspect.signature(function).parameters)

    def test_the_composed_actions_hand_the_loan_on_rather_than_holding_it(self) -> None:
        """A loan the actions keep to themselves is one the prompt never gets.

        Everything an install needs is stubbed except the hop under test: the recorder stops the
        call the moment it has read what it was handed, so this holds the forwarding and nothing
        about installing.
        """

        import types
        from datetime import datetime, timezone

        import agent_artifacts.io.consumer_actions as actions_module
        from agent_artifacts.io.consumer_actions import LocalConsumerActions

        recorded: dict = {}

        def _recorder(prepared, **kwargs):
            recorded.update(kwargs)
            return Err(
                (Diagnostic(DiagnosticCode("EXEC01"), Severity.ERROR, "stopped after the hop"),)
            )

        original = actions_module.complete_configured_installation
        actions_module.complete_configured_installation = _recorder
        self.addCleanup(setattr, actions_module, "complete_configured_installation", original)

        loan = _Journal().handover
        actions = LocalConsumerActions.__new__(LocalConsumerActions)
        actions._terminal_handover = loan
        actions._context = types.SimpleNamespace(
            policy=None, credential_providers=(), offline=False
        )
        actions._now = lambda: datetime(2026, 9, 10, tzinfo=timezone.utc)
        actions._reviewed_host = lambda: None  # type: ignore[method-assign]
        actions._failed = lambda command, lines: "refused"  # type: ignore[method-assign]
        pending = types.SimpleNamespace(
            prepared=types.SimpleNamespace(review_digest=None),
            previous_receipts=(),
            # D-260: a plan with no harness choice to make, so the targets check has nothing to hold.
            targets=(),
            chosen_targets=(),
        )

        command = types.SimpleNamespace(action=None, targets=())
        outcome = actions._execute_installation(command, pending)  # type: ignore[arg-type]

        self.assertEqual("refused", outcome)
        self.assertIs(loan, recorded.get("credential_handover"))
        self.assertTrue(recorded.get("interactive_credentials"))


if __name__ == "__main__":
    unittest.main()
