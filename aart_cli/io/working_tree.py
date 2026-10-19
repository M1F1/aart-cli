"""An author's own directory, read as Git would commit it.

`source-local`, `author check`, `registry scan` and `registry promote --checkout` read a directory the
author works in. Inside a Git work tree that directory also holds what the author's tools made and
`.gitignore` excludes -- a virtual environment whose `bin/python` is a symlink, caches, editor
state. None of it is the author's content, so none of it is read: the Source is the tracked files
plus the untracked ones Git would add (`git ls-files --cached --others --exclude-standard`), read
from the working tree. A directory outside Git is read whole, as it always was.

Only the set of paths comes from Git. Every file is still opened by the bounded, non-following
reader, so a symlink or special file Git *would* commit is refused exactly as before.
"""

from __future__ import annotations

from dataclasses import replace

from aart_cli.domain.result import Err, Ok, Result
from aart_cli.io.git import GitProcessRequest, run_git_process
from aart_cli.sources.local import read_local_snapshot
from aart_cli.sources.model import LocalSnapshotRequest, SourceCandidate

_TIMEOUT_SECONDS = 30
_MAX_LISTING_BYTES = 16 * 1024 * 1024


def _git(root: str, *arguments: str, max_output_bytes: int) -> Result[bytes]:
    observed = run_git_process(
        GitProcessRequest(
            ("git", "-c", "core.hooksPath=/dev/null", "-C", root, *arguments),
            root,
            _TIMEOUT_SECONDS,
            max_output_bytes=max_output_bytes,
        )
    )
    if isinstance(observed, Err):
        return observed
    return Ok(observed.value.stdout)


def git_visible_paths(root: str) -> frozenset[str] | None:
    """The paths under `root` Git would commit, or None when `root` is not in a Git work tree."""

    inside = _git(root, "rev-parse", "--is-inside-work-tree", max_output_bytes=64)
    if isinstance(inside, Err) or inside.value.strip() != b"true":
        return None
    listed = _git(
        root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        max_output_bytes=_MAX_LISTING_BYTES,
    )
    if isinstance(listed, Err) or len(listed.value) >= _MAX_LISTING_BYTES:
        return None
    try:
        names = listed.value.decode("utf-8", errors="strict").split("\0")
    except UnicodeDecodeError:
        return None
    return frozenset(name for name in names if name)


def read_working_tree(request: LocalSnapshotRequest) -> Result[SourceCandidate]:
    """Read an author's directory; inside Git, only what Git would commit from it."""

    visible = git_visible_paths(request.root)
    if visible is None:
        return read_local_snapshot(request)
    try:
        narrowed = replace(request, include=visible)
    except ValueError:
        # A name Git lists but no safe relative path can carry: read the tree whole, so the
        # reader reports that path rather than this narrowing hiding it.
        return read_local_snapshot(request)
    return read_local_snapshot(narrowed)


__all__ = ["git_visible_paths", "read_working_tree"]
