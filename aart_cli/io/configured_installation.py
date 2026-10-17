"""Configured approved Selection to verified object placements and screen-07 state.

This adapter stops before an offer when required inputs are unanswered.  Synchronizing an immutable
artifact object is allowed at this stage; changing the target machine is not.  Once every field has
a safe source, ``prepared_placements`` applies those sources to the exact placements whose declared
inputs produced the form.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from aart_cli.application.installation_inputs import (
    InstallationInputComposition,
    InstallationInputUse,
    OwnedInputSource,
    compose_installation_inputs,
)
from aart_cli.application.installation_offer import ArtifactPlacement
from aart_cli.application.marketplace_resolution import ResolutionPolicy
from aart_cli.application.promotion import load_configured_registry_versions
from aart_cli.configuration.policy import EffectiveConfiguration
from aart_cli.domain.credentials import CredentialReference
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.harness import Scope
from aart_cli.domain.inputs import SecretProviderReference
from aart_cli.domain.installation_owner import (
    InstallationOwner,
    credential_address,
    installed_names,
)
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.python_runtime import PythonInstaller
from aart_cli.domain.registry import RegistryArtifactVersion, RegistryContentMode
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

from .artifact_placement import placements_for
from .configured_selection import resolve_configured_selection
from .object_store import publish_object, read_object
from .source_store import read_current_source

__all__ = [
    "CONFIGURED_INSTALLATION_INVALID",
    "CONFIGURED_INSTALLATION_INPUTS_REQUIRED",
    "ConfiguredInstallationDraft",
    "configured_object_candidate",
    "object_candidate_from_registry_snapshot",
    "placement_owner",
    "prepare_configured_installation_draft",
]

CONFIGURED_INSTALLATION_INVALID = DiagnosticCode("configured-installation-invalid")
CONFIGURED_INSTALLATION_INPUTS_REQUIRED = DiagnosticCode("configured-installation-inputs-required")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def _selected(placements: tuple[ArtifactPlacement, ...]) -> tuple[ResolvedArtifact, ...]:
    """The artifacts a draft's placements cover, each named once and in the order they appear.

    A placement is one harness's, so an artifact selected for four harnesses appears four times.
    What the draft has to account for is still the Selection: every artifact resolved, none added,
    and in the order the Selection resolved them.
    """

    covered: list[ResolvedArtifact] = []
    for placement in placements:
        if placement.artifact not in covered:
            covered.append(placement.artifact)
    return tuple(covered)


@dataclass(frozen=True, slots=True)
class InstallationAssignment:
    """One ticked artifact and harness at the scope chosen for it: an installation to be (§172).

    `artifact` is the resolved coordinate as a Selection writes it, which is what screen 05's rows
    name. The owner follows once placement adds the Registry alias and the concrete root.
    """

    artifact: str
    harness: str
    scope: Scope

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact, str)
            or not self.artifact
            or not isinstance(self.harness, str)
            or not self.harness
            or not isinstance(self.scope, Scope)
            or any(character in self.artifact + self.harness for character in "\t\r\n")
        ):
            raise ValueError("an installation assignment is invalid")


@dataclass(frozen=True, slots=True)
class ConfiguredInstallationDraft:
    """Resolved and placed immutable content plus the current aggregate input form."""

    selection: ResolvedSelection
    #: One per installation this draft would create: an artifact selected for two harnesses is two
    #: placements, because §169.3 gives each of them its own payload, runtime, launcher and
    #: configuration. The artifacts they cover are still exactly the selection's, in its order.
    placements: tuple[ArtifactPlacement, ...]
    inputs: InstallationInputComposition
    #: Every installation this draft would create, one per placement and in the same order. This is
    #: the unit configuration and credentials belong to (§169.4-6).
    owners: tuple[InstallationOwner, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.selection, ResolvedSelection)
            or any(not isinstance(item, ArtifactPlacement) for item in self.placements)
            or any(not isinstance(item, InstallationOwner) for item in self.owners)
            or not isinstance(self.inputs, InstallationInputComposition)
            or _selected(self.placements) != self.selection.artifacts
        ):
            raise ValueError("a configured installation draft is inconsistent")

    @property
    def ready(self) -> bool:
        return self.inputs.ready

    def prepared_placements(self) -> Result[tuple[ArtifactPlacement, ...]]:
        """Apply each installation's own answers to the placement that is that installation.

        A placement is one harness's (§169.3), so there is exactly one set of answers to apply and
        nothing left to reconcile across targets. That is the point of the split: what used to be
        one launcher carrying one set of values for every harness it registered with -- and a
        refusal when two harnesses answered differently (D-354) -- is now one launcher per
        installation, each carrying its own.
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
            owner = placement.owner
            if owner is None:
                return _error(
                    CONFIGURED_INSTALLATION_INVALID,
                    f"{placement.coordinate} is placed without naming the installation it is",
                )
            sources = self.inputs.sources_for(owner)
            secrets = tuple(item for item in sources if isinstance(item, SecretProviderReference))
            prepared.append(
                replace(
                    placement,
                    sources=sources,
                    # The item this installation is entitled to, composed from its own owner rather
                    # than taken from what was answered: what a provider is asked for, and what the
                    # receipt records, is an address nobody typed.
                    credential_addresses=tuple(
                        CredentialReference(
                            item.input,
                            credential_address(owner, item.input, provider=item.provider.provider),
                        )
                        for item in secrets
                    ),
                )
            )
        return Ok(tuple(prepared))


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
    loaded = load_configured_registry_versions(current.value.candidate.snapshot, alias)
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
    if version.mode is not RegistryContentMode.SELF_CONTAINED:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"pinned-reference approved version {version.coordinate} cannot be materialized from this "
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
    assignments: tuple[InstallationAssignment, ...] = (),
    scope_roots: Mapping[Scope, str] | None = None,
) -> Result[ConfiguredInstallationDraft]:
    """Resolve, materialize and place one Selection without planning target-machine mutation.

    `harness_root` is the scope's own root. Only an artifact a harness reads off a path needs it,
    and `placement_for` refuses by name when one is selected and no root was supplied -- rather
    than resolving a harness path against whatever directory this process happens to be in.

    `assignments`, when given, replace `scope` and `profiles`: each artifact is placed into exactly
    its own pairs, every scope against its root in `scope_roots` (§172, INV-258, INV-260).
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
    owner_root = harness_root if harness_root is not None else project_root
    keys = {str(artifact.version.coordinate) for artifact in resolved.value.artifacts}
    stray = sorted({item.artifact for item in assignments} - keys)
    if stray:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"{stray[0]} was given a harness but is not part of this selection",
        )
    placements: list[ArtifactPlacement] = []
    for artifact in resolved.value.artifacts:
        materialized = _materialize(effective, artifact, data_root=data_root, store=store)
        if isinstance(materialized, Err):
            return materialized
        if not assignments:
            groups: tuple[tuple[Scope, tuple[str, ...], bool, str | None], ...] = (
                (scope, profiles, profiles_requested, owner_root),
            )
        else:
            # §172: each artifact goes where its own pairs say, each scope under its own root. A
            # pair names a harness somebody ticked, so a harness unable to host it is a refusal.
            key = str(artifact.version.coordinate)
            pairs = tuple(item for item in assignments if item.artifact == key)
            if not pairs:
                return _error(
                    CONFIGURED_INSTALLATION_INVALID,
                    f"{key} has no harness chosen to install into",
                )
            roots = scope_roots or {}
            groups = tuple(
                (
                    each,
                    tuple(dict.fromkeys(item.harness for item in pairs if item.scope is each)),
                    True,
                    roots.get(each),
                )
                for each in (Scope.PROJECT, Scope.USER)
                if any(item.scope is each for item in pairs)
            )
        for each, chosen, requested, root in groups:
            placed = placements_for(
                artifact,
                scope=each,
                profiles=chosen,
                profiles_requested=requested,
                project_root=project_root,
                data_root=data_root,
                store=store,
                harness_root=root,
                preferred_installer=preferred_installer,
            )
            if isinstance(placed, Err):
                return placed
            placements.extend(placed.value)
    owners: list[InstallationOwner] = []
    for placement in placements:
        owned = placement_owner(placement)
        if isinstance(owned, Err):
            return owned
        owners.append(owned.value)
    named = installed_names(tuple(owners))
    if isinstance(named, Err):
        return named
    installed_by_owner = dict(named.value)
    placements = [
        replace(placement, installed_name=installed_by_owner[owner])
        for placement, owner in zip(placements, owners, strict=True)
    ]
    uses = tuple(
        InstallationInputUse(owner, runtime_input)
        for placement, owner in zip(placements, owners, strict=True)
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


def placement_owner(placement: ArtifactPlacement) -> Result[InstallationOwner]:
    """The one installation this placement is, checked against the harness it actually reaches.

    A placement is one harness's (§169.3), and it says so twice: the owner it carries and the
    targets, deliveries, merges and settings that name a harness. Those two have to be the same
    harness. If they ever came apart, the configuration and the credential item would belong to one
    installation while the files went to another, and nothing downstream would notice.
    """

    if not isinstance(placement, ArtifactPlacement):
        return _error(CONFIGURED_INSTALLATION_INVALID, "an installation owner needs a placement")
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
    owner = placement.owner
    if owner is None:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"{placement.coordinate} is placed without naming the installation it is",
        )
    if harnesses != {owner.harness}:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"{placement.coordinate} is owned by {owner.harness} and reaches "
            + ", ".join(sorted(harnesses)),
        )
    return Ok(owner)
