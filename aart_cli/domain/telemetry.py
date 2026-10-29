"""What is sent to a telemetry server, where, and when (§213, docs/telemetry-api-v1.md).

Pure. The outbox, the clock, the lock and HTTP are the caller's; this module decides. Every rule a
version-1 server applies to an event is applied here first, so an event that leaves this machine
is one the contract allows, and nothing else -- no project, path, argument or credential -- can be
put into one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum

from .artifact_usage import InstalledName, UsageKind, resolve_installed
from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .result import Err, Ok, Result

__all__ = [
    "AUTH_PAUSE",
    "BACKOFF",
    "BATCH_PATH",
    "BATCH_SIZE",
    "HTTP_TIMEOUT_SECONDS",
    "MAX_REQUESTS_PER_RUN",
    "RUN_SECONDS",
    "SYNC_INTERVAL",
    "TELEMETRY_ENDPOINT_INVALID",
    "TELEMETRY_SOURCES",
    "Answer",
    "AnswerKind",
    "SyncState",
    "TelemetryEvent",
    "after_failure",
    "after_success",
    "batch_document",
    "classify_answer",
    "contract_moment",
    "lifecycle_event",
    "lifecycle_event_type",
    "parse_telemetry_endpoint",
    "sync_due",
    "use_event",
]

#: The least time between two successful synchronisations; checked when something is recorded,
#: never on a timer (D-503).
SYNC_INTERVAL = timedelta(seconds=600)
#: What one request carries at most. It bounds a request; it never decides when to send.
BATCH_SIZE = 100
HTTP_TIMEOUT_SECONDS = 10.0
#: How long after the n-th failure in a row the next attempt may start, before jitter.
BACKOFF: tuple[timedelta, ...] = tuple(timedelta(minutes=minutes) for minutes in (1, 2, 5, 10, 30))
#: How long a refused authorisation stops automatic attempts.
AUTH_PAUSE = timedelta(hours=1)
#: One synchronisation sends at most this many requests and runs at most this long.
MAX_REQUESTS_PER_RUN = 20
RUN_SECONDS = 60.0

BATCH_PATH = "/api/v1/events/batch"
TELEMETRY_ENDPOINT_INVALID = DiagnosticCode("telemetry-endpoint-invalid")

#: The contract's `source` for a use recorded by each harness's hook.
TELEMETRY_SOURCES: dict[str, str] = {"claude": "claude_hook", "opencode": "opencode_plugin"}

_LIFECYCLE_EVENTS = {
    "install": "artifact.installed",
    "update": "artifact.updated",
    "downgrade": "artifact.updated",
    "uninstall": "artifact.removed",
}

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_MOMENT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z")
_NAME = re.compile(r"[0-9A-Za-z._@:+-]{1,200}")
_KIND = re.compile(r"[a-z0-9-]{1,64}")
_VERSION = re.compile(r"[0-9A-Za-z.+-]{1,64}")
_EVENT_SOURCES = {
    "artifact.installed": frozenset({"aart_cli"}),
    "artifact.updated": frozenset({"aart_cli"}),
    "artifact.removed": frozenset({"aart_cli"}),
    "artifact.used": frozenset(TELEMETRY_SOURCES.values()),
}

#: `scheme://host[:port][/path]`, nothing else: no user, password, query or fragment.
_ENDPOINT = re.compile(
    r"(?P<scheme>https?)://(?P<host>\[[0-9A-Fa-f:.]+\]|[0-9A-Za-z.-]+)(?::(?P<port>[0-9]{1,5}))?"
    r"(?P<path>(?:/[0-9A-Za-z._~%!$&'()*+,;=:@-]*)*)",
)
_LOOPBACK = re.compile(r"localhost|127(?:\.[0-9]{1,3}){3}|\[::1\]", re.IGNORECASE)


def _invalid(message: str) -> Err:
    return Err((Diagnostic(TELEMETRY_ENDPOINT_INVALID, Severity.ERROR, message),))


def parse_telemetry_endpoint(raw: str) -> Result[str]:
    """A telemetry server's base address, without a trailing slash, or why it cannot be one.

    `https://` for any host; `http://` only for loopback, which is local development. An address
    that carries a user, a password, a query or a fragment is refused, so no credential can ride
    in it (D-503). The reason never repeats the address.
    """

    value = raw.strip()
    found = _ENDPOINT.fullmatch(value)
    if found is None:
        return _invalid(
            "a telemetry server is an address such as https://HOST[:PORT][/PATH], with no "
            "user, password, query or fragment"
        )
    port = found["port"]
    if port is not None and not 1 <= int(port) <= 65535:
        return _invalid("a telemetry server's port is 1 to 65535")
    scheme = found["scheme"]
    if scheme == "http" and _LOOPBACK.fullmatch(found["host"]) is None:
        return _invalid("http:// is accepted only for 127.0.0.1, ::1 or localhost; use https://")
    return Ok(value.rstrip("/"))


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """One event as the contract's version 1 carries it."""

    event_id: str
    occurred_at: str
    event_type: str
    source: str
    artifact_id: str
    artifact_type: str
    artifact_version: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.event_id, str)
            or _UUID.fullmatch(self.event_id) is None
            or not isinstance(self.occurred_at, str)
            or _MOMENT.fullmatch(self.occurred_at) is None
            or self.source not in _EVENT_SOURCES.get(self.event_type, ())
            or not isinstance(self.artifact_id, str)
            or _NAME.fullmatch(self.artifact_id) is None
            or not isinstance(self.artifact_type, str)
            or _KIND.fullmatch(self.artifact_type) is None
            or (
                self.artifact_version is not None
                and (
                    not isinstance(self.artifact_version, str)
                    or _VERSION.fullmatch(self.artifact_version) is None
                )
            )
        ):
            raise ValueError("a telemetry event does not follow the contract")

    def document(self) -> dict[str, str]:
        body = {
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "event_type": self.event_type,
            "source": self.source,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
        }
        if self.artifact_version is not None:
            body["artifact_version"] = self.artifact_version
        return body


