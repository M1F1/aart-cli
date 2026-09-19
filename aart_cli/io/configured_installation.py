"""Configured approved Selection to verified object placements and screen-07 state.

This adapter stops before an offer when required inputs are unanswered.  Synchronizing an immutable
artifact object is allowed at this stage; changing the target machine is not.  Once every field has
a safe source, ``prepared_placements`` applies those sources to the exact placements whose declared
inputs produced the form.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from aart_cli.application.installation_inputs import (
    InstallationInputComposition,
    InstallationInputUse,
    OwnedInputSource,
    compose_installation_inputs,
)
from aart_cli.application.installation_offer import ArtifactPlacement
from aart_cli.application.marketplace_resolution import ResolutionPolicy
from aart_cli.application.promotion import load_published_registry_versions
from aart_cli.application.runtime_projection import HARNESS_PLACEHOLDER
from aart_cli.configuration.policy import EffectiveConfiguration
from aart_cli.domain.credentials import CredentialReference
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.harness import Scope
from aart_cli.domain.inputs import InputValueSource, SecretProviderReference
from aart_cli.domain.installation_owner import (
    InstallationOwner,
    credential_address,
    credential_service_template,
    installation_owner,
    installed_names,
)
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.python_runtime import PythonInstaller
from aart_cli.domain.registry import PromotionMode, RegistryArtifactVersion
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.selection import ArtifactSelection, ResolvedArtifact, ResolvedSelection
from aart_cli.protocol.native_tree import SnapshotEntry, SnapshotEntryKind, SourceSnapshot
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)
from aart_cli.store.model import (
    ObjectCandidate,
    ObjectPublishCommand,
    ObjectReadRequest,
    ObjectStorePaths,
    make_object_candidate,
    object_store_paths,
)

from .artifact_placement import placement_for
from .configured_selection import resolve_configured_selection
from .object_store import publish_object, read_object
from .source_store import read_current_source

__all__ = [
    "CONFIGURED_INSTALLATION_INVALID",
    "CONFIGURED_INSTALLATION_INPUTS_REQUIRED",
    "CONFIGURED_INSTALLATION_VALUES_DIFFER",
    "ConfiguredInstallationDraft",
    "placement_owners",
    "configured_object_candidate",
    "object_candidate_from_registry_snapshot",
    "prepare_configured_installation_draft",
]

CONFIGURED_INSTALLATION_INVALID = DiagnosticCode("configured-installation-invalid")
CONFIGURED_INSTALLATION_INPUTS_REQUIRED = DiagnosticCode("configured-installation-inputs-required")
#: One placement's targets answered the same input differently in something other than the
#: credential each addresses, and a single generated launcher carries one set of configuration
#: values. Refused rather than installed with whichever came first (D-354, narrowed by D-355).
CONFIGURED_INSTALLATION_VALUES_DIFFER = DiagnosticCode(
    "configured-installation-per-target-values-differ"
)


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _harness_slot_template(owners: tuple[InstallationOwner, ...]) -> str | None:
    """The credential service these installations share, with the harness they differ in left open.

    `None` where there is nothing to compose: one installation's launcher can read the address it
    was given, and owners that differ in anything but the harness have no single template between
    them. Every owner of one placement shares its alias, artifact, scope and root by construction,
    so in practice the second case is the profile, which nothing sets yet.
    """

    if len(owners) < 2:
        return None
    templates = {credential_service_template(owner, HARNESS_PLACEHOLDER) for owner in owners}
    return templates.pop() if len(templates) == 1 else None


def _with_open_harness_slot(
    source: InputValueSource,
    owner: InstallationOwner,
    template: str | None,
) -> InputValueSource:
    """An installation's own credential address, written as the template it composes from.

    Only the address this owner is entitled to is folded: a reference pointing anywhere else is
    left as it is, so two targets naming different arbitrary items still read as the disagreement
    they are rather than being quietly unified.
    """

    if (
        template is None
        or not isinstance(source, SecretProviderReference)
        or source.provider
        != credential_address(owner, source.input, provider=source.provider.provider)
    ):
        return source
    return replace(source, provider=replace(source.provider, service=template))


@dataclass(frozen=True, slots=True)
class ConfiguredInstallationDraft:
    """Resolved and placed immutable content plus the current aggregate input form."""

    selection: ResolvedSelection
    placements: tuple[ArtifactPlacement, ...]
    inputs: InstallationInputComposition
    #: Every installation this draft would create: one per placement per harness it reaches. This
    #: is the unit configuration and credentials belong to (§169.4-6), and it is deliberately not
    #: derivable from a placement alone, which spans its targets.
    owners: tuple[InstallationOwner, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.selection, ResolvedSelection)
            or any(not isinstance(item, ArtifactPlacement) for item in self.placements)
            or any(not isinstance(item, InstallationOwner) for item in self.owners)
            or not isinstance(self.inputs, InstallationInputComposition)
            or tuple(item.artifact for item in self.placements) != self.selection.artifacts
        ):
            raise ValueError("a configured installation draft is inconsistent")

    @property
    def ready(self) -> bool:
        return self.inputs.ready

    def prepared_placements(self) -> Result[tuple[ArtifactPlacement, ...]]:
        """Apply each installation's own answers to the placement whose declarations asked for them.

        A placement spans every harness it registers with, and each of those is its own
        installation with its own answers (D-353). The one thing those answers are *meant* to
        differ in is the credential each addresses: separate items are §169.4-6's contract, not a
        conflict. So each installation's own address is folded back to the template it composes
        from (D-355), and what remains has to agree -- one generated launcher still carries one set
        of configuration values, and a disagreement about those is refused by name rather than
        settled by whichever came first (D-354).
        """

        if not self.ready:
            names = ", ".join(
                f"{item.owner} {item.input.id.value}" for item in self.inputs.unanswered
            )
            return _error(
                CONFIGURED_INSTALLATION_INPUTS_REQUIRED,
                f"required installation inputs are unanswered: {names}",
            )
        prepared: list[ArtifactPlacement] = []
        for placement in self.placements:
            owners = self.owners_for(placement)
            template = _harness_slot_template(owners)
            answered = {
                owner: tuple(
                    _with_open_harness_slot(source, owner, template)
                    for source in self.inputs.sources_for(owner)
                )
                for owner in owners
            }
            distinct = {tuple(values) for values in answered.values()}
            if len(distinct) > 1:
                return _error(
                    CONFIGURED_INSTALLATION_VALUES_DIFFER,
                    f"{placement.coordinate} is registered with "
                    + ", ".join(sorted(owner.harness for owner in answered))
                    + ", which answered its inputs differently in something other than the "
                    "credential each addresses; one generated launcher carries one set of values, "
                    "so there is nothing here to compose per harness",
                )
            sources = next(iter(distinct), ())
            composed = tuple(
                item
                for item in sources
                if isinstance(item, SecretProviderReference) and item.provider.service == template
            )
            prepared.append(
                replace(
                    placement,
                    sources=sources,
                    credential_service_template=template if composed else None,
                    # What the launcher composes is text; what a provider is asked for is an item.
                    # So every installation's own address is carried beside the template, because
                    # the template itself names nothing anyone holds.
                    credential_addresses=tuple(
                        CredentialReference(
                            item.input,
                            credential_address(owner, item.input, provider=item.provider.provider),
                        )
                        for owner in owners
                        for item in composed
                    ),
                )
            )
        return Ok(tuple(prepared))

    def owners_for(self, placement: ArtifactPlacement) -> tuple[InstallationOwner, ...]:
        """The installations this one placement would create, in canonical order."""

        return tuple(item for item in self.owners if item.artifact == placement.coordinate.artifact)


def _configured_snapshot(
    effective: EffectiveConfiguration,
    version: RegistryArtifactVersion,
    *,
    data_root: str,
) -> Result[SourceSnapshot]:
    alias = version.coordinate.source
    configured = next(
        (
            item
            for item in effective.configuration.sources
            if item.enabled and item.alias == alias and item.is_registry
        ),
        None,
    )
    if configured is None:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"resolved artifact {version.coordinate} has no enabled configured registry",
        )
    paths = source_store_paths(data_root, source_instance_id(configured))
    current = read_current_source(CurrentSourceRequest(paths, alias))
    if isinstance(current, Err):
        return current
    if current.value is None:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"configured registry {alias} has no synchronized current snapshot",
        )
    loaded = load_published_registry_versions(current.value.candidate.snapshot)
    if isinstance(loaded, Err):
        return loaded
    exact = next(
        (item for item in loaded.value if item.coordinate == version.coordinate),
        None,
    )
    if exact != version:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"configured registry {alias} no longer contains the resolved approved version "
            f"{version.coordinate}",
        )
    return Ok(current.value.candidate.snapshot)


def _object_entries(
    snapshot: SourceSnapshot,
    version: RegistryArtifactVersion,
) -> Result[tuple[SnapshotEntry, ...]]:
    if version.mode is not PromotionMode.VENDORED:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"referenced approved version {version.coordinate} cannot be materialized from this "
            "registry snapshot",
        )
    identity = version.coordinate.artifact
    prefix = f"artifacts/{identity.kind}/{identity.name}/{version.coordinate.version}/"
    entries: list[SnapshotEntry] = []
    for entry in snapshot.entries:
        raw = str(entry.path)
        if not raw.startswith(prefix) or entry.kind is SnapshotEntryKind.DIRECTORY:
            continue
        if entry.kind is not SnapshotEntryKind.FILE:
            return _error(
                CONFIGURED_INSTALLATION_INVALID,
                f"approved object {version.coordinate} contains forbidden {entry.kind.value}",
            )
        relative = parse_relative_path(raw.removeprefix(prefix))
        if isinstance(relative, Err):
            return relative
        entries.append(
            SnapshotEntry(relative.value, SnapshotEntryKind.FILE, entry.content, entry.executable)
        )
    if not entries:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"approved object {version.coordinate} is absent from its configured snapshot",
        )
    return Ok(tuple(entries))


def configured_object_candidate(
    effective: EffectiveConfiguration,
    version: RegistryArtifactVersion,
    *,
    data_root: str,
) -> Result[ObjectCandidate]:
    """Read and verify one approved object's cached bytes without publishing them.

    Offline readiness and installation must answer the same question about the registry snapshot.
    Keeping extraction and digest verification here prevents Doctor from growing a second package
    reader merely to avoid the write that materialization performs.
    """

    snapshot = _configured_snapshot(effective, version, data_root=data_root)
    if isinstance(snapshot, Err):
        return snapshot
    return object_candidate_from_registry_snapshot(snapshot.value, version)


def object_candidate_from_registry_snapshot(
    snapshot: SourceSnapshot,
    version: RegistryArtifactVersion,
) -> Result[ObjectCandidate]:
    """Verify one approved object's exact bytes from an already observed registry snapshot."""

    entries = _object_entries(snapshot, version)
    if isinstance(entries, Err):
        return entries
    return make_object_candidate(entries.value, expected_digest=version.object_digest)


