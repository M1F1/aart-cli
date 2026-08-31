"""A region of a text file AART owns, inside a file it does not.

A Skill is delivered: AART writes the whole destination and owns every byte of it. A memory
artifact is not. Its body goes into `CLAUDE.md`, `TABNINE.md` or `AGENTS.md` -- files a person
writes in and keeps their own notes in -- so installing one means owning a named region and leaving
everything around it exactly as it was. `DeliverArtifact` replaces its destination, which is why
using it here would delete the file it merged into (B-034).

The refusals are the substance. A file already holding two blocks for one name is ambiguous about
which region is AART's, and a half-open block says the file has been edited in a way that leaves
the end of AART's region unknown. The legacy memory path resolves the second case by writing from
the opening marker to the end of the file, which destroys everything the user wrote below it. Both
are refused here instead: the file is evidence, and guessing at a boundary is how it stops being.

Pure text in, pure text out. Nothing here reads or writes a file.
"""

from __future__ import annotations

import re
from enum import Enum

from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .result import Err, Ok, Result

__all__ = [
    "BLOCK_UNMERGEABLE",
    "BlockPosition",
    "managed_block",
    "merge_managed_block",
    "remove_managed_block",
]

#: The file cannot be merged into without guessing where AART's region begins or ends.
BLOCK_UNMERGEABLE = DiagnosticCode("managed-block-unmergeable")

#: A markdown comment, because the harness reads this file as instructions: a marker it rendered as
#: content would become part of what the agent is told.
_BEGIN = "<!-- >>> agent-artifacts memory:{name} >>> -->"
_END = "<!-- <<< agent-artifacts memory:{name} <<< -->"

#: The name reaches a marker that is later matched literally, so it may not carry a newline, a
#: space or any part of the delimiter syntax -- a name that did could close its own region early.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class BlockPosition(str, Enum):
    """Where a block goes the first time it is written. A replacement stays where it is."""

    TOP = "top"
    BOTTOM = "bottom"


def _error(message: str) -> Err:
    return Err((Diagnostic(BLOCK_UNMERGEABLE, Severity.ERROR, message),))


def managed_block(name: str, body: str) -> str:
    """The exact text this artifact owns, markers included."""

    return f"{_BEGIN.format(name=name)}\n{body.rstrip(chr(10))}\n{_END.format(name=name)}"


def _region(existing: str, name: str) -> Result[tuple[int, int] | None]:
    """Where this artifact's region starts and stops, or `None` when it is not there yet."""

    begin = _BEGIN.format(name=name)
    end = _END.format(name=name)
    opens = [match.start() for match in re.finditer(re.escape(begin), existing)]
    closes = [match.end() for match in re.finditer(re.escape(end), existing)]
    if len(opens) > 1 or len(closes) > 1:
        return _error(
            f"this file holds more than one region for {name}, so which one AART owns is "
            "ambiguous; remove the duplicate and install again"
        )
    if not opens and not closes:
        return Ok(None)
    if not opens or not closes or closes[0] < opens[0]:
        return _error(
            f"this file holds only one half of the region for {name}, so where AART's text ends "
            "is unknown; restore or remove the stray marker and install again"
        )
    return Ok((opens[0], closes[0]))


def merge_managed_block(
    existing: str,
    name: str,
    body: str,
    *,
    position: BlockPosition = BlockPosition.BOTTOM,
) -> Result[str]:
    """Put this artifact's body into `existing`, owning only its own region."""

    if not isinstance(name, str) or _NAME_RE.fullmatch(name) is None:
        return _error(f"{name!r} cannot name a managed region")
    if not isinstance(existing, str) or not isinstance(body, str):
        return _error("merging a managed region needs the file's text and the artifact's body")

    block = managed_block(name, body)
    if _BEGIN.format(name=name) in body or _END.format(name=name) in body:
        # Otherwise the artifact decides where AART's region stops, and everything past that
        # marker becomes the user's text as far as a later withdrawal is concerned.
        return _error(f"the body of {name} carries the marker that delimits it")

    found = _region(existing, name)
    if isinstance(found, Err):
        return found
    if found.value is not None:
        start, stop = found.value
        return Ok(existing[:start] + block + existing[stop:])

    if not existing:
        return Ok(f"{block}\n")
    base = existing if existing.endswith("\n") else f"{existing}\n"
    if position is BlockPosition.TOP:
        return Ok(f"{block}\n\n{base}")
    return Ok(f"{base}\n{block}\n")


def remove_managed_block(existing: str, name: str) -> Result[str]:
    """Take this artifact's region back out, and leave the rest of the file as evidence."""

    if not isinstance(name, str) or _NAME_RE.fullmatch(name) is None:
        return _error(f"{name!r} cannot name a managed region")
    if not isinstance(existing, str):
        return _error("removing a managed region needs the file's text")

    found = _region(existing, name)
    if isinstance(found, Err):
        return found
    if found.value is None:
        # Already gone is the state that was asked for, so this converges rather than failing.
        return Ok(existing)

    start, stop = found.value
    head, tail = existing[:start], existing[stop:]
    if tail.startswith("\n"):
        tail = tail[1:]
    if not tail:
        # The block was the last thing in the file: drop the blank line that separated it from
        # whatever came before, rather than leaving the file ending in whitespace it did not have.
        head = head.rstrip("\n")
        return Ok(f"{head}\n" if head else "")
    return Ok(head + tail)
