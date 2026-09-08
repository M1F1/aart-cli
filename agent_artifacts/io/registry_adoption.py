"""`QA-021`/`B-095`: adopting artifacts from a repository that is not a configured Source.

The monitored path -- subscribe to an authoring Source, sync it, review its Candidates, promote a
selection -- is the one AART is built around, and it stays that. Beside it a maintainer needs an
artifact-scoped path: look at a credential-free Git URL once, see exactly what its authors
declared, choose some of it, and let the registry own immutable copies of only those files. Nothing
about that is a subscription, so nothing here writes configuration and nothing here implies that
the repository will be watched (INV-199, INV-200).

Three things are load-bearing and each is a boundary rather than a convenience.

**Discovery is explicit.** Only committed `aart.yaml`/`aart.json` manifests are read, through the
same `compile_author_snapshot` the monitored path uses. A conventional-looking directory that
declares nothing is not an artifact (INV-201).

**Only the declared payload is copied.** The compiled canonical package is built from each
manifest's own `payload.include`, so a file that merely sits beside a manifest is not adopted by
proximity. This module never re-derives that set; it carries the compiler's answer.

**The copy remembers where it came from.** The upstream URL, the resolved commit, the manifest path
and its input digest travel into the registry as the package's own provenance, which is what a
later explicit upstream check has to compare against. Publication itself stays external (165.27):
this writes the registry checkout and nothing else.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

from agent_artifacts.application.candidate_validation import (
    validate_candidate,
    validated_candidate,
)
from agent_artifacts.application.maintainer import (
    CandidateBundle,
    SourceScan,
    reconcile_source_scan,
)
from agent_artifacts.application.maintainer_promotion import promotion_evidence
from agent_artifacts.application.promotion import (
    PromotionPlan,
    finalize_promotion,
    load_registry_versions,
    plan_bulk_promotion,
)
from agent_artifacts.curation.runtime import default_native_acquirer
from agent_artifacts.domain.candidates import CandidateState
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.registry_promotion import FilesystemPromotionOutput
from agent_artifacts.io.registry_workspace import FilesystemRegistryWorkspace
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_schema import parse_source_manifest
from agent_artifacts.protocol.native_tree import SnapshotEntryKind
from agent_artifacts.registry_maintenance.model import NativeReferenceAcquisition

__all__ = [
    "REPOSITORY_ADOPTION_REFUSED",
    "PreparedAdoption",
    "RepositoryScan",
    "ScannedArtifact",
    "apply_adoption",
    "prepare_adoption",
    "scan_repository",
]

#: A one-off scan or adoption that will not proceed.
REPOSITORY_ADOPTION_REFUSED = DiagnosticCode("repository-adoption-refused")

RepositoryAcquirer = Callable[[str, str], Result[NativeReferenceAcquisition]]

_SLUG = re.compile(r"[^a-z0-9]+")

#: The policy a scan judges by when the caller names none. Held once rather than built per call so
#: the default is one object both entry points share.
_DEFAULT_POLICY = EffectivePolicy()


def _error(message: str, *interactive: str) -> Err:
    return Err(
        (
            Diagnostic(
                REPOSITORY_ADOPTION_REFUSED,
                Severity.ERROR,
                message,
                interactive=interactive,
            ),
        )
    )


def _scan_alias(url: str) -> SourceAlias:
    """A stable in-memory name for one scan, which is never written to configuration.

    A compiled artifact's coordinate needs a Source name, but nothing here subscribes: the name
    exists for the duration of the scan. What the registry publishes carries the registry's own
    alias, so this never becomes registry identity -- only the upstream URL and commit do, and
    those are recorded as provenance.
    """

    tail = url.rstrip("/").rsplit("/", 1)[-1]
    slug = _SLUG.sub("-", tail.removesuffix(".git").lower()).strip("-")
    return SourceAlias(f"scan-{slug}" if slug else "scan-repository")


@dataclass(frozen=True, slots=True)
class ScannedArtifact:
    """One artifact a repository's own manifest declared, and what adopting it would copy."""

    coordinate: str
    kind: str
    name: str
    version: str
    summary: str
    manifest_path: str
    input_digest: str
    state: str
    payload_paths: tuple[str, ...]
    adoptable: bool


