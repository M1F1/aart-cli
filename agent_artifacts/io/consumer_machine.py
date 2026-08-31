"""Read the canonical consumer machine from durable local evidence.

This is the imperative half of :func:`assemble_consumer_machine`.  Receipts and finished actions
are read once, each recorded installation is inspected once, and the resulting immutable machine
is handed to the consumer application.  Drawing a screen never reaches back into the filesystem.

An unavailable credential provider is not evidence that a credential is absent.  References for
which no provider was supplied therefore become ``UNKNOWN`` observations and ``UNKNOWN``
components.  The consumer can still open and explain the attention without inventing a fact.

The same rule governs the legacy manifests.  Canonical receipts describe MCP servers; Skills,
guidelines, hooks and memory are still installed through the setup path, which records them in the
project or user ``manifest.json``.  Reading only the receipt store would report a machine with a
Skill installed as a machine with nothing installed -- and that emptiness would be acted on, by an
install that writes over it or a repair that finds nothing to repair.  So both manifests are read
here and carried through as unadopted installations until a kind-neutral canonical receipt replaces
them.  An unreadable manifest is a refusal, never an empty list.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

from agent_artifacts.application.consumer_session import (
    ConsumerMachine,
    InstalledInspection,
    UnadoptedInstallation,
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
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.receipts import InstalledRecord
from agent_artifacts.domain.reconciliation import ComponentState
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.install_state.model import InstallScope
from agent_artifacts.install_state.paths import install_state_paths
from agent_artifacts.install_state.schema import parse_install_state

from .credentials import CredentialProviderPort
from .harness import LocalHarnessRegistry
from .receipt_store import LocalReceiptStore
from .runtime_projection import observe_installation

__all__ = ["INSTALL_STATE_UNREADABLE", "read_consumer_machine"]

#: An installation manifest exists and could not be read.  Distinct from a missing manifest:
#: one means nothing was installed in that scope, the other means this process cannot tell.
INSTALL_STATE_UNREADABLE = DiagnosticCode("install-state-unreadable")


_COMPONENT_STATE = {
    CredentialState.PRESENT: ComponentState.MATCHED,
    CredentialState.ABSENT: ComponentState.ABSENT,
    CredentialState.INVALID: ComponentState.DIVERGENT,
    CredentialState.UNKNOWN: ComponentState.UNKNOWN,
}


def _error(message: str) -> Err:
    return Err((Diagnostic(INSTALL_STATE_UNREADABLE, Severity.ERROR, message),))


def _unversioned(coordinate: ArtifactCoordinate) -> str:
    """The identity two records share when one names a version and the other cannot.

    A legacy manifest record never carries a version; a canonical receipt may.  Comparing the
    printed forms would therefore never match, and the same installation would be listed twice
    -- once measured and once unknown -- which reads as two installs where there is one.
    """

    return f"{coordinate.source}/{coordinate.artifact}"


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


def _unadopted(
    scope: InstallScope, *, project_root: str, user_home: str, data_root: str
) -> Result[tuple[UnadoptedInstallation, ...]]:
    """Read one legacy manifest, or report why it could not be read.

    A missing manifest is genuinely no installations in that scope -- nothing ever wrote one.  A
    manifest that exists and cannot be parsed is the opposite: installations are recorded there and
    this process cannot see them, so the only safe answer is to refuse rather than to return the
    empty tuple that a missing file returns.
    """

    paths = install_state_paths(
        scope, project_root=project_root, user_home=user_home, data_root=data_root
    )
    manifest = Path(paths.destination_path)
    try:
        raw = manifest.read_bytes()
    except FileNotFoundError:
        return Ok(())
    except OSError as error:
        return _error(f"{manifest} could not be read: {error}")
    parsed = parse_install_state(raw, path=str(manifest))
    if isinstance(parsed, Err):
        return parsed
    return Ok(
        tuple(
            UnadoptedInstallation(str(record.coordinate), record.scope)
            for record in parsed.value.installations
        )
    )


def read_consumer_machine(
    *,
    state_root: str,
    harness_root: str,
    today: date,
    project_root: str,
    user_home: str,
    data_root: str,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
) -> Result[ConsumerMachine]:
    """Read, inspect and assemble the machine the canonical consumer shell opens on.

    Providers are injected because credential inspection is an effect boundary.  A reference with
    no matching provider is kept as unknown; a provider that was explicitly supplied and then
    failed is reported as an inspection failure rather than silently downgraded.

    The legacy roots are required rather than optional for the same reason.  A caller that omitted
    them would get a machine that quietly reports every Skill, guideline, hook and memory on the
    disk as absent, and there is no signature that should make that easy to ask for by accident.
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

    unadopted: list[UnadoptedInstallation] = []
    receipted = {_unversioned(record.coordinate) for record in installed.value}
    for scope in ("project", "user"):
        legacy = _unadopted(
            scope, project_root=project_root, user_home=user_home, data_root=data_root
        )
        if isinstance(legacy, Err):
            return legacy
        # A coordinate with a canonical receipt is answered by the receipt.  The manifest entry is
        # the same installation seen through the older lens, not a second one, and showing both
        # would invent an install nobody performed.
        unadopted.extend(item for item in legacy.value if item.coordinate not in receipted)

    return Ok(
        assemble_consumer_machine(
            tuple(inspections),
            credentials=tuple(observations),
            actions=actions.value,
            unadopted=tuple(unadopted),
            today=today,
        )
    )
