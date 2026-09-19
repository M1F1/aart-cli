"""Configure one installed runtime artifact without reinstalling any other component.

Preparation reads the selected, receipt-owned files and lowers their pure transformation through
``configure_intent``.  Completion checks the reviewed identity, takes the installation mutation
lease, enforces a compare-and-swap baseline for every selected file, executes the shared lifecycle,
records the updated digest-only receipt, and re-reads the machine.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from aart_cli.application.configuration_edit import (
    ConfigurationEdit,
    plan_configuration_edit,
)
from aart_cli.application.consumer_session import ConsumerMachine, InstalledInspection
from aart_cli.application.execution import LifecycleExecutionOutcome, execute_lifecycle
from aart_cli.application.intents import (
    LifecyclePlan,
    configure_intent,
    plan_lifecycle_intent,
)
from aart_cli.application.receipt_recording import RecordedOutcome, record_lifecycle_outcome
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import InputId, ObjectDigest
from aart_cli.domain.inputs import InputValidation
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.receipts import InstallationReceipt, InstalledRecord
from aart_cli.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredState,
    compare_states,
)
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.hashing import sha256_bytes

from .configured_installation_action import InstallationHost
from .configured_repair_action import interpreters_for_receipt
from .consumer_machine import read_consumer_machine
from .credentials import CredentialProviderPort
from .execution import FileEffectInterpreter, LocalMutationLock
from .harness import LocalHarnessRegistry
from .installation_observation import observe_recorded_installation
from .receipt_store import LocalReceiptStore

__all__ = [
    "CONFIGURED_CONFIGURATION_INVALID",
    "CompletedConfiguredConfiguration",
    "PreparedConfiguredConfiguration",
    "complete_configured_configuration",
    "prepare_configured_configuration",
]

CONFIGURED_CONFIGURATION_INVALID = DiagnosticCode("configured-configuration-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURED_CONFIGURATION_INVALID, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class PreparedConfiguredConfiguration:
    """One CONFIGURATION-only reviewed lifecycle and its compare-and-swap file baseline."""

    record: InstalledRecord
    edit: ConfigurationEdit
    plan: LifecyclePlan

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record, InstalledRecord)
            or not isinstance(self.record.receipt, InstallationReceipt)
            or not isinstance(self.edit, ConfigurationEdit)
            or not isinstance(self.plan, LifecyclePlan)
            or self.record.coordinate != self.plan.repair.artifact
            or self.edit.receipt.artifact != self.record.receipt.artifact
            or any(
                step.component.component is not Component.CONFIGURATION
                for step in self.plan.repair.steps
            )
            or {step.component.name for step in self.plan.repair.steps}
            != {item.harness for item in self.edit.files}
        ):
            raise ValueError("a prepared configuration action is invalid")

    @property
    def review_digest(self) -> ObjectDigest:
        return self.plan.review_digest


@dataclass(frozen=True, slots=True)
class CompletedConfiguredConfiguration:
    outcome: LifecycleExecutionOutcome
    recorded: RecordedOutcome
    machine: ConsumerMachine

    def __post_init__(self) -> None:
        if (
            not isinstance(self.outcome, LifecycleExecutionOutcome)
            or not isinstance(self.recorded, RecordedOutcome)
            or not isinstance(self.machine, ConsumerMachine)
        ):
            raise ValueError("a completed configuration action is invalid")


def prepare_configured_configuration(
    inspection: InstalledInspection,
    *,
    input_id: InputId,
    harnesses: tuple[str, ...],
    value: str,
    policy: EffectivePolicy,
    validation: InputValidation | None = None,
) -> Result[PreparedConfiguredConfiguration]:
    """Read and plan one exact edit, without mutating the installation."""

    if not isinstance(inspection, InstalledInspection):
        return _error("configuring needs one inspected installation")
    receipt = inspection.record.receipt
    if not isinstance(receipt, InstallationReceipt):
        return _error("only an installed runtime artifact has editable configuration files")

    records = {item.harness: item for item in receipt.configuration_files}
    if not harnesses:
        return _error("choose at least one installed harness")
    if (
        len(set(harnesses)) != len(harnesses)
        or any(not isinstance(item, str) or not item for item in harnesses)
        or any(item not in records for item in harnesses)
    ):
        return _error("the configuration harness choice is empty, invalid or stale")
    chosen = {ComponentId(Component.CONFIGURATION, harness) for harness in harnesses}
    existing_drift = compare_states(inspection.desired, inspection.current)
    if existing_drift:
        selected_drift = tuple(item for item in existing_drift if item.component in chosen)
        if selected_drift:
            names = ", ".join(item.component.name for item in selected_drift)
            return _error(
                f"the chosen configuration changed outside AART: {names}; inspect it first"
            )
        return _error(
            "this installation already has unrelated drift; verify or repair it before changing "
            "configuration so the edit cannot include unrelated components"
        )

    contents: list[tuple[str, bytes]] = []
    for harness in harnesses:
        record = records[harness]
        try:
            contents.append((harness, Path(record.path).read_bytes()))
        except FileNotFoundError:
            return _error(f"{harness}'s configuration changed outside AART: the file is missing")
        except OSError:
            return _error(f"{harness}'s configuration could not be read")

    edited = plan_configuration_edit(
        receipt,
        input_id=input_id,
        harnesses=harnesses,
        value=value,
        current_files=tuple(contents),
        validation=validation,
    )
    if isinstance(edited, Err):
        return edited

    intent = configure_intent(inspection.desired, edited.value.replacements)
    # The old files matched the old desired state and each replacement has a different digest.
    # Re-express just those observations as divergent from the new desired state; every other
    # observation stays exactly as measured for the INV-179 scope check above.
    current = CurrentState(
        inspection.current.artifact,
        tuple(
            replace(item, state=ComponentState.DIVERGENT) if item.id in chosen else item
            for item in inspection.current.components
        ),
    )
    planned = plan_lifecycle_intent(intent, current, policy=policy)
    if isinstance(planned, Err):
        return planned
    if {step.component for step in planned.value.repair.steps} != chosen:
        return _error("the configuration plan would change something outside the chosen harnesses")
    try:
        return Ok(PreparedConfiguredConfiguration(inspection.record, edited.value, planned.value))
    except ValueError as error:
        return _error(f"this configuration edit cannot be prepared: {error}")


def complete_configured_configuration(
    prepared: PreparedConfiguredConfiguration,
    *,
    expected_review_digest: ObjectDigest | None,
    host: InstallationHost,
    policy: EffectivePolicy,
    recorded_at: str,
    today: date,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    timeout_seconds: float = 900.0,
    offline: bool = False,
) -> Result[CompletedConfiguredConfiguration]:
    """Execute the confirmed CONFIGURATION-only lifecycle and persist its updated receipt."""

    if not isinstance(prepared, PreparedConfiguredConfiguration) or not isinstance(
        host, InstallationHost
    ):
        return _error("completing configuration needs a prepared plan and a host")
    if not isinstance(expected_review_digest, ObjectDigest):
        return _error("completing configuration needs the confirmed review digest")
    if expected_review_digest != prepared.review_digest:
        return _error(
            f"the configuration plan changed since it was reviewed: expected "
            f"{expected_review_digest}, recomputed {prepared.review_digest}"
        )

    receipt = prepared.edit.receipt
    registry = LocalHarnessRegistry(host.harness_root)
    interpreters = list(
        interpreters_for_receipt(
            receipt,
            registry=registry,
            credential_providers=credential_providers,
            timeout_seconds=timeout_seconds,
            offline=offline,
        )
    )
    file_interpreter = next(
        (item for item in interpreters if isinstance(item, FileEffectInterpreter)), None
    )
    if file_interpreter is None:
        return _error("no file effect boundary is available for this configuration")
    for item in prepared.edit.files:
        if file_interpreter.offer(item.content) != str(item.updated.digest):
            return _error("the offered configuration content does not match its reviewed digest")

    baselines = {
        item.previous.path: (item.previous.digest, item.updated.digest)
        for item in prepared.edit.files
    }

    def inspect(desired: DesiredState) -> CurrentState:
        if desired.artifact != prepared.record.coordinate:
            raise ValueError(f"{desired.artifact} is not what this configuration action measures")
        for path, accepted in baselines.items():
            try:
                digest = sha256_bytes(Path(path).read_bytes())
            except FileNotFoundError as error:
                raise ValueError(
                    f"{path} changed outside AART since Review: the file is missing"
                ) from error
            except OSError as error:
                raise ValueError(
                    f"{path} changed outside AART since Review: it cannot be read"
                ) from error
            if digest not in accepted:
                raise ValueError(f"{path} changed outside AART since Review")
        return observe_recorded_installation(
            desired,
            receipt,
            registry=registry,
            credential_providers=credential_providers,
        )

    executed = execute_lifecycle(
        prepared.plan,
        policy=policy,
        interpreters=tuple(interpreters),
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
        return Ok(CompletedConfiguredConfiguration(executed.value, recorded.value, machine.value))
    except ValueError as error:
        return _error(f"this configuration edit cannot be completed: {error}")