@dataclass(frozen=True, slots=True)
class RepositoryScan:
    """One pinned read-only observation of a repository that is not a Source."""

    url: str
    ref: str
    commit: str
    manifest_count: int
    artifacts: tuple[ScannedArtifact, ...]
    #: The compiled Candidates the observation is made of. Held so that choosing from what was
    #: shown does not require acquiring the repository a second time and reviewing something else.
    observation: SourceScan = field(repr=False, compare=False)
    #: The same Candidates carrying what validation found. The state a maintainer reads on the scan
    #: screen and the state adoption enforces are then one answer, not two that can disagree.
    bundles: tuple[CandidateBundle, ...] = field(default=(), repr=False, compare=False)
    registry_alias: str = ""


@dataclass(frozen=True, slots=True)
class PreparedAdoption:
    """The exact registry transaction one selection would apply, having written nothing."""

    url: str
    ref: str
    commit: str
    selected: tuple[str, ...]
    changed_paths: tuple[str, ...]
    plan: PromotionPlan = field(repr=False, compare=False)

    @property
    def review_digest(self) -> str:
        return str(self.plan.review_digest)


def _coordinate(bundle: CandidateBundle) -> str:
    coordinate = bundle.candidate.artifact.coordinate
    return f"{coordinate.artifact}@{coordinate.version}"


def _registry_alias(registry_root: str) -> Result[SourceAlias]:
    snapshot = FilesystemRegistryWorkspace(registry_root).snapshot()
    if isinstance(snapshot, Err):
        return snapshot
    marker = next(
        (
            entry
            for entry in snapshot.value.entries
            if str(entry.path) == "aart-source.json" and entry.kind is SnapshotEntryKind.FILE
        ),
        None,
    )
    if marker is None:
        return _error(
            "this project has no registry to adopt into",
            "Create the registry first from the Registry screen, then scan a repository.",
        )
    parsed = parse_source_manifest(marker.content)
    if isinstance(parsed, Err):
        return parsed
    try:
        return Ok(SourceAlias(str(parsed.value.source_id)))
    except ValueError as error:
        return _error(str(error))


def scan_repository(
    *,
    url: str,
    ref: str,
    registry_root: str,
    acquire: RepositoryAcquirer = default_native_acquirer,
    policy: EffectivePolicy = _DEFAULT_POLICY,
) -> Result[RepositoryScan]:
    """Observe one repository's declared artifacts at one pinned commit, changing nothing."""

    if not os.path.isabs(registry_root) or os.path.normpath(registry_root) != registry_root:
        return _error("a repository is scanned against an absolute registry checkout")
    if not url or not ref or any(char in url + ref for char in "\r\n"):
        return _error(
            "a scan needs a credential-free Git URL and a branch or tag",
            "Type the repository's HTTPS or SSH URL and the branch or tag to read.",
        )
    alias = _registry_alias(registry_root)
    if isinstance(alias, Err):
        return alias
    acquired = acquire(url, ref)
    if isinstance(acquired, Err):
        return acquired
    workspace = FilesystemRegistryWorkspace(registry_root).snapshot()
    if isinstance(workspace, Err):
        return workspace
    approved = load_registry_versions(workspace.value)
    if isinstance(approved, Err):
        return approved
    compiled = compile_author_snapshot(
        acquired.value.snapshot,
        source_alias=_scan_alias(url),
        source=url,
        revision=acquired.value.resolved_commit,
    )
    if isinstance(compiled, Err):
        return compiled
    if not compiled.value:
        return _error(
            f"{url} declares no aart.yaml or aart.json artifact at {ref}",
            "AART reads only manifests the authors committed. Ask them to declare one, or scan "
            "a branch or tag where they already did.",
        )
    observed = reconcile_source_scan(
        _scan_alias(url),
        acquired.value.resolved_commit,
        compiled.value,
        previous=(),
        approved=approved.value,
        target_registry=alias.value,
    )
    if isinstance(observed, Err):
        return observed
    # Validation happens here rather than at adoption so that what the scan screen says about an
    # artifact is what adopting it will enforce.  A Candidate straight out of reconciliation is
    # `new`; only assessment makes it `ready`, and offering an unassessed one as adoptable would
    # promise a maintainer something the plan would then refuse.
    bundles = tuple(
        bundle
        if bundle.candidate.state in _TERMINAL
        else validated_candidate(bundle, policy=policy)
        for bundle in observed.value.active
    )
    return Ok(
        RepositoryScan(
            url,
            ref,
            acquired.value.resolved_commit,
            observed.value.manifest_count,
            tuple(_scanned(bundle) for bundle in bundles),
            observed.value,
            bundles,
            alias.value.value,
        )
    )


