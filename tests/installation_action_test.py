"""One reviewed installation action from offer through durable transaction recording.

The shell and the public command must not each reassemble these calls.  Preparation stops with a
review and performs no mutation. Completion accepts only that review identity, executes the whole
Selection once, records one transaction plus its installed members, and returns the same receipt
the flow will draw.
"""

from __future__ import annotations

import unittest

from agent_artifacts.application.installation_action import (
    ACTION_REVIEW_MISMATCH,
    CompletedInstallationAction,
    PreparedInstallationAction,
    complete_installation_action,
    prepare_installation_action,
)
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok
from tests.artifact_installation_test import (
    INTERPRETER,
    _capabilities,
    _facts,
    _Inspector,
    _Keychain,
)
from tests.installation_offer_test import _nothing_installed, _placement
from tests.installation_proposal_test import _selection
from tests.installation_transaction_test import _Interpreter, _Lock, _matched
from tests.receipt_recording_test import FakeStore

MOMENT = "2026-08-31T20:15:00+00:00"


def _prepare():
    placement = _placement()
    prepared = prepare_installation_action(
        _selection(placement.artifact),
        (placement,),
        policy=EffectivePolicy(),
        facts=_facts(),
        inspect=_Inspector(_capabilities()),
        observe=_nothing_installed,
        selected_remediations=None,
        base_interpreter=INTERPRETER,
        resolvers=(_Keychain(),),
    )
    assert isinstance(prepared, Ok), getattr(prepared, "diagnostics", ())
    return prepared.value


class InstallationActionPreparationTest(unittest.TestCase):
    def test_preparation_holds_one_offer_and_the_review_derived_from_it(self) -> None:
        prepared = _prepare()

        self.assertIsInstance(prepared, PreparedInstallationAction)
        self.assertEqual(prepared.offer.installations, prepared.installations)
        self.assertEqual(prepared.review_digest, prepared.flow.proposal.review_digest)
        self.assertEqual(
            prepared.flow.artifacts,
            tuple(item.coordinate for item in prepared.installations),
        )

    def test_none_means_the_noninteractive_caller_accepts_the_whole_offer(self) -> None:
        """Commands have nobody between Offer and Begin to tick remediation choices."""

        prepared = _prepare()

        self.assertEqual(
            {item.remediation for item in prepared.offer.remediations},
            {item.remediation for item in prepared.flow.proposal.plan.remediations},
        )


class InstallationActionCompletionTest(unittest.TestCase):
    def test_the_reviewed_selection_executes_and_is_recorded_as_one_action(self) -> None:
        prepared = _prepare()
        planned = prepared.installations[0]
        calls = 0

        def inspect(_desired):
            nonlocal calls
            calls += 1
            return _nothing_installed(planned) if calls < 3 else _matched(planned)

        store = FakeStore()
        lock = _Lock()
        completed = complete_installation_action(
            prepared,
            expected_review_digest=prepared.review_digest,
            policy=EffectivePolicy(),
            interpreters=(_Interpreter(),),
            inspect=inspect,
            lock=lock,
            store=store,
            recorded_at=MOMENT,
        )

        self.assertIsInstance(completed, Ok, getattr(completed, "diagnostics", ()))
        self.assertIsInstance(completed.value, CompletedInstallationAction)
        self.assertEqual((lock.acquired, lock.released), (1, 1))
        self.assertEqual(len(store.actions), 1)
        self.assertEqual(len(store.installations), 1)
        self.assertEqual(completed.value.flow.outcome, completed.value.recorded.receipt)
        self.assertEqual(
            completed.value.recorded.receipt.review_digest, str(prepared.review_digest)
        )

    def test_a_different_review_identity_refuses_before_lock_or_recording(self) -> None:
        prepared = _prepare()
        store = FakeStore()
        lock = _Lock()

        refused = complete_installation_action(
            prepared,
            expected_review_digest=ObjectDigest("sha256", "0" * 64),
            policy=EffectivePolicy(),
            interpreters=(_Interpreter(),),
            inspect=lambda _desired: self.fail("a mismatched review must inspect nothing"),
            lock=lock,
            store=store,
            recorded_at=MOMENT,
        )

        self.assertIsInstance(refused, Err)
        self.assertIs(refused.diagnostics[0].code, ACTION_REVIEW_MISMATCH)
        self.assertEqual((lock.acquired, lock.released), (0, 0))
        self.assertEqual(store.actions, [])
        self.assertEqual(store.installations, {})


if __name__ == "__main__":
    unittest.main()
