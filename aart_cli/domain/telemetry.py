"""What is sent to a telemetry server, where, and when (§213, docs/telemetry-api-v1.md).

Pure. The outbox, the clock, the lock and HTTP are the caller's; this module decides. Every rule a
version-1 server applies to an event is applied here first, so an event that leaves this machine
is one the contract allows, and nothing else -- no project, path, argument or credential -- can be
put into one.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, timedelta, timezone
from enum import Enum

from .artifact_usage import InstalledName, UsageKind, resolve_installed
from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .failures import Failure
from .result import Err, Ok, Result

__all__ = [
    "AUTH_PAUSE",
    "AUTOMATED_VARIABLE",
    "BACKOFF",
    "BATCH_PATH",
    "BATCH_SIZE",
    "CONTEXT_FOR",
    "CONTEXT_REVISION",
    "CONTRACT_PATH",
    "FAILED",
    "HTTP_TIMEOUT_SECONDS",
    "MAX_REQUESTS_PER_RUN",
    "RUN_SECONDS",
    "SYNC_INTERVAL",
    "TELEMETRY_ENDPOINT_INVALID",
    "TELEMETRY_ERRORS_INVALID",
    "TELEMETRY_SOURCES",
    "TELEMETRY_UNMANAGED_INVALID",
    "UNMANAGED_USED",
    "Answer",
    "AnswerKind",
    "Environment",
    "EventContext",
    "SyncState",
    "TelemetryEvent",
    "after_failure",
    "after_success",
    "automated",
    "batch_document",
    "classify_answer",
    "contract_moment",
    "environment_of",
    "failure_event",
    "history_event_id",
    "lifecycle_event",
    "lifecycle_event_type",
    "parse_failures_sent",
    "parse_telemetry_endpoint",
    "parse_unmanaged_uses",
    "read_contract",
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
#: Where a server says which revision of the contract it holds (revision 6).
CONTRACT_PATH = "/api/v1/contract"
#: The revision that added where and how an event happened, and `environment` (D-518).
CONTEXT_REVISION = 7
#: The first revision that says itself: a server naming an earlier one is not believed.
_SAYS_ITS_REVISION = 6
#: Says whether aart-cli runs as automation, `on` or `off`, overruling `CI` (D-511).
AUTOMATED_VARIABLE = "AART_CLI_AUTOMATED"
TELEMETRY_ENDPOINT_INVALID = DiagnosticCode("telemetry-endpoint-invalid")
TELEMETRY_UNMANAGED_INVALID = DiagnosticCode("telemetry-unmanaged-invalid")
TELEMETRY_ERRORS_INVALID = DiagnosticCode("telemetry-errors-invalid")

#: A use of a skill or MCP no artifact aart-cli installed answers to, by the name the harness used
#: (D-508).
UNMANAGED_USED = "unmanaged.used"
#: A failure aart-cli met, with the `failure` object only it carries (§215, D-509).
FAILED = "aart_cli.failed"

#: The contract's `source` for a use recorded by each harness's hook.
TELEMETRY_SOURCES: dict[str, str] = {"claude": "claude_hook", "opencode": "opencode_plugin"}
#: The harness each use's source is, so a use that names its harness names that one.
_HARNESS_OF = {source: harness for harness, source in TELEMETRY_SOURCES.items()}

_LIFECYCLE_EVENTS = {
    "install": "artifact.installed",
    "update": "artifact.updated",
    "downgrade": "artifact.updated",
    "uninstall": "artifact.removed",
}

#: Names every event id drawn from a record; an installation's history key keeps them its own.
_HISTORY = uuid.UUID("5d1c0c8e-3f4a-4b7e-9a51-6d2f0e7b8c34")

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_MOMENT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z")
_NAME = re.compile(r"[0-9A-Za-z._@:+-]{1,200}")
_KIND = re.compile(r"[a-z0-9-]{1,64}")
_VERSION = re.compile(r"[0-9A-Za-z.+-]{1,64}")
_SLUG = re.compile(r"(?=.{1,64}\Z)[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_ARCH = re.compile(r"[a-z0-9_]{1,16}")
_PYTHON = re.compile(r"[0-9A-Za-z.+-]{1,32}")
MAX_DURATION_MS = 86_400_000
MAX_INPUTS = 1000
_EVENT_SOURCES = {
    "artifact.installed": frozenset({"aart_cli"}),
    "artifact.updated": frozenset({"aart_cli"}),
    "artifact.removed": frozenset({"aart_cli"}),
    "artifact.used": frozenset(TELEMETRY_SOURCES.values()),
    UNMANAGED_USED: frozenset(TELEMETRY_SOURCES.values()),
    FAILED: frozenset({"aart_cli"}),
}

#: What a release variable that switches something telemetry sends says; unset sends (D-508).
_SENDS = {"": True, "on": True, "true": True, "off": False, "false": False}

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


def parse_unmanaged_uses(raw: str) -> Result[bool]:
    """`AART_CLI_TELEMETRY_UNMANAGED_USES`: whether a build sends uses aart-cli did not install.

    Unset or empty sends them, because a release variable cannot be told unset from empty and
    the owner chose sending as the default (D-508); `on`/`true` and `off`/`false` say so in any
    case. Anything else is refused rather than guessed.
    """

    return _switch(
        raw,
        TELEMETRY_UNMANAGED_INVALID,
        "whether uses aart-cli did not install are sent is on, true, off or false",
    )


def parse_failures_sent(raw: str) -> Result[bool]:
    """`AART_CLI_TELEMETRY_ERRORS`: whether a build sends the failures aart-cli meets (D-509).

    Read as `parse_unmanaged_uses` reads its variable: unset or empty sends them.
    """

    return _switch(
        raw, TELEMETRY_ERRORS_INVALID, "whether failures are sent is on, true, off or false"
    )


def _switch(raw: str, code: DiagnosticCode, message: str) -> Result[bool]:
    value = raw.strip().lower()
    if value not in _SENDS:
        return Err((Diagnostic(code, Severity.ERROR, message),))
    return Ok(_SENDS[value])


_LIFECYCLE = frozenset({"artifact.installed", "artifact.updated", "artifact.removed"})
_PLACED = frozenset({"artifact.installed", "artifact.updated"})
_USES = frozenset({"artifact.used", UNMANAGED_USED})

#: Which event types each field of an event's context may be given in (revision 7).
CONTEXT_FOR: Mapping[str, frozenset[str]] = {
    "harness": _LIFECYCLE | _USES,
    "scope": _LIFECYCLE | {"artifact.used"},
    "registry": _LIFECYCLE | {"artifact.used"},
    "interface": _LIFECYCLE,
    "previous_version": frozenset({"artifact.updated"}),
    "via": _LIFECYCLE,
    "collection": _LIFECYCLE,
    "collection_version": _LIFECYCLE,
    "package_digest": _PLACED,
    "duration_ms": _LIFECYCLE,
    "configuration_inputs": _PLACED,
    "credential_inputs": _PLACED,
    "tool": _USES,
    "session": _USES,
}

#: Each field's shape, as the contract writes it.
_SHAPES: Mapping[str, Callable[[object], bool]] = {
    "harness": lambda value: _matches(_SLUG, value),
    "scope": lambda value: value in ("user", "project"),
    "registry": lambda value: _matches(_SLUG, value),
    "interface": lambda value: value in ("tui", "cli"),
    "previous_version": lambda value: _matches(_VERSION, value),
    "via": lambda value: value in ("direct", "collection", "plugin"),
    "collection": lambda value: _matches(_NAME, value),
    "collection_version": lambda value: _matches(_VERSION, value),
    "package_digest": lambda value: _matches(_DIGEST, value),
    "duration_ms": lambda value: _count(value, MAX_DURATION_MS),
    "configuration_inputs": lambda value: _count(value, MAX_INPUTS),
    "credential_inputs": lambda value: _count(value, MAX_INPUTS),
    "tool": lambda value: _matches(_NAME, value),
    "session": lambda value: _matches(_UUID, value),
}


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _count(value: object, most: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= most


@dataclass(frozen=True, slots=True)
class EventContext:
    """Where and how an event happened (revision 7): every field optional, each held by the
    event types `CONTEXT_FOR` names. Never a project, a path, a Registry address, a user or host
    name, or a value anyone typed -- only what each field's shape allows."""

    harness: str | None = None
    scope: str | None = None
    registry: str | None = None
    interface: str | None = None
    previous_version: str | None = None
    via: str | None = None
    collection: str | None = None
    collection_version: str | None = None
    package_digest: str | None = None
    duration_ms: int | None = None
    configuration_inputs: int | None = None
    credential_inputs: int | None = None
    tool: str | None = None
    session: str | None = None

    def __post_init__(self) -> None:
        for name, value in self.document().items():
            if not _SHAPES[name](value):
                raise ValueError(f"an event's {name} does not follow the contract")

    def document(self) -> dict[str, object]:
        """The fields that hold something, by the contract's names."""

        return {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if getattr(self, item.name) is not None
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> EventContext:
        """The context `document` says; `TypeError` for a field the contract does not have."""

        return cls(**document)  # type: ignore[arg-type]

    @classmethod
    def fitting(cls, **said: object) -> EventContext:
        """The context of every field in `said` that holds something of its shape; the rest is
        left out, so a value that cannot be said never costs the event."""

        return cls(
            **{  # type: ignore[arg-type]
                name: value
                for name, value in said.items()
                if value is not None and _SHAPES[name](value)
            }
        )

    def problem(self, event_type: str, source: str, artifact_type: str) -> str | None:
        """Why this context cannot be an event's of that type, source and kind; `None` when it
        can."""

        given = self.document()
        if any(event_type not in CONTEXT_FOR[name] for name in given):
            return "this event_type does not hold that field"
        if ("collection" in given or "collection_version" in given) and (
            self.via != "collection" or self.collection is None
        ):
            return "a collection is named exactly when via is collection"
        if self.tool is not None and artifact_type != "mcp":
            return "a tool is an mcp's"
        harness = _HARNESS_OF.get(source)
        if harness is not None and self.harness not in (None, harness):
            return "a use's harness is its source's"
        return None


@dataclass(frozen=True, slots=True)
class Environment:
    """What a request was sent from (revision 7): no host, user or path."""

    os: str
    arch: str
    python: str

    def __post_init__(self) -> None:
        if (
            self.os not in ("darwin", "linux", "windows", "other")
            or not _matches(_ARCH, self.arch)
            or not _matches(_PYTHON, self.python)
        ):
            raise ValueError("an environment is the contract's os, arch and python")

    def document(self) -> dict[str, str]:
        return {"os": self.os, "arch": self.arch, "python": self.python}


def environment_of(system: str, machine: str, python: str) -> Environment | None:
    """`platform.system()`, `platform.machine()` and `platform.python_version()` in the
    contract's words, or `None` when one of them cannot be said in them."""

    os_name = system.strip().lower()
    try:
        return Environment(
            os_name if os_name in ("darwin", "linux", "windows") else "other",
            machine.strip().lower(),
            python.strip(),
        )
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """One event as the contract's version 1 carries it. `failure` is present in a failure's
    event and in no other, and names its kind and place as `artifact_type` and `artifact_id`."""

    event_id: str
    occurred_at: str
    event_type: str
    source: str
    artifact_id: str
    artifact_type: str
    artifact_version: str | None = None
    failure: Failure | None = None
    context: EventContext = field(default_factory=EventContext)

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
                    self.event_type in (UNMANAGED_USED, FAILED)
                    or not isinstance(self.artifact_version, str)
                    or _VERSION.fullmatch(self.artifact_version) is None
                )
            )
            or (self.failure is not None) != (self.event_type == FAILED)
            or (
                self.failure is not None
                and (
                    not isinstance(self.failure, Failure)
                    or self.failure.kind.value != self.artifact_type
                    or self.failure.place != self.artifact_id
                )
            )
        ):
            raise ValueError("a telemetry event does not follow the contract")
        if not isinstance(self.context, EventContext):
            raise ValueError("a telemetry event's context is an EventContext")
        problem = self.context.problem(self.event_type, self.source, self.artifact_type)
        if problem is not None:
            raise ValueError(f"a telemetry event's context does not follow the contract: {problem}")

    def document(self, *, revision: int | None = None) -> dict[str, object]:
        """The event as `revision` of the contract carries it: where and how it happened only
        from `CONTEXT_REVISION` on."""

        body: dict[str, object] = {
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "event_type": self.event_type,
            "source": self.source,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
        }
        if self.artifact_version is not None:
            body["artifact_version"] = self.artifact_version
        if self.failure is not None:
            body["failure"] = self.failure.document()
        if revision is not None and revision >= CONTEXT_REVISION:
            body |= self.context.document()
        return body


