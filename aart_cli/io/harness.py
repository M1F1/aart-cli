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
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.harness import (
    McpEditor,
    McpRegistration,
    McpTarget,
    Scope,
    registered_command,
    registration_entry,
    settings_syntax,
    sibling_settings_paths,
)
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.settings_text import (
    JsoncError,
    parse_settings_text,
    render_settings_text,
)
from aart_cli.io.fs import write_atomic

HARNESS_SETTINGS_UNREADABLE = DiagnosticCode("harness-settings-unreadable")
HARNESS_SETTINGS_UNUSABLE = DiagnosticCode("harness-settings-unusable")
HARNESS_SETTINGS_UNWRITABLE = DiagnosticCode("harness-settings-unwritable")
#: The harness that owns this file is not installed here, so nothing can be registered with it.
HARNESS_EDITOR_MISSING = DiagnosticCode("harness-editor-missing")
#: It is installed and refused. That is the harness's answer, not something to work around.
HARNESS_EDITOR_FAILED = DiagnosticCode("harness-editor-failed")
#: A target names a scope this operation was given no root for.
HARNESS_SCOPE_UNROOTED = DiagnosticCode("harness-scope-unrooted")

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
    def register(
        self, registration: McpRegistration, *, note: str | None = None
    ) -> Result[HarnessReceipt]: ...

    def unregister(
        self, target: McpTarget, server: str, *, command: str | None = None
    ) -> Result[HarnessReceipt]: ...

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

    def register(
        self, registration: McpRegistration, *, note: str | None = None
    ) -> Result[HarnessReceipt]:
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

    def unregister(
        self, target: McpTarget, server: str, *, command: str | None = None
    ) -> Result[HarnessReceipt]:
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


