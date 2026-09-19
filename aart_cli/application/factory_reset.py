"""Pure planning for deleting only AART-owned per-user application state."""

from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import dataclass
from enum import Enum

from aart_cli.configuration.paths import (
    MANAGED_HOME_ENTRIES,
    ConfigPaths,
    config_lock_directory,
)
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


def _is_filesystem_root(path: str) -> bool:
    return posixpath.dirname(path) == path


def plan_factory_reset(paths: ConfigPaths, *, home: str) -> Result[FactoryResetPlan]:
    """Name the exact entries inside the application home that a reset may remove.

    It never names the home itself. That directory can be anywhere now -- `AART_CLI_HOME` lets a CI
    job put it in its own workspace -- so a plan that removed the root would be one environment
    variable away from deleting whatever that variable happened to point at. Removing the seven
    entries §169.2 lists is the same forgetting, and leaves anything the tool did not write where
    it was.

    Two homes are still refused outright, because for them even the entries are not ours: a
    filesystem root, whose `tmp` and `state` belong to the machine, and the user's own home
    directory, whose `cache` and `objects` may belong to anything.
    """

    home = posixpath.normpath(home)
    root = paths.application_home
    if _is_filesystem_root(root):
        return _error(f"application home is a filesystem root: {root}")
    if root == home:
        return _error(f"application home is the user home itself: {root}")

    kinds = {"config.json": FactoryResetTargetKind.FILE}
    candidates = [
        FactoryResetTarget(
            posixpath.join(root, entry),
            kinds.get(entry, FactoryResetTargetKind.DIRECTORY),
        )
        for entry in MANAGED_HOME_ENTRIES
    ]
    candidates.append(
        FactoryResetTarget(config_lock_directory(paths), FactoryResetTargetKind.DIRECTORY)
    )
    for target in candidates:
        if posixpath.normpath(target.path) != target.path or posixpath.dirname(target.path) != root:
            return _error(f"factory reset target is not directly inside the home: {target.path}")

    targets = tuple(sorted(dict.fromkeys(candidates), key=lambda item: item.path))
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
