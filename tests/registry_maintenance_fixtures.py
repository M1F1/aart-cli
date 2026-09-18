from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.json import canonical_json_bytes, parse_json
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path

NATIVE_FIXTURE = Path("tests/fixtures/protocol/native-source-v1")


def _file(path: str, content: bytes) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content)


def tree_snapshot(root: Path, origin: SnapshotOrigin) -> SourceSnapshot:
    entries: list[SnapshotEntry] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        parsed = parse_relative_path(relative)
        assert isinstance(parsed, Ok)
        if path.is_dir():
            entries.append(SnapshotEntry(parsed.value, SnapshotEntryKind.DIRECTORY))
        else:
            entries.append(
                SnapshotEntry(
                    parsed.value,
                    SnapshotEntryKind.FILE,
                    path.read_bytes(),
                    bool(path.stat().st_mode & 0o111),
                )
            )
    return SourceSnapshot(origin, tuple(entries))


def _canonical(document: dict) -> bytes:
    parsed = parse_json(json.dumps(document).encode())
    assert isinstance(parsed, Ok), parsed
    return canonical_json_bytes(parsed.value)


def empty_registry_snapshot() -> SourceSnapshot:
    registry = {
        "schema_version": 1,
        "protocol_version": 1,
        "registry_id": "test-registry",
        "display_name": "Test Registry",
        "requires_aart": {"min_inclusive": "0.0.1", "max_exclusive": "3.0.0"},
        "required_capabilities": [],
        "default_channel": "main",
        "services": {},
    }
    source = {
        "schema_version": 1,
        "protocol_version": 1,
        "source_id": "test-registry",
        "display_name": "Test Registry",
        "requires_aart": {"min_inclusive": "0.0.1", "max_exclusive": "3.0.0"},
        "required_capabilities": [],
        "artifact_roots": ["artifacts"],
        "collection_roots": [],
    }
    # Canonical bytes, because every fixture built on top of this one is a Registry that `format`
    # must find nothing to do in; a fixture spelled differently from what AART writes would make
    # `changed_paths == 0` unreachable for an approved Registry (CP-26.5).
    return SourceSnapshot(
        SnapshotOrigin.LOCAL,
        (
            _file("aart-registry.json", _canonical(registry)),
            _file("aart-source.json", _canonical(source)),
        ),
    )


def native_snapshot() -> SourceSnapshot:
    return tree_snapshot(NATIVE_FIXTURE, SnapshotOrigin.IMMUTABLE_GIT)


def renamed_native_snapshot(name: str) -> SourceSnapshot:
    """The reference snapshot with only the ``code-review`` package renamed.

    The rename must follow the path, never every manifest in the snapshot: a package whose
    directory was not renamed keeps its own identity, and rewriting its ``name`` would produce a
    manifest that disagrees with its package path — which the loader correctly rejects.
    """

    entries: list[SnapshotEntry] = []
    for entry in native_snapshot().entries:
        original = str(entry.path)
        raw = original.replace("/code-review", f"/{name}")
        parsed = parse_relative_path(raw)
        assert isinstance(parsed, Ok)
        content = entry.content
        if raw != original:
            if raw.endswith("/artifact.json"):
                value = json.loads(content)
                value["name"] = name
                content = json.dumps(value).encode()
            elif raw.endswith("/payload/SKILL.md"):
                content = content.replace(b"name: code-review", f"name: {name}".encode())
        entries.append(SnapshotEntry(parsed.value, entry.kind, content, entry.executable))
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, tuple(entries))


def registry_with_owned_package() -> SourceSnapshot:
    base = empty_registry_snapshot()
    native = native_snapshot()
    owned = tuple(
        SnapshotEntry(entry.path, entry.kind, entry.content, entry.executable)
        for entry in native.entries
        if str(entry.path).startswith("artifacts/")
    )
    return SourceSnapshot(SnapshotOrigin.LOCAL, (*base.entries, *owned))


