from __future__ import annotations

import unittest

from aart_cli.application.store import object_status
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import ObjectDigest
from aart_cli.domain.result import Err, Ok
from aart_cli.store.model import (
    ObjectReadRequest,
    ObjectStatusKind,
    object_store_paths,
)


class StoreStatusApplicationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.request = ObjectReadRequest(
            object_store_paths("/managed"), ObjectDigest("sha256", "a" * 64)
        )

    def test_missing_and_degraded_statuses_are_explicit(self) -> None:
        missing = object_status(self.request, lambda _request: Ok(None))
        failure = Err(
            (Diagnostic(DiagnosticCode("digest-mismatch"), Severity.ERROR, "object is corrupt"),)
        )
        degraded = object_status(self.request, lambda _request: failure)

        self.assertIs(missing.kind, ObjectStatusKind.MISSING)
        self.assertIs(degraded.kind, ObjectStatusKind.DEGRADED)
        self.assertEqual(degraded.diagnostics, failure.diagnostics)


if __name__ == "__main__":
    unittest.main()
