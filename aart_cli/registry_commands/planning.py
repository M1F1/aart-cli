"""Pure registry workspace planning and quality checks over inert snapshots."""

from __future__ import annotations

from aart_cli.application.promotion import (
    read_registry_version_records,
    registry_catalog_entries,
    registry_state_digest,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import (
    ArtifactIdentity,
    SourceId,
    source_revision_kind,
)
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.capabilities import Capability
from aart_cli.protocol.hashing import sha256_bytes
from aart_cli.protocol.json import JsonObject, canonical_json_bytes, parse_json
from aart_cli.protocol.native_models import (
    ArtifactManifest,
    SourceManifest,
)
from aart_cli.protocol.native_schema import (
    parse_artifact_manifest,
    parse_provenance,
    parse_source_manifest,
    source_manifest_to_json,
)
from aart_cli.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SourceSnapshot,
)
from aart_cli.protocol.paths import SafeRelativePath, parse_relative_path
from aart_cli.protocol.registry_models import (
    RegistryManifest,
)
from aart_cli.protocol.registry_schema import (
    parse_registry_manifest,
    registry_manifest_to_json,
)
from aart_cli.protocol.semver import SemVer, VersionBounds
from aart_cli.registry_maintenance.delivery import (
    delivery_reference_message,
    describe_delivery,
    mcp_descriptor_message,
)
from aart_cli.registry_maintenance.model import REPOSITORY_ADOPTION_RECORD
from aart_cli.registry_maintenance.planning import (
    registry_native_content,
)
from aart_cli.runtime_contract import EXECUTABLE_VERSION
from aart_cli.security.application import verify_security_index
from aart_cli.security.attestation_schema import parse_security_index
from aart_cli.security.model import InstallationRisk
from aart_cli.sources.model import source_snapshot_digest

from .model import (
    RegistryInitOptions,
    RegistryOperation,
    RegistryQualityCheck,
    RegistryQualityReport,
    RegistryWorkspaceChange,
    RegistryWorkspacePlan,
    WorkspaceChangeKind,
    registry_workspace_review_digest,
)
from .templates import (
    REGISTRY_CI_WORKFLOW,
    REGISTRY_GITIGNORE,
    render_registry_readme,
)

REGISTRY_COMMAND_INVALID = DiagnosticCode("registry-command-invalid")
REGISTRY_AUDIT_WARNING = DiagnosticCode("registry-audit-warning")
# A report of what the audit did, as opposed to what it found. It carries no remediation
# because there is nothing to remedy — an operator reads it to know the check ran at all.
REGISTRY_AUDIT_NOTE = DiagnosticCode("registry-audit-note")


# The next step a refused registry command hands over. These are shared lines rather than
# one sentence per call site because the operator's
# next step is the same wherever the same problem is stated, and a distinct sentence per site
# invents distinctions they do not have. Every `aart …` written here is parsed by the shipped CLI in
# `tests/source_remediation_test.py`, so a command that stops existing fails the suite.
_REVIEW_AGAIN = (
    "the workspace moved between the review and the finalize; run the command again to review the "
    "current workspace, then repeat it with `--yes`",
)
_REVIEW_FIRST = (
    "run the same command without `--yes` to produce the review, approve it, then repeat the "
    "command with `--yes`",
)
_INITIALIZE = (
    "point `--source` at a registry checkout, or create one with "
    "`aart-cli maintain registry init --source-id SLUG --display-name NAME --yes`",
)
_CLEAR_PATH = (
    "move or remove whatever occupies that path in the checkout, then run the command again",
)
_ALREADY_A_REGISTRY = (
    "this checkout is already a registry: read it with `aart-cli maintain registry validate`, or "
    "initialize a different directory by pointing `--source` at it",
)
_LIST_PACKAGES = (
    "`aart-cli maintain registry validate` reports every package this registry holds",
)
_CANONICAL_ROOTS = (
    "restore the canonical `artifacts/` and `collections/` roots in `aart-cli-source.json`, then "
    "`aart-cli maintain registry validate`",
)
_SETUP_RECIPE = (
    "add the declared recipe and its `SETUP.md` to the package, or drop the setup declaration from "
    "its manifest, then adopt the change",
)


