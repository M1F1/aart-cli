"""Compose immutable Maintainer Source views from one durable machine observation.

Configuration says which authoring Sources exist, the Source store says which pinned snapshot is
current and how healthy it is, and Candidate history says what that exact snapshot produced. The
three reads meet here, outside every renderer and reducer.
"""

from __future__ import annotations

import time

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.maintainer_sync import ApprovedRegistryState
from agent_artifacts.application.maintainer_views import (
    MaintainerViews,
    project_maintainer_bulk_promotion,
    project_maintainer_candidate_lifecycle,
    project_maintainer_candidates,
    project_maintainer_collection_candidate,
    project_maintainer_collection_validation,
    project_maintainer_dashboard,
    project_maintainer_promotion_review,
    project_maintainer_provenance,
    project_maintainer_registry,
    project_maintainer_registry_diff,
    project_maintainer_source,
    project_maintainer_validation,
    project_maintainer_version_conflict,
)
from agent_artifacts.application.promotion import (
    PromotionAudit,
    load_registry_promotions,
    load_registry_versions,
)
from agent_artifacts.application.sources import SourceStatusRequest, source_status
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.configuration.policy import EffectiveConfiguration, redact_text
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode, RegistryArtifactVersion
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.native_tree import SourceSnapshot
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)

from .candidate_store import candidate_history_paths, read_candidate_history
from .configured_selection import load_configured_approved_marketplace
from .maintainer_sync import read_approved_registry_state
from .registry_promotion import FilesystemPromotionOutput
from .source_store import read_current_source

__all__ = ["MAINTAINER_COMPOSITION_INVALID", "read_maintainer_views"]

MAINTAINER_COMPOSITION_INVALID = DiagnosticCode("maintainer-composition-invalid")


def _error(message: str) -> Err:
    return Err(
        (
            Diagnostic(
                MAINTAINER_COMPOSITION_INVALID,
                Severity.ERROR,
                redact_text(message),
            ),
        )
    )


