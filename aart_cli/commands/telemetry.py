"""`aart-cli consume telemetry`: turned on or off, its state, and sending now (§213)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from aart_cli import command_outcome as _common
from aart_cli.configuration.policy import redact_text
from aart_cli.configuration.seed import baked_telemetry_endpoint
from aart_cli.domain.result import Err
from aart_cli.domain.telemetry import BATCH_PATH, parse_telemetry_endpoint
from aart_cli.io.telemetry_store import TelemetryOutbox
from aart_cli.io.telemetry_sync import synchronise
from aart_cli.model import Request

from ._configured_runtime import load_runtime_configuration

_OPERATION = "telemetry"


def _print(request: Request, document: dict[str, object], lines: list[str]) -> None:
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": f"{_OPERATION}.{request.telemetry_action}",
                    **document,
                },
                indent=2,
            )
        )
    else:
        for line in lines:
            print(line)


def _failure(request: Request, message: str) -> int:
    safe = redact_text(message)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": f"{_OPERATION}.{request.telemetry_action}",
                    "diagnostics": [{"code": "telemetry-invalid", "message": safe}],
                },
                indent=2,
            )
        )
    else:
        print(f"error: {safe}")
    return _common.ERROR


def _moment(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _status(request: Request, outbox: TelemetryOutbox) -> int:
    setting = outbox.setting()
    counts = outbox.counts()
    state = outbox.sync_state()
    for result in (setting, counts, state):
        if isinstance(result, Err):
            return _failure(request, result.diagnostics[0].message)
    assert not isinstance(setting, Err) and not isinstance(counts, Err)
    assert not isinstance(state, Err)
    current, waiting = setting.value, counts.value
    enabled = current is not None and current.enabled
    sync = state.value
    document: dict[str, object] = {
        "enabled": enabled,
        "endpoint": None if current is None else current.endpoint,
        "client_id": None if current is None else current.client_id,
        "outbox": outbox.path,
        "events": {
            "waiting": waiting.waiting,
            "sent": waiting.sent,
            "rejected": waiting.rejected,
            "skipped": waiting.skipped,
        },
        "last_success_at": _moment(sync.last_success_at),
        "last_attempt_at": _moment(sync.last_attempt_at),
        "next_retry_at": _moment(sync.next_retry_at),
        "failures": sync.failures,
        "paused": sync.paused,
    }
    offered = baked_telemetry_endpoint()
    lines = [f"telemetry: {'on' if enabled else 'off'}"]
    if current is not None:
        lines.append(f"server: {current.endpoint}")
        lines.append(f"installation id: {current.client_id}")
    elif offered is not None:
        lines.append(f"this aart-cli offers: {offered}")
    lines.append(
        f"events: {waiting.waiting} waiting, {waiting.sent} sent, {waiting.rejected} rejected, "
        f"{waiting.skipped} skipped (not an installed artifact)"
    )
    lines.append(f"last success: {document['last_success_at'] or 'never'}")
    if sync.next_retry_at is not None:
        lines.append(f"next attempt after: {document['next_retry_at']} ({sync.failures} failed)")
    if sync.paused == "unauthorised":
        lines.append("paused: the server refused authorisation; `sync --force` tries again")
    _print(request, document, lines)
    return _common.OK


def run(request: Request) -> int:
    action = request.telemetry_action
    if action not in {"status", "enable", "disable", "sync"}:
        return _failure(request, "unsupported telemetry action")
    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _failure(request, runtime.diagnostics[0].message)
    home = runtime.value.paths.data_root
    outbox = TelemetryOutbox(f"{home}/state")
    if action == "status":
        return _status(request, outbox)
    if action == "enable":
        raw = request.telemetry_endpoint or baked_telemetry_endpoint()
        if not raw:
            return _failure(
                request, "this aart-cli offers no telemetry server; give one with --endpoint"
            )
        endpoint = parse_telemetry_endpoint(raw)
        if isinstance(endpoint, Err):
            return _failure(request, endpoint.diagnostics[0].message)
        enabled = outbox.enable(endpoint.value, str(uuid.uuid4()))
        if isinstance(enabled, Err):
            return _failure(request, enabled.diagnostics[0].message)
        _print(
            request,
            {"endpoint": enabled.value.endpoint, "client_id": enabled.value.client_id},
            [
                f"telemetry: on, sending to {enabled.value.endpoint}{BATCH_PATH}",
                "From now on each install, update and removal aart-cli completes, and each "
                "recorded use of an artifact aart-cli installed, is sent at most every ten "
                "minutes, when something new is recorded.",
                "Sent: the event, the artifact's kind, name and version, the moment, the "
                f"installation id {enabled.value.client_id} and aart-cli's version. Never a "
                "project, path, argument, prompt, user or host name, or credential.",
                f"Waiting events are kept in {outbox.path}.",
            ],
        )
        return _common.OK
    if action == "disable":
        disabled = outbox.disable(forget=request.telemetry_forget)
        if isinstance(disabled, Err):
            return _failure(request, disabled.diagnostics[0].message)
        said = (
            "telemetry: off; what waited and the installation id are deleted."
            if request.telemetry_forget
            else "telemetry: off; nothing more is recorded or sent. What waits is kept, unsent."
        )
        _print(request, {"forgotten": request.telemetry_forget}, [said])
        return _common.OK
    report = synchronise(home, manual=True, force=request.telemetry_force)
    document: dict[str, object] = {
        "started": report.started,
        "sent": report.sent,
        "rejected": report.rejected,
        "skipped": report.skipped,
        "requests": report.requests,
        "reason": report.reason or None,
    }
    if not report.started:
        lines = [f"nothing sent: {report.reason}"]
    else:
        lines = [
            f"sent {report.sent}, rejected {report.rejected}, skipped {report.skipped} "
            f"in {report.requests} request(s)"
            + (f"; stopped: the server is {report.reason}" if report.reason else "")
        ]
    _print(request, document, lines)
    return _common.OK if not report.reason or report.reason == "not due" else _common.ERROR
