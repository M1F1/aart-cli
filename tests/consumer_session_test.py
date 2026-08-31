"""One machine, assembled once into everything the consumer application can say about it.

The screens are projections; this is what decides *what* they are projections of. The rules under
test are the ones nothing else can decide: which Collection an installed artifact belongs to, which
installations depend on a credential, and what the Dashboard is counting.
"""

from __future__ import annotations

import datetime as dt
import unittest

from agent_artifacts.application.consumer_session import (
    InstalledInspection,
    assemble_consumer_machine,
)
from agent_artifacts.application.consumer_views import ActivityRecord, project_receipt_detail
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.effects import ConfigureHarness, WriteFile
from agent_artifacts.domain.harness import McpRegistration, Scope, mcp_target
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    ObjectDigest,
    SourceAlias,
)
from agent_artifacts.domain.receipts import InstallationReceipt, InstalledRecord
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    ObservedComponent,
)
from agent_artifacts.domain.selection import OwnershipKind, OwnershipReason
from tests.consumer_activity_test import lifecycle_outcome

TODAY = dt.date(2026, 8, 31)
KIT = OwnershipReason(OwnershipKind.COLLECTION, "public/collection/data-scientist@1.0.0")
LAUNCHER = ComponentId(Component.LAUNCHER)
HARNESS = ComponentId(Component.HARNESS, "tabnine")
TOKEN = CredentialReference(
    InputId("github-token"), CredentialProviderRef("macos-keychain", "github.com", "work")
)
OTHER = CredentialReference(
    InputId("jira-token"), CredentialProviderRef("macos-keychain", "jira.acme", "work")
)


def coordinate(name: str = "github", version: str = "1.6.0") -> ArtifactCoordinate:
    return ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", name), version)


def receipt(name: str = "github", credentials=(TOKEN,)) -> InstallationReceipt:
    root = f"/opt/agents/mcp/{name}"
    return InstallationReceipt(
        f"mcp/{name}",
        root,
        f"{root}/launch.sh",
        ObjectDigest("sha256", "a" * 64),
        f"{root}/runtime/.venv/bin/python",
        registrations=(
            McpRegistration(mcp_target("tabnine", Scope.PROJECT), name, f"{root}/launch.sh"),
        ),
        credentials=credentials,
    )


def desired(name: str = "github") -> DesiredState:
    root = f"/opt/agents/mcp/{name}"
    return DesiredState(
        coordinate(name),
        (
            DesiredComponent(
                LAUNCHER, (WriteFile(f"{root}/launch.sh", "sha256:" + "a" * 64, True),)
            ),
            DesiredComponent(
                HARNESS, (ConfigureHarness("tabnine", f"mcp/{name}", ".tabnine/settings.json"),)
            ),
        ),
    )


def current(name: str = "github", state: ComponentState = ComponentState.MATCHED) -> CurrentState:
    return CurrentState(
        coordinate(name),
        (ObservedComponent(LAUNCHER, state), ObservedComponent(HARNESS, ComponentState.MATCHED)),
    )


def inspection(
    name: str = "github",
    *,
    ownership: tuple[OwnershipReason, ...] = (),
    state: ComponentState = ComponentState.MATCHED,
    credentials=(TOKEN,),
    update_available: bool = False,
) -> InstalledInspection:
    return InstalledInspection(
        InstalledRecord(coordinate(name), receipt(name, credentials), ownership),
        desired(name),
        current(name, state),
        update_available,
    )


def observed(
    reference: CredentialReference, state=CredentialState.PRESENT
) -> CredentialObservation:
    return CredentialObservation(reference, ProviderState.AVAILABLE, state, "reference resolves")


