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
)
from agent_artifacts.application.reconciliation import repair_plan_to_data
from agent_artifacts.domain.diagnostics import diagnostic_to_data
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err
from agent_artifacts.io.configured_repair_action import prepare_configured_repair
from agent_artifacts.io.consumer_machine import read_installed_inspections
from agent_artifacts.io.credentials import MacOsKeychainProvider
from agent_artifacts.model import Request
from agent_artifacts.receipt_service import resolved_paths
from agent_artifacts.tui_consumer import render_doctor

from ._configured_runtime import load_runtime_configuration

_OPERATION = "doctor"


def _emit_error(request: Request, result: Err) -> int:
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": _OPERATION,
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
    inspected = read_installed_inspections(
        state_root=os.path.join(runtime.value.paths.data_root, "state"),
        harness_root=project_root,
        credential_providers=providers,
    )
    if isinstance(inspected, Err):
        return _emit_error(request, inspected)

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
    }
    if request.json:
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(render_doctor(view, PresentationProfile.FAST)))
    return _common.OK if payload["ok"] else _common.ERROR
