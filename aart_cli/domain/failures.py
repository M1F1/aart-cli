"""A failure aart-cli met, as it is journaled and sent (§215, docs/telemetry-api-v1.md).

Pure. What a failure keeps is fixed here, by the shapes the contract's `failure` object allows:
its kind, where it happened in aart-cli's own words, the exception's type name, the frames of
aart-cli's own package as `module:function:line`, diagnostic codes, the exit code, Python's version
and the platform. Each is matched whole against its pattern, so a message, a path, an argument or a
value cannot ride in one of them (INV-333); what does not match is dropped, never cut to fit.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .result import Err, Ok, Result

__all__ = [
    "FAILURE_INVALID",
    "JOURNAL_STATES",
    "MAX_DIAGNOSTICS",
    "MAX_FRAMES",
    "PLATFORMS",
    "Failure",
    "FailureGroup",
    "FailureKind",
    "JournaledFailure",
    "failure_of",
    "grouped",
]

FAILURE_INVALID = DiagnosticCode("failure-invalid")
MAX_FRAMES = 30
MAX_DIAGNOSTICS = 10
PLATFORMS = frozenset({"darwin", "linux", "other"})

_PLACE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_EXCEPTION = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,127}")
_MODULE = re.compile(r"aart_cli(?:\.[A-Za-z0-9_]+)*")
_FUNCTION = re.compile(r"[A-Za-z0-9_<>]{1,128}")
_FRAME = re.compile(
    r"(?P<module>[A-Za-z0-9_.]{1,128}):(?P<function>[A-Za-z0-9_<>]{1,128}):[0-9]{1,6}"
)
_CODE = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}")
_PYTHON = re.compile(r"[0-9A-Za-z.+-]{1,32}")
_FINGERPRINT = re.compile(r"[0-9a-f]{16}")
_FIELDS = frozenset(
    {"fingerprint", "exception", "frames", "diagnostics", "exit_code", "python", "platform"}
)


class FailureKind(str, Enum):
    #: An exception no handler took.
    CRASH = "crash"
    #: A command that ended with a nonzero exit code, or a terminal action that stopped.
    ERROR = "error"
    #: Ctrl+C: the person's choice, counted rather than diagnosed.
    INTERRUPTED = "interrupted"


def _frame(module: str, function: str, line: int) -> str | None:
    if (
        not isinstance(module, str)
        or len(module) > 128
        or _MODULE.fullmatch(module) is None
        or not isinstance(function, str)
        or _FUNCTION.fullmatch(function) is None
        or not isinstance(line, int)
        or isinstance(line, bool)
        or not 0 <= line <= 999999
    ):
        return None
    return f"{module}:{function}:{line}"


def _frame_is_kept(frame: object) -> bool:
    if not isinstance(frame, str):
        return False
    found = _FRAME.fullmatch(frame)
    return found is not None and _MODULE.fullmatch(found["module"]) is not None


@dataclass(frozen=True, slots=True)
class Failure:
    """One failure as the contract's `failure` object carries it, with its kind and place."""

    kind: FailureKind
    place: str
    exception: str | None
    frames: tuple[str, ...]
    diagnostics: tuple[str, ...]
    exit_code: int | None
    python: str
    platform: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, FailureKind)
            or not isinstance(self.place, str)
            or _PLACE.fullmatch(self.place) is None
            or (self.exception is None and self.kind is FailureKind.CRASH)
            or (
                self.exception is not None
                and (
                    not isinstance(self.exception, str)
                    or _EXCEPTION.fullmatch(self.exception) is None
                )
            )
            or not isinstance(self.frames, tuple)
            or len(self.frames) > MAX_FRAMES
            or not all(_frame_is_kept(frame) for frame in self.frames)
            or not isinstance(self.diagnostics, tuple)
            or len(self.diagnostics) > MAX_DIAGNOSTICS
            or len(set(self.diagnostics)) != len(self.diagnostics)
            or not all(isinstance(code, str) and _CODE.fullmatch(code) for code in self.diagnostics)
            or (
                self.exit_code is not None
                and (
                    not isinstance(self.exit_code, int)
                    or isinstance(self.exit_code, bool)
                    or not 0 <= self.exit_code <= 255
                )
            )
            or not isinstance(self.python, str)
            or _PYTHON.fullmatch(self.python) is None
            or self.platform not in PLATFORMS
        ):
            raise ValueError("a failure does not follow the contract")

    @property
    def fingerprint(self) -> str:
        """The first 16 hex digits of the SHA-256 of what names the defect: everything kept but
        the line numbers, the exit code and the versions (INV-334)."""

        body = json.dumps(
            [
                self.kind.value,
                self.place,
                self.exception or "",
                [frame.rsplit(":", 1)[0] for frame in self.frames],
                list(self.diagnostics),
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    def document(self) -> dict[str, object]:
        body: dict[str, object] = {"fingerprint": self.fingerprint}
        if self.exception is not None:
            body["exception"] = self.exception
        body["frames"] = list(self.frames)
        body["diagnostics"] = list(self.diagnostics)
        if self.exit_code is not None:
            body["exit_code"] = self.exit_code
        body["python"] = self.python
        body["platform"] = self.platform
        return body

    @classmethod
    def from_document(cls, kind: str, place: str, document: object) -> Result[Failure]:
        """A `failure` object read back, or why it is not one: a field the contract does not
        name, a shape it does not allow, or a fingerprint that is not its own."""

        invalid = Err(
            (Diagnostic(FAILURE_INVALID, Severity.ERROR, "a failure is not the contract's"),)
        )
        if not isinstance(document, Mapping) or not set(document) <= _FIELDS:
            return invalid
        frames, codes = document.get("frames"), document.get("diagnostics")
        if not isinstance(frames, list) or not isinstance(codes, list):
            return invalid
        try:
            failure = cls(
                FailureKind(kind),
                place,
                document.get("exception"),
                tuple(frames),
                tuple(codes),
                document.get("exit_code"),
                document.get("python"),  # type: ignore[arg-type]
                document.get("platform"),  # type: ignore[arg-type]
            )
        except ValueError:
            return invalid
        fingerprint = document.get("fingerprint")
        if not isinstance(fingerprint, str) or _FINGERPRINT.fullmatch(fingerprint) is None:
            return invalid
        return Ok(failure) if fingerprint == failure.fingerprint else invalid


def failure_of(
    kind: FailureKind,
    place: str,
    exception: str | None,
    frames: Iterable[tuple[str, str, int]],
    diagnostics: Iterable[str],
    exit_code: int | None,
    python: str,
    platform: str,
) -> Failure | None:
    """What is kept of a failure, or `None` when its place, versions or platform cannot be.

    Frames outside aart-cli's own package are left out and the innermost `MAX_FRAMES` kept; codes
    the contract cannot carry are left out and the first `MAX_DIAGNOSTICS` distinct ones kept. A
    crash whose type cannot be named is an `Exception`; anything else simply has none.
    """

    kept = [frame for frame in (_frame(*item) for item in frames) if frame is not None]
    codes: list[str] = []
    for code in diagnostics:
        if isinstance(code, str) and _CODE.fullmatch(code) and code not in codes:
            codes.append(code)
    named = (
        exception
        if isinstance(exception, str) and _EXCEPTION.fullmatch(exception) is not None
        else None
    )
    if named is None and kind is FailureKind.CRASH:
        named = "Exception"
    try:
        return Failure(
            kind,
            place,
            named,
            tuple(kept[-MAX_FRAMES:]),
            tuple(codes[:MAX_DIAGNOSTICS]),
            exit_code,
            python,
            platform,
        )
    except ValueError:
        return None


JOURNAL_STATES = frozenset({"waiting", "sent", "rejected", "skipped"})


@dataclass(frozen=True, slots=True)
class JournaledFailure:
    """A failure as the journal keeps it: its event id, when, in which aart-cli, and whether it
    waits, was sent, was rejected or was skipped."""

    event_id: str
    occurred_at: str
    version: str
    state: str
    failure: Failure


@dataclass(frozen=True, slots=True)
class FailureGroup:
    """Every journaled failure with one fingerprint: the newest of them, how many, when the first
    and the last were, and the aart-cli versions they were in, newest first."""

    failure: Failure
    count: int
    first_seen: str
    last_seen: str
    versions: tuple[str, ...]


def grouped(entries: Iterable[JournaledFailure]) -> tuple[FailureGroup, ...]:
    """`entries` by fingerprint, the group seen last first; each keeps its newest failure."""

    groups: dict[str, list[JournaledFailure]] = {}
    for entry in entries:
        groups.setdefault(entry.failure.fingerprint, []).append(entry)
    result = []
    for members in groups.values():
        ordered = sorted(members, key=lambda entry: entry.occurred_at, reverse=True)
        versions: list[str] = []
        for entry in ordered:
            if entry.version not in versions:
                versions.append(entry.version)
        result.append(
            FailureGroup(
                ordered[0].failure,
                len(ordered),
                ordered[-1].occurred_at,
                ordered[0].occurred_at,
                tuple(versions),
            )
        )
    return tuple(sorted(result, key=lambda group: group.last_seen, reverse=True))