def _unreadable(result: Err) -> bool:
    """A sibling file nobody could read is not one this installation's server is in to remove.

    Its harness does not read it while the chosen file exists (§218), and stopping an install into
    the file it does read because of one it does not would be worse than leaving it alone; the
    observation skips it the same way.
    """

    return all(
        item.code in (HARNESS_SETTINGS_UNREADABLE, HARNESS_SETTINGS_UNUSABLE)
        for item in result.diagnostics
    )


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

    def _load(self, path: str, target: McpTarget) -> Result[tuple[dict[str, object], str]]:
        """The settings document at `path` and the text it was read from; both empty when the
        file is not there yet."""

        if not os.path.exists(path):
            return Ok(({}, ""))
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = handle.read()
        except OSError as error:
            return _error(HARNESS_SETTINGS_UNREADABLE, f"cannot read {path}: {error.strerror}")
        except UnicodeDecodeError:
            return _error(HARNESS_SETTINGS_UNREADABLE, f"{path} is not UTF-8 text")
        syntax = settings_syntax(target.harness)
        try:
            data = parse_settings_text(raw, syntax) if raw.strip() else {}
        except ValueError as error:
            return _error(
                HARNESS_SETTINGS_UNREADABLE,
                f"{path} is not valid {syntax.value.upper()} ({error}); fix or move it, and "
                "register again",
            )
        if not isinstance(data, dict):
            return _error(
                HARNESS_SETTINGS_UNUSABLE,
                f"{path} holds a {type(data).__name__} where the harness expects an object",
            )
        return Ok((data, raw))

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

    def _save(
        self,
        path: str,
        target: McpTarget,
        raw: str,
        data: dict[str, object],
        *,
        server: str,
        note: str | None = None,
    ) -> Result[None]:
        try:
            text = render_settings_text(
                raw,
                data,
                settings_syntax(target.harness),
                path=path,
                note=note,
                ours=lambda where, _value: where == (target.server_map, server),
            )
        except JsoncError as error:
            return _error(
                HARNESS_SETTINGS_UNWRITABLE,
                f"{path} cannot take {server} without losing a comment in it ({error})",
                f"move the comments out of {target.server_map!r} in {path}, and register again",
            )
        content = text.encode("utf-8")
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            mode = _DEFAULT_MODE
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            write_atomic(path, content)
            os.chmod(path, mode)
        except OSError as error:
            return _error(HARNESS_SETTINGS_UNWRITABLE, f"cannot write {path}: {error.strerror}")
        return Ok(None)

    def _siblings(self, target: McpTarget) -> tuple[tuple[str, McpTarget], ...]:
        """The other files this harness reads at this scope, each as the target it would be."""

        path = self.path_for(target)
        prefix = path[: -len(target.settings_file)]
        return tuple(
            (sibling, replace(target, settings_file=sibling[len(prefix) :]))
            for sibling in sibling_settings_paths(target.harness, path)
        )

    def _held_elsewhere(self, target: McpTarget, server: str, command: str) -> str | None:
        """The first other file this harness reads that still names this server at `command`."""

        for sibling, sibling_target in self._siblings(target):
            loaded = self._load(sibling, sibling_target)
            if isinstance(loaded, Err):
                continue
            servers = self._servers(loaded.value[0], sibling_target)
            if isinstance(servers, Err):
                continue
            if registered_command(sibling_target, servers.value.get(server)) == command:
                return sibling
        return None

    def _remove(
        self, target: McpTarget, server: str, *, command: str | None = None
    ) -> Result[HarnessReceipt]:
        """`server` out of `target`'s file; with `command`, only while it still starts that.

        A file named for one server that starts something else holds someone's own server, which
        is not this installation's to remove.
        """

        path = self.path_for(target)
        loaded = self._load(path, target)
        if isinstance(loaded, Err):
            return loaded
        data, raw = loaded.value
        servers = self._servers(data, target)
        if isinstance(servers, Err):
            return servers
        if server not in servers.value:
            return Ok(HarnessReceipt(path, server, changed=False))
        if command is not None and registered_command(target, servers.value[server]) != command:
            return Ok(HarnessReceipt(path, server, changed=False))
        updated = dict(data)
        updated[target.server_map] = {
            key: value for key, value in servers.value.items() if key != server
        }
        saved = self._save(path, target, raw, updated, server=server)
        if isinstance(saved, Err):
            return saved
        return Ok(HarnessReceipt(path, server, changed=True))

    def register(
        self, registration: McpRegistration, *, note: str | None = None
    ) -> Result[HarnessReceipt]:
        """Write the server into the target's file, and out of every other file the harness reads
        at that scope (§218): left there, a harness that reads both would hold it twice."""

        target = registration.target
        delegate = self._delegate(target)
        if delegate is not None:
            return delegate.register(registration)
        path = self.path_for(target)
        loaded = self._load(path, target)
        if isinstance(loaded, Err):
            return loaded
        data, raw = loaded.value
        servers = self._servers(data, target)
        if isinstance(servers, Err):
            return servers

        changed = False
        entry = registration_entry(registration)
        if servers.value.get(registration.server) != entry:
            updated = dict(data)
            members = dict(servers.value)
            members[registration.server] = entry
            updated[target.server_map] = members
            saved = self._save(path, target, raw, updated, server=registration.server, note=note)
            if isinstance(saved, Err):
                return saved
            changed = True
        for _sibling, sibling_target in self._siblings(target):
            removed = self._remove(
                sibling_target, registration.server, command=registration.command
            )
            if isinstance(removed, Err):
                if _unreadable(removed):
                    continue
                return removed
            changed = changed or removed.value.changed
        return Ok(HarnessReceipt(path, registration.server, changed=changed))

    def unregister(
        self, target: McpTarget, server: str, *, command: str | None = None
    ) -> Result[HarnessReceipt]:
        """Take the server out of the target's file, and -- when `command` says which server is
        this installation's -- out of the other files the harness reads too."""

        delegate = self._delegate(target)
        if delegate is not None:
            return delegate.unregister(target, server)
        removed = self._remove(target, server)
        if isinstance(removed, Err):
            return removed
        changed = removed.value.changed
        if command is not None:
            for _sibling, sibling_target in self._siblings(target):
                elsewhere = self._remove(sibling_target, server, command=command)
                if isinstance(elsewhere, Err):
                    if _unreadable(elsewhere):
                        continue
                    return elsewhere
                changed = changed or elsewhere.value.changed
        return Ok(HarnessReceipt(removed.value.path, server, changed=changed))

    def registered(self, target: McpTarget) -> Result[tuple[str, ...]]:
        """The server names this harness currently knows, for comparison against desired state."""

        delegate = self._delegate(target)
        if delegate is not None:
            return delegate.registered(target)
        loaded = self._load(self.path_for(target), target)
        if isinstance(loaded, Err):
            return loaded
        servers = self._servers(loaded.value[0], target)
        if isinstance(servers, Err):
            return servers
        return Ok(tuple(sorted(servers.value)))

    def observed_command(self, registration: McpRegistration) -> str | None:
        """The launcher this harness currently has for one server, in that harness's own spelling.

        Nothing above this needs to know how a harness stores its servers, and a reader that
        assumed one spelling is what made a correct OpenCode registration read as missing.

        A server that is also, or only, in another file the harness reads comes back with that
        said, which no launcher path equals: it reads as divergent, so the repair writes it where
        it belongs and out of the other file, and an uninstall takes it out of both (§218).
        """

        target = registration.target
        delegate = self._delegate(target)
        if delegate is not None:
            return delegate.observed_command(registration)
        loaded = self._load(self.path_for(target), target)
        if isinstance(loaded, Err):
            return None
        servers = self._servers(loaded.value[0], target)
        if isinstance(servers, Err):
            return None
        command = registered_command(target, servers.value.get(registration.server))
        elsewhere = self._held_elsewhere(target, registration.server, registration.command)
        if command is None:
            # Only in another file the harness reads: divergent rather than missing, so an
            # uninstall still takes it out and a repair moves it.
            return None if elsewhere is None else f"{registration.command} (only in {elsewhere})"
        return command if elsewhere is None else f"{command} (also in {elsewhere})"


