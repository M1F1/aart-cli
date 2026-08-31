"""End to end: a real machine on disk becomes the screens a person actually reads.

Nothing here is handed a view. A real installation -- owned interpreter, generated launcher,
harness entry, provider-held credential -- is recorded with who asked for it, and then a second
process reads that record back, inspects the machine, assembles it once and draws the screens from
the result. What a person sees is therefore what was measured, not what a test arranged.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import sys
import unittest

from agent_artifacts.application.consumer_session import (
    InstalledInspection,
    assemble_consumer_machine,
)
from agent_artifacts.application.consumer_ui import (
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerScreen, navigation_targets
from agent_artifacts.application.execution import execute_lifecycle
from agent_artifacts.application.installed_state import (
    current_state_from_observation,
    desired_state_from_receipt,
)
from agent_artifacts.application.intents import install_intent, plan_lifecycle_intent
from agent_artifacts.application.receipt_recording import record_lifecycle_outcome
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import ComponentState
from agent_artifacts.domain.result import Ok
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason
from agent_artifacts.io.execution import LocalMutationLock
from agent_artifacts.io.receipt_store import LocalReceiptStore
from agent_artifacts.io.runtime_projection import observe_installation
from agent_artifacts.tui_consumer import CanonicalScreenSource, _reload, frame, screens_from
from tests.repair_e2e_test import COORDINATE, InstalledFixture

TODAY = dt.date(2026, 8, 31)
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")


def _route(screen: ConsumerScreen) -> tuple[ConsumerScreen, ...]:
    """The shortest accepted way in from the Dashboard."""

    frontier: list[tuple[ConsumerScreen, ...]] = [()]
    seen = {ConsumerScreen.DASHBOARD}
    while frontier:
        path = frontier.pop(0)
        current = path[-1] if path else ConsumerScreen.DASHBOARD
        if current is screen:
            return path
        for target in navigation_targets(current):
            if target not in seen:
                seen.add(target)
                frontier.append((*path, target))
    raise AssertionError(f"{screen.value} is not reachable from the Dashboard")


class ConsumerSessionTest(InstalledFixture):
    def setUp(self) -> None:
        super().setUp()
        self.state_root = str(self.scope / "state")
        self.store = LocalReceiptStore(self.state_root)
        self.install(ownership=(KIT,))

    def install(self, *, ownership: tuple[OwnershipReason, ...]) -> None:
        """Install for real, through the reviewed and locked path, and record who asked."""

        def inspect(_=None):
            return self.inspect()

        planned = plan_lifecycle_intent(
            install_intent(self.desired, ownership=ownership),
            inspect(),
            policy=EffectivePolicy(),
        )
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        executed = execute_lifecycle(
            planned.value,
            policy=EffectivePolicy(),
            interpreters=self.interpreters(),
            inspect=inspect,
            lock=LocalMutationLock(self.state_root, str(self.scope)),
        )
        self.assertIsInstance(executed, Ok, getattr(executed, "diagnostics", ()))
        recorded = record_lifecycle_outcome(
            executed.value,
            recorded_at="2026-08-31T14:32:00+00:00",
            store=self.store,
            receipt=self.receipt,
        )
        self.assertIsInstance(recorded, Ok, getattr(recorded, "diagnostics", ()))

    def machine(self):
        """Everything a second process can say about this machine, read from disk."""

        later = LocalReceiptStore(self.state_root)
        records = later.installations()
        self.assertIsInstance(records, Ok, getattr(records, "diagnostics", ()))
        inspections = []
        for record in records.value:
            desired = desired_state_from_receipt(
                record.coordinate, record.receipt, base_interpreter=sys.executable
            )
            inspections.append(
                InstalledInspection(
                    record,
                    desired,
                    current_state_from_observation(
                        desired,
                        record.receipt,
                        observe_installation(record.receipt, registry=self.registry),
                        credentials=(
                            (("github-token", ComponentState.MATCHED),)
                            if os.path.exists(self.provider.path)
                            else (("github-token", ComponentState.ABSENT),)
                        ),
                    ),
                )
            )
        actions = later.actions()
        self.assertIsInstance(actions, Ok, getattr(actions, "diagnostics", ()))
        return assemble_consumer_machine(
            tuple(inspections),
            credentials=tuple(
                CredentialObservation(
                    reference,
                    ProviderState.AVAILABLE,
                    CredentialState.PRESENT
                    if os.path.exists(self.provider.path)
                    else CredentialState.ABSENT,
                    "reference resolves",
                )
                for reference in self.receipt.credentials
            ),
            actions=actions.value,
            today=TODAY,
        )

    def drawn(self, screen: ConsumerScreen) -> str:
        """Draw one screen, reached the way a person reaches it: by the accepted routes."""

        source = CanonicalScreenSource(screens_from(self.machine()))
        state = _reload(source, ConsumerUiState(), entering=True)
        for hop in _route(screen):
            state, _ = reduce_consumer_ui(
                state, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=hop)
            )
            state = _reload(source, state, entering=True)
        self.assertIs(state.session.screen, screen)
        return "\n".join(frame(source, state))

    def test_the_dashboard_a_second_process_opens_counts_what_is_really_installed(self):
        drawn = self.drawn(ConsumerScreen.DASHBOARD)

        self.assertIn("1 installed", drawn)
        self.assertIn("1 ready", drawn)
        self.assertIn("Installed public/mcp/github@1.5.0", drawn)

    def test_installed_lists_the_collection_that_asked_for_the_artifact_and_the_artifact(self):
        drawn = self.drawn(ConsumerScreen.INSTALLED)

        self.assertIn(KIT.owner, drawn)
        self.assertIn(str(COORDINATE), drawn)

    def test_a_launcher_broken_after_the_install_is_what_the_screen_says(self):
        pathlib.Path(self.receipt.launcher).write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")

        drawn = self.drawn(ConsumerScreen.INSTALLED)
        doctor = self.drawn(ConsumerScreen.DOCTOR)

        self.assertIn("broken", drawn)
        self.assertIn(str(COORDINATE), doctor)

    def test_the_collection_health_is_its_members_health(self):
        pathlib.Path(self.receipt.launcher).write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")

        machine = self.machine()

        self.assertEqual([item.collection for item in machine.collections], [KIT.owner])
        self.assertEqual(machine.collections[0].health, "broken")
        self.assertEqual(machine.collections[0].members_requiring_attention, (str(COORDINATE),))

    def test_the_credential_screen_names_the_installation_that_depends_on_it(self):
        drawn = self.drawn(ConsumerScreen.CREDENTIALS)

        self.assertIn("github-token", drawn)
        self.assertIn("Used by 1", drawn)

    def test_no_screen_this_machine_draws_contains_the_real_secret(self):
        drawn = "\n".join(self.drawn(screen) for screen in ConsumerScreen)

        self.assertNotIn(self.token, drawn)
        self.assertNotIn("is not available yet", drawn)


if __name__ == "__main__":
    unittest.main()
