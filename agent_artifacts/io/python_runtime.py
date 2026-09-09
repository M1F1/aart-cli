"""Interpreters for the Python environment and dependency effects.

Everything here runs a child process and nothing here decides anything: the backend, the
descriptor and the interpreter all arrive already chosen and already reviewed. The one judgement
this module does make is refusing to act on an effect whose paths are not the ones the artifact
owns, because an interpreter that trusts its input is where "AART never touches your global
Python" stops being true.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import CreatePythonEnvironment, InstallPythonDependencies
from agent_artifacts.domain.inspection import RemediationCapability, RemediationCapabilityKind
from agent_artifacts.domain.python_runtime import ArtifactEnvironment, PythonInstaller
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.redaction import redact_text

PYTHON_RUNTIME_FAILED = DiagnosticCode("python-runtime-failed")
PYTHON_RUNTIME_REFUSED = DiagnosticCode("python-runtime-refused")
PYTHON_RUNTIME_UNSUPPORTED = DiagnosticCode("python-runtime-unsupported")

_ALLOWED_ENVIRONMENT = ("HOME", "PATH", "SYSTEMROOT", "TMPDIR")
_MAX_OUTPUT_BYTES = 8192


@dataclass(frozen=True, slots=True)
class ProcessOutcome:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ProcessRunner(Protocol):
    def __call__(self, argv: tuple[str, ...], *, timeout: float) -> ProcessOutcome: ...


def _environment(environ: Mapping[str, str]) -> dict[str, str]:
    result = {name: environ[name] for name in _ALLOWED_ENVIRONMENT if name in environ}
    result.update(
        {
            "LC_ALL": "C",
            # A venv inherited from the caller is how an install silently lands somewhere else.
            "PYTHONNOUSERSITE": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
    )
    return result


def run_python_process(argv: tuple[str, ...], *, timeout: float) -> ProcessOutcome:
    completed = subprocess.run(
        argv,
        shell=False,
        env=_environment(os.environ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        text=True,
    )
    return ProcessOutcome(
        completed.returncode,
        (completed.stdout or "")[:_MAX_OUTPUT_BYTES],
        (completed.stderr or "")[:_MAX_OUTPUT_BYTES],
    )


@dataclass(frozen=True, slots=True)
class EnvironmentReceipt:
    """What actually happened, in terms a reconciler can re-check."""

    interpreter: str
    detail: str


class PythonRuntimePort(Protocol):
    def create_environment(self, effect: CreatePythonEnvironment) -> Result[EnvironmentReceipt]: ...

    def install_dependencies(
        self, effect: InstallPythonDependencies
    ) -> Result[EnvironmentReceipt]: ...


def _failure(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, redact_text(message)),))


class ExecutableLocator(Protocol):
    def __call__(self, name: str) -> str | None: ...


def _which(name: str) -> str | None:
    return shutil.which(name)


def observe_python_installers(
    *,
    locate: ExecutableLocator = _which,
    interpreter: str | None = None,
) -> tuple[RemediationCapability, ...]:
    """Which dependency backends this machine can actually run, as planning capabilities.

    pip is reported when the given interpreter can import it, not when a `pip` script happens to be
    on PATH -- a shim pointing at another interpreter is exactly the confusion this avoids.
    """

    python = interpreter or sys.executable
    capabilities = []
    probe = subprocess.run(
        (python, "-c", "import pip"),
        shell=False,
        env=_environment(os.environ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30.0,
        check=False,
    )
    if probe.returncode == 0:
        capabilities.append(
            RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, "pip")
        )
    if locate("uv") is not None:
        capabilities.append(RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, "uv"))
    return tuple(capabilities)


@dataclass(frozen=True, slots=True)
class LocalPythonRuntime:
    """Create artifact-owned environments and install into them, and nowhere else.

    `environment` is the artifact this interpreter is allowed to act for. Every path in every
    effect is checked against it before a process starts, so a plan that named someone else's
    directory is refused rather than executed.
    """

    environment: ArtifactEnvironment
    run: ProcessRunner = field(default=run_python_process)
    timeout_seconds: float = 900.0
    offline: bool = False
    uv_executable: str = "uv"

    def _refuse_unowned(self, *paths: str) -> Err | None:
        unowned = tuple(path for path in paths if not self.environment.owns(path))
        if unowned:
            return _failure(
                PYTHON_RUNTIME_REFUSED,
                f"refusing to act outside {self.environment.root}: {', '.join(unowned)}",
            )
        return None

    def _execute(self, argv: tuple[str, ...], label: str) -> Result[ProcessOutcome]:
        try:
            outcome = self.run(argv, timeout=self.timeout_seconds)
        except FileNotFoundError:
            return _failure(PYTHON_RUNTIME_FAILED, f"{label} failed: {argv[0]} is not available")
        except OSError as error:
            return _failure(PYTHON_RUNTIME_FAILED, f"{label} failed: {error}")
        except subprocess.TimeoutExpired:
            return _failure(
                PYTHON_RUNTIME_FAILED,
                f"{label} timed out after {self.timeout_seconds:g}s",
            )
        if outcome.returncode != 0:
            detail = (outcome.stderr or outcome.stdout).strip().splitlines()
            tail = detail[-1] if detail else "(no output)"
            return _failure(
                PYTHON_RUNTIME_FAILED,
                f"{label} failed with status {outcome.returncode}: {tail}",
            )
        return Ok(outcome)

    def create_environment(self, effect: CreatePythonEnvironment) -> Result[EnvironmentReceipt]:
        if effect.artifact != self.environment.artifact:
            return _failure(
                PYTHON_RUNTIME_REFUSED,
                f"this interpreter acts for {self.environment.artifact}, not {effect.artifact}",
            )
        refused = self._refuse_unowned(effect.destination)
        if refused is not None:
            return refused
        if self.environment.owns(effect.base_interpreter):
            return _failure(
                PYTHON_RUNTIME_REFUSED,
                "the base interpreter cannot be the environment being built from it",
            )
        executed = self._execute(
            (effect.base_interpreter, "-m", "venv", effect.destination),
            "environment creation",
        )
        if isinstance(executed, Err):
            return executed
        return Ok(
            EnvironmentReceipt(
                self.environment.interpreter,
                f"created from {effect.base_interpreter}",
            )
        )

    def _install_argv(self, effect: InstallPythonDependencies) -> tuple[str, ...] | None:
        """The command for one backend and one descriptor kind, or None when unsupported."""

        interpreter = f"{effect.environment}/bin/python"
        target = (
            effect.descriptor
            if effect.descriptor_kind == "requirements"
            else effect.descriptor.rsplit("/", 1)[0]
        )
        if effect.installer == PythonInstaller.PIP.value:
            flags = ("--no-index",) if self.offline else ()
            source = ("-r", target) if effect.descriptor_kind == "requirements" else (target,)
            return (
                interpreter,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--no-cache-dir",
                *flags,
                *source,
            )
        if effect.installer == PythonInstaller.UV.value:
            flags = ("--offline",) if self.offline else ()
            source = ("-r", target) if effect.descriptor_kind == "requirements" else (target,)
            return (
                self.uv_executable,
                "pip",
                "install",
                "--python",
                interpreter,
                *flags,
                *source,
            )
        return None

    def install_dependencies(self, effect: InstallPythonDependencies) -> Result[EnvironmentReceipt]:
        refused = self._refuse_unowned(effect.environment, effect.descriptor)
        if refused is not None:
            return refused
        if effect.environment != self.environment.environment:
            return _failure(
                PYTHON_RUNTIME_REFUSED,
                f"this interpreter installs into {self.environment.environment} only",
            )
        if effect.descriptor_kind == "locked-project":
            # The lock is modelled and planned, but installing one is not implemented here yet.
            # Ignoring it and installing loose versions would defeat the reason it exists.
            return _failure(
                PYTHON_RUNTIME_UNSUPPORTED,
                f"installing a locked project with {effect.installer} is not supported yet",
            )
        argv = self._install_argv(effect)
        if argv is None:
            return _failure(
                PYTHON_RUNTIME_UNSUPPORTED,
                f"dependency installer {effect.installer} is not supported",
            )
        executed = self._execute(argv, "dependency installation")
        if isinstance(executed, Err):
            return executed
        return Ok(
            EnvironmentReceipt(
                self.environment.interpreter,
                f"installed {effect.descriptor_kind} with {effect.installer}",
            )
        )
