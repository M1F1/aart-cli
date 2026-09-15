"""CP-13 screens 25–27 — the activity timeline, one entry, and the receipt behind it."""

from __future__ import annotations

import datetime as dt
import json
import unittest

from agent_artifacts.application.consumer_views import (
    ActivityOutcome,
    ActivityRecord,
    PresentationProfile,
    activity_view_to_data,
    project_activity,
    project_receipt_detail,
    receipt_detail_to_data,
)
from agent_artifacts.application.execution import (
    ExecutionOutcome,
    LifecycleExecutionOutcome,
    StepOutcome,
    StepStatus,
)
from agent_artifacts.application.intents import (
    LifecycleIntentKind,
    LifecyclePlan,
    credential_rotation_intent,
    install_intent,
)
from agent_artifacts.application.reconciliation import plan_repair
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    ReplaceCredential,
    StoreCredential,
    WriteFile,
)
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ArtifactIdentity, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    ObservedComponent,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.tui_consumer import render_activity, render_receipt_detail

ARTIFACT = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.6.0")
ROOT = "/opt/agents/mcp/github"

LAUNCHER = ComponentId(Component.LAUNCHER)
HARNESS = ComponentId(Component.HARNESS, "tabnine")
TOKEN = ComponentId(Component.CREDENTIAL, "github-token")

TODAY = dt.date(2026, 8, 31)


def desired() -> DesiredState:
    return DesiredState(
        ARTIFACT,
        (
            DesiredComponent(
                LAUNCHER, (WriteFile(f"{ROOT}/launch.sh", "sha256:" + "a" * 64, True),)
            ),
            DesiredComponent(
                HARNESS,
                (ConfigureHarness("tabnine", "mcp/github", ".tabnine/agent/settings.json"),),
            ),
        ),
    )


def current(**states: ComponentState) -> CurrentState:
    names = {"launcher": LAUNCHER, "harness": HARNESS}
    return CurrentState(
        ARTIFACT,
        tuple(
            ObservedComponent(identifier, states.get(name, ComponentState.MATCHED))
            for name, identifier in names.items()
        ),
    )


def lifecycle_outcome(
    *,
    statuses: tuple[StepStatus, ...] = (StepStatus.APPLIED, StepStatus.APPLIED),
    converged: bool | None = True,
    residual=(),
    restoration: ExecutionOutcome | None = None,
) -> LifecycleExecutionOutcome:
    wanted = desired()
    planned = plan_repair(
        wanted,
        current(launcher=ComponentState.ABSENT, harness=ComponentState.ABSENT),
        policy=EffectivePolicy(),
    )
    assert isinstance(planned, Ok), getattr(planned, "diagnostics", ())
    plan = LifecyclePlan(install_intent(wanted), planned.value)
    steps = tuple(
        StepOutcome(step.component, step.effect, status)
        for step, status in zip(planned.value.steps, statuses, strict=True)
    )
    primary = ExecutionOutcome(plan.review_digest, steps, converged, tuple(residual))
    return LifecycleExecutionOutcome(plan, primary, restoration)


def record(day_offset: int = 0, time: str = "14:32:00", **kwargs) -> ActivityRecord:
    when = dt.datetime.combine(
        TODAY - dt.timedelta(days=day_offset),
        dt.time.fromisoformat(time),
        tzinfo=dt.timezone.utc,
    )
    return ActivityRecord(when.isoformat().replace("+00:00", "Z"), lifecycle_outcome(**kwargs))


class ActivityTimelineTest(unittest.TestCase):
    def test_entries_group_by_day_with_the_most_recent_day_first(self):
        view = project_activity(
            (record(1, "16:02:00"), record(0, "10:41:00"), record(0, "14:32:00")), today=TODAY
        )
        self.assertEqual([day.label for day in view.days], ["Today", "Yesterday"])
        self.assertEqual([entry.time for entry in view.days[0].entries], ["14:32", "10:41"])
        self.assertEqual([entry.time for entry in view.days[1].entries], ["16:02"])

    def test_a_day_older_than_yesterday_is_named_by_its_date(self):
        view = project_activity((record(17),), today=TODAY)
        self.assertEqual([day.label for day in view.days], ["2026-08-14"])

    def test_an_entry_says_what_a_person_did_not_which_effects_ran(self):
        entry = project_activity((record(),), today=TODAY).days[0].entries[0]
        self.assertEqual(entry.intent, LifecycleIntentKind.INSTALL.value)
        self.assertEqual(entry.summary, "Installed public/mcp/github@1.6.0")
        self.assertIs(entry.outcome, ActivityOutcome.SUCCEEDED)

    def test_each_terminal_status_maps_to_the_mark_a_reader_scans_for(self):
        cases = (
            ({}, ActivityOutcome.SUCCEEDED),
            (
                {
                    "converged": False,
                    "residual": (),
                    "statuses": (StepStatus.APPLIED, StepStatus.APPLIED),
                },
                ActivityOutcome.ATTENTION,
            ),
            (
                {"statuses": (StepStatus.FAILED, StepStatus.NOT_ATTEMPTED), "converged": False},
                ActivityOutcome.FAILED,
            ),
        )
        for kwargs, expected in cases:
            with self.subTest(expected=expected):
                entry = project_activity((record(**kwargs),), today=TODAY).days[0].entries[0]
                self.assertIs(entry.outcome, expected)

    def test_a_restored_update_reads_as_restored_rather_than_as_failed(self):
        outcome = lifecycle_outcome()
        restoration = ExecutionOutcome(outcome.plan.review_digest, (), True)
        entry = project_activity((record(restoration=restoration),), today=TODAY).days[0].entries[0]
        self.assertIs(entry.outcome, ActivityOutcome.RESTORED)

    def test_an_empty_timeline_is_a_view_with_no_days_rather_than_an_error(self):
        self.assertEqual(project_activity((), today=TODAY).days, ())

    def test_a_record_needs_a_timestamp_it_can_actually_read(self):
        for bad in ("", "yesterday", "2026-08-31"):
            with self.subTest(recorded_at=bad), self.assertRaises(ValueError):
                ActivityRecord(bad, lifecycle_outcome())

    def test_the_projection_names_artifacts_and_digests_and_no_value(self):
        projected = json.dumps(activity_view_to_data(project_activity((record(),), today=TODAY)))
        self.assertIn("public/mcp/github@1.6.0", projected)
        self.assertIn("sha256:", projected)
        self.assertNotIn("token", projected.lower())


