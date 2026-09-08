"""Maintainer registry commands over pure plans and reviewed filesystem effects."""

from __future__ import annotations

import json
import os
import re
import subprocess

from agent_artifacts import command_outcome as _common
from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.application.promotion import (
    PromotionEvidence,
    finalize_promotion,
    load_registry_versions,
    plan_bulk_promotion,
)
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.curation.model import (
    DEFAULT_MAXIMUM_AART,
    DEFAULT_MINIMUM_AART,
    CurationAction,
    CurationOutcome,
    CurationRequest,
    CurationReview,
    render_curation_outcome,
    render_curation_review,
)
from agent_artifacts.curation.runtime import (
    default_native_acquirer,
    load_local_curation_service,
)
from agent_artifacts.domain.candidates import CandidateState, assess_candidate
from agent_artifacts.domain.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    Severity,
    diagnostic_to_data,
)
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.registry import PromotionMode, RegistryArtifactVersion
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.registry_adoption import (
    AdoptionUpstreamCheck,
    PreparedAdoption,
    RepositoryScan,
    ScannedArtifact,
    apply_adoption,
    check_adopted_upstream,
    prepare_adoption,
    scan_repository,
)
from agent_artifacts.io.registry_promotion import FilesystemPromotionOutput
from agent_artifacts.io.registry_workspace import FilesystemRegistryWorkspace
from agent_artifacts.model import Request
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.hashing import parse_sha256
from agent_artifacts.protocol.native_tree import SnapshotEntryKind, SourceSnapshot
from agent_artifacts.protocol.registry_models import RegistryManifest
from agent_artifacts.protocol.registry_schema import parse_registry_manifest
from agent_artifacts.protocol.semver import SemVer, parse_semver
from agent_artifacts.registry_commands.model import RegistryQualityReport
from agent_artifacts.registry_commands.planning import (
    audit_registry_workspace,
    test_registry_compatibility,
    validate_registry_workspace,
)
from agent_artifacts.registry_maintenance.discovery import discover_vendor_candidates
from agent_artifacts.runtime_contract import EXECUTABLE_CAPABILITIES, EXECUTABLE_VERSION
from agent_artifacts.sources.local import read_local_snapshot
from agent_artifacts.sources.model import LocalSnapshotRequest, SnapshotLimits, source_instance_id

_VERSION = EXECUTABLE_VERSION
_CAPABILITIES = EXECUTABLE_CAPABILITIES
REGISTRY_COMMAND_INVALID = DiagnosticCode("registry-command-invalid")


# `RS-09`: what an operator does next after this module refuses. The planning module carries the
# same idea for the refusals it raises; these are the ones raised before planning is reached, where
# the problem is the invocation rather than the workspace.
_READ_THE_ACTIONS = ("`aart registry --help` lists the actions this command accepts",)
_NAME_THE_ARTIFACT = (
    "name exactly one artifact kind and name, in the form the action's own `--help` shows",
)
_INITIALIZE = (
    "point `--source` at a registry checkout, or create one with "
    "`aart registry init --source-id SLUG --display-name NAME --yes`",
)
_STATE_THE_RELEASE = (
    "state the release to test against: `aart registry test --latest-version VERSION`",
)
_MINIMUM_VERSION = (
    "record a minimum AART version in `aart-registry.json` — `requires_aart.min_inclusive` — then "
    "`aart registry test`",
)


def _error(message: str, remediation: tuple[str, ...]) -> Err:
    return Err(
        (Diagnostic(REGISTRY_COMMAND_INVALID, Severity.ERROR, message, remediation=remediation),)
    )


def _root(request: Request) -> str:
    return os.path.abspath(request.source_dir or ".")


def _version(raw: str | None, label: str) -> Result[SemVer]:
    if raw is None:
        return _error(f"{label} is required", _STATE_THE_RELEASE)
    parsed = parse_semver(raw)
    if isinstance(parsed, Err):
        return _error(f"{label} must be canonical SemVer", _STATE_THE_RELEASE)
    return parsed


def _emit_error(request: Request, action: str, result: Err) -> int:
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "operation": f"registry.{action}",
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


def _curation_review_data(review: CurationReview) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ok": True,
        "operation": f"registry.{review.action.value}",
        "phase": "review",
        "applied": False,
        "mutating": review.mutating,
        "review_digest": str(review.review_digest),
        "snapshot_digest": str(review.snapshot_digest),
        "changes": [{"path": item.path, "status": item.status} for item in review.changes],
        "checks": [
            {"name": item.name, "passed": item.passed, "details": list(item.details)}
            for item in review.checks
        ],
        "warnings": list(review.warnings),
        "follow_up_commands": list(review.follow_up_commands),
    }


def _curation_outcome_data(outcome: CurationOutcome) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ok": outcome.status != "failed",
        "operation": f"registry.{outcome.action.value}",
        "phase": "finalized",
        "status": outcome.status,
        "changed_paths": outcome.changed_paths,
        "observed_paths": outcome.observed_paths,
        "checks": [
            {"name": item.name, "passed": item.passed, "details": list(item.details)}
            for item in outcome.checks
        ],
        "warnings": list(outcome.warnings),
        "follow_up_commands": list(outcome.follow_up_commands),
    }


def _emit_curation_review(request: Request, review: CurationReview) -> None:
    if request.json:
        print(json.dumps(_curation_review_data(review), indent=2))
        return
    print("\n".join(render_curation_review(review)))


