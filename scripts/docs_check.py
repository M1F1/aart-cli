#!/usr/bin/env python3
"""Non-mutating Markdown and AART documentation consistency checks."""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
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


# History and the target, not instructions: both name commands on purpose that the executable
# does not have (§177).
_COMMANDS_NOT_HELD = ("docs/refactor/", "docs/product-specification/")
_PLACEHOLDER_RE = re.compile(r"<[^<>\s]+>")
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
#: Where a shell line stops being the `aart-cli` invocation: a pipe, a list or a redirection.
_SHELL_BREAKS = frozenset({"|", "||", "&", "&&", ";", ">", ">>", "<", "2>", "&>"})


class _Rejected(Exception):
    pass


def _fenced_commands(text: str) -> Iterator[tuple[int, str]]:
    """Every `aart-cli` invocation in a fenced block, joined across `\\` continuations."""

    active_marker: str | None = None
    pending: tuple[int, str] | None = None
    for line_number, line in enumerate(text.splitlines(), 1):
        match = _FENCE_RE.match(line)
        if match is not None:
            marker = match.group(1)[0]
            if active_marker is None:
                active_marker = marker
            elif marker == active_marker:
                active_marker = None
            if pending is not None:
                yield pending
                pending = None
            continue
        if active_marker is None:
            continue
        if pending is not None:
            start, joined = pending
            joined = f"{joined} {line.strip()}"
        else:
            stripped = line.strip().removeprefix("$ ")
            words = stripped.split()
            while words and _ENV_ASSIGNMENT_RE.match(words[0]):
                words.pop(0)
            if not words or words[0] != "aart-cli":
                continue
            start, joined = line_number, " ".join(words)
        if joined.endswith("\\"):
            pending = (start, joined[:-1].rstrip())
            continue
        pending = None
        yield start, joined
    if pending is not None:
        yield pending


def command_failure(command: str, parser: argparse.ArgumentParser) -> str | None:
    """Hand one documented `aart-cli …` line to the parser; return why it refused, or `None`."""

    lexer = shlex.shlex(
        _PLACEHOLDER_RE.sub("placeholder", command), posix=True, punctuation_chars=True
    )
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError as error:
        return f"cannot be read as a shell line: {error}"
    arguments: list[str] = []
    for word in words[1:]:
        if word in _SHELL_BREAKS:
            break
        arguments.append(word)

    def reject(_self: argparse.ArgumentParser, message: str) -> None:
        raise _Rejected(message)

    original = argparse.ArgumentParser.error
    argparse.ArgumentParser.error = reject  # type: ignore[method-assign]
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(arguments)
    except _Rejected as rejected:
        return str(rejected)
    except SystemExit as exited:
        if exited.code not in (0, None):
            return f"exits {exited.code}"
    finally:
        argparse.ArgumentParser.error = original  # type: ignore[method-assign]
    return None


def _holds_commands(path: Path, root: Path) -> bool:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return not relative.startswith(_COMMANDS_NOT_HELD)


def validate_markdown(
    path: Path, text: str, root: Path, *, parser: argparse.ArgumentParser | None = None
) -> tuple[Diagnostic, ...]:
    """Return deterministic fence/link diagnostics for one Markdown document.

    With `parser`, every fenced `aart-cli` command outside history and the specification must also
    parse (DOC003).
    """

    diagnostics: list[Diagnostic] = []
    if parser is not None and _holds_commands(path, root):
        for line_number, command in _fenced_commands(text):
            failure = command_failure(command, parser)
            if failure is not None:
                diagnostics.append(
                    Diagnostic(
                        str(path.relative_to(root)),
                        line_number,
                        "DOC003",
                        f"`{command}` does not parse: {failure}",
                    )
                )
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


def _shipped_parser() -> argparse.ArgumentParser:
    # The checkout's own parser, not an installed copy: the documents describe this tree.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from aart_cli.cli_parser import build_parser

    return build_parser()


def check_repository(root: Path = ROOT) -> tuple[Diagnostic, ...]:
    parser = _shipped_parser()
    diagnostics: list[Diagnostic] = []
    for path in _repository_markdown(root):
        diagnostics.extend(
            validate_markdown(path, path.read_text(encoding="utf-8"), root, parser=parser)
        )
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
