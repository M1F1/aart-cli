"""Pure source-kind-aware validation bridges for acquired candidates."""

from __future__ import annotations

from aart_cli.application.promotion import (
    load_registry_versions,
    validate_promoted_registry,
)
from aart_cli.configuration.model import ConfiguredSource
from aart_cli.domain.diagnostics import Diagnostic, Severity
from aart_cli.domain.identifiers import SourceId
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.authoring import discover_author_manifests
from aart_cli.protocol.native_schema import parse_source_manifest
from aart_cli.protocol.native_tree import (
    SnapshotEntryKind,
    SourceSnapshot,
    load_native_source,
)
from aart_cli.protocol.registry_schema import parse_registry_manifest
from aart_cli.registry_maintenance.promoted import (
    is_promoted_registry,
    legacy_registry_paths,
)

from .model import (
    SOURCE_INVALID,
    SourceValidationRequest,
    ValidatedSourceCandidate,
    source_instance_id,
)

_REGISTRY_MARKER = "aart-cli-registry.json"
_SOURCE_MARKER = "aart-cli-source.json"
_AUTHOR_MANIFESTS = "aart-cli.yaml/aart-cli.json"


def validate_source_candidate(
    request: SourceValidationRequest,
) -> Result[ValidatedSourceCandidate]:
    """Validate a direct or local source against the native source protocol."""

    loaded = load_native_source(
        request.candidate.snapshot,
        executable_version=request.executable_version,
        available_capabilities=request.available_capabilities,
    )
    if isinstance(loaded, Err):
        return loaded
    # A native source that also publishes a registry marker is a registry being consumed through
    # the direct path.  The value the whole subscription model pins is its identity, and until now
    # no consumer-side gate compared the two documents that declare it — the publisher's own
    # `registry validate --strict --frozen` did, and the one-way adaptation rule says a consumer
    # does not soften a rule the publisher's tooling enforces.
    # A marker that is there must be readable. Comparing the two identities only when both
    # documents parse would leave a third state nobody chose — a broken `aart-cli-registry.json` would
    # skip the comparison in silence. On the registry path the workspace validation refuses first;
    # this is the same refusal on the direct/local path.
    unreadable = _unreadable_registry_marker(request)
    if unreadable is not None:
        return Err((unreadable,))
    disagreement = _identity_disagreement(request)
    if disagreement is not None:
        return Err((disagreement,))
    return Ok(
        ValidatedSourceCandidate(
            request.candidate,
            loaded.value.manifest.source_id,
        )
    )


def _error(message: str) -> Err:
    return Err((Diagnostic(SOURCE_INVALID, Severity.ERROR, message),))


def declares_native_source(snapshot: SourceSnapshot) -> bool:
    """Whether the acquired tree claims to be a native package source at its root.

    This is the one question that decides which admission rule an authoring Source is read by,
    so it asks only what the marker's own presence answers.  Whether that marker *parses* is
    `load_native_source`'s refusal to make, not a reason to silently fall through to the other
    format: a tree that says it is a native source and then is not is broken, not an authoring
    repository.
    """

    return any(
        str(entry.path) == _SOURCE_MARKER and entry.kind is SnapshotEntryKind.FILE
        for entry in snapshot.entries
    )