def _emit_curation_outcome(
    request: Request,
    outcome: CurationOutcome,
    *,
    reviewed: CurationReview | None = None,
) -> None:
    if request.json:
        print(json.dumps(_curation_outcome_data(outcome), indent=2))
        return
    print("\n".join(render_curation_outcome(outcome, reviewed=reviewed)))


def _emit_curation_finalization(
    request: Request,
    review: CurationReview,
    outcome: CurationOutcome,
) -> None:
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": outcome.status != "failed",
                    "operation": f"registry.{outcome.action.value}",
                    "phase": "finalized",
                    "review": _curation_review_data(review),
                    "outcome": _curation_outcome_data(outcome),
                },
                indent=2,
            )
        )
        return
    _emit_curation_review(request, review)
    _emit_curation_outcome(request, outcome, reviewed=review)


def _curation_request(request: Request, action: CurationAction) -> Result[CurationRequest]:
    if action in {
        CurationAction.PROMOTE_NATIVE,
        CurationAction.REFRESH_NATIVE,
        CurationAction.VENDOR,
        CurationAction.REVENDOR,
    } and (request.artifact_kind is None or len(request.names) != 1):
        return _error(
            f"{action.value} requires an exact artifact kind and name", _NAME_THE_ARTIFACT
        )
    if action is CurationAction.COLLECTION and len(request.names) != 1:
        return _error("collection requires an exact collection name", _NAME_THE_ARTIFACT)
    try:
        return Ok(
            CurationRequest(
                action,
                _root(request),
                kind=request.artifact_kind,
                name=request.names[0] if len(request.names) == 1 else None,
                summary=request.summary,
                members=request.collection_members,
                vendor_manifest=(
                    os.path.abspath(request.vendor_manifest)
                    if request.vendor_manifest is not None
                    else None
                ),
                # Re-vendoring is the one action where an unstated version is an answer rather
                # than a gap: it means "tell me what moved, plan nothing".
                artifact_version=(
                    request.artifact_version
                    if action is CurationAction.REVENDOR
                    else request.artifact_version or "1.0.0"
                ),
                artifact_license=request.artifact_license,
                profiles=request.profiles,
                platforms=request.registry_platforms,
                scopes=request.registry_scopes or ("project",),
                modes=request.registry_modes or ("copy",),
                url=request.native_url,
                ref=request.ref or "main",
                path=request.native_path,
                setup_recipe=request.setup_recipe,
                review_policy=request.review_policy or "manual-review-v1",
                source_id=request.source_id,
                display_name=request.display_name,
                usage_reporting_repository=request.usage_reporting_repository,
                # `RS-02`: only `init` declares a compatibility window, and only `init` reads one
                # back, so every other action arrives here with both unset.  The substitute has to
                # be the window of the AART that is running -- literals bound a registry to the
                # release they were typed in, and `1.0.0`/`2.0.0` had already stopped a major
                # short of the executable stamping them.
                minimum_version=request.minimum_version or DEFAULT_MINIMUM_AART,
                maximum_version=request.maximum_version or DEFAULT_MAXIMUM_AART,
            )
        )
    except ValueError as error:
        return _error(str(error), _READ_THE_ACTIONS)


def _run_curation(request: Request, action: CurationAction) -> int:
    curation_request = _curation_request(request, action)
    if isinstance(curation_request, Err):
        return _emit_error(request, action.value, curation_request)
    service = load_local_curation_service(_root(request))
    if isinstance(service, Err):
        return _emit_error(request, action.value, service)
    prepared = service.value.prepare(curation_request.value)
    if isinstance(prepared, Err):
        return _emit_error(request, action.value, prepared)
    review = prepared.value.review
    if request.check:
        _emit_curation_review(request, review)
        # A failed check counts as drift.  Without this, `revendor --check` against an unreachable
        # upstream would exit zero for having written nothing, which is the one reading design §6
        # forbids.
        return (
            _common.OK
            if all(item.status == "unchanged" for item in review.changes)
            and all(item.passed for item in review.checks)
            else _common.ERROR
        )
    if not request.yes:
        _emit_curation_review(request, review)
        return _common.OK
    finalized = service.value.finalize(prepared.value, review.review_digest)
    if isinstance(finalized, Err):
        return _emit_error(request, action.value, finalized)
    _emit_curation_finalization(request, review, finalized.value)
    return _common.OK if finalized.value.status != "failed" else _common.ERROR


def _emit_report(request: Request, action: str, report: RegistryQualityReport) -> None:
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": report.passed,
                    "operation": f"registry.{action}",
                    "checks": [
                        {
                            "name": check.name,
                            "passed": check.passed,
                            "diagnostics": [diagnostic_to_data(item) for item in check.diagnostics],
                        }
                        for check in report.checks
                    ],
                },
                indent=2,
            )
        )
        return
    for check in report.checks:
        print(f"registry {check.name}: {'passed' if check.passed else 'failed'}")
        for diagnostic in check.diagnostics:
            print(f"  {diagnostic.severity.value}: {diagnostic.message}")
            # `RS-09`: the JSON envelope carried remediation through `diagnostic_to_data` all along
            # and this renderer dropped it, which is `LAF-52`'s shape one command family over. A
            # report is where `validate` and `audit` state a refusal, so it renders the next step
            # exactly as `_emit_error` does.
            for remediation in diagnostic.remediation:
                print(f"    remediation: {remediation}")


def _snapshot(workspace: FilesystemRegistryWorkspace) -> Result[SourceSnapshot]:
    return workspace.snapshot()


