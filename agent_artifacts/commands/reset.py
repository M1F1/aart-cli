"""Doubly confirmed reset of AART-owned per-user application state."""

from __future__ import annotations

import os
import shutil
import stat
import sys

from agent_artifacts.application.factory_reset import (
    FactoryResetTarget,
    FactoryResetTargetKind,
    plan_factory_reset,
)
from agent_artifacts.command_outcome import ERROR, OK
from agent_artifacts.configuration.paths import Platform, resolve_config_paths
from agent_artifacts.domain.result import Err
from agent_artifacts.model import Request


def _paths(request: Request):
    platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
    home = os.path.abspath(request.user_home or os.path.expanduser("~"))
    paths = resolve_config_paths(
        platform,
        home=home,
        xdg_config_home=os.environ.get("XDG_CONFIG_HOME"),
        xdg_data_home=os.environ.get("XDG_DATA_HOME"),
        xdg_cache_home=os.environ.get("XDG_CACHE_HOME"),
    )
    return home, paths


def _safe_ancestors(target: FactoryResetTarget, *, home: str) -> None:
    parent = os.path.dirname(target.path)
    relative = os.path.relpath(parent, home)
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        raise ValueError(f"refusing factory reset target outside user home: {target.path}")
    current = home
    for component in () if relative == os.curdir else relative.split(os.sep):
        try:
            observed = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise ValueError(f"refusing symlinked factory reset path: {current}")
        current = os.path.join(current, component)
    try:
        observed = os.lstat(current)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise ValueError(f"refusing symlinked factory reset path: {current}")


def _safe_observation(target: FactoryResetTarget, *, home: str) -> tuple[int, int, int] | None:
    _safe_ancestors(target, home=home)
    try:
        observed = os.lstat(target.path)
    except FileNotFoundError:
        return None
    expected = stat.S_ISREG if target.kind is FactoryResetTargetKind.FILE else stat.S_ISDIR
    if stat.S_ISLNK(observed.st_mode) or not expected(observed.st_mode):
        raise ValueError(f"refusing unsafe factory reset target: {target.path}")
    return observed.st_dev, observed.st_ino, stat.S_IFMT(observed.st_mode)


def _remove(target: FactoryResetTarget) -> None:
    if target.kind is FactoryResetTargetKind.FILE:
        os.unlink(target.path)
    else:
        shutil.rmtree(target.path)


def _confirmed(prompt: str, phrase: str) -> bool:
    try:
        return input(prompt) == phrase
    except (EOFError, KeyboardInterrupt, StopIteration):
        return False


def run(request: Request) -> int:
    try:
        home, paths = _paths(request)
        planned = plan_factory_reset(paths, home=home)
    except ValueError as error:
        print(f"error: {error}")
        return ERROR
    if isinstance(planned, Err):
        for diagnostic in planned.diagnostics:
            print(f"error: {diagnostic.message}")
        return ERROR

    plan = planned.value
    print("AART factory reset review")
    print("The following AART-owned application state will be removed:")
    for target in plan.targets:
        print(f"  {target.kind.value}: {target.path}")
    print("Projects, harness files and credentials owned by other applications are not removed.")
    print(f"Review identity: {plan.review_digest}")

    if not _confirmed("Type RESET AART to continue: ", "RESET AART"):
        print("Factory reset cancelled; nothing changed.")
        return OK
    if not _confirmed("Type DELETE AART STATE to confirm: ", "DELETE AART STATE"):
        print("Factory reset cancelled; nothing changed.")
        return OK

    try:
        observations = tuple(
            (target, _safe_observation(target, home=home)) for target in plan.targets
        )
        # Validate every existing target before deleting the first one.
        for target, observed in observations:
            if observed is None:
                continue
            if _safe_observation(target, home=home) != observed:
                raise ValueError(f"factory reset target changed after Review: {target.path}")
        for target, observed in observations:
            if observed is not None:
                if _safe_observation(target, home=home) != observed:
                    raise ValueError(f"factory reset target changed before deletion: {target.path}")
                _remove(target)
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return ERROR

    print("AART factory reset complete. No Registry, Source, setting, receipt or cache remains.")
    return OK


__all__ = ["run"]
