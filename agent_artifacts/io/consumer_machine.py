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

import os
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
    current_state_from_placement,
    desired_state_from_placement,
    desired_state_from_receipt,
)
from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import Scope, delivery_destination, delivery_target
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.receipts import (
    InstallationReceipt,
    InstalledRecord,
    PlacedArtifactReceipt,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.install_state.model import InstallScope
from agent_artifacts.install_state.paths import install_state_paths
from agent_artifacts.install_state.schema import parse_install_state

from .credentials import CredentialProviderPort
from .harness import LocalHarnessRegistry
from .installation_observation import COMPONENT_STATE
from .receipt_store import LocalReceiptStore
from .runtime_projection import observe_installation, observe_placement

__all__ = ["INSTALL_STATE_UNREADABLE", "read_consumer_machine"]

#: An installation manifest exists and could not be read.  Distinct from a missing manifest:
#: one means nothing was installed in that scope, the other means this process cannot tell.
INSTALL_STATE_UNREADABLE = DiagnosticCode("install-state-unreadable")


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
        references.update(record.credential_references)
    return tuple(sorted(references))


def _unknown(reference: CredentialReference) -> CredentialObservation:
    return CredentialObservation(
        reference,
        ProviderState.UNKNOWN,
        CredentialState.UNKNOWN,
        "no configured provider was asked to inspect this reference",
    )


def _unadopted(
    scope: InstallScope,
    *,
    project_root: str,
    user_home: str,
    data_root: str,
    profiles: tuple[str, ...] = (),
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
            if not profiles or record.profile in profiles
        )
    )


def _targets_scope_and_profile(
    record: InstalledRecord,
    *,
    scope: Scope,
    profiles: tuple[str, ...],
    harness_root: str,
) -> bool:
    """Whether a durable receipt belongs to the public status view being requested."""

    receipt = record.receipt
    if isinstance(receipt, InstallationReceipt):
        return any(
            registration.target.scope is scope
            and (not profiles or registration.target.harness in profiles)
            for registration in receipt.registrations
        )

    kind = ArtifactKind(record.coordinate.artifact.kind)
    for delivery in receipt.deliveries:
        if profiles and delivery.harness not in profiles:
            continue
        try:
            target = delivery_target(delivery.harness, scope, kind)
        except KeyError:
            continue
        expected = os.path.join(
            harness_root,
            delivery_destination(target, record.coordinate.artifact.name),
        )
        if delivery.destination == expected:
            return True
    return False


def read_consumer_machine(
    *,
    state_root: str,
    harness_root: str,
    today: date,
    project_root: str,
    user_home: str,
    data_root: str,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    scope: Scope | None = None,
    profiles: tuple[str, ...] = (),
) -> Result[ConsumerMachine]:
    """Read, inspect and assemble the machine the canonical consumer shell opens on.

    Providers are injected because credential inspection is an effect boundary.  A reference with
    no matching provider is kept as unknown; a provider that was explicitly supplied and then
    failed is reported as an inspection failure rather than silently downgraded.

    The legacy roots are required rather than optional for the same reason.  A caller that omitted
    them would get a machine that quietly reports every Skill, guideline, hook and memory on the
    disk as absent, and there is no signature that should make that easy to ask for by accident.

    ``scope`` and ``profiles`` narrow a command-facing read to the harness targets the caller
    requested.  The persistent TUI omits them and retains its whole-machine view; a scoped public
    status must not report a user installation while answering for a project, or vice versa.
    """

    providers = {item.provider: item for item in credential_providers}
    if len(providers) != len(credential_providers):
        raise ValueError("consumer machine reading needs one adapter per credential provider")

    if scope is not None and not isinstance(scope, Scope):
        raise ValueError("consumer machine scope is invalid")
    if any(not isinstance(profile, str) or not profile for profile in profiles):
        raise ValueError("consumer machine profiles are invalid")

    store = LocalReceiptStore(state_root)
    installed = store.installations()
    if isinstance(installed, Err):
        return installed
    actions = store.actions()
    if isinstance(actions, Err):
        return actions

    records = installed.value
    if scope is not None:
        records = tuple(
            record
            for record in records
            if _targets_scope_and_profile(
                record,
                scope=scope,
                profiles=profiles,
                harness_root=harness_root,
            )
        )

    observations: list[CredentialObservation] = []
    for reference in _references(records):
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
    for record in records:
        receipt = record.receipt
        if isinstance(receipt, PlacedArtifactReceipt):
            # An artifact a harness reads. There is no launcher to look for and no interpreter to
            # find, so none is looked for: reporting a missing process for something that starts
            # none would make every healthy Skill ask for a repair forever.
            placed = desired_state_from_placement(record.coordinate, receipt)
            inspections.append(
                InstalledInspection(
                    record,
                    placed,
                    current_state_from_placement(placed, receipt, observe_placement(receipt)),
                )
            )
            continue
        desired = desired_state_from_receipt(
            record.coordinate,
            receipt,
            base_interpreter=receipt.base_interpreter,
        )
        credential_states = tuple(
            (reference.input.value, COMPONENT_STATE[by_reference[reference].state])
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
    receipted = {_unversioned(record.coordinate) for record in records}
    legacy_scopes: tuple[InstallScope, ...] = (
        (scope.value,) if scope is not None else ("project", "user")
    )
    for legacy_scope in legacy_scopes:
        legacy = _unadopted(
            legacy_scope,
            project_root=project_root,
            user_home=user_home,
            data_root=data_root,
            profiles=profiles,
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
