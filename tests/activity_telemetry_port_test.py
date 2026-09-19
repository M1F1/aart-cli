"""CP-25.07: future telemetry starts at Activity, without enabling transmission."""

from __future__ import annotations

import unittest

from aart_cli.application.activity_telemetry import (
    DisabledActivityTelemetry,
    TelemetryDelivery,
    publish_activity,
)
from aart_cli.application.consumer_views import ActivityRecord
from aart_cli.domain.result import Ok
from tests.consumer_activity_test import lifecycle_outcome


def _record() -> ActivityRecord:
    return ActivityRecord("2026-09-17T12:00:00Z", lifecycle_outcome())


class ActivityTelemetryPortTest(unittest.TestCase):
    def test_the_default_adapter_is_explicitly_disabled_and_has_no_callback(self) -> None:
        adapter = DisabledActivityTelemetry()

        result = publish_activity((_record(),), adapter)

        self.assertEqual(result, Ok(TelemetryDelivery("disabled", 0)))
        self.assertEqual(vars(adapter) if hasattr(adapter, "__dict__") else {}, {})

    def test_a_future_adapter_receives_the_exact_activity_records(self) -> None:
        received: list[tuple[ActivityRecord, ...]] = []

        class RecordingAdapter:
            def publish(self, records: tuple[ActivityRecord, ...]):
                received.append(records)
                return Ok(TelemetryDelivery("delivered", len(records)))

        records = (_record(),)
        result = publish_activity(records, RecordingAdapter())

        self.assertEqual(received, [records])
        self.assertEqual(result, Ok(TelemetryDelivery("delivered", 1)))

    def test_the_boundary_rejects_values_that_are_not_activity_records(self) -> None:
        with self.assertRaises(ValueError):
            publish_activity((object(),), DisabledActivityTelemetry())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
