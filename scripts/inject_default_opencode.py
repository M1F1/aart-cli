#!/usr/bin/env python3
"""Stamp which OpenCode project plugins are installed for into ``aart_cli/_default_opencode.py``.

A build-time step beside ``scripts/inject_default_usage.py``, reading the repository variable
``AART_CLI_DEFAULT_OPENCODE``: ``1`` or ``2``. Which OpenCode an organisation runs is a
deployment's decision, the way its Registry is (D-309), so a fork sets it in repository settings and
the source tree carries none (§171.3, D-532).

**Unset bakes nothing**, which is OpenCode 1 and the public build's state, and is not an error. The
rendered module is then identical to the committed one.

**A value aart-cli cannot honour fails the release**, rather than being read as 1 on somebody's
machine.

Idempotent and re-runnable: it rewrites the file from scratch. Keep the committed source empty.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aart_cli.domain.opencode_runtime import parse_opencode_runtime  # noqa: E402
from aart_cli.domain.result import Err  # noqa: E402

TARGET = ROOT / "aart_cli" / "_default_opencode.py"
VARIABLE = "AART_CLI_DEFAULT_OPENCODE"

# Kept verbatim so the rewritten module reads the same as the version-controlled one.
DOCSTRING = '''"""Which OpenCode this package installs project plugins for until a person chooses (§171.3).

Generated at build time by ``scripts/inject_default_opencode.py`` from the release variable
``AART_CLI_DEFAULT_OPENCODE``: ``1`` or ``2``.

Empty here, and it must stay empty in the source tree. Empty is OpenCode 1, the one most people
run and the only one published as a release. Which OpenCode an organisation runs is that
deployment's decision, the way its Registry is (D-309, D-532).

Read this module through ``aart_cli.configuration.seed``, never directly.
"""'''


def render(runtime: str) -> str:
    return f'{DOCSTRING}\n\nRUNTIME = "{runtime}"\n'


def render_from(raw: str, source: str) -> str:
    """Render the module for one release variable, or exit non-zero saying what is wrong."""

    parsed = parse_opencode_runtime(raw)
    if isinstance(parsed, Err):
        raise SystemExit(
            f"{source}: " + "; ".join(diagnostic.message for diagnostic in parsed.diagnostics)
        )
    # Empty stays empty, so an unset variable leaves the committed module byte for byte.
    return render(raw.strip() and str(parsed.value))


def write(target: Path, raw: str, source: str = VARIABLE) -> int:
    """Render first, write second, so a refused value leaves the previous module in place."""

    rendered = render_from(raw, source)
    target.write_text(rendered, encoding="utf-8")
    return 0


def stamp(target: Path) -> None:
    """Write this environment's stamp to ``target``; the uniform entry point every injector has."""

    write(target, os.environ.get(VARIABLE, ""))


def main() -> int:
    stamp(TARGET)
    raw = os.environ.get(VARIABLE, "").strip()
    print(
        f"inject_default_opencode: wrote {('OpenCode ' + raw) if raw else 'no default OpenCode'} "
        f"to {TARGET.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
