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
from collections.abc import Callable
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
    TelemetryEvent,
    after_failure,
    after_success,
    batch_document,
    classify_answer,
    sync_due,
    use_event,
)

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
) -> SyncReport:
    """Send what waits, under the lock, if it is due; what happened."""

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
        )
    finally:
        os.close(lock)


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
) -> SyncReport:
    setting = outbox.setting()
    if isinstance(setting, Err) or setting.value is None or not setting.value.enabled:
        return SyncReport(False, reason="telemetry is off")
    endpoint, client_id = setting.value.endpoint, setting.value.client_id
    state = outbox.sync_state()
    counts = outbox.counts()
    if isinstance(state, Err) or isinstance(counts, Err):
        return SyncReport(False, reason="the outbox cannot be read")
    current = state.value
    if force:
        current = replace(current, next_retry_at=None, paused=None)
    if not sync_due(current, now(), pending=counts.value.waiting, manual=manual):
        return SyncReport(False, reason="not due")

    installed = _installed(state_root)
    unmanaged = _sends_unmanaged(str(Path(state_root).parent))
    started = monotonic()
    size = BATCH_SIZE
    sent = rejected = skipped = requests = 0
    while requests < MAX_REQUESTS_PER_RUN and monotonic() - started < RUN_SECONDS:
        waiting = outbox.waiting(limit=size)
        if isinstance(waiting, Err) or not waiting.value:
            break
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
            if isinstance(outbox.settle(tuple(unattributed), "skipped", now()), Err):
                break
            skipped += len(unattributed)
        if not events:
            continue
        ids = tuple(event.event_id for event in events)
        body = json.dumps(batch_document(client_id, client_version, tuple(events))).encode()
        requests += 1
        status, answer_body = post(endpoint + BATCH_PATH, body, HTTP_TIMEOUT_SECONDS)
        answer = classify_answer(status, answer_body, ids)
        if answer.kind is AnswerKind.STORED:
            outbox.settle(answer.event_ids, "sent", now())
            sent += len(answer.event_ids)
            current = after_success(current, now())
            outbox.save_sync_state(current)
        elif answer.kind is AnswerKind.REJECTED:
            outbox.settle(answer.event_ids, "rejected", now())
            rejected += len(answer.event_ids)
        elif answer.kind is AnswerKind.SPLIT:
            if len(events) == 1:
                outbox.settle(ids, "rejected", now())
                rejected += 1
            else:
                size = max(1, len(events) // 2)
        else:
            current = after_failure(current, now(), answer.kind, jitter=jitter())
            outbox.save_sync_state(current)
            return SyncReport(True, sent, rejected, skipped, requests, answer.kind.value)
    return SyncReport(True, sent, rejected, skipped, requests)


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
        if not sync_due(state.value, now(), pending=counts.value.waiting):
            return False
        return (spawn or spawn_sync)(home)
    except Exception:  # noqa: BLE001 -- telemetry never fails what triggered it
        return False


def main(arguments: list[str]) -> int:
    try:
        if len(arguments) == 1 and arguments[0].startswith("/"):
            synchronise(arguments[0])
    except Exception:  # noqa: BLE001 -- nobody reads this process's outcome
        pass
    return 0