def _run_validate(request: Request, workspace: FilesystemRegistryWorkspace) -> int:
    current = _snapshot(workspace)
    if isinstance(current, Err):
        return _emit_error(request, "validate", current)
    checked = validate_registry_workspace(
        current.value,
        executable_version=_VERSION,
        available_capabilities=_CAPABILITIES,
        require_compiled=request.strict or request.frozen,
    )
    if isinstance(checked, Err):
        return _emit_error(request, "validate", checked)
    _emit_report(request, "validate", checked.value)
    return _common.OK if checked.value.passed else _common.ERROR


def _run_audit(request: Request, workspace: FilesystemRegistryWorkspace) -> int:
    current = _snapshot(workspace)
    if isinstance(current, Err):
        return _emit_error(request, "audit", current)
    checked = audit_registry_workspace(
        current.value,
        executable_version=_VERSION,
        available_capabilities=_CAPABILITIES,
        # The audit reads the committed workspace and nothing else unless asked: `--check-upstream`
        # is what turns it into a command that resolves vendored origins, and it still only reports.
        upstream_acquirer=default_native_acquirer if request.check_upstream else None,
    )
    if isinstance(checked, Err):
        return _emit_error(request, "audit", checked)
    _emit_report(request, "audit", checked.value)
    return _common.OK if checked.value.passed else _common.ERROR


def _registry_manifest(snapshot: SourceSnapshot) -> Result[RegistryManifest]:
    for item in snapshot.entries:
        if str(item.path) == "aart-registry.json" and item.kind is SnapshotEntryKind.FILE:
            return parse_registry_manifest(item.content)
    return _error("registry workspace requires aart-registry.json", _INITIALIZE)


def _run_test(request: Request, workspace: FilesystemRegistryWorkspace) -> int:
    current = _snapshot(workspace)
    if isinstance(current, Err):
        return _emit_error(request, "test", current)
    manifest = _registry_manifest(current.value)
    latest = _version(request.latest_version, "--latest-version")
    if isinstance(manifest, Err):
        return _emit_error(request, "test", manifest)
    if isinstance(latest, Err):
        return _emit_error(request, "test", latest)
    minimum = manifest.value.requires_aart.min_inclusive
    if minimum is None:
        return _emit_error(
            request,
            "test",
            _error("registry compatibility tests require a minimum AART version", _MINIMUM_VERSION),
        )
    checked = test_registry_compatibility(
        current.value,
        minimum=minimum,
        latest=latest.value,
        available_capabilities=_CAPABILITIES,
    )
    if isinstance(checked, Err):
        return _emit_error(request, "test", checked)
    selected = checked.value
    if request.compatibility in {"minimum", "latest"}:
        selected = RegistryQualityReport(
            tuple(item for item in selected.checks if item.name == request.compatibility)
        )
    _emit_report(request, "test", selected)
    return _common.OK if selected.passed else _common.ERROR


def _run_discover(request: Request) -> int:
    """Scan one inert checkout and emit the manifest the batch command consumes."""

    if (
        request.discovery_checkout is None
        or request.native_url is None
        or request.artifact_version is None
        or not request.profiles
        or not request.registry_platforms
    ):
        return _emit_error(
            request,
            "discover",
            _error(
                "discover requires checkout, URL, artifact version, profiles, and platforms",
                _READ_THE_ACTIONS,
            ),
        )
    version = _version(request.artifact_version, "artifact version")
    if isinstance(version, Err):
        return _emit_error(request, "discover", version)
    checkout = os.path.abspath(request.discovery_checkout)
    try:
        configured = ConfiguredSource(
            SourceAlias("registry-discovery"),
            SourceKind.SOURCE_LOCAL,
            checkout,
            None,
            True,
        )
        acquired = read_local_snapshot(
            LocalSnapshotRequest(
                source_instance_id(configured),
                configured.alias,
                checkout,
                SnapshotLimits(),
            )
        )
    except ValueError as error:
        return _emit_error(request, "discover", _error(str(error), _READ_THE_ACTIONS))
    if isinstance(acquired, Err):
        return _emit_error(request, "discover", acquired)
    candidates = discover_vendor_candidates(acquired.value.snapshot)
    defaults: dict[str, object] = {
        "artifact_version": str(version.value),
        "profiles": list(request.profiles),
        "platforms": list(request.registry_platforms),
        "scopes": list(request.registry_scopes or ("project",)),
        "modes": list(request.registry_modes or ("copy",)),
        "review_policy": request.review_policy or "manual-review-v1",
    }
    manifest = {
        "schema_version": 1,
        "origin": {"url": request.native_url, "ref": request.ref or "main"},
        "defaults": defaults,
        "artifacts": [
            {
                "accept": request.discovery_accept_all,
                "kind": candidate.kind,
                "name": candidate.name,
                "path": candidate.path,
                "summary": f"Discovered {candidate.kind} from {candidate.path}.",
                "reason": candidate.reason,
            }
            for candidate in candidates
        ],
    }
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if request.discovery_output is None:
        print(rendered, end="")
        return _common.OK
    output = os.path.abspath(request.discovery_output)
    try:
        with open(output, "x", encoding="utf-8") as stream:
            stream.write(rendered)
    except OSError as error:
        return _emit_error(
            request,
            "discover",
            _error(f"cannot create discovery manifest {output}: {error}", _READ_THE_ACTIONS),
        )
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": "registry.discover",
                    "output": output,
                    "candidates": len(candidates),
                    "accepted": len(candidates) if request.discovery_accept_all else 0,
                },
                indent=2,
            )
        )
    else:
        print(f"wrote {len(candidates)} candidates to {output}")
        print("review each `accept` field, then run `aart registry vendor-batch --manifest FILE`")
    return _common.OK


