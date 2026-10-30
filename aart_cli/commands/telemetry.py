"""`aart-cli consume telemetry`: turned on or off, its state, and sending now (§213)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import datetime

from aart_cli import command_outcome as _common
from aart_cli.application.consumer_views import ConsumerSettings
from aart_cli.configuration.paths import APPLICATION_HOME_VARIABLE, Platform, resolve_config_paths
from aart_cli.configuration.policy import redact_text
from aart_cli.configuration.seed import baked_telemetry_endpoint
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.telemetry import BATCH_PATH, parse_telemetry_endpoint
from aart_cli.io.consumer_settings import read_consumer_settings, write_consumer_settings
from aart_cli.io.telemetry_consent import announce_turned_on, turn_on, turn_on_by_default
from aart_cli.io.telemetry_store import TelemetryOutbox
from aart_cli.io.telemetry_sync import new_installation_id, synchronise
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


def _unmanaged(settings: ConsumerSettings) -> tuple[dict[str, object], str]:
    """Whether uses aart-cli did not install are sent, and who decided, as data and as a line."""

    chosen = settings.telemetry_unmanaged is not None
    sent = settings.sends_unmanaged_uses
    who = "your choice" if chosen else "this aart-cli's default"
    return (
        {"sent": sent, "chosen": chosen},
        f"uses of tools aart-cli did not install: {'sent' if sent else 'not sent'} ({who})",
    )


def _settings(home: str) -> ConsumerSettings:
    """The person's settings, or the defaults when they cannot be read: a status still reports."""

    settings = read_consumer_settings(home)
    return settings.value if isinstance(settings, Ok) else ConsumerSettings()


def _status(request: Request, outbox: TelemetryOutbox, home: str) -> int:
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
        "endpoint": None if current is None else current.endpoint or None,
        "client_id": None if current is None else current.client_id or None,
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
    unmanaged, said = _unmanaged(_settings(home))
    document["unmanaged_uses"] = unmanaged
    offered = baked_telemetry_endpoint()
    lines = [f"telemetry: {'on' if enabled else 'off'}"]
    if current is not None and current.endpoint:
        lines.append(f"server: {current.endpoint}")
    if current is not None and current.client_id:
        lines.append(f"installation id: {current.client_id}")
    if (current is None or not current.endpoint) and offered is not None:
        lines.append(f"this aart-cli offers: {offered}")
    lines.append(said)
    lines.append(
        f"events: {waiting.waiting} waiting, {waiting.sent} sent, {waiting.rejected} rejected, "
        f"{waiting.skipped} skipped (not sent by choice, or nothing the contract can name)"
    )
    lines.append(f"last success: {document['last_success_at'] or 'never'}")
    if sync.next_retry_at is not None:
        lines.append(f"next attempt after: {document['next_retry_at']} ({sync.failures} failed)")
    if sync.paused == "unauthorised":
        lines.append("paused: the server refused authorisation; `sync --force` tries again")
    _print(request, document, lines)
    return _common.OK


def turn_on_for_this_build(request: Request) -> None:
    """Turn telemetry on where this build names a server and nobody decided, and say so on stderr
    (§213, D-505). Never fails the command it runs before."""

    try:
        platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
        paths = resolve_config_paths(
            platform,
            home=os.path.abspath(request.user_home or os.path.expanduser("~")),
            application_home=os.environ.get(APPLICATION_HOME_VARIABLE) or None,
        )
        turned_on = turn_on_by_default(paths.data_root, baked_telemetry_endpoint())
    except Exception:  # noqa: BLE001 -- telemetry never fails what triggered it
        return
    if turned_on is not None:
        announce_turned_on(
            turned_on,
            lambda line: print(line, file=sys.stderr),
            unmanaged=_settings(paths.data_root).sends_unmanaged_uses,
        )


def run(request: Request) -> int:
    action = request.telemetry_action
    if action not in {"status", "enable", "disable", "unmanaged", "sync"}:
        return _failure(request, "unsupported telemetry action")
    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _failure(request, runtime.diagnostics[0].message)
    home = runtime.value.paths.data_root
    outbox = TelemetryOutbox(f"{home}/state")
    if action == "status":
        return _status(request, outbox, home)
    if action == "unmanaged":
        return _choose_unmanaged(request, home)
    if action == "enable":
        raw = request.telemetry_endpoint or baked_telemetry_endpoint()
        if not raw:
            return _failure(
                request, "this aart-cli offers no telemetry server; give one with --endpoint"
            )
        endpoint = parse_telemetry_endpoint(raw)
        if isinstance(endpoint, Err):
            return _failure(request, endpoint.diagnostics[0].message)
        enabled = turn_on(home, endpoint.value, new_installation_id())
        if isinstance(enabled, Err):
            return _failure(request, enabled.diagnostics[0].message)
        setting, queued = enabled.value
        unmanaged = _settings(home).sends_unmanaged_uses
        _print(
            request,
            {"endpoint": setting.endpoint, "client_id": setting.client_id, "queued": queued},
            [
                f"telemetry: on, sending to {setting.endpoint}{BATCH_PATH}",
                f"Queued {queued} event(s) Activity already held. From now on each install, "
                "update and removal aart-cli completes, each recorded use of an artifact "
                "aart-cli installed"
                + (
                    ", and each use of a skill or MCP aart-cli did not install, by the name the "
                    "harness used (`consume telemetry unmanaged off` stops that),"
                    if unmanaged
                    else ","
                )
                + " is sent at most every ten minutes, when something new is recorded.",
                "Sent: the event, the artifact's kind, name and version, the moment, the "
                f"installation id {setting.client_id} and aart-cli's version. Never a "
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
            "telemetry: off; what waited, what was sent and the installation id are deleted."
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


def _choose_unmanaged(request: Request, home: str) -> int:
    """Keep the person's choice about uses aart-cli did not install in Settings (D-508)."""

    if request.telemetry_unmanaged not in {"on", "off"}:
        return _failure(request, "say on or off")
    settings = read_consumer_settings(home)
    if isinstance(settings, Err):
        return _failure(request, settings.diagnostics[0].message)
    kept = replace(settings.value, telemetry_unmanaged=request.telemetry_unmanaged == "on")
    written = write_consumer_settings(kept, data_root=home)
    if isinstance(written, Err):
        return _failure(request, written.diagnostics[0].message)
    unmanaged, said = _unmanaged(kept)
    _print(
        request,
        {"unmanaged_uses": unmanaged},
        [
            said,
            "Kept in Settings, which changes it too."
            + ("" if kept.sends_unmanaged_uses else " Such uses still waiting are never sent."),
        ],
    )
    return _common.OK
