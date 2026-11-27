"""Which OpenCode a machine runs, as far as where a project plugin goes (§171.3, D-532).

OpenCode 1.x and OpenCode 2 read the same settings files, but load a project plugin from different
places: 1.x only from the `plugin` list of the project's `opencode.json`, OpenCode 2 also from a
directory of its own under `.opencode/plugins/`, which it finds by itself. Both at once is a plugin
OpenCode 2 loads twice, and a list entry is resolved from the directory OpenCode 2 was started in,
so it is lost from a subdirectory (B-276). One installation can therefore suit only one of them.

Nothing on the machine says which one a person runs: a launcher starts its own binary, which is
not the `opencode` on `PATH`. So it is a choice -- this build's default until a person makes it in
Settings -- and never a detection.
"""

from __future__ import annotations

from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .result import Err, Ok, Result

__all__ = [
    "OPENCODE_RUNTIMES",
    "OPENCODE_RUNTIME_INVALID",
    "parse_opencode_runtime",
]

#: The OpenCode runtimes a project plugin can be installed for.
OPENCODE_RUNTIMES: tuple[int, ...] = (1, 2)

OPENCODE_RUNTIME_INVALID = DiagnosticCode("opencode-runtime-invalid")


def parse_opencode_runtime(raw: str) -> Result[int]:
    """`AART_CLI_DEFAULT_OPENCODE`: `1` or `2`; empty is 1, the OpenCode most people run.

    Empty rather than unset, because a release variable cannot be told unset from empty (D-502).
    Spaces around the value are the shell's and are dropped; nothing else is repaired.
    """

    value = raw.strip() if isinstance(raw, str) else None
    if value == "":
        return Ok(1)
    if value in {str(runtime) for runtime in OPENCODE_RUNTIMES}:
        return Ok(int(value))
    return Err(
        (
            Diagnostic(
                OPENCODE_RUNTIME_INVALID,
                Severity.ERROR,
                f"default OpenCode {raw!r} is not 1 or 2",
            ),
        )
    )