_IDENTITIES = (
    "make `registry_id` in `aart-cli-registry.json` and `source_id` in `aart-cli-source.json` the same "
    "value, then `aart-cli maintain registry validate`",
)


_PROVENANCE = (
    "a package adopted from a source repository gets its provenance from the adoption; a package "
    "without one stays a warning",
)
_DECLARE_LICENSE = ("declare the license in the artifact's source manifest, then adopt the change",)
_SECURITY_EVIDENCE = (
    "supply the per-object evidence under `security/index.json`, or accept that the audit reports "
    "installation risk as unassessed",
)
_SECURITY_REBUILD = (
    "the evidence describes a different registry state: regenerate it against this registry's "
    "approved content, then `aart-cli maintain registry audit`",
)
_SECURITY_RISK = (
    "read the attestation for that object and either correct the package or stop publishing it; "
    "the audit reports the risk rather than deciding it for you",
)


def _delivery(identity: ArtifactIdentity) -> tuple[str, ...]:
    """The next step for a package whose shipped shape is wrong, naming the package."""

    return (
        f"correct {identity}'s manifest in its source repository, then adopt or promote the change",
    )


def _error(message: str, remediation: tuple[str, ...]) -> Err:
    return Err(
        (Diagnostic(REGISTRY_COMMAND_INVALID, Severity.ERROR, message, remediation=remediation),)
    )


_REMOTE_ORIGIN = (
    "a Registry other people install from takes artifacts only from remote upstreams: adopt it "
    "from its upstream's Git URL with `aart-cli maintain upstream adopt --source . --url URL "
    "--ref REF --artifact KIND/NAME@VERSION`, on a branch that holds no version from a local "
    "checkout",
)


def _local_origin(version: str, location: object, *, refused: bool) -> Diagnostic:
    """A version promoted from a checkout on the maintainer's machine (INV-286).

    The location is the one the version itself records, so the finding says whose checkout it was.
    """

    where = f" ({location})" if isinstance(location, str) and location else ""
    return _diagnostic(
        f"{version} came from a local checkout{where}, not from a remote upstream",
        _REMOTE_ORIGIN,
        warning=not refused,
    )


_DEFAULT_BRANCH = (
    "the default branch others install from takes only what its upstream's default branch holds: "
    "adopt it again with `aart-cli maintain upstream adopt --source . --url URL --ref REF "
    "--artifact KIND/NAME@VERSION`, naming the default branch or a tag on it",
)


def _off_default_branch(
    version: str, url: object, record: object, *, refused: bool
) -> Diagnostic | None:
    """A remote version not shown to come from its upstream's default branch (INV-289).

    `upstream adopt` records whether the adopted commit is reachable from the upstream's default
    branch. A plain audit reports only a version recorded as off it; for the default branch, a
    version with no such record is refused too, because nothing shows where it came from.
    """

    where = f" of {url}" if isinstance(url, str) and url else ""
    if not isinstance(record, JsonObject):
        if not refused:
            return None
        message = (
            f"{version} was not adopted with `upstream adopt`, so nothing records that it came "
            f"from the default branch{where}"
        )
    elif record.get("default_branch") is True:
        return None
    elif record.get("default_branch") is False:
        ref = record.get("ref")
        message = f"{version} was adopted from {ref}, which is not on the default branch{where}"
    elif not refused:
        return None
    else:
        message = (
            f"{version} was adopted without a record of whether it is on the default branch{where}"
        )
    return _diagnostic(message, _DEFAULT_BRANCH, warning=not refused)


def _note(message: str) -> Diagnostic:
    return Diagnostic(REGISTRY_AUDIT_NOTE, Severity.INFO, message)


def _diagnostic(message: str, remediation: tuple[str, ...], *, warning: bool = False) -> Diagnostic:
    """One line of a `validate` or `audit` report, with what to do about it.

    A report is where these two commands state a problem, so a finding that names no next
    step is the same dead end as a refusal that names none. A warning gets one too — most of them
    describe a limit rather than a defect, and saying which is exactly what the operator needs.
    """

    return Diagnostic(
        REGISTRY_AUDIT_WARNING if warning else REGISTRY_COMMAND_INVALID,
        Severity.WARNING if warning else Severity.ERROR,
        message,
        remediation=remediation,
    )


