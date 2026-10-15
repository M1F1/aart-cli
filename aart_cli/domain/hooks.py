"""One hook's entry inside a settings file the harness and the person using it both own.

A hook is two things and only one of them is a delivery. The script is placed in a directory of its
own, which `DeliverArtifact` already covers. The entry that makes the harness run it is a member of
a list inside `settings.json`, beside every other hook and beside whatever else the user configured
there -- so installing one means owning one element of that list and leaving the file around it
exactly as it was (B-034).

The entry is modelled rather than templated. Only two shapes have been measured, both appear here
by name, and rendering one from a `${...}` template would put an untyped renderer between what
somebody reviewed and what is written into their configuration.

Identity is the matcher and the command. Those two are what the harness acts on, so two entries
agreeing on both are the same hook however the rest of the entry is spelled -- which is what lets a
reinstall converge on the entry that is already there instead of adding a second one beside it.

A plugin is the other measured list member (§171.3). OpenCode loads the plugins named in the
`plugin` list of `opencode.json`, and an entry there is a bare string -- the path of the module
relative to that file -- so its identity is the whole string and there is nothing else to spell.

Pure data in, pure data out. Nothing here reads or writes a file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .result import Err, Ok, Result

__all__ = [
    "SETTINGS_UNMERGEABLE",
    "HookEntry",
    "HookEntryShape",
    "PluginEntry",
    "SettingsListEntry",
    "settings_entry_label",
    "settings_entry_at",
    "settings_entry_fingerprint",
    "settings_entry_to_json",
    "merge_settings_entry",
    "remove_settings_entry",
]

#: The settings file cannot be merged into without replacing something somebody else put there.
SETTINGS_UNMERGEABLE = DiagnosticCode("settings-entry-unmergeable")


class HookEntryShape(str, Enum):
    """How one measured harness spells the entry that runs a hook.

    Measured, not derived. `NESTED_COMMAND` is what Claude Code's `settings.json` holds -- a matcher
    with a list of commands under it -- and `FLAT_COMMAND` is what the observed Tabnine build holds.
    A harness nobody has looked at gets neither.
    """

    NESTED_COMMAND = "nested-command"
    FLAT_COMMAND = "flat-command"


@dataclass(frozen=True, slots=True)
class HookEntry:
    """What the harness is told: when to run something, and what to run."""

    shape: HookEntryShape
    matcher: str
    command: str

    def __post_init__(self) -> None:
        if not isinstance(self.shape, HookEntryShape):
            raise ValueError("a hook entry needs a measured entry shape")
        for value, label in ((self.matcher, "matcher"), (self.command, "command")):
            if (
                not isinstance(value, str)
                or not value.strip()
                or any(character in value for character in "\r\n")
            ):
                raise ValueError(f"a hook entry {label} must be one non-empty line")
        if not self.command.startswith("/"):
            # The harness resolves the command against a working directory nobody here controls,
            # the same rule a registration's command and a delivery's paths follow.
            raise ValueError("a hook command must be one absolute path")


#: A plugin path as AART writes it: `./`, then segments of ordinary file-name characters, ending in a
#: module the harness loads. Narrower than any path opencode accepts on purpose -- no scheme, no
#: `@`, no absolute root and no parent segment -- because each of those is a spelling that loads
#: something other than the installation's own reviewed copy (INV-255).
_PLUGIN_REFERENCE_RE = re.compile(r"^\./(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+\.(?:js|mjs|ts)$")


@dataclass(frozen=True, slots=True)
class PluginEntry:
    """What the harness is told: load the module at this path, relative to the settings file."""

    reference: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.reference, str)
            or _PLUGIN_REFERENCE_RE.fullmatch(self.reference) is None
            or any(part in (".", "..") for part in self.reference.split("/")[1:])
        ):
            raise ValueError(
                "a plugin entry is a ./ path inside the installation to a .js, .mjs or .ts module"
            )


#: One member of a list in a settings file that an installation owns.
SettingsListEntry = HookEntry | PluginEntry


def settings_entry_label(entry: SettingsListEntry) -> str:
    """How a person is told which entry this is: the hook's matcher, or the plugin's path."""

    return entry.matcher if isinstance(entry, HookEntry) else entry.reference


def _error(message: str) -> Err:
    return Err((Diagnostic(SETTINGS_UNMERGEABLE, Severity.ERROR, message),))


def settings_entry_to_json(entry: SettingsListEntry) -> object:
    """The entry exactly as the harness expects to read it."""

    if isinstance(entry, PluginEntry):
        return entry.reference
    if not isinstance(entry, HookEntry):
        raise ValueError("rendering a settings entry needs a hook or a plugin entry")
    if entry.shape is HookEntryShape.FLAT_COMMAND:
        return {"matcher": entry.matcher, "command": entry.command}
    return {
        "matcher": entry.matcher,
        "hooks": [{"type": "command", "command": entry.command}],
    }


def settings_entry_fingerprint(entry: object) -> str:
    """One canonical spelling of an entry, so two of them can be compared for having drifted.

    Whatever the settings file happens to hold is compared against what was recorded, and a file a
    person reformatted must not read as a changed hook. Key order and whitespace are therefore
    normalised away; anything the harness would actually act on differently is not.
    """

    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identifies(candidate: object, entry: SettingsListEntry) -> bool:
    """Whether `candidate` is this entry, however the rest of a hook's entry is spelled."""

    if isinstance(entry, PluginEntry):
        return candidate == entry.reference
    if not isinstance(candidate, dict) or candidate.get("matcher") != entry.matcher:
        return False
    if entry.shape is HookEntryShape.FLAT_COMMAND:
        return candidate.get("command") == entry.command
    nested = candidate.get("hooks")
    if not isinstance(nested, list):
        return False
    return any(isinstance(item, dict) and item.get("command") == entry.command for item in nested)


