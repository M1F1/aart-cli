from __future__ import annotations

import unittest

from aart_cli.application.sources import SourceStatusRequest, source_status
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.sources.model import (
    CurrentSourceRequest,
    HealthStatus,
    SourceInstanceId,
    source_store_paths,
)


class SourceStatusApplicationTest(unittest.TestCase):
    def setUp(self) -> None:
        paths = source_store_paths("/managed", SourceInstanceId("local-" + "a" * 32))
        self.request = SourceStatusRequest(
            CurrentSourceRequest(paths, SourceAlias("local")),
            now_epoch_seconds=100,
            max_age_seconds=30,
        )

    def test_missing_source_has_explicit_status(self) -> None:
        health = source_status(self.request, lambda _request: Ok(None))

        self.assertIs(health.status, HealthStatus.MISSING)
        self.assertIsNone(health.current)

    def test_corrupt_durable_state_is_degraded_with_diagnostics(self) -> None:
        failure = Err(
            (
                Diagnostic(
                    DiagnosticCode("source-invalid"),
                    Severity.ERROR,
                    "current pointer is corrupt",
                ),
            )
        )

        health = source_status(self.request, lambda _request: failure)

        self.assertIs(health.status, HealthStatus.DEGRADED)
        self.assertEqual(health.diagnostics, failure.diagnostics)


if __name__ == "__main__":
    unittest.main()