def _files(snapshot: SourceSnapshot) -> Result[dict[str, SnapshotEntry]]:
    digest = source_snapshot_digest(snapshot)
    if isinstance(digest, Err):
        return _error("registry command requires one safe inert workspace snapshot", _CLEAR_PATH)
    return Ok({str(item.path): item for item in snapshot.entries})


def _path(raw: str) -> SafeRelativePath:
    parsed = parse_relative_path(raw)
    assert isinstance(parsed, Ok)
    return parsed.value


def _change(
    raw_path: str,
    before: SnapshotEntry | None,
    content: bytes,
    *,
    executable: bool = False,
) -> RegistryWorkspaceChange:
    before_digest = None if before is None else sha256_bytes(before.content)
    after_digest = sha256_bytes(content)
    if before is None:
        kind = WorkspaceChangeKind.ADDED
    elif before.content == content and before.executable == executable:
        kind = WorkspaceChangeKind.UNCHANGED
    else:
        kind = WorkspaceChangeKind.CHANGED
    return RegistryWorkspaceChange(
        _path(raw_path),
        kind,
        content,
        before_digest,
        after_digest,
        executable,
    )


def _removal(raw_path: str, before: SnapshotEntry) -> RegistryWorkspaceChange:
    return RegistryWorkspaceChange(
        _path(raw_path),
        WorkspaceChangeKind.REMOVED,
        b"",
        sha256_bytes(before.content),
        None,
        before.executable,
    )


def _project_changes(
    snapshot: SourceSnapshot,
    changes: tuple[RegistryWorkspaceChange, ...],
) -> Result[SourceSnapshot]:
    current = _files(snapshot)
    if isinstance(current, Err):
        return current
    output = dict(current.value)
    for change in changes:
        raw = str(change.path)
        before = output.get(raw)
        if before is not None and before.kind is not SnapshotEntryKind.FILE:
            return _error(f"registry change target is not a regular file: {raw}", _CLEAR_PATH)
        actual = None if before is None else sha256_bytes(before.content)
        if actual != change.before_digest:
            return _error(f"registry change precondition changed: {raw}", _REVIEW_AGAIN)
        if change.kind is WorkspaceChangeKind.REMOVED:
            # The directory entries stay: an emptied directory is still on disk after the file is
            # unlinked, and a projection that dropped it would disagree with the snapshot the
            # applier re-reads to verify itself.  Git does not track empty directories, so the
            # maintainer's commit is unaffected either way.
            del output[raw]
            continue
        output[raw] = SnapshotEntry(
            change.path,
            SnapshotEntryKind.FILE,
            change.content,
            change.executable,
        )
        for length in range(1, len(change.path.parts)):
            parent = SafeRelativePath(change.path.parts[:length])
            existing = output.get(str(parent))
            if existing is not None and existing.kind is not SnapshotEntryKind.DIRECTORY:
                return _error(f"registry change parent is not a directory: {parent}", _CLEAR_PATH)
            output.setdefault(
                str(parent),
                SnapshotEntry(parent, SnapshotEntryKind.DIRECTORY),
            )
    return Ok(SourceSnapshot(snapshot.origin, tuple(output.values())))


def _plan(
    operation: RegistryOperation,
    snapshot: SourceSnapshot,
    desired: tuple[tuple[str, bytes, bool], ...],
    *,
    prune_under: str | None = None,
) -> Result[RegistryWorkspacePlan]:
    """Plan exactly ``desired``; under ``prune_under``, also remove what ``desired`` no longer names.

    Pruning is opt-in and confined to one directory because every other operation writes a fixed set
    of derived documents and owns nothing else in the workspace.
    """

    current = _files(snapshot)
    if isinstance(current, Err):
        return current
    expected = source_snapshot_digest(snapshot)
    if isinstance(expected, Err):
        return expected
    kept = {path for path, _content, _executable in desired}
    changes = tuple(
        _change(path, current.value.get(path), content, executable=executable)
        for path, content, executable in sorted(desired)
    ) + (
        ()
        if prune_under is None
        else tuple(
            _removal(raw, entry)
            for raw, entry in sorted(current.value.items())
            if raw.startswith(f"{prune_under}/")
            and entry.kind is SnapshotEntryKind.FILE
            and raw not in kept
        )
    )
    projected = _project_changes(snapshot, changes)
    if isinstance(projected, Err):
        return projected
    next_digest = source_snapshot_digest(projected.value)
    if isinstance(next_digest, Err):
        return next_digest
    return Ok(
        RegistryWorkspacePlan(
            operation,
            expected.value,
            next_digest.value,
            changes,
            registry_workspace_review_digest(
                operation,
                expected.value,
                next_digest.value,
                changes,
            ),
        )
    )


