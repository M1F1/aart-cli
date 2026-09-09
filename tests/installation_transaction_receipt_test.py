"""One bulk execution becomes one durable Activity receipt and per-artifact installed state."""

from __future__ import annotations

import datetime as dt
import unittest

from agent_artifacts.application.consumer_views import (
    ActivityOutcome,
    activity_from_receipts,
    project_installation_receipt,
    receipt_detail_from_data,
    receipt_detail_to_data,
)
from agent_artifacts.application.execution import (
    InstallationExecutionStatus,
    execute_installation,
)
from agent_artifacts.application.installation_proposal import intended_receipt
from agent_artifacts.application.receipt_recording import record_installation_transaction
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok
from tests.installation_proposal_test import _nothing_installed
from tests.installation_transaction_test import (
    _Interpreter,
    _Lock,
    _matched,
    _proposal,
)
from tests.receipt_recording_test import FakeStore

MOMENT = "2026-08-31T17:05:00+00:00"


def _executed():
    proposal, planned = _proposal()
    before = {item.coordinate: _nothing_installed(item) for item in planned}
    after = {item.coordinate: _matched(item) for item in planned}
    calls = {item.coordinate: 0 for item in planned}

    def inspect(desired):
        calls[desired.artifact] += 1
        return before[desired.artifact] if calls[desired.artifact] < 3 else after[desired.artifact]

    outcome = execute_installation(
        proposal,
        policy=EffectivePolicy(),
        interpreters=(_Interpreter(),),
        inspect=inspect,
        lock=_Lock(),
    )
    assert isinstance(outcome, Ok), getattr(outcome, "diagnostics", ())
    return outcome.value, planned


class InstallationTransactionReceiptTest(unittest.TestCase):
    def test_one_receipt_explains_selection_artifacts_effects_and_final_ownership(self) -> None:
        outcome, _ = _executed()

        receipt = project_installation_receipt(outcome, recorded_at=MOMENT)

        self.assertEqual(receipt.intent, "install")
        self.assertEqual(receipt.summary, "Installed 2 artifacts")
        self.assertIs(receipt.outcome, ActivityOutcome.SUCCEEDED)
        self.assertEqual(receipt.review_digest, str(outcome.proposal.review_digest))
        self.assertIsNotNone(receipt.selection)
        assert receipt.selection is not None
        self.assertEqual(len(receipt.selection.resolved), 2)
        self.assertEqual(len(receipt.artifacts), 2)
        self.assertTrue(all(item.ownership for item in receipt.artifacts))
        self.assertTrue(all(item.steps for item in receipt.artifacts))

    def test_transaction_receipt_round_trips_and_rebuilds_one_activity_entry(self) -> None:
        outcome, _ = _executed()
        receipt = project_installation_receipt(outcome, recorded_at=MOMENT)

        parsed = receipt_detail_from_data(receipt_detail_to_data(receipt))

        self.assertEqual(parsed, Ok(receipt))
        activity = activity_from_receipts(
            (parsed.value,),
            today=dt.date(2026, 8, 31),
        )
        self.assertEqual(len(activity.entries), 1)
        self.assertEqual(activity.entries[0].summary, "Installed 2 artifacts")

    def test_a_transaction_nobody_finished_cannot_be_undone(self) -> None:
        """Reversing half a Selection is not reversing it."""

        outcome, _ = _failed()

        receipt = project_installation_receipt(outcome, recorded_at=MOMENT)

        self.assertFalse(receipt.undo.available)
        self.assertIn("not every artifact", receipt.undo.reason)

    def test_a_member_that_never_ran_is_still_named_in_the_receipt(self) -> None:
        """A receipt listing only what ran cannot distinguish an abandoned half of a Selection
        from one nobody asked for."""

        outcome, _ = _failed()

        receipt = project_installation_receipt(outcome, recorded_at=MOMENT)

        self.assertEqual(len(receipt.artifacts), 2)
        self.assertEqual(receipt.artifacts[1].status, "not-attempted")
        self.assertEqual(receipt.artifacts[1].steps, ())
        self.assertIs(receipt.outcome, ActivityOutcome.FAILED)

    def test_recording_writes_one_action_and_each_resulting_installation(self) -> None:
        outcome, planned = _executed()
        store = FakeStore()

        recorded = record_installation_transaction(
            outcome,
            recorded_at=MOMENT,
            store=store,
            receipts=tuple((item.coordinate, intended_receipt(item)) for item in planned),
        )

        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        self.assertEqual(len(store.actions), 1)
        self.assertEqual(store.actions[0].summary, "Installed 2 artifacts")
        self.assertEqual(len(store.installations), 2)
        self.assertEqual(len(recorded.value.installations), 2)

    def test_a_transaction_that_took_no_effect_records_the_attempt_and_nothing_installed(
        self,
    ) -> None:
        outcome, _ = _failed()
        store = FakeStore()

        recorded = record_installation_transaction(outcome, recorded_at=MOMENT, store=store)

        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        self.assertEqual(len(store.actions), 1)
        self.assertEqual(store.installations, {})

    def test_a_member_that_applied_and_has_no_receipt_is_refused_rather_than_forgotten(
        self,
    ) -> None:
        """Its leftovers are on the machine either way; a record is what makes them somebody's."""

        outcome, planned = _executed()

        refused = record_installation_transaction(
            outcome,
            recorded_at=MOMENT,
            store=FakeStore(),
            receipts=((planned[0].coordinate, intended_receipt(planned[0])),),
        )

        self.assertIsInstance(refused, Err)
        self.assertIn(str(planned[1].coordinate), refused.diagnostics[0].message)

    def test_a_member_that_applied_is_recorded_even_though_a_later_one_failed(self) -> None:
        """Its leftovers are on the machine, so a later repair has to be able to find them."""

        outcome, planned = _partially_applied()
        store = FakeStore()

        recorded = record_installation_transaction(
            outcome,
            recorded_at=MOMENT,
            store=store,
            receipts=tuple((item.coordinate, intended_receipt(item)) for item in planned),
        )

        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        self.assertEqual(list(store.installations), [str(planned[0].coordinate)])
        self.assertEqual(len(store.actions), 1)
        self.assertIs(store.actions[0].outcome, ActivityOutcome.PARTIAL)

    def test_the_same_artifact_cannot_be_given_two_receipts(self) -> None:
        outcome, planned = _executed()
        pair = (planned[0].coordinate, intended_receipt(planned[0]))

        refused = record_installation_transaction(
            outcome, recorded_at=MOMENT, store=FakeStore(), receipts=(pair, pair)
        )

        self.assertIsInstance(refused, Err)
        self.assertIn("twice", refused.diagnostics[0].message)