def _materialize(
    effective: EffectiveConfiguration,
    artifact: ResolvedArtifact,
    *,
    data_root: str,
    store: ObjectStorePaths,
) -> Result[None]:
    existing = read_object(ObjectReadRequest(store, artifact.version.object_digest))
    if isinstance(existing, Ok) and existing.value is not None:
        return Ok(None)
    if isinstance(existing, Err) and any(
        item.code.value not in {"digest-mismatch", "store-invalid"} for item in existing.diagnostics
    ):
        return existing
    candidate = configured_object_candidate(
        effective,
        artifact.version,
        data_root=data_root,
    )
    if isinstance(candidate, Err):
        return candidate
    published = publish_object(ObjectPublishCommand(store, candidate.value))
    return published if isinstance(published, Err) else Ok(None)


def prepare_configured_installation_draft(
    effective: EffectiveConfiguration,
    selection: ArtifactSelection,
    *,
    data_root: str,
    project_root: str,
    scope: Scope,
    profiles: tuple[str, ...],
    profiles_requested: bool = True,
    sources: tuple[OwnedInputSource, ...],
    policy: EffectivePolicy,
    harness_root: str | None = None,
    resolution_policy: ResolutionPolicy | None = None,
    preferred_installer: PythonInstaller | None = None,
) -> Result[ConfiguredInstallationDraft]:
    """Resolve, materialize and place one Selection without planning target-machine mutation.

    `harness_root` is the scope's own root. Only an artifact a harness reads off a path needs it,
    and `placement_for` refuses by name when one is selected and no root was supplied -- rather
    than resolving a harness path against whatever directory this process happens to be in.
    """

    resolved = resolve_configured_selection(
        effective,
        selection,
        data_root=data_root,
        policy=resolution_policy,
    )
    if isinstance(resolved, Err):
        return resolved
    store = object_store_paths(data_root)
    placements: list[ArtifactPlacement] = []
    for artifact in resolved.value.artifacts:
        materialized = _materialize(effective, artifact, data_root=data_root, store=store)
        if isinstance(materialized, Err):
            return materialized
        placed = placement_for(
            artifact,
            scope=scope,
            profiles=profiles,
            profiles_requested=profiles_requested,
            project_root=project_root,
            data_root=data_root,
            store=store,
            harness_root=harness_root,
            preferred_installer=preferred_installer,
        )
        if isinstance(placed, Err):
            return placed
        placements.append(placed.value)
    owner_root = harness_root if harness_root is not None else project_root
    owners: list[InstallationOwner] = []
    for placement in placements:
        owned = placement_owners(placement, scope=scope, root=owner_root)
        if isinstance(owned, Err):
            return owned
        owners.extend(owned.value)
    named = installed_names(owners)
    if isinstance(named, Err):
        return named
    installed_by_owner = dict(named.value)
    named_placements: list[ArtifactPlacement] = []
    for placement in placements:
        names = {
            installed_by_owner[owner]
            for owner in owners
            if owner.artifact == placement.coordinate.artifact
        }
        if len(names) != 1:
            return _error(
                CONFIGURED_INSTALLATION_INVALID,
                f"{placement.coordinate} does not have one installed name across its targets",
            )
        named_placements.append(replace(placement, installed_name=next(iter(names))))
    placements = named_placements
    uses = tuple(
        InstallationInputUse(owner, runtime_input)
        for placement in placements
        for owner in owners
        if owner.artifact == placement.coordinate.artifact
        for runtime_input in placement.description.inputs
    )
    inputs = compose_installation_inputs(uses, sources, policy)
    if isinstance(inputs, Err):
        return inputs
    try:
        return Ok(
            ConfiguredInstallationDraft(
                resolved.value, tuple(placements), inputs.value, tuple(owners)
            )
        )
    except ValueError as error:
        return _error(CONFIGURED_INSTALLATION_INVALID, f"installation draft is invalid: {error}")


def placement_owners(
    placement: ArtifactPlacement,
    *,
    scope: Scope,
    root: str,
) -> Result[tuple[InstallationOwner, ...]]:
    """The installations one placement would create: one per harness it actually reaches.

    A harness reaches an artifact in one of two ways, and a placement records exactly one of them.
    An artifact that starts a process is registered with a target; one that is read off a path is
    delivered, merged or given a settings entry. Both name the harness, and that harness with this
    scope and this root is the installation (§169.4).
    """

    harnesses = {item.harness for item in placement.targets}
    harnesses.update(item.harness for item in placement.deliveries)
    harnesses.update(item.harness for item in placement.merges)
    harnesses.update(item.harness for item in placement.settings)
    if not harnesses:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"{placement.coordinate} is placed but reaches no harness, so there is nothing to own "
            "its configuration",
        )
    try:
        return Ok(
            tuple(
                sorted(
                    installation_owner(
                        placement.coordinate, scope=scope, root=root, harness=harness
                    )
                    for harness in harnesses
                )
            )
        )
    except ValueError as error:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"{placement.coordinate} cannot name its installations: {error}",
        )
