"""Maintainer registry commands over pure plans and reviewed filesystem effects."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import cast, get_args

from aart_cli import command_outcome as _common
from aart_cli.application.candidate_validation import validate_candidate
from aart_cli.application.maintainer import CandidateBundle, reconcile_source_scan
from aart_cli.application.maintainer_promotion import effective_policy_digest, promotion_evidence
from aart_cli.application.promotion import (
    PromotionEvidence,
    PromotionPlan,
    finalize_promotion,
    load_registry_versions,
    plan_bulk_promotion,
)
from aart_cli.application.registry_collections import (
    collection_validation_digest,
    plan_collection_definition,
)
from aart_cli.application.registry_versions import ApprovedRegistryVersions
from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.curation.model import (
    DEFAULT_MAXIMUM_AART,
    DEFAULT_MINIMUM_AART,
    CurationAction,
    CurationOutcome,
    CurationRequest,
    CurationReview,
    render_curation_outcome,
    render_curation_review,
)
from aart_cli.domain.candidates import CandidateState, assess_candidate
from aart_cli.domain.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    Severity,
    diagnostic_to_data,
)
from aart_cli.domain.identifiers import ArtifactIdentity, ArtifactKind, SourceAlias
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.registry import RegistryArtifactVersion, RegistryContentMode
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.io.curation_runtime import (
    load_local_curation_service,
)
from aart_cli.io.git import GitProcessRequest, run_git_process
from aart_cli.io.registry_adoption import (
    AdoptionUpstreamCheck,
    PreparedAdoption,
    RepositoryScan,
    ScannedArtifact,
    apply_adoption,
    check_adopted_upstream,
    prepare_adoption,
    scan_repository,
)
from aart_cli.io.registry_promotion import FilesystemPromotionOutput
from aart_cli.io.registry_publication import publish_registry_commit
from aart_cli.io.registry_workspace import (
    FilesystemRegistryWorkspace,
    read_registry_workspace,
)
from aart_cli.io.working_tree import read_working_tree
from aart_cli.model import Request
from aart_cli.protocol.authoring import compile_author_snapshot
from aart_cli.protocol.hashing import parse_sha256
from aart_cli.protocol.native_tree import SnapshotEntryKind, SourceSnapshot
from aart_cli.protocol.registry_models import RegistryManifest
from aart_cli.protocol.registry_schema import parse_registry_manifest
from aart_cli.protocol.semver import SemVer, parse_semver
from aart_cli.registry_commands.model import RegistryQualityReport
from aart_cli.registry_commands.planning import (
    audit_registry_workspace,
    test_registry_compatibility,
    validate_registry_workspace,
)
from aart_cli.registry_commands.publication_state import (
    prepare_registry_publication,
    publication_summary,
)
from aart_cli.registry_maintenance.promoted import (
    is_promoted_registry,
    legacy_registry_paths,
)
from aart_cli.runtime_contract import EXECUTABLE_CAPABILITIES, EXECUTABLE_VERSION
from aart_cli.sources.model import LocalSnapshotRequest, SnapshotLimits, source_instance_id

_VERSION = EXECUTABLE_VERSION
_CAPABILITIES = EXECUTABLE_CAPABILITIES
REGISTRY_COMMAND_INVALID = DiagnosticCode("registry-command-invalid")


# What an operator does next after this module refuses. The planning module carries the
# same idea for the refusals it raises; these are the ones raised before planning is reached, where
# the problem is the invocation rather than the workspace.
_READ_THE_ACTIONS = ("`aart-cli maintain registry --help` lists the actions this command accepts",)
_NAME_THE_ARTIFACT = (
    "name exactly one artifact kind and name, in the form the action's own `--help` shows",
)
_INITIALIZE = (
    "point `--source` at a registry checkout, or create one with "
    "`aart-cli maintain registry init --source-id SLUG --display-name NAME --yes`",
)
_STATE_THE_RELEASE = (
    "state the release to test against: `aart-cli maintain registry test --latest-version VERSION`",
)
_MINIMUM_VERSION = (
    "record a minimum AART version in `aart-cli-registry.json` — `requires_aart.min_inclusive` — then "
    "`aart-cli maintain registry test`",
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
    try:
        return Ok(
            CurationRequest(
                action,
                _root(request),
                source_id=request.source_id,
                display_name=request.display_name,
                # Only `init` declares a compatibility window, and only `init` reads one
                # back, so every other action arrives here with both unset.  The substitute has to
                # be the window of the AART that is running; a literal would bind a registry to the
                # release it was typed in.
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
        # A failed check counts as drift, so a check that wrote nothing still exits nonzero.
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
            # The JSON envelope carries remediation through `diagnostic_to_data`, and the text
            # renderer must not drop it. A report is where `validate` and `audit` state a refusal, so it renders the next step
            # exactly as `_emit_error` does.
            for remediation in diagnostic.remediation:
                print(f"    remediation: {remediation}")


def _snapshot(workspace: FilesystemRegistryWorkspace) -> Result[SourceSnapshot]:
    return workspace.snapshot()


def _canonical_snapshot(workspace: FilesystemRegistryWorkspace) -> Result[SourceSnapshot]:
    current = _snapshot(workspace)
    if isinstance(current, Err):
        return current
    retired = legacy_registry_paths(current.value)
    if retired:
        return _error(
            "registry maintenance found the retired authoring-workspace representation: "
            + ", ".join(retired),
            (
                "author artifacts in a Source checkout, then use registry scan and promote; "
                "canonical Registry maintenance does not read entries, aart.lock.json, "
                "aart.index.json, or unversioned artifact packages",
            ),
        )
    if not is_promoted_registry(current.value):
        return _error(
            "registry maintenance requires the canonical approved-Registry representation",
            _INITIALIZE,
        )
    return current


def _run_validate(request: Request, workspace: FilesystemRegistryWorkspace) -> int:
    current = _canonical_snapshot(workspace)
    if isinstance(current, Err):
        return _emit_error(request, "validate", current)
    checked = validate_registry_workspace(
        current.value,
        executable_version=_VERSION,
        available_capabilities=_CAPABILITIES,
    )
    if isinstance(checked, Err):
        return _emit_error(request, "validate", checked)
    _emit_report(request, "validate", checked.value)
    return _common.OK if checked.value.passed else _common.ERROR


def _run_audit(request: Request, workspace: FilesystemRegistryWorkspace) -> int:
    current = _canonical_snapshot(workspace)
    if isinstance(current, Err):
        return _emit_error(request, "audit", current)
    checked = audit_registry_workspace(
        current.value,
        executable_version=_VERSION,
        available_capabilities=_CAPABILITIES,
        for_default_branch=request.for_default_branch,
    )
    if isinstance(checked, Err):
        return _emit_error(request, "audit", checked)
    _emit_report(request, "audit", checked.value)
    return _common.OK if checked.value.passed else _common.ERROR


def _registry_manifest(snapshot: SourceSnapshot) -> Result[RegistryManifest]:
    for item in snapshot.entries:
        if str(item.path) == "aart-cli-registry.json" and item.kind is SnapshotEntryKind.FILE:
            return parse_registry_manifest(item.content)
    return _error("registry workspace requires aart-cli-registry.json", _INITIALIZE)


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
                "Upstream scan requires one clean pinned Git checkout at HEAD",
                (
                    "commit or discard author checkout changes; `aart-cli maintain upstream scan --help` "
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
        acquired = read_working_tree(
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
    approved: tuple[RegistryArtifactVersion, ...] = ()
    if request.source_dir is not None:
        registry_snapshot = FilesystemRegistryWorkspace(_root(request)).snapshot()
        if isinstance(registry_snapshot, Err):
            return _emit_error(request, "scan", registry_snapshot)
        loaded_versions = load_registry_versions(registry_snapshot.value)
        if isinstance(loaded_versions, Err):
            return _emit_error(request, "scan", loaded_versions)
        approved = loaded_versions.value
    compiled = compile_author_snapshot(
        acquired.value.snapshot,
        source_alias=source_alias,
        source=request.candidate_source_url,
        revision=pinned_revision,
        versions=ApprovedRegistryVersions(approved, target_registry),
    )
    if isinstance(compiled, Err):
        return _emit_error(request, "scan", compiled)
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
        print(f"Upstream scan {source_alias.value}@{pinned_revision}")
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
    try:
        mode = RegistryContentMode(request.content_mode)
    except ValueError:
        return _emit_error(
            request,
            "promote",
            _error("content mode must be self-contained or pinned-reference", _READ_THE_ACTIONS),
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
        acquired = read_working_tree(
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
        versions=ApprovedRegistryVersions(approved.value, target_registry),
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
                "one or more selected Candidate IDs no longer match the pinned Upstream scan",
                (
                    "use `aart-cli maintain upstream scan --help`, run a fresh scan with explicit boundaries, "
                    "and review the current Candidate IDs",
                ),
            ),
        )
    # The evidence is the run AART does here, against the same policy the Maintainer screens judge
    # with, so nothing a caller types can stand in for it and each Candidate records its own (D-387).
    policy = EffectivePolicy()
    selected: list[CandidateBundle] = []
    evidence_by_candidate: list[tuple[CandidateBundle, PromotionEvidence]] = []
    for candidate_id in sorted(request.promotion_candidate_ids):
        bundle = by_id[candidate_id]
        validation = validate_candidate(bundle, policy=policy)
        candidate = assess_candidate(
            bundle.candidate,
            findings=validation.findings,
            manual_approval_required=validation.manual_approval_required,
        )
        if validation.state not in {CandidateState.READY, CandidateState.WARNING} or (
            candidate.state not in {CandidateState.READY, CandidateState.WARNING}
        ):
            return _emit_error(
                request,
                "promote",
                _error(
                    f"Candidate {candidate.id} is {validation.state.value} and cannot be promoted",
                    (
                        "open the Candidate's validation in the Maintainer screens to see each "
                        "failing check, fix the author manifest, commit it and run Upstream scan again",
                    ),
                ),
            )
        recorded = promotion_evidence(validation, policy)
        if isinstance(recorded, Err):
            return _emit_error(request, "promote", recorded)
        reviewed = CandidateBundle(candidate, bundle.artifact)
        selected.append(reviewed)
        evidence_by_candidate.append((reviewed, recorded.value))
    evidence = tuple((item.candidate.id, record) for item, record in evidence_by_candidate)
    stated_evidence = [
        {
            "candidate_id": item.candidate.id.value,
            "artifact": str(item.candidate.artifact.coordinate),
            "validation_report_digest": str(record.validation_report_digest),
            "effective_policy_digest": str(record.effective_policy_digest),
            "warnings": list(record.warnings),
        }
        for item, record in evidence_by_candidate
    ]
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
                        "evidence": stated_evidence,
                        "collections": _collection_versions(plan),
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
            for stated in stated_evidence:
                print(f"  {stated['artifact']}  {stated['candidate_id']}")
                print(f"    validation report: {stated['validation_report_digest']}")
                print(f"    effective policy:  {stated['effective_policy_digest']}")
                for warning in stated["warnings"]:
                    print(f"    warning: {warning}")
            for coordinate in _collection_versions(plan):
                print(f"  {coordinate}  next Collection version: a member moved")
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


def _collection_versions(plan: PromotionPlan) -> list[str]:
    """The Collection versions a planned transaction publishes, a promoted member's bumps included."""

    return sorted(
        str(item.coordinate)
        for item in plan.versions
        if str(item.coordinate.artifact.kind) == "collection"
    )