def project_registry_workspace_plan(
    snapshot: SourceSnapshot,
    plan: RegistryWorkspacePlan,
) -> Result[SourceSnapshot]:
    current = source_snapshot_digest(snapshot)
    if isinstance(current, Err):
        return current
    if current.value != plan.expected_snapshot_digest:
        return _error("registry workspace changed after plan review", _REVIEW_AGAIN)
    projected = _project_changes(snapshot, plan.changes)
    if isinstance(projected, Err):
        return projected
    digest = source_snapshot_digest(projected.value)
    if isinstance(digest, Err) or digest.value != plan.next_snapshot_digest:
        return _error("registry plan no longer produces its reviewed snapshot", _REVIEW_AGAIN)
    return projected


def plan_registry_workspace_files(
    operation: RegistryOperation,
    snapshot: SourceSnapshot,
    desired: tuple[tuple[str, bytes, bool], ...],
) -> Result[RegistryWorkspacePlan]:
    """Build a reviewed plan for already-materialized deterministic managed files."""

    return _plan(operation, snapshot, desired)


def plan_registry_init(
    snapshot: SourceSnapshot,
    options: RegistryInitOptions,
) -> Result[RegistryWorkspacePlan]:
    files = _files(snapshot)
    if isinstance(files, Err):
        return files
    occupied = {"aart-cli-registry.json", "aart-cli-source.json"} & files.value.keys()
    if occupied:
        return _error("registry init refuses an existing registry workspace", _ALREADY_A_REGISTRY)
    # Every registry gets byte-identical files.  Where CI fetches AART from is a repository
    # variable, not something written in here at creation time, so these bytes never have to be
    # regenerated when a company moves the tool.
    templates = (
        (".gitignore", REGISTRY_GITIGNORE),
        (".github/workflows/aart-cli-registry.yml", REGISTRY_CI_WORKFLOW),
    )
    # The README is the one generated file a maintainer is meant to edit, so it is written when
    # absent and left alone otherwise -- never compared, never overwritten.  Managing it would
    # make the file people are supposed to change the file that puts the registry out of step
    # with the command that manages it, and a repository created on GitHub with "Add a README"
    # already has one.
    written_once = tuple(
        (path, content)
        for path, content in (
            (
                "README.md",
                render_registry_readme(
                    options.registry_id,
                    options.display_name,
                ),
            ),
            # The pin is the version of the tool creating the registry -- the same number `init`
            # already writes as `requires_aart.min_inclusive`.  No inference is involved: AART
            # knows its own version, which is exactly what the deleted origin stamp did not.
            (".aart-cli-version", f"{EXECUTABLE_VERSION}\n".encode("utf-8")),
        )
        if path not in files.value
    )
    for path, expected in templates:
        existing = files.value.get(path)
        if existing is not None and (
            existing.kind is not SnapshotEntryKind.FILE
            or existing.content != expected
            or existing.executable
        ):
            return _error(
                f"registry init refuses to overwrite an existing template: {path}", _CLEAR_PATH
            )
    bounds = VersionBounds(options.minimum_aart, options.maximum_aart_exclusive)
    registry = RegistryManifest(
        1,
        1,
        SourceId(options.registry_id),
        options.display_name,
        bounds,
        tuple(
            Capability(value)
            for value in (
                "artifact-manifest-v1",
                "lockfile-v1",
                "registry-entry-v1",
            )
        ),
        "main",
        (),
    )
    source = SourceManifest(
        1,
        1,
        SourceId(options.registry_id),
        options.display_name,
        bounds,
        (Capability("artifact-manifest-v1"),),
        (_path("artifacts"),),
        (_path("collections"),),
    )
    return _plan(
        RegistryOperation.INIT,
        snapshot,
        (
            *((path, content, False) for path, content in (*templates, *written_once)),
            (
                "aart-cli-registry.json",
                canonical_json_bytes(registry_manifest_to_json(registry)),
                False,
            ),
            (
                "aart-cli-source.json",
                canonical_json_bytes(source_manifest_to_json(source)),
                False,
            ),
        ),
    )


