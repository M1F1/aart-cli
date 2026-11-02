"""`aart-cli consume report`: the failures aart-cli met here, to paste into an issue (§215)."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AbstractContextManager

from aart_cli import command_outcome as _common
from aart_cli.configuration.paths import APPLICATION_HOME_VARIABLE, Platform, resolve_config_paths
from aart_cli.configuration.policy import redact_text
from aart_cli.domain.failures import FailureGroup, FailureKind, grouped
from aart_cli.domain.result import Err
from aart_cli.io.failure_journal import FailureJournal, noting, record_failure
from aart_cli.model import Request

from ._configured_runtime import load_runtime_configuration

_OPERATION = "report"


def _failure(request: Request, message: str) -> int:
    safe = redact_text(message)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": _OPERATION,
                    "diagnostics": [{"code": "report-invalid", "message": safe}],
                },
                indent=2,
            )
        )
    else:
        print(f"error: {safe}")
    return _common.ERROR


def _group_data(group: FailureGroup) -> dict[str, object]:
    return {
        "kind": group.failure.kind.value,
        "place": group.failure.place,
        "count": group.count,
        "first_seen": group.first_seen,
        "last_seen": group.last_seen,
        "versions": list(group.versions),
        "failure": group.failure.document(),
    }


def report_lines(groups: tuple[FailureGroup, ...]) -> list[str]:
    """The groups as a block to paste into an issue."""

    if not groups:
        return ["No failures are journaled here."]
    lines = ["aart-cli failures, seen last first; nothing here left this machine.", "```"]
    for number, group in enumerate(groups, start=1):
        failure = group.failure
        times = "once" if group.count == 1 else f"{group.count} times"
        lines.append(
            f"{number}. {failure.kind.value} in {failure.place}: {times}, "
            f"{group.first_seen} .. {group.last_seen}, aart-cli {', '.join(group.versions)}"
        )
        lines.append(f"   fingerprint: {failure.fingerprint}")
        if failure.exception is not None:
            lines.append(f"   exception: {failure.exception}")
        if failure.exit_code is not None:
            lines.append(f"   exit code: {failure.exit_code}")
        if failure.diagnostics:
            lines.append(f"   diagnostics: {', '.join(failure.diagnostics)}")
        lines.append(f"   python {failure.python} on {failure.platform}")
        if failure.frames:
            lines.append("   frames, innermost last:")
            lines.extend(f"     {frame}" for frame in failure.frames)
    lines.append("```")
    return lines


def run(request: Request) -> int:
    limit = request.report_limit
    if limit is not None and limit < 1:
        return _failure(request, "--limit is a whole number of at least 1")
    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _failure(request, runtime.diagnostics[0].message)
    journal = FailureJournal(f"{runtime.value.paths.data_root}/state")
    entries = journal.entries()
    if isinstance(entries, Err):
        return _failure(request, entries.diagnostics[0].message)
    groups = grouped(entries.value)[:limit]
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": _OPERATION,
                    "journal": journal.path,
                    "failures": [_group_data(group) for group in groups],
                },
                indent=2,
            )
        )
    else:
        for line in report_lines(groups):
            print(line)
    return _common.OK


#: The subcommand destinations of `cli_parser`, in the order a command line names them.
_ACTIONS = (
    "consume_action",
    "maintain_action",
    "author_action",
    "security_action",
    "registry_action",
    "source_action",
    "candidate_action",
    "mcp_action",
    "usage_action",
    "telemetry_action",
    "inputs_action",
    "receipt_action",
)


def command_place(args: object) -> str:
    """Where a command failed, in its own words: the command and its subcommands, joined by `.`
    (`consume.update`); never an argument (INV-333)."""

    words = [getattr(args, "command", None)]
    words.extend(getattr(args, action, None) for action in _ACTIONS)
    return ".".join(word for word in words if isinstance(word, str) and word)


def noting_diagnostics() -> AbstractContextManager[list[str]]:
    """Collect the diagnostic codes the command run inside reports, for its failure."""

    return noting()


def record_command_failure(
    request: Request,
    kind: str,
    place: str,
    *,
    error: BaseException | None = None,
    exit_code: int | None = None,
    diagnostics: tuple[str, ...] = (),
) -> None:
    """Journal a command's failure in its application home (§215)."""

    record_in_application_home(
        request.user_home,
        kind,
        place,
        error=error,
        exit_code=exit_code,
        diagnostics=diagnostics,
    )


def record_in_application_home(
    user_home: str | None,
    kind: str,
    place: str,
    *,
    error: BaseException | None = None,
    exit_code: int | None = None,
    diagnostics: tuple[str, ...] = (),
) -> None:
    """Journal a failure in the application home `user_home` resolves to, as every command
    resolves it. Never raises, never prints: what failed ends as it would have (INV-335)."""

    try:
        paths = resolve_config_paths(
            Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX,
            home=os.path.abspath(user_home or os.path.expanduser("~")),
            application_home=os.environ.get(APPLICATION_HOME_VARIABLE) or None,
        )
        record_failure(
            paths.data_root,
            FailureKind(kind),
            place,
            error=error,
            exit_code=exit_code,
            diagnostics=diagnostics,
        )
    except Exception:  # noqa: BLE001 -- recording never changes what failed
        pass
