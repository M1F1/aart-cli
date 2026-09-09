"""The one adapter a public command or the persistent shell calls to take an installation back out.

The counterpart of `configured_installation_action`, and deliberately a shorter composition. An
uninstall resolves nothing: what is removed is what this machine recorded, so there is no registry
snapshot to read, no object to materialize and no input form to answer. That is not an omission --
an installed artifact stays installed after its source is removed from the configuration, and an
uninstall that needed the source would refuse exactly when somebody most needs it to work.

The two properties this exists to hold are the same ones the install composition holds. Preparation
touches nothing: it reads receipts, measures the machine and produces a review. And completion
hands back the machine as it was read afterwards, never as the removal believed it left it -- an
uninstall that half-worked has to be visible as what is still there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agent_artifacts.application.consumer_session import ConsumerMachine
from agent_artifacts.application.execution import (
    EffectInterpreter,
    InstallationExecutionOutcome,
    execute_installation,
)
from agent_artifacts.application.receipt_recording import (
    RecordedTransaction,
    record_installation_transaction,
)
from agent_artifacts.application.removal_proposal import (
    PlannedRemoval,
    RemovalProposal,
    plan_removal,
    propose_removal,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import DeleteCredential
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import InstalledRecord, PlacedArtifactReceipt
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import OwnershipReason

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
    SettingsEntryInterpreter,
)
from .harness import LocalHarnessRegistry
from .installation_observation import observe_recorded_installation
from .receipt_store import LocalReceiptStore

__all__ = [
    "CONFIGURED_UNINSTALL_INVALID",
    "CompletedConfiguredUninstall",
    "PreparedConfiguredUninstall",
    "complete_configured_uninstall",
    "prepare_configured_uninstall",
]

CONFIGURED_UNINSTALL_INVALID = DiagnosticCode("configured-uninstall-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURED_UNINSTALL_INVALID, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class PreparedConfiguredUninstall:
    """A reviewable removal, and the records it was derived from."""

    proposal: RemovalProposal
    removals: tuple[PlannedRemoval, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, RemovalProposal) or any(
            not isinstance(item, PlannedRemoval) for item in self.removals
        ):
            raise ValueError("a prepared configured uninstall is invalid")

    @property
    def review_digest(self) -> ObjectDigest:
        return self.proposal.review_digest


@dataclass(frozen=True, slots=True)
class CompletedConfiguredUninstall:
    """What was taken out and recorded, beside the machine as it stands afterwards."""

    execution: InstallationExecutionOutcome
    recorded: RecordedTransaction
    machine: ConsumerMachine

    def __post_init__(self) -> None:
        if (
            not isinstance(self.execution, InstallationExecutionOutcome)
            or not isinstance(self.recorded, RecordedTransaction)
            or not isinstance(self.machine, ConsumerMachine)
        ):
            raise ValueError("a completed configured uninstall is invalid")


def _interpreters(
    removals: tuple[PlannedRemoval, ...],
    proposal: RemovalProposal,
    *,
    registry: LocalHarnessRegistry,
    credential_providers: tuple[CredentialProviderPort, ...],
) -> Result[tuple[EffectInterpreter, ...]]:
    """The adapters this removal is carried out through, each bound to what it may take away.

    Bound to this removal's own paths, registrations and references, for the same reason an
    install's are (D-072): withdrawal reaches into a directory the harness owns rather than one
    AART owns, and an interpreter that accepted any destination could take away a file this
    artifact never delivered.

    A credential adapter is required only when the reviewed removal actually deletes a credential.
    Retaining one is the default and needs nobody to ask a provider anything, so demanding an
    adapter for it would make an uninstall depend on a keychain it never intends to touch.
    """

    interpreters: list[EffectInterpreter] = []
    for removal in removals:
        receipt = removal.record.receipt
        interpreters.append(
            FileEffectInterpreter(ArtifactEnvironment(receipt.artifact, receipt.root))
        )
        if isinstance(receipt, PlacedArtifactReceipt):
            # Only what this receipt actually recorded: both adapters refuse to exist empty, and
            # one holding nothing would claim every effect of its kind in the transaction and then
            # refuse it as one it was not given.
            if receipt.deliveries:
                interpreters.append(DeliveryEffectInterpreter(receipt.artifact, receipt.deliveries))
            if receipt.merges:
                interpreters.append(ManagedBlockInterpreter(receipt.artifact, receipt.merges))
            if receipt.settings:
                interpreters.append(SettingsEntryInterpreter(receipt.artifact, receipt.settings))
            continue
        interpreters.append(
            HarnessEffectInterpreter(registry, receipt.registrations, artifact=receipt.artifact)
        )

    deleting = {
        effect.provider for effect in proposal.effects if isinstance(effect, DeleteCredential)
    }
    if not deleting:
        return Ok(tuple(interpreters))
    providers = {item.provider: item for item in credential_providers}
    missing = sorted(name for name in deleting if name not in providers)
    if missing:
        return _error(
            "nothing here can delete credentials held by "
            + ", ".join(missing)
            + "; no adapter for that provider was supplied"
        )
    references = tuple(
        reference
        for removal in removals
        if not isinstance(removal.record.receipt, PlacedArtifactReceipt)
        for reference in removal.record.receipt.credentials
    )
    interpreters.extend(
        CredentialEffectInterpreter(
            providers[name],
            tuple(item for item in references if item.provider.provider == name),
        )
        for name in sorted(deleting)
    )
    return Ok(tuple(interpreters))


def prepare_configured_uninstall(
    records: tuple[InstalledRecord, ...],
    *,
    host: InstallationHost,
    policy: EffectivePolicy,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    release: tuple[OwnershipReason, ...] | None = None,
    delete_credentials: bool = False,
) -> Result[PreparedConfiguredUninstall]:
    """Plan taking these recorded installations out, measuring the machine and mutating nothing.

    `release` defaults to everything each record is owned for, which is what somebody uninstalling
    an artifact directly means. A Collection removal passes the one claim it is giving up, so an
    artifact something else still wants stays installed and the record narrows instead.
    """

    if not isinstance(host, InstallationHost):
        return _error("preparing an uninstall needs an installation host")
    if not records:
        return _error("preparing an uninstall needs at least one recorded installation")

    registry = LocalHarnessRegistry(host.harness_root)
    removals: list[PlannedRemoval] = []
    observed: list[tuple[object, CurrentState]] = []
    for record in records:
        planned = plan_removal(
            record,
            release=record.ownership if release is None else release,
            delete_credentials=delete_credentials,
        )
        if isinstance(planned, Err):
            return planned
        removals.append(planned.value)
        observed.append(
            (
                record.coordinate,
                # Measured against the state the removal converges to, not against the one it is
                # leaving. Both name the same components; only this one is the vocabulary the
                # executor re-measures in before it is allowed to touch anything, and a review
                # written in the other one would be stale the moment it was checked.
                observe_recorded_installation(
                    planned.value.removal,
                    record.receipt,
                    registry=registry,
                    credential_providers=credential_providers,
                ),
            )
        )

    proposed = propose_removal(
        tuple(removals),
        observed=tuple(observed),  # type: ignore[arg-type]
        policy=policy,
    )
    if isinstance(proposed, Err):
        return proposed
    try:
        return Ok(PreparedConfiguredUninstall(proposed.value, tuple(removals)))
    except ValueError as error:
        return _error(f"this uninstall cannot be prepared: {error}")


def complete_configured_uninstall(
    prepared: PreparedConfiguredUninstall,
    *,
    expected_review_digest: ObjectDigest | None,
    host: InstallationHost,
    policy: EffectivePolicy,
    recorded_at: str,
    today: date,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
) -> Result[CompletedConfiguredUninstall]:
    """Execute the confirmed removal, record it, and re-read the machine it left behind."""

    if not isinstance(prepared, PreparedConfiguredUninstall) or not isinstance(
        host, InstallationHost
    ):
        return _error("completing an uninstall needs a prepared removal and a host")
    if not isinstance(expected_review_digest, ObjectDigest):
        return _error("completing an uninstall needs the confirmed review digest")
    if expected_review_digest != prepared.review_digest:
        return _error(
            f"the removal changed since it was reviewed: expected {expected_review_digest}, "
            f"recomputed {prepared.review_digest}"
        )

    registry = LocalHarnessRegistry(host.harness_root)
    interpreters = _interpreters(
        prepared.removals,
        prepared.proposal,
        registry=registry,
        credential_providers=credential_providers,
    )
    if isinstance(interpreters, Err):
        return interpreters

    records = {item.coordinate: item.record.receipt for item in prepared.removals}

    def inspect(desired: DesiredState) -> CurrentState:
        receipt = records.get(desired.artifact)
        if receipt is None:
            raise ValueError(f"{desired.artifact} is not part of this removal")
        return observe_recorded_installation(
            desired, receipt, registry=registry, credential_providers=credential_providers
        )

    executed = execute_installation(
        prepared.proposal,
        policy=policy,
        interpreters=interpreters.value,
        inspect=inspect,
        lock=LocalMutationLock(host.state_root, host.lock_scope),
    )
    if isinstance(executed, Err):
        return executed

    recorded = record_installation_transaction(
        executed.value,
        recorded_at=recorded_at,
        store=LocalReceiptStore(host.state_root),
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
        return Ok(CompletedConfiguredUninstall(executed.value, recorded.value, machine.value))
    except ValueError as error:
        return _error(f"this uninstall cannot be completed: {error}")