def _source_manifest(files: dict[str, SnapshotEntry]) -> Result[SourceManifest]:
    marker = files.get("aart-cli-source.json")
    if marker is None or marker.kind is not SnapshotEntryKind.FILE:
        return _error("registry workspace requires aart-cli-source.json", _INITIALIZE)
    parsed = parse_source_manifest(marker.content)
    if isinstance(parsed, Err):
        return parsed
    if parsed.value.artifact_roots != (
        _path("artifacts"),
    ) or parsed.value.collection_roots not in {
        (),
        (_path("collections"),),
    }:
        return _error(
            "registry maintainer commands require canonical artifacts/ and collections/ roots",
            _CANONICAL_ROOTS,
        )
    return parsed


def plan_registry_format(snapshot: SourceSnapshot) -> Result[RegistryWorkspacePlan]:
    files = _files(snapshot)
    if isinstance(files, Err):
        return files
    source = _source_manifest(files.value)
    if isinstance(source, Err):
        return source

    def is_protocol_document(path: str) -> bool:
        if path in {"aart-cli-registry.json", "aart-cli-source.json"}:
            return path.endswith(".json")
        parts = tuple(path.split("/"))
        for root in source.value.collection_roots:
            if parts[: len(root.parts)] == root.parts:
                return path.endswith(".json")
        for root in source.value.artifact_roots:
            if parts[: len(root.parts)] != root.parts:
                continue
            relative = parts[len(root.parts) :]
            return (
                len(relative) == 3 and relative[-1] in {"artifact.json", "provenance.json"}
            ) or (len(relative) == 4 and relative[-2:] == ("setup", "installer.json"))
        return False

    desired: list[tuple[str, bytes, bool]] = []
    for path, item in sorted(files.value.items()):
        if item.kind is not SnapshotEntryKind.FILE or not is_protocol_document(path):
            continue
        parsed = parse_json(item.content)
        if isinstance(parsed, Err):
            return parsed
        desired.append((path, canonical_json_bytes(parsed.value), item.executable))
    if not desired:
        return _error("registry format found no JSON documents", _INITIALIZE)
    return _plan(RegistryOperation.FORMAT, snapshot, tuple(desired))


def _registry_inputs(
    snapshot: SourceSnapshot,
) -> Result[tuple[RegistryManifest, SourceManifest]]:
    files = _files(snapshot)
    if isinstance(files, Err):
        return files
    registry_file = files.value.get("aart-cli-registry.json")
    if registry_file is None or registry_file.kind is not SnapshotEntryKind.FILE:
        return _error("registry workspace requires aart-cli-registry.json", _INITIALIZE)
    registry = parse_registry_manifest(registry_file.content)
    source = _source_manifest(files.value)
    if isinstance(registry, Err):
        return registry
    if isinstance(source, Err):
        return source
    if registry.value.registry_id != source.value.source_id:
        return _error("registry and source identities differ", _IDENTITIES)
    return Ok((registry.value, source.value))


def plan_promoted_registry_build(snapshot: SourceSnapshot) -> Result[RegistryWorkspacePlan]:
    """Rebuild what the approved representation derives, which is its two catalogs and nothing else.

    Version records, promotion records and package bytes are decisions somebody reviewed; a rebuild
    that rewrote them would be inventing approvals. The catalogs are computed from those decisions,
    so they are the only thing here that can be restored rather than re-decided (`B-057`).
    """

    records = read_registry_version_records(snapshot)
    if isinstance(records, Err):
        return records
    catalogs = registry_catalog_entries(snapshot, records.value)
    if isinstance(catalogs, Err):
        return catalogs
    return _plan(
        RegistryOperation.BUILD,
        snapshot,
        tuple((path, content, False) for path, content in catalogs.value),
    )