def contract_moment(moment: datetime) -> str:
    """`moment` in UTC as the contract writes it."""

    if moment.tzinfo is None:
        raise ValueError("a telemetry moment needs a time zone")
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def history_event_id(key: str, record: str, index: int = 0) -> str:
    """The id of the `index`-th event Activity's `record` amounts to, under the history `key`.

    The same record always has the same id, so a record queued as it happened and again from the
    history when telemetry is turned on is kept once, and a server that already stored it stores
    it once (D-505).
    """

    if not isinstance(key, str) or not key or not isinstance(record, str) or not record:
        raise ValueError("an event id from the history needs a key and a record")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise ValueError("an event's place in its record is a whole number")
    return str(uuid.uuid5(_HISTORY, json.dumps([key, record, index])))


def _artifact(coordinate: str) -> tuple[str, str, str | None] | None:
    """`source/kind/name[@version]` as (kind, name, version), or `None` when it is not one."""

    body, _, version = coordinate.partition("@")
    parts = body.split("/")
    if len(parts) != 3 or not all(parts):
        return None
    return parts[1], parts[2], version or None


def _registry(coordinate: str) -> str:
    """The Registry alias `source/kind/name[@version]` comes from."""

    return coordinate.partition("/")[0]


def _event(
    event_id: str,
    moment: str,
    event_type: str,
    source: str,
    kind: str,
    name: str,
    version: str | None,
    context: EventContext | None = None,
) -> TelemetryEvent | None:
    try:
        return TelemetryEvent(
            event_id,
            moment,
            event_type,
            source,
            name,
            kind,
            version,
            context=context or EventContext(),
        )
    except ValueError:
        return None


