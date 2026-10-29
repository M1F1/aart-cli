"""Read what the connected Registries pin for aart-cli, and how this aart-cli was installed (§211).

Only two small files are read from each Registry's current snapshot, through its current pointer.
The snapshot was verified when it was published, and every `consume` command asks this, so the
whole tree is not read and hashed again just to learn a version.

Nothing here may stop a command or a screen: whatever cannot be read is announced as nothing.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from aart_cli.application.aart_cli_update import (
    INSTALLER_MARKS,
    AartCliUpdate,
    RegistryPin,
    RunningAartCli,
    aart_cli_update,
    detect_installer,
)
from aart_cli.configuration.policy import EffectiveConfiguration
from aart_cli.configuration.seed import baked_default_registry
from aart_cli.domain.result import Ok
from aart_cli.runtime_contract import EXECUTABLE_VERSION
from aart_cli.sources.model import source_instance_id, source_store_paths
from aart_cli.sources.pointer import parse_current_pointer

__all__ = ["read_aart_cli_update", "read_registry_pins", "running_aart_cli"]

#: A pin is one line and a source file a handful; anything larger is not one of them.
_MAX_BYTES = 64 * 1024


def _small_file(path: Path) -> bytes | None:
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        with path.open("rb") as handle:
            content = handle.read(_MAX_BYTES + 1)
    except OSError:
        return None
    return None if len(content) > _MAX_BYTES else content


def read_registry_pins(
    effective: EffectiveConfiguration, *, data_root: str
) -> tuple[RegistryPin, ...]:
    """Each enabled Registry's pin and `.aart-cli-source`, from its current snapshot."""

    pins = []
    for configured in effective.configuration.sources:
        if not configured.enabled or not configured.is_registry:
            continue
        paths = source_store_paths(data_root, source_instance_id(configured))
        current = _small_file(Path(paths.current_file))
        if current is None:
            continue
        pointer = parse_current_pointer(current)
        if not isinstance(pointer, Ok):
            continue
        root = Path(paths.snapshots) / pointer.value.snapshot_digest.value / "source"
        pin = _small_file(root / ".aart-cli-version")
        if pin is None:
            continue
        pins.append(
            RegistryPin(
                str(configured.alias),
                pin.decode("utf-8", "replace"),
                configured.location,
                _small_file(root / ".aart-cli-source"),
            )
        )
    return tuple(pins)


def running_aart_cli(*, prefix: str | None = None, module: str = __file__) -> RunningAartCli:
    """This aart-cli: its version, its interpreter, and how it was installed.

    `prefix` and `module` are this process's environment and this file unless a test names others.
    """

    environment = sys.prefix if prefix is None else prefix
    # `module` is `aart_cli/io/aart_cli_pins.py`; two levels up is a checkout when it runs from one.
    root = Path(module).resolve().parents[2]
    checkout = str(root) if (root / ".git").exists() and (root / "pyproject.toml").is_file() else ""
    marks = frozenset(mark for mark in INSTALLER_MARKS if (Path(environment) / mark).is_file())
    return RunningAartCli(
        EXECUTABLE_VERSION,
        sys.executable,
        detect_installer(environment, checkout, marks),
        checkout,
    )


def read_aart_cli_update(
    effective: EffectiveConfiguration,
    *,
    data_root: str,
    running: RunningAartCli | None = None,
) -> AartCliUpdate | None:
    """The newer aart-cli a connected Registry runs and how to install it, else `None`.

    A defect in finding out is `None` too: this is advice, and advice may not stop anything.
    """

    try:
        default = baked_default_registry()
        default_alias = (
            str(default.value.alias) if isinstance(default, Ok) and default.value else ""
        )
        return aart_cli_update(
            read_registry_pins(effective, data_root=data_root),
            running_aart_cli() if running is None else running,
            default_alias=default_alias,
        )
    except Exception:
        return None
