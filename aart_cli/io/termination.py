"""An end by SIGTERM or SIGHUP, journaled (§215, B-265).

A closed terminal sends SIGHUP and a supervisor SIGTERM. Neither raises anything a command or the
terminal application could catch, so without this an end by either left no trace in the journal.

`TerminationGuard` takes a signal only while it holds its default handling -- one ignored or handled
by whoever started aart-cli is left as it was -- and only in the main thread, where Python allows
it. On the signal it records the end at the place it holds, with the shell's exit code
(128 + the signal's number), then gives the signal back its default handling and sends it again,
so the process ends exactly as it would have without it (INV-335). A failure while recording is
dropped.
"""

from __future__ import annotations

import os
import signal
from collections.abc import Callable
from types import FrameType, TracebackType

__all__ = ["TerminationGuard"]

_SIGNALS = tuple(
    number
    for number in (getattr(signal, name, None) for name in ("SIGTERM", "SIGHUP"))
    if number is not None
)


class TerminationGuard:
    """Records an end by SIGTERM or SIGHUP at `place` while the `with` block runs."""

    def __init__(self, record: Callable[[str, int], object], place: str) -> None:
        self.place = place
        self._record = record
        self._taken: list[int] = []

    def __enter__(self) -> TerminationGuard:
        for number in _SIGNALS:
            try:
                if signal.getsignal(number) is signal.SIG_DFL:
                    signal.signal(number, self._end)
                    self._taken.append(number)
            except (OSError, ValueError):  # not the main thread: nothing is taken
                continue
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for number in self._taken:
            try:
                if signal.getsignal(number) == self._end:
                    signal.signal(number, signal.SIG_DFL)
            except (OSError, ValueError):
                continue
        self._taken.clear()

    def _end(self, number: int, frame: FrameType | None) -> None:
        try:
            self._record(self.place, 128 + number)
        except Exception:  # noqa: BLE001 -- recording never changes how the process ends
            pass
        signal.signal(number, signal.SIG_DFL)
        os.kill(os.getpid(), number)
