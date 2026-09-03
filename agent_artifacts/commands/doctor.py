"""Environment-wide inspection through the canonical reconciliation engine.

Doctor is a read.  It observes each recorded installation once, projects the same health the
consumer application shows, and asks the existing repair planner for the smallest plan that would
reconcile each observation.  It neither resolves Marketplace content nor replays installation.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from agent_artifacts import command_outcome as _common
from agent_artifacts.application.consumer_views import (
    InstalledArtifactView,
    PresentationProfile,
    project_doctor,
    project_installed_artifact,
    project_lifecycle_plan,
    receipt_detail_to_data,
)
from agent_artifacts.application.offline_readiness import (
    OfflineReadiness,
    offline_readiness_to_data,
)
from agent_artifacts.application.orphaned_runs import (
    orphaned_run_lines,
    orphaned_runs_to_data,
)
from agent_artifacts.application.reconciliation import repair_plan_to_data
from agent_artifacts.consumer.application import CONSUMER_REVIEW_MISMATCH
from agent_artifacts.consumer.coordinates import CONSUMER_INVALID, parse_artifact_selector
from agent_artifacts.domain.diagnostics import Diagnostic, Severity, diagnostic_to_data
from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err
from agent_artifacts.io.configured_installation_action import InstallationHost
from agent_artifacts.io.configured_repair_action import (
    complete_configured_repair,
    prepare_configured_repair,
)
from agent_artifacts.io.consumer_machine import read_installed_inspections
from agent_artifacts.io.credentials import MacOsKeychainProvider
from agent_artifacts.io.offline_readiness import read_offline_readiness
from agent_artifacts.io.orphaned_runs import read_orphaned_runs
from agent_artifacts.model import Request
from agent_artifacts.receipt_service import resolved_paths
from agent_artifacts.tui_consumer import (
    render_doctor,
    render_lifecycle_plan,
    render_receipt_detail,
)

from ._configured_runtime import load_runtime_configuration

_OPERATION = "doctor"
_REPAIR_OPERATION = "doctor.repair"


def _emit_error(
    request: Request,
    result: Err,
    operation: str = _OPERATION,
    **fields: object,
) -> int:
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": operation,
                    **fields,
                    "diagnostics": [diagnostic_to_data(item) for item in result.diagnostics],
                },
                indent=2,
            )
        )
    else:
        for diagnostic in result.diagnostics:
            print(f"{diagnostic.severity.value}: {diagnostic.message}")
            for remediation in diagnostic.remediation:
                print(f"  remediation: {remediation}")
    return _common.ERROR


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (
            Diagnostic(
                CONSUMER_INVALID,
                Severity.ERROR,
                message,
                remediation=remediation,
            ),
        )
    )


def _emit(request: Request, payload: dict[str, object], lines: tuple[str, ...]) -> None:
    if request.json:
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(lines))


def _item_data(item: InstalledArtifactView) -> dict[str, object]:
    return {
        "coordinate": item.coordinate,
        "health": item.health,
        "drift": [
            {
                "component": drift.component,
                "kind": drift.kind,
                "repairable": drift.repairable,
            }
            for drift in item.drift
        ],
    }


def _offline_lines(readiness: OfflineReadiness) -> tuple[str, ...]:
    lines = ["Offline readiness"]
    for source in readiness.sources:
        lines.append(f"{source.alias}: metadata {source.metadata.value}")
        for artifact in source.artifacts:
            lines.extend(
                (
                    str(artifact.coordinate),
                    f"  metadata {artifact.metadata.value}",
                    f"  canonical payload {artifact.canonical_payload.value}",
                    f"  runtime dependencies {artifact.runtime_dependencies.value}",
                )
            )
    return tuple(lines)


def _run_repair(
    request: Request,
    *,
    data_root: str,
    project_root: str,
    user_home: str,
    credential_providers: tuple[MacOsKeychainProvider, ...],
) -> int:
    """Review or execute one exact repair through the configured lifecycle adapter."""

    scope = Scope(request.scope)
    inspected = read_installed_inspections(
        state_root=os.path.join(data_root, "state"),
        harness_root=project_root if scope is Scope.PROJECT else user_home,
        credential_providers=credential_providers,
        scope=scope,
    )
    if isinstance(inspected, Err):
        return _emit_error(request, inspected, _REPAIR_OPERATION, finalized=False)

    raw = request.names[0]
    selector = parse_artifact_selector(raw)
    if isinstance(selector, Err):
        return _emit_error(request, selector, _REPAIR_OPERATION, finalized=False)
    if selector.value.source is None or selector.value.version is None:
        return _emit_error(
            request,
            _error(
                "Doctor repair needs an exact source-qualified installed version",
                "pass --repair <source>/<kind>/<name>@<version>",
            ),
            _REPAIR_OPERATION,
            finalized=False,
        )
    coordinate = str(selector.value)
    matches = tuple(
        item for item in inspected.value.inspections if str(item.record.coordinate) == coordinate
    )
    if len(matches) != 1:
        return _emit_error(
            request,
            _error(
                f"no {scope.value}-scope installation matches {coordinate}",
                "run aart doctor, then pass one exact installed coordinate to --repair",
            ),
            _REPAIR_OPERATION,
            finalized=False,
        )

    policy = EffectivePolicy()
    prepared = prepare_configured_repair(matches[0], policy=policy)
    if isinstance(prepared, Err):
        return _emit_error(request, prepared, _REPAIR_OPERATION, finalized=False)
    digest = str(prepared.value.review_digest)
    review = repair_plan_to_data(prepared.value.plan.repair)
    review_lines = render_lifecycle_plan(
        project_lifecycle_plan(prepared.value.plan), PresentationProfile.FAST
    )
    base = {
        "schema_version": 1,
        "operation": _REPAIR_OPERATION,
        "coordinate": coordinate,
        "scope": scope.value,
        "review_digest": digest,
        "review": review,
    }
    if not request.yes:
        _emit(
            request,
            {**base, "ok": True, "finalized": False},
            (*review_lines, "Reviewed only; re-run with --yes and --expect to apply this plan."),
        )
        return _common.OK

    if request.expect is None or request.expect != digest:
        expected = request.expect
        message = (
            "repair confirmation requires --expect with the digest from a prior review"
            if expected is None
            else f"the plan changed since it was reviewed: expected {expected}, recomputed {digest}"
        )
        refusal = Err(
            (
                Diagnostic(
                    CONSUMER_REVIEW_MISMATCH,
                    Severity.ERROR,
                    message,
                    remediation=(
                        "re-read the repair review, then re-run --yes --expect with its review_digest",
                    ),
                ),
            )
        )
        return _emit_error(
            request,
            refusal,
            _REPAIR_OPERATION,
            finalized=False,
            expected_review_digest=expected,
            review_digest=digest,
            review=review,
        )

    host = InstallationHost(data_root, project_root, user_home, scope)
    now = datetime.now(timezone.utc)
    completed = complete_configured_repair(
        prepared.value,
        expected_review_digest=prepared.value.review_digest,
        host=host,
        policy=policy,
        recorded_at=now.isoformat(),
        today=now.date(),
        credential_providers=credential_providers,
        offline=request.offline,
    )
    if isinstance(completed, Err):
        return _emit_error(
            request,
            completed,
            _REPAIR_OPERATION,
            finalized=False,
            review_digest=digest,
        )
    receipt = completed.value.recorded.receipt
    successful = receipt.outcome.value in {"succeeded", "attention"}
    _emit(
        request,
        {
            **base,
            "ok": successful,
            "finalized": True,
            "session_status": receipt.outcome.value,
            "receipt": receipt_detail_to_data(receipt),
        },
        render_receipt_detail(receipt, PresentationProfile.FAST),
    )
    return _common.OK if successful else _common.ERROR


def run(request: Request) -> int:
    """Inspect every canonical installation and report minimal reconciliation plans."""

    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _emit_error(request, runtime)
    project_root, user_home = resolved_paths(
        data_root=runtime.value.paths.data_root,
        project=request.project,
        user_home=request.user_home,
    )
    providers = (MacOsKeychainProvider(),) if sys.platform == "darwin" else ()
    if request.names:
        return _run_repair(
            request,
            data_root=runtime.value.paths.data_root,
            project_root=project_root,
            user_home=user_home,
            credential_providers=providers,
        )
    inspected = read_installed_inspections(
        state_root=os.path.join(runtime.value.paths.data_root, "state"),
        harness_root=project_root,
        credential_providers=providers,
    )
    if isinstance(inspected, Err):
        return _emit_error(request, inspected)
    offline = read_offline_readiness(
        runtime.value.loaded.effective,
        data_root=runtime.value.paths.data_root,
    )
    if isinstance(offline, Err):
        return _emit_error(request, offline)
    # The run root is the data root, not the project root: deriving it a second time is `LAF-66`.
    orphaned = read_orphaned_runs(run_root=runtime.value.paths.data_root)

    artifacts = tuple(
        project_installed_artifact(
            item.desired,
            item.current,
            ownership=item.record.ownership,
            update_available=item.update_available,
        )
        for item in inspected.value.inspections
    )
    view = project_doctor(artifacts)
    policy = EffectivePolicy()
    repairs = []
    for item in inspected.value.inspections:
        prepared = prepare_configured_repair(item, policy=policy)
        if isinstance(prepared, Err):
            return _emit_error(request, prepared)
        if prepared.value.plan.repair.drift:
            repairs.append(repair_plan_to_data(prepared.value.plan.repair))

    payload = {
        "schema_version": 1,
        "ok": not view.attention_count,
        "operation": _OPERATION,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "ready": view.ready_count,
            "needs_attention": view.attention_count,
        },
        "items": [_item_data(item) for item in artifacts],
        "repairs": repairs,
        "offline_readiness": offline_readiness_to_data(offline.value),
        "orphaned_runs": orphaned_runs_to_data(orphaned),
    }
    if request.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            "\n".join(
                (
                    *render_doctor(view, PresentationProfile.FAST),
                    "",
                    *_offline_lines(offline.value),
                    "",
                    *orphaned_run_lines(orphaned),
                )
            )
        )
    return _common.OK if payload["ok"] else _common.ERROR