def _run_scan(request: Request) -> int:
    """Observe one exact author revision and report Candidates without registry effects."""

    if (
        request.candidate_checkout is None
        or request.candidate_source_alias is None
        or request.candidate_source_url is None
        or request.target_registry_alias is None
    ):
        return _emit_error(
            request,
            "scan",
            _error(
                "scan requires checkout, source alias, source URL, and target registry",
                _READ_THE_ACTIONS,
            ),
        )
    alias_pattern = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
    if (
        re.fullmatch(alias_pattern, request.candidate_source_alias) is None
        or re.fullmatch(alias_pattern, request.target_registry_alias) is None
        or not request.candidate_source_url.strip()
        or request.candidate_source_url != request.candidate_source_url.strip()
        or any(character in request.candidate_source_url for character in "\r\n")
    ):
        return _emit_error(
            request,
            "scan",
            _error("scan aliases or source URL are invalid", _READ_THE_ACTIONS),
        )
    checkout = os.path.abspath(request.candidate_checkout)
    revision = _git(checkout, "rev-parse", "--verify", "HEAD")
    dirty = _git(checkout, "status", "--porcelain=v1", "--untracked-files=all")
    if (
        revision.returncode != 0
        or re.fullmatch(r"[0-9a-f]{40}", revision.stdout.strip()) is None
        or dirty.returncode != 0
        or dirty.stdout
    ):
        return _emit_error(
            request,
            "scan",
            _error(
                "Source Scan requires one clean pinned Git checkout at HEAD",
                (
                    "commit or discard author checkout changes; `aart registry scan --help` "
                    "shows the explicit source boundaries",
                ),
            ),
        )
    source_alias = SourceAlias(request.candidate_source_alias)
    target_registry = SourceAlias(request.target_registry_alias)
    try:
        configured = ConfiguredSource(
            source_alias,
            SourceKind.SOURCE_LOCAL,
            checkout,
            None,
            True,
        )
        acquired = read_local_snapshot(
            LocalSnapshotRequest(
                source_instance_id(configured),
                source_alias,
                checkout,
                SnapshotLimits(),
            )
        )
    except ValueError as error:
        return _emit_error(request, "scan", _error(str(error), _READ_THE_ACTIONS))
    if isinstance(acquired, Err):
        return _emit_error(request, "scan", acquired)
    pinned_revision = revision.stdout.strip()
    compiled = compile_author_snapshot(
        acquired.value.snapshot,
        source_alias=source_alias,
        source=request.candidate_source_url,
        revision=pinned_revision,
    )
    if isinstance(compiled, Err):
        return _emit_error(request, "scan", compiled)
    approved: tuple[RegistryArtifactVersion, ...] = ()
    if request.source_dir is not None:
        registry_snapshot = FilesystemRegistryWorkspace(_root(request)).snapshot()
        if isinstance(registry_snapshot, Err):
            return _emit_error(request, "scan", registry_snapshot)
        loaded_versions = load_registry_versions(registry_snapshot.value)
        if isinstance(loaded_versions, Err):
            return _emit_error(request, "scan", loaded_versions)
        approved = loaded_versions.value
    scanned = reconcile_source_scan(
        source_alias,
        pinned_revision,
        compiled.value,
        previous=(),
        approved=approved,
        target_registry=target_registry,
    )
    if isinstance(scanned, Err):
        return _emit_error(request, "scan", scanned)
    candidates = tuple(item.candidate for item in scanned.value.active)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": "registry.scan",
                    "source_alias": source_alias.value,
                    "source_revision": pinned_revision,
                    "target_registry": target_registry.value,
                    "manifest_count": scanned.value.manifest_count,
                    "registry_mutations": len(scanned.value.registry_mutations),
                    "candidates": [
                        {
                            "candidate_id": item.id.value,
                            "coordinate": str(item.artifact.coordinate),
                            "input_digest": str(item.artifact.provenance.input_digest),
                            "canonical_digest": str(item.canonical_digest),
                            "state": item.state.value,
                        }
                        for item in candidates
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Source Scan {source_alias.value}@{pinned_revision}")
        print(f"target registry: {target_registry.value}")
        print(f"{len(candidates)} candidate(s); registry mutations: 0")
        for item in candidates:
            print(f"  {item.state.value:>7}  {item.artifact.coordinate}  {item.id}")
    return _common.OK


def _run_candidate_promotion(request: Request) -> int:
    """Re-observe exact IDs, then review or apply one local promotion transaction."""

    if (
        request.source_dir is None
        or request.candidate_checkout is None
        or request.candidate_source_alias is None
        or request.candidate_source_url is None
        or request.target_registry_alias is None
        or request.promotion_validation_report is None
        or request.promotion_policy_result is None
        or not request.promotion_candidate_ids
    ):
        return _emit_error(
            request,
            "promote",
            _error(
                "candidate promotion requires all explicit review boundaries", _READ_THE_ACTIONS
            ),
        )
    alias_pattern = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
    if (
        re.fullmatch(alias_pattern, request.candidate_source_alias) is None
        or re.fullmatch(alias_pattern, request.target_registry_alias) is None
        or not request.candidate_source_url.strip()
        or request.candidate_source_url != request.candidate_source_url.strip()
        or any(character in request.candidate_source_url for character in "\r\n")
        or len(set(request.promotion_candidate_ids)) != len(request.promotion_candidate_ids)
        or any(
            re.fullmatch(r"[0-9a-f]{64}", candidate_id) is None
            for candidate_id in request.promotion_candidate_ids
        )
    ):
        return _emit_error(
            request,
            "promote",
            _error("candidate promotion aliases, URL or IDs are invalid", _READ_THE_ACTIONS),
        )
    validation_report = parse_sha256(request.promotion_validation_report)
    policy_result = parse_sha256(request.promotion_policy_result)
    if isinstance(validation_report, Err) or isinstance(policy_result, Err):
        return _emit_error(
            request,
            "promote",
            _error("promotion evidence digests must be canonical SHA-256", _READ_THE_ACTIONS),
        )
    try:
        mode = PromotionMode(request.promotion_mode)
    except ValueError:
        return _emit_error(
            request,
            "promote",
            _error("promotion mode must be vendored or referenced", _READ_THE_ACTIONS),
        )
    output = FilesystemPromotionOutput(_root(request))
    registry_snapshot = output.current()
    if isinstance(registry_snapshot, Err):
        return _emit_error(request, "promote", registry_snapshot)
    approved = load_registry_versions(registry_snapshot.value)
    if isinstance(approved, Err):
        return _emit_error(request, "promote", approved)

    checkout = os.path.abspath(request.candidate_checkout)
    revision = _git(checkout, "rev-parse", "--verify", "HEAD")
    dirty = _git(checkout, "status", "--porcelain=v1", "--untracked-files=all")
    if (
        revision.returncode != 0
        or re.fullmatch(r"[0-9a-f]{40}", revision.stdout.strip()) is None
        or dirty.returncode != 0
        or dirty.stdout
    ):
        return _emit_error(
            request,
            "promote",
            _error(
                "Candidate promotion requires one clean pinned Git checkout at HEAD",
                ("commit or discard author checkout changes, then scan again",),
            ),
        )
    source_alias = SourceAlias(request.candidate_source_alias)
    target_registry = SourceAlias(request.target_registry_alias)
    try:
        configured = ConfiguredSource(
            source_alias,
            SourceKind.SOURCE_LOCAL,
            checkout,
            None,
            True,
        )
        acquired = read_local_snapshot(
            LocalSnapshotRequest(
                source_instance_id(configured),
                source_alias,
                checkout,
                SnapshotLimits(),
            )
        )
    except ValueError as error:
        return _emit_error(request, "promote", _error(str(error), _READ_THE_ACTIONS))
    if isinstance(acquired, Err):
        return _emit_error(request, "promote", acquired)
    pinned_revision = revision.stdout.strip()
    compiled = compile_author_snapshot(
        acquired.value.snapshot,
        source_alias=source_alias,
        source=request.candidate_source_url,
        revision=pinned_revision,
    )
    if isinstance(compiled, Err):
        return _emit_error(request, "promote", compiled)
    scanned = reconcile_source_scan(
        source_alias,
        pinned_revision,
        compiled.value,
        previous=(),
        approved=approved.value,
        target_registry=target_registry,
    )
    if isinstance(scanned, Err):
        return _emit_error(request, "promote", scanned)
    by_id = {item.candidate.id.value: item for item in scanned.value.active}
    if not set(request.promotion_candidate_ids) <= set(by_id):
        return _emit_error(
            request,
            "promote",
            _error(
                "one or more selected Candidate IDs no longer match the pinned Source Scan",
                (
                    "use `aart registry scan --help`, run a fresh scan with explicit boundaries, "
                    "and review the current Candidate IDs",
                ),
            ),
        )
    selected: list[CandidateBundle] = []
    for candidate_id in sorted(request.promotion_candidate_ids):
        bundle = by_id[candidate_id]
        candidate = bundle.candidate
        if candidate.state in {CandidateState.NEW, CandidateState.CHANGED}:
            candidate = assess_candidate(candidate)
        if candidate.state not in {CandidateState.READY, CandidateState.WARNING}:
            return _emit_error(
                request,
                "promote",
                _error(
                    f"Candidate {candidate.id} is {candidate.state.value} and cannot be promoted",
                    ("resolve validation/policy findings and run Source Scan again",),
                ),
            )
        selected.append(CandidateBundle(candidate, bundle.artifact))
    evidence = tuple(
        (
            item.candidate.id,
            PromotionEvidence(validation_report.value, policy_result.value),
        )
        for item in selected
    )
    planned = plan_bulk_promotion(
        registry_snapshot.value,
        tuple(selected),
        evidence=evidence,
        approved=approved.value,
        mode=mode,
    )
    if isinstance(planned, Err):
        return _emit_error(request, "promote", planned)
    plan = planned.value
    changes = [
        {"path": str(item.path), "status": item.kind.value}
        for item in plan.changes
        if item.kind.value != "unchanged"
    ]
    if not request.yes:
        if request.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "operation": "registry.promote",
                        "phase": "review",
                        "applied": False,
                        "candidate_ids": list(sorted(request.promotion_candidate_ids)),
                        "mode": plan.mode.value,
                        "review_digest": str(plan.review_digest),
                        "registry_snapshot_before": str(plan.expected_registry_snapshot),
                        "registry_snapshot_after": str(plan.next_registry_snapshot),
                        "changes": changes,
                        "commit": False,
                        "push": False,
                    },
                    indent=2,
                )
            )
        else:
            print(f"Promotion review: {len(selected)} Candidate(s), mode={plan.mode.value}")
            print(f"review digest: {plan.review_digest}")
            for item in changes:
                print(f"  {item['status']:>7}  {item['path']}")
            print("Reviewed only. Re-run with --yes to promote locally; no commit or push.")
        return _common.OK
    applied = finalize_promotion(plan, plan.review_digest, output=output)
    if isinstance(applied, Err):
        return _emit_error(request, "promote", applied)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": "registry.promote",
                    "phase": "promoted-local",
                    "applied": True,
                    "candidate_ids": list(sorted(request.promotion_candidate_ids)),
                    "mode": plan.mode.value,
                    "review_digest": str(applied.value.review_digest),
                    "registry_snapshot": str(applied.value.registry_snapshot),
                    "changed_paths": applied.value.changed_paths,
                    "commit": False,
                    "push": False,
                },
                indent=2,
            )
        )
    else:
        print(
            f"Promoted {len(selected)} Candidate(s) locally ({applied.value.changed_paths} paths)."
        )
        print("Not committed. Not pushed. Canonical-branch publication remains external.")
    return _common.OK