def validate_authoring_source_candidate(
    source: ConfiguredSource,
    request: SourceValidationRequest,
) -> Result[ValidatedSourceCandidate]:
    """Admit one authoring Source: a native package tree, or an explicit author manifest tree.

    An authoring Source is a location that *offers Candidates*, which Product Specification 72.1
    and 164.2 describe as a repository an author opted into by committing an `aart-cli.yaml` or
    `aart-cli.json`.  It is not a consumer native package tree, and requiring it to be one refused
    every real authoring repository at the public entrance (B-094/QA-020).

    Admission is exactly INV-201 and no more: *some* explicit manifest is declared here.  It is
    deliberately not "every manifest compiles" -- 164.2 shows a Source list whose entries say
    `3 manifests · 1 invalid`, so an invalid manifest is a Candidate state that Source Sync
    reports, not a subscription this refuses (INV-199).  What is refused is a repository that
    declares nothing at all, because "no manifest = no AART artifact candidate" is the rule that
    keeps discovery from becoming a heuristic crawl of arbitrary files.

    Nothing here relaxes a safety boundary.  Symlinks and special entries never reach this
    function: `source_snapshot_digest` refuses them outright, and `SourceCandidate` will not
    construct without that digest.  Transport, size limits and revision pinning are the
    acquisition adapter's, already applied.  Manifest discovery itself still refuses a manifest
    that is not a regular file and a boundary that declares both spellings at once.
    """

    if declares_native_source(request.candidate.snapshot):
        return validate_source_candidate(request)
    discovered = discover_author_manifests(request.candidate.snapshot)
    if isinstance(discovered, Err):
        return discovered
    if not discovered.value:
        return Err((_undeclared_source_refusal(),))
    # An authoring repository declares no identity of its own -- there is no document in it whose
    # job is to say "this Source is X", and inventing one from the URL would make a rename look
    # like a different Source.  The alias is what already identifies it everywhere the Candidate
    # model looks: `compile_author_source` stamps candidates with `source_alias`, and the
    # Maintainer screens key their history by it.  Naming the same thing here keeps identity
    # single-valued, and makes the identity-transition check inert for a Source that has no
    # declared identity to move.
    return Ok(ValidatedSourceCandidate(request.candidate, SourceId(source.alias.value)))


def _undeclared_source_refusal() -> Diagnostic:
    return Diagnostic(
        SOURCE_INVALID,
        Severity.ERROR,
        (
            "this tree declares no AART content: an authoring Source declares each artifact in "
            f"an explicit {_AUTHOR_MANIFESTS} manifest beside the files it names, and a native "
            f"package source declares itself in {_SOURCE_MARKER} at its root; this one has "
            "neither"
        ),
        remediation=(
            f"in the source repository, commit an {_AUTHOR_MANIFESTS} manifest in each directory "
            "that should become an artifact",
            "then add the source again; AART never infers artifacts from repository layout",
        ),
    )


def _root_file(request: SourceValidationRequest, path: str) -> Result[bytes]:
    entry = next(
        (item for item in request.candidate.snapshot.entries if str(item.path) == path),
        None,
    )
    if entry is None or entry.kind is not SnapshotEntryKind.FILE:
        return _error(f"registry source requires a regular {path}")
    return Ok(entry.content)


def _root_entry(request: SourceValidationRequest, path: str):
    return next(
        (item for item in request.candidate.snapshot.entries if str(item.path) == path),
        None,
    )


def _unreadable_registry_marker(request: SourceValidationRequest) -> Diagnostic | None:
    """The refusal when a root `aart-cli-registry.json` is present and cannot be read.

    Absence is not the case this answers: a source publishing `aart-cli-source.json` alone is an
    ordinary native source and stays one.  What is refused is a snapshot that reserves the registry
    marker's name and then does not honour it — a directory under that name, or a document that
    does not parse.  Either way the identity comparison below has nothing to compare, and admitting
    the subscription anyway would be silent about it.
    """

    entry = _root_entry(request, _REGISTRY_MARKER)
    if entry is None:
        return None
    if entry.kind is not SnapshotEntryKind.FILE:
        return _marker_refusal(f"{_REGISTRY_MARKER} is present and is not a regular file")
    parsed = parse_registry_manifest(entry.content)
    if isinstance(parsed, Err):
        # The parser's own first line, kept: *that it does not parse* is the refusal, and *why* is
        # the only part the maintainer can act on.
        return _marker_refusal(
            f"{_REGISTRY_MARKER} is present and does not parse",
            detail=parsed.diagnostics[0].message,
        )
    return None


def _marker_refusal(message: str, *, detail: str | None = None) -> Diagnostic:
    stated = f"{message}, so the identity this source declares cannot be checked"
    return Diagnostic(
        SOURCE_INVALID,
        Severity.ERROR,
        stated if detail is None else f"{stated}: {detail}",
        remediation=(
            "in the registry, run `aart-cli registry validate` there before republishing",
            f"or remove {_REGISTRY_MARKER} if this source is not a registry",
        ),
    )


