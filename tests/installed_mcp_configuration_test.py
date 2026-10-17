"""Missing inputs cannot produce passing installation-configuration smoke evidence."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.mcp_smoke import SmokeOutcome, SmokeStage, SmokeStageResult
from aart_cli.commands import mcp
from aart_cli.domain.configuration_files import (
    ConfigurationFileRecord,
    configuration_file_path,
    render_configuration_file,
)
from aart_cli.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from aart_cli.domain.identifiers import InputId, ObjectDigest
from aart_cli.domain.inputs import SKIPPED_INPUT
from aart_cli.domain.result import Ok
from aart_cli.io import installed_smoke
from aart_cli.model import Request
from tests.mcp_smoke_selection_test import installed


def _digest(content: bytes) -> ObjectDigest:
    return ObjectDigest("sha256", hashlib.sha256(content).hexdigest())


class InstalledMcpConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        record = installed("company", "claude", root=self.directory.name)
        launcher = Path(record.receipt.launcher)
        launcher.parent.mkdir(parents=True)
        launcher.write_bytes(b"#!/bin/sh\nexit 0\n")
        launcher.chmod(0o700)
        self.record = replace(
            record, receipt=replace(record.receipt, launcher_digest=_digest(launcher.read_bytes()))
        )
        self.reference = CredentialReference(
            InputId("api-token"), CredentialProviderRef("macos-keychain", "aart-test", "owner")
        )
        self.protocol = mock.patch.object(
            installed_smoke,
            "_protocol",
            return_value=SmokeStageResult(
                SmokeStage.PROTOCOL, SmokeOutcome.PASS, "declared call returned successfully"
            ),
        )
        self.called = self.protocol.start()
        self.addCleanup(self.protocol.stop)

    def _secret(
        self, state=CredentialState.PRESENT, *, placeholder=False, provider=ProviderState.AVAILABLE
    ):
        observation = CredentialObservation(
            self.reference, provider, state, placeholder=placeholder
        )
        record = replace(
            self.record, receipt=replace(self.record.receipt, credentials=(self.reference,))
        )
        with mock.patch.object(installed_smoke, "MacOsKeychainProvider") as adapter:
            adapter.return_value.provider = "macos-keychain"
            adapter.return_value.inspect.return_value = Ok(observation)
            result = installed_smoke.smoke_installation(record, self.directory.name)
            adapter.return_value.inspect.assert_called_once_with(self.reference)
            adapter.return_value.read.assert_not_called()
        return result

    def _ordinary(self, value):
        path = Path(configuration_file_path(self.record.receipt.root, "claude"))
        path.parent.mkdir(parents=True, exist_ok=True)
        content = render_configuration_file(
            "mcp/identity",
            "claude",
            ((InputId("site"), value), (InputId("other-site"), "configured")),
        ).encode()
        path.write_bytes(content)
        record = replace(
            self.record,
            receipt=replace(
                self.record.receipt,
                configuration_files=(
                    ConfigurationFileRecord("claude", str(path), _digest(content)),
                ),
            ),
        )
        return installed_smoke.smoke_installation(record, self.directory.name)

    def _not_configured(self, report):
        self.assertFalse(report.ok)
        self.assertEqual(
            [stage.outcome for stage in report.stages],
            [SmokeOutcome.NOT_CONFIGURED, SmokeOutcome.NOT_RUN],
        )
        self.assertIn("Credentials and variables", report.stages[0].reason)
        self.assertIsNone(report.response)
        self.called.assert_not_called()

    def test_a_present_secret_placeholder_is_not_configured_and_never_starts_the_server(self):
        report = self._secret(placeholder=True)
        self._not_configured(report)
        self.assertIn(SKIPPED_INPUT, report.stages[0].reason)

    def test_an_absent_credential_is_not_configured_and_never_starts_the_server(self):
        self._not_configured(self._secret(CredentialState.ABSENT))

    def test_an_ordinary_placeholder_is_not_configured_and_never_starts_the_server(self):
        report = self._ordinary(SKIPPED_INPUT)
        self._not_configured(report)
        self.assertIn(SKIPPED_INPUT, report.stages[0].reason)

    def test_a_present_configured_reference_still_runs_the_protocol(self):
        report = self._secret()
        self.assertTrue(report.ok)
        self.called.assert_called_once()

    def test_an_unavailable_provider_remains_blocked(self):
        report = self._secret(CredentialState.UNKNOWN, provider=ProviderState.UNAVAILABLE)
        self.assertEqual(
            [stage.outcome for stage in report.stages], [SmokeOutcome.BLOCKED, SmokeOutcome.NOT_RUN]
        )
        self.assertIsInstance(report.stages[0].reason, str)
        self.assertTrue(report.stages[0].reason)
        self.called.assert_not_called()

    def test_invalid_or_unknown_credentials_remain_blocked(self):
        for state in (CredentialState.INVALID, CredentialState.UNKNOWN):
            with self.subTest(state=state):
                report = self._secret(state)
                self.assertEqual(report.stages[0].outcome, SmokeOutcome.BLOCKED)
                self.assertFalse(report.ok)
                self.assertIsInstance(report.stages[0].reason, str)
                self.assertTrue(report.stages[0].reason)
                self.called.assert_not_called()

    def test_cli_reports_not_configured_and_returns_nonzero_for_a_secret_placeholder(self):
        record = replace(
            self.record, receipt=replace(self.record.receipt, credentials=(self.reference,))
        )
        observation = CredentialObservation(
            self.reference, ProviderState.AVAILABLE, CredentialState.PRESENT, placeholder=True
        )
        output = io.StringIO()
        with (
            mock.patch.object(
                mcp,
                "load_runtime_configuration",
                return_value=Ok(
                    SimpleNamespace(paths=SimpleNamespace(data_root=self.directory.name))
                ),
            ),
            mock.patch.object(
                mcp, "resolved_paths", return_value=(self.directory.name, self.directory.name)
            ),
            mock.patch.object(mcp, "LocalReceiptStore") as store,
            mock.patch.object(installed_smoke, "MacOsKeychainProvider") as adapter,
            contextlib.redirect_stdout(output),
        ):
            store.return_value.installations.return_value = Ok((record,))
            adapter.return_value.provider = "macos-keychain"
            adapter.return_value.inspect.return_value = Ok(observation)
            status = mcp.run(
                Request(
                    "mcp", mcp_action="test", profiles=("claude",), all_installed=True, json=True
                )
            )
        self.assertNotEqual(status, 0)
        report = json.loads(output.getvalue())
        self.assertFalse(report["ok"])
        self.assertEqual(
            [s["outcome"] for s in report["targets"][0]["stages"]], ["NOT CONFIGURED", "NOT RUN"]
        )
        self.called.assert_not_called()

    def test_ordinary_answers_other_than_the_exact_placeholder_remain_usable(self):
        @given(
            value=st.text(
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
                min_size=1,
                max_size=40,
            ).filter(lambda value: value != SKIPPED_INPUT)
        )
        def usable(value):
            self.called.reset_mock()
            report = self._ordinary(value)
            self.assertTrue(report.ok)
            self.called.assert_called_once()

        usable()
