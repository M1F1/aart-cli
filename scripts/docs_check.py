#!/usr/bin/env python3
"""Non-mutating Markdown and AART documentation consistency checks."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_LINK_RE = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")


@dataclass(frozen=True, order=True)
class Diagnostic:
    path: str
    line: int
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.code} {self.message}"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _link_path(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith(("#", "mailto:", "data:")):
        return None
    return unquote(parsed.path)


def validate_markdown(path: Path, text: str, root: Path) -> tuple[Diagnostic, ...]:
    """Return deterministic fence/link diagnostics for one Markdown document."""

    diagnostics: list[Diagnostic] = []
    active_marker: str | None = None
    active_line = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        match = _FENCE_RE.match(line)
        if match is None:
            continue
        marker = match.group(1)[0]
        if active_marker is None:
            active_marker = marker
            active_line = line_number
        elif marker == active_marker:
            active_marker = None
            active_line = 0
    if active_marker is not None:
        diagnostics.append(
            Diagnostic(
                str(path.relative_to(root)),
                active_line,
                "DOC001",
                f"unclosed {active_marker * 3} fence",
            )
        )

    fork_safe = _repository_relative(path, root)
    for match in _LINK_RE.finditer(text):
        local = _link_path(match.group(1))
        if not local:
            continue
        if local in fork_safe:
            continue
        if local.startswith("/"):
            candidate = root / local.lstrip("/")
        else:
            candidate = path.parent / local
        if not candidate.resolve().exists():
            diagnostics.append(
                Diagnostic(
                    str(path.relative_to(root)),
                    _line_number(text, match.start()),
                    "DOC002",
                    f"missing relative link target: {local}",
                )
            )
    return tuple(sorted(diagnostics))


# GitHub resolves a link against `host/owner/name/blob/branch/<the file's own directory>/`, so
# `../../releases` from a file at the repository root lands on that repository's own releases page
# -- whichever repository, on whichever instance, the reader is looking at.  There is no file
# behind it and there is not meant to be: it is the one way a page can point at a release without
# writing down an address that would be upstream's in every fork, and a merge conflict on every
# merge from upstream.
_REPOSITORY_PAGES = ("releases", "issues", "pulls", "tags")


def _repository_relative(path: Path, root: Path) -> frozenset[str]:
    """The fork-safe forms *for this file*, which depend on how deep it sits.

    Two steps up strip the filename and the branch; a file in a subdirectory needs one more for
    each directory between it and the root.  Accepting every depth everywhere would accept a link
    that lands inside `blob/branch/` -- a page about a file rather than the releases -- and
    accepting only two would refuse the correct link from every document under `docs/`.
    """

    depth = len(path.resolve().relative_to(root.resolve()).parts) - 1
    prefix = "../" * (depth + 2)
    return frozenset(prefix + page for page in _REPOSITORY_PAGES)


def _repository_markdown(root: Path) -> tuple[Path, ...]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.md",
        ],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return tuple(
        path
        for raw in result.stdout.split(b"\0")
        if raw
        if (path := root / raw.decode("utf-8")).is_file()
    )


def check_repository(root: Path = ROOT) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for path in _repository_markdown(root):
        diagnostics.extend(validate_markdown(path, path.read_text(encoding="utf-8"), root))
    return tuple(sorted(diagnostics))


def main() -> int:
    diagnostics = check_repository()
    for diagnostic in diagnostics:
        print(diagnostic.render())
    if diagnostics:
        print(f"docs check FAILED: {len(diagnostics)} diagnostic(s)")
        return 1
    print("docs check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
