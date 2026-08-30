"""The interpreter that writes a generated launcher into the artifact's own directory.

Two things happen here that the pure generator cannot do and must not be trusted to have done.
The path is checked against the artifact that owns it, so a projection built for one artifact
cannot be written over another's; and the file is read back and re-digested after the write, so
what the harness will execute is the same bytes that were reviewed rather than the bytes somebody
meant to write.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from agent_artifacts.application.installation_verification import InstallationObservation
from agent_artifacts.application.runtime_projection import RuntimeProjection
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import McpRegistration
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import InstallationReceipt
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.fs import write_atomic
from agent_artifacts.protocol.hashing import sha256_bytes

PROJECTION_REFUSED = DiagnosticCode("projection-refused")
PROJECTION_FAILED = DiagnosticCode("projection-failed")
PROJECTION_CORRUPTED = DiagnosticCode("projection-corrupted")

_LAUNCHER_MODE = 0o700


@dataclass(frozen=True, slots=True)
class ProjectionReceipt:
    """The launcher that now exists on disk, and the digest of what it actually contains."""

    path: str
    digest: ObjectDigest
    changed: bool


class ProjectionWriterPort(Protocol):
    def write(self, projection: RuntimeProjection) -> Result[ProjectionReceipt]: ...


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


class LocalProjectionWriter:
    """Writes launchers for exactly one artifact."""

    def __init__(self, environment: ArtifactEnvironment) -> None:
        if not isinstance(environment, ArtifactEnvironment):
            raise ValueError("a projection writer belongs to one artifact environment")
        self._environment = environment

    def write(self, projection: RuntimeProjection) -> Result[ProjectionReceipt]:
        if not isinstance(projection, RuntimeProjection):
            return _error(PROJECTION_REFUSED, "a projection is required")
        if not self._environment.owns(projection.path):
            return _error(
                PROJECTION_REFUSED,
                f"{projection.path} is outside {self._environment.artifact}; "
                "a launcher is only ever written inside the artifact that runs it",
            )

        content = projection.content.encode("utf-8")
        try:
            existing = os.path.exists(projection.path) and open(projection.path, "rb").read()
        except OSError as error:
            return _error(PROJECTION_FAILED, f"cannot read {projection.path}: {error.strerror}")
        if existing == content and os.access(projection.path, os.X_OK):
            return Ok(ProjectionReceipt(projection.path, projection.digest, changed=False))

        try:
            write_atomic(projection.path, content)
            os.chmod(projection.path, _LAUNCHER_MODE if projection.executable else 0o600)
            with open(projection.path, "rb") as handle:
                written = handle.read()
        except OSError as error:
            return _error(PROJECTION_FAILED, f"cannot write {projection.path}: {error.strerror}")

        digest = sha256_bytes(written)
        if str(digest) != str(projection.digest):
            return _error(
                PROJECTION_CORRUPTED,
                f"{projection.path} does not hold what was planned; expected "
                f"{projection.digest} and found {digest}",
            )
        return Ok(ProjectionReceipt(projection.path, digest, changed=True))


def observe_installation(
    receipt: InstallationReceipt,
    *,
    registry: object | None = None,
) -> InstallationObservation:
    """Measure what `receipt` claims, on this machine, right now.

    Every failure to measure is reported as a fact rather than raised. A launcher that cannot be
    read is not a launcher that matches, and saying so is the point of verifying.
    """

    if not isinstance(receipt, InstallationReceipt):
        raise ValueError("observing an installation needs a receipt")

    present = os.path.isfile(receipt.launcher)
    digest: ObjectDigest | None = None
    if present:
        try:
            with open(receipt.launcher, "rb") as handle:
                digest = sha256_bytes(handle.read())
        except OSError:
            digest = None

    commands: list[tuple[str, str, str | None]] = []
    for registration in receipt.registrations:
        command: str | None = None
        if registry is not None:
            command = _observed_command(registry, registration)
        commands.append((registration.target.harness, registration.server, command))

    return InstallationObservation(
        root_present=os.path.isdir(receipt.root),
        launcher_present=present,
        launcher_executable=present and os.access(receipt.launcher, os.X_OK),
        launcher_digest=digest,
        interpreter_present=os.access(receipt.interpreter, os.X_OK),
        registered_commands=tuple(commands),
    )


def _observed_command(registry: object, registration: McpRegistration) -> str | None:
    path = registry.path_for(registration.target)  # type: ignore[attr-defined]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    servers = data.get(registration.target.server_map)
    if not isinstance(servers, dict):
        return None
    entry = servers.get(registration.server)
    if not isinstance(entry, dict):
        return None
    command = entry.get("command")
    return command if isinstance(command, str) else None
