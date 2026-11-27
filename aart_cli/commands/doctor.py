"""Environment-wide inspection through the canonical reconciliation engine.

Doctor is a read.  It observes each recorded installation once, projects the same health the
consumer application shows, and asks the existing repair planner for the smallest plan that would
reconcile each observation.  It neither resolves Marketplace content nor replays installation.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from aart_cli import command_outcome as _common
from aart_cli.application.consumer_session import (
    InstalledInspection,
    credential_dependants,
    installed_collections,
)
from aart_cli.application.consumer_views import (
    ActivityView,
    CredentialRecordView,
    InstalledArtifactView,
    PresentationProfile,
    ReceiptDetailView,
    activity_from_receipts,
    activity_view_to_data,
    project_credential_record,
    project_doctor,
    project_installed_artifact,
    project_lifecycle_plan,
    receipt_detail_to_data,
)
from aart_cli.application.maintainer_views import UnboundCandidateHistory
from aart_cli.application.offline_readiness import (
    OfflineReadiness,
    offline_readiness_to_data,
)
from aart_cli.application.orphaned_runs import (
    orphaned_run_lines,
    orphaned_runs_to_data,
)
from aart_cli.application.python_installers import (
    python_installer_lines,
    python_installers_to_data,
)
from aart_cli.application.reconciliation import repair_plan_to_data
from aart_cli.configuration.policy import EffectiveConfiguration
from aart_cli.consumer.application import CONSUMER_REVIEW_MISMATCH
from aart_cli.consumer.coordinates import CONSUMER_INVALID, parse_artifact_selector
from aart_cli.domain.diagnostics import Diagnostic, Severity, diagnostic_to_data
from aart_cli.domain.harness import Scope
from aart_cli.domain.installation_owner import describe_installation
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.result import Err
from aart_cli.io.configured_installation_action import InstallationHost
from aart_cli.io.configured_repair_action import (
    complete_configured_repair,
    prepare_configured_repair,
)
from aart_cli.io.consumer_machine import read_installed_inspections
from aart_cli.io.credentials import CredentialProviderPort
from aart_cli.io.failure_journal import note_diagnostics
from aart_cli.io.maintainer_views import read_unbound_candidate_histories
from aart_cli.io.offline_readiness import read_offline_readiness
from aart_cli.io.orphaned_runs import read_orphaned_runs
from aart_cli.io.python_installers import read_python_installers
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.model import Request
from aart_cli.receipt_service import resolved_paths
from aart_cli.tui_consumer import (
    render_activity,
    render_doctor,
    render_lifecycle_plan,
    render_receipt_detail,
)

from ._configured_runtime import load_runtime_configuration

_OPERATION = "doctor"
_REPAIR_OPERATION = "doctor.repair"


def _emit_error(
    request: Request,
    result: Err,
    operation: str = _OPERATION,
    **fields: object,
) -> int:
    note_diagnostics(result.diagnostics)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": operation,
                    **fields,
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


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (
            Diagnostic(
                CONSUMER_INVALID,
                Severity.ERROR,
                message,
                remediation=remediation,
            ),
        )
    )


def _emit(request: Request, payload: dict[str, object], lines: tuple[str, ...]) -> None:
    if request.json:
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(lines))


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


def _action_data(item: ReceiptDetailView) -> dict[str, object]:
    """One finished action, with the undo answer taken from the receipt rather than recomputed.

    INV-192: Doctor must not invent stronger undo guarantees than a receipt carries. Reusing
    `receipt_detail_to_data`'s own block is what keeps that structural rather than remembered --
    there is no second opinion here to drift out of step with the first.
    """

    return {
        "artifact": item.artifact,
        "intent": item.intent,
        "recorded_at": item.recorded_at,
        "status": item.status,
        "undo": receipt_detail_to_data(item)["undo"],
    }


def _activity_lines(
    actions: tuple[ReceiptDetailView, ...],
    view: ActivityView,
    profile: PresentationProfile,
) -> tuple[str, ...]:
    """The accepted timeline, then what each recorded action says about reversing itself."""

    if not actions:
        return ("Recent activity: nothing has been recorded on this machine yet.",)
    lines = ["Recent activity:", *render_activity(view, profile), ""]
    for item in actions:
        answer = (
            "can be undone: " + ", ".join(item.undo.components)
            if item.undo.available
            else "cannot be undone -- " + item.undo.reason
        )
        lines.append(f"  {item.artifact} ({item.intent}) {answer}")
    return tuple(lines)


def _credential_data(view: CredentialRecordView) -> dict[str, object]:
    """One credential reference and its observed health.

    `CredentialObservation` "deliberately has no value field", so there is no material here to
    withhold -- the type makes the guarantee, and this function cannot break it by forgetting.
    """

    return {
        "reference": view.reference,
        "input": view.input,
        "provider": view.provider,
        "service": view.service,
        "account": view.account,
        "provider_state": view.provider_state,
        "health": view.health,
        "detail": view.detail,
        "dependants": list(view.dependants),
        "actions": list(view.actions),
    }


def _configuration_data(effective: EffectiveConfiguration) -> dict[str, object]:
    """The two ways a machine quietly ignores what an operator configured.

    A disabled source is skipped by every other part of this report, deliberately, so nothing says
    it exists. And an organization policy that sets a reporting field replaces the user's own
    configured value -- `_locked_override_diagnostics` refuses a *runtime* override of one, but a
    value written in the user's configuration file is replaced in silence.
    """

    configuration = effective.configuration
    return {
        "disabled_sources": [
            {"alias": source.alias.value, "kind": source.kind.value, "location": source.location}
            for source in configuration.sources
            if not source.enabled
        ],
        "policy_locked_fields": list(effective.locked_fields),
    }


def _configuration_lines(effective: EffectiveConfiguration) -> tuple[str, ...]:
    disabled = tuple(source for source in effective.configuration.sources if not source.enabled)
    locked = effective.locked_fields
    if not disabled and not locked:
        return ("Configuration: every configured source is enabled and no field is policy-locked.",)
    lines = ["Configuration:"]
    for source in disabled:
        lines.append(
            f"  source {source.alias.value} is configured but disabled, so nothing offers it"
        )
    if locked:
        lines.append(
            "  set by organization policy, so your own value is not in force: " + ", ".join(locked)
        )
    return tuple(lines)


def _credential_lines(records: tuple[CredentialRecordView, ...]) -> tuple[str, ...]:
    if not records:
        return ("Credentials: no installed artifact references one.",)
    lines = ["Credentials:"]
    for item in records:
        needed = (
            "needed by " + ", ".join(map(describe_installation, item.dependants))
            if item.dependants
            else "no installed artifact needs it"
        )
        if item.health == "invalid":
            # Stored, but not what its artifact declares, so it is said why (§204).
            lines.append(f"  {item.reference} is not configured: {item.detail} ({needed})")
        else:
            lines.append(f"  {item.reference} is {item.health} ({needed})")
    return tuple(lines)


def _offline_lines(readiness: OfflineReadiness) -> tuple[str, ...]:
    lines = ["Offline readiness"]
    for source in readiness.sources:
        lines.append(f"{source.alias}: metadata {source.metadata.value}")
        for artifact in source.artifacts:
            lines.extend(
                (
                    str(artifact.coordinate),
                    f"  metadata {artifact.metadata.value}",
                    f"  canonical payload {artifact.canonical_payload.value}",
                    f"  runtime dependencies {artifact.runtime_dependencies.value}",
                )
            )
    return tuple(lines)


def _settings_move_data(inspections: tuple[InstalledInspection, ...]) -> list[dict[str, object]]:
    return [
        {
            "installation": item.installation,
            "coordinate": item.coordinate,
            "harness": move.harness,
            "recorded": move.recorded,
            "read": move.read,
            "scope": ""
            if item.record.receipt.owner is None
            else item.record.receipt.owner.scope.value,
        }
        for item in inspections
        for move in item.moves
    ]


def _settings_move_lines(
    inspections: tuple[InstalledInspection, ...], user_home: str
) -> tuple[str, ...]:
    """Say which installations sit in a settings file their harness no longer reads (§218).

    Without it the row above says only that a `settings` or `harness` component is divergent,
    which does not tell anybody that OpenCode never sees the server or plugin. Silence when there
    is none, as for Candidate history.
    """

    moved = [(item, move) for item in inspections for move in item.moves]
    if not moved:
        return ()
    home = user_home.rstrip("/") + "/"

    def shown(path: str) -> str:
        return "~/" + path[len(home) :] if path.startswith(home) else path

    lines = ["Settings files"]
    by_scope: dict[str, list[str]] = {}
    for item, move in moved:
        lines.extend(
            (
                f"⚠ {item.coordinate} · {move.harness}: written in {shown(move.recorded)}",
                f"  {move.harness} reads {shown(move.read)} instead, so it does not load this",
            )
        )
        owner = item.record.receipt.owner
        coordinates = by_scope.setdefault("" if owner is None else owner.scope.value, [])
        if item.coordinate not in coordinates:
            coordinates.append(item.coordinate)
    # One command per scope moves them all, reviewed and confirmed once.
    for scope, coordinates in by_scope.items():
        flag = f" --scope {scope}" if scope else ""
        lines.append(f"Move them: aart-cli doctor --repair {' '.join(coordinates)}{flag}")
    return tuple(lines)


def _candidate_history_lines(unbound: tuple[UnboundCandidateHistory, ...]) -> tuple[str, ...]:
    """Say which Sources hold Candidate history that does not describe what they have pinned.

    Silence when there is none: a section that prints "all clear" for a state nobody has ever seen
    is noise in a report people read when something is already wrong.
    """

    if not unbound:
        return ()
    lines = ["Candidate history"]
    for item in unbound:
        pinned = "nothing pinned" if item.pinned_revision is None else item.pinned_revision[:12]
        lines.append(
            f"{item.alias}: history recorded at {item.recorded_revision[:12]}, "
            f"snapshot pinned at {pinned}"
        )
        lines.append("  its Candidates are not shown until this is rebuilt")
        lines.append(f"  remediation: {item.remedy}")
    return tuple(lines)


def _run_repair(
    request: Request,
    *,
    data_root: str,
    project_root: str,
    user_home: str,
    credential_providers: tuple[CredentialProviderPort, ...],
) -> int:
    """Review or execute exact repairs through the configured lifecycle adapter: one, or several
    named together and confirmed as one plan."""

    scope = Scope(request.scope)
    inspected = read_installed_inspections(
        state_root=os.path.join(data_root, "state"),
        harness_root=project_root if scope is Scope.PROJECT else user_home,
        credential_providers=credential_providers,
        scope=scope,
    )
    if isinstance(inspected, Err):
        return _emit_error(request, inspected, _REPAIR_OPERATION, finalized=False)

    prepared_items = []
    for raw in dict.fromkeys(request.names):
        selector = parse_artifact_selector(raw)
        if isinstance(selector, Err):
            return _emit_error(request, selector, _REPAIR_OPERATION, finalized=False)
        if selector.value.source is None or selector.value.version is None:
            return _emit_error(
                request,
                _error(
                    "Doctor repair needs an exact source-qualified installed version",
                    "pass --repair <source>/<kind>/<name>@<version>",
                ),
                _REPAIR_OPERATION,
                finalized=False,
            )
        coordinate = str(selector.value)
        matches = tuple(
            item
            for item in inspected.value.inspections
            if str(item.record.coordinate) == coordinate
        )
        if len(matches) != 1:
            return _emit_error(
                request,
                _error(
                    f"no {scope.value}-scope installation matches {coordinate}",
                    "run aart-cli doctor, then pass exact installed coordinates to --repair",
                ),
                _REPAIR_OPERATION,
                finalized=False,
            )
        policy = EffectivePolicy()
        prepared = prepare_configured_repair(matches[0], policy=policy)
        if isinstance(prepared, Err):
            return _emit_error(request, prepared, _REPAIR_OPERATION, finalized=False)
        prepared_items.append((coordinate, policy, prepared.value))

    # One artifact keeps its own digest; several are reviewed and confirmed as one plan, whose
    # digest covers every one of theirs in order (§218: moving ten servers is one decision).
    digests = [str(item.review_digest) for _coordinate, _policy, item in prepared_items]
    digest = (
        digests[0]
        if len(digests) == 1
        else "sha256:" + hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()
    )
    reviews = [
        {
            "coordinate": coordinate,
            "review_digest": str(item.review_digest),
            "review": repair_plan_to_data(item.plan.repair),
        }
        for coordinate, _policy, item in prepared_items
    ]
    review_lines: list[str] = []
    for _coordinate, _policy, item in prepared_items:
        review_lines.extend(
            render_lifecycle_plan(project_lifecycle_plan(item.plan), PresentationProfile.LESS_INFO)
        )
    if len(prepared_items) == 1:
        base: dict[str, object] = {
            "schema_version": 1,
            "operation": _REPAIR_OPERATION,
            "coordinate": reviews[0]["coordinate"],
            "scope": scope.value,
            "review_digest": digest,
            "review": reviews[0]["review"],
        }
    else:
        review_lines.append(f"Repairs reviewed together: {len(prepared_items)}")
        review_lines.append(f"Review identity: {digest}")
        base = {
            "schema_version": 1,
            "operation": _REPAIR_OPERATION,
            "coordinates": [item["coordinate"] for item in reviews],
            "scope": scope.value,
            "review_digest": digest,
            "reviews": reviews,
        }
    if not request.yes:
        _emit(
            request,
            {**base, "ok": True, "finalized": False},
            (*review_lines, "Reviewed only; re-run with --yes and --expect to apply this plan."),
        )
        return _common.OK

    if request.expect is None or request.expect != digest:
        expected = request.expect
        message = (
            "repair confirmation requires --expect with the digest from a prior review"
            if expected is None
            else f"the plan changed since it was reviewed: expected {expected}, recomputed {digest}"
        )
        refusal = Err(
            (
                Diagnostic(
                    CONSUMER_REVIEW_MISMATCH,
                    Severity.ERROR,
                    message,
                    remediation=(
                        "re-read the repair review, then re-run --yes --expect with its review_digest",
                    ),
                ),
            )
        )
        return _emit_error(
            request,
            refusal,
            _REPAIR_OPERATION,
            finalized=False,
            expected_review_digest=expected,
            review_digest=digest,
            **({"review": base["review"]} if "review" in base else {"reviews": reviews}),
        )

    host = InstallationHost(data_root, project_root, user_home, scope)
    results: list[dict[str, object]] = []
    lines: list[str] = []
    successful = True
    for coordinate, policy, item in prepared_items:
        now = datetime.now(timezone.utc)
        completed = complete_configured_repair(
            item,
            expected_review_digest=item.review_digest,
            host=host,
            policy=policy,
            recorded_at=now.isoformat(),
            today=now.date(),
            credential_providers=credential_providers,
            offline=request.offline,
        )
        if isinstance(completed, Err):
            if len(prepared_items) == 1:
                return _emit_error(
                    request,
                    completed,
                    _REPAIR_OPERATION,
                    finalized=False,
                    review_digest=digest,
                )
            # The ones before it are applied and recorded; say which stopped, and go on with the
            # rest: each is its own installation, as an uninstall of several is.
            note_diagnostics(completed.diagnostics)
            successful = False
            results.append(
                {
                    "coordinate": coordinate,
                    "ok": False,
                    "diagnostics": [diagnostic_to_data(d) for d in completed.diagnostics],
                }
            )
            lines.extend(f"{coordinate}: {d.message}" for d in completed.diagnostics)
            continue
        receipt = completed.value.recorded.receipt
        ok = receipt.outcome.value in {"succeeded", "attention"}
        successful = successful and ok
        results.append(
            {
                "coordinate": coordinate,
                "ok": ok,
                "session_status": receipt.outcome.value,
                "receipt": receipt_detail_to_data(receipt),
            }
        )
        lines.extend(render_receipt_detail(receipt, PresentationProfile.LESS_INFO))
    if len(prepared_items) == 1:
        (only,) = results
        _emit(
            request,
            {
                **base,
                "ok": only["ok"],
                "finalized": True,
                "session_status": only["session_status"],
                "receipt": only["receipt"],
            },
            tuple(lines),
        )
    else:
        _emit(
            request,
            {**base, "ok": successful, "finalized": True, "results": results},
            tuple(lines),
        )
    return _common.OK if successful else _common.ERROR


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
    from . import marketplace

    # The stores every other command reads credentials through, so doctor agrees with them.
    providers = marketplace._credential_providers()
    if request.names:
        return _run_repair(
            request,
            data_root=runtime.value.paths.data_root,
            project_root=project_root,
            user_home=user_home,
            credential_providers=providers,
        )
    inspected = read_installed_inspections(
        state_root=os.path.join(runtime.value.paths.data_root, "state"),
        harness_root=project_root,
        credential_providers=providers,
    )
    if isinstance(inspected, Err):
        return _emit_error(request, inspected)
    offline = read_offline_readiness(
        runtime.value.loaded.effective,
        data_root=runtime.value.paths.data_root,
    )
    if isinstance(offline, Err):
        return _emit_error(request, offline)
    # pip and uv as an install runs them: the interpreter, the environment and the index (§216).
    installers = read_python_installers(check_index=request.check_index)
    # The run root is the data root, not the project root: deriving it a second time invites disagreement.
    orphaned = read_orphaned_runs(run_root=runtime.value.paths.data_root)
    # What the Maintainer screens say per Source, said here too: this is where somebody looks when
    # a Source's Candidates have gone quiet, and the repair is a command, not a file to delete.
    unbound = read_unbound_candidate_histories(
        runtime.value.loaded.effective,
        data_root=runtime.value.paths.data_root,
    )
    if isinstance(unbound, Err):
        return _emit_error(request, unbound)
    recorded = LocalReceiptStore(os.path.join(runtime.value.paths.data_root, "state")).actions()
    if isinstance(recorded, Err):
        return _emit_error(request, recorded)
    now = datetime.now(timezone.utc)
    timeline = activity_from_receipts(recorded.value, today=now.date())
    credentials = tuple(
        project_credential_record(
            item,
            dependants=credential_dependants(item, inspected.value.inspections),
        )
        for item in inspected.value.credentials
    )
    effective = runtime.value.loaded.effective

    artifacts = tuple(
        project_installed_artifact(
            item.desired,
            item.current,
            ownership=item.record.ownership,
            receipt=item.record.receipt,
            harness=item.harness,
        )
        for item in inspected.value.inspections
    )
    # Named by installation, as the TUI names them, so a Collection's members are its rows (§173.6).
    view = project_doctor(artifacts, installed_collections(inspected.value.inspections, artifacts))
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
        "ok": not view.attention_count and not unbound.value and not installers.needs_attention,
        "operation": _OPERATION,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "ready": view.ready_count,
            "needs_attention": view.attention_count,
        },
        "items": [_item_data(item) for item in artifacts],
        "repairs": repairs,
        "settings_files": _settings_move_data(inspected.value.inspections),
        "offline_readiness": offline_readiness_to_data(offline.value),
        "python_installers": python_installers_to_data(installers),
        "orphaned_runs": orphaned_runs_to_data(orphaned),
        "candidate_history": {
            "unbound": [
                {
                    "alias": item.alias,
                    "pinned_revision": item.pinned_revision,
                    "recorded_revision": item.recorded_revision,
                    "remediation": item.remedy,
                }
                for item in unbound.value
            ]
        },
        "activity": activity_view_to_data(timeline),
        "recorded_actions": [_action_data(item) for item in recorded.value],
        "credentials": [_credential_data(item) for item in credentials],
        "configuration": _configuration_data(effective),
    }
    if request.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            "\n".join(
                (
                    *render_doctor(view, PresentationProfile.LESS_INFO),
                    *(
                        ("", *moves)
                        if (moves := _settings_move_lines(inspected.value.inspections, user_home))
                        else ()
                    ),
                    "",
                    *_offline_lines(offline.value),
                    "",
                    *python_installer_lines(installers),
                    "",
                    *orphaned_run_lines(orphaned),
                    "",
                    *_candidate_history_lines(unbound.value),
                    "",
                    *_activity_lines(recorded.value, timeline, PresentationProfile.LESS_INFO),
                    "",
                    *_credential_lines(credentials),
                    "",
                    *_configuration_lines(effective),
                )
            )
        )
    return _common.OK if payload["ok"] else _common.ERROR