def replace_snapshot_file(
    snapshot: SourceSnapshot,
    path: str,
    content: bytes,
) -> SourceSnapshot:
    return SourceSnapshot(
        snapshot.origin,
        tuple(
            SnapshotEntry(entry.path, entry.kind, content, entry.executable)
            if str(entry.path) == path
            else entry
            for entry in snapshot.entries
        ),
    )


def append_snapshot_file(
    snapshot: SourceSnapshot,
    path: str,
    content: bytes,
) -> SourceSnapshot:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SourceSnapshot(
        snapshot.origin,
        (*snapshot.entries, SnapshotEntry(parsed.value, SnapshotEntryKind.FILE, content)),
    )


def snapshot_file(snapshot: SourceSnapshot, path: str) -> bytes:
    return next(entry.content for entry in snapshot.entries if str(entry.path) == path)


def without_snapshot_paths(snapshot: SourceSnapshot, *paths: str) -> SourceSnapshot:
    removed = set(paths)
    return SourceSnapshot(
        snapshot.origin,
        tuple(entry for entry in snapshot.entries if str(entry.path) not in removed),
    )


def approved_registry_snapshot(
    *,
    names: tuple[str, ...] = ("github-mcp",),
    version: str = "1.0.0",
    registry_alias: str = "company",
) -> SourceSnapshot:
    """An initialized Registry holding one approved, vendored version per name.

    Built through the same promotion the maintainer runs, so the fixture cannot claim a shape the
    product does not write: `registry/versions/`, `registry/promotions/`, both derived catalogs and
    one package per version under `artifacts/<kind>/<name>/<version>/`.
    """

    from agent_artifacts.application.maintainer import reconcile_source_scan
    from agent_artifacts.application.promotion import (
        PromotionEvidence,
        plan_bulk_promotion,
        project_promotion,
    )
    from agent_artifacts.domain.candidates import assess_candidate
    from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
    from agent_artifacts.protocol.authoring import compile_author_snapshot

    entries = []
    for name in names:
        manifest = {
            "schema": "aart.dev/mcp/v1",
            "artifact": {"name": name, "kind": "mcp", "version": version},
            "payload": {"include": ["server.py"]},
            "transport": {"type": "stdio"},
            "runtime": {"type": "python", "version": ">=3.11"},
            "launch": {"type": "python", "entrypoint": "server.py"},
        }
        entries.append(_file(f"{name}/aart.json", json.dumps(manifest).encode()))
        entries.append(_file(f"{name}/server.py", f"print('{name}')\n".encode()))
    revision = "a" * 40
    compiled = compile_author_snapshot(
        SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, tuple(entries)),
        source_alias=SourceAlias("authors"),
        source="https://git.example/servers.git",
        revision=revision,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        revision,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias(registry_alias),
    )
    assert isinstance(scanned, Ok), scanned
    bundles = tuple(
        dataclasses.replace(bundle, candidate=assess_candidate(bundle.candidate))
        for bundle in scanned.value.active
    )
    assert len(bundles) == len(names), bundles
    base = empty_registry_snapshot()
    evidence = tuple(
        (
            bundle.candidate.id,
            PromotionEvidence(
                ObjectDigest("sha256", "7" * 64),
                ObjectDigest("sha256", "8" * 64),
                (),
            ),
        )
        for bundle in bundles
    )
    planned = plan_bulk_promotion(base, bundles, evidence=evidence, approved=())
    assert isinstance(planned, Ok), planned
    projected = project_promotion(base, planned.value)
    assert isinstance(projected, Ok), projected
    return SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, projected.value.entries)


def write_snapshot(root: Path, snapshot: SourceSnapshot) -> Path:
    """Materialize a snapshot as a real checkout, so a CLI gate can read what a fixture built."""

    for entry in snapshot.entries:
        path = root / str(entry.path)
        if entry.kind is SnapshotEntryKind.DIRECTORY:
            path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(entry.content)
        if entry.executable:
            path.chmod(path.stat().st_mode | 0o111)
    return root
