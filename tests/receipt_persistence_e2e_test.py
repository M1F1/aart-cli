"""End to end: what one process installed is what another process reconciles from.

The installation here is the real CP-12 one -- owned interpreter, generated launcher, harness entry,
provider-held credential. What is new is that nothing in memory is trusted afterwards. A second
store, built fresh over the same directory, reads the receipt back off disk, and every later
decision is made from that read-back receipt: the desired state, the review digest, the repair and
the timeline a person would see.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import unittest

from agent_artifacts.application.consumer_views import activity_from_receipts
from agent_artifacts.application.execution import LifecycleExecutionStatus, execute_lifecycle
from agent_artifacts.application.installed_state import (
    current_state_from_observation,
    desired_state_from_receipt,
    removal_state_from_receipt,
)
from agent_artifacts.application.intents import (
    plan_lifecycle_intent,
    repair_intent,
    uninstall_intent,
)
from agent_artifacts.application.receipt_recording import record_lifecycle_outcome
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import Component, ComponentId, ComponentState
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.execution import LocalMutationLock
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.io.runtime_projection import observe_installation
from tests.repair_e2e_test import COORDINATE, InstalledFixture

TODAY = dt.date(2026, 8, 31)


class ReceiptPersistenceTest(InstalledFixture):
    def setUp(self) -> None:
        super().setUp()
        self.state_root = str(self.scope / "state")
        self.store = LocalReceiptStore(self.state_root)
        self.moments = iter(f"2026-08-31T{hour:02d}:15:00+00:00" for hour in range(9, 20))

    def another_process(self) -> LocalReceiptStore:
        """A store that shares nothing with the one that wrote, except the directory."""

        return LocalReceiptStore(self.state_root)

    def lock(self) -> LocalMutationLock:
        return LocalMutationLock(self.state_root, str(self.scope))

    def reconcile(self, receipt) -> tuple:
        """Plan and run a repair using only what the given receipt says."""

        desired = desired_state_from_receipt(COORDINATE, receipt, base_interpreter=sys.executable)

        def inspect(_=None):
            return current_state_from_observation(
                desired,
                receipt,
                observe_installation(receipt, registry=self.registry),
                credentials=(
                    (("github-token", ComponentState.MATCHED),)
                    if os.path.exists(self.provider.path)
                    else (("github-token", ComponentState.ABSENT),)
                ),
            )

        planned = plan_lifecycle_intent(repair_intent(desired), inspect(), policy=EffectivePolicy())
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        executed = execute_lifecycle(
            planned.value,
            policy=EffectivePolicy(),
            interpreters=self.interpreters(),
            inspect=inspect,
            lock=self.lock(),
        )
        self.assertIsInstance(executed, Ok, getattr(executed, "diagnostics", ()))
        return desired, executed.value

    def uninstalled(self):
        """Tear the installation down for real, through the same reviewed, locked path."""

        removal = removal_state_from_receipt(COORDINATE, self.receipt)
        desired = desired_state_from_receipt(
            COORDINATE, self.receipt, base_interpreter=sys.executable
        )

        def inspect(_=None):
            return self.inspect_for(removal)

        planned = plan_lifecycle_intent(
            uninstall_intent(desired, removal), inspect(), policy=EffectivePolicy()
        )
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        executed = execute_lifecycle(
            planned.value,
            policy=EffectivePolicy(),
            interpreters=self.interpreters(),
            inspect=inspect,
            lock=self.lock(),
        )
        self.assertIsInstance(executed, Ok, getattr(executed, "diagnostics", ()))
        return executed.value

    def record(self, outcome, **kwargs):
        recorded = record_lifecycle_outcome(
            outcome, recorded_at=next(self.moments), store=self.store, **kwargs
        )
        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))
        return recorded.value

    def test_a_receipt_written_by_one_process_is_the_desired_state_of_the_next(self):
        _, outcome = self.reconcile(self.receipt)
        self.record(outcome, receipt=self.receipt)

        read = self.another_process().installation(COORDINATE)

        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        self.assertEqual(read.value, self.receipt)
        rebuilt = desired_state_from_receipt(
            COORDINATE, read.value, base_interpreter=sys.executable
        )
        self.assertEqual(rebuilt, self.desired)

    def test_a_launcher_broken_after_the_write_is_repaired_from_the_stored_receipt_alone(self):
        _, first = self.reconcile(self.receipt)
        self.record(first, receipt=self.receipt)
        pathlib.Path(self.receipt.launcher).write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")

        stored = self.another_process().installation(COORDINATE).value
        _, outcome = self.reconcile(stored)

        self.assertIs(outcome.status, LifecycleExecutionStatus.COMPLETED)
        self.assertEqual(
            [str(step.component) for step in outcome.primary.applied],
            [str(ComponentId(Component.LAUNCHER))],
        )
        self.assertEqual(self.server_answers()["org"], "acme")

    def test_the_timeline_another_process_reads_is_the_one_this_process_recorded(self):
        _, first = self.reconcile(self.receipt)
        recorded = self.record(first, receipt=self.receipt)
        pathlib.Path(self.receipt.launcher).unlink()
        _, second = self.reconcile(self.another_process().installation(COORDINATE).value)
        self.record(second, receipt=self.receipt)

        actions = self.another_process().actions()

        self.assertIsInstance(actions, Ok, getattr(actions, "diagnostics", ()))
        timeline = activity_from_receipts(actions.value, today=TODAY)
        self.assertEqual([day.label for day in timeline.days], ["Today"])
        self.assertEqual(
            [entry.summary for entry in timeline.days[0].entries],
            ["Repaired public/mcp/github@1.5.0"] * 2,
        )
        self.assertEqual(timeline.days[0].entries[-1].review_digest, recorded.receipt.review_digest)

    def test_an_uninstall_that_completed_leaves_nothing_for_the_next_process_to_find(self):
        _, outcome = self.reconcile(self.receipt)
        self.record(outcome, receipt=self.receipt)
        removal = self.uninstalled()

        self.record(removal)

        later = self.another_process()
        self.assertIsInstance(later.installation(COORDINATE), Err)
        self.assertEqual(later.installations().value, ())
        self.assertEqual(len(later.actions().value), 2)

    def test_no_stored_file_anywhere_contains_the_real_secret(self):
        _, outcome = self.reconcile(self.receipt)
        self.record(outcome, receipt=self.receipt)

        stored = tuple(
            path
            for path in pathlib.Path(self.state_root).rglob("*")
            if path.is_file() and path.suffix == ".json"
        )

        self.assertTrue(stored)
        for path in stored:
            self.assertNotIn(self.token, path.read_text(encoding="utf-8"))
        installation = pathlib.Path(self.store.path_for(COORDINATE)).read_text(encoding="utf-8")
        self.assertIn(
            "github-token", json.loads(installation)["receipt"]["credentials"][0]["input"]
        )


if __name__ == "__main__":
    unittest.main()