class ConsumerMachineTest(unittest.TestCase):
    def test_an_installed_record_becomes_a_row_with_measured_health_and_recorded_ownership(self):
        machine = assemble_consumer_machine((inspection(ownership=(KIT,)),), today=TODAY)

        self.assertEqual(len(machine.installed), 1)
        row = machine.installed[0]
        self.assertEqual(row.coordinate, "public/mcp/github@1.6.0")
        self.assertEqual(row.health, "ready")
        self.assertEqual([item.owner for item in row.ownership], [KIT.owner])

    def test_health_is_measured_rather_than_assumed_from_the_record_existing(self):
        machine = assemble_consumer_machine(
            (inspection(state=ComponentState.DIVERGENT),), today=TODAY
        )

        self.assertEqual(machine.installed[0].health, "broken")
        self.assertEqual([item.component for item in machine.installed[0].drift], ["launcher"])
        self.assertEqual(machine.doctor.issues, ("public/mcp/github@1.6.0",))

    def test_artifacts_a_collection_owns_are_aggregated_into_that_collection(self):
        machine = assemble_consumer_machine(
            (
                inspection(ownership=(KIT,)),
                inspection("jira", ownership=(KIT,), state=ComponentState.DIVERGENT),
                inspection("slack"),
            ),
            today=TODAY,
        )

        self.assertEqual([item.collection for item in machine.collections], [KIT.owner])
        group = machine.collections[0]
        self.assertEqual(
            [item.artifact for item in group.members],
            ["public/mcp/github@1.6.0", "public/mcp/jira@1.6.0"],
        )
        self.assertEqual(group.health, "broken")
        self.assertEqual(group.members_requiring_attention, ("public/mcp/jira@1.6.0",))

    def test_a_credential_is_depended_on_by_the_installations_that_name_it(self):
        machine = assemble_consumer_machine(
            (inspection(), inspection("jira", credentials=(OTHER,))),
            credentials=(observed(TOKEN), observed(OTHER)),
            today=TODAY,
        )

        dependants = {item.input: item.dependants for item in machine.credentials}
        self.assertEqual(dependants["github-token"], ("public/mcp/github@1.6.0",))
        self.assertEqual(dependants["jira-token"], ("public/mcp/jira@1.6.0",))

    def test_a_credential_nothing_installed_uses_is_still_listed_owing_nothing(self):
        machine = assemble_consumer_machine(
            (inspection(),), credentials=(observed(TOKEN), observed(OTHER)), today=TODAY
        )

        unused = next(item for item in machine.credentials if item.input == "jira-token")
        self.assertEqual(unused.dependants, ())
        self.assertIn("delete", unused.actions)

    def test_a_credential_that_cannot_be_resolved_is_counted_as_needing_attention(self):
        machine = assemble_consumer_machine(
            (inspection(),),
            credentials=(observed(TOKEN, CredentialState.INVALID),),
            today=TODAY,
        )

        self.assertEqual(machine.dashboard.credential_attention_count, 1)

    def test_the_dashboard_counts_the_rows_and_opens_with_what_just_happened(self):
        receipts = (
            project_receipt_detail(ActivityRecord("2026-08-31T14:32:00Z", lifecycle_outcome())),
        )

        machine = assemble_consumer_machine(
            (inspection(), inspection("jira", update_available=True)),
            actions=receipts,
            registries=(),
            today=TODAY,
        )

        self.assertEqual(machine.dashboard.installed_count, 2)
        self.assertEqual(machine.dashboard.update_count, 1)
        self.assertEqual(machine.dashboard.recent_activity, ("Installed public/mcp/github@1.6.0",))
        self.assertEqual([day.label for day in machine.activity.days], ["Today"])
        self.assertEqual(machine.receipts, receipts)

    def test_an_empty_machine_is_an_empty_machine_rather_than_an_error(self):
        machine = assemble_consumer_machine((), today=TODAY)

        self.assertEqual(machine.installed, ())
        self.assertEqual(machine.dashboard.installed_count, 0)
        self.assertEqual(machine.activity.days, ())
        self.assertEqual(machine.doctor.issues, ())


if __name__ == "__main__":
    unittest.main()
