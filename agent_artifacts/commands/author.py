"""The authoring group: `aart author init` writes a skeleton an author edits down.

A group of its own, rather than a `registry` or `source` action. `registry` writes to a Registry,
which is the wrong target -- an author's workspace is their own -- and `source` is about
subscriptions rather than content (CP-26 §1.3).
"""

from __future__ import annotations

import json

from agent_artifacts.authoring.check import AuthorCheckReport, check_author_manifests
from agent_artifacts.authoring.skeleton import author_skeleton
from agent_artifacts.command_outcome import ERROR, OK
from agent_artifacts.domain.diagnostics import Diagnostic, diagnostic_to_data
from agent_artifacts.domain.result import Err
from agent_artifacts.io.author_workspace import read_author_workspace, write_author_skeleton
from agent_artifacts.model import Request

_READ_THE_ACTIONS = "Run `aart author --help` for the actions this build has."


def _report(diagnostics: tuple[Diagnostic, ...], *, as_json: bool = False) -> int:
    if as_json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": "author.check",
                    "diagnostics": [diagnostic_to_data(item) for item in diagnostics],
                },
                indent=2,
            )
        )
        return ERROR
    for diagnostic in diagnostics:
        print(f"error: {diagnostic.message}")
        for remediation in diagnostic.remediation:
            print(f"  {remediation}")
    return ERROR


def _run_init(request: Request) -> int:
    kind = request.artifact_kind or ""
    name = request.author_name or ""
    generated = author_skeleton(kind, name)
    if isinstance(generated, Err):
        return _report(generated.diagnostics)
    written = write_author_skeleton(generated.value, into=request.author_into or ".")
    if isinstance(written, Err):
        return _report(written.diagnostics)
    print(f"Wrote a {kind} authoring workspace for {name} under {written.value.root}:")
    for relative in written.value.paths:
        print(f"  {relative}")
    print("Delete what you do not need, uncomment what you do, then `aart author check`.")
    return OK


def _check_data(report: AuthorCheckReport) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ok": report.accepted,
        "operation": "author.check",
        "manifests": [
            {
                "path": verdict.path,
                "ok": verdict.accepted,
                "diagnostics": [diagnostic_to_data(item) for item in verdict.diagnostics],
            }
            for verdict in report.verdicts
        ],
    }


def _run_check(request: Request) -> int:
    """Read the tree the way a Source Sync reads one, then answer with the parser."""

    snapshot = read_author_workspace(request.author_source or ".")
    if isinstance(snapshot, Err):
        return _report(snapshot.diagnostics, as_json=request.json)
    checked = check_author_manifests(snapshot.value)
    if isinstance(checked, Err):
        return _report(checked.diagnostics, as_json=request.json)
    report = checked.value
    if request.json:
        print(json.dumps(_check_data(report), indent=2))
        return OK if report.accepted else ERROR
    for verdict in report.verdicts:
        print(f"{'ok   ' if verdict.accepted else 'error'} {verdict.path}")
        for diagnostic in verdict.diagnostics:
            print(f"        {diagnostic.message}")
            for remediation in diagnostic.remediation:
                print(f"        {remediation}")
    if report.accepted:
        print(f"{len(report.verdicts)} manifest(s) parse.")
        return OK
    return ERROR


def run(request: Request) -> int:
    action = request.author_action or "unknown"
    if action == "init":
        return _run_init(request)
    if action == "check":
        return _run_check(request)
    print(f"error: unknown author action: {action}")
    print(f"  {_READ_THE_ACTIONS}")
    return ERROR


__all__ = ["run"]
