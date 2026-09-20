"""Writing a generated authoring workspace into a directory that does not already hold one.

`aart-cli author init` is usually the first AART command an author runs, and often into a directory
that already holds something of theirs. So this writer never replaces a path it did not create:
every target is checked before the first byte is written, and a failure part-way removes what this
call made. What the author sees afterwards is either the whole workspace or the directory they
started with -- never a half of one they would then have to tell apart from their own edits.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from aart_cli.authoring.skeleton import (
    SKELETON_MANIFEST_NAME,
    AuthorSkeleton,
    PayloadFile,
)
from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.domain.diagnostics import Diagnostic, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.protocol.codes import AUTHOR_MANIFEST_UNWRITABLE
from aart_cli.protocol.native_tree import SourceSnapshot
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.sources.local import read_local_snapshot
from aart_cli.sources.model import (
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


def _files(skeleton: AuthorSkeleton) -> Result[tuple[PayloadFile, ...]]:
    """The workspace as relative path and content, with every path read by the path parser.

    The paths come from the generator rather than from an author, which is exactly why they are
    checked here: a generator that one day emits an absolute or climbing entrypoint would
    otherwise write outside the directory the author named.
    """

    files: list[PayloadFile] = []
    for file in (PayloadFile(SKELETON_MANIFEST_NAME, skeleton.manifest), *skeleton.payload):
        safe = parse_relative_path(file.path)
        if isinstance(safe, Err):
            return _error(f"the generated workspace names an unusable path: {file.path!r}")
        files.append(PayloadFile(str(safe.value), file.content, file.executable))
    return Ok(tuple(files))


def _occupied(root: Path, files: tuple[PayloadFile, ...]) -> str | None:
    """The first target that already exists, by any kind of directory entry there may be."""

    for file in files:
        if os.path.lexists(root / file.path):
            return file.path
    return None


def _directories(root: Path, files: tuple[PayloadFile, ...]) -> tuple[Path, ...]:
    """Every directory the workspace needs, outermost first, without repeating one."""

    ordered: list[Path] = []
    for file in files:
        current = root
        for component in Path(file.path).parts[:-1]:
            current = current / component
            if current not in ordered:
                ordered.append(current)
    return tuple(ordered)


#: Execute for everyone who can already read, which is what `chmod +x` does and what
#: `package_hook` checks for.
_EXECUTABLE_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


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
        for file in files:
            target = root / file.path
            target.write_text(file.content, encoding="utf-8")
            created.append(target)
            if file.executable:
                # A hook's script is refused at install time unless the harness can run it, so the
                # bit is part of what `init` writes rather than something the author is told about.
                target.chmod(target.stat().st_mode | _EXECUTABLE_BITS)
    except OSError as error:
        _undo(created)
        return _error(f"the authoring workspace could not be written under {into}: {error}")
    return Ok(AuthorWorkspaceWrite(str(root), tuple(file.path for file in files)))


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
WORKING_TREE_ALIAS = SourceAlias("working-tree")


@dataclass(frozen=True, slots=True)
class AuthorWorkspaceRead:
    """One read of an author's directory, in the terms the compiler asks a Source for.

    `root` and `revision` are not decoration: compiling a manifest requires a canonical location
    and an immutable pin, and the local reader has already computed both. Passing anything else
    would be inventing an identity for a tree that has one.
    """

    root: str
    revision: str
    snapshot: SourceSnapshot


def read_author_workspace(root: str) -> Result[AuthorWorkspaceRead]:
    """The author's directory, read exactly as a Source Sync would read it.

    `aart-cli author check` has to answer with the verdict `registry scan` will later issue, and half
    of that verdict is what was in the tree at all. So this is `read_local_snapshot` -- the same
    bounded, symlink-refusing, special-file-refusing reader -- rather than a second walk with its
    own idea of what a file is. The Source identity it wants is inert here: nothing is configured
    and nothing is persisted.
    """

    absolute = os.path.abspath(root)
    try:
        # A value, not a record: `source_instance_id` is a pure function of these fields and
        # nothing here is written to the Source store or offered to the consumer surface.
        described = ConfiguredSource(
            WORKING_TREE_ALIAS, SourceKind.SOURCE_LOCAL, absolute, None, True
        )
        request = LocalSnapshotRequest(
            source_instance_id(described), WORKING_TREE_ALIAS, absolute, SnapshotLimits()
        )
    except ValueError as error:  # pragma: no cover - an absolute path is always accepted
        return _error(f"{root} cannot be read as an authoring workspace: {error}")
    acquired = read_local_snapshot(request)
    if isinstance(acquired, Err):
        return acquired
    candidate = acquired.value
    return Ok(AuthorWorkspaceRead(absolute, candidate.resolved_revision, candidate.snapshot))


__all__ = [
    "WORKING_TREE_ALIAS",
    "AuthorWorkspaceRead",
    "AuthorWorkspaceWrite",
    "read_author_workspace",
    "write_author_skeleton",
]
