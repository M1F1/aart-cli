#!/usr/bin/env python3
"""Stamp the release's default Registry into ``aart_cli/_default_registry.py``.

A build-time step beside ``scripts/inject_commit.py``, reading the repository variable
``AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL``, which holds ``<alias>=<url>``. A fork supplies its own
Registry through repository settings instead of patching the source tree -- the arrangement
``AART_CLI_REFERENCE_REGISTRY_URL`` already has, and for the reason D-309 gives: a default naming
one deployment's Registry cannot be right for a fork that can never reach it.

**Unset bakes nothing**, which is the public build's state and is not an error. The rendered module
is then identical to the committed one, so a public wheel is unchanged.

**A malformed value fails the release.** The alternative is a first run that cannot use what it was
given, and that run is the one moment a person has no configuration to fall back on. The release is
the moment somebody is watching.

Idempotent and re-runnable: it rewrites the file from scratch, preserving the module docstring, the
way ``inject_commit`` does. Keep the committed source empty -- only a wheel should carry an address.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aart_cli.configuration.seed import baked_default_registry  # noqa: E402
from aart_cli.domain.result import Err  # noqa: E402

TARGET = ROOT / "aart_cli" / "_default_registry.py"
VARIABLE = "AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL"
SEPARATOR = "="

# Kept verbatim so the rewritten module reads the same as the version-controlled one.
DOCSTRING = '''"""Default Registry this package was built with.

Generated at build time by ``scripts/inject_default_registry.py`` from the release variable
``AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL``, which holds ``<alias>=<url>``.

Both values are empty here and must stay empty in the source tree. Empty means the build baked no
default: the public build's state, and not an error. A real address committed here would make one
deployment's Registry the default for every fork of this project, which is the mistake D-309
removed from the release workflow.

Read this module through ``aart_cli.configuration.seed``, never directly. It is a default rather
than a restriction: it says where a first run starts, never what a person is allowed to connect.
"""'''


def render(alias: str, url: str) -> str:
    return f'{DOCSTRING}\n\nALIAS = "{alias}"\nURL = "{url}"\n'


def render_from(raw: str, source: str) -> str:
    """Render the module for one release variable, or exit non-zero saying what is wrong.

    Surrounding whitespace is the shell's rather than the value's -- a variable set from ``echo``
    arrives with a trailing newline -- so it is trimmed once, here, where the provenance is known.
    Nothing inside the value is repaired: ``configuration.seed`` refuses a newline within an alias,
    and it still does after this trim, so the leniency does not widen what a build may bake.

    Splitting on the first separator only: an alias cannot contain one, and a URL that would is
    refused by the same reader for other reasons.
    """

    value = raw.strip()
    if not value:
        return render("", "")
    if SEPARATOR not in value:
        raise SystemExit(f"{source} must be <alias>{SEPARATOR}<url>, and has no {SEPARATOR!r}")
    alias, url = value.split(SEPARATOR, 1)
    parsed = baked_default_registry(alias, url)
    if isinstance(parsed, Err):
        raise SystemExit(
            f"{source}: " + "; ".join(diagnostic.message for diagnostic in parsed.diagnostics)
        )
    seeded = parsed.value
    return render("", "") if seeded is None else render(seeded.alias.value, seeded.url)


def write(target: Path, raw: str, source: str = VARIABLE) -> int:
    """Render first, write second, so a refused value leaves the previous module in place."""

    rendered = render_from(raw, source)
    target.write_text(rendered, encoding="utf-8")
    return 0


def stamp(target: Path) -> None:
    """Write this environment's stamp to ``target``; the uniform entry point every injector has."""

    write(target, os.environ.get(VARIABLE, ""))


def main() -> int:
    raw = os.environ.get(VARIABLE, "")
    stamp(TARGET)
    baked = raw.strip()
    print(
        f"inject_default_registry: wrote {'no default registry' if not baked else baked} "
        f"to {TARGET.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
