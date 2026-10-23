#!/usr/bin/env python3
"""Stamp the release's local version label into ``pyproject.toml``.

A build-time step beside ``scripts/inject_default_registry.py``, reading the repository variable
``AART_CLI_LOCAL_VERSION_LABEL``. A fork that bakes its own default Registry ships other bytes under
the tag's version than the public wheel does, and once that public wheel is on PyPI an index group
proxying PyPI lists both under one filename. A PEP 440 local label (``1.4.0+corp``) gives the fork's
wheel a filename of its own; ``aart-cli==1.4.0`` still matches it, and pip prefers it (D-476).

**Only the distribution's version moves.** ``aart_cli.__version__`` keeps the tag's version, because
``aart-cli --version`` is what a Registry's CI compares with its ``.aart-cli-version``.

**Unset labels nothing**, which is the public build's state; the file is then left byte for byte.

**A malformed label fails the release.** The grammar is the part of PEP 440's local label that is
also SemVer build metadata and needs no normalisation: lower-case letters and digits, in segments
joined by dots, with no leading zero on a segment of digits only. Anything else is refused rather
than normalised, so the label in the variable is the label in the filename.

Idempotent: a version already carrying a label is relabelled, never labelled twice.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "pyproject.toml"
VARIABLE = "AART_CLI_LOCAL_VERSION_LABEL"
# A segment of digits only is a number to PEP 440, which drops its leading zeros (`00` becomes `0`),
# so such a segment is refused rather than built into a filename that differs from the variable.
_SEGMENT = r"(?:0|[1-9][0-9]*|[a-z0-9]*[a-z][a-z0-9]*)"
LABEL_RE = re.compile(rf"{_SEGMENT}(?:\.{_SEGMENT})*")
# The `[project]` table's own `version`, and no other: the line must follow `[project]` with no
# other table header in between.
_PROJECT_VERSION_RE = re.compile(
    r'(?ms)^(\[project\]\n(?:(?!^\[).)*?^version = ")([^"+]+)(?:\+[^"]*)?(")'
)


def label_from(raw: str, source: str) -> str:
    """The label the variable holds, or exit non-zero saying what is wrong with it.

    Surrounding whitespace is the shell's, as in the other injectors, so it is trimmed once here.
    """

    label = raw.strip()
    if label and LABEL_RE.fullmatch(label) is None:
        raise SystemExit(
            f"{source} must be lower-case letters and digits, in segments joined by dots, with "
            f"no leading zero on a number, such as corp or corp.2; got {label!r}"
        )
    return label


def render(text: str, label: str) -> str:
    """``text`` with the project version labelled, or unchanged when there is no label."""

    if not label:
        return text
    rendered, found = _PROJECT_VERSION_RE.subn(rf"\g<1>\g<2>+{label}\g<3>", text, count=1)
    if not found:
        raise SystemExit("pyproject.toml has no [project] version to label")
    return rendered


def write(target: Path, raw: str, source: str = VARIABLE) -> int:
    """Render first, write second, so a refused label leaves the file as it was."""

    label = label_from(raw, source)
    rendered = render(target.read_text(encoding="utf-8"), label)
    if label:
        target.write_text(rendered, encoding="utf-8")
    return 0


def stamp(target: Path) -> None:
    """Write this environment's stamp to ``target``; the uniform entry point every injector has."""

    write(target, os.environ.get(VARIABLE, ""))


def main() -> int:
    label = os.environ.get(VARIABLE, "").strip()
    stamp(TARGET)
    print(
        f"inject_local_version: {'no local version label' if not label else '+' + label} "
        f"in {TARGET.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