class ScopedHarnessRegistry:
    """Registrations under each scope's own root, chosen by the scope every target names.

    One operation may install into both scopes (§172.5, INV-260). Every `McpTarget` already says
    which scope it belongs to, so the root follows from the target rather than from the operation.
    A target whose scope has no root is refused, not resolved against the other scope's root.
    """

    def __init__(self, roots: Mapping[Scope, str]) -> None:
        self._registries = {scope: LocalHarnessRegistry(root) for scope, root in roots.items()}

    def _for(self, target: McpTarget) -> LocalHarnessRegistry | None:
        return self._registries.get(target.scope)

    def _unrooted(self, target: McpTarget) -> Err:
        return _error(
            HARNESS_SCOPE_UNROOTED,
            f"{target.harness} is registered at {target.scope.value} scope, which this operation "
            "has no root for",
        )

    def path_for(self, target: McpTarget) -> str:
        registry = self._for(target)
        if registry is None:
            raise ValueError(f"no root is known for {target.scope.value} scope")
        return registry.path_for(target)

    def register(
        self, registration: McpRegistration, *, note: str | None = None
    ) -> Result[HarnessReceipt]:
        registry = self._for(registration.target)
        if registry is None:
            return self._unrooted(registration.target)
        return registry.register(registration, note=note)

    def unregister(
        self, target: McpTarget, server: str, *, command: str | None = None
    ) -> Result[HarnessReceipt]:
        registry = self._for(target)
        if registry is None:
            return self._unrooted(target)
        return registry.unregister(target, server, command=command)

    def registered(self, target: McpTarget) -> Result[tuple[str, ...]]:
        registry = self._for(target)
        if registry is None:
            return self._unrooted(target)
        return registry.registered(target)

    def observed_command(self, registration: McpRegistration) -> str | None:
        registry = self._for(registration.target)
        return None if registry is None else registry.observed_command(registration)
