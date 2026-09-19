"""The authoring group: `aart author init` writes a skeleton an author edits down.

A group of its own, rather than a `registry` or `source` action. `registry` writes to a Registry,
which is the wrong target -- an author's workspace is their own -- and `source` is about
subscriptions rather than content (CP-26 §1.3).
"""

from __future__ import annotations

from agent_artifacts.authoring.skeleton import author_skeleton
from agent_artifacts.command_outcome import ERROR, OK
from agent_artifacts.domain.diagnostics import Diagnostic
from agent_artifacts.domain.result import Err
from agent_artifacts.io.author_workspace import write_author_skeleton
from agent_artifacts.model import Request

_READ_THE_ACTIONS = "Run `aart author --help` for the actions this build has."


def _report(diagnostics: tuple[Diagnostic, ...]) -> int:
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
    print("Delete the fields you do not need and uncomment the ones you do.")
    return OK


def run(request: Request) -> int:
    action = request.author_action or "unknown"
    if action == "init":
        return _run_init(request)
    print(f"error: unknown author action: {action}")
    print(f"  {_READ_THE_ACTIONS}")
    return ERROR


__all__ = ["run"]
