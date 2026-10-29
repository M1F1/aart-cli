#!/usr/bin/env python3
"""Stamp the telemetry server a build offers into ``aart_cli/_default_telemetry.py`` (§213).

A build-time step beside ``scripts/inject_default_usage.py``, reading the repository variable
``AART_CLI_TELEMETRY_ENDPOINT``: a server's base address. Where an organisation's telemetry
server is, is that deployment's, the way its Registry is (D-309), so a fork sets it in repository
settings and the source tree carries none (D-503).

**Unset bakes nothing**, which is the public build's state and is not an error. The rendered
module is then identical to the committed one.

**An address aart-cli would refuse fails the release**, rather than on somebody's machine:
plain ``http://`` to anything but loopback, a user, a password, a query or a fragment.

Idempotent and re-runnable: it rewrites the file from scratch. Keep the committed source empty.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aart_cli.domain.result import Err  # noqa: E402
from aart_cli.domain.telemetry import parse_telemetry_endpoint  # noqa: E402

TARGET = ROOT / "aart_cli" / "_default_telemetry.py"
VARIABLE = "AART_CLI_TELEMETRY_ENDPOINT"

# Kept verbatim so the rewritten module reads the same as the version-controlled one.
DOCSTRING = '''"""The telemetry server this package offers when a person turns telemetry on (§213).

Generated at build time by ``scripts/inject_default_telemetry.py`` from the release variable
``AART_CLI_TELEMETRY_ENDPOINT``: a server's base address, such as ``https://telemetry.example.com``.

Empty here, and it must stay empty in the source tree. Empty offers no server: telemetry is then
turned on only with an address given. A baked address alone sends nothing; telemetry stays off
until a person turns it on (D-503).

Read this module through ``aart_cli.configuration.seed``, never directly.
"""'''


def render(endpoint: str) -> str:
    return f'{DOCSTRING}\n\nENDPOINT = "{endpoint}"\n'


def render_from(raw: str, source: str) -> str:
    """Render the module for one release variable, or exit non-zero saying what is wrong."""

    value = raw.strip()
    if not value:
        return render("")
    parsed = parse_telemetry_endpoint(value)
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
    baked = os.environ.get(VARIABLE, "").strip()
    print(
        "inject_default_telemetry: wrote "
        f"{'a telemetry server' if baked else 'no telemetry server'} to {TARGET.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