def _walk(document: object, path: str) -> Result[tuple[list[object], list[dict[str, object]]]]:
    """The parts of `path`, and the objects each one is read from, refusing anything in the way.

    Returns the path's segments beside the chain of objects leading to them, so a caller can read
    the list at the end or rebuild the document around it without walking twice.
    """

    if not isinstance(document, dict):
        return _error(
            f"the settings file holds a {type(document).__name__} where the harness expects "
            "an object"
        )
    parts = [part for part in path.split(".") if part]
    if not parts:
        return _error("a settings entry needs the path the harness reads it from")
    chain: list[dict[str, object]] = [document]
    for index, part in enumerate(parts[:-1]):
        found = chain[-1].get(part)
        if found is None:
            found = {}
        if not isinstance(found, dict):
            return _error(
                f"the settings path {path!r} crosses {'.'.join(parts[: index + 1])!r}, which "
                f"holds a {type(found).__name__} rather than an object"
            )
        chain.append(found)
    return Ok((list(parts), chain))


def _entries(
    chain: list[dict[str, object]], parts: list[object], path: str
) -> Result[list[object]]:
    found = chain[-1].get(str(parts[-1]))
    if found is None:
        return Ok([])
    if not isinstance(found, list):
        return _error(
            f"the settings path {path!r} holds a {type(found).__name__} where the harness expects "
            "a list of entries"
        )
    return Ok(list(found))


def _rebuilt(
    chain: list[dict[str, object]], parts: list[object], entries: list[object]
) -> dict[str, object]:
    """The document with `entries` at the path, and everything else copied rather than shared."""

    rebuilt: object = entries
    for depth in range(len(parts) - 1, -1, -1):
        holder = dict(chain[depth])
        holder[str(parts[depth])] = rebuilt
        rebuilt = holder
    assert isinstance(rebuilt, dict)
    return rebuilt


def settings_entry_at(
    document: object, path: str, entry: SettingsListEntry
) -> Result[object | None]:
    """This hook's entry as the settings file currently spells it, or `None` when it is not there.

    What the file says now, not what was written: an entry somebody edited reads back as the edit,
    which is what makes drift in it detectable rather than assumed away.
    """

    if not isinstance(entry, (HookEntry, PluginEntry)):
        return _error("reading a settings entry needs the entry it identifies")
    walked = _walk(document, path)
    if isinstance(walked, Err):
        return walked
    parts, chain = walked.value
    found = _entries(chain, parts, path)
    if isinstance(found, Err):
        return found
    return Ok(next((item for item in found.value if _identifies(item, entry)), None))


def merge_settings_entry(
    document: object, path: str, entry: SettingsListEntry
) -> Result[dict[str, object]]:
    """`document` with this hook's entry at `path`, and everything else exactly as it was."""

    if not isinstance(entry, (HookEntry, PluginEntry)):
        return _error("merging a settings entry needs the entry to write")
    walked = _walk(document, path)
    if isinstance(walked, Err):
        return walked
    parts, chain = walked.value
    found = _entries(chain, parts, path)
    if isinstance(found, Err):
        return found

    written = settings_entry_to_json(entry)
    entries = list(found.value)
    for index, item in enumerate(entries):
        if _identifies(item, entry):
            entries[index] = written
            break
    else:
        entries.append(written)
    return Ok(_rebuilt(chain, parts, entries))


def remove_settings_entry(
    document: object, path: str, entry: SettingsListEntry
) -> Result[dict[str, object]]:
    """`document` without this hook's entry, and with everyone else's left standing.

    The list itself stays, empty if it has to. It is the harness's key, not this artifact's, and an
    uninstall that tidied it away would be removing something it never created.
    """

    if not isinstance(entry, (HookEntry, PluginEntry)):
        return _error("removing a settings entry needs the entry it identifies")
    walked = _walk(document, path)
    if isinstance(walked, Err):
        return walked
    parts, chain = walked.value
    found = _entries(chain, parts, path)
    if isinstance(found, Err):
        return found
    remaining = [item for item in found.value if not _identifies(item, entry)]
    if len(remaining) == len(found.value) and not isinstance(chain[-1].get(str(parts[-1])), list):
        # Nothing to remove and no list to leave behind: converge on the document as it stands
        # rather than writing a key the harness never had.
        assert isinstance(document, dict)
        return Ok(document)
    return Ok(_rebuilt(chain, parts, remaining))