def _git(root: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", root, *arguments),
        text=True,
        capture_output=True,
        check=False,
    )


def _git_pending(root: str) -> Result[tuple[tuple[str, str], ...]]:
    result = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if result.returncode != 0:
        return _error(f"git status failed: {result.stderr.strip()}", _READ_THE_ACTIONS)
    records = result.stdout.split("\0")
    changes: list[tuple[str, str]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            return _error("git status returned an invalid record", _READ_THE_ACTIONS)
        status = record[:2].strip() or "??"
        path = record[3:]
        changes.append((status, path))
        if ("R" in status or "C" in status) and index < len(records):
            previous = records[index]
            index += 1
            if previous:
                changes.append(("D", previous))
    return Ok(tuple(sorted(set(changes), key=lambda item: item[1])))


def _publish_subject(root: str, stated: str | None) -> Result[str]:
    if stated is not None:
        if not stated or stated != stated.strip() or "\n" in stated or "\r" in stated:
            return _error("publish commit message must be one non-empty line", _READ_THE_ACTIONS)
        return Ok(stated)
    try:
        with open(os.path.join(root, "aart.index.json"), encoding="utf-8") as stream:
            index = json.load(stream)
        artifacts = len(index.get("artifacts", [])) if isinstance(index, dict) else 0
        collections = len(index.get("collections", [])) if isinstance(index, dict) else 0
    except (OSError, ValueError):
        return Ok("Publish registry")
    subject = f"Publish registry: {artifacts} artifact{'s' if artifacts != 1 else ''}"
    if collections:
        subject += f", {collections} collection{'s' if collections != 1 else ''}"
    return Ok(subject)


def _reviewed_publish_paths(
    review: CurationReview,
    pending: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    by_path = {path: status for status, path in pending}
    for change in review.changes:
        if change.status != "unchanged":
            by_path[change.path] = "planned"
    return tuple((status, path) for path, status in sorted(by_path.items()))


def _run_publish(request: Request) -> int:
    """Finalize one reviewed publisher snapshot, then commit exactly the listed Git worktree."""

    if request.publish_message is not None and (
        not request.publish_message
        or request.publish_message != request.publish_message.strip()
        or "\n" in request.publish_message
        or "\r" in request.publish_message
    ):
        return _emit_error(
            request,
            "publish",
            _error("publish commit message must be one non-empty line", _READ_THE_ACTIONS),
        )
    curation_request = _curation_request(request, CurationAction.PUBLISH)
    if isinstance(curation_request, Err):
        return _emit_error(request, "publish", curation_request)
    root = _root(request)
    if _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return _emit_error(
            request,
            "publish",
            _error("registry publish requires a Git checkout", _INITIALIZE),
        )
    service = load_local_curation_service(root)
    if isinstance(service, Err):
        return _emit_error(request, "publish", service)
    prepared = service.value.prepare(curation_request.value)
    if isinstance(prepared, Err):
        return _emit_error(request, "publish", prepared)
    review = prepared.value.review
    before = _git_pending(root)
    if isinstance(before, Err):
        return _emit_error(request, "publish", before)
    reviewed_paths = _reviewed_publish_paths(review, before.value)
    if not request.yes:
        subject = request.publish_message or "Publish registry (derived after build)"
        if request.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "operation": "registry.publish",
                        "phase": "review",
                        "review": _curation_review_data(review),
                        "commit": {
                            "subject": subject,
                            "paths": [
                                {"status": status, "path": path} for status, path in reviewed_paths
                            ],
                            "push": False,
                        },
                    },
                    indent=2,
                )
            )
        else:
            _emit_curation_review(request, review)
            print(f"\n{len(reviewed_paths)} paths would be committed:")
            for status, path in reviewed_paths:
                print(f"  {status:>7}  {path}")
            print(f"subject: {subject}")
            print("Reviewed only. Re-run with --yes to write, validate, audit, and commit.")
        return _common.OK
    finalized = service.value.finalize(prepared.value, review.review_digest)
    if isinstance(finalized, Err):
        return _emit_error(request, "publish", finalized)
    pending = _git_pending(root)
    if isinstance(pending, Err):
        return _emit_error(request, "publish", pending)
    publish_subject = _publish_subject(root, request.publish_message)
    if isinstance(publish_subject, Err):
        return _emit_error(request, "publish", publish_subject)
    if not pending.value:
        if request.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "operation": "registry.publish",
                        "phase": "finalized",
                        "review": _curation_review_data(review),
                        "outcome": _curation_outcome_data(finalized.value),
                        "commit": None,
                    },
                    indent=2,
                )
            )
        else:
            _emit_curation_finalization(request, review, finalized.value)
            print("\nnothing changed; there is nothing to commit")
        return _common.OK
    added = _git(root, "add", "-A")
    if added.returncode != 0:
        return _emit_error(
            request,
            "publish",
            _error(f"git add failed: {added.stderr.strip()}", _READ_THE_ACTIONS),
        )
    committed = _git(root, "commit", "-m", publish_subject.value)
    if committed.returncode != 0:
        return _emit_error(
            request,
            "publish",
            _error(
                f"git commit failed: {committed.stderr.strip() or committed.stdout.strip()}",
                _READ_THE_ACTIONS,
            ),
        )
    revision = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": "registry.publish",
                    "phase": "finalized",
                    "review": _curation_review_data(review),
                    "outcome": _curation_outcome_data(finalized.value),
                    "commit": {
                        "revision": revision,
                        "subject": publish_subject.value,
                        "paths": [
                            {"status": status, "path": path} for status, path in pending.value
                        ],
                        "push": False,
                    },
                },
                indent=2,
            )
        )
    else:
        _emit_curation_finalization(request, review, finalized.value)
        print(f"\ncommitted {len(pending.value)} paths:")
        for status, path in pending.value:
            print(f"  {status:>7}  {path}")
        print(f"committed {revision}: {publish_subject.value}")
        print("Not pushed.")
    return _common.OK