class _FailsAfter:
    """Applies effects until a given count, then refuses -- so an earlier member can succeed."""

    def __init__(self, applies: int) -> None:
        self.applies = applies

    def supports(self, _effect) -> bool:
        return True

    def apply(self, _effect):
        if self.applies <= 0:
            return Err(
                (
                    Diagnostic(
                        DiagnosticCode("transaction-effect-failed"),
                        Severity.ERROR,
                        "the later artifact failed",
                    ),
                )
            )
        self.applies -= 1
        return Ok("applied")


def _partially_applied():
    """A transaction whose first artifact completes and whose second one fails."""

    proposal, planned = _proposal()
    before = {item.coordinate: _nothing_installed(item) for item in planned}
    after = {item.coordinate: _matched(item) for item in planned}
    calls = {item.coordinate: 0 for item in planned}

    def inspect(desired):
        calls[desired.artifact] += 1
        return before[desired.artifact] if calls[desired.artifact] < 3 else after[desired.artifact]

    outcome = execute_installation(
        proposal,
        policy=EffectivePolicy(),
        interpreters=(_FailsAfter(len(proposal.lifecycle[0].repair.steps)),),
        inspect=inspect,
        lock=_Lock(),
    )
    assert isinstance(outcome, Ok), getattr(outcome, "diagnostics", ())
    assert outcome.value.status is InstallationExecutionStatus.PARTIALLY_APPLIED, (
        outcome.value.status
    )
    return outcome.value, planned


def _failed():
    """One transaction whose first artifact fails, so the second is never attempted."""

    proposal, planned = _proposal()
    before = {item.coordinate: _nothing_installed(item) for item in planned}

    outcome = execute_installation(
        proposal,
        policy=EffectivePolicy(),
        interpreters=(_Interpreter(fail_first=True),),
        inspect=lambda desired: before[desired.artifact],
        lock=_Lock(),
    )
    assert isinstance(outcome, Ok), getattr(outcome, "diagnostics", ())
    assert outcome.value.status is InstallationExecutionStatus.FAILED
    return outcome.value, planned


if __name__ == "__main__":
    unittest.main()