def _identity_disagreement(request: SourceValidationRequest) -> Diagnostic | None:
    """The refusal when the two identity documents disagree, ``None`` when there is nothing to compare.

    "Nothing to compare" is deliberately narrow: only a snapshot that carries both markers as
    regular files, each parsing as its own protocol document, has an agreement to check.  A source
    publishing `aart-cli-source.json` alone is not a registry and is unaffected; a malformed
    `aart-cli-registry.json` is refused before this runs, by `_unreadable_registry_marker`.
    """

    registry_file = _root_file(request, _REGISTRY_MARKER)
    source_file = _root_file(request, _SOURCE_MARKER)
    if isinstance(registry_file, Err) or isinstance(source_file, Err):
        return None
    registry = parse_registry_manifest(registry_file.value)
    source = parse_source_manifest(source_file.value)
    if isinstance(registry, Err) or isinstance(source, Err):
        return None
    if registry.value.registry_id == source.value.source_id:
        return None
    return Diagnostic(
        SOURCE_INVALID,
        Severity.ERROR,
        (
            f"the two identity documents disagree: {_REGISTRY_MARKER} declares registry_id "
            f"{registry.value.registry_id}; {_SOURCE_MARKER} declares source_id "
            f"{source.value.source_id}"
        ),
        remediation=(
            f"in the registry, make source_id in {_SOURCE_MARKER} equal registry_id in "
            f"{_REGISTRY_MARKER}",
            "then re-run `aart-cli registry validate` there before republishing",
        ),
    )


def _registry_identity(request: SourceValidationRequest) -> Result[SourceId]:
    registry_file = _root_file(request, _REGISTRY_MARKER)
    source_file = _root_file(request, _SOURCE_MARKER)
    if isinstance(registry_file, Err):
        return registry_file
    if isinstance(source_file, Err):
        return source_file
    registry = parse_registry_manifest(registry_file.value)
    source = parse_source_manifest(source_file.value)
    if isinstance(registry, Err):
        return registry
    if isinstance(source, Err):
        return source
    disagreement = _identity_disagreement(request)
    if disagreement is not None:
        return Err((disagreement,))
    return Ok(registry.value.registry_id)


def validate_registry_source_candidate(
    request: SourceValidationRequest,
) -> Result[ValidatedSourceCandidate]:
    """Require one validated registry representation before admitting a marketplace source."""

    snapshot = request.candidate.snapshot
    # Promotion produces the approved, versioned registry representation named by the Product
    # Specification (`registry/versions/*` plus exact catalogs), and it is the only representation
    # a Registry source is admitted through.  The retired maintainer workspace compiler wrote
    # `aart.lock.json`, `aart.index.json` and `entries/`; there is no second authority to fall back
    # to, so a checkout still carrying that shape -- or carrying both -- is refused by name rather
    # than compiled by whichever branch matched first (CP-26.4, D-308).
    retired = legacy_registry_paths(snapshot)
    if retired:
        return _error(
            "registry source carries the retired authoring-workspace representation: "
            + ", ".join(retired)
        )
    if not is_promoted_registry(snapshot):
        return _error(
            "registry source is not a canonical approved Registry: its root must declare "
            f"{_REGISTRY_MARKER} and {_SOURCE_MARKER}"
        )
    versions = load_registry_versions(snapshot)
    if isinstance(versions, Err):
        return versions
    checked_promotion = validate_promoted_registry(snapshot, versions.value)
    if isinstance(checked_promotion, Err):
        return checked_promotion
    identity = _registry_identity(request)
    if isinstance(identity, Err):
        return identity
    return Ok(ValidatedSourceCandidate(request.candidate, identity.value))


def validate_configured_source_candidate(
    source: ConfiguredSource,
    request: SourceValidationRequest,
) -> Result[ValidatedSourceCandidate]:
    """Validate one acquired candidate using the protocol selected by its configured kind."""

    if (
        request.candidate.alias != source.alias
        or request.candidate.instance_id != source_instance_id(source)
    ):
        return _error("source validator received a candidate for another configured source")
    # By what the source *is*, not by how its bytes arrived. A Registry read out of a checkout is
    # admitted through the canonical Registry contract and nothing else (D-350): the whole value of
    # testing an artifact this way is that what passes here is what a remote Registry would publish.
    if source.is_registry:
        return validate_registry_source_candidate(request)
    return validate_authoring_source_candidate(source, request)
