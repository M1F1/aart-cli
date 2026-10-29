"""CP-50: `aart-cli consume telemetry status|enable|disable|sync` (§213, INV-322, INV-323, INV-327)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from aart_cli import _default_telemetry, cli
from tests.credential_fixtures import credential_url
from tests.telemetry_sync_test import ContractHandler, Home


class TelemetryCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Home(self)
        user = tempfile.TemporaryDirectory()
        self.addCleanup(user.cleanup)
        self.environment = {"HOME": user.name, "AART_CLI_HOME": self.home.path}
        ContractHandler.stored = {}
        ContractHandler.mode = "ok"
        server = ThreadingHTTPServer(("127.0.0.1", 0), ContractHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f"http://127.0.0.1:{server.server_address[1]}"

    def _run(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.environment),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = cli.main(["consume", "telemetry", *argv])
        return code, out.getvalue()

    def _json(self, *argv: str) -> tuple[int, dict]:
        code, out = self._run(*argv, "--json")
        return code, json.loads(out)

    def test_it_is_off_until_a_person_turns_it_on(self) -> None:
        code, status = self._json("status")
        self.assertEqual((code, status["enabled"], status["endpoint"]), (0, False, None))
        self.assertEqual(status["events"]["waiting"], 0)
        self.assertFalse(self.home.outbox.exists())

    def test_without_an_address_or_an_offered_one_it_says_so(self) -> None:
        code, out = self._run("enable")
        self.assertEqual(code, 1)
        self.assertIn("--endpoint", out)
        self.assertFalse(self.home.outbox.exists())

    def test_a_refused_address_is_not_repeated(self) -> None:
        refused = credential_url("telemetry.example.com", user="u", held="pw")
        for raw in ("http://telemetry.example.com", refused):
            with self.subTest(raw=raw):
                code, out = self._run("enable", "--endpoint", raw)
                self.assertEqual(code, 1)
                self.assertNotIn("telemetry.example.com", out)
                self.assertNotIn("pw", out)
        self.assertFalse(self.home.outbox.exists())

    def test_on_it_says_what_is_sent_and_never(self) -> None:
        code, out = self._run("enable", "--endpoint", self.url)
        self.assertEqual(code, 0)
        self.assertIn(f"{self.url}/api/v1/events/batch", out)
        self.assertIn("Never a project, path, argument, prompt", out)
        code, status = self._json("status")
        self.assertEqual((status["enabled"], status["endpoint"]), (True, self.url))
        self.assertRegex(status["client_id"], r"^[0-9a-f-]{36}$")

    def test_an_offered_address_is_used_only_when_a_person_enables(self) -> None:
        with mock.patch.object(_default_telemetry, "ENDPOINT", "https://telemetry.example.com"):
            _, out = self._run("status")
            self.assertIn("telemetry: off", out)
            self.assertIn("this aart-cli offers: https://telemetry.example.com", out)
            self.assertFalse(self.home.outbox.exists())
            code, status = self._json("enable")
        self.assertEqual((code, status["endpoint"]), (0, "https://telemetry.example.com"))

    def test_sync_sends_now_and_reports_it(self) -> None:
        self._run("enable", "--endpoint", self.url)
        self.home.use(3)
        code, report = self._json("sync")
        self.assertEqual((code, report["sent"], report["requests"]), (0, 3, 1))
        self.assertEqual(len(ContractHandler.stored), 3)
        _, status = self._json("status")
        self.assertEqual((status["events"]["waiting"], status["events"]["sent"]), (0, 3))
        self.assertIsNotNone(status["last_success_at"])

    def test_a_server_that_fails_is_an_error_and_keeps_everything(self) -> None:
        self._run("enable", "--endpoint", self.url)
        self.home.use(2)
        ContractHandler.mode = "error"
        code, report = self._json("sync")
        self.assertEqual((code, report["sent"], report["reason"]), (1, 0, "unavailable"))
        _, status = self._json("status")
        self.assertEqual((status["events"]["waiting"], status["failures"]), (2, 1))
        self.assertIsNotNone(status["next_retry_at"])

    def test_off_keeps_what_waits_and_forget_deletes_it(self) -> None:
        self._run("enable", "--endpoint", self.url)
        self.home.use(2)
        code, _ = self._run("disable")
        self.assertEqual(code, 0)
        self.home.use(5)
        _, status = self._json("status")
        self.assertEqual((status["enabled"], status["events"]["waiting"]), (False, 2))
        self.assertEqual(self._json("sync")[1]["sent"], 0)
        code, _ = self._run("disable", "--forget")
        self.assertEqual(code, 0)
        _, status = self._json("status")
        self.assertEqual(
            (status["enabled"], status["client_id"], status["events"]),
            (False, None, {"waiting": 0, "sent": 0, "rejected": 0, "skipped": 0}),
        )


if __name__ == "__main__":
    unittest.main()
