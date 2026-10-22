"""Local checkout adapter for canonical, digest-bound Maintainer curation."""

from __future__ import annotations

import os
import shlex
import tempfile
from dataclasses import dataclass
from typing import Protocol

from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.curation.model import (
    CurationAction,
    CurationChange,
    CurationCheck,
    CurationOutcome,
    CurationOutcomeStatus,
    CurationRequest,
    CurationReview,
    curation_review_digest,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import ObjectDigest, SourceAlias
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.io.git_acquisition import acquire_git_snapshot, commit_on_default_branch
from aart_cli.io.registry_workspace import FilesystemRegistryWorkspace
from aart_cli.protocol.native_tree import SnapshotEntryKind, SourceSnapshot
from aart_cli.protocol.semver import SemVer, parse_semver
from aart_cli.registry_commands.model import (
    RegistryInitOptions,
    RegistryOperation,
    RegistryQualityReport,
    RegistryWorkspacePlan,
)
from aart_cli.registry_commands.planning import (
    audit_registry_workspace,
    plan_promoted_registry_build,
    plan_registry_format,
    plan_registry_workspace_files,
    validate_registry_workspace,
)
from aart_cli.registry_commands.publication_state import prepare_registry_publication_state
from aart_cli.registry_commands.workspace import (
    finalize_registry_workspace,
    prepare_registry_init,
)
from aart_cli.registry_maintenance.model import (
    NativeReferenceAcquisition,
)
from aart_cli.registry_maintenance.promoted import (
    is_promoted_registry,
    legacy_registry_paths,
)
from aart_cli.runtime_contract import EXECUTABLE_CAPABILITIES, EXECUTABLE_VERSION
from aart_cli.sources.model import (
    GitSnapshotRequest,
    SnapshotLimits,
    SourceCandidate,
    source_instance_id,
    source_snapshot_digest,
)

_VERSION = EXECUTABLE_VERSION
_CAPABILITIES = EXECUTABLE_CAPABILITIES
CURATION_INVALID = DiagnosticCode("curation-invalid")
CURATION_STALE = DiagnosticCode("curation-stale")


@dataclass(frozen=True, slots=True)
class _ReadOnlyPrepared:
    snapshot: SourceSnapshot
    checks: tuple[CurationCheck, ...]


@dataclass(frozen=True, slots=True)
class PreparedCuration:
    review: CurationReview
    payload: RegistryWorkspacePlan | _ReadOnlyPrepared | SourceSnapshot


class CurationService(Protocol):
    def prepare(self, request: CurationRequest) -> Result[PreparedCuration]: ...

    def finalize(
        self,
        prepared: PreparedCuration,
        reviewed_digest: ObjectDigest,
    ) -> Result[CurationOutcome]: ...


def _error(message: str, *, stale: bool = False, remediation: tuple[str, ...] = ()) -> Err:
    return Err(
        (
            Diagnostic(
                CURATION_STALE if stale else CURATION_INVALID,
                Severity.ERROR,
                message,
                remediation=remediation,
            ),
        )
    )


def _legacy_workspace_files(snapshot: SourceSnapshot) -> tuple[str, ...]:
    return legacy_registry_paths(snapshot)


def _semver(raw: str, label: str) -> Result[SemVer]:
    parsed = parse_semver(raw)
    if isinstance(parsed, Err):
        return _error(f"{label} must be canonical SemVer")
    return parsed


def _snapshot_digest(snapshot: SourceSnapshot) -> Result[ObjectDigest]:
    digest = source_snapshot_digest(snapshot)
    if isinstance(digest, Err):
        return _error("registry workspace snapshot cannot be hashed")
    return digest


def _workspace_changes(plan: RegistryWorkspacePlan) -> tuple[CurationChange, ...]:
    return tuple(CurationChange(str(item.path), item.kind.value) for item in plan.changes)


def _checks(report: RegistryQualityReport) -> tuple[CurationCheck, ...]:
    return tuple(
        CurationCheck(
            item.name,
            item.passed,
            tuple(
                f"{diagnostic.severity.value}: {diagnostic.message}"
                for diagnostic in item.diagnostics
            ),
        )
        for item in report.checks
    )


def _follow_up(
    workspace: str,
    changes: tuple[CurationChange, ...],
    action: CurationAction,
) -> tuple[str, ...]:
    # `QA-014`: this does not lead with `git -C … diff -- <every reviewed path>`, which would repeat
    # the path list the review has just printed and be the longest line in a successful run.
    # `render_curation_review` already closes a mutating action with "AART will not commit or push;
    # review the working-tree diff afterward" — the same instruction, without the repetition and
    # without a shell command, which is also what keeps screen 46 free of one (`QA-017`).
    quoted = shlex.quote(workspace)
    if action is CurationAction.INIT:
        return (
            f"aart-cli maintain registry validate --source {quoted}",
            f"aart-cli maintain registry build --source {quoted}",
            f"aart-cli maintain registry audit --source {quoted}",
        )
    return (
        f"aart-cli maintain registry validate --source {quoted}",
        f"aart-cli maintain registry audit --source {quoted}",
    )


def _candidate(
    location: str,
    ref: str,
    *,
    alias: str,
    allow_local_transport: bool,
) -> Result[tuple[SourceCandidate, bool | None]]:
    """The pinned snapshot, and whether its commit is on the upstream's default branch."""

    with tempfile.TemporaryDirectory(prefix="aart-curation-source-") as temporary:
        configured = ConfiguredSource(
            SourceAlias(alias),
            SourceKind.SOURCE_GIT,
            location,
            ref,
            True,
        )
        request = GitSnapshotRequest(
            source_instance_id(configured),
            configured.alias,
            configured.location,
            ref,
            os.path.join(temporary, "mirror.git"),
            os.path.join(temporary, "tmp"),
            SnapshotLimits(),
            60,
            allow_local_transport,
        )
        acquired = acquire_git_snapshot(request)
        if isinstance(acquired, Err):
            return acquired
        return Ok(
            (
                acquired.value,
                commit_on_default_branch(request, acquired.value.resolved_revision),
            )
        )


def default_native_acquirer(url: str, ref: str) -> Result[NativeReferenceAcquisition]:
    acquired = _candidate(url, ref, alias="curation-native", allow_local_transport=False)
    if isinstance(acquired, Err):
        return acquired
    candidate, default_branch = acquired.value
    try:
        return Ok(
            NativeReferenceAcquisition(
                url,
                ref,
                candidate.resolved_revision,
                candidate.snapshot,
                default_branch=default_branch,
            )
        )
    except ValueError as error:
        return _error(str(error))


class LocalCurationService:
    """Prepare complete reviews and apply only their exact digest to one local checkout."""

    def __init__(self, workspace: str):
        if not os.path.isabs(workspace) or os.path.normpath(workspace) != workspace:
            raise ValueError("curation workspace must be normalized and absolute")
        self.root = workspace
        self.workspace = FilesystemRegistryWorkspace(workspace)

    def _current(self) -> Result[SourceSnapshot]:
        return self.workspace.current()

    def _canonical_current(self) -> Result[SourceSnapshot]:
        current = self._current()
        if isinstance(current, Err):
            return current
        retired = _legacy_workspace_files(current.value)
        if retired:
            return _error(
                "registry maintenance found the retired authoring-workspace representation: "
                + ", ".join(retired),
                remediation=(
                    "author artifacts in a Source checkout, then use registry scan and promote; "
                    "canonical Registry maintenance does not read entries, aart.lock.json, "
                    "aart.index.json, or unversioned artifact packages",
                ),
            )
        if not is_promoted_registry(current.value):
            return _error(
                "registry maintenance requires the canonical approved-Registry representation",
                remediation=(
                    "initialize a canonical Registry or point --source at its local checkout",
                ),
            )
        return current

    def _mutation_target(self) -> Result[None]:
        return self.workspace.verify_mutation_target()

    def _workspace_review(
        self,
        request: CurationRequest,
        plan: RegistryWorkspacePlan,
        *,
        checks: tuple[CurationCheck, ...] = (),
        warnings: tuple[str, ...] = (),
    ) -> PreparedCuration:
        changes = _workspace_changes(plan)
        return PreparedCuration(
            CurationReview(
                request.action,
                self.root,
                True,
                plan.review_digest,
                plan.expected_snapshot_digest,
                changes,
                checks=checks,
                warnings=warnings,
                follow_up_commands=_follow_up(self.root, changes, request.action),
            ),
            plan,
        )

    def _prepare_init(self, request: CurationRequest) -> Result[PreparedCuration]:
        if request.source_id is None or request.display_name is None:
            return _error("init requires source ID and display name")
        minimum = _semver(request.minimum_version, "minimum version")
        maximum = _semver(request.maximum_version, "maximum version")
        if isinstance(minimum, Err):
            return minimum
        if isinstance(maximum, Err):
            return maximum
        try:
            options = RegistryInitOptions(
                request.source_id,
                request.display_name,
                minimum.value,
                maximum.value,
            )
        except ValueError as error:
            return _error(str(error))
        planned = prepare_registry_init(options, output=self.workspace)
        if isinstance(planned, Err):
            return planned
        warnings: tuple[str, ...] = ()
        # Two questions, two homes, and `init` owes the reader both.  *Which* AART is the
        # registry's own decision and is now pinned in a file it can review and revert; *where
        # this deployment gets it from* is a fact about the instance and stays in settings.
        warnings += (
            f"registry CI runs AART {EXECUTABLE_VERSION}, pinned in .aart-cli-version -- bump it in a "
            "pull request and the gates run against the new version before it is merged",
            "where CI fetches that version from is a repository variable, first one set wins: "
            "AART_CLI_PACKAGE (package index), AART_CLI_WHEEL_URL (released wheel), AART_CLI_TOOL_PATH "
            "(already on the runner), then AART_CLI_TOOL_URL (git clone, or AART_CLI_REPOSITORY as "
            "owner/name on this instance). Set none and the first run stops and lists them "
            "rather than guessing; set one on the organisation so it configures every registry "
            "at once",
        )
        return Ok(self._workspace_review(request, planned.value, warnings=warnings))

    def _prepare_format(self, request: CurationRequest) -> Result[PreparedCuration]:
        current = self._canonical_current()
        if isinstance(current, Err):
            return current
        planned = plan_registry_format(current.value)
        if isinstance(planned, Err):
            return planned
        return Ok(self._workspace_review(request, planned.value))

    def _prepare_promoted_lock(
        self,
        request: CurationRequest,
        snapshot: SourceSnapshot,
    ) -> Result[PreparedCuration]:
        """Lock over the approved representation, which has nothing left to resolve.

        A lock pins what authored entries point at, and the approved representation has no authored
        entries: every approval already carries the input, payload, canonical and object digests it
        was reviewed against, and `validate` holds the registry to them. So this reports that and
        writes nothing, rather than manufacturing the older workspace's lock file beside approvals
        that never needed one (`B-057`).
        """

        digest = _snapshot_digest(snapshot)
        if isinstance(digest, Err):
            return digest
        checks = (
            CurationCheck(
                "lock",
                True,
                ("approved versions are pinned by their own records; nothing to resolve",),
            ),
        )
        review_digest = curation_review_digest(request.action, digest.value, (), checks, ())
        return Ok(
            PreparedCuration(
                CurationReview(
                    request.action,
                    self.root,
                    False,
                    review_digest,
                    digest.value,
                    (),
                    checks,
                ),
                _ReadOnlyPrepared(snapshot, checks),
            )
        )

    def _prepare_generated(self, request: CurationRequest) -> Result[PreparedCuration]:
        current = self._canonical_current()
        if isinstance(current, Err):
            return current
        if request.action is CurationAction.LOCK:
            return self._prepare_promoted_lock(request, current.value)
        planned = plan_promoted_registry_build(current.value)
        if isinstance(planned, Err):
            return planned
        return Ok(self._workspace_review(request, planned.value))

    def _prepare_publish(self, request: CurationRequest) -> Result[PreparedCuration]:
        """Use the same complete publication preparation as Push readiness and CI."""

        current = self._canonical_current()
        if isinstance(current, Err):
            return current
        prepared = prepare_registry_publication_state(
            current.value,
            executable_version=_VERSION,
            available_capabilities=_CAPABILITIES,
        )
        if isinstance(prepared, Err):
            return prepared
        failed = tuple(
            detail for gate in prepared.value.gates if not gate.passed for detail in gate.details
        )
        if failed:
            return _error("registry publish gate failed: " + "; ".join(failed))
        touched = {str(change.path) for change in prepared.value.plan.changes}
        files = {
            str(entry.path): entry
            for entry in prepared.value.snapshot.entries
            if entry.kind is SnapshotEntryKind.FILE
        }
        aggregate = plan_registry_workspace_files(
            RegistryOperation.PUBLISH,
            current.value,
            tuple(
                (path, files[path].content, files[path].executable)
                for path in sorted(touched)
                if path in files
            ),
        )
        if isinstance(aggregate, Err):
            return aggregate
        return Ok(
            self._workspace_review(
                request,
                aggregate.value,
                checks=tuple(
                    CurationCheck(gate.name, gate.passed, gate.details)
                    for gate in prepared.value.gates
                ),
                warnings=(
                    "Publish runs the canonical format, lock, build, validation, audit, and compatibility contract over one reviewed snapshot.",
                    "Finalizing commits every listed Git change in the registry checkout and never pushes.",
                ),
            )
        )

    def _prepare_read_only(self, request: CurationRequest) -> Result[PreparedCuration]:
        current = (
            self._canonical_current()
            if request.action in {CurationAction.VALIDATE, CurationAction.AUDIT}
            else self._current()
        )
        if isinstance(current, Err):
            return current
        digest = _snapshot_digest(current.value)
        if isinstance(digest, Err):
            return digest
        changes: tuple[CurationChange, ...] = ()
        checks: tuple[CurationCheck, ...] = ()
        warnings: tuple[str, ...] = ()
        if request.action is CurationAction.VALIDATE:
            report = validate_registry_workspace(
                current.value,
                executable_version=_VERSION,
                available_capabilities=_CAPABILITIES,
            )
            if isinstance(report, Err):
                return report
            checks = _checks(report.value)
        elif request.action is CurationAction.AUDIT:
            report = audit_registry_workspace(
                current.value,
                executable_version=_VERSION,
                available_capabilities=_CAPABILITIES,
            )
            if isinstance(report, Err):
                return report
            checks = _checks(report.value)
            warnings = (
                "Audit reports review, provenance, setup, license, and available security evidence; it is not a safety certificate.",
            )
        else:
            plan = plan_registry_format(current.value)
            if isinstance(plan, Err):
                return plan
            changes = _workspace_changes(plan.value)
        review_digest = curation_review_digest(
            request.action,
            digest.value,
            changes,
            checks,
            warnings,
        )
        review = CurationReview(
            request.action,
            self.root,
            False,
            review_digest,
            digest.value,
            changes,
            checks,
            warnings,
        )
        return Ok(PreparedCuration(review, _ReadOnlyPrepared(current.value, checks)))

    def prepare(self, request: CurationRequest) -> Result[PreparedCuration]:
        if request.workspace != self.root:
            return _error("curation request targets a different workspace")
        mutating = request.action in {
            CurationAction.INIT,
            CurationAction.FORMAT,
            CurationAction.LOCK,
            CurationAction.BUILD,
            CurationAction.PUBLISH,
        }
        if mutating:
            target = self._mutation_target()
            if isinstance(target, Err):
                return target
        if request.action is CurationAction.INIT:
            return self._prepare_init(request)
        if request.action is CurationAction.FORMAT:
            return self._prepare_format(request)
        if request.action in {CurationAction.LOCK, CurationAction.BUILD}:
            return self._prepare_generated(request)
        if request.action is CurationAction.PUBLISH:
            return self._prepare_publish(request)
        return self._prepare_read_only(request)

    def finalize(
        self,
        prepared: PreparedCuration,
        reviewed_digest: ObjectDigest,
    ) -> Result[CurationOutcome]:
        if reviewed_digest != prepared.review.review_digest:
            return _error("reviewed curation digest does not match the prepared action")
        payload = prepared.payload
        if isinstance(payload, RegistryWorkspacePlan):
            workspace_applied = finalize_registry_workspace(
                payload, reviewed_digest, output=self.workspace
            )
            if isinstance(workspace_applied, Err):
                return workspace_applied
            changed = workspace_applied.value.changed_paths
        elif isinstance(payload, _ReadOnlyPrepared):
            current = self._current()
            if isinstance(current, Err):
                return current
            digest = _snapshot_digest(current.value)
            if isinstance(digest, Err):
                return digest
            if digest.value != prepared.review.snapshot_digest:
                return _error("registry workspace changed after read-only review", stale=True)
            changed = 0
        else:
            return _error("prepared curation payload is not executable")
        read_only = not prepared.review.mutating
        status: CurationOutcomeStatus = (
            "failed"
            if read_only and any(not item.passed for item in prepared.review.checks)
            else "succeeded"
            if read_only or changed
            else "no-op"
        )
        observed = sum(item.status != "unchanged" for item in prepared.review.changes)
        return Ok(
            CurationOutcome(
                prepared.review.action,
                status,
                changed,
                observed,
                prepared.review.checks,
                prepared.review.warnings,
                prepared.review.follow_up_commands,
            )
        )


def load_local_curation_service(workspace: str) -> Result[LocalCurationService]:
    try:
        return Ok(LocalCurationService(os.path.abspath(workspace)))
    except ValueError as error:
        return _error(str(error))
