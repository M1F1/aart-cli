"""Sending the outbox to the telemetry server (§213).

`maybe_sync` is what recording an event calls: it reads the outbox, and when a synchronisation
is due it starts `main` as its own short-lived process and returns at once, so neither a hook
nor an action waits for the network. That process -- or `consume telemetry sync` -- calls
`synchronise`, which takes a non-blocking lock, checks again, and sends in batches. No transaction
is open while a request is in flight, and an event is marked sent only by the id a server
acknowledged; a process killed half way leaves its events waiting.

Nothing here raises to its caller. Whatever the outbox, the lock, the network or the server does,
what triggered it carries on.
"""

from __future__ import annotations

import fcntl
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from aart_cli.domain.artifact_usage import InstalledName
from aart_cli.domain.result import Err, Ok
from aart_cli.domain.telemetry import (
    BATCH_PATH,
    BATCH_SIZE,
    HTTP_TIMEOUT_SECONDS,
    MAX_REQUESTS_PER_RUN,
    RUN_SECONDS,
    AnswerKind,
    SyncState,
    TelemetryEvent,
    after_failure,
    after_success,
    automated,
    batch_document,
    classify_answer,
    failure_event,
    sync_due,
    use_event,
)

from .failure_journal import FailureJournal
from .telemetry_store import TelemetryOutbox

__all__ = [
    "Post",
    "SyncReport",
    "http_post",
    "maybe_sync",
    "new_installation_id",
    "spawn_sync",
    "synchronise",
]

#: `(url, body, timeout)` -> `(status, parsed JSON body)`; `(None, None)` when nothing answered.
Post = Callable[[str, bytes, float], tuple[int | None, object]]

_MAX_ANSWER = 1024 * 1024

#: `-I` keeps the current directory -- a project a harness works in -- off the import path, so the
#: package is put on it from where this file is, as the first argument.
_BOOTSTRAP = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from aart_cli.io.telemetry_sync import main; sys.exit(main(sys.argv[2:]))"
)


def new_installation_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _loopback(url: str) -> bool:
    authority = url.split("://", 1)[-1].split("/", 1)[0]
    host = authority.rsplit(":", 1)[0] if not authority.endswith("]") else authority
    return host.lower() in {"127.0.0.1", "localhost", "[::1]"} or host.startswith("127.")


def http_post(url: str, body: bytes, timeout: float) -> tuple[int | None, object]:
    """POST `body` as JSON; the status and the parsed answer, or `(None, None)`."""

    from aart_cli.runtime_contract import EXECUTABLE_VERSION

    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"aart-cli/{EXECUTABLE_VERSION}",
        },
    )
    # A loopback server is never reached through a proxy the environment names.
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if _loopback(url)
        else urllib.request.build_opener()
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            status, raw = response.status, response.read(_MAX_ANSWER)
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read(_MAX_ANSWER)
    except (urllib.error.URLError, OSError, ValueError):
        return None, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None


def _installed(state_root: str) -> tuple[InstalledName, ...]:
    """What aart-cli installed here, as each harness names it; nothing when it cannot be read."""

    from aart_cli.domain.artifact_usage import installed_names
    from aart_cli.io.receipt_store import LocalReceiptStore

    records = LocalReceiptStore(state_root).installations()
    return () if isinstance(records, Err) else installed_names(records.value)


def _sends_unmanaged(home: str) -> bool:
    """Whether uses aart-cli did not install are sent now: the person's choice, else the build's
    (D-508). Settings that cannot be read send none of them."""

    from aart_cli.io.consumer_settings import read_consumer_settings

    try:
        settings = read_consumer_settings(home)
    except Exception:  # noqa: BLE001 -- telemetry never fails what triggered it
        return False
    return isinstance(settings, Ok) and settings.value.sends_unmanaged_uses


def _sends_failures(home: str) -> bool:
    """Whether failures aart-cli met are sent now: the person's choice, else the build's
    (D-509). Settings that cannot be read send none of them."""

    from aart_cli.io.consumer_settings import read_consumer_settings

    try:
        settings = read_consumer_settings(home)
    except Exception:  # noqa: BLE001 -- telemetry never fails what triggered it
        return False
    return isinstance(settings, Ok) and settings.value.sends_failures


@dataclass(frozen=True, slots=True)
class SyncReport:
    started: bool
    sent: int = 0
    rejected: int = 0
    skipped: int = 0
    requests: int = 0
    reason: str = ""


