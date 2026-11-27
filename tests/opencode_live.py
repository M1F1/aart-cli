"""Running a real `opencode` for the live tests, isolated from the person running them.

Two things the live tests got wrong on some machines:

- **Output cut at 64 KB.** OpenCode exits as soon as it has written, and a Bun process writing to a
  pipe can exit before the pipe is drained: `opencode debug config` on 1.18.30 prints more than the
  64 KB a pipe holds, and the test read a cut-off document that no longer parsed. Stdout goes to a
  file instead, which is written before the process exits.
- **The developer's own configuration.** Only `HOME` and the `XDG_*` directories were replaced, so a
  shell where a launcher had set `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR` or
  `OPENCODE_CONFIG_PROJECT_DISABLE` measured that configuration, not the test's. Every `OPENCODE_*`
  variable is dropped.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


class OpenCodeUnavailable(Exception):
    """`opencode` is not installed here, or refused the command; the caller skips."""


def run_opencode(*arguments: str, home: Path, cwd: Path, timeout: int = 180) -> str:
    """What `opencode <arguments>` prints, run with `home` as its home and nothing of the caller's."""

    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(("XDG_", "OPENCODE_"))
    }
    environment["HOME"] = str(home)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
        try:
            completed = subprocess.run(
                ("opencode", *arguments),
                cwd=str(cwd),
                env=environment,
                stdout=output,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            raise OpenCodeUnavailable("`opencode` is not installed") from error
        if completed.returncode != 0:
            raise OpenCodeUnavailable(
                f"`opencode {' '.join(arguments)}` is unavailable: {completed.stderr[:200]}"
            )
        output.seek(0)
        return output.read()
