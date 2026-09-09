"""Aggregate approved registry state and resolve Selection into exact versions.

This application service is pure.  It consumes already-validated registry snapshots, performs no
source synchronization or author-repository scan, and emits no install effects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
    is_pinned_source_revision,
)
from agent_artifacts.domain.registry import (
    PublicationStage,
    RegistryArtifactVersion,
    RegistryLifecycle,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    Collection,
    CollectionCoordinate,
    OwnershipKind,
    OwnershipReason,
    ResolvedArtifact,
    ResolvedSelection,
    VersionConstraint,
    artifact_coordinate_sort_key,
    artifact_request_sort_key,
)
from agent_artifacts.protocol.semver import SemVer, parse_semver

MARKETPLACE_INVALID = DiagnosticCode("approved-marketplace-invalid")
ARTIFACT_AMBIGUOUS = DiagnosticCode("artifact-ambiguous")
ARTIFACT_NOT_FOUND = DiagnosticCode("artifact-not-found")
ARTIFACT_REVOKED = DiagnosticCode("artifact-revoked")
COLLECTION_NOT_FOUND = DiagnosticCode("collection-not-found")
CROSS_REGISTRY_DENIED = DiagnosticCode("cross-registry-denied")
VERSION_CONFLICT = DiagnosticCode("version-conflict")
VERSION_CONSTRAINT_INVALID = DiagnosticCode("version-constraint-invalid")

_PARTIAL_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?(?:\.(0|[1-9][0-9]*))?$")


def _error(
    code: DiagnosticCode,
    message: str,
    *,
    details: tuple[tuple[str, str], ...] = (),
) -> Diagnostic:
    return Diagnostic(code, Severity.ERROR, message, details=details)


def _artifact_key(
    artifact: ApprovedMarketplaceArtifact,
) -> tuple[str, str, str, str]:
    return artifact_coordinate_sort_key(artifact.version.coordinate)


class RegistryTrust(str, Enum):
    ENTERPRISE_APPROVED = "enterprise-approved"
    REGISTRY_REVIEWED = "registry-reviewed"
    COMMUNITY = "community"
    LOCAL_UNREVIEWED = "local-unreviewed"


@dataclass(frozen=True, slots=True)
class ApprovedMarketplaceArtifact:
    version: RegistryArtifactVersion
    dependencies: tuple[ArtifactRequest, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.version, RegistryArtifactVersion) or any(
            not isinstance(item, ArtifactRequest) for item in self.dependencies
        ):
            raise ValueError("approved marketplace artifact is invalid")
        if self.version.coordinate.version is None or isinstance(
            parse_semver(self.version.coordinate.version), Err
        ):
            raise ValueError("approved marketplace artifact requires an exact SemVer")
        object.__setattr__(
            self,
            "dependencies",
            tuple(sorted(set(self.dependencies), key=artifact_request_sort_key)),
        )


@dataclass(frozen=True, slots=True)
class ApprovedRegistrySnapshot:
    alias: SourceAlias
    snapshot: ObjectDigest
    trust: RegistryTrust
    artifacts: tuple[ApprovedMarketplaceArtifact, ...]
    collections: tuple[Collection, ...] = ()
    resolved_revision: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.alias, SourceAlias)
            or not self.alias.value
            or not isinstance(self.snapshot, ObjectDigest)
            or not isinstance(self.trust, RegistryTrust)
            or any(not isinstance(item, ApprovedMarketplaceArtifact) for item in self.artifacts)
            or any(not isinstance(item, Collection) for item in self.collections)
            or any(item.version.coordinate.source != self.alias for item in self.artifacts)
            or any(item.version.registry_snapshot != self.snapshot for item in self.artifacts)
            or any(item.coordinate.source != self.alias for item in self.collections)
            or any(item.registry_snapshot != self.snapshot for item in self.collections)
            or (
                self.resolved_revision is not None
                and not is_pinned_source_revision(self.resolved_revision)
            )
        ):
            raise ValueError("approved registry snapshot is inconsistent")
        object.__setattr__(self, "artifacts", tuple(sorted(self.artifacts, key=_artifact_key)))
        object.__setattr__(
            self,
            "collections",
            tuple(sorted(self.collections, key=lambda item: item.coordinate)),
        )


@dataclass(frozen=True, slots=True)
class ApprovedMarketplace:
    registries: tuple[ApprovedRegistrySnapshot, ...]
    artifacts: tuple[ApprovedMarketplaceArtifact, ...]
    collections: tuple[Collection, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registries",
            tuple(sorted(self.registries, key=lambda item: item.alias.value)),
        )
        object.__setattr__(self, "artifacts", tuple(sorted(self.artifacts, key=_artifact_key)))
        object.__setattr__(
            self,
            "collections",
            tuple(sorted(self.collections, key=lambda item: item.coordinate)),
        )


@dataclass(frozen=True, slots=True)
class ResolutionPolicy:
    allow_cross_registry: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.allow_cross_registry, bool):
            raise ValueError("cross-registry policy must be boolean")


def aggregate_approved_marketplace(
    snapshots: tuple[ApprovedRegistrySnapshot, ...],
) -> Result[ApprovedMarketplace]:
    """Project only published approved versions; local promotion is not publication."""

    aliases = tuple(snapshot.alias for snapshot in snapshots)
    if len(set(aliases)) != len(aliases):
        return Err(
            (
                _error(
                    MARKETPLACE_INVALID,
                    "approved marketplace registry aliases must be unique",
                ),
            )
        )
    artifacts = tuple(
        artifact
        for snapshot in snapshots
        for artifact in snapshot.artifacts
        if artifact.version.publication is PublicationStage.PUBLISHED
    )
    qualified_versions: dict[
        tuple[SourceAlias, ArtifactIdentity, str], ApprovedMarketplaceArtifact
    ] = {}
    for artifact in artifacts:
        coordinate = artifact.version.coordinate
        assert coordinate.version is not None
        key = (coordinate.source, coordinate.artifact, coordinate.version)
        existing = qualified_versions.get(key)
        if existing is not None and existing != artifact:
            return Err(
                (
                    _error(
                        MARKETPLACE_INVALID,
                        f"published registry version is not unique: {coordinate}",
                    ),
                )
            )
        qualified_versions[key] = artifact
    collections = tuple(collection for snapshot in snapshots for collection in snapshot.collections)
    collection_coordinates = tuple(collection.coordinate for collection in collections)
    if len(set(collection_coordinates)) != len(collection_coordinates):
        return Err(
            (
                _error(
                    MARKETPLACE_INVALID,
                    "published Collection coordinates must be unique within a registry",
                ),
            )
        )
    return Ok(
        ApprovedMarketplace(
            tuple(snapshots),
            tuple(qualified_versions.values()),
            collections,
        )
    )


@dataclass(frozen=True, slots=True)
class _Comparison:
    operator: str
    version: SemVer

    def allows(self, candidate: SemVer) -> bool:
        if self.operator == ">=":
            return candidate >= self.version
        if self.operator == ">":
            return candidate > self.version
        if self.operator == "<=":
            return candidate <= self.version
        if self.operator == "<":
            return candidate < self.version
        return candidate == self.version


@dataclass(frozen=True, slots=True)
class _ParsedConstraint:
    raw: VersionConstraint
    comparisons: tuple[_Comparison, ...]

    def allows(self, candidate: SemVer) -> bool:
        return all(comparison.allows(candidate) for comparison in self.comparisons)


def _partial_semver(raw: str) -> SemVer | None:
    match = _PARTIAL_VERSION_RE.fullmatch(raw)
    if match is None:
        return None
    values = tuple(0 if value is None else int(value) for value in match.groups())
    if any(value > 2**63 - 1 for value in values):
        return None
    return SemVer(values[0], values[1], values[2])


def _parse_constraint(constraint: VersionConstraint) -> Result[_ParsedConstraint]:
    raw = constraint.value
    if raw == "*":
        return Ok(_ParsedConstraint(constraint, ()))
    if raw.startswith("^"):
        minimum = _partial_semver(raw[1:])
        if minimum is None:
            return Err(
                (
                    _error(
                        VERSION_CONSTRAINT_INVALID,
                        f"invalid version constraint: {raw}",
                    ),
                )
            )
        if minimum.major > 0:
            maximum = SemVer(minimum.major + 1, 0, 0)
        elif minimum.minor > 0:
            maximum = SemVer(0, minimum.minor + 1, 0)
        else:
            maximum = SemVer(0, 0, minimum.patch + 1)
        return Ok(
            _ParsedConstraint(
                constraint,
                (_Comparison(">=", minimum), _Comparison("<", maximum)),
            )
        )
    comparisons: list[_Comparison] = []
    for part in raw.split(","):
        match = re.fullmatch(r"(>=|<=|>|<|=)?(.+)", part)
        if match is None:
            comparisons = []
            break
        operator = match.group(1) or "="
        version = _partial_semver(match.group(2))
        if version is None:
            exact = parse_semver(match.group(2))
            if isinstance(exact, Err):
                comparisons = []
                break
            version = exact.value
        comparisons.append(_Comparison(operator, version))
    if not comparisons:
        return Err(
            (
                _error(
                    VERSION_CONSTRAINT_INVALID,
                    f"invalid version constraint: {raw}",
                ),
            )
        )
    return Ok(_ParsedConstraint(constraint, tuple(comparisons)))


@dataclass(frozen=True, slots=True)
class _Requirement:
    request: ArtifactRequest
    ownership: OwnershipReason
    preferred_source: SourceAlias | None = None
    dependant: ArtifactCoordinate | None = None


@dataclass(frozen=True, slots=True)
class _ResolutionState:
    chosen: dict[ArtifactIdentity, ApprovedMarketplaceArtifact]
    ownership: dict[ArtifactIdentity, frozenset[OwnershipReason]]
    edges: dict[ArtifactIdentity, frozenset[ArtifactIdentity]]


def _constraint_diagnostic(
    identity: ArtifactIdentity,
    requirements: tuple[_Requirement, ...],
) -> Diagnostic:
    constraints = tuple(sorted({item.request.version.value for item in requirements}))
    return _error(
        VERSION_CONFLICT,
        f"no single version of {identity} satisfies: {', '.join(constraints)}",
        details=(
            ("artifact", str(identity)),
            ("constraints", ",".join(constraints)),
        ),
    )


def _candidate_options(
    marketplace: ApprovedMarketplace,
    identity: ArtifactIdentity,
    requirements: tuple[_Requirement, ...],
    policy: ResolutionPolicy,
) -> Result[tuple[ApprovedMarketplaceArtifact, ...]]:
    parsed: list[_ParsedConstraint] = []
    for requirement in requirements:
        result = _parse_constraint(requirement.request.version)
        if isinstance(result, Err):
            return result
        parsed.append(result.value)

    candidates = tuple(
        artifact
        for artifact in marketplace.artifacts
        if artifact.version.coordinate.artifact == identity
    )

    def satisfies_every_constraint(artifact: ApprovedMarketplaceArtifact) -> bool:
        raw_version = artifact.version.coordinate.version
        assert raw_version is not None
        version = parse_semver(raw_version)
        assert isinstance(version, Ok)
        return all(item.allows(version.value) for item in parsed)

    explicit_sources = {
        item.request.source for item in requirements if item.request.source is not None
    }
    if len(explicit_sources) > 1:
        return Err((_constraint_diagnostic(identity, requirements),))
    preferred_sources = {
        item.preferred_source for item in requirements if item.preferred_source is not None
    }
    explicit_source = next(iter(explicit_sources), None)
    source_is_bound = explicit_source is not None
    if explicit_source is not None:
        crossings = tuple(source for source in preferred_sources if source != explicit_source)
        if crossings and not policy.allow_cross_registry:
            return Err(
                (
                    _error(
                        CROSS_REGISTRY_DENIED,
                        f"cross-registry resolution of {identity} from {explicit_source} is denied",
                        details=(
                            ("artifact", str(identity)),
                            ("registry", explicit_source.value),
                        ),
                    ),
                )
            )
        candidates = tuple(
            artifact
            for artifact in candidates
            if artifact.version.coordinate.source == explicit_source
        )
    elif len(preferred_sources) == 1:
        preferred = next(iter(preferred_sources))
        local = tuple(
            artifact for artifact in candidates if artifact.version.coordinate.source == preferred
        )
        if any(satisfies_every_constraint(artifact) for artifact in local):
            candidates = local
            source_is_bound = True
        elif not policy.allow_cross_registry:
            external_match = any(
                artifact.version.coordinate.source != preferred
                and satisfies_every_constraint(artifact)
                for artifact in candidates
            )
            if external_match:
                return Err(
                    (
                        _error(
                            CROSS_REGISTRY_DENIED,
                            f"{identity} is unavailable in {preferred}; cross-registry resolution is denied",
                            details=(
                                ("artifact", str(identity)),
                                ("registry", preferred.value),
                            ),
                        ),
                    )
                )
            candidates = local
    elif len(preferred_sources) > 1 and not policy.allow_cross_registry:
        rendered = ", ".join(sorted(source.value for source in preferred_sources))
        return Err(
            (
                _error(
                    CROSS_REGISTRY_DENIED,
                    f"{identity} is required across registries {rendered}",
                    details=(("artifact", str(identity)), ("registries", rendered)),
                ),
            )
        )

    parsed_versions: list[tuple[ApprovedMarketplaceArtifact, SemVer]] = []
    individually_satisfiable = [False for _ in parsed]
    for artifact in candidates:
        raw_version = artifact.version.coordinate.version
        assert raw_version is not None
        version = parse_semver(raw_version)
        assert isinstance(version, Ok)
        permissions = tuple(item.allows(version.value) for item in parsed)
        for index, permitted in enumerate(permissions):
            individually_satisfiable[index] = individually_satisfiable[index] or permitted
        if all(permissions):
            parsed_versions.append((artifact, version.value))

    if not parsed_versions:
        if candidates and parsed and all(individually_satisfiable):
            return Err((_constraint_diagnostic(identity, requirements),))
        return Err(
            (
                _error(
                    ARTIFACT_NOT_FOUND,
                    f"no approved published version of {identity} satisfies the Selection",
                    details=(("artifact", str(identity)),),
                ),
            )
        )

    satisfying_sources = {
        artifact.version.coordinate.source for artifact, _version in parsed_versions
    }
    if not source_is_bound and len(satisfying_sources) > 1:
        coordinates = tuple(
            sorted(str(artifact.version.coordinate) for artifact, _version in parsed_versions)
        )
        return Err(
            (
                _error(
                    ARTIFACT_AMBIGUOUS,
                    f"{identity} is ambiguous; valid approved coordinates: {', '.join(coordinates)}",
                    details=(("coordinates", ",".join(coordinates)),),
                ),
            )
        )

    installable = tuple(
        (artifact, version)
        for artifact, version in parsed_versions
        if artifact.version.lifecycle is not RegistryLifecycle.REVOKED
    )
    if not installable:
        dependants = tuple(
            sorted(
                {
                    str(requirement.dependant)
                    for requirement in requirements
                    if requirement.dependant is not None
                }
            )
        )
        context = "" if not dependants else f" required by {', '.join(dependants)}"
        return Err(
            (
                _error(
                    ARTIFACT_REVOKED,
                    f"every satisfying version of {identity}{context} is revoked",
                    details=(
                        ("artifact", str(identity)),
                        ("dependants", ",".join(dependants)),
                    ),
                ),
            )
        )
    ordered = tuple(
        item[0]
        for item in sorted(
            installable,
            key=lambda item: (item[1], item[0].version.coordinate.version or ""),
            reverse=True,
        )
    )
    return Ok(ordered)


def _solve(
    marketplace: ApprovedMarketplace,
    pending: tuple[_Requirement, ...],
    state: _ResolutionState,
    policy: ResolutionPolicy,
) -> Result[_ResolutionState]:
    if not pending:
        return Ok(state)
    identity = min(
        (requirement.request.identity for requirement in pending),
        key=lambda item: (item.kind, item.name),
    )
    grouped = tuple(item for item in pending if item.request.identity == identity)
    remaining = tuple(item for item in pending if item.request.identity != identity)
    options = _candidate_options(marketplace, identity, grouped, policy)
    if isinstance(options, Err):
        return options
    already_chosen = state.chosen.get(identity)
    if already_chosen is not None:
        if already_chosen not in options.value:
            return Err((_constraint_diagnostic(identity, grouped),))
        ownership = dict(state.ownership)
        ownership[identity] = ownership.get(identity, frozenset()) | frozenset(
            item.ownership for item in grouped
        )
        return _solve(
            marketplace,
            remaining,
            _ResolutionState(state.chosen, ownership, state.edges),
            policy,
        )

    first_failure: Err | None = None
    for candidate in options.value:
        coordinate = candidate.version.coordinate
        chosen = dict(state.chosen)
        chosen[identity] = candidate
        ownership = dict(state.ownership)
        ownership[identity] = ownership.get(identity, frozenset()) | frozenset(
            item.ownership for item in grouped
        )
        edges = dict(state.edges)
        dependency_identities = frozenset(item.identity for item in candidate.dependencies)
        edges[identity] = dependency_identities
        dependency_requirements = tuple(
            _Requirement(
                dependency,
                OwnershipReason(OwnershipKind.DEPENDENCY, str(coordinate)),
                coordinate.source,
                coordinate,
            )
            for dependency in candidate.dependencies
        )
        result = _solve(
            marketplace,
            (*remaining, *dependency_requirements),
            _ResolutionState(chosen, ownership, edges),
            policy,
        )
        if isinstance(result, Ok):
            return result
        if first_failure is None:
            first_failure = result
    assert first_failure is not None
    return first_failure


def _collection_requirements(
    marketplace: ApprovedMarketplace,
    selection: ArtifactSelection,
) -> Result[tuple[_Requirement, ...]]:
    by_coordinate = {collection.coordinate: collection for collection in marketplace.collections}
    requirements: list[_Requirement] = []
    missing: list[CollectionCoordinate] = []
    for coordinate in selection.collections:
        collection = by_coordinate.get(coordinate)
        if collection is None:
            missing.append(coordinate)
            continue
        requirements.extend(
            _Requirement(
                member.request,
                OwnershipReason(OwnershipKind.COLLECTION, str(coordinate)),
                coordinate.source,
            )
            for member in collection.members
        )
    if missing:
        rendered = ", ".join(str(item) for item in missing)
        return Err(
            (
                _error(
                    COLLECTION_NOT_FOUND,
                    f"exact Collection versions were not found: {rendered}",
                    details=(("collections", rendered),),
                ),
            )
        )
    return Ok(tuple(requirements))


def resolve_selection(
    marketplace: ApprovedMarketplace,
    selection: ArtifactSelection,
    *,
    policy: ResolutionPolicy | None = None,
) -> Result[ResolvedSelection]:
    """Resolve one/many/direct/Collection intent through one deterministic pipeline."""

    effective_policy = ResolutionPolicy() if policy is None else policy
    collection_requirements = _collection_requirements(marketplace, selection)
    if isinstance(collection_requirements, Err):
        return collection_requirements
    direct = tuple(
        _Requirement(
            request,
            OwnershipReason(OwnershipKind.DIRECT, str(request)),
        )
        for request in selection.artifacts
    )
    initial = _ResolutionState({}, {}, {})
    solved = _solve(
        marketplace,
        (*direct, *collection_requirements.value),
        initial,
        effective_policy,
    )
    if isinstance(solved, Err):
        return solved
    revisions = {registry.alias: registry.resolved_revision for registry in marketplace.registries}
    artifacts = tuple(
        ResolvedArtifact(
            artifact.version,
            tuple(solved.value.ownership[identity]),
            tuple(
                solved.value.chosen[dependency].version.coordinate
                for dependency in solved.value.edges.get(identity, frozenset())
            ),
            revisions.get(artifact.version.coordinate.source),
        )
        for identity, artifact in solved.value.chosen.items()
    )
    return Ok(ResolvedSelection(selection, artifacts))
