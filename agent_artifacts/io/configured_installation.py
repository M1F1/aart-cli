"""Configured approved Selection to verified object placements and screen-07 state.

This adapter stops before an offer when required inputs are unanswered.  Synchronizing an immutable
artifact object is allowed at this stage; changing the target machine is not.  Once every field has
a safe source, ``prepared_placements`` applies those sources to the exact placements whose declared
inputs produced the form.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from agent_artifacts.application.installation_inputs import (
    InstallationInputComposition,
    InstallationInputUse,
    compose_installation_inputs,
)
from agent_artifacts.application.installation_offer import ArtifactPlacement
from agent_artifacts.application.marketplace_resolution import ResolutionPolicy
from agent_artifacts.application.promotion import load_registry_versions
from agent_artifacts.configuration.policy import EffectiveConfiguration
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.inputs import InputValueSource
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import PythonInstaller
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ArtifactSelection, ResolvedArtifact, ResolvedSelection
from agent_artifacts.protocol.native_tree import SnapshotEntry, SnapshotEntryKind, SourceSnapshot
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)
from agent_artifacts.store.model import (
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
    "ConfiguredInstallationDraft",
    "prepare_configured_installation_draft",
]

CONFIGURED_INSTALLATION_INVALID = DiagnosticCode("configured-installation-invalid")
CONFIGURED_INSTALLATION_INPUTS_REQUIRED = DiagnosticCode("configured-installation-inputs-required")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class ConfiguredInstallationDraft:
    """Resolved and placed immutable content plus the current aggregate input form."""

    selection: ResolvedSelection
    placements: tuple[ArtifactPlacement, ...]
    inputs: InstallationInputComposition

    def __post_init__(self) -> None:
        if (
            not isinstance(self.selection, ResolvedSelection)
            or any(not isinstance(item, ArtifactPlacement) for item in self.placements)
            or not isinstance(self.inputs, InstallationInputComposition)
            or tuple(item.artifact for item in self.placements) != self.selection.artifacts
        ):
            raise ValueError("a configured installation draft is inconsistent")

    @property
    def ready(self) -> bool:
        return self.inputs.ready

    def prepared_placements(self) -> Result[tuple[ArtifactPlacement, ...]]:
        if not self.ready:
            names = ", ".join(item.input.id.value for item in self.inputs.unanswered)
            return _error(
                CONFIGURED_INSTALLATION_INPUTS_REQUIRED,
                f"required installation inputs are unanswered: {names}",
            )
        return Ok(
            tuple(
                replace(
                    placement,
                    sources=self.inputs.sources_for(placement.coordinate),
                )
                for placement in self.placements
            )
        )


def _configured_snapshot(
    effective: EffectiveConfiguration,
    artifact: ResolvedArtifact,
    *,
    data_root: str,
) -> Result[SourceSnapshot]:
    alias = artifact.version.coordinate.source
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
            f"resolved artifact {artifact.version.coordinate} has no enabled configured registry",
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
    loaded = load_registry_versions(current.value.candidate.snapshot)
    if isinstance(loaded, Err):
        return loaded
    exact = next(
        (item for item in loaded.value if item.coordinate == artifact.version.coordinate),
        None,
    )
    if exact != artifact.version:
        return _error(
            CONFIGURED_INSTALLATION_INVALID,
            f"configured registry {alias} no longer contains the resolved approved version "
            f"{artifact.version.coordinate}",
        )
    return Ok(current.value.candidate.snapshot)


def _object_entries(
    snapshot: SourceSnapshot,
    artifact: ResolvedArtifact,
) -> Result[tuple[SnapshotEntry, ...]]:
    version = artifact.version
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
    snapshot = _configured_snapshot(effective, artifact, data_root=data_root)
    if isinstance(snapshot, Err):
        return snapshot
    entries = _object_entries(snapshot.value, artifact)
    if isinstance(entries, Err):
        return entries
    candidate = make_object_candidate(
        entries.value,
        expected_digest=artifact.version.object_digest,
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
    sources: tuple[InputValueSource, ...],
    policy: EffectivePolicy,
    resolution_policy: ResolutionPolicy | None = None,
    preferred_installer: PythonInstaller | None = None,
) -> Result[ConfiguredInstallationDraft]:
    """Resolve, materialize and place one Selection without planning target-machine mutation."""

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
            project_root=project_root,
            data_root=data_root,
            store=store,
            preferred_installer=preferred_installer,
        )
        if isinstance(placed, Err):
            return placed
        placements.append(placed.value)
    uses = tuple(
        InstallationInputUse(placement.coordinate, runtime_input)
        for placement in placements
        for runtime_input in placement.description.inputs
    )
    inputs = compose_installation_inputs(uses, sources, policy)
    if isinstance(inputs, Err):
        return inputs
    try:
        return Ok(ConfiguredInstallationDraft(resolved.value, tuple(placements), inputs.value))
    except ValueError as error:
        return _error(CONFIGURED_INSTALLATION_INVALID, f"installation draft is invalid: {error}")