def lifecycle_event_type(intent: str) -> str | None:
    """The contract's event type for a finished action's intent; a repair is none."""

    return _LIFECYCLE_EVENTS.get(intent)


def lifecycle_event(
    event_id: str,
    moment: str,
    intent: str,
    coordinate: str,
    *,
    member: str | None = None,
    harness: str | None = None,
    scope: str | None = None,
) -> TelemetryEvent | None:
    """An install, update or removal aart-cli carried out, or `None` when it is not reportable.

    With `member`, of that skill of the plugin `coordinate` names: a skill named
    `<plugin>:<member>` at the plugin's version, as its uses are (§214). It says the Registry alias
    it came from, and the harness and scope it was for when they are known; what cannot be said in
    the contract's words is left out (D-518).
    """

    event_type = lifecycle_event_type(intent)
    artifact = _artifact(coordinate)
    if event_type is None or artifact is None:
        return None
    kind, name, version = artifact
    if member is not None:
        kind, name = "skill", f"{name}:{member}"
    context = EventContext.fitting(harness=harness, scope=scope, registry=_registry(coordinate))
    return _event(event_id, moment, event_type, "aart_cli", kind, name, version, context)


def use_event(
    event_id: str,
    moment: str,
    harness: str,
    kind: UsageKind,
    name: str,
    installed: tuple[InstalledName, ...],
    *,
    unmanaged: bool = False,
) -> TelemetryEvent | None:
    """A recorded use as an event: the artifact aart-cli installed, or, when `unmanaged`, the name.

    An installed artifact is named by its installation, never by the tool the harness called. A
    use no installed artifact answers to is sent only when `unmanaged` -- the person's choice, or
    without one the build's (D-508) -- as `unmanaged.used` with the name the harness used and no
    version; a name the contract cannot carry is not sent.
    """

    source = TELEMETRY_SOURCES.get(harness)
    if source is None:
        return None
    resolved = resolve_installed(harness, kind, name, installed)
    if resolved is None:
        if not unmanaged:
            return None
        return _event(event_id, moment, UNMANAGED_USED, source, kind.value, name, None)
    artifact = _artifact(resolved.artifact)
    if artifact is None:
        return None
    artifact_kind, artifact_name, _ = artifact
    # opencode names an MCP's tool `<server>_<tool>`; Claude Code's hook keeps the server alone,
    # which is the name it was resolved by.
    tool = (
        name[len(resolved.name) + 1 :] if kind is UsageKind.MCP and name != resolved.name else None
    )
    context = EventContext.fitting(registry=_registry(resolved.artifact), tool=tool)
    if resolved.member is not None:
        # A skill a plugin carries: a skill, named after its plugin as `<plugin>:<member>`, which
        # version 1's `artifact_id` allows, so neither the contract nor the server changes (§214).
        artifact_kind, artifact_name = "skill", f"{artifact_name}:{resolved.member}"
    return _event(
        event_id,
        moment,
        "artifact.used",
        source,
        artifact_kind,
        artifact_name,
        resolved.version,
        context,
    )


