"""Turning telemetry on: by a person, or by a build that names a server (§213, D-505).

Turning it on queues what Activity already holds, so a server learns about installs and uses from
before as well as after. Each record's events are drawn with the ids the live path gives them, so
a record queued twice is kept once.

A build that names a server turns telemetry on at the first start where nobody turned it on or
off; that is decided once, under the outbox's write lock, and never again for the person.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from aart_cli.application.consumer_views import receipt_detail_from_data
from aart_cli.application.telemetry_events import lifecycle_events
from aart_cli.domain.artifact_usage import ArtifactUse
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.telemetry import contract_moment

from .activity_store import ActivityDatabase
from .telemetry_store import EventsOf, TelemetryOutbox, TelemetrySetting
from .telemetry_sync import maybe_sync, new_installation_id

__all__ = ["announce_turned_on", "queue_history", "turn_on", "turn_on_by_default"]


def _state(home: str) -> str:
    return str(Path(home) / "state")


def _events_of(receipt: bytes) -> EventsOf | None:
    """What one recorded receipt amounts to, or `None` when it cannot be read."""

    try:
        parsed = receipt_detail_from_data(json.loads(receipt.decode("utf-8")))
    except (UnicodeDecodeError, ValueError, TypeError, KeyError):
        return None
    if isinstance(parsed, Err):
        return None
    detail = parsed.value
    return lambda ids: lifecycle_events(detail, ids)


def _moment(recorded: str) -> str | None:
    try:
        return contract_moment(datetime.fromisoformat(recorded))
    except ValueError:
        return None


def queue_history(home: str) -> Result[int]:
    """Queue everything Activity holds, when telemetry is on; how many events were new.

    A record that cannot be read is left out rather than stopping the rest.
    """

    database = ActivityDatabase(_state(home))
    actions = database.action_rows()
    if isinstance(actions, Err):
        return actions
    uses = database.use_rows()
    if isinstance(uses, Err):
        return uses
    readable_uses: list[tuple[str, str, ArtifactUse]] = []
    for record, recorded, use in uses.value:
        moment = _moment(recorded)
        if moment is not None:
            readable_uses.append((record, moment, use))
    readable_actions: list[tuple[str, EventsOf]] = []
    for record, receipt in actions.value:
        events_of = _events_of(receipt)
        if events_of is not None:
            readable_actions.append((record, events_of))
    return TelemetryOutbox(_state(home)).record(uses=readable_uses, actions=readable_actions)


def turn_on(
    home: str,
    endpoint: str,
    new_client_id: str,
    *,
    sync: Callable[[str], bool] = maybe_sync,
) -> Result[tuple[TelemetrySetting, int]]:
    """Turn telemetry on for `endpoint` and queue Activity's history; the setting and how many
    events the history added. A due sync is started without waiting for it."""

    enabled = TelemetryOutbox(_state(home)).enable(endpoint, new_client_id)
    if isinstance(enabled, Err):
        return enabled
    assert enabled.value is not None
    queued = queue_history(home)
    sync(home)
    return Ok((enabled.value, queued.value if isinstance(queued, Ok) else 0))


def turn_on_by_default(
    home: str,
    endpoint: str | None,
    *,
    sync: Callable[[str], bool] = maybe_sync,
) -> TelemetrySetting | None:
    """Turn telemetry on for the build's `endpoint` where nobody decided; the setting when this
    call turned it on, else `None`. Nothing here fails what started it."""

    if endpoint is None:
        return None
    try:
        outbox = TelemetryOutbox(_state(home))
        if outbox.exists():
            return None
        enabled = outbox.enable(endpoint, new_installation_id(), only_if_undecided=True)
        if not isinstance(enabled, Ok) or enabled.value is None:
            return None
        queue_history(home)
        sync(home)
        return enabled.value
    except Exception:  # noqa: BLE001 -- telemetry never fails what triggered it
        return None


def announce_turned_on(
    setting: TelemetrySetting, say: Callable[[str], None], *, unmanaged: bool
) -> None:
    """Say, once, that this build turned telemetry on, what it sends and how to turn it off.

    `unmanaged` is whether uses aart-cli did not install are sent too (D-508): then it says so,
    and where that alone is turned off.
    """

    others = (
        ", and each use of a skill or MCP it did not install, by the name the harness used"
        if unmanaged
        else ""
    )
    say(
        f"Telemetry is on: this aart-cli sends to {setting.endpoint} each install, update and "
        f"removal it completes and each use of an artifact it installed{others}, including what "
        "Activity already holds; never a project, path, argument, prompt, user or host name, or "
        "credential. `aart-cli consume telemetry disable` turns it off."
        + (
            " Settings > Telemetry, or `aart-cli consume telemetry unmanaged off`, stops "
            "sending uses of tools aart-cli did not install."
            if unmanaged
            else ""
        )
    )