def validate_registry_workspace(
    snapshot: SourceSnapshot,
    *,
    executable_version: SemVer,
    available_capabilities: tuple[Capability, ...],
) -> Result[RegistryQualityReport]:
    """Check that an approved Registry's committed content is well formed and self-consistent.

    There is nothing generated left to require: the approved representation compiles no lock and no
    index, and its version records carry the digests the retired workspace kept in `aart.lock.json`.
    `registry_native_content` holds the registry to those records through `validate_promoted_registry`,
    which is the whole of what a second compiled catalog used to re-assert (`B-057`, CP-26.5).
    """

    diagnostics: list[Diagnostic] = []
    parsed = _registry_inputs(snapshot)
    if isinstance(parsed, Err):
        diagnostics.extend(parsed.diagnostics)
        return Ok(RegistryQualityReport((RegistryQualityCheck("validate", tuple(diagnostics)),)))
    registry, source = parsed.value
    files = _files(snapshot)
    assert isinstance(files, Ok)
    native = registry_native_content(
        snapshot,
        files.value,
        registry,
        executable_version=executable_version,
        available_capabilities=available_capabilities,
    )
    if isinstance(native, Err):
        diagnostics.extend(native.diagnostics)
    return Ok(RegistryQualityReport((RegistryQualityCheck("validate", tuple(diagnostics)),)))


def package_delivery_diagnostics(
    files: dict[str, SnapshotEntry],
    base: str,
    manifest: ArtifactManifest,
) -> tuple[Diagnostic, ...]:
    """Report a descriptor that launches a file consumers never receive.

    An error rather than a warning: unlike a missing licence, this is not a fact about the world the
    maintainer may accept. It is an artifact that cannot start on any consumer machine.

    Nothing in the consequence depends on where the bytes came from — the merge writes an empty
    entry either way — so the check runs for every package the audit walks.

    The audit is where it runs, not `registry validate`. `validate_registry_workspace` is also the
    consumer's gate on a candidate source, so a new hard failure there makes every registry already
    carrying such a descriptor unloadable on upgrade, for its subscribers as well as its maintainer.
    That would be a protocol break. `registry audit` is maintainer-side and is what the
    generated registry CI runs.
    """

    prefix = f"{base}/{manifest.payload.root}/"
    finding = describe_delivery(
        manifest.identity.kind,
        {
            raw.removeprefix(f"{base}/"): entry.content
            for raw, entry in files.items()
            if raw.startswith(prefix) and entry.kind is SnapshotEntryKind.FILE
        },
    )
    if finding is None:
        return ()
    identity = manifest.identity
    diagnostics: list[Diagnostic] = []
    if finding.referenced:
        diagnostics.append(
            _diagnostic(
                delivery_reference_message(identity, finding),
                _delivery(identity),
            )
        )
    if finding.starts_nothing:
        diagnostics.append(_diagnostic(mcp_descriptor_message(identity), _delivery(identity)))
    return tuple(diagnostics)


