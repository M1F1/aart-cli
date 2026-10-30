#!/usr/bin/env python3
"""Stamp the telemetry server a build offers into ``aart_cli/_default_telemetry.py`` (§213).

A build-time step beside ``scripts/inject_default_usage.py``, reading the repository variables
``AART_CLI_TELEMETRY_ENDPOINT``, a server's base address, and
``AART_CLI_TELEMETRY_UNMANAGED_USES``, whether uses aart-cli did not install are sent until a
person chooses (D-508): unset, ``on`` or ``true`` sends them, ``off`` or ``false`` does not. Where an organisation's telemetry
server is, is that deployment's, the way its Registry is (D-309), so a fork sets it in repository
settings and the source tree carries none (D-503).

**Unset bakes nothing**, which is the public build's state and is not an error. The rendered
module is then identical to the committed one.

**An address aart-cli would refuse fails the release**, rather than on somebody's machine:
plain ``http://`` to anything but loopback, a user, a password, a query or a fragment; and a
value for unmanaged uses that is none of the four.

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
from aart_cli.domain.telemetry import (  # noqa: E402
    parse_telemetry_endpoint,
    parse_unmanaged_uses,
)

TARGET = ROOT / "aart_cli" / "_default_telemetry.py"
VARIABLE = "AART_CLI_TELEMETRY_ENDPOINT"
UNMANAGED_VARIABLE = "AART_CLI_TELEMETRY_UNMANAGED_USES"

# Kept verbatim so the rewritten module reads the same as the version-controlled one.
DOCSTRING = '''"""The telemetry server this package sends to, and whether it sends uses it did not install (§213).

Generated at build time by ``scripts/inject_default_telemetry.py`` from the release variables
``AART_CLI_TELEMETRY_ENDPOINT``: a server's base address, such as ``https://telemetry.example.com``;
and ``AART_CLI_TELEMETRY_UNMANAGED_USES``: ``on`` or ``off``.

Both are empty here, and must stay empty in the source tree. An empty address names no server:
telemetry is then turned on only with an address given. A baked address turns telemetry on at a
home's first start where nobody turned it on or off, and it then sends Activity's history too
(D-503, D-505). An empty ``UNMANAGED_USES`` sends uses of skills and MCPs aart-cli did not install,
by name, until a person chooses otherwise in Settings; ``off`` does not (D-508).

Read this module through ``aart_cli.configuration.seed``, never directly.
"""'''


def render(endpoint: str, unmanaged: str = "") -> str:
    return f'{DOCSTRING}\n\nENDPOINT = "{endpoint}"\nUNMANAGED_USES = "{unmanaged}"\n'


def render_from(raw: str, source: str, unmanaged: str = "") -> str:
    """Render the module for the release variables, or exit non-zero saying what is wrong.

    Unset unmanaged uses is baked empty, which sends them, so an unset build renders the committed
    module byte for byte.
    """

    choice = unmanaged.strip().lower()
    sends = parse_unmanaged_uses(choice)
    if isinstance(sends, Err):
        raise SystemExit(
            f"{UNMANAGED_VARIABLE}: "
            + "; ".join(diagnostic.message for diagnostic in sends.diagnostics)
        )
    value = raw.strip()
    if not value:
        return render("", choice)
    parsed = parse_telemetry_endpoint(value)
    if isinstance(parsed, Err):
        raise SystemExit(
            f"{source}: " + "; ".join(diagnostic.message for diagnostic in parsed.diagnostics)
        )
    return render(parsed.value, choice)


def write(target: Path, raw: str, source: str = VARIABLE, unmanaged: str = "") -> int:
    """Render first, write second, so a refused value leaves the previous module in place."""

    rendered = render_from(raw, source, unmanaged)
    target.write_text(rendered, encoding="utf-8")
    return 0


def stamp(target: Path) -> None:
    """Write this environment's stamp to ``target``; the uniform entry point every injector has."""

    write(target, os.environ.get(VARIABLE, ""), unmanaged=os.environ.get(UNMANAGED_VARIABLE, ""))


def main() -> int:
    stamp(TARGET)
    baked = os.environ.get(VARIABLE, "").strip()
    print(
        "inject_default_telemetry: wrote "
        f"{'a telemetry server' if baked else 'no telemetry server'} to {TARGET.relative_to(ROOT)}"
        f"; uses aart-cli did not install: {os.environ.get(UNMANAGED_VARIABLE, '').strip() or 'on'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