_NAME_THE_SCAN = (
    "name the repository to look at: `aart registry adopt --source DIR --url URL --ref REF`",
)
_NAME_THE_ADOPTED = (
    "name one adopted artifact, as `KIND/NAME@VERSION`; `aart registry adopt` without "
    "`--artifact` lists what a repository declares",
)


def _scanned_artifact_data(item: ScannedArtifact) -> dict[str, object]:
    return {
        "coordinate": item.coordinate,
        "kind": item.kind,
        "name": item.name,
        "version": item.version,
        "summary": item.summary,
        "manifest_path": item.manifest_path,
        "input_digest": item.input_digest,
        "state": item.state,
        "adoptable": item.adoptable,
        "payload_paths": list(item.payload_paths),
    }


def _prepared_adoption_data(prepared: PreparedAdoption) -> dict[str, object]:
    return {
        "url": prepared.url,
        "ref": prepared.ref,
        "resolved_commit": prepared.commit,
        "selected": list(prepared.selected),
        "review_digest": prepared.review_digest,
        "changes": list(prepared.changed_paths),
    }


def _scan_data(scan: RepositoryScan) -> dict[str, object]:
    return {
        "url": scan.url,
        "ref": scan.ref,
        "resolved_commit": scan.commit,
        "registry_alias": scan.registry_alias,
        "manifest_count": scan.manifest_count,
        "artifacts": [
            _scanned_artifact_data(item)
            for item in sorted(scan.artifacts, key=lambda item: item.coordinate)
        ],
    }