def audit_registry_workspace(
    snapshot: SourceSnapshot,
    *,
    executable_version: SemVer,
    available_capabilities: tuple[Capability, ...],
    for_default_branch: bool = False,
) -> Result[RegistryQualityReport]:
    """Audit committed registry content: a pure function of the snapshot, with no network.

    A version promoted from a local checkout, or adopted from off its upstream's default branch, is
    a warning, so a maintainer's trial Registry still publishes and is told. `for_default_branch`
    makes both errors, and also refuses a remote version with no adoption record saying it came
    from the default branch. The generated Registry CI passes it, so such a version never reaches
    the default branch others install from (INV-286, INV-289).
    """

    parsed = _registry_inputs(snapshot)
    if isinstance(parsed, Err):
        return Ok(RegistryQualityReport((RegistryQualityCheck("audit", parsed.diagnostics),)))
    registry, source = parsed.value
    files = _files(snapshot)
    assert isinstance(files, Ok)
    diagnostics: list[Diagnostic] = []
    native = registry_native_content(
        snapshot,
        files.value,
        registry,
        executable_version=executable_version,
        available_capabilities=available_capabilities,
    )
    if isinstance(native, Err):
        diagnostics.extend(native.diagnostics)
    roots = tuple(f"{root}/" for root in source.artifact_roots)
    owned = tuple(
        (path, item)
        for path, item in sorted(files.value.items())
        if item.kind is SnapshotEntryKind.FILE
        and path.endswith("/artifact.json")
        and any(path.startswith(root) for root in roots)
    )
    # `QA-015`: a registry holding nothing has nothing to be partial about. The finding below
    # describes a limit rather than a defect, and on an empty registry the limit is the whole state
    # of it, so it is reported as a note — what the audit did.
    nothing_to_assess = not owned
    if nothing_to_assess:
        diagnostics.append(
            _note("registry contains no artifacts, so there is no provenance to check")
        )
    for path, item in owned:
        manifest = parse_artifact_manifest(item.content, path=path)
        if isinstance(manifest, Err):
            diagnostics.extend(manifest.diagnostics)
            continue
        base = path.removesuffix("/artifact.json")
        provenance_path = f"{base}/provenance.json"
        provenance = files.value.get(provenance_path)
        if provenance is None:
            diagnostics.append(
                _diagnostic(
                    f"owned package has no provenance document: {manifest.value.identity}",
                    _PROVENANCE,
                    warning=True,
                )
            )
        elif provenance.kind is not SnapshotEntryKind.FILE:
            diagnostics.append(
                _diagnostic(f"provenance is not a file: {provenance_path}", _CLEAR_PATH)
            )
        else:
            parsed_provenance = parse_provenance(provenance.content, path=provenance_path)
            if isinstance(parsed_provenance, Err):
                diagnostics.extend(parsed_provenance.diagnostics)
            elif parsed_provenance.value.origin.kind == "local":
                diagnostics.append(
                    _local_origin(
                        f"{manifest.value.identity}@{base.rsplit('/', 1)[-1]}",
                        parsed_provenance.value.origin.url,
                        refused=for_default_branch,
                    )
                )
            else:
                branch = _off_default_branch(
                    f"{manifest.value.identity}@{base.rsplit('/', 1)[-1]}",
                    parsed_provenance.value.origin.url,
                    dict(parsed_provenance.value.extensions).get(REPOSITORY_ADOPTION_RECORD),
                    refused=for_default_branch,
                )
                if branch is not None:
                    diagnostics.append(branch)
        # What a consumer receives from an `mcp` package is a property of the package.
        diagnostics.extend(package_delivery_diagnostics(files.value, base, manifest.value))
        if manifest.value.license is None:
            diagnostics.append(
                _diagnostic(
                    f"owned package has no declared license: {manifest.value.identity}",
                    _DECLARE_LICENSE,
                    warning=True,
                )
            )
        if manifest.value.setup is not None:
            recipe = f"{base}/{manifest.value.setup.recipe}"
            recipe_file = files.value.get(recipe)
            if recipe_file is None or recipe_file.kind is not SnapshotEntryKind.FILE:
                diagnostics.append(
                    _diagnostic(f"declared setup recipe is missing: {recipe}", _SETUP_RECIPE)
                )
    # A pinned reference holds no package, only the record of where it is: `revision` is the pin,
    # and `local:` is a checkout on the maintainer's machine.
    for path, item in sorted(files.value.items()):
        parts = path.removesuffix(".json").split("/")
        if item.kind is not SnapshotEntryKind.FILE or len(parts) != 4 or parts[0] != "references":
            continue
        record = parse_json(item.content)
        if not isinstance(record, Ok) or not isinstance(record.value, JsonObject):
            continue
        revision = record.value.get("revision")
        if isinstance(revision, str) and source_revision_kind(revision) == "local":
            diagnostics.append(
                _local_origin(
                    f"{parts[1]}/{parts[2]}@{parts[3]}",
                    record.value.get("source"),
                    refused=for_default_branch,
                )
            )
        else:
            # `upstream adopt` writes only self-contained versions, so a pinned reference never
            # carries the record (INV-289).
            branch = _off_default_branch(
                f"{parts[1]}/{parts[2]}@{parts[3]}",
                record.value.get("source"),
                None,
                refused=for_default_branch,
            )
            if branch is not None:
                diagnostics.append(branch)
    security_file = files.value.get("security/index.json")
    if security_file is None:
        diagnostics.append(
            _note("registry contains no artifacts, so there is no installation risk to assess")
            if nothing_to_assess
            else _diagnostic(
                "no per-object installation-risk evidence was supplied to registry audit",
                _SECURITY_EVIDENCE,
                warning=True,
            )
        )
    elif security_file.kind is not SnapshotEntryKind.FILE:
        diagnostics.append(
            _diagnostic("registry security index is not a regular file", _CLEAR_PATH)
        )
    else:
        security_index = parse_security_index(security_file.content)
        if isinstance(security_index, Err):
            diagnostics.extend(security_index.diagnostics)
        else:
            documents = []
            missing_document = False
            for security_entry in security_index.value.entries:
                document = files.value.get(str(security_entry.path))
                if document is None or document.kind is not SnapshotEntryKind.FILE:
                    diagnostics.append(
                        _diagnostic(
                            f"registry security index document is missing: {security_entry.path}",
                            _SECURITY_EVIDENCE,
                        )
                    )
                    missing_document = True
                    continue
                documents.append((security_entry.path, document.content))
            if not missing_document:
                verified = verify_security_index(security_index.value, tuple(documents))
                if isinstance(verified, Err):
                    diagnostics.extend(verified.diagnostics)
                else:
                    # The evidence set claims a registry identity and a registry content state.
                    # Both are recomputed from this snapshot rather than read out of a catalog the
                    # same commit could have rewritten, so a tampered registry cannot assert the
                    # state its evidence was made for (D-319, CP-26.5).
                    registry_state = registry_state_digest(snapshot)
                    if isinstance(registry_state, Err) or isinstance(native, Err):
                        diagnostics.append(
                            _diagnostic(
                                "registry security index requires readable approved content",
                                _SECURITY_REBUILD,
                            )
                        )
                    elif (
                        security_index.value.registry_id != registry.registry_id
                        or security_index.value.registry_inputs_digest != registry_state.value
                    ):
                        diagnostics.append(
                            _diagnostic(
                                "registry security index identity differs from this registry",
                                _SECURITY_REBUILD,
                            )
                        )
                    else:
                        expected_objects = {item.object_digest for item in native.value[0]}
                        evidence_objects = {
                            item.cache_key.object_digest for item in verified.value.attestations
                        }
                        missing_objects = expected_objects - evidence_objects
                        extra_objects = evidence_objects - expected_objects
                        if missing_objects:
                            diagnostics.append(
                                _diagnostic(
                                    "registry security index lacks evidence for one or more "
                                    "approved objects",
                                    _SECURITY_REBUILD,
                                )
                            )
                        if extra_objects:
                            diagnostics.append(
                                _diagnostic(
                                    "registry security index contains evidence for unknown objects",
                                    _SECURITY_REBUILD,
                                )
                            )
                        for attestation in verified.value.attestations:
                            risk = attestation.assessment.installation_risk
                            if risk is InstallationRisk.CRITICAL:
                                diagnostics.append(
                                    _diagnostic(
                                        "registry security evidence reports critical installation risk "
                                        f"for {attestation.cache_key.object_digest}",
                                        _SECURITY_RISK,
                                    )
                                )
                            elif risk in {InstallationRisk.HIGH, InstallationRisk.UNKNOWN}:
                                diagnostics.append(
                                    _diagnostic(
                                        "registry security evidence requires review because installation "
                                        f"risk is {risk.value} for {attestation.cache_key.object_digest}",
                                        _SECURITY_RISK,
                                        warning=True,
                                    )
                                )
    return Ok(RegistryQualityReport((RegistryQualityCheck("audit", tuple(diagnostics)),)))


def test_registry_compatibility(
    snapshot: SourceSnapshot,
    *,
    minimum: SemVer,
    latest: SemVer,
    available_capabilities: tuple[Capability, ...],
) -> Result[RegistryQualityReport]:
    checks = []
    for name, version in (("minimum", minimum), ("latest", latest)):
        result = validate_registry_workspace(
            snapshot,
            executable_version=version,
            available_capabilities=available_capabilities,
        )
        assert isinstance(result, Ok)
        diagnostics = tuple(
            diagnostic for check in result.value.checks for diagnostic in check.diagnostics
        )
        checks.append(RegistryQualityCheck(name, diagnostics))
    return Ok(RegistryQualityReport(tuple(checks)))
