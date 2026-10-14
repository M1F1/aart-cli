"""CLI-only smoke verification for already installed MCP artifacts."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from aart_cli import command_outcome as _common
from aart_cli.application.mcp_smoke import SmokeStageResult, select_installed_mcps
from aart_cli.configuration.policy import redact_text
from aart_cli.domain.harness import Scope
from aart_cli.domain.result import Err
from aart_cli.io.installed_smoke import SmokeTargetResult, smoke_installation
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.model import Request
from aart_cli.receipt_service import resolved_paths

from ._configured_runtime import load_runtime_configuration

_OPERATION = "mcp.test"
_HARNESSES = frozenset({"opencode", "tabnine", "claude"})


def _stage_data(stage: SmokeStageResult) -> dict[str, str]:
    return {"stage": stage.stage.value, "outcome": stage.outcome.value, "reason": stage.reason}


def _target_data(target: SmokeTargetResult) -> dict[str, object]:
    data: dict[str, object] = {
        "installation": target.installation,
        "coordinate": target.coordinate,
        "owner": target.owner,
        "content_digest": target.content_digest,
        "harness": target.harness,
        "ok": target.ok,
        "stages": [_stage_data(stage) for stage in target.stages],
    }
    if target.response is not None:
        data["response"] = target.response
    return data


def _failure(request: Request, message: str) -> int:
    safe = redact_text(message)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": _OPERATION,
                    "diagnostics": [{"code": "mcp-smoke-invalid", "message": safe}],
                },
                indent=2,
            )
        )
    else:
        print(f"error: {safe}")
    return _common.ERROR


def run(request: Request) -> int:
    if request.mcp_action != "test":
        return _failure(request, "unsupported MCP command action")
    harnesses = frozenset(request.profiles)
    unknown = sorted(harnesses - _HARNESSES)
    if unknown:
        return _failure(request, f"unsupported MCP smoke harness {unknown[0]!r}")
    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _failure(request, runtime.diagnostics[0].message)
    project_root, user_home = resolved_paths(
        data_root=runtime.value.paths.data_root,
        project=request.project,
        user_home=request.user_home,
    )
    root = project_root if request.scope == "project" else user_home
    records = LocalReceiptStore(
        os.path.join(runtime.value.paths.data_root, "state")
    ).installations()
    if isinstance(records, Err):
        return _failure(request, records.diagnostics[0].message)
    selection = select_installed_mcps(
        records.value,
        scope=Scope(request.scope),
        root=root,
        harnesses=harnesses,
        selectors=request.names,
        all_installed=request.all_installed,
    )
    if selection.failure is not None:
        return _failure(request, selection.failure)
    data_root = runtime.value.paths.data_root
    results = tuple(
        smoke_installation(record, data_root, show_response=request.show_response)
        for record in selection.targets
    )
    ok = bool(results) and all(result.ok for result in results)
    targets = [_target_data(result) for result in results]
    payload = {
        "schema_version": 1,
        "ok": ok,
        "operation": _OPERATION,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scope": request.scope,
        "targets": targets,
    }
    if request.json:
        print(json.dumps(payload, indent=2))
    else:
        for result in results:
            print(result.installation)
            for stage in result.stages:
                print(f"  {stage.outcome.value:<14} {stage.stage.value}: {stage.reason}")
            if result.response is not None:
                suffix = " (truncated)" if result.response.get("truncated") else ""
                print(f"  response{suffix}: {result.response.get('content', '')}")
    return _common.OK if ok else _common.ERROR


__all__ = ["run"]