class ReceiptDetailTest(unittest.TestCase):
    def test_a_receipt_exposes_intent_digest_and_the_effects_that_ran(self):
        view = project_receipt_detail(record())
        self.assertEqual(view.intent, "install")
        self.assertEqual(view.artifact, "public/mcp/github@1.6.0")
        self.assertTrue(view.review_digest.startswith("sha256:"))
        self.assertEqual([step.component for step in view.steps], ["launcher", "harness:tabnine"])

    def test_undo_is_offered_only_when_every_applied_effect_is_reversible(self):
        view = project_receipt_detail(record())
        self.assertTrue(view.undo.available)
        self.assertEqual(view.undo.components, ("launcher", "harness:tabnine"))

    def test_a_credential_mutation_is_never_undoable_because_no_old_value_is_kept(self):
        wanted = DesiredState(
            ARTIFACT,
            (
                DesiredComponent(
                    TOKEN,
                    (StoreCredential("github-token", "macos-keychain"),),
                    (ReplaceCredential("github-token", "macos-keychain"),),
                ),
            ),
        )
        observed = CurrentState(ARTIFACT, (ObservedComponent(TOKEN, ComponentState.DIVERGENT),))
        planned = plan_repair(wanted, observed, policy=EffectivePolicy())
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        plan = LifecyclePlan(credential_rotation_intent(wanted, wanted.components), planned.value)
        applied = tuple(
            StepOutcome(step.component, step.effect, StepStatus.APPLIED)
            for step in planned.value.steps
        )
        self.assertEqual([type(step.effect).__name__ for step in applied], ["ReplaceCredential"])
        view = project_receipt_detail(
            ActivityRecord(
                "2026-08-31T14:32:00Z",
                LifecycleExecutionOutcome(
                    plan, ExecutionOutcome(plan.review_digest, applied, True)
                ),
            )
        )
        self.assertFalse(view.undo.available)
        self.assertIn("no previous value", view.undo.reason)
        self.assertEqual(view.undo.components, ())

    def test_a_failed_step_is_not_undone_because_it_never_took_effect(self):
        view = project_receipt_detail(
            record(statuses=(StepStatus.FAILED, StepStatus.NOT_ATTEMPTED), converged=False)
        )
        self.assertFalse(view.undo.available)
        self.assertEqual(view.undo.components, ())

    def test_the_machine_receipt_carries_identity_and_effects_and_no_value(self):
        projected = json.dumps(receipt_detail_to_data(project_receipt_detail(record())))
        self.assertIn("public/mcp/github@1.6.0", projected)
        self.assertIn("write-file", projected)
        self.assertIn("policy_digest", projected)
        self.assertNotIn("secret", projected.lower())


class ActivityRenderingTest(unittest.TestCase):
    def test_fast_shows_the_timeline_a_person_reads(self):
        lines = render_activity(
            project_activity((record(1, "16:02:00"), record(0)), today=TODAY),
            PresentationProfile.FAST,
        )
        joined = "\n".join(lines)
        self.assertIn("Today", joined)
        self.assertIn("Yesterday", joined)
        self.assertIn("14:32", joined)
        self.assertIn("Installed public/mcp/github@1.6.0", joined)
        self.assertNotIn("sha256:", joined)

    def test_verbose_adds_the_digest_without_changing_what_happened(self):
        view = project_activity((record(),), today=TODAY)
        fast = render_activity(view, PresentationProfile.FAST)
        verbose = render_activity(view, PresentationProfile.VERBOSE)
        self.assertIn("sha256:", "\n".join(verbose))
        self.assertEqual(
            [line for line in fast if "Installed" in line],
            [line.split("  sha256")[0] for line in verbose if "Installed" in line],
        )

    def test_a_receipt_says_plainly_when_undo_is_not_available(self):
        lines = render_receipt_detail(
            project_receipt_detail(
                record(statuses=(StepStatus.FAILED, StepStatus.NOT_ATTEMPTED), converged=False)
            ),
            PresentationProfile.VERBOSE,
        )
        joined = "\n".join(lines)
        self.assertIn("Undo", joined)
        self.assertIn("not available", joined)


if __name__ == "__main__":
    unittest.main()
