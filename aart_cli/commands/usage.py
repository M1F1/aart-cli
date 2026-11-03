"""`aart-cli consume usage`: the most used artifacts, and recording turned on or off (§212)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace

from aart_cli import command_outcome as _common
from aart_cli.application.usage_recording import usage_disclosure, usage_ranking_lines
from aart_cli.configuration.paths import APPLICATION_HOME_VARIABLE, Platform, resolve_config_paths
from aart_cli.configuration.policy import redact_text
from aart_cli.domain.artifact_usage import USAGE_HARNESSES
from aart_cli.domain.result import Err, Ok
from aart_cli.io.activity_store import ActivityDatabase
from aart_cli.io.consumer_settings import read_consumer_settings, write_consumer_settings
from aart_cli.io.usage_hooks import (
    harness_file,
    read_artifact_usage,
    reconcile_usage_hooks,
    set_usage_hook,
    telemetry_endpoint,
)
from aart_cli.model import Request

from ._configured_runtime import load_runtime_configuration

_OPERATION = "usage"


def _failure(request: Request, message: str) -> int:
    safe = redact_text(message)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": f"{_OPERATION}.{request.usage_action}",
                    "diagnostics": [{"code": "usage-invalid", "message": safe}],
                },
                indent=2,
            )
        )
    else:
        print(f"error: {safe}")
    return _common.ERROR


def _show(request: Request, *, data_root: str, user_home: str) -> int:
    settings = read_consumer_settings(data_root)
    if isinstance(settings, Err):
        return _failure(request, settings.diagnostics[0].message)
    usage = read_artifact_usage(data_root=data_root, user_home=user_home)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": f"{_OPERATION}.show",
                    "database": usage.database,
                    "harnesses": [
                        {
                            "harness": harness,
                            "recording": harness in settings.value.recorded_usage,
                            "hooked": harness in usage.hooked,
                            "file": usage.file(harness),
                        }
                        for harness in USAGE_HARNESSES
                    ],
                    "ranking": [
                        {
                            "artifact": item.artifact,
                            "installed": item.installed,
                            "kind": item.kind.value,
                            "harness": item.harness,
                            "uses": item.uses,
                            "last_used": item.last_used,
                        }
                        for item in usage.ranking
                    ],
                },
                indent=2,
            )
        )
        return _common.OK
    for harness in USAGE_HARNESSES:
        if harness not in settings.value.recorded_usage:
            state = "off"
        elif harness in usage.hooked:
            state = "on"
        else:
            state = "on, not hooked yet: this harness has no configuration here"
        print(f"{harness}: {state}")
    print()
    lines = usage_ranking_lines(usage.ranking, limit=len(usage.ranking))
    if lines:
        print("Most used:")
        for line in lines:
            print(line)
    else:
        print("No artifact use is recorded yet.")
    return _common.OK


def record_usage_for_this_build(request: Request) -> None:
    """Put the usage hook in place where recording is on, after a `consume` command (§212, D-516).

    The TUI does this at its start; a `consume` command does it too, so a person who only uses the
    command line records what the build or they chose to (B-249). A wheel runs nothing when it is
    installed, so a command's run is the first moment aart-cli can. A harness turned off loses its
    hook, one not on this machine is left alone. It is said on stderr, so a `--json` document is
    unchanged, and nothing here fails the command.
    """

    try:
        platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
        user_home = os.path.abspath(request.user_home or os.path.expanduser("~"))
        data_root = resolve_config_paths(
            platform,
            home=user_home,
            application_home=os.environ.get(APPLICATION_HOME_VARIABLE) or None,
        ).data_root
        settings = read_consumer_settings(data_root)
        if isinstance(settings, Err):
            return
        started = reconcile_usage_hooks(
            settings.value.recorded_usage, user_home=user_home, data_root=data_root
        )
    except Exception:  # noqa: BLE001 -- recording usage is never what fails a command
        return
    for harness in started:
        print(
            f"Recording which skills and MCPs {harness} uses; "
            f"`aart-cli consume usage disable --harness {harness}` turns it off.",
            file=sys.stderr,
        )


def run(request: Request) -> int:
    action = request.usage_action
    if action not in {"show", "enable", "disable", "forget"}:
        return _failure(request, "unsupported usage action")
    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _failure(request, runtime.diagnostics[0].message)
    data_root = runtime.value.paths.data_root
    user_home = os.path.abspath(request.user_home or os.path.expanduser("~"))
    if action == "show":
        return _show(request, data_root=data_root, user_home=user_home)
    harnesses = tuple(dict.fromkeys(request.profiles))
    unknown = [item for item in harnesses if item not in USAGE_HARNESSES]
    if unknown or not harnesses:
        return _failure(
            request,
            f"artifact usage can be recorded in {', '.join(USAGE_HARNESSES)}, "
            f"not {', '.join(unknown) or 'no harness'}",
        )
    settings = read_consumer_settings(data_root)
    if isinstance(settings, Err):
        return _failure(request, settings.diagnostics[0].message)
    kept = settings.value
    said: list[str] = []
    for harness in harnesses:
        if action in {"enable", "disable"}:
            enabled = action == "enable"
            changed = set_usage_hook(harness, enabled, user_home=user_home, data_root=data_root)
            if isinstance(changed, Err):
                return _failure(request, changed.diagnostics[0].message)
            others = tuple(item for item in kept.recorded_usage if item != harness)
            kept = replace(kept, artifact_usage=(*others, harness) if enabled else others)
            written = write_consumer_settings(kept, data_root=data_root)
            if isinstance(written, Err):
                return _failure(request, written.diagnostics[0].message)
            if enabled:
                said.extend(
                    usage_disclosure(
                        harness,
                        database=ActivityDatabase(f"{data_root}/state").path,
                        changed_file=harness_file(harness, user_home=user_home),
                        telemetry_endpoint=telemetry_endpoint(data_root),
                    )
                )
            else:
                said.append(
                    f"{harness}: recording is off; the hook is removed from {changed.value}."
                )
        if action == "forget" or request.usage_forget:
            forgotten = ActivityDatabase(f"{data_root}/state").forget_uses(harness)
            if not isinstance(forgotten, Ok):
                return _failure(request, forgotten.diagnostics[0].message)
            said.append(f"{harness}: {forgotten.value} recorded uses deleted.")
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": f"{_OPERATION}.{action}",
                    "harnesses": list(harnesses),
                    "said": said,
                },
                indent=2,
            )
        )
    else:
        for line in said:
            print(line)
    return _common.OK
