"""`aart-cli consume opencode [1|2]`: which OpenCode project plugins are installed for (D-532)."""

from __future__ import annotations

import json
from dataclasses import replace

from aart_cli import command_outcome as _common
from aart_cli.application.consumer_views import ConsumerSettings
from aart_cli.configuration.policy import redact_text
from aart_cli.domain.result import Err
from aart_cli.io.consumer_settings import read_consumer_settings, write_consumer_settings
from aart_cli.model import Request

from ._configured_runtime import load_runtime_configuration

_OPERATION = "opencode"


def _failure(request: Request, message: str) -> int:
    safe = redact_text(message)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": _OPERATION,
                    "diagnostics": [{"code": "opencode-invalid", "message": safe}],
                },
                indent=2,
            )
        )
    else:
        print(f"error: {safe}")
    return _common.ERROR


def _said(settings: ConsumerSettings, *, chosen_now: bool) -> list[str]:
    runtime = settings.opencode
    where = (
        "a directory of its own under .opencode/plugins/"
        if runtime == 2
        else "the plugin list in the project's opencode.json"
    )
    lines = [f"Project plugins are installed for OpenCode {runtime}: {where}."]
    if chosen_now:
        lines.append(
            "Kept in Settings, which changes it too. Plugins already installed stay as they were: "
            "uninstall and install them again to move them."
        )
    elif settings.opencode_runtime is None:
        lines.append("This aart-cli's build decides until you choose: consume opencode 1|2.")
    else:
        lines.append("You chose it; consume opencode 1|2 or Settings changes it.")
    return lines


def run(request: Request) -> int:
    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _failure(request, runtime.diagnostics[0].message)
    home = runtime.value.paths.data_root
    settings = read_consumer_settings(home)
    if isinstance(settings, Err):
        return _failure(request, settings.diagnostics[0].message)
    kept = settings.value
    if request.opencode_runtime is not None:
        if request.opencode_runtime not in {"1", "2"}:
            return _failure(request, "say 1 or 2")
        kept = replace(kept, opencode_runtime=int(request.opencode_runtime))
        written = write_consumer_settings(kept, data_root=home)
        if isinstance(written, Err):
            return _failure(request, written.diagnostics[0].message)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": _OPERATION,
                    "opencode": kept.opencode,
                    "decided_by": "build" if kept.opencode_runtime is None else "you",
                },
                indent=2,
            )
        )
    else:
        for line in _said(kept, chosen_now=request.opencode_runtime is not None):
            print(line)
    return _common.OK
