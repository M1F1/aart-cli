"""Writing a harness registration into a file the harness already owns.

Every rule here follows from that ownership. The file belongs to the harness and to the person
using it, so unrelated keys survive untouched, the existing permissions survive, a file that cannot
be parsed is reported rather than replaced, and a server map that is not a map is refused rather
than overwritten with one. A registration that would destroy someone's configuration to succeed is
not a successful registration.

Writes go through a staging file and a rename, so a harness reading concurrently sees either the
old file or the new one and never a half-written one.

That is the JSON interpreter, and it is most of this module. The rest is what happens when a
harness keeps its servers in a format the interpreter cannot make those promises about. Codex uses
TOML tables, which the standard library cannot write -- `tomllib` reads only, and only from 3.11,
while `requires-python` is `>=3.10`, and INV-071 forbids a dependency. Hand-rolling a writer that
preserves comments, ordering and unrelated tables is precisely the thing that quietly destroys
somebody's configuration. Codex ships its own editor for that file and was measured keeping the
promise this module could not, so a target may name it and the registration is delegated.

`LocalHarnessRegistry` routes on that: it edits what it can promise to edit and asks the harness
for the rest, so nothing above it has to know which harness stores its servers in what.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from typing import Protocol

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import (
    McpEditor,
    McpRegistration,
    McpTarget,
    registered_command,
    registration_entry,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.fs import write_atomic

HARNESS_SETTINGS_UNREADABLE = DiagnosticCode("harness-settings-unreadable")
HARNESS_SETTINGS_UNUSABLE = DiagnosticCode("harness-settings-unusable")
HARNESS_SETTINGS_UNWRITABLE = DiagnosticCode("harness-settings-unwritable")
#: The harness that owns this file is not installed here, so nothing can be registered with it.
HARNESS_EDITOR_MISSING = DiagnosticCode("harness-editor-missing")
#: It is installed and refused. That is the harness's answer, not something to work around.
HARNESS_EDITOR_FAILED = DiagnosticCode("harness-editor-failed")

_DEFAULT_MODE = 0o600

#: Long enough for a cold harness binary to start, short enough that a wedged one is reported.
_EDITOR_TIMEOUT_SECONDS = 60.0


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

    def observed_command(self, registration: McpRegistration) -> str | None: ...


def _error(code: DiagnosticCode, message: str, *remediation: str) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message, remediation=remediation),))


class CodexServerEditor:
    """Codex's own `mcp` subcommand, run against one scope root.

    The root stands in for the home directory, so `CODEX_HOME` is `<root>/.codex` -- both what
    Codex defaults to and what the measured `.codex/config.toml` target names. Reads come back
    through `codex mcp list --json` rather than by parsing TOML this build cannot parse.
    """

    def __init__(self, root: str, *, executable: str = "codex") -> None:
        self._root = os.path.abspath(root)
        self._executable = executable

    def path_for(self, target: McpTarget) -> str:
        return os.path.join(self._root, target.settings_file)

    def _run(self, *arguments: str) -> Result[str]:
        located = shutil.which(self._executable)
        if located is None:
            return _error(
                HARNESS_EDITOR_MISSING,
                f"{self._executable} is not on PATH, and it is what writes Codex's server list",
                "install Codex, or install this artifact for a harness this machine has",
            )
        environment = dict(os.environ)
        environment["CODEX_HOME"] = os.path.join(self._root, ".codex")
        try:
            completed = subprocess.run(
                (located, *arguments),
                capture_output=True,
                text=True,
                timeout=_EDITOR_TIMEOUT_SECONDS,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return _error(HARNESS_EDITOR_FAILED, f"{self._executable} could not be run: {error}")
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            return _error(
                HARNESS_EDITOR_FAILED,
                f"`{self._executable} {' '.join(arguments)}` failed: "
                + (detail[0] if detail else f"exit {completed.returncode}"),
            )
        return Ok(completed.stdout)

    def _servers(self) -> Result[dict[str, dict]]:
        listed = self._run("mcp", "list", "--json")
        if isinstance(listed, Err):
            return listed
        try:
            data = json.loads(listed.value or "[]")
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            return _error(HARNESS_EDITOR_FAILED, f"codex mcp list --json is not JSON ({error})")
        if not isinstance(data, list):
            return _error(
                HARNESS_EDITOR_FAILED,
                f"codex mcp list --json returned a {type(data).__name__}, not a list of servers",
            )
        return Ok(
            {
                entry["name"]: entry
                for entry in data
                if isinstance(entry, dict) and isinstance(entry.get("name"), str)
            }
        )

    def register(self, registration: McpRegistration) -> Result[HarnessReceipt]:
        servers = self._servers()
        if isinstance(servers, Err):
            return servers
        path = self.path_for(registration.target)
        existing = servers.value.get(registration.server)
        wanted = (registration.command, list(registration.arguments))
        if existing is not None and _codex_transport(existing) == wanted:
            return Ok(HarnessReceipt(path, registration.server, changed=False))
        # `add` overwrites a name it already knows rather than refusing it -- measured, so a
        # change needs no removal first, and doing one anyway would widen the window in which the
        # operator's Codex has no server at all.
        added = self._run(
            "mcp", "add", registration.server, "--", registration.command, *registration.arguments
        )
        if isinstance(added, Err):
            return added
        return Ok(HarnessReceipt(path, registration.server, changed=True))

    def unregister(self, target: McpTarget, server: str) -> Result[HarnessReceipt]:
        servers = self._servers()
        if isinstance(servers, Err):
            return servers
        path = self.path_for(target)
        if server not in servers.value:
            return Ok(HarnessReceipt(path, server, changed=False))
        removed = self._run("mcp", "remove", server)
        if isinstance(removed, Err):
            return removed
        return Ok(HarnessReceipt(path, server, changed=True))

    def registered(self, target: McpTarget) -> Result[tuple[str, ...]]:
        servers = self._servers()
        if isinstance(servers, Err):
            return servers
        return Ok(tuple(sorted(servers.value)))

    def observed_command(self, registration: McpRegistration) -> str | None:
        servers = self._servers()
        if isinstance(servers, Err):
            return None
        entry = servers.value.get(registration.server)
        return None if entry is None else _codex_transport(entry)[0]


def _codex_transport(entry: dict) -> tuple[str | None, list[str]]:
    """The command and arguments out of one `codex mcp list --json` row."""

    transport = entry.get("transport")
    if not isinstance(transport, dict):
        return (None, [])
    command = transport.get("command")
    arguments = transport.get("args")
    return (
        command if isinstance(command, str) else None,
        [item for item in arguments if isinstance(item, str)]
        if isinstance(arguments, list)
        else [],
    )


#: Which editor owns which kind of file. A target that names no delegate is AART's to write.
_DELEGATES = {McpEditor.HARNESS_COMMAND: CodexServerEditor}


class LocalHarnessRegistry:
    """Registrations under one scope root on this machine.

    Routes each target to whoever can write its file safely: this module's JSON interpreter, or the
    harness's own editor for a format the interpreter cannot promise to preserve.
    """

    def __init__(self, root: str) -> None:
        self._root = os.path.abspath(root)
        self._delegated: dict[McpEditor, object] = {}

    def _delegate(self, target: McpTarget):
        """The editor for this target, or nothing when this module writes the file itself."""

        if target.editor is McpEditor.SETTINGS_FILE:
            return None
        editor = self._delegated.get(target.editor)
        if editor is None:
            editor = _DELEGATES[target.editor](self._root)
            self._delegated[target.editor] = editor
        return editor

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
        delegate = self._delegate(target)
        if delegate is not None:
            return delegate.register(registration)
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
        delegate = self._delegate(target)
        if delegate is not None:
            return delegate.unregister(target, server)
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

        delegate = self._delegate(target)
        if delegate is not None:
            return delegate.registered(target)
        loaded = self._load(self.path_for(target))
        if isinstance(loaded, Err):
            return loaded
        servers = self._servers(loaded.value, target)
        if isinstance(servers, Err):
            return servers
        return Ok(tuple(sorted(servers.value)))

    def observed_command(self, registration: McpRegistration) -> str | None:
        """The launcher this harness currently has for one server, in that harness's own spelling.

        Nothing above this needs to know how a harness stores its servers, and a reader that
        assumed one spelling is what made a correct OpenCode registration read as missing.
        """

        target = registration.target
        delegate = self._delegate(target)
        if delegate is not None:
            return delegate.observed_command(registration)
        loaded = self._load(self.path_for(target))
        if isinstance(loaded, Err):
            return None
        servers = self._servers(loaded.value, target)
        if isinstance(servers, Err):
            return None
        return registered_command(target, servers.value.get(registration.server))