def _print_scan(scan: RepositoryScan) -> None:
    print(f"{scan.url} at {scan.ref} ({scan.commit})")
    print(f"{scan.manifest_count} declared manifest(s); nothing was written and no Source saved")
    for item in sorted(scan.artifacts, key=lambda entry: entry.coordinate):
        mark = " " if item.adoptable else "!"
        print(f"  {mark} {item.state:>8}  {item.coordinate}  {item.manifest_path}")


def _print_adoption(prepared: PreparedAdoption, *, applied: bool) -> None:
    print(f"{prepared.url} at {prepared.ref} ({prepared.commit})")
    for coordinate in prepared.selected:
        print(f"  adopt  {coordinate}")
    print(f"review digest: {prepared.review_digest}")
    for path in prepared.changed_paths:
        print(f"  {path}")
    if applied:
        print("Written to the registry checkout. Not committed, not pushed, not merged.")
    else:
        print("Review only; nothing was written. Add `--yes` to apply exactly this transaction.")


def _run_adopt(request: Request) -> int:
    """Scan one repository that is not a Source, then review or apply a selection (`B-095`)."""

    if request.source_dir is None or request.native_url is None or request.ref is None:
        return _emit_error(
            request, "adopt", _error("adoption needs a registry, a URL and a ref", _NAME_THE_SCAN)
        )
    scanned = scan_repository(url=request.native_url, ref=request.ref, registry_root=_root(request))
    if isinstance(scanned, Err):
        return _emit_error(request, "adopt", scanned)
    selected = tuple(request.names)
    if not selected:
        # Scanning is the whole command when nothing is selected: an operator has to be able to see
        # what a repository declares before naming any of it, and looking is not adopting.
        if request.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "operation": "registry.adopt",
                        "phase": "scan",
                        "applied": False,
                        **_scan_data(scanned.value),
                        "selected": [],
                    },
                    indent=2,
                )
            )
        else:
            _print_scan(scanned.value)
        return _common.OK
    prepared = prepare_adoption(scanned.value, selected, registry_root=_root(request))
    if isinstance(prepared, Err):
        return _emit_error(request, "adopt", prepared)
    digest = prepared.value.review_digest
    if request.expect is not None and request.expect != digest:
        return _emit_error(
            request,
            "adopt",
            _error(
                f"the adoption changed since it was reviewed: expected {request.expect}, "
                f"recomputed {digest}",
                ("review the repository again, then finalize the digest that review reports",),
            ),
        )
    if not request.yes:
        if request.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "operation": "registry.adopt",
                        "phase": "review",
                        "applied": False,
                        **_prepared_adoption_data(prepared.value),
                    },
                    indent=2,
                )
            )
        else:
            _print_adoption(prepared.value, applied=False)
        return _common.OK
    applied = apply_adoption(prepared.value, digest, registry_root=_root(request))
    if isinstance(applied, Err):
        return _emit_error(request, "adopt", applied)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": "registry.adopt",
                    "phase": "adopted-local",
                    "applied": True,
                    **_prepared_adoption_data(prepared.value),
                },
                indent=2,
            )
        )
    else:
        _print_adoption(prepared.value, applied=True)
    return _common.OK


