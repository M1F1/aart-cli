"""The terminal a credential store's own prompt is spoken on, and what is said before it (D-486).

Storing a credential is the provider's conversation with a person: `security` asks, the person
types, and this process never learns the value (§161.8, §198, §201). What the provider says is only
that it wants a password, so what the credential is, who needs it and how to get it is written to
the terminal first (D-263). The TUI lends its drawn screen around this; the command line has no
screen to lend and only says it.
"""

from __future__ import annotations

import shutil
import sys
import textwrap
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TextIO


def terminal_present() -> bool:
    """Whether a person can answer a credential store's prompt on this process's terminal."""

    return sys.stdin is not None and sys.stdin.isatty()


class BriefingHandover:
    """Say the briefing on `stream`, then let the provider speak; a `TerminalHandover`.

    Each line is wrapped to the terminal's width without ever breaking a link, keeping its indent.
    """

    def __init__(
        self, *, stream: TextIO | None = None, columns: Callable[[], int] | None = None
    ) -> None:
        self._stream = stream
        self._columns = columns

    def __call__(self, briefing: tuple[str, ...] = ()):
        return self._briefed(briefing)

    def _say(self, briefing: tuple[str, ...]) -> None:
        if not briefing:
            return
        stream = self._stream if self._stream is not None else sys.stdout
        width = self._columns() if self._columns is not None else shutil.get_terminal_size().columns
        for line in briefing:
            indent = line[: len(line) - len(line.lstrip(" "))]
            wrapped = textwrap.wrap(
                line.strip(),
                width=max(width - 1, 20),
                initial_indent=indent,
                subsequent_indent=indent + "  ",
                break_long_words=False,
                break_on_hyphens=False,
            )
            stream.write("\n".join(wrapped or [""]) + "\n")
        stream.flush()

    @contextmanager
    def _briefed(self, briefing: tuple[str, ...]) -> Iterator[None]:
        self._say(briefing)
        yield


__all__ = ["BriefingHandover", "terminal_present"]
