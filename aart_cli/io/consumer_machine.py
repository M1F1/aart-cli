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
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from aart_cli.application.consumer_session import (
    ConsumerMachine,
    InstalledInspection,
    UnadoptedInstallation,
    assemble_consumer_machine,
)
from aart_cli.application.consumer_views import ConfigurationFileView
from aart_cli.application.installed_state import (
    current_state_from_observation,
    current_state_from_placement,
    desired_state_from_placement,
    desired_state_from_receipt,
)
from aart_cli.domain.artifacts import ArtifactKind
from aart_cli.domain.configuration_files import parse_configuration_file
from aart_cli.domain.credentials import (
    CredentialObservation,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.harness import (
    Scope,
    delivery_destination,
    delivery_target,
    memory_target,
)
from aart_cli.domain.identifiers import ArtifactCoordinate
from aart_cli.domain.receipts import (
    InstallationReceipt,
    InstalledRecord,
    PlacedArtifactReceipt,
)
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.install_state.model import InstallScope
from aart_cli.install_state.paths import install_state_paths
from aart_cli.install_state.schema import parse_install_state
from aart_cli.protocol.hashing import sha256_bytes

from .credentials import CredentialProviderPort
from .harness import LocalHarnessRegistry
from .installation_observation import COMPONENT_STATE
from .receipt_store import LocalReceiptStore
from .runtime_projection import observe_installation, observe_placement

__all__ = [
    "INSTALL_STATE_UNREADABLE",
    "InspectedInstallations",
    "read_consumer_machine",
    "read_configuration_files",
    "read_installed_inspections",
]

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
        # The name the harness reads it under, not the one the author gave it: an installation is
        # delivered under its own name (`§169.7`), and recomputing the authored one here would
        # leave every delivered artifact out of the view that lists what is installed.
        expected = os.path.join(
            harness_root,
            delivery_destination(
                target, delivery.projected_name or record.coordinate.artifact.name
            ),
        )
        if delivery.destination == expected:
            return True
    # An artifact merged into a shared file belongs to the same view for the same reason: what
    # decides is where this scope's harness reads it, not how it reads it.
    for merge in receipt.merges:
        if profiles and merge.harness not in profiles:
            continue
        try:
            memory = memory_target(merge.harness, scope)
        except KeyError:
            continue
        if merge.destination == os.path.join(harness_root, memory.destination):
            return True
    return False


@dataclass(frozen=True, slots=True)
class InspectedInstallations:
    """Every canonical installation this machine holds, as read and as measured.

    The pair travels together because it was produced together: the credential observations are
    what the component states were derived from, and separating them invites a second, disagreeing
    inspection of the same references.
    """

    inspections: tuple[InstalledInspection, ...]
    credentials: tuple[CredentialObservation, ...]
    configurations: tuple[ConfigurationFileView, ...] = ()


def read_configuration_files(
    records: tuple[InstalledRecord, ...],
) -> Result[tuple[ConfigurationFileView, ...]]:
    """Read artifact-owned config files without turning absence or damage into guessed values."""

    if any(not isinstance(item, InstalledRecord) for item in records):
        raise ValueError("configuration reading needs installed records")
    views: list[ConfigurationFileView] = []
    for installed in records:
        receipt = installed.receipt
        if not isinstance(receipt, InstallationReceipt):
            continue
        input_ids = tuple(item.input.value for item in receipt.config)
        for record in receipt.configuration_files:
            try:
                content = Path(record.path).read_bytes()
            except FileNotFoundError:
                views.append(
                    ConfigurationFileView(
                        str(installed.coordinate),
                        record.harness,
                        record.path,
                        "missing",
                        (),
                        "the configuration file is missing",
                        input_ids,
                    )
                )
                continue
            except OSError:
                views.append(
                    ConfigurationFileView(
                        str(installed.coordinate),
                        record.harness,
                        record.path,
                        "unreadable",
                        (),
                        "the configuration file could not be read",
                        input_ids,
                    )
                )
                continue
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                parsed = None
            else:
                candidate = parse_configuration_file(text)
                parsed = candidate.value if isinstance(candidate, Ok) else None
            if parsed is None:
                views.append(
                    ConfigurationFileView(
                        str(installed.coordinate),
                        record.harness,
                        record.path,
                        "unreadable",
                        (),
                        "the configuration file does not use the supported format",
                        input_ids,
                    )
                )
                continue
            state = "matched" if sha256_bytes(content) == record.digest else "changed-outside-aart"
            views.append(
                ConfigurationFileView(
                    str(installed.coordinate),
                    record.harness,
                    record.path,
                    state,
                    tuple((item[0].value, item[1]) for item in parsed),
                    (
                        ""
                        if state == "matched"
                        else "the file changed outside AART after its receipt was recorded"
                    ),
                    input_ids or tuple(item[0].value for item in parsed),
                )
            )
    return Ok(tuple(views))


def read_installed_inspections(
    *,
    state_root: str,
    harness_root: str,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    scope: Scope | None = None,
    profiles: tuple[str, ...] = (),
) -> Result[InspectedInstallations]:
    """Read every canonical receipt in scope and measure what is actually there.

    This is the half of :func:`read_consumer_machine` that answers "what is installed, and what
    state is it in". It is separate because a lifecycle action needs exactly that and nothing
    else: an update has to know the version it replaces and the state that version converged on,
    and assembling a dashboard, an activity feed and the legacy manifests to find out would make a
    command depend on projections it never draws.
    """

    providers = {item.provider: item for item in credential_providers}
    if len(providers) != len(credential_providers):
        raise ValueError("consumer machine reading needs one adapter per credential provider")

    if scope is not None and not isinstance(scope, Scope):
        raise ValueError("consumer machine scope is invalid")
    if any(not isinstance(profile, str) or not profile for profile in profiles):
        raise ValueError("consumer machine profiles are invalid")

    installed = LocalReceiptStore(state_root).installations()
    if isinstance(installed, Err):
        return installed

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

    configurations = read_configuration_files(records)
    if isinstance(configurations, Err):
        return configurations
    return Ok(
        InspectedInstallations(
            tuple(inspections),
            tuple(observations),
            configurations.value,
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

    read = read_installed_inspections(
        state_root=state_root,
        harness_root=harness_root,
        credential_providers=credential_providers,
        scope=scope,
        profiles=profiles,
    )
    if isinstance(read, Err):
        return read
    inspections = list(read.value.inspections)
    observations = list(read.value.credentials)
    actions = LocalReceiptStore(state_root).actions()
    if isinstance(actions, Err):
        return actions

    unadopted: list[UnadoptedInstallation] = []
    receipted = {_unversioned(item.record.coordinate) for item in inspections}
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
            configurations=read.value.configurations,
            today=today,
        )
    )