def _upstream_check_data(check: AdoptionUpstreamCheck, *, applied: bool) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ok": True,
        "operation": "registry.check-upstream",
        "coordinate": check.adopted.coordinate,
        "url": check.adopted.url,
        "ref": check.adopted.ref,
        "recorded_commit": check.recorded_commit,
        "resolved_commit": check.resolved_commit,
        "disposition": check.disposition.value,
        "observed_coordinate": check.observed_coordinate,
        "observed_input_digest": check.observed_input_digest,
        "new_version_required": check.new_version_required,
        "details": list(check.details),
        "applied": applied,
        "proposal": (None if check.proposal is None else _prepared_adoption_data(check.proposal)),
    }


def _print_upstream_check(check: AdoptionUpstreamCheck, *, applied: bool) -> None:
    print(f"{check.adopted.coordinate}: {check.disposition.value}")
    print(f"  upstream: {check.adopted.url} at {check.adopted.ref}")
    print(f"  adopted at {check.recorded_commit}; now {check.resolved_commit or 'unresolved'}")
    for detail in check.details:
        print(f"  {detail}")
    if check.new_version_required:
        # The published coordinate is immutable (INV-203). Upstream moved without releasing, so
        # there is nothing to propose: the authors have to version the change themselves.
        print("  upstream changed without a new version; the published copy stays as it is")
    if check.proposal is not None:
        _print_adoption(check.proposal, applied=applied)


def _run_check_upstream(request: Request) -> int:
    """Compare one adopted package with the ref it recorded, and never rewrite it (`B-095`)."""

    if request.source_dir is None or len(request.names) != 1:
        return _emit_error(
            request,
            "check-upstream",
            _error(
                "checking upstream needs a registry and one adopted artifact", _NAME_THE_ADOPTED
            ),
        )
    checked = check_adopted_upstream(request.names[0], registry_root=_root(request))
    if isinstance(checked, Err):
        return _emit_error(request, "check-upstream", checked)
    check = checked.value
    proposal = check.proposal
    if request.expect is not None and (
        proposal is None or request.expect != proposal.review_digest
    ):
        return _emit_error(
            request,
            "check-upstream",
            _error(
                f"upstream no longer proposes the reviewed transaction {request.expect}",
                ("check the artifact upstream again, then finalize the digest it reports",),
            ),
        )
    applied = False
    if request.yes and proposal is not None:
        finalized = apply_adoption(proposal, proposal.review_digest, registry_root=_root(request))
        if isinstance(finalized, Err):
            return _emit_error(request, "check-upstream", finalized)
        applied = True
    if request.json:
        print(json.dumps(_upstream_check_data(check, applied=applied), indent=2))
    else:
        _print_upstream_check(check, applied=applied)
    return _common.OK


def run(request: Request) -> int:
    action = request.registry_action or "unknown"
    workspace = FilesystemRegistryWorkspace(_root(request))
    if action == "init":
        return _run_curation(request, CurationAction.INIT)
    if action == "scaffold":
        return _run_curation(request, CurationAction.SCAFFOLD)
    if action == "collection":
        return _run_curation(request, CurationAction.COLLECTION)
    if action == "scan":
        return _run_scan(request)
    if action == "adopt":
        return _run_adopt(request)
    if action == "check-upstream":
        return _run_check_upstream(request)
    if action == "promote":
        return _run_candidate_promotion(request)
    if action == "discover":
        return _run_discover(request)
    if action == "format":
        return _run_curation(request, CurationAction.FORMAT)
    if action == "promote-native":
        return _run_curation(request, CurationAction.PROMOTE_NATIVE)
    if action == "refresh-native":
        return _run_curation(request, CurationAction.REFRESH_NATIVE)
    if action == "vendor":
        return _run_curation(request, CurationAction.VENDOR)
    if action == "vendor-batch":
        return _run_curation(request, CurationAction.VENDOR_BATCH)
    if action == "revendor":
        return _run_curation(request, CurationAction.REVENDOR)
    if action in {"lock", "build"}:
        return _run_curation(request, CurationAction(action))
    if action == "validate":
        return _run_validate(request, workspace)
    if action == "audit":
        return _run_audit(request, workspace)
    if action == "publish":
        return _run_publish(request)
    if action == "test":
        return _run_test(request, workspace)
    if action == "diff":
        return _run_curation(request, CurationAction.DIFF)
    return _emit_error(request, action, _error("unknown registry action", _READ_THE_ACTIONS))