def synchronise(
    home: str,
    *,
    manual: bool = False,
    force: bool = False,
    post: Post = http_post,
    now: Callable[[], datetime] = _now,
    jitter: Callable[[], float] = random.random,
    monotonic: Callable[[], float] = time.monotonic,
    environ: Mapping[str, str] | None = None,
) -> SyncReport:
    """Send what waits, under the lock, if it is due; what happened.

    Each request says whether this sender runs as automation, as `environ` (by default this
    process's environment, which the detached sender inherits) says now (D-511).
    """

    from aart_cli.runtime_contract import EXECUTABLE_VERSION

    state_root = str(Path(home) / "state")
    outbox = TelemetryOutbox(state_root)
    if not outbox.exists():
        return SyncReport(False, reason="telemetry is off")
    try:
        lock = os.open(outbox.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return SyncReport(False, reason="the lock cannot be opened")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return SyncReport(False, reason="another synchronisation is running")
        return _under_lock(
            outbox,
            state_root,
            manual=manual or force,
            force=force,
            post=post,
            now=now,
            jitter=jitter,
            monotonic=monotonic,
            client_version=str(EXECUTABLE_VERSION),
            automated=automated(os.environ if environ is None else environ),
        )
    finally:
        os.close(lock)


class _Run:
    """One synchronisation's budget, counts and state, across the outbox and the journal."""

    def __init__(
        self,
        outbox: TelemetryOutbox,
        state: SyncState,
        *,
        endpoint: str,
        client_id: str,
        post: Post,
        now: Callable[[], datetime],
        jitter: Callable[[], float],
        monotonic: Callable[[], float],
        automated: bool,
    ) -> None:
        self.outbox, self.current = outbox, state
        self.automated = automated
        self.endpoint, self.client_id = endpoint, client_id
        self.post, self.now, self.jitter, self.monotonic = post, now, jitter, monotonic
        self.started = monotonic()
        self.size = BATCH_SIZE
        self.sent = self.rejected = self.skipped = self.requests = 0
        self.stopped = ""

    def budget(self) -> bool:
        return (
            not self.stopped
            and self.requests < MAX_REQUESTS_PER_RUN
            and self.monotonic() - self.started < RUN_SECONDS
        )

    def send(
        self,
        events: tuple[TelemetryEvent, ...],
        client_version: str,
        settle: Callable[[tuple[str, ...], str, datetime], object],
    ) -> None:
        """Post one batch and settle by what the server answered; a failure stops the run."""

        ids = tuple(event.event_id for event in events)
        try:
            document = batch_document(
                self.client_id, client_version, events, automated=self.automated
            )
        except ValueError:
            settle(ids, "rejected", self.now())
            self.rejected += len(ids)
            return
        self.requests += 1
        status, answer_body = self.post(
            self.endpoint + BATCH_PATH, json.dumps(document).encode(), HTTP_TIMEOUT_SECONDS
        )
        answer = classify_answer(status, answer_body, ids)
        if answer.kind is AnswerKind.STORED:
            settle(answer.event_ids, "sent", self.now())
            self.sent += len(answer.event_ids)
            self.current = after_success(self.current, self.now())
            self.outbox.save_sync_state(self.current)
        elif answer.kind is AnswerKind.REJECTED:
            settle(answer.event_ids, "rejected", self.now())
            self.rejected += len(answer.event_ids)
        elif answer.kind is AnswerKind.SPLIT:
            if len(events) == 1:
                settle(ids, "rejected", self.now())
                self.rejected += 1
            else:
                self.size = max(1, len(events) // 2)
        else:
            self.current = after_failure(
                self.current, self.now(), answer.kind, jitter=self.jitter()
            )
            self.outbox.save_sync_state(self.current)
            self.stopped = answer.kind.value

    def report(self) -> SyncReport:
        return SyncReport(True, self.sent, self.rejected, self.skipped, self.requests, self.stopped)


def _under_lock(
    outbox: TelemetryOutbox,
    state_root: str,
    *,
    manual: bool,
    force: bool,
    post: Post,
    now: Callable[[], datetime],
    jitter: Callable[[], float],
    monotonic: Callable[[], float],
    client_version: str,
    automated: bool,
) -> SyncReport:
    setting = outbox.setting()
    if isinstance(setting, Err) or setting.value is None or not setting.value.enabled:
        return SyncReport(False, reason="telemetry is off")
    journal = FailureJournal(state_root)
    state = outbox.sync_state()
    counts = outbox.counts()
    failures = journal.counts()
    if isinstance(state, Err) or isinstance(counts, Err):
        return SyncReport(False, reason="the outbox cannot be read")
    current = state.value
    if force:
        current = replace(current, next_retry_at=None, paused=None)
    pending = counts.value.waiting + (0 if isinstance(failures, Err) else failures.value.waiting)
    if not sync_due(current, now(), pending=pending, manual=manual):
        return SyncReport(False, reason="not due")

    home = str(Path(state_root).parent)
    run = _Run(
        outbox,
        current,
        endpoint=setting.value.endpoint,
        client_id=setting.value.client_id,
        post=post,
        now=now,
        jitter=jitter,
        monotonic=monotonic,
        automated=automated,
    )
    _send_outbox(run, state_root, client_version)
    if not run.stopped:
        _send_journal(run, journal, sends=_sends_failures(home))
    return run.report()


def _send_outbox(run: _Run, state_root: str, client_version: str) -> None:
    installed = _installed(state_root)
    unmanaged = _sends_unmanaged(str(Path(state_root).parent))
    while run.budget():
        waiting = run.outbox.waiting(limit=run.size)
        if isinstance(waiting, Err) or not waiting.value:
            return
        events: list[TelemetryEvent] = []
        unattributed: list[str] = []
        for item in waiting.value:
            if item.event is not None:
                events.append(item.event)
                continue
            assert item.harness is not None and item.kind is not None and item.name is not None
            event = use_event(
                item.event_id,
                item.occurred_at,
                item.harness,
                item.kind,
                item.name,
                installed,
                unmanaged=unmanaged,
            )
            if event is None:
                unattributed.append(item.event_id)
            else:
                events.append(event)
        if unattributed:
            if isinstance(run.outbox.settle(tuple(unattributed), "skipped", run.now()), Err):
                return
            run.skipped += len(unattributed)
        if events:
            run.send(tuple(events), client_version, run.outbox.settle)


def _send_journal(run: _Run, journal: FailureJournal, *, sends: bool) -> None:
    """Send the failures that wait, each batch from one aart-cli version and with it as the
    batch's `client_version` (§215); not sent, they are skipped (INV-336)."""

    if not sends:
        skipped = journal.skip_waiting(run.now())
        if isinstance(skipped, Ok):
            run.skipped += skipped.value
        return
    while run.budget():
        waiting = journal.waiting(limit=run.size)
        if isinstance(waiting, Err) or not waiting.value:
            return
        version = waiting.value[0].version
        same = [item for item in waiting.value if item.version == version]
        unreadable = tuple(item.event_id for item in same if item.failure is None)
        if unreadable:
            if isinstance(journal.settle(unreadable, "skipped", run.now()), Err):
                return
            run.skipped += len(unreadable)
        events = tuple(
            failure_event(item.event_id, item.occurred_at, item.failure)
            for item in same
            if item.failure is not None
        )
        if events:
            run.send(events, version, journal.settle)


def spawn_sync(home: str) -> bool:
    """Start `synchronise` for `home` as a detached process; whether it started."""

    try:
        subprocess.Popen(  # noqa: S603 -- this interpreter, this package, one argument
            [
                sys.executable,
                "-I",
                "-c",
                _BOOTSTRAP,
                str(Path(__file__).resolve().parents[2]),
                home,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def maybe_sync(
    home: str,
    *,
    now: Callable[[], datetime] = _now,
    spawn: Callable[[str], bool] | None = None,
) -> bool:
    """Start a synchronisation when one is due, without waiting for it; whether one started.

    `spawn` defaults to `spawn_sync` as it is when called, so replacing it replaces it here too.
    """

    try:
        outbox = TelemetryOutbox(str(Path(home) / "state"))
        if not outbox.exists():
            return False
        setting = outbox.setting()
        if isinstance(setting, Err) or setting.value is None or not setting.value.enabled:
            return False
        state = outbox.sync_state()
        counts = outbox.counts()
        if isinstance(state, Err) or isinstance(counts, Err):
            return False
        failures = FailureJournal(str(Path(home) / "state")).counts()
        pending = counts.value.waiting + (
            0 if isinstance(failures, Err) else failures.value.waiting
        )
        if not sync_due(state.value, now(), pending=pending):
            return False
        return (spawn or spawn_sync)(home)
    except Exception:  # noqa: BLE001 -- telemetry never fails what triggered it
        return False


def main(arguments: list[str]) -> int:
    try:
        if len(arguments) == 1 and arguments[0].startswith("/"):
            synchronise(arguments[0])
    except Exception as error:  # noqa: BLE001 -- nobody reads this process's outcome
        # Journaled for the next synchronisation, never starting one (§215).
        try:
            from aart_cli.domain.failures import FailureKind
            from aart_cli.io.failure_journal import record_failure

            record_failure(
                arguments[0], FailureKind.CRASH, "telemetry-sync", error=error, sync=False
            )
        except Exception:  # noqa: BLE001 -- nor its journal
            pass
    return 0
