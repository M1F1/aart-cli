"""Read the canonical consumer machine from durable local evidence.

This is the imperative half of :func:`assemble_consumer_machine`.  Receipts and finished actions
are read once, each recorded installation is inspected once, and the resulting immutable machine
is handed to the consumer application.  Drawing a screen never reaches back into the filesystem.

An unavailable credential provider is not evidence that a credential is absent.  References for
which no provider was supplied therefore become ``UNKNOWN`` observations and ``UNKNOWN``
components.  The consumer can still open and explain the attention without inventing a fact.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from agent_artifacts.application.consumer_session import (
    ConsumerMachine,
    InstalledInspection,
    assemble_consumer_machine,
)
from agent_artifacts.application.installed_state import (
    current_state_from_observation,
    desired_state_from_receipt,
)
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.receipts import InstalledRecord
from agent_artifacts.domain.reconciliation import ComponentState
from agent_artifacts.domain.result import Err, Ok, Result

from .credentials import CredentialProviderPort
from .harness import LocalHarnessRegistry
from .receipt_store import LocalReceiptStore
from .runtime_projection import observe_installation

__all__ = ["read_consumer_machine"]


_COMPONENT_STATE = {
    CredentialState.PRESENT: ComponentState.MATCHED,
    CredentialState.ABSENT: ComponentState.ABSENT,
    CredentialState.INVALID: ComponentState.DIVERGENT,
    CredentialState.UNKNOWN: ComponentState.UNKNOWN,
}


def _references(records: Iterable[InstalledRecord]) -> tuple[CredentialReference, ...]:
    references: set[CredentialReference] = set()
    for record in records:
        references.update(record.receipt.credentials)
    return tuple(sorted(references))


def _unknown(reference: CredentialReference) -> CredentialObservation:
    return CredentialObservation(
        reference,
        ProviderState.UNKNOWN,
        CredentialState.UNKNOWN,
        "no configured provider was asked to inspect this reference",
    )


def read_consumer_machine(
    *,
    state_root: str,
    harness_root: str,
    today: date,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
) -> Result[ConsumerMachine]:
    """Read, inspect and assemble the machine the canonical consumer shell opens on.

    Providers are injected because credential inspection is an effect boundary.  A reference with
    no matching provider is kept as unknown; a provider that was explicitly supplied and then
    failed is reported as an inspection failure rather than silently downgraded.
    """

    providers = {item.provider: item for item in credential_providers}
    if len(providers) != len(credential_providers):
        raise ValueError("consumer machine reading needs one adapter per credential provider")

    store = LocalReceiptStore(state_root)
    installed = store.installations()
    if isinstance(installed, Err):
        return installed
    actions = store.actions()
    if isinstance(actions, Err):
        return actions

    observations: list[CredentialObservation] = []
    for reference in _references(installed.value):
        provider = providers.get(reference.provider.provider)
        if provider is None:
            observations.append(_unknown(reference))
            continue
        observed = provider.inspect(reference)
        if isinstance(observed, Err):
            return observed
        observations.append(observed.value)

    by_reference = {item.reference: item for item in observations}
    registry = LocalHarnessRegistry(harness_root)
    inspections = []
    for record in installed.value:
        receipt = record.receipt
        desired = desired_state_from_receipt(
            record.coordinate,
            receipt,
            base_interpreter=receipt.base_interpreter,
        )
        credential_states = tuple(
            (reference.input.value, _COMPONENT_STATE[by_reference[reference].state])
            for reference in receipt.credentials
        )
        current = current_state_from_observation(
            desired,
            receipt,
            observe_installation(receipt, registry=registry),
            credentials=credential_states,
        )
        inspections.append(InstalledInspection(record, desired, current))

    return Ok(
        assemble_consumer_machine(
            tuple(inspections),
            credentials=tuple(observations),
            actions=actions.value,
            today=today,
        )
    )
