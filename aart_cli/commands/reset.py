"""Reset AART-owned per-user state into a backup, and bring a backup back (§175.4).

Nothing is deleted (INV-271). A reset renames each entry the factory reset plan names into
`<application home>-backups/<UTC timestamp>/`, beside the home, so aart-cli starts as on a new
machine and the old state can come back with `--restore`.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
from datetime import datetime, timezone

from aart_cli.application.factory_reset import (
    FactoryResetPlan,
    FactoryResetTarget,
    FactoryResetTargetKind,
    plan_factory_reset,
)
from aart_cli.command_outcome import ERROR, OK
from aart_cli.configuration.paths import (
    APPLICATION_HOME_VARIABLE,
    Platform,
    resolve_config_paths,
)
from aart_cli.domain.result import Err
from aart_cli.model import Request


def _paths(request: Request):
    platform = Platform.DARWIN if sys.platform == "darwin" else Platform.LINUX
    home = os.path.abspath(request.user_home or os.path.expanduser("~"))
    paths = resolve_config_paths(
        platform,
        home=home,
        application_home=os.environ.get(APPLICATION_HOME_VARIABLE) or None,
    )
    return home, paths


def _safe_ancestors(target: FactoryResetTarget, *, home: str) -> None:
    """Walk from the application home to the target, refusing a symlink anywhere on the way.

    `home` is the application home rather than the user's, because that is what the plan is
    relative to now. Every target is a direct child of it, so the walk usually checks one thing:
    that the home itself is a real directory. That is the case worth checking -- a symlinked
    `~/.aart-cli` would put `shutil.rmtree` somewhere nobody named.
    """

    parent = os.path.dirname(target.path)
    relative = os.path.relpath(parent, home)
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        raise ValueError(
            f"refusing factory reset target outside the application home: {target.path}"
        )
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


_RESET_PHRASE = "RESET AART"
_RESTORE_PHRASE = "RESTORE AART"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup_root(anchor: str) -> str:
    """Beside the home: outside what a reset moves, and normally on the same filesystem."""

    return anchor.rstrip(os.sep) + "-backups"


def _real_directory(path: str) -> bool:
    observed = os.lstat(path)
    return stat.S_ISDIR(observed.st_mode) and not stat.S_ISLNK(observed.st_mode)


def _new_backup(anchor: str) -> str:
    root = _backup_root(anchor)
    try:
        if not _real_directory(root):
            raise ValueError(f"refusing a backup directory that is not a real directory: {root}")
    except FileNotFoundError:
        os.mkdir(root, 0o700)
    stamp = _timestamp()
    candidate, attempt = os.path.join(root, stamp), 2
    while True:
        try:
            os.mkdir(candidate, 0o700)
            return candidate
        except FileExistsError:
            candidate, attempt = os.path.join(root, f"{stamp}-{attempt}"), attempt + 1


def _observations(
    plan: FactoryResetPlan, anchor: str
) -> tuple[tuple[FactoryResetTarget, tuple[int, int, int]], ...]:
    """Every existing target, validated before the first one moves."""

    observed = tuple((target, _safe_observation(target, home=anchor)) for target in plan.targets)
    return tuple((target, seen) for target, seen in observed if seen is not None)


def _move(source: str, destination: str) -> None:
    try:
        os.rename(source, destination)
    except OSError as error:
        if error.errno == errno.EXDEV:
            raise ValueError(
                f"refusing to copy across filesystems: {source} and {destination} are on "
                "different devices"
            ) from error
        raise


def _move_out(
    observations: tuple[tuple[FactoryResetTarget, tuple[int, int, int]], ...],
    backup: str,
    anchor: str,
) -> None:
    for target, observed in observations:
        if _safe_observation(target, home=anchor) != observed:
            raise ValueError(f"reset target changed after Review: {target.path}")
        _move(target.path, os.path.join(backup, os.path.basename(target.path)))


def _confirmed(prompt: str, phrase: str) -> bool:
    try:
        return input(prompt) == phrase
    except (EOFError, KeyboardInterrupt, StopIteration):
        return False


def _restorable(plan: FactoryResetPlan, directory: str, anchor: str) -> tuple[str, ...]:
    """The entries of a backup, refusing anything a reset could not have put there."""

    kinds = {os.path.basename(target.path): target.kind for target in plan.targets}
    relative = os.path.relpath(directory, anchor)
    if relative == os.curdir or not (relative == os.pardir or relative.startswith(os.pardir)):
        raise ValueError(f"refusing to restore from inside the application home: {directory}")
    try:
        if not _real_directory(directory):
            raise ValueError(f"refusing to restore from a symlink or file: {directory}")
    except FileNotFoundError:
        raise ValueError(f"no such backup: {directory}") from None
    entries = tuple(sorted(os.listdir(directory)))
    foreign = tuple(name for name in entries if name not in kinds)
    if foreign:
        raise ValueError(f"not an AART backup; it also holds: {', '.join(foreign)}")
    for name in entries:
        observed = os.lstat(os.path.join(directory, name))
        expected = stat.S_ISREG if kinds[name] is FactoryResetTargetKind.FILE else stat.S_ISDIR
        if stat.S_ISLNK(observed.st_mode) or not expected(observed.st_mode):
            raise ValueError(f"refusing unsafe backup entry: {os.path.join(directory, name)}")
    return entries


def _reset(plan: FactoryResetPlan, anchor: str, *, yes: bool) -> int:
    observations = _observations(plan, anchor)
    if not observations:
        print("Nothing to reset: aart-cli already starts clean.")
        return OK
    print("AART reset review")
    print(f"This AART-owned state moves into a backup under {_backup_root(anchor)}:")
    for target, _ in observations:
        print(f"  {target.kind.value}: {target.path}")
    print("Nothing is deleted. Projects, harness files and organization policy are not touched.")
    print(f"Review identity: {plan.review_digest}")
    if not yes and not _confirmed(f"Type {_RESET_PHRASE} to continue: ", _RESET_PHRASE):
        print("Reset cancelled; nothing changed.")
        return OK
    backup = _new_backup(anchor)
    _move_out(observations, backup, anchor)
    print("aart-cli starts clean. The previous state is kept in:")
    print(f"  {backup}")
    print(f"Bring it back with: aart-cli reset --restore {backup}")
    return OK


def _restore(plan: FactoryResetPlan, anchor: str, directory: str, *, yes: bool) -> int:
    entries = _restorable(plan, directory, anchor)
    observations = _observations(plan, anchor)
    print("AART restore review")
    print(f"Bring back from {directory}: {', '.join(entries) or 'nothing'}")
    if observations:
        print(f"The current state moves into a new backup under {_backup_root(anchor)} first.")
    if not yes and not _confirmed(f"Type {_RESTORE_PHRASE} to continue: ", _RESTORE_PHRASE):
        print("Restore cancelled; nothing changed.")
        return OK
    if observations:
        backup = _new_backup(anchor)
        _move_out(observations, backup, anchor)
        print(f"The state before this restore is kept in: {backup}")
    if not os.path.lexists(anchor):
        os.mkdir(anchor, 0o700)
    for name in entries:
        _move(os.path.join(directory, name), os.path.join(anchor, name))
    try:
        os.rmdir(directory)
    except OSError:
        pass
    print(f"Restored the AART state from {directory}.")
    return OK


def run(request: Request) -> int:
    try:
        home, paths = _paths(request)
        planned = plan_factory_reset(paths, home=home)
        anchor = paths.application_home
    except ValueError as error:
        print(f"error: {error}")
        return ERROR
    if isinstance(planned, Err):
        for diagnostic in planned.diagnostics:
            print(f"error: {diagnostic.message}")
        return ERROR
    try:
        if request.reset_restore is not None:
            return _restore(
                planned.value,
                anchor,
                os.path.abspath(request.reset_restore),
                yes=request.yes,
            )
        return _reset(planned.value, anchor, yes=request.yes)
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return ERROR


__all__ = ["run"]