_ADOPTABLE = frozenset({CandidateState.READY, CandidateState.WARNING})
#: A Candidate the registry has already answered for. Re-running validation over one of these is a
#: contradiction -- the registry's answer is the record -- so the scan carries the state as found.
_TERMINAL = frozenset(
    {CandidateState.PROMOTED, CandidateState.SUPERSEDED, CandidateState.SOURCE_REMOVED}
)


def _scanned(bundle: CandidateBundle) -> ScannedArtifact:
    candidate = bundle.candidate
    artifact = candidate.artifact
    version = artifact.coordinate.version or ""
    return ScannedArtifact(
        _coordinate(bundle),
        str(artifact.coordinate.artifact.kind),
        artifact.coordinate.artifact.name,
        version,
        bundle.artifact.native_package.manifest.summary,
        str(bundle.artifact.manifest_path),
        str(artifact.provenance.input_digest),
        candidate.state.value,
        tuple(
            str(entry.path)
            for entry in bundle.artifact.canonical_entries
            if str(entry.path).startswith("payload/")
        ),
        candidate.state in _ADOPTABLE,
    )


def prepare_adoption(
    scan: RepositoryScan,
    selected: tuple[str, ...],
    *,
    registry_root: str,
    policy: EffectivePolicy = _DEFAULT_POLICY,
) -> Result[PreparedAdoption]:
    """Plan the exact owned copies one selection would write, writing nothing.

    A selection is one transaction: the registry is left as the review describes it or not written
    at all, so an artifact whose own plan refuses takes the whole preparation down by name.
    """

    if not isinstance(scan, RepositoryScan):
        return _error("adopting from a repository needs one scan of it")
    if not selected:
        return _error(
            "nothing was selected to adopt",
            "Choose at least one artifact from the scan, then continue.",
        )
    by_coordinate = {_coordinate(bundle): bundle for bundle in scan.bundles}
    missing = tuple(item for item in selected if item not in by_coordinate)
    if missing:
        return _error(
            f"this scan of {scan.url} does not offer {', '.join(sorted(missing))}",
            "Scan the repository again and choose from what it declares now.",
        )
    bundles = tuple(by_coordinate[item] for item in selected)
    refused = tuple(
        item
        for item, bundle in zip(selected, bundles, strict=True)
        if bundle.candidate.state not in _ADOPTABLE
    )
    if refused:
        return _error(
            f"{', '.join(sorted(refused))} did not pass validation, so it cannot be adopted",
            "Open the scan again and choose an artifact whose manifest validates.",
        )
    workspace = FilesystemRegistryWorkspace(registry_root).snapshot()
    if isinstance(workspace, Err):
        return workspace
    approved = load_registry_versions(workspace.value)
    if isinstance(approved, Err):
        return approved
    evidence = []
    for bundle in bundles:
        validation = validate_candidate(bundle, policy=policy)
        record = promotion_evidence(validation, policy)
        if isinstance(record, Err):
            return record
        evidence.append((bundle.candidate.id, record.value))
    planned = plan_bulk_promotion(
        workspace.value,
        bundles,
        evidence=tuple(evidence),
        approved=approved.value,
        mode=PromotionMode.VENDORED,
    )
    if isinstance(planned, Err):
        return planned
    return Ok(
        PreparedAdoption(
            scan.url,
            scan.ref,
            scan.commit,
            tuple(selected),
            tuple(str(change.path) for change in planned.value.changes),
            planned.value,
        )
    )


def apply_adoption(
    prepared: PreparedAdoption,
    review_digest: str,
    *,
    registry_root: str,
) -> Result[PreparedAdoption]:
    """Apply exactly the reviewed transaction to the local registry checkout, and nothing else."""

    if not isinstance(prepared, PreparedAdoption):
        return _error("applying an adoption needs one prepared adoption")
    if review_digest != prepared.review_digest:
        return _error(
            "this confirmation names a different plan than the one reviewed",
            "Review the adoption again before confirming it.",
        )
    applied = finalize_promotion(
        prepared.plan,
        prepared.plan.review_digest,
        output=FilesystemPromotionOutput(registry_root),
    )
    if isinstance(applied, Err):
        return applied
    return Ok(prepared)
