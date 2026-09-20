"""Pure configuration precedence, organization-policy checks, and redaction."""

from __future__ import annotations

from dataclasses import dataclass, replace

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok, Result

from ..redaction import redact_text
from .model import (
    OrganizationPolicy,
    SourceKind,
    SyncMode,
    SyncSettings,
    UserConfiguration,
    git_location_parts,
)

SOURCE_POLICY_DENIED = DiagnosticCode("source-policy-denied")
CONFIG_INVALID = DiagnosticCode("config-invalid")


@dataclass(frozen=True, slots=True)
class RuntimeOverrides:
    default_registry: SourceAlias | None = None
    sync_mode: SyncMode | None = None
    max_age_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class EffectiveConfiguration:
    configuration: UserConfiguration
    policy: OrganizationPolicy
    locked_fields: tuple[str, ...]


def _denied(message: str) -> Diagnostic:
    return Diagnostic(SOURCE_POLICY_DENIED, Severity.ERROR, redact_text(message))


def _invalid(message: str) -> Err:
    return Err((Diagnostic(CONFIG_INVALID, Severity.ERROR, redact_text(message)),))


def _policy_diagnostics(
    configuration: UserConfiguration,
    policy: OrganizationPolicy,
    *,
    allow_missing_required_sources: bool = False,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    enabled = {source.alias: source for source in configuration.sources if source.enabled}
    if not allow_missing_required_sources:
        for required in policy.required_sources:
            if required not in enabled:
                diagnostics.append(
                    _denied(f"required source {required} is not configured and enabled")
                )
    for source in enabled.values():
        if policy.allow_direct_sources is False and source.kind is not SourceKind.REGISTRY_GIT:
            diagnostics.append(
                _denied(f"direct source {source.alias} is denied by organization policy")
            )
        if not source.is_git:
            continue
        location = git_location_parts(source.location)
        if location is None:
            diagnostics.append(_denied(f"source {source.alias} has an invalid Git location"))
            continue
        host, repository = location
        if policy.allowed_git_hosts is not None and host not in policy.allowed_git_hosts:
            diagnostics.append(_denied(f"Git host for source {source.alias} is not allowed"))
        if policy.allowed_repository_prefixes is not None and not any(
            repository.startswith(prefix) for prefix in policy.allowed_repository_prefixes
        ):
            diagnostics.append(_denied(f"repository path for source {source.alias} is not allowed"))
    return tuple(diagnostics)


def _apply_configuration(
    user: UserConfiguration,
    overrides: RuntimeOverrides,
    policy: OrganizationPolicy,
    *,
    allow_missing_required_sources: bool,
) -> Result[EffectiveConfiguration]:
    """Apply precedence and policy, with a narrowly scoped source-onboarding exception."""

    try:
        sync = SyncSettings(
            user.sync.mode if overrides.sync_mode is None else overrides.sync_mode,
            (
                user.sync.max_age_seconds
                if overrides.max_age_seconds is None
                else overrides.max_age_seconds
            ),
        )
        effective = replace(
            user,
            default_registry=(
                user.default_registry
                if overrides.default_registry is None
                else overrides.default_registry
            ),
            sync=sync,
        )
    except ValueError as error:
        return _invalid(str(error))
    sources = {source.alias: source for source in effective.sources if source.enabled}
    if effective.default_registry is not None:
        default = sources.get(effective.default_registry)
        if default is None or not default.is_registry:
            return _invalid("effective default registry must name an enabled registry")
    diagnostics = _policy_diagnostics(
        effective,
        policy,
        allow_missing_required_sources=allow_missing_required_sources,
    )
    if diagnostics:
        return Err(diagnostics)
    return Ok(EffectiveConfiguration(effective, policy, ()))


def apply_configuration(
    user: UserConfiguration,
    overrides: RuntimeOverrides,
    policy: OrganizationPolicy,
) -> Result[EffectiveConfiguration]:
    """Apply built-in/user/runtime/policy precedence for a content-capable operation."""

    return _apply_configuration(
        user,
        overrides,
        policy,
        allow_missing_required_sources=False,
    )


def apply_configuration_for_source_management(
    user: UserConfiguration,
    policy: OrganizationPolicy,
    overrides: RuntimeOverrides | None = None,
) -> Result[EffectiveConfiguration]:
    """Validate a source-management state without authorizing marketplace content.

    Organizations may require several source aliases.  A user must be able to synchronize and
    persist each allowed alias one at a time, but the ordinary content configuration path remains
    fail-closed until all required aliases are enabled.  This helper bypasses *only* that missing
    alias check; all origin, direct-source, reporting, and default-registry constraints remain in
    force.
    """

    return _apply_configuration(
        user,
        RuntimeOverrides() if overrides is None else overrides,
        policy,
        allow_missing_required_sources=True,
    )