def _collection_member(raw: str) -> ArtifactIdentity | None:
    kind, _, name = raw.partition("/")
    if kind not in get_args(ArtifactKind) or kind == "collection" or not name:
        return None
    try:
        return ArtifactIdentity(cast(ArtifactKind, kind), name)
    except ValueError:
        return None


def _run_collection(request: Request) -> int:
    """Define a Collection from approved artifacts as one reviewed Registry transaction (D-430)."""

    (name,) = request.names
    members = tuple(_collection_member(raw) for raw in request.collection_members)
    if any(item is None for item in members):
        return _emit_error(
            request,
            "collection",
            _error(
                "each --include must name an artifact as KIND/NAME",
                ("name approved artifacts, for example `--include mcp/notes`",),
            ),
        )
    output = FilesystemPromotionOutput(_root(request))
    registry_snapshot = output.current()
    if isinstance(registry_snapshot, Err):
        return _emit_error(request, "collection", registry_snapshot)
    approved = load_registry_versions(registry_snapshot.value)
    if isinstance(approved, Err):
        return _emit_error(request, "collection", approved)
    registries = {item.coordinate.source for item in approved.value}
    if len(registries) != 1:
        return _emit_error(
            request,
            "collection",
            _error(
                "a Collection is made of artifacts this Registry approved, and it has none",
                ("approve its members first; see `aart-cli maintain candidate promote --help`",),
            ),
        )
    (target_registry,) = registries
    defined = plan_collection_definition(
        approved.value,
        registry_snapshot.value,
        target_registry=target_registry,
        name=name,
        summary=request.summary,
        members=tuple(item for item in members if item is not None),
    )
    if isinstance(defined, Err):
        return _emit_error(request, "collection", defined)
    if defined.value is None:
        if request.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "operation": "registry.collection",
                        "phase": "unchanged",
                        "applied": False,
                        "collection": name,
                    },
                    indent=2,
                )
            )
        else:
            print(f"Collection {name} already has these members and summary; nothing to publish.")
        return _common.OK
    change = defined.value
    policy = EffectivePolicy()
    planned = plan_bulk_promotion(
        registry_snapshot.value,
        (),
        evidence=(
            (
                change.id,
                PromotionEvidence(
                    collection_validation_digest(change), effective_policy_digest(policy)
                ),
            ),
        ),
        approved=approved.value,
        collections=(change,),
    )
    if isinstance(planned, Err):
        return _emit_error(request, "collection", planned)
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
                        "operation": "registry.collection",
                        "phase": "review",
                        "applied": False,
                        "collection": change.coordinate,
                        "summary": change.summary,
                        "members": [str(item) for item in change.members],
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
            print(f"Collection review: {change.coordinate}")
            print(f"  {change.summary}")
            for member in change.members:
                print(f"  member {member}")
            print(f"review digest: {plan.review_digest}")
            for item in changes:
                print(f"  {item['status']:>7}  {item['path']}")
            print("Reviewed only. Re-run with --yes to publish locally; no commit or push.")
        return _common.OK
    applied = finalize_promotion(plan, plan.review_digest, output=output)
    if isinstance(applied, Err):
        return _emit_error(request, "collection", applied)
    if request.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "operation": "registry.collection",
                    "phase": "published-local",
                    "applied": True,
                    "collection": change.coordinate,
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
        print(f"Published {change.coordinate} locally ({applied.value.changed_paths} paths).")
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
        with open(os.path.join(root, "registry", "index.json"), encoding="utf-8") as stream:
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
    "name the repository to look at: `aart-cli maintain upstream adopt --source DIR --url URL --ref REF`",
)
_NAME_THE_ADOPTED = (
    "name one adopted artifact, as `KIND/NAME@VERSION`; "
    "`aart-cli maintain upstream adopt --source DIR --url URL --ref REF` without `--artifact` lists what a "
    "repository declares",
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
        "held_by": list(item.held_by),
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
        if item.held_by:
            print(
                f"             this Registry took {item.kind}/{item.name} from "
                f"{', '.join(item.held_by)}; adopt it with --rename "
                f"{item.kind}/{item.name}=NEW-NAME"
            )


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
    renames = tuple(
        (identity, name)
        for identity, _equals, name in (item.partition("=") for item in request.adoption_renames)
    )
    if any(not identity or not name for identity, name in renames):
        return _emit_error(
            request,
            "adopt",
            _error(
                "a new Registry name is given as KIND/NAME=NEW-NAME",
                ("for example --rename skill/brainstorming=brainstorming-official",),
            ),
        )
    prepared = prepare_adoption(
        scanned.value, selected, registry_root=_root(request), renames=renames
    )
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


def _run_push(request: Request) -> int:
    """Publish the commit this checkout is on, to a branch that is not the one people read.

    The revision is resolved here rather than carried as `HEAD`: `RegistryPublicationCommand`
    refuses a moving name on purpose, because the whole point is that the bytes pushed are the
    bytes reviewed. Resolving it at the surface and passing the result is the honest reading of
    "the commit AART just made for you".
    """

    root = _root(request)
    readiness = read_registry_workspace(root)
    if readiness is None:
        return _emit_error(
            request,
            "push",
            _error(
                "push requires the canonical Registry at the exact worktree root",
                ("Run Push from the root of the Registry checkout.",),
            ),
        )
    if not readiness.push_ready:
        return _emit_error(
            request,
            "push",
            _error(
                "Registry Push is unavailable: " + "; ".join(readiness.push_blockers),
                ("Resolve every listed publication blocker, then review Push again.",),
            ),
        )
    branch = request.publication_branch or ""
    current_is_target = readiness.branch not in {None, "main", readiness.default_branch}
    if current_is_target and branch != readiness.branch:
        return _emit_error(
            request,
            "push",
            _error(
                f"this Registry commit belongs to its current branch {readiness.branch}",
                (f"Push to {readiness.branch}; AART does not redirect it to another branch.",),
            ),
        )
    if readiness.revision is None or readiness.publication_review_digest is None:
        return _emit_error(
            request,
            "push",
            _error(
                "Registry Push has no exact reviewed commit",
                ("Review Push again after the Registry publication gates pass.",),
            ),
        )
    review_digest = parse_sha256(readiness.publication_review_digest)
    if isinstance(review_digest, Err):
        return _emit_error(request, "push", review_digest)
    prepared = prepare_registry_publication(
        registry=SourceAlias(os.path.basename(root) or "registry"),
        remote=request.publication_remote,
        default_branch=readiness.default_branch,
        requested_branch=branch,
        revision=readiness.revision,
        review_digest=review_digest.value,
    )
    if isinstance(prepared, Err):
        return _emit_error(request, "push", prepared)
    repeated = read_registry_workspace(root)
    if (
        repeated is None
        or not repeated.push_ready
        or any(
            before != after
            for before, after in (
                (readiness.root, repeated.root if repeated else None),
                (readiness.revision, repeated.revision if repeated else None),
                (readiness.content_digest, repeated.content_digest if repeated else None),
                (
                    readiness.publication_review_digest,
                    repeated.publication_review_digest if repeated else None,
                ),
            )
        )
    ):
        blockers = () if repeated is None else repeated.push_blockers
        return _emit_error(
            request,
            "push",
            _error(
                "Registry Push readiness changed after review"
                + (": " + "; ".join(blockers) if blockers else ""),
                ("Review the current Registry state and prepare Push again.",),
            ),
        )
    published = publish_registry_commit(root, prepared.value)
    if isinstance(published, Err):
        return _emit_error(request, "push", published)
    if request.json:
        receipt = published.value
        print(
            json.dumps(
                {
                    "action": "push",
                    "registry": receipt.registry.value,
                    "remote": receipt.remote,
                    "branch": receipt.branch.value,
                    "revision": receipt.revision,
                    "outcome": receipt.outcome.value,
                },
                indent=2,
            )
        )
    else:
        for line in publication_summary(published.value):
            print(line)
    return _common.OK


def _configured_registry_branch(request: Request) -> str:
    """The branch a subscriber of this registry reads, which is the one publication may never be.

    Read from the checkout's own remote HEAD when it can be, because that is what the remote
    itself calls default. The adapter checks it again for the same reason; this makes the refusal
    reachable before a remote is contacted at all when the answer is already known locally.
    """

    root = _root(request)
    shown = run_git_process(
        GitProcessRequest(
            (
                "git",
                "-C",
                root,
                "symbolic-ref",
                "--short",
                f"refs/remotes/{request.publication_remote}/HEAD",
            ),
            root,
            30.0,
            256,
        )
    )
    if isinstance(shown, Ok):
        named = shown.value.stdout.decode("utf-8", errors="replace").strip()
        prefix = f"{request.publication_remote}/"
        if named.startswith(prefix):
            return named[len(prefix) :]
    current = run_git_process(
        GitProcessRequest(("git", "-C", root, "branch", "--show-current"), root, 30.0, 256)
    )
    if isinstance(current, Ok):
        branch = current.value.stdout.decode("utf-8", errors="replace").strip()
        if branch:
            return branch
    return "main"


def run(request: Request) -> int:
    action = request.registry_action or "unknown"
    workspace = FilesystemRegistryWorkspace(_root(request))
    if action == "init":
        return _run_curation(request, CurationAction.INIT)
    if action == "collection":
        return _run_collection(request)
    if action == "scan":
        return _run_scan(request)
    if action == "adopt":
        return _run_adopt(request)
    if action == "check-upstream":
        return _run_check_upstream(request)
    if action == "promote":
        return _run_candidate_promotion(request)
    if action == "format":
        return _run_curation(request, CurationAction.FORMAT)
    if action in {"lock", "build"}:
        return _run_curation(request, CurationAction(action))
    if action == "validate":
        return _run_validate(request, workspace)
    if action == "audit":
        return _run_audit(request, workspace)
    if action == "publish":
        return _run_publish(request)
    if action == "push":
        return _run_push(request)
    if action == "test":
        return _run_test(request, workspace)
    if action == "diff":
        return _run_curation(request, CurationAction.DIFF)
    return _emit_error(request, action, _error("unknown registry action", _READ_THE_ACTIONS))
