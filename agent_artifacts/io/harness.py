"""The interpreter that writes a harness registration into a file the harness already owns.

Every rule here follows from that ownership. The file belongs to the harness and to the person
using it, so unrelated keys survive untouched, the existing permissions survive, a file that cannot
be parsed is reported rather than replaced, and a server map that is not a map is refused rather
than overwritten with one. A registration that would destroy someone's configuration to succeed is
not a successful registration.

Writes go through a staging file and a rename, so a harness reading concurrently sees either the
old file or the new one and never a half-written one.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from typing import Protocol

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import McpRegistration, McpTarget, registration_entry
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.fs import write_atomic

HARNESS_SETTINGS_UNREADABLE = DiagnosticCode("harness-settings-unreadable")
HARNESS_SETTINGS_UNUSABLE = DiagnosticCode("harness-settings-unusable")
HARNESS_SETTINGS_UNWRITABLE = DiagnosticCode("harness-settings-unwritable")

_DEFAULT_MODE = 0o600


@dataclass(frozen=True, slots=True)
class HarnessReceipt:
    """What one registration did, so a reconciler can tell a no-op from a change."""

    path: str
    server: str
    changed: bool


class HarnessRegistryPort(Protocol):
    def register(self, registration: McpRegistration) -> Result[HarnessReceipt]: ...

    def unregister(self, target: McpTarget, server: str) -> Result[HarnessReceipt]: ...

    def registered(self, target: McpTarget) -> Result[tuple[str, ...]]: ...


def _error(code: DiagnosticCode, message: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message),))


class LocalHarnessRegistry:
    """Registrations under one scope root on this machine."""

    def __init__(self, root: str) -> None:
        self._root = os.path.abspath(root)

    def path_for(self, target: McpTarget) -> str:
        return os.path.join(self._root, target.settings_file)

    def _load(self, path: str) -> Result[dict[str, object]]:
        if not os.path.exists(path):
            return Ok({})
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = handle.read()
        except OSError as error:
            return _error(HARNESS_SETTINGS_UNREADABLE, f"cannot read {path}: {error.strerror}")
        if not raw.strip():
            return Ok({})
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            return _error(
                HARNESS_SETTINGS_UNREADABLE,
                f"{path} is not valid JSON ({error}); fix or move it, and register again",
            )
        if not isinstance(data, dict):
            return _error(
                HARNESS_SETTINGS_UNUSABLE,
                f"{path} holds a {type(data).__name__} where the harness expects an object",
            )
        return Ok(data)

    def _servers(self, data: dict[str, object], target: McpTarget) -> Result[dict[str, object]]:
        existing = data.get(target.server_map)
        if existing is None:
            return Ok({})
        if not isinstance(existing, dict):
            return _error(
                HARNESS_SETTINGS_UNUSABLE,
                f"{target.server_map} is a {type(existing).__name__}, not a map of servers; "
                "AART will not replace it",
            )
        return Ok(existing)

    def _save(self, path: str, data: dict[str, object]) -> Result[None]:
        content = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            mode = _DEFAULT_MODE
        try:
            write_atomic(path, content)
            os.chmod(path, mode)
        except OSError as error:
            return _error(HARNESS_SETTINGS_UNWRITABLE, f"cannot write {path}: {error.strerror}")
        return Ok(None)

    def register(self, registration: McpRegistration) -> Result[HarnessReceipt]:
        target = registration.target
        path = self.path_for(target)
        loaded = self._load(path)
        if isinstance(loaded, Err):
            return loaded
        servers = self._servers(loaded.value, target)
        if isinstance(servers, Err):
            return servers

        entry = registration_entry(registration)
        if servers.value.get(registration.server) == entry:
            return Ok(HarnessReceipt(path, registration.server, changed=False))

        data = dict(loaded.value)
        updated = dict(servers.value)
        updated[registration.server] = entry
        data[target.server_map] = updated
        saved = self._save(path, data)
        if isinstance(saved, Err):
            return saved
        return Ok(HarnessReceipt(path, registration.server, changed=True))

    def unregister(self, target: McpTarget, server: str) -> Result[HarnessReceipt]:
        path = self.path_for(target)
        loaded = self._load(path)
        if isinstance(loaded, Err):
            return loaded
        servers = self._servers(loaded.value, target)
        if isinstance(servers, Err):
            return servers
        if server not in servers.value:
            return Ok(HarnessReceipt(path, server, changed=False))

        data = dict(loaded.value)
        updated = {key: value for key, value in servers.value.items() if key != server}
        data[target.server_map] = updated
        saved = self._save(path, data)
        if isinstance(saved, Err):
            return saved
        return Ok(HarnessReceipt(path, server, changed=True))

    def registered(self, target: McpTarget) -> Result[tuple[str, ...]]:
        """The server names this harness currently knows, for comparison against desired state."""

        loaded = self._load(self.path_for(target))
        if isinstance(loaded, Err):
            return loaded
        servers = self._servers(loaded.value, target)
        if isinstance(servers, Err):
            return servers
        return Ok(tuple(sorted(servers.value)))
