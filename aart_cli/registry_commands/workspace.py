"""Registry command orchestration through an injected workspace port."""

from __future__ import annotations

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import ObjectDigest
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.registry_commands.model import (
    RegistryApplyCommand,
    RegistryApplyReceipt,
    RegistryInitOptions,
    RegistryWorkspacePlan,
)
from aart_cli.registry_commands.planning import (
    plan_registry_format,
    plan_registry_init,
    project_registry_workspace_plan,
)
from aart_cli.registry_commands.ports import RegistryWorkspacePort

REGISTRY_REVIEW_MISMATCH = DiagnosticCode("registry-review-mismatch")
REGISTRY_APPLY_MISMATCH = DiagnosticCode("registry-apply-mismatch")


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


def prepare_registry_init(
    options: RegistryInitOptions,
    *,
    output: RegistryWorkspacePort,
) -> Result[RegistryWorkspacePlan]:
    current = output.current()
    if isinstance(current, Err):
        return current
    return plan_registry_init(current.value, options)


def prepare_registry_format(*, output: RegistryWorkspacePort) -> Result[RegistryWorkspacePlan]:
    current = output.current()
    if isinstance(current, Err):
        return current
    return plan_registry_format(current.value)


def finalize_registry_workspace(
    plan: RegistryWorkspacePlan,
    reviewed_digest: ObjectDigest,
    *,
    output: RegistryWorkspacePort,
) -> Result[RegistryApplyReceipt]:
    """Apply only the exact reviewed plan; a no-op still rechecks its precondition."""

    if reviewed_digest != plan.review_digest:
        return _error(
            REGISTRY_REVIEW_MISMATCH,
            "reviewed registry command digest does not match the prepared plan",
        )
    if plan.changed_paths == 0:
        current = output.current()
        if isinstance(current, Err):
            return current
        verified = project_registry_workspace_plan(current.value, plan)
        if isinstance(verified, Err):
            return verified
        return Ok(
            RegistryApplyReceipt(
                plan.review_digest,
                plan.next_snapshot_digest,
                0,
            )
        )
    applied = output.apply(RegistryApplyCommand(plan))
    if isinstance(applied, Err):
        return applied
    if (
        applied.value.review_digest != plan.review_digest
        or applied.value.snapshot_digest != plan.next_snapshot_digest
        or applied.value.changed_paths != plan.changed_paths
    ):
        return _error(
            REGISTRY_APPLY_MISMATCH,
            "registry apply receipt does not match the reviewed plan",
        )
    return applied
