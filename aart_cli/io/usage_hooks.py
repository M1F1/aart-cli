"""Write and remove the artifact-usage hook in a harness's user configuration (§212).

Claude Code's hook is one entry in `~/.claude/settings.json`; opencode's is one plugin file in
`~/.config/opencode/plugins/`. Both are user-wide, because consent is given per harness rather than
per project. A settings file that is not JSON is refused and left exactly as it was.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from aart_cli.application.usage_recording import (
    OPENCODE_PLUGIN_MARK,
    ArtifactUsageView,
    UsageHook,
    claude_settings_with,
    claude_settings_without,
    claude_usage_hooked,
    opencode_plugin,
)
from aart_cli.domain.artifact_usage import USAGE_HARNESSES, installed_names, rank_usage
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok, Result

from . import usage_hook
from .activity_store import ActivityDatabase
from .receipt_store import LocalReceiptStore

__all__ = [
    "USAGE_HOOK_UNWRITABLE",
    "harness_file",
    "read_artifact_usage",
    "reconcile_usage_hooks",
    "running_usage_hook",
    "set_usage_hook",
    "usage_hooked",
]

USAGE_HOOK_UNWRITABLE = DiagnosticCode("usage-hook-unwritable")

_MAX_SETTINGS = 4 * 1024 * 1024


def _error(message: str) -> Err:
    return Err((Diagnostic(USAGE_HOOK_UNWRITABLE, Severity.ERROR, message),))


def harness_file(harness: str, *, user_home: str) -> str:
    """The one file turning usage on changes in this harness."""

    if harness == "claude":
        return str(Path(user_home) / ".claude" / "settings.json")
    if harness == "opencode":
        return str(Path(user_home) / ".config" / "opencode" / "plugins" / "aart-cli-usage.js")
    raise ValueError(f"artifact usage cannot be recorded in {harness}")


def running_usage_hook(harness: str, *, data_root: str) -> UsageHook:
    """The hook this aart-cli would install: its own interpreter and its own copy of the script."""

    return UsageHook(
        harness,
        sys.executable,
        str(Path(usage_hook.__file__).resolve()),
        os.path.abspath(data_root),
    )


def _read_settings(path: Path) -> Result[dict[str, object]]:
    try:
        if path.stat().st_size > _MAX_SETTINGS:
            return _error(f"{path} is too large to be settings; aart-cli changed nothing in it")
        document = json.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError:
        return Ok({})
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return _error(f"{path} is not readable JSON ({error}); aart-cli changed nothing in it")
    if not isinstance(document, dict):
        return _error(f"{path} does not hold a JSON object; aart-cli changed nothing in it")
    return Ok(document)


def _write(path: Path, content: bytes) -> Result[str]:
    stage: str | None = None
    try:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, stage = tempfile.mkstemp(prefix=".aart-usage-", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, path)
        stage = None
        return Ok(str(path))
    except OSError as error:
        return _error(f"cannot write {path}: {error}")
    finally:
        if stage is not None:
            try:
                os.unlink(stage)
            except OSError:
                pass


def usage_hooked(harness: str, *, user_home: str) -> bool:
    """Whether this harness's user configuration runs aart-cli's usage hook now."""

    path = Path(harness_file(harness, user_home=user_home))
    if harness == "claude":
        read = _read_settings(path)
        return isinstance(read, Ok) and claude_usage_hooked(read.value)
    try:
        return path.read_text(encoding="utf-8").startswith(OPENCODE_PLUGIN_MARK)
    except (OSError, UnicodeDecodeError):
        return False


def set_usage_hook(harness: str, enabled: bool, *, user_home: str, data_root: str) -> Result[str]:
    """Add or remove the usage hook; the file changed, which is left alone when nothing changes."""

    if harness not in USAGE_HARNESSES:
        return _error(f"artifact usage cannot be recorded in {harness}")
    path = Path(harness_file(harness, user_home=user_home))
    if harness == "claude":
        read = _read_settings(path)
        if isinstance(read, Err):
            return read
        try:
            changed = (
                claude_settings_with(read.value, running_usage_hook(harness, data_root=data_root))
                if enabled
                else claude_settings_without(read.value)
            )
        except ValueError as error:
            return _error(f"{path}: {error}; aart-cli changed nothing in it")
        if changed == read.value:
            return Ok(str(path))
        return _write(path, (json.dumps(changed, indent=2, ensure_ascii=False) + "\n").encode())
    if enabled:
        plugin = opencode_plugin(running_usage_hook(harness, data_root=data_root))
        return _write(path, plugin.encode("utf-8"))
    if not path.exists():
        return Ok(str(path))
    if not usage_hooked(harness, user_home=user_home):
        return _error(f"{path} was not written by aart-cli; aart-cli leaves it in place")
    try:
        path.unlink()
    except OSError as error:
        return _error(f"cannot remove {path}: {error}")
    return Ok(str(path))


def read_artifact_usage(*, data_root: str, user_home: str) -> ArtifactUsageView:
    """Where usage is kept, which hooks are in place, and the ranking against what is installed.

    Never raises and never stops a screen: what cannot be read ranks nothing.
    """

    state = str(Path(data_root) / "state")
    database = ActivityDatabase(state)
    files = tuple(
        (harness, harness_file(harness, user_home=user_home)) for harness in USAGE_HARNESSES
    )
    hooked = tuple(
        harness for harness in USAGE_HARNESSES if usage_hooked(harness, user_home=user_home)
    )
    ranking: tuple = ()
    try:
        counts = database.usage_counts()
        installed = LocalReceiptStore(state).installations()
        if isinstance(counts, Ok) and counts.value:
            records = installed.value if isinstance(installed, Ok) else ()
            ranking = rank_usage(counts.value, installed_names(records))
    except Exception:  # noqa: BLE001 -- a ranking is never what stops a screen
        ranking = ()
    return ArtifactUsageView(database.path, files, hooked, ranking)


def harness_present(harness: str, *, user_home: str) -> bool:
    """Whether this harness keeps user configuration here, so it is one a hook can go into."""

    directory = Path(harness_file(harness, user_home=user_home)).parent
    if harness == "opencode":
        directory = directory.parent
    return directory.is_dir()


def reconcile_usage_hooks(
    recorded: tuple[str, ...], *, user_home: str, data_root: str
) -> tuple[str, ...]:
    """Each detected harness in `recorded` hooked; the harnesses that were not hooked before.

    A harness not recorded loses the hook; a harness that is not on this machine is left alone, so
    no configuration directory is created for a harness nobody installed.
    """

    added = []
    for harness in USAGE_HARNESSES:
        if harness not in recorded:
            if usage_hooked(harness, user_home=user_home):
                set_usage_hook(harness, False, user_home=user_home, data_root=data_root)
            continue
        if not harness_present(harness, user_home=user_home):
            continue
        before = usage_hooked(harness, user_home=user_home)
        written = set_usage_hook(harness, True, user_home=user_home, data_root=data_root)
        if isinstance(written, Ok) and not before:
            added.append(harness)
    return tuple(added)