def contract_moment(moment: datetime) -> str:
    """`moment` in UTC as the contract writes it."""

    if moment.tzinfo is None:
        raise ValueError("a telemetry moment needs a time zone")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _artifact(coordinate: str) -> tuple[str, str, str | None] | None:
    """`source/kind/name[@version]` as (kind, name, version), or `None` when it is not one."""

    body, _, version = coordinate.partition("@")
    parts = body.split("/")
    if len(parts) != 3 or not all(parts):
        return None
    return parts[1], parts[2], version or None


def _event(
    event_id: str,
    moment: str,
    event_type: str,
    source: str,
    kind: str,
    name: str,
    version: str | None,
) -> TelemetryEvent | None:
    try:
        return TelemetryEvent(event_id, moment, event_type, source, name, kind, version)
    except ValueError:
        return None


def lifecycle_event_type(intent: str) -> str | None:
    """The contract's event type for a finished action's intent; a repair is none."""

    return _LIFECYCLE_EVENTS.get(intent)


def lifecycle_event(
    event_id: str, moment: str, intent: str, coordinate: str
) -> TelemetryEvent | None:
    """An install, update or removal aart-cli carried out, or `None` when it is not reportable."""

    event_type = lifecycle_event_type(intent)
    artifact = _artifact(coordinate)
    if event_type is None or artifact is None:
        return None
    kind, name, version = artifact
    return _event(event_id, moment, event_type, "aart_cli", kind, name, version)


def use_event(
    event_id: str,
    moment: str,
    harness: str,
    kind: UsageKind,
    name: str,
    installed: tuple[InstalledName, ...],
) -> TelemetryEvent | None:
    """A recorded use as an event, only when it is an artifact aart-cli installed.

    A use the harness names that no installed artifact answers to is never sent: it may be the
    person's own tool, and its name is theirs (D-503). The artifact is named by its installation,
    never by the tool the harness called.
    """

    source = TELEMETRY_SOURCES.get(harness)
    resolved = None if source is None else resolve_installed(harness, kind, name, installed)
    if source is None or resolved is None:
        return None
    artifact = _artifact(resolved.artifact)
    if artifact is None:
        return None
    artifact_kind, artifact_name, _ = artifact
    return _event(
        event_id,
        moment,
        "artifact.used",
        source,
        artifact_kind,
        artifact_name,
        resolved.version,
    )


