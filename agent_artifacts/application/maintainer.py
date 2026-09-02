"""Pure maintainer Source Scan reconciliation over compiled author artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace

from agent_artifacts.domain.candidates import (
    Candidate,
    CandidateFinding,
    CandidateState,
    FindingSeverity,
    assess_candidate,
    candidate_id_for,
    make_candidate,
    mark_candidate_promoted,
    mark_source_removed,
    supersede_candidate,
)
from agent_artifacts.domain.collection_candidates import (
    CollectionCandidate,
    collection_candidate_id_for,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import (
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
    is_pinned_source_revision,
)
from agent_artifacts.domain.registry import RegistryArtifactVersion
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.authoring import CompiledAuthorArtifact, CompiledAuthorCollection
from agent_artifacts.protocol.hashing import file_entry, tree_digest

SOURCE_SCAN_INVALID = DiagnosticCode("source-scan-invalid")


@dataclass(frozen=True, slots=True)
class CandidateBundle:
    candidate: Candidate
    artifact: CompiledAuthorArtifact

    def __post_init__(self) -> None:
        if self.candidate.artifact != self.artifact.package:
            raise ValueError("candidate bundle must bind one compiled artifact")


@dataclass(frozen=True, slots=True)
class SourceScan:
    source_alias: SourceAlias
    revision: str
    manifest_count: int
    active: tuple[CandidateBundle, ...]
    history: tuple[CandidateBundle, ...]
    registry_mutations: tuple[object, ...] = ()
    collection_active: tuple[CollectionCandidate, ...] = ()
    collection_history: tuple[CollectionCandidate, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_alias, SourceAlias)
            or not is_pinned_source_revision(self.revision)
            or self.manifest_count != len(self.active) + len(self.collection_active)
            or self.registry_mutations
            or any(not isinstance(item, CollectionCandidate) for item in self.collection_active)
            or any(not isinstance(item, CollectionCandidate) for item in self.collection_history)
        ):
            raise ValueError("source scan must be a non-mutating pinned observation")


def _error(message: str) -> Err:
    return Err((Diagnostic(SOURCE_SCAN_INVALID, Severity.ERROR, message),))


def _canonical_digest(artifact: CompiledAuthorArtifact) -> Result[ObjectDigest]:
    entries = []
    for entry in artifact.canonical_entries:
        if str(entry.path) == "provenance.json":
            continue
        entries.append(file_entry(entry.path, entry.content, executable=entry.executable))
    digest = tree_digest(entries)
    if isinstance(digest, Err):
        return _error("compiled artifact does not form one canonical content tree")
    return digest


def _locator(bundle: CandidateBundle) -> tuple[str, str]:
    return (
        bundle.candidate.target_registry.value,
        bundle.candidate.artifact.provenance.manifest_path,
    )


def _approved_for(
    artifact: CompiledAuthorArtifact,
    target_registry: SourceAlias,
    approved: tuple[RegistryArtifactVersion, ...],
) -> RegistryArtifactVersion | None:
    identity = artifact.package.coordinate.artifact
    version = artifact.package.coordinate.version
    return next(
        (
            item
            for item in approved
            if item.coordinate.source == target_registry
            and item.coordinate.artifact == identity
            and item.coordinate.version == version
        ),
        None,
    )


def _with_registry_state(
    candidate: Candidate,
    approved: RegistryArtifactVersion | None,
) -> Candidate:
    if approved is None:
        return candidate
    if (
        approved.candidate_id == candidate.id
        and approved.input_digest == candidate.artifact.provenance.input_digest
        and approved.payload_digest == candidate.artifact.payload_digest
    ):
        ready = assess_candidate(candidate)
        return mark_candidate_promoted(ready, approved.registry_snapshot)
    finding = CandidateFinding(
        "registry-version-immutable",
        FindingSeverity.ERROR,
        "Published coordinate/version already contains different canonical content",
    )
    return assess_candidate(candidate, findings=(finding,))


def reconcile_source_scan(
    source_alias: SourceAlias,
    revision: str,
    compiled: tuple[CompiledAuthorArtifact, ...],
    *,
    previous: tuple[CandidateBundle, ...],
    approved: tuple[RegistryArtifactVersion, ...],
    target_registry: SourceAlias,
    collections: tuple[CompiledAuthorCollection, ...] = (),
    previous_collections: tuple[CollectionCandidate, ...] = (),
) -> Result[SourceScan]:
    """Reconcile candidates only; approved registry state is read-only input."""

    if (
        not isinstance(source_alias, SourceAlias)
        or not source_alias.value
        or not isinstance(target_registry, SourceAlias)
        or not target_registry.value
        or not is_pinned_source_revision(revision)
    ):
        return _error("source scan requires aliases and one pinned source revision")
    for compiled_artifact in compiled:
        if (
            compiled_artifact.package.coordinate.source != source_alias
            or compiled_artifact.package.provenance.revision != revision
        ):
            return _error("compiled artifacts do not match the scanned source observation")
    for collection in collections:
        if collection.source_alias != source_alias or collection.revision != revision:
            return _error("compiled Collections do not match the scanned source observation")

    previous_by_id = {bundle.candidate.id: bundle for bundle in previous}
    if len(previous_by_id) != len(previous):
        return _error("candidate history contains duplicate candidate IDs")
    current_by_locator: dict[tuple[str, str], CandidateBundle] = {}
    for bundle in previous:
        if bundle.candidate.target_registry != target_registry:
            continue
        if bundle.candidate.artifact.coordinate.source != source_alias:
            continue
        if bundle.candidate.state is CandidateState.SUPERSEDED:
            continue
        locator = _locator(bundle)
        if locator in current_by_locator:
            return _error("candidate history contains multiple current records for one manifest")
        current_by_locator[locator] = bundle

    history = dict(previous_by_id)
    active: list[CandidateBundle] = []
    seen_locators: set[tuple[str, str]] = set()
    for artifact in sorted(compiled, key=lambda item: str(item.manifest_path)):
        locator = (target_registry.value, str(artifact.manifest_path))
        if locator in seen_locators:
            return _error("source scan contains duplicate manifest boundaries")
        seen_locators.add(locator)
        prior = current_by_locator.get(locator)
        digest = _canonical_digest(artifact)
        if isinstance(digest, Err):
            return digest
        candidate_id = candidate_id_for(artifact.package, target_registry)
        if prior is not None and prior.candidate.id == candidate_id:
            active.append(prior)
            continue
        candidate = make_candidate(
            artifact.package,
            digest.value,
            target_registry,
            previous=None if prior is None else prior.candidate.id,
        )
        registry_version = _approved_for(artifact, target_registry, approved)
        candidate = _with_registry_state(candidate, registry_version)
        if prior is None and registry_version is None:
            older_published = any(
                item.coordinate.source == target_registry
                and item.coordinate.artifact == artifact.package.coordinate.artifact
                for item in approved
            )
            if older_published:
                candidate = replace(candidate, state=CandidateState.CHANGED)
        bundle = CandidateBundle(candidate, artifact)
        history[candidate.id] = bundle
        active.append(bundle)
        if prior is not None:
            superseded = replace(
                prior,
                candidate=supersede_candidate(prior.candidate, candidate.id),
            )
            history[prior.candidate.id] = superseded

    for locator, prior in current_by_locator.items():
        if locator in seen_locators:
            continue
        removed = replace(prior, candidate=mark_source_removed(prior.candidate))
        history[prior.candidate.id] = removed

    collection_previous_by_id = {item.id: item for item in previous_collections}
    if len(collection_previous_by_id) != len(previous_collections):
        return _error("Collection Candidate history contains duplicate Candidate IDs")
    collection_current_by_locator: dict[tuple[str, str], CollectionCandidate] = {}
    for collection_record in previous_collections:
        if (
            collection_record.target_registry != target_registry
            or collection_record.source_alias != source_alias
            or collection_record.state is CandidateState.SUPERSEDED
        ):
            continue
        locator = (target_registry.value, collection_record.manifest_path)
        if locator in collection_current_by_locator:
            return _error(
                "Collection Candidate history contains multiple current records for one manifest"
            )
        collection_current_by_locator[locator] = collection_record

    collection_history = dict(collection_previous_by_id)
    collection_active: list[CollectionCandidate] = []
    collection_seen: set[tuple[str, str]] = set()
    for collection in sorted(collections, key=lambda item: str(item.manifest_path)):
        locator = (target_registry.value, str(collection.manifest_path))
        if locator in collection_seen:
            return _error("source scan contains duplicate Collection manifest boundaries")
        collection_seen.add(locator)
        collection_prior = collection_current_by_locator.get(locator)
        candidate_id = collection_candidate_id_for(
            collection.source_alias,
            str(collection.manifest_path),
            collection.input_digest,
            target_registry,
        )
        if collection_prior is not None and collection_prior.id == candidate_id:
            collection_active.append(collection_prior)
            continue
        collection_candidate = CollectionCandidate(
            candidate_id,
            collection.source_alias,
            collection.source,
            collection.revision,
            str(collection.manifest_path),
            collection.input_digest,
            collection.canonical_digest,
            target_registry,
            collection.name,
            collection.version,
            collection.summary,
            collection.members,
            CandidateState.NEW if collection_prior is None else CandidateState.CHANGED,
            None if collection_prior is None else collection_prior.id,
        )
        approved_version = next(
            (
                item
                for item in approved
                if item.coordinate.source == target_registry
                and item.coordinate.artifact == ArtifactIdentity("collection", collection.name)
                and item.coordinate.version == collection.version
            ),
            None,
        )
        if approved_version is not None:
            if (
                approved_version.candidate_id == collection_candidate.id
                and approved_version.input_digest == collection_candidate.input_digest
                and approved_version.canonical_digest == collection_candidate.canonical_digest
            ):
                collection_candidate = replace(collection_candidate, state=CandidateState.PROMOTED)
            else:
                collection_candidate = replace(
                    collection_candidate,
                    state=CandidateState.INVALID,
                    findings=(
                        CandidateFinding(
                            "registry-version-immutable",
                            FindingSeverity.ERROR,
                            "Published Collection coordinate/version already contains different "
                            "canonical content",
                        ),
                    ),
                )
        elif collection_prior is None and any(
            item.coordinate.source == target_registry
            and item.coordinate.artifact == ArtifactIdentity("collection", collection.name)
            for item in approved
        ):
            collection_candidate = replace(collection_candidate, state=CandidateState.CHANGED)
        collection_history[collection_candidate.id] = collection_candidate
        collection_active.append(collection_candidate)
        if collection_prior is not None:
            collection_history[collection_prior.id] = replace(
                collection_prior,
                state=CandidateState.SUPERSEDED,
                successor=collection_candidate.id,
            )

    for locator, collection_prior in collection_current_by_locator.items():
        if locator in collection_seen:
            continue
        collection_history[collection_prior.id] = replace(
            collection_prior,
            state=CandidateState.SOURCE_REMOVED,
            successor=None,
        )

    return Ok(
        SourceScan(
            source_alias,
            revision,
            len(active) + len(collection_active),
            tuple(sorted(active, key=lambda item: str(item.artifact.manifest_path))),
            tuple(sorted(history.values(), key=lambda item: item.candidate.id.value)),
            (),
            tuple(sorted(collection_active, key=lambda item: item.manifest_path)),
            tuple(sorted(collection_history.values(), key=lambda item: item.id.value)),
        )
    )
