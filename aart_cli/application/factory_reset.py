"""Pure planning for deleting only AART-owned per-user application state."""

from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import dataclass
from enum import Enum

from aart_cli.configuration.paths import ConfigPaths, config_lock_directory
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result


class FactoryResetTargetKind(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True, slots=True)
class FactoryResetTarget:
    path: str
    kind: FactoryResetTargetKind


@dataclass(frozen=True, slots=True)
class FactoryResetPlan:
    targets: tuple[FactoryResetTarget, ...]
    review_digest: str


def _error(message: str) -> Err:
    return Err(
        (
            Diagnostic(
                DiagnosticCode("factory-reset-invalid"),
                Severity.ERROR,
                message,
                remediation=("correct the path environment before retrying factory reset",),
            ),
        )
    )


def _inside_home(path: str, home: str) -> bool:
    try:
        return posixpath.commonpath((path, home)) == home and path != home
    except ValueError:
        return False


def plan_factory_reset(paths: ConfigPaths, *, home: str) -> Result[FactoryResetPlan]:
    """Name the exact config/data/cache entries a reset may remove.

    The suffix checks are intentional defence in depth: resolving an environment variable to a
    broad directory must not turn a request for application reset into deletion of that directory.
    """

    home = posixpath.normpath(home)
    candidates = (
        FactoryResetTarget(paths.user_config_file, FactoryResetTargetKind.FILE),
        FactoryResetTarget(config_lock_directory(paths), FactoryResetTargetKind.DIRECTORY),
        FactoryResetTarget(paths.data_root, FactoryResetTargetKind.DIRECTORY),
        FactoryResetTarget(paths.cache_root, FactoryResetTargetKind.DIRECTORY),
    )
    for target in candidates:
        if not _inside_home(target.path, home):
            return _error(f"factory reset target is outside the selected user home: {target.path}")
        if target.kind is FactoryResetTargetKind.FILE:
            safe_name = (
                posixpath.basename(target.path) == "config.json"
                and posixpath.basename(posixpath.dirname(target.path)) == "agent-artifacts"
            )
        elif target.path.endswith("config.json.lock"):
            safe_name = posixpath.basename(posixpath.dirname(target.path)) == "agent-artifacts"
        else:
            safe_name = posixpath.basename(target.path) == "agent-artifacts"
        if not safe_name:
            return _error(f"factory reset target is not an AART-owned path: {target.path}")

    directory_paths = tuple(
        target.path for target in candidates if target.kind is FactoryResetTargetKind.DIRECTORY
    )
    targets = tuple(
        target
        for target in candidates
        if not any(
            target.path != directory and posixpath.commonpath((target.path, directory)) == directory
            for directory in directory_paths
        )
    )
    targets = tuple(dict.fromkeys(targets))
    identity = json.dumps(
        [{"path": target.path, "kind": target.kind.value} for target in targets],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return Ok(FactoryResetPlan(targets, "sha256:" + hashlib.sha256(identity).hexdigest()))


__all__ = [
    "FactoryResetPlan",
    "FactoryResetTarget",
    "FactoryResetTargetKind",
    "plan_factory_reset",
]
