"""Observe pip and uv exactly as an install runs them, for doctor (§216).

Every probe goes through `run_python_process`, so it sees the reduced environment an install sees
and nothing more; a probe that ran with the person's whole shell would pass where the install
fails, which is the one answer this check exists to avoid. The index check builds a throwaway
environment from the same base interpreter an install uses, so the pip it runs is the pip a new
artifact environment gets, and removes it afterwards.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping

from aart_cli.application.python_installers import (
    IndexCheck,
    PythonInstallersReadiness,
    ignored_installer_settings,
    installer_failure,
)
from aart_cli.redaction import redact_text

from .python_runtime import ProcessOutcome, ProcessRunner, installer_environment, run_python_process

#: A probe either answers quickly or is not going to; the index check is the slow one.
_PROBE_TIMEOUT = 60.0
#: Asked of pip because it is on every index; nothing is installed.
_PIP_PROBE = "pip"
#: Resolved by uv in a dry run with no cache, so the index is really asked; nothing is installed.
_UV_PROBE = "packaging"
# Two answers, the second optional: an interpreter without ensurepip still has a pip to report.
_ENVIRONMENT_PIP = (
    "import importlib.util\n"
    "print('pip' if importlib.util.find_spec('pip') else '-')\n"
    "try:\n"
    "    import ensurepip\n"
    "    print(ensurepip.version())\n"
    "except Exception:\n"
    "    pass\n"
)


def _run(run: ProcessRunner, argv: tuple[str, ...]) -> ProcessOutcome | None:
    try:
        return run(argv, timeout=_PROBE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _failed_check(outcome: ProcessOutcome | None) -> IndexCheck:
    if outcome is None:
        return IndexCheck(False, installer_failure("the installer did not answer in time"))
    return IndexCheck(False, installer_failure(f"{outcome.stdout}\n{outcome.stderr}"))


def _check(outcome: ProcessOutcome | None) -> IndexCheck:
    if outcome is not None and outcome.returncode == 0:
        return IndexCheck(True)
    return _failed_check(outcome)


def _check_indexes(
    run: ProcessRunner, interpreter: str, uv: str | None
) -> tuple[IndexCheck, IndexCheck | None]:
    with tempfile.TemporaryDirectory(prefix="aart-cli-index-check-") as scratch:
        environment = os.path.join(scratch, "env")
        created = _run(run, (interpreter, "-m", "venv", environment))
        if created is None or created.returncode != 0:
            failed = _failed_check(created)
            return failed, (None if uv is None else failed)
        python = f"{environment}/bin/python"
        pip = _check(
            _run(
                run,
                (
                    python,
                    "-m",
                    "pip",
                    "index",
                    "versions",
                    _PIP_PROBE,
                    "--disable-pip-version-check",
                    "--no-input",
                    "--no-cache-dir",
                ),
            )
        )
        checked_uv = (
            None
            if uv is None
            else _check(
                _run(
                    run,
                    (
                        "uv",
                        "pip",
                        "install",
                        "--dry-run",
                        "--no-cache",
                        "--python",
                        python,
                        _UV_PROBE,
                    ),
                )
            )
        )
        return pip, checked_uv


def _uv_version(run: ProcessRunner, locate: Callable[[str], str | None]) -> str | None:
    if locate("uv") is None:
        return None
    outcome = _run(run, ("uv", "--version"))
    if outcome is None or outcome.returncode != 0:
        return None
    words = outcome.stdout.split()
    return words[1] if len(words) > 1 else (words[0] if words else None)


def read_python_installers(
    *,
    interpreter: str | None = None,
    environ: Mapping[str, str] | None = None,
    check_index: bool = False,
    run: ProcessRunner = run_python_process,
    locate: Callable[[str], str | None] = shutil.which,
) -> PythonInstallersReadiness:
    """What pip and uv look like to an install on this machine; never installs anything.

    Without `check_index` nothing leaves the machine. With it, pip and uv are each asked once for
    a package from their configured index, from a throwaway environment that is removed again.
    """

    python = interpreter or sys.executable
    shell = os.environ if environ is None else environ
    probed = _run(run, (python, "-c", _ENVIRONMENT_PIP))
    answer = probed.stdout.split() if probed is not None and probed.returncode == 0 else []
    selectable = bool(answer) and answer[0] == "pip"
    environment_pip = answer[1] if len(answer) > 1 else None
    configuration: tuple[str, ...] = ()
    if selectable:
        listed = _run(run, (python, "-m", "pip", "config", "list"))
        if listed is not None and listed.returncode == 0:
            # `:env:` lines are the variables aart-cli sets for its own runs, not the person's.
            configuration = tuple(
                redact_text(line.strip())
                for line in listed.stdout.splitlines()
                if line.strip() and not line.strip().startswith(":env:")
            )
    uv = _uv_version(run, locate)
    pip_index: IndexCheck | None = None
    uv_index: IndexCheck | None = None
    if check_index:
        pip_index, uv_index = _check_indexes(run, python, uv)
    return PythonInstallersReadiness(
        interpreter=python,
        pip_selectable=selectable,
        environment_pip=environment_pip,
        uv=uv,
        pip_configuration=configuration,
        ignored_settings=ignored_installer_settings(shell, installer_environment(shell)),
        pip_index=pip_index,
        uv_index=uv_index,
    )


__all__ = ["read_python_installers"]