def batch_document(
    client_id: str, client_version: str, events: tuple[TelemetryEvent, ...]
) -> dict[str, object]:
    """The request body for `events`."""

    if _UUID.fullmatch(client_id) is None:
        raise ValueError("a telemetry client id is a lowercase UUID")
    if _VERSION.fullmatch(client_version) is None:
        raise ValueError("a telemetry client version does not follow the contract")
    if not 1 <= len(events) <= BATCH_SIZE:
        raise ValueError("a telemetry batch holds 1 to BATCH_SIZE events")
    return {
        "schema_version": 1,
        "client_id": client_id,
        "client_version": client_version,
        "events": [event.document() for event in events],
    }


class AnswerKind(str, Enum):
    STORED = "stored"
    REJECTED = "rejected"  # these events, named by the server, are invalid; send the rest
    SPLIT = "split"  # the request was refused as a whole; send fewer at a time
    UNAUTHORISED = "unauthorised"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Answer:
    kind: AnswerKind
    event_ids: tuple[str, ...] = ()


def classify_answer(status: int | None, body: object, sent: tuple[str, ...]) -> Answer:
    """What a server's answer to a request carrying `sent` means. `None` is no answer at all.

    Only ids that were sent are ever acknowledged or rejected: a server cannot mark anything
    else this machine holds.
    """

    if status == 200:
        acknowledged = body.get("acknowledged_event_ids") if isinstance(body, dict) else None
        if isinstance(acknowledged, list):
            named = set(item for item in acknowledged if isinstance(item, str))
            stored = tuple(item for item in sent if item in named)
            if stored:
                return Answer(AnswerKind.STORED, stored)
        return Answer(AnswerKind.UNAVAILABLE)
    if status == 422 and isinstance(body, dict) and isinstance(body.get("rejected_events"), list):
        refused = {
            item.get("event_id") for item in body["rejected_events"] if isinstance(item, dict)
        }
        rejected = tuple(item for item in sent if item in refused)
        if rejected:
            return Answer(AnswerKind.REJECTED, rejected)
    if status in (400, 413, 422):
        return Answer(AnswerKind.SPLIT)
    if status in (401, 403):
        return Answer(AnswerKind.UNAUTHORISED)
    return Answer(AnswerKind.UNAVAILABLE)


@dataclass(frozen=True, slots=True)
class SyncState:
    """When this machine last sent successfully, last tried, and may try next."""

    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    failures: int = 0
    paused: str | None = None

    def __post_init__(self) -> None:
        for moment in (self.last_success_at, self.last_attempt_at, self.next_retry_at):
            if moment is not None and (not isinstance(moment, datetime) or moment.tzinfo is None):
                raise ValueError("a synchronisation moment needs a time zone")
        if (
            not isinstance(self.failures, int)
            or isinstance(self.failures, bool)
            or self.failures < 0
        ):
            raise ValueError("failures are a count")


def sync_due(state: SyncState, now: datetime, *, pending: int, manual: bool = False) -> bool:
    """Whether a synchronisation may start now.

    Something must be waiting. A failure's backoff, and a refused authorisation's pause, hold
    even for a manual run. Otherwise a manual run is always due, and an automatic one when nothing
    was ever sent successfully or at least `SYNC_INTERVAL` passed since it last was. The number
    waiting never makes it due sooner.
    """

    if pending < 1:
        return False
    if state.next_retry_at is not None and now < state.next_retry_at:
        return False
    if manual or state.last_success_at is None:
        return True
    return now - state.last_success_at >= SYNC_INTERVAL


def after_success(state: SyncState, now: datetime) -> SyncState:
    return SyncState(last_success_at=now, last_attempt_at=now)


def after_failure(
    state: SyncState, now: datetime, answer: AnswerKind, *, jitter: float
) -> SyncState:
    """The state after a failed attempt; `jitter` in [0, 1) spreads machines that failed at once."""

    if not 0 <= jitter < 1:
        raise ValueError("jitter is a fraction in [0, 1)")
    failures = state.failures + 1
    if answer is AnswerKind.UNAUTHORISED:
        return replace(
            state,
            last_attempt_at=now,
            next_retry_at=now + AUTH_PAUSE,
            failures=failures,
            paused="unauthorised",
        )
    delay = BACKOFF[min(failures, len(BACKOFF)) - 1]
    return replace(
        state,
        last_attempt_at=now,
        next_retry_at=now + delay * (1 + jitter / 5),
        failures=failures,
        paused=None,
    )
