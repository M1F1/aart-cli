#!/usr/bin/env python3
"""Stamp the harnesses that record artifact usage by default into ``aart_cli/_default_usage.py``.

A build-time step beside ``scripts/inject_default_registry.py``, reading the repository variable
``AART_CLI_DEFAULT_USAGE_HARNESSES``: harness names separated by commas, such as ``opencode``, or
``none``. Recording without asking is a deployment's decision, the way its Registry is (D-309), so
a fork sets it in repository settings and the source tree carries none (§212, D-502).

**Unset or ``none`` bakes nothing**, which is the public build's state and is not an error: such a
wheel records nowhere until a person turns it on. The rendered module is then identical to the
committed one.

**A value aart-cli cannot honour fails the release**, rather than being ignored on somebody's
machine: a harness without hooks, an unknown name, an empty one or a repeated one.

Idempotent and re-runnable: it rewrites the file from scratch. Keep the committed source empty.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aart_cli.domain.artifact_usage import parse_usage_harnesses  # noqa: E402
from aart_cli.domain.result import Err  # noqa: E402

TARGET = ROOT / "aart_cli" / "_default_usage.py"
VARIABLE = "AART_CLI_DEFAULT_USAGE_HARNESSES"

# Kept verbatim so the rewritten module reads the same as the version-controlled one.
DOCSTRING = '''"""Harnesses this package records artifact usage in until a person chooses otherwise (§212).

Generated at build time by ``scripts/inject_default_usage.py`` from the release variable
``AART_CLI_DEFAULT_USAGE_HARNESSES``: harness names separated by commas, or ``none``.

Empty here, and it must stay empty in the source tree. Empty records nowhere without asking: the
public build's state. Which harnesses an organisation records by default is that deployment's
decision, the way its Registry is (D-309, D-502).

Read this module through ``aart_cli.configuration.seed``, never directly.
"""'''


def render(harnesses: tuple[str, ...]) -> str:
    return f'{DOCSTRING}\n\nHARNESSES = "{",".join(harnesses)}"\n'


def render_from(raw: str, source: str) -> str:
    """Render the module for one release variable, or exit non-zero saying what is wrong."""

    parsed = parse_usage_harnesses(raw)
    if isinstance(parsed, Err):
        raise SystemExit(
            f"{source}: " + "; ".join(diagnostic.message for diagnostic in parsed.diagnostics)
        )
    return render(parsed.value)


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
    parsed = parse_usage_harnesses(os.environ.get(VARIABLE, ""))
    baked = ",".join(parsed.value) if not isinstance(parsed, Err) else ""
    print(
        f"inject_default_usage: wrote {baked or 'no default usage harnesses'} "
        f"to {TARGET.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
