"""Transport-neutral telemetry boundary over the local Activity record.

The boundary is deliberately not wired to a transport.  Activity remains local unless a caller
injects an explicitly configured adapter; the default adapter records that delivery is disabled
and performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from aart_cli.domain.result import Ok, Result

from .consumer_views import ActivityRecord

__all__ = [
    "ActivityTelemetryPort",
    "DisabledActivityTelemetry",
    "TelemetryDelivery",
    "publish_activity",
]


@dataclass(frozen=True, slots=True)
class TelemetryDelivery:
    status: str
    accepted: int

    def __post_init__(self) -> None:
        if self.status not in {"disabled", "delivered"} or self.accepted < 0:
            raise ValueError("telemetry delivery is invalid")


class ActivityTelemetryPort(Protocol):
    """An injectable destination for already-recorded Activity entries."""

    def publish(self, records: tuple[ActivityRecord, ...]) -> Result[TelemetryDelivery]: ...


@dataclass(frozen=True, slots=True)
class DisabledActivityTelemetry:
    """The no-I/O default: telemetry is not an implicit opt-in."""

    def publish(self, records: tuple[ActivityRecord, ...]) -> Result[TelemetryDelivery]:
        if any(not isinstance(record, ActivityRecord) for record in records):
            raise ValueError("telemetry accepts Activity records only")
        return Ok(TelemetryDelivery("disabled", 0))


def publish_activity(
    records: tuple[ActivityRecord, ...],
    port: ActivityTelemetryPort,
) -> Result[TelemetryDelivery]:
    """Hand local Activity records to an explicitly selected telemetry adapter."""

    if not isinstance(records, tuple) or any(
        not isinstance(record, ActivityRecord) for record in records
    ):
        raise ValueError("telemetry accepts a tuple of Activity records")
    return port.publish(records)
