"""Symlink-safe durable storage for Candidate lifecycle history.

Compiled artifact envelopes are immutable and content-addressed. A small per-Source index points at
those envelopes and is the only value atomically replaced when Source Sync establishes a newer
scan. Objects are written first and retained, so interruption can leave unreferenced evidence but
can never make a partial scan current.
"""

from __future__ import annotations

import os
import posixpath
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agent_artifacts.application.candidate_history import (
    parse_source_scan,
    serialize_source_scan,
    source_scan_object_digests,
)
from agent_artifacts.application.maintainer import SourceScan
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.sources.model import SourceStorePaths
from agent_artifacts.store.model import ObjectCandidate, parse_object_candidate

__all__ = [
    "CANDIDATE_STORE_INVALID",
    "CANDIDATE_STORE_UNAVAILABLE",
    "CandidateHistoryPaths",
    "CandidateHistoryReceipt",
    "candidate_history_paths",
    "read_candidate_history",
    "write_candidate_history",
]

CANDIDATE_STORE_INVALID = DiagnosticCode("candidate-store-invalid")
CANDIDATE_STORE_UNAVAILABLE = DiagnosticCode("candidate-store-unavailable")
_MAX_INDEX_BYTES = 16 * 1024 * 1024
_MAX_OBJECT_BYTES = 150 * 1024 * 1024


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, redact_text(message)),))


@dataclass(frozen=True, slots=True)
class CandidateHistoryPaths:
    source_root: str
    root: str
    objects: str
    index_file: str

    def __post_init__(self) -> None:
        values = (self.source_root, self.root, self.objects, self.index_file)
        if any(
            not posixpath.isabs(value) or posixpath.normpath(value) != value for value in values
        ):
            raise ValueError("Candidate history paths must be normalized and absolute")
        if self.source_root == "/" or (
            self.root,
            self.objects,
            self.index_file,
        ) != (
            posixpath.join(self.source_root, "candidates"),
            posixpath.join(self.source_root, "candidates", "objects", "sha256"),
            posixpath.join(self.source_root, "candidates", "current.json"),
        ):
            raise ValueError("Candidate history paths must use the managed Source layout")


@dataclass(frozen=True, slots=True)
class CandidateHistoryReceipt:
    index_path: str
    revision: str
    object_digests: tuple[ObjectDigest, ...]

    def __post_init__(self) -> None:
        if (
            not posixpath.isabs(self.index_path)
            or posixpath.normpath(self.index_path) != self.index_path
            or not self.revision
            or tuple(sorted(set(self.object_digests), key=lambda item: item.value))
            != self.object_digests
        ):
            raise ValueError("Candidate history receipt must describe one canonical write")


def candidate_history_paths(source: SourceStorePaths) -> CandidateHistoryPaths:
    root = posixpath.join(source.root, "candidates")
    return CandidateHistoryPaths(
        source.root,
        root,
        posixpath.join(root, "objects", "sha256"),
        posixpath.join(root, "current.json"),
    )


def _real_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(os.stat(path, follow_symlinks=False).st_mode)
    except OSError:
        return False


def _components(paths: CandidateHistoryPaths) -> tuple[Path, ...]:
    root = Path(paths.root)
    return (
        Path(paths.source_root),
        root,
        root / "objects",
        Path(paths.objects),
    )


def _existing_components_are_real(paths: CandidateHistoryPaths) -> bool:
    return all(not os.path.lexists(path) or _real_directory(path) for path in _components(paths))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _prepare(paths: CandidateHistoryPaths) -> Result[None]:
    if not _existing_components_are_real(paths):
        return _error(
            CANDIDATE_STORE_INVALID,
            "Candidate history path is not a real directory",
        )
    try:
        for component in _components(paths):
            component.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not _real_directory(component):
                return _error(
                    CANDIDATE_STORE_INVALID,
                    "Candidate history path is not a real directory",
                )
            os.chmod(component, 0o700, follow_symlinks=False)
        return Ok(None)
    except OSError as error:
        return _error(
            CANDIDATE_STORE_UNAVAILABLE,
            f"cannot prepare Candidate history: {error}",
        )


def _read_file(path: Path, maximum: int, label: str) -> Result[bytes | None]:
    try:
        before = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return Ok(None)
    except OSError as error:
        return _error(CANDIDATE_STORE_UNAVAILABLE, f"cannot inspect {label}: {error}")
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        return _error(CANDIDATE_STORE_INVALID, f"{label} is not a bounded real file")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
            ):
                return _error(CANDIDATE_STORE_INVALID, f"{label} changed while opening")
            content = stream.read(maximum + 1)
    except OSError as error:
        return _error(CANDIDATE_STORE_UNAVAILABLE, f"cannot read {label}: {error}")
    if len(content) != before.st_size:
        return _error(CANDIDATE_STORE_INVALID, f"{label} changed while reading")
    return Ok(content)


