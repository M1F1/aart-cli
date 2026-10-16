"""Registry command orchestration through an injected workspace port."""

from __future__ import annotations

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import ArtifactIdentity, ObjectDigest
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.capabilities import Capability
from aart_cli.protocol.paths import SafeRelativePath
from aart_cli.protocol.registry_models import ReviewRecord
from aart_cli.protocol.semver import SemVer
from aart_cli.registry_commands.model import (
    CollectionAuthorOptions,
    RegistryApplyCommand,
    RegistryApplyReceipt,
    RegistryInitOptions,
    RegistryWorkspacePlan,
    VendoredArtifactCheck,
    VendoredArtifactPlan,
)
from aart_cli.registry_commands.planning import (
    VendoredArtifactOrigin,
    plan_artifact_revendor,
    plan_artifact_vendor,
    plan_registry_collection,
    plan_registry_format,
    plan_registry_init,
    project_registry_workspace_plan,
    read_vendored_artifact,
)
from aart_cli.registry_commands.ports import RegistryWorkspacePort
from aart_cli.registry_maintenance.model import NativeReferenceAcquisition
from aart_cli.registry_maintenance.vendoring import VendorOptions

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


def prepare_registry_collection(
    options: CollectionAuthorOptions,
    *,
    executable_version: SemVer,
    available_capabilities: tuple[Capability, ...],
    output: RegistryWorkspacePort,
) -> Result[RegistryWorkspacePlan]:
    current = output.current()
    if isinstance(current, Err):
        return current
    return plan_registry_collection(
        current.value,
        options,
        executable_version=executable_version,
        available_capabilities=available_capabilities,
    )


def prepare_artifact_vendor(
    acquisition: NativeReferenceAcquisition,
    options: VendorOptions,
    *,
    path: SafeRelativePath,
    review: ReviewRecord,
    importer_version: SemVer,
    output: RegistryWorkspacePort,
) -> Result[VendoredArtifactPlan]:
    current = output.current()
    if isinstance(current, Err):
        return current
    return plan_artifact_vendor(
        current.value,
        acquisition,
        options,
        path=path,
        review=review,
        importer_version=importer_version,
    )


def read_vendored_artifact_origin(
    identity: ArtifactIdentity,
    *,
    output: RegistryWorkspacePort,
) -> Result[VendoredArtifactOrigin]:
    current = output.current()
    if isinstance(current, Err):
        return current
    return read_vendored_artifact(current.value, identity)


def prepare_artifact_revendor(
    acquisition: NativeReferenceAcquisition,
    vendored: VendoredArtifactOrigin,
    *,
    version: SemVer | None,
    review: ReviewRecord,
    importer_version: SemVer,
    output: RegistryWorkspacePort,
) -> Result[VendoredArtifactCheck]:
    current = output.current()
    if isinstance(current, Err):
        return current
    return plan_artifact_revendor(
        current.value,
        acquisition,
        vendored,
        version=version,
        review=review,
        importer_version=importer_version,
    )


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
