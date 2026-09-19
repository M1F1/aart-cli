"""Writing a generated authoring workspace into a directory that does not already hold one.

`aart author init` is usually the first AART command an author runs, and often into a directory
that already holds something of theirs. So this writer never replaces a path it did not create:
every target is checked before the first byte is written, and a failure part-way removes what this
call made. What the author sees afterwards is either the whole workspace or the directory they
started with -- never a half of one they would then have to tell apart from their own edits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent_artifacts.authoring.skeleton import SKELETON_MANIFEST_NAME, AuthorSkeleton
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.domain.diagnostics import Diagnostic, Severity
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.codes import AUTHOR_MANIFEST_UNWRITABLE
from agent_artifacts.protocol.native_tree import SourceSnapshot
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.sources.local import read_local_snapshot
from agent_artifacts.sources.model import (
    LocalSnapshotRequest,
    SnapshotLimits,
    source_instance_id,
)


@dataclass(frozen=True, slots=True)
class AuthorWorkspaceWrite:
    """What one `author init` put on the disk, in the order it was written."""

    root: str
    paths: tuple[str, ...]


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (
            Diagnostic(
                AUTHOR_MANIFEST_UNWRITABLE,
                Severity.ERROR,
                message,
                remediation=remediation,
            ),
        )
    )


def _files(skeleton: AuthorSkeleton) -> Result[tuple[tuple[str, str], ...]]:
    """The workspace as relative path and content, with every path read by the path parser.

    The paths come from the generator rather than from an author, which is exactly why they are
    checked here: a generator that one day emits an absolute or climbing entrypoint would
    otherwise write outside the directory the author named.
    """

    files: list[tuple[str, str]] = []
    for relative, content in ((SKELETON_MANIFEST_NAME, skeleton.manifest), *skeleton.payload):
        safe = parse_relative_path(relative)
        if isinstance(safe, Err):
            return _error(f"the generated workspace names an unusable path: {relative!r}")
        files.append((str(safe.value), content))
    return Ok(tuple(files))


def _occupied(root: Path, files: tuple[tuple[str, str], ...]) -> str | None:
    """The first target that already exists, by any kind of directory entry there may be."""

    for relative, _ in files:
        if os.path.lexists(root / relative):
            return relative
    return None


def _directories(root: Path, files: tuple[tuple[str, str], ...]) -> tuple[Path, ...]:
    """Every directory the workspace needs, outermost first, without repeating one."""

    ordered: list[Path] = []
    for relative, _ in files:
        current = root
        for component in Path(relative).parts[:-1]:
            current = current / component
            if current not in ordered:
                ordered.append(current)
    return tuple(ordered)


def write_author_skeleton(skeleton: AuthorSkeleton, *, into: str) -> Result[AuthorWorkspaceWrite]:
    """Write the manifest and its payload under `into`, or leave `into` as it was."""

    named = _files(skeleton)
    if isinstance(named, Err):
        return named
    files = named.value
    root = Path(into)
    if os.path.lexists(root) and not root.is_dir():
        return _error(
            f"{into} is not a directory, so no authoring workspace can be written there",
            "Name a directory, or a path that does not exist yet.",
        )
    taken = _occupied(root, files)
    if taken is not None:
        return _error(
            f"{Path(into) / taken} already exists; `author init` never replaces a file",
            "Write into an empty directory, or move what is there out of the way.",
        )

    created: list[Path] = []
    try:
        for directory in (root, *_directories(root, files)):
            if not directory.exists():
                directory.mkdir(parents=True)
                created.append(directory)
        for relative, content in files:
            target = root / relative
            target.write_text(content, encoding="utf-8")
            created.append(target)
    except OSError as error:
        _undo(created)
        return _error(f"the authoring workspace could not be written under {into}: {error}")
    return Ok(AuthorWorkspaceWrite(str(root), tuple(relative for relative, _ in files)))


def _undo(created: list[Path]) -> None:
    """Remove what this call made, innermost first. Best effort: the error being reported is the
    one the author needs, and a failure to clean up must not replace it."""

    for path in reversed(created):
        try:
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink()
        except OSError:  # pragma: no cover - reported error takes precedence over cleanup
            return


#: The alias a read of the author's own directory carries. It is not a configured Source and
#: never becomes one; the name exists because the reader below is the Source reader, deliberately.
_WORKING_TREE_ALIAS = "working-tree"


def read_author_workspace(root: str) -> Result[SourceSnapshot]:
    """The author's directory, read exactly as a Source Sync would read it.

    `aart author check` has to answer with the verdict `registry scan` will later issue, and half
    of that verdict is what was in the tree at all. So this is `read_local_snapshot` -- the same
    bounded, symlink-refusing, special-file-refusing reader -- rather than a second walk with its
    own idea of what a file is. The Source identity it wants is inert here: nothing is configured,
    nothing is persisted, and the candidate's digest and revision are discarded.
    """

    absolute = os.path.abspath(root)
    alias = SourceAlias(_WORKING_TREE_ALIAS)
    try:
        # A value, not a record: `source_instance_id` is a pure function of these fields and
        # nothing here is written to the Source store or offered to the consumer surface.
        described = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, absolute, None, True)
        request = LocalSnapshotRequest(
            source_instance_id(described), alias, absolute, SnapshotLimits()
        )
    except ValueError as error:  # pragma: no cover - an absolute path is always accepted
        return _error(f"{root} cannot be read as an authoring workspace: {error}")
    acquired = read_local_snapshot(request)
    if isinstance(acquired, Err):
        return acquired
    return Ok(acquired.value.snapshot)


__all__ = ["AuthorWorkspaceWrite", "read_author_workspace", "write_author_skeleton"]
