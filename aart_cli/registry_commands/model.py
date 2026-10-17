"""Frozen command plans, reports, and options for registry maintenance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from aart_cli.domain.diagnostics import Diagnostic, Severity, sort_diagnostics
from aart_cli.domain.identifiers import ObjectDigest
from aart_cli.protocol.hashing import json_digest, sha256_bytes
from aart_cli.protocol.json import JsonArray, JsonObject
from aart_cli.protocol.paths import SafeRelativePath
from aart_cli.protocol.semver import SemVer

_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, ObjectDigest)
        and value.algorithm == "sha256"
        and _DIGEST_RE.fullmatch(value.value) is not None
    )


def _one_safe_line(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and all(character.isprintable() for character in value)
    )


class RegistryOperation(str, Enum):
    INIT = "init"
    COLLECTION = "collection"
    FORMAT = "format"
    LOCK = "lock"
    BUILD = "build"
    MIGRATE = "migrate"
    PUBLISH = "publish"
    CANDIDATE_PROMOTION = "candidate-promotion"


class WorkspaceChangeKind(str, Enum):
    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    # A plan removing a managed file, such as a retired workspace document.
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class RegistryInitOptions:
    registry_id: str
    display_name: str
    minimum_aart: SemVer
    maximum_aart_exclusive: SemVer

    def __post_init__(self) -> None:
        if (
            _SLUG_RE.fullmatch(self.registry_id) is None
            or not _one_safe_line(self.display_name)
            or not isinstance(self.minimum_aart, SemVer)
            or not isinstance(self.maximum_aart_exclusive, SemVer)
            or not self.minimum_aart < self.maximum_aart_exclusive
        ):
            raise ValueError("registry init options are invalid")


@dataclass(frozen=True, slots=True, order=True)
class RegistryWorkspaceChange:
    path: SafeRelativePath
    kind: WorkspaceChangeKind
    content: bytes
    before_digest: ObjectDigest | None
    # `None` only for a removal, where there is no resulting file to name.  Every other kind carries
    # the digest of exactly the bytes it writes.
    after_digest: ObjectDigest | None
    executable: bool = False

    def __post_init__(self) -> None:
        removal = self.kind is WorkspaceChangeKind.REMOVED
        if (
            not isinstance(self.path, SafeRelativePath)
            or not _managed_path(self.path)
            or not isinstance(self.kind, WorkspaceChangeKind)
            or not isinstance(self.content, bytes)
            or not isinstance(self.executable, bool)
            or (not removal and not _valid_digest(self.after_digest))
            or (not removal and sha256_bytes(self.content) != self.after_digest)
            or (self.before_digest is not None and not _valid_digest(self.before_digest))
        ):
            raise ValueError("registry workspace change is invalid")
        if removal and (
            self.after_digest is not None
            or self.content != b""
            or not _valid_digest(self.before_digest)
        ):
            raise ValueError("removed workspace file names only what it removes")
        if self.kind is WorkspaceChangeKind.ADDED and self.before_digest is not None:
            raise ValueError("added workspace file cannot have a previous digest")
        if self.kind is WorkspaceChangeKind.CHANGED and (
            self.before_digest is None or self.before_digest == self.after_digest
        ):
            raise ValueError("changed workspace file requires distinct digests")
        if self.kind is WorkspaceChangeKind.UNCHANGED and self.before_digest != self.after_digest:
            raise ValueError("unchanged workspace file requires equal digests")


def _managed_path(path: SafeRelativePath) -> bool:
    raw = str(path)
    if raw in {
        "aart-cli-registry.json",
        "aart-cli-source.json",
        ".gitignore",
        # A plan may *write* these two; that is not the same as AART owning them.  `init` writes
        # each only when it is absent and never compares it afterwards, so these entries permit
        # the one write rather than claiming the file.  `.aart-cli-version` is the registry's own pin,
        # bumped by a person in a pull request; the README is the page they read.
        "README.md",
        ".aart-cli-version",
        ".github/workflows/aart-cli-registry.yml",
    }:
        return True
    # `security/` carries committed assessment evidence.  It is not a registry input — the inputs
    # digest ignores it — so a plan may write evidence without making the lock and index stale.
    return path.parts[0] in {
        "entries",
        "artifacts",
        "collections",
        "security",
        "registry",
        "references",
    }


def registry_workspace_review_digest(
    operation: RegistryOperation,
    expected_snapshot_digest: ObjectDigest,
    next_snapshot_digest: ObjectDigest,
    changes: tuple[RegistryWorkspaceChange, ...],
) -> ObjectDigest:
    ordered = tuple(sorted(changes, key=lambda item: str(item.path)))
    return json_digest(
        JsonObject(
            (
                (
                    "changes",
                    JsonArray(
                        tuple(
                            JsonObject(
                                (
                                    (
                                        "after_digest",
                                        None
                                        if item.after_digest is None
                                        else str(item.after_digest),
                                    ),
                                    (
                                        "before_digest",
                                        None
                                        if item.before_digest is None
                                        else str(item.before_digest),
                                    ),
                                    ("executable", item.executable),
                                    ("kind", item.kind.value),
                                    ("path", str(item.path)),
                                )
                            )
                            for item in ordered
                        )
                    ),
                ),
                ("expected_snapshot_digest", str(expected_snapshot_digest)),
                ("next_snapshot_digest", str(next_snapshot_digest)),
                ("operation", operation.value),
            )
        )
    )


@dataclass(frozen=True, slots=True)
class RegistryWorkspacePlan:
    operation: RegistryOperation
    expected_snapshot_digest: ObjectDigest
    next_snapshot_digest: ObjectDigest
    changes: tuple[RegistryWorkspaceChange, ...]
    review_digest: ObjectDigest

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.changes, key=lambda item: str(item.path)))
        paths = tuple(item.path for item in ordered)
        if (
            not isinstance(self.operation, RegistryOperation)
            or not _valid_digest(self.expected_snapshot_digest)
            or not _valid_digest(self.next_snapshot_digest)
            or not ordered
            or len(set(paths)) != len(paths)
            or not _valid_digest(self.review_digest)
            or self.review_digest
            != registry_workspace_review_digest(
                self.operation,
                self.expected_snapshot_digest,
                self.next_snapshot_digest,
                ordered,
            )
        ):
            raise ValueError("registry workspace plan is invalid")
        object.__setattr__(self, "changes", ordered)

    @property
    def changed_paths(self) -> int:
        return sum(item.kind is not WorkspaceChangeKind.UNCHANGED for item in self.changes)


@dataclass(frozen=True, slots=True)
class RegistryApplyCommand:
    plan: RegistryWorkspacePlan

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RegistryWorkspacePlan):
            raise ValueError("registry apply command requires an exact reviewed plan")


@dataclass(frozen=True, slots=True)
class RegistryApplyReceipt:
    review_digest: ObjectDigest
    snapshot_digest: ObjectDigest
    changed_paths: int

    def __post_init__(self) -> None:
        if (
            not _valid_digest(self.review_digest)
            or not _valid_digest(self.snapshot_digest)
            or not isinstance(self.changed_paths, int)
            or isinstance(self.changed_paths, bool)
            or self.changed_paths < 0
        ):
            raise ValueError("registry apply receipt is invalid")


@dataclass(frozen=True, slots=True)
class RegistryQualityCheck:
    name: str
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if _SLUG_RE.fullmatch(self.name) is None:
            raise ValueError("registry quality check name must be a slug")
        object.__setattr__(self, "diagnostics", sort_diagnostics(self.diagnostics))

    @property
    def passed(self) -> bool:
        return not any(item.severity is Severity.ERROR for item in self.diagnostics)


@dataclass(frozen=True, slots=True)
class RegistryQualityReport:
    checks: tuple[RegistryQualityCheck, ...]

    def __post_init__(self) -> None:
        if not self.checks or len({item.name for item in self.checks}) != len(self.checks):
            raise ValueError("registry quality report requires unique checks")

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.checks)