def failure_event(event_id: str, moment: str, failure: Failure) -> TelemetryEvent:
    """A failure as the event that sends it: its kind and place, no version (§215)."""

    return TelemetryEvent(
        event_id, moment, FAILED, "aart_cli", failure.place, failure.kind.value, None, failure
    )


def automated(environment: Mapping[str, str]) -> bool:
    """Whether aart-cli runs as automation -- a CI job, for one -- rather than for a person.

    `AART_CLI_AUTOMATED` says so when it is `on`/`true` or `off`/`false`; otherwise `CI`, which CI
    services set, says so when it holds anything but nothing, `false` or `0` (D-511).
    """

    setting = environment.get(AUTOMATED_VARIABLE, "").strip().lower()
    if setting in ("on", "true"):
        return True
    if setting in ("off", "false"):
        return False
    return environment.get("CI", "").strip().lower() not in ("", "false", "0")


def batch_document(
    client_id: str,
    client_version: str,
    events: tuple[TelemetryEvent, ...],
    *,
    automated: bool = False,
    revision: int | None = None,
    environment: Environment | None = None,
) -> dict[str, object]:
    """The request body for `events` as `revision` of the contract carries it; `None` is a server
    that named none.

    It says `automated` only when it is, so a person's request is the one an older server reads
    (D-511). Where and how each event happened, and `environment`, only go to a server that holds
    `CONTEXT_REVISION` (D-518).
    """

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
        **({"automated": True} if automated else {}),
        **(
            {"environment": environment.document()}
            if environment is not None and revision is not None and revision >= CONTEXT_REVISION
            else {}
        ),
        "events": [event.document(revision=revision) for event in events],
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


def read_contract(status: int | None, body: object) -> int | None | AnswerKind:
    """What a server's answer to `GET CONTRACT_PATH` means: the revision it holds; `None` when it
    names none, as a server older than revision 6 does; or, as for a batch, a refused
    authorisation or no answer, which ends the synchronisation."""

    if status in (401, 403):
        return AnswerKind.UNAUTHORISED
    if status is None or status == 429 or status >= 500:
        return AnswerKind.UNAVAILABLE
    if status != 200 or not isinstance(body, dict) or body.get("schema_version") != 1:
        return None
    revision = body.get("revision")
    if not isinstance(revision, int):
        return None
    return revision if revision >= _SAYS_ITS_REVISION else None


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