def _object_path(paths: CandidateHistoryPaths, digest: ObjectDigest) -> Path:
    return Path(paths.objects) / f"{digest.value}.json"


def _read_object(
    paths: CandidateHistoryPaths,
    digest: ObjectDigest,
) -> Result[ObjectCandidate]:
    content = _read_file(
        _object_path(paths, digest),
        _MAX_OBJECT_BYTES,
        "Candidate compiled object",
    )
    if isinstance(content, Err):
        return content
    if content.value is None:
        return _error(
            CANDIDATE_STORE_INVALID,
            f"candidate compiled object is missing: {digest}",
        )
    parsed = parse_object_candidate(content.value, digest)
    if isinstance(parsed, Err):
        return _error(
            CANDIDATE_STORE_INVALID,
            f"Candidate compiled object is corrupt or misaddressed: {digest}",
        )
    return parsed


def read_candidate_history(paths: CandidateHistoryPaths) -> Result[SourceScan | None]:
    if not isinstance(paths, CandidateHistoryPaths):
        raise ValueError("reading Candidate history needs managed paths")
    if not _existing_components_are_real(paths):
        return _error(
            CANDIDATE_STORE_INVALID,
            "Candidate history path is not a real directory",
        )
    index = _read_file(Path(paths.index_file), _MAX_INDEX_BYTES, "Candidate history index")
    if isinstance(index, Err):
        return index
    if index.value is None:
        return Ok(None)
    referenced = source_scan_object_digests(index.value)
    if isinstance(referenced, Err):
        return referenced
    objects: list[ObjectCandidate] = []
    for digest in referenced.value:
        loaded = _read_object(paths, digest)
        if isinstance(loaded, Err):
            return loaded
        objects.append(loaded.value)
    return parse_source_scan(index.value, tuple(objects))


def _publish_object(paths: CandidateHistoryPaths, candidate: ObjectCandidate) -> Result[None]:
    target = _object_path(paths, candidate.digest)
    existing = _read_file(target, _MAX_OBJECT_BYTES, "Candidate compiled object")
    if isinstance(existing, Err):
        return existing
    if existing.value is not None:
        parsed = parse_object_candidate(existing.value, candidate.digest)
        if isinstance(parsed, Err) or parsed.value != candidate:
            return _error(
                CANDIDATE_STORE_INVALID,
                f"Candidate object identity already contains different content: {candidate.digest}",
            )
        return Ok(None)
    stage: Path | None = None
    try:
        descriptor, raw_stage = tempfile.mkstemp(prefix=".stage-", dir=paths.objects)
        stage = Path(raw_stage)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(candidate.canonical_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(stage, target, follow_symlinks=False)
        except FileExistsError:
            raced = _read_object(paths, candidate.digest)
            if isinstance(raced, Ok) and raced.value == candidate:
                return Ok(None)
            if isinstance(raced, Err):
                return raced
            return _error(
                CANDIDATE_STORE_INVALID,
                f"concurrent Candidate object write published different content: {candidate.digest}",
            )
        _fsync_directory(Path(paths.objects))
        return Ok(None)
    except OSError as error:
        return _error(
            CANDIDATE_STORE_UNAVAILABLE,
            f"cannot publish Candidate compiled object: {error}",
        )
    finally:
        if stage is not None:
            try:
                stage.unlink()
            except OSError:
                pass


def _write_index(paths: CandidateHistoryPaths, content: bytes) -> Result[None]:
    stage: Path | None = None
    try:
        descriptor, raw_stage = tempfile.mkstemp(prefix=".stage-", dir=paths.root)
        stage = Path(raw_stage)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, paths.index_file)
        stage = None
        os.chmod(paths.index_file, 0o600, follow_symlinks=False)
        _fsync_directory(Path(paths.root))
        return Ok(None)
    except OSError as error:
        return _error(
            CANDIDATE_STORE_UNAVAILABLE,
            f"cannot publish Candidate history index: {error}",
        )
    finally:
        if stage is not None:
            try:
                stage.unlink()
            except OSError:
                pass


def write_candidate_history(
    paths: CandidateHistoryPaths,
    scan: SourceScan,
) -> Result[CandidateHistoryReceipt]:
    if not isinstance(paths, CandidateHistoryPaths) or not isinstance(scan, SourceScan):
        raise ValueError("writing Candidate history needs managed paths and one Source Scan")
    serialized = serialize_source_scan(scan)
    if isinstance(serialized, Err):
        return serialized
    prepared = _prepare(paths)
    if isinstance(prepared, Err):
        return prepared
    for candidate in serialized.value.objects:
        published = _publish_object(paths, candidate)
        if isinstance(published, Err):
            return published
    current = read_candidate_history(paths)
    if isinstance(current, Err):
        return current
    written = _write_index(paths, serialized.value.index)
    if isinstance(written, Err):
        return written
    digests = tuple(item.digest for item in serialized.value.objects)
    return Ok(CandidateHistoryReceipt(paths.index_file, scan.revision, digests))
