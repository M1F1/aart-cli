"""`aart-cli maintain candidate list`: the Candidates the Upstream repositories offer (§175.2).

It reads exactly what Registry Maintainer Mode's Candidates screen reads -- the active Candidate
history bound to each Upstream repository's pinned snapshot -- and changes nothing. `promote` stays
with the Registry handler, which owns the transaction.
"""

from __future__ import annotations

import json

from aart_cli import command_outcome as _common
from aart_cli.application.maintainer_views import MaintainerCandidateView
from aart_cli.domain.diagnostics import diagnostic_to_data
from aart_cli.domain.result import Err
from aart_cli.io.maintainer_views import read_maintainer_views
from aart_cli.model import Request

from ._configured_runtime import load_runtime_configuration

_OPERATION = "candidate.list"


def _candidate_data(view: MaintainerCandidateView) -> dict[str, object]:
    return {
        "id": view.id,
        "state": view.state.value,
        "coordinate": view.coordinate,
        "version": view.version,
        "upstream": view.source_alias,
        "revision": view.source_revision,
        "manifest": view.manifest_path,
        "target_registry": view.target_registry,
        "promotion": view.promotion.value,
        "findings": list(view.findings),
    }


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


def run(request: Request) -> int:
    runtime = load_runtime_configuration(request, content_required=False)
    if isinstance(runtime, Err):
        return _emit_error(request, runtime)
    views = read_maintainer_views(
        runtime.value.loaded.effective,
        data_root=runtime.value.paths.data_root,
        registry_root=request.source_dir or request.project,
    )
    if isinstance(views, Err):
        return _emit_error(request, views)
    items = tuple(_candidate_data(view) for view in views.value.candidates or ())
    if request.json:
        print(
            json.dumps(
                {"schema_version": 1, "ok": True, "operation": _OPERATION, "candidates": items},
                indent=2,
            )
        )
    elif not items:
        # Only Registry Maintainer Mode's Source Sync records Candidate history today (B-202).
        print(
            "No Candidates are recorded. Open Registry Maintainer Mode in the TUI and run "
            "Source Sync on an Upstream repository."
        )
    else:
        for item in items:
            print(
                f"{item['id']} {item['state']} {item['coordinate']}@{item['version']} "
                f"from {item['upstream']}; {item['promotion']}"
            )
    return _common.OK
