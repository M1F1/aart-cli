"""Concrete configured composition for reviewed Maintainer Source Sync."""

from __future__ import annotations

import time

from agent_artifacts.application.maintainer_sync import (
    ApprovedRegistryState,
    MaintainerSourceSyncPorts,
    PreparedSourceSync,
    SourceSyncExecutionResult,
    execute_source_sync,
    prepare_source_sync,
)
from agent_artifacts.application.promotion import load_registry_versions
from agent_artifacts.application.sources import SourceSyncRequest
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.configuration.policy import EffectiveConfiguration, redact_text
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.authoring import compile_author_source
from agent_artifacts.runtime_contract import EXECUTABLE_CAPABILITIES, EXECUTABLE_VERSION
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    SnapshotLimits,
    SyncFallback,
    source_instance_id,
    source_store_paths,
)
from agent_artifacts.sources.runtime import (
    DEFAULT_SOURCE_SYNC_TIMEOUT_SECONDS,
    source_sync_ports,
)

from .candidate_store import (
    candidate_history_paths,
    read_candidate_history,
    write_candidate_history,
)
from .source_store import read_current_source

MAINTAINER_SYNC_CONFIGURATION_INVALID = DiagnosticCode(
    "maintainer-source-sync-configuration-invalid"
)


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (
            Diagnostic(
                MAINTAINER_SYNC_CONFIGURATION_INVALID,
                Severity.ERROR,
                redact_text(message),
                remediation=tuple(redact_text(item) for item in remediation),
            ),
        )
    )


def _configured(
    effective: EffectiveConfiguration,
    alias: SourceAlias,
    *,
    kind: SourceKind | None = None,
) -> ConfiguredSource | None:
    return next(
        (
            item
            for item in effective.configuration.sources
            if item.enabled and item.alias == alias and (kind is None or item.kind is kind)
        ),
        None,
    )


def read_approved_registry_state(
    effective: EffectiveConfiguration,
    alias: SourceAlias,
    *,
    data_root: str,
) -> Result[ApprovedRegistryState]:
    """Read one enabled configured registry's exact approved projection without mutation."""

    if not isinstance(effective, EffectiveConfiguration) or not isinstance(alias, SourceAlias):
        return _error("reading approved registry state needs effective configuration and an alias")
    registry = _configured(effective, alias, kind=SourceKind.REGISTRY_GIT)
    if registry is None:
        return _error(f"target registry {alias} is not configured and enabled")
    paths = source_store_paths(data_root, source_instance_id(registry))
    current = read_current_source(CurrentSourceRequest(paths, alias))
    if isinstance(current, Err):
        return current
    if current.value is None:
        return _error(
            f"target registry {alias} has no synchronized approved snapshot",
            f"synchronize registry {alias} before reviewing Source Sync",
        )
    versions = load_registry_versions(current.value.candidate.snapshot)
    if isinstance(versions, Err):
        return versions
    try:
        return Ok(
            ApprovedRegistryState(
                alias,
                current.value.candidate.resolved_revision,
                current.value.candidate.snapshot_digest,
                versions.value,
            )
        )
    except ValueError as error:
        return _error(str(error))


def prepare_configured_source_sync(
    effective: EffectiveConfiguration,
    source_alias: SourceAlias,
    *,
    data_root: str,
    observed_at_epoch_seconds: int | None = None,
    offline: bool = False,
    timeout_seconds: int = DEFAULT_SOURCE_SYNC_TIMEOUT_SECONDS,
    limits: SnapshotLimits | None = None,
) -> Result[PreparedSourceSync]:
    """Read and bind the focused Source, its history and the configured default registry."""

    if not isinstance(effective, EffectiveConfiguration) or not isinstance(
        source_alias, SourceAlias
    ):
        return _error("preparing configured Source Sync needs effective configuration and an alias")
    source = _configured(effective, source_alias)
    if source is None or source.kind is SourceKind.REGISTRY_GIT:
        return _error(f"authoring Source {source_alias} is not configured and enabled")
    target = effective.configuration.default_registry
    if target is None:
        return _error(
            "Source Sync needs an explicit default target registry",
            "configure an enabled default registry, then review Source Sync again",
        )
    approved = read_approved_registry_state(effective, target, data_root=data_root)
    if isinstance(approved, Err):
        return approved
    paths = source_store_paths(data_root, source_instance_id(source))
    current = read_current_source(CurrentSourceRequest(paths, source.alias))
    if isinstance(current, Err):
        return current
    history = read_candidate_history(candidate_history_paths(paths))
    if isinstance(history, Err):
        return history
    observed = int(time.time()) if observed_at_epoch_seconds is None else observed_at_epoch_seconds
    try:
        request = SourceSyncRequest(
            source,
            data_root,
            EXECUTABLE_VERSION,
            EXECUTABLE_CAPABILITIES,
            observed,
            SyncFallback.REQUIRE_FRESH,
            offline,
            timeout_seconds,
            SnapshotLimits() if limits is None else limits,
        )
    except ValueError as error:
        return _error(str(error))
    return prepare_source_sync(request, current.value, history.value, approved.value)


def complete_configured_source_sync(
    effective: EffectiveConfiguration,
    prepared: PreparedSourceSync,
    *,
    reviewed_digest: ObjectDigest,
) -> Result[SourceSyncExecutionResult]:
    """Execute the reviewed Source Sync through real source and Candidate stores."""

    if not isinstance(effective, EffectiveConfiguration):
        return _error("completing configured Source Sync needs effective configuration")

    def read_history(paths):
        return read_candidate_history(candidate_history_paths(paths))

    def write_history(paths, scan):
        written = write_candidate_history(candidate_history_paths(paths), scan)
        return written if isinstance(written, Err) else Ok(None)

    def read_approved(alias):
        return read_approved_registry_state(
            effective,
            alias,
            data_root=prepared.request.data_root,
        )

    def compile_snapshot(snapshot, source_alias, source, revision):
        return compile_author_source(
            snapshot,
            source_alias=source_alias,
            source=source,
            revision=revision,
        )

    return execute_source_sync(
        prepared,
        reviewed_digest,
        MaintainerSourceSyncPorts(
            source_sync_ports(prepared.request.source),
            read_history,
            write_history,
            read_approved,
            compile_snapshot,
        ),
    )


__all__ = [
    "MAINTAINER_SYNC_CONFIGURATION_INVALID",
    "complete_configured_source_sync",
    "prepare_configured_source_sync",
    "read_approved_registry_state",
]
