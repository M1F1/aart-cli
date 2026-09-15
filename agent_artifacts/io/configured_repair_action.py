"""The one adapter a public command or the persistent shell calls to verify and repair.

The third of the configured compositions, beside `configured_installation_action` and
`configured_uninstall_action`, and the smallest of them. A repair resolves nothing and removes
nothing: what should be true is what this machine already recorded, so the receipt is the whole
input, and the only question is whether the machine still matches it.

That is also the boundary of what a repair can converge. The desired state is derived from the
receipt, so a repair fixes exactly the components a receipt can describe -- deliveries, merged
regions, settings entries, harness registrations, environments and dependencies. It cannot rewrite
a launcher: a receipt records the digest its content had, never the content, and writing a file
whose bytes nothing here holds is refused at that step rather than approximated (D-086). A repair
that needs the payload back needs the object it was installed from, which is an install.

Preparation touches nothing. Completion re-plans under the mutation lease and refuses if the
machine moved since the review, then records what happened and re-reads the machine it left behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agent_artifacts.application.consumer_session import ConsumerMachine, InstalledInspection
from agent_artifacts.application.execution import (
    EffectInterpreter,
    LifecycleExecutionOutcome,
    execute_lifecycle,
)
from agent_artifacts.application.intents import (
    LifecyclePlan,
    plan_lifecycle_intent,
    repair_intent,
)
from agent_artifacts.application.receipt_recording import (
    RecordedOutcome,
    record_lifecycle_outcome,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import (
    ArtifactReceipt,
    InstalledRecord,
    PlacedArtifactReceipt,
)
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState
from agent_artifacts.domain.result import Err, Ok, Result

from .configured_installation_action import InstallationHost
from .consumer_machine import read_consumer_machine
from .credentials import CredentialProviderPort
from .execution import (
    CredentialEffectInterpreter,
    DeliveryEffectInterpreter,
    FileEffectInterpreter,
    HarnessEffectInterpreter,
    LocalMutationLock,
    ManagedBlockInterpreter,
    RuntimeEffectInterpreter,
    SettingsEntryInterpreter,
)
from .harness import LocalHarnessRegistry
from .installation_observation import observe_recorded_installation
from .python_runtime import LocalPythonRuntime
from .receipt_store import LocalReceiptStore

__all__ = [
    "CONFIGURED_REPAIR_INVALID",
    "CompletedConfiguredRepair",
    "PreparedConfiguredRepair",
    "complete_configured_repair",
    "interpreters_for_receipt",
    "prepare_configured_repair",
]

CONFIGURED_REPAIR_INVALID = DiagnosticCode("configured-repair-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURED_REPAIR_INVALID, Severity.ERROR, message),))


def interpreters_for_receipt(
    receipt: ArtifactReceipt,
    *,
    registry: LocalHarnessRegistry,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    timeout_seconds: float = 900.0,
    offline: bool = False,
) -> tuple[EffectInterpreter, ...]:
    """The adapters one recorded installation may be repaired through.

    Bound to what this receipt actually records, for the reason every interpreter assembly is
    (D-072): a repair reaches into directories the harness owns, and an adapter that accepted any
    destination could rewrite a file this artifact never installed. Each is built only when the
    receipt gives it something to hold, because they refuse to exist empty -- one holding nothing
    would claim every effect of its kind and then refuse it as one it was not given.

    No launcher content is offered, because a receipt does not record any. A repair whose plan
    rewrites the launcher therefore fails closed at that step, naming the content nothing here
    holds, rather than writing something nobody planned.
    """

    interpreters: list[EffectInterpreter] = [
        FileEffectInterpreter(ArtifactEnvironment(receipt.artifact, receipt.root))
    ]
    if isinstance(receipt, PlacedArtifactReceipt):
        if receipt.deliveries:
            interpreters.append(DeliveryEffectInterpreter(receipt.artifact, receipt.deliveries))
        if receipt.merges:
            interpreters.append(ManagedBlockInterpreter(receipt.artifact, receipt.merges))
        if receipt.settings:
            interpreters.append(SettingsEntryInterpreter(receipt.artifact, receipt.settings))
        return tuple(interpreters)
    interpreters.append(
        RuntimeEffectInterpreter(
            LocalPythonRuntime(
                ArtifactEnvironment(receipt.artifact, receipt.root),
                timeout_seconds=timeout_seconds,
                offline=offline,
            )
        )
    )
    interpreters.append(
        HarnessEffectInterpreter(registry, receipt.registrations, artifact=receipt.artifact)
    )
    providers = {item.provider: item for item in credential_providers}
    for name in sorted({item.provider.provider for item in receipt.credentials}):
        provider = providers.get(name)
        if provider is None:
            continue
        interpreters.append(
            CredentialEffectInterpreter(
                provider,
                tuple(item for item in receipt.credentials if item.provider.provider == name),
            )
        )
    return tuple(interpreters)


@dataclass(frozen=True, slots=True)
class PreparedConfiguredRepair:
    """One measured installation and the plan that would put it back as recorded."""

    record: InstalledRecord
    plan: LifecyclePlan

    def __post_init__(self) -> None:
        if not isinstance(self.record, InstalledRecord) or not isinstance(self.plan, LifecyclePlan):
            raise ValueError("a prepared configured repair is invalid")
        if self.plan.repair.artifact != self.record.coordinate:
            raise ValueError("a prepared repair plans a different artifact than it records")

    @property
    def review_digest(self) -> ObjectDigest:
        return self.plan.review_digest

    @property
    def converged(self) -> bool:
        """Whether nothing is wrong: a verification that found the machine as it was recorded."""

        return not self.plan.repair.steps


@dataclass(frozen=True, slots=True)
class CompletedConfiguredRepair:
    """What the repair did and recorded, beside the machine as it stands afterwards."""

    outcome: LifecycleExecutionOutcome
    recorded: RecordedOutcome
    machine: ConsumerMachine

    def __post_init__(self) -> None:
        if (
            not isinstance(self.outcome, LifecycleExecutionOutcome)
            or not isinstance(self.recorded, RecordedOutcome)
            or not isinstance(self.machine, ConsumerMachine)
        ):
            raise ValueError("a completed configured repair is invalid")


def prepare_configured_repair(
    inspection: InstalledInspection,
    *,
    policy: EffectivePolicy,
) -> Result[PreparedConfiguredRepair]:
    """Plan putting one measured installation back as it was recorded, mutating nothing.

    The inspection is passed in rather than taken, because measuring is what screen 20 already
    did to decide there was something to look at. Measuring again here would answer a different
    question than the one somebody is reading.
    """

    if not isinstance(inspection, InstalledInspection):
        return _error("preparing a repair needs one inspected installation")
    planned = plan_lifecycle_intent(
        repair_intent(inspection.desired), inspection.current, policy=policy
    )
    if isinstance(planned, Err):
        return planned
    try:
        return Ok(PreparedConfiguredRepair(inspection.record, planned.value))
    except ValueError as error:
        return _error(f"this repair cannot be prepared: {error}")


def complete_configured_repair(
    prepared: PreparedConfiguredRepair,
    *,
    expected_review_digest: ObjectDigest | None,
    host: InstallationHost,
    policy: EffectivePolicy,
    recorded_at: str,
    today: date,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    timeout_seconds: float = 900.0,
    offline: bool = False,
) -> Result[CompletedConfiguredRepair]:
    """Execute the confirmed repair, record it, and re-read the machine it left behind."""

    if not isinstance(prepared, PreparedConfiguredRepair) or not isinstance(host, InstallationHost):
        return _error("completing a repair needs a prepared plan and a host")
    if not isinstance(expected_review_digest, ObjectDigest):
        return _error("completing a repair needs the confirmed review digest")
    if expected_review_digest != prepared.review_digest:
        return _error(
            f"the repair changed since it was reviewed: expected {expected_review_digest}, "
            f"recomputed {prepared.review_digest}"
        )

    receipt = prepared.record.receipt
    registry = LocalHarnessRegistry(host.harness_root)

    def inspect(desired: DesiredState) -> CurrentState:
        if desired.artifact != prepared.record.coordinate:
            raise ValueError(f"{desired.artifact} is not what this repair measures")
        return observe_recorded_installation(
            desired, receipt, registry=registry, credential_providers=credential_providers
        )

    executed = execute_lifecycle(
        prepared.plan,
        policy=policy,
        interpreters=interpreters_for_receipt(
            receipt,
            registry=registry,
            credential_providers=credential_providers,
            timeout_seconds=timeout_seconds,
            offline=offline,
        ),
        inspect=inspect,
        lock=LocalMutationLock(host.state_root, host.lock_scope),
    )
    if isinstance(executed, Err):
        return executed

    recorded = record_lifecycle_outcome(
        executed.value,
        recorded_at=recorded_at,
        store=LocalReceiptStore(host.state_root),
        receipt=receipt,
    )
    if isinstance(recorded, Err):
        return recorded

    machine = read_consumer_machine(
        state_root=host.state_root,
        harness_root=host.harness_root,
        today=today,
        project_root=host.project_root,
        user_home=host.user_home,
        data_root=host.data_root,
        credential_providers=credential_providers,
    )
    if isinstance(machine, Err):
        return machine
    try:
        return Ok(CompletedConfiguredRepair(executed.value, recorded.value, machine.value))
    except ValueError as error:
        return _error(f"this repair cannot be completed: {error}")
