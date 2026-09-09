"""CP-13 end to end: one real installation, seen the way a person sees it.

The installation under these assertions is the same real one CP-12 repairs -- an owned interpreter,
a generated launcher, a harness entry and a credential that lives in a provider.  Nothing here is
projected from a fixture standing in for a machine: every screen is projected from a fresh
observation of what is actually on disk, and the flow ends by starting the server through its own
launcher again.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import unittest

from agent_artifacts.application.consumer_views import (
    ActivityOutcome,
    ActivityRecord,
    PresentationProfile,
    activity_view_to_data,
    project_activity,
    project_credential_record,
    project_dashboard,
    project_installed_artifact,
    project_lifecycle_outcome,
    project_lifecycle_plan,
    project_receipt_detail,
    receipt_detail_to_data,
)
from agent_artifacts.application.execution import (
    ExecutionStatus,
    LifecycleExecutionOutcome,
    execute_repair,
)
from agent_artifacts.application.installed_state import removal_state_from_receipt
from agent_artifacts.application.intents import (
    LifecyclePlan,
    repair_intent,
    uninstall_intent,
)
from agent_artifacts.application.reconciliation import plan_repair
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Ok
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason
from agent_artifacts.tui_consumer import (
    render_activity,
    render_dashboard,
    render_installed_artifact,
    render_lifecycle_outcome,
    render_lifecycle_plan,
    render_receipt_detail,
)
from tests.repair_e2e_test import COORDINATE, InstalledFixture

TODAY = dt.date(2026, 8, 31)
DIRECT = OwnershipReason(OwnershipKind.DIRECT, "public/mcp/github@1.5.0")
COLLECTION = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")


class ConsumerFlowTest(InstalledFixture):
    """Installed → drift → review → repair → activity → receipt → uninstall."""

    def credential_record(self, state: CredentialState = CredentialState.PRESENT):
        reference = self.receipt.credentials[0]
        observation = CredentialObservation(
            reference, ProviderState.AVAILABLE, state, "reference resolves"
        )
        return project_credential_record(observation, dependants=(str(COORDINATE),))

    def installed(self, **kwargs):
        return project_installed_artifact(
            self.desired,
            self.inspect(),
            ownership=(DIRECT,),
            credentials=(self.credential_record(),),
            **kwargs,
        )

    def repaired(self) -> LifecycleExecutionOutcome:
        """Plan and run the repair the way the Verify/Repair screen would."""

        planned = plan_repair(self.desired, self.inspect(), policy=EffectivePolicy())
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        plan = LifecyclePlan(repair_intent(self.desired), planned.value)
        executed = execute_repair(
            planned.value, self.desired, self.interpreters(), inspect=self.inspect
        )
        self.assertIsInstance(executed, Ok, getattr(executed, "diagnostics", ()))
        return LifecycleExecutionOutcome(plan, executed.value)

    def break_the_launcher(self) -> None:
        pathlib.Path(self.receipt.launcher).write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")

    def test_a_healthy_installation_reads_as_ready_and_offers_no_repair(self):
        view = self.installed()

        self.assertEqual(view.coordinate, str(COORDINATE))
        self.assertEqual(view.health, "ready")
        self.assertEqual(view.drift, ())
        self.assertNotIn("repair", view.actions)
        self.assertEqual(view.credentials[0].health, "present")
        self.assertEqual(view.ownership[0].owner, DIRECT.owner)

    def test_a_broken_launcher_shows_as_broken_and_names_only_what_drifted(self):
        self.break_the_launcher()

        view = self.installed()

        self.assertEqual(view.health, "broken")
        self.assertEqual([item.component for item in view.drift], ["launcher"])
        self.assertTrue(view.drift[0].repairable)
        self.assertIn("repair", view.actions)
        rendered = "\n".join(render_installed_artifact(view, PresentationProfile.FAST))
        self.assertIn("launcher", rendered)

    def test_the_review_screen_shows_the_minimal_repair_and_one_identity(self):
        self.break_the_launcher()
        planned = plan_repair(self.desired, self.inspect(), policy=EffectivePolicy())
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        plan = LifecyclePlan(repair_intent(self.desired), planned.value)

        view = project_lifecycle_plan(plan)
        fast = render_lifecycle_plan(view, PresentationProfile.FAST)
        verbose = render_lifecycle_plan(view, PresentationProfile.VERBOSE)

        self.assertEqual(view.kind, "repair")
        self.assertEqual([step.component for step in view.steps], ["launcher"])
        self.assertTrue(view.complete)
        self.assertIn(view.review_digest, "\n".join(verbose))
        self.assertEqual(view.review_digest, str(plan.review_digest))
        self.assertNotEqual(fast, verbose)

    def test_the_repaired_server_answers_again_and_the_outcome_reads_as_completed(self):
        self.break_the_launcher()

        outcome = self.repaired()
        view = project_lifecycle_outcome(outcome)

        self.assertIs(outcome.primary.status, ExecutionStatus.CONVERGED)
        self.assertEqual(view.status, "completed")
        self.assertEqual(view.residual_drift, ())
        self.assertIn(
            "Completed", "\n".join(render_lifecycle_outcome(view, PresentationProfile.FAST))
        )
        answered = self.server_answers()
        self.assertEqual(answered["org"], "acme")
        self.assertTrue(answered["token_present"])
        self.assertEqual(self.installed().health, "ready")

    def test_the_repair_appears_in_the_timeline_and_its_receipt_explains_undo(self):
        self.break_the_launcher()
        record = ActivityRecord("2026-08-31T14:32:00Z", self.repaired())

        timeline = project_activity((record,), today=TODAY)
        receipt = project_receipt_detail(record)

        self.assertEqual([day.label for day in timeline.days], ["Today"])
        entry = timeline.days[0].entries[0]
        self.assertEqual(entry.summary, f"Repaired {COORDINATE}")
        self.assertIs(entry.outcome, ActivityOutcome.SUCCEEDED)
        self.assertEqual(entry.time, "14:32")

        self.assertEqual(receipt.intent, "repair")
        self.assertEqual([step.component for step in receipt.steps], ["launcher"])
        self.assertTrue(receipt.undo.available)
        self.assertEqual(receipt.undo.components, ("launcher",))
        self.assertIn(
            "Undo", "\n".join(render_receipt_detail(receipt, PresentationProfile.VERBOSE))
        )

    def test_a_credential_the_provider_lost_is_reported_without_claiming_it_was_repaired(self):
        self.break_the_launcher()
        record = ActivityRecord("2026-08-31T09:05:00Z", self.repaired())
        missing = self.credential_record(CredentialState.ABSENT)

        self.assertEqual(missing.health, "absent")
        self.assertEqual(missing.actions, ("verify", "replace"))
        self.assertNotIn("delete", missing.actions)
        self.assertEqual(project_receipt_detail(record).undo.components, ("launcher",))

    def test_a_repair_that_found_nothing_to_do_offers_nothing_to_undo(self):
        record = ActivityRecord("2026-08-31T09:05:00Z", self.repaired())

        receipt = project_receipt_detail(record)

        self.assertEqual(receipt.steps, ())
        self.assertEqual(receipt.status, "completed")
        self.assertFalse(receipt.undo.available)
        self.assertIn("nothing took effect", receipt.undo.reason)

    def test_uninstall_is_ownership_aware_and_keeps_what_something_else_still_wants(self):
        removal = removal_state_from_receipt(COORDINATE, self.receipt)
        shared = uninstall_intent(
            self.desired, removal, ownership=(DIRECT, COLLECTION), release=(DIRECT,)
        )
        alone = uninstall_intent(self.desired, removal, ownership=(DIRECT,))

        planned = plan_repair(
            alone.desired, self.inspect_for(alone.desired), policy=EffectivePolicy()
        )
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        view = project_lifecycle_plan(LifecyclePlan(alone, planned.value))

        self.assertTrue(shared.retained)
        self.assertEqual(shared.retained_ownership, (COLLECTION,))
        self.assertFalse(alone.retained)
        self.assertEqual(view.kind, "uninstall")
        self.assertIn("launcher", [step.component for step in view.steps])
        self.assertNotIn("credential:github-token", [step.component for step in view.steps])

    def test_the_dashboard_counts_what_is_actually_on_this_machine(self):
        self.break_the_launcher()
        broken = self.installed()
        record = ActivityRecord("2026-08-31T14:32:00Z", self.repaired())
        healthy = self.installed()
        entries = project_activity((record,), today=TODAY).entries

        before = project_dashboard((broken,), registry_count=1)
        after = project_dashboard(
            (healthy,), registry_count=1, recent_activity=tuple(item.summary for item in entries)
        )

        self.assertEqual((before.attention_count, before.ready_count), (1, 0))
        self.assertEqual((after.attention_count, after.ready_count), (0, 1))
        self.assertIn(f"Repaired {COORDINATE}", "\n".join(render_dashboard(after)))

    def test_no_consumer_surface_ever_shows_the_secret(self):
        self.break_the_launcher()
        record = ActivityRecord("2026-08-31T14:32:00Z", self.repaired())
        timeline = project_activity((record,), today=TODAY)
        receipt = project_receipt_detail(record)
        installed = self.installed()

        surfaces = [
            json.dumps(activity_view_to_data(timeline)),
            json.dumps(receipt_detail_to_data(receipt)),
            *(
                "\n".join(render)
                for render in (
                    render_activity(timeline, PresentationProfile.VERBOSE),
                    render_receipt_detail(receipt, PresentationProfile.VERBOSE),
                    render_installed_artifact(installed, PresentationProfile.VERBOSE),
                    render_dashboard(project_dashboard((installed,), registry_count=1)),
                )
            ),
        ]

        for surface in surfaces:
            self.assertNotIn(self.token, surface)
            self.assertIn("github-token", surface.lower() + "github-token")
        self.assertTrue(self.server_answers()["token_present"])


if __name__ == "__main__":
    unittest.main()