def read_maintainer_views(
    effective: EffectiveConfiguration,
    *,
    data_root: str,
    observed_at_epoch_seconds: int | None = None,
    policy: EffectivePolicy | None = None,
    registry_root: str | None = None,
) -> Result[MaintainerViews]:
    """Read each configured authoring Source once and bind only matching Candidate history."""

    if not isinstance(effective, EffectiveConfiguration) or not isinstance(data_root, str):
        return _error("reading Maintainer views needs effective configuration and a data root")
    # The policy is a parameter rather than something a projection reaches for, so the validation
    # a Maintainer reads is reproducible from the run that composed it.
    judged = EffectivePolicy() if policy is None else policy
    if not isinstance(judged, EffectivePolicy):
        return _error("reading Maintainer views needs an effective policy")
    now = int(time.time()) if observed_at_epoch_seconds is None else observed_at_epoch_seconds
    if not isinstance(now, int) or isinstance(now, bool) or now < 0:
        return _error("reading Maintainer views needs a non-negative observation time")
    projected = []
    scans = []
    for configured in effective.configuration.sources:
        if configured.kind is SourceKind.REGISTRY_GIT:
            continue
        paths = source_store_paths(data_root, source_instance_id(configured))
        health = source_status(
            SourceStatusRequest(
                CurrentSourceRequest(paths, configured.alias),
                now,
                effective.configuration.sync.max_age_seconds,
            ),
            read_current_source,
        )
        history = read_candidate_history(candidate_history_paths(paths))
        if isinstance(history, Err):
            return history
        try:
            projected.append(project_maintainer_source(configured, health, history.value))
            if history.value is not None:
                scans.append(history.value)
        except ValueError as error:
            return _error(f"cannot bind Candidate history for {configured.alias}: {error}")
    sources = tuple(projected)
    try:
        candidates = project_maintainer_candidates(tuple(scans))
        collection_candidate_records = tuple(
            candidate for scan in scans for candidate in scan.collection_active
        )
        collection_candidates = tuple(
            project_maintainer_collection_candidate(candidate)
            for candidate in collection_candidate_records
        )
        loaded_marketplace = load_configured_approved_marketplace(
            effective,
            data_root=data_root,
        )
        approved_marketplace = (
            None if isinstance(loaded_marketplace, Err) else loaded_marketplace.value
        )
        collection_validations = tuple(
            project_maintainer_collection_validation(candidate, approved_marketplace)
            for candidate in collection_candidate_records
        )
        runs = tuple(
            (bundle, validate_candidate(bundle, policy=judged))
            for scan in scans
            for bundle in scan.active
        )
        validations = tuple(
            project_maintainer_validation(bundle, policy=judged) for bundle, _ in runs
        )
        # Each Candidate names the registry it was scanned for. A registry with no synchronized
        # snapshot is a refusal screen 41 can state, not an error that hides the rest of what was
        # composed, so the failed read becomes `None` rather than aborting the composition.
        approved: dict[str, ApprovedRegistryState | None] = {}
        for bundle, _ in runs:
            alias = bundle.candidate.target_registry
            if alias.value not in approved:
                observed = read_approved_registry_state(effective, alias, data_root=data_root)
                approved[alias.value] = None if isinstance(observed, Err) else observed.value
        # Both modes, composed once: screen 42 chooses between them by selecting an already
        # projected review rather than making one while drawing.
        # The plan needs the registry *workspace*, not only its approved projection: what a
        # transaction writes is decided against the tree it would write into.
        workspaces: dict[str, SourceSnapshot | None] = {}
        for alias_value in approved:
            registry = next(
                (
                    item
                    for item in effective.configuration.sources
                    if item.alias.value == alias_value and item.kind is SourceKind.REGISTRY_GIT
                ),
                None,
            )
            workspaces[alias_value] = None
            if registry is None:
                continue
            registry_paths = source_store_paths(data_root, source_instance_id(registry))
            workspace = read_current_source(CurrentSourceRequest(registry_paths, registry.alias))
            if isinstance(workspace, Ok) and workspace.value is not None:
                workspaces[alias_value] = workspace.value.candidate.snapshot
        # Screen 48 includes locally promoted state before publication. With exactly one configured
        # registry, D-103 identifies the project root as that registry's checkout; otherwise no
        # checkout can be attributed safely (B-042), so synchronized evidence remains the answer.
        configured_registries = tuple(
            item
            for item in effective.configuration.sources
            if item.enabled and item.kind is SourceKind.REGISTRY_GIT
        )
        checkout: SourceSnapshot | None = None
        if registry_root is not None and len(configured_registries) == 1:
            local = FilesystemPromotionOutput(registry_root).current()
            if isinstance(local, Ok):
                checkout = local.value
        lifecycle_snapshots = dict(workspaces)
        if checkout is not None:
            lifecycle_snapshots[configured_registries[0].alias.value] = checkout
        audits: dict[str, tuple[PromotionAudit, ...] | None] = {}
        versions_by_registry: dict[str, tuple[RegistryArtifactVersion, ...] | None] = {}
        for alias_value, registry_workspace in lifecycle_snapshots.items():
            if registry_workspace is None:
                audits[alias_value] = None
                versions_by_registry[alias_value] = None
                continue
            loaded_audits = load_registry_promotions(registry_workspace)
            audits[alias_value] = None if isinstance(loaded_audits, Err) else loaded_audits.value
            loaded_versions = load_registry_versions(registry_workspace)
            versions_by_registry[alias_value] = (
                None if isinstance(loaded_versions, Err) else loaded_versions.value
            )
        histories = {item.candidate.id: scan.history for scan in scans for item in scan.active}
        lifecycles = tuple(
            project_maintainer_candidate_lifecycle(
                bundle,
                validation,
                history=histories[bundle.candidate.id],
                versions=versions_by_registry[bundle.candidate.target_registry.value],
                audits=audits[bundle.candidate.target_registry.value],
            )
            for bundle, validation in runs
        )
        provenances = tuple(project_maintainer_provenance(bundle) for bundle, _ in runs)
        version_conflict_views = []
        for bundle, _ in runs:
            approved_state = approved[bundle.candidate.target_registry.value]
            conflict = project_maintainer_version_conflict(
                bundle,
                None if approved_state is None else approved_state.versions,
            )
            if conflict is not None:
                version_conflict_views.append(conflict)
        version_conflicts = tuple(version_conflict_views)
        registry_diffs = tuple(
            project_maintainer_registry_diff(
                bundle,
                validation,
                judged,
                approved[bundle.candidate.target_registry.value],
                workspaces[bundle.candidate.target_registry.value],
                mode=mode,
            )
            for bundle, validation in runs
            for mode in PromotionMode
        )
        promotions = tuple(
            project_maintainer_promotion_review(
                bundle,
                validation,
                judged,
                approved[bundle.candidate.target_registry.value],
                mode=mode,
            )
            for bundle, validation in runs
            for mode in PromotionMode
        )
        # Screen 46 is about the registries themselves, so it covers every configured one rather
        # than only those some active Candidate happens to target.
        registries = []
        bulk_promotions = []
        for registry in configured_registries:
            alias_value = registry.alias.value
            if alias_value not in approved:
                published = read_approved_registry_state(
                    effective, registry.alias, data_root=data_root
                )
                approved[alias_value] = None if isinstance(published, Err) else published.value
                registry_paths = source_store_paths(data_root, source_instance_id(registry))
                current = read_current_source(CurrentSourceRequest(registry_paths, registry.alias))
                workspaces[alias_value] = (
                    current.value.candidate.snapshot
                    if isinstance(current, Ok) and current.value is not None
                    else None
                )
            bulk_promotions.append(
                project_maintainer_bulk_promotion(registry.alias, runs, approved[alias_value])
            )
            registries.append(
                project_maintainer_registry(
                    registry.alias,
                    approved[alias_value],
                    workspaces[alias_value],
                    checkout,
                )
            )
        return Ok(
            MaintainerViews(
                project_maintainer_dashboard(sources),
                sources,
                candidates,
                validations,
                promotions,
                registry_diffs,
                tuple(registries),
                tuple(bulk_promotions),
                lifecycles,
                provenances,
                version_conflicts,
                collection_candidates,
                collection_validations,
            )
        )
    except ValueError as error:
        return _error(f"cannot project durable Candidates: {error}")
