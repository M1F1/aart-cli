"""CP-08 credential provider interpreter integration.

The scripted half proves the argv this package actually builds and the statuses it reads back.
The gated half runs the same interpreter against a real, temporary macOS Keychain, so the shape
of the commands is checked against `security` itself rather than against a fake that agrees.
"""

from __future__ import annotations

import copy
import json
import os
import pickle
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from agent_artifacts.application.credential_lifecycle import (
    CREDENTIAL_STATE_CONFLICT,
    credential_plan_to_data,
    plan_credential_mutation,
)
from agent_artifacts.domain.credentials import (
    CredentialIntent,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.identifiers import InputId
from agent_artifacts.domain.inputs import BindingExposure
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io import credentials as io_credentials
from agent_artifacts.io.credentials import (
    ITEM_NOT_FOUND,
    PROMPT_CEILING_BYTES,
    SECURITY_TOOL,
    MacOsKeychainProvider,
    ProcessOutcome,
    SecretConsumedError,
    TransientSecret,
)
from tests.credential_fixtures import credential_url

PROVIDER = CredentialProviderRef("macos-keychain", "com.example.forge", "agent")
REFERENCE = CredentialReference(InputId("forge-credential"), PROVIDER)


class ScriptedSecurity:
    """A stand-in for `security` that records every argv and answers from a script."""

    def __init__(
        self,
        timeline: list[str] | None = None,
        **statuses: ProcessOutcome,
    ) -> None:
        self.statuses = statuses
        self.timeline = [] if timeline is None else timeline
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        capture: bool,
        timeout: float,
    ) -> ProcessOutcome:
        self.calls.append((argv, capture))
        self.timeline.append(argv[1])
        return self.statuses.get(argv[1].replace("-", "_"), ProcessOutcome(0))

    @property
    def subcommands(self) -> tuple[str, ...]:
        return tuple(argv[1] for argv, _ in self.calls)

    def flat(self) -> str:
        return "\x00".join("\x00".join(argv) for argv, _ in self.calls)


class ScriptedCounter:
    """A stand-in for the counting pipeline, which in production never returns content."""

    def __init__(
        self,
        printed: int | None = 0,
        hex_encoded: int | None = 0,
        timeline: list[str] | None = None,
    ) -> None:
        self.printed = printed
        self.hex_encoded = hex_encoded
        self.timeline = [] if timeline is None else timeline
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        producer: tuple[str, ...],
        counter: tuple[str, ...],
        *,
        from_stderr: bool,
        counter_accepts: tuple[int, ...],
        timeout: float,
    ) -> int | None:
        self.calls.append(producer)
        self.timeline.append("measure" + producer[-2])
        return self.hex_encoded if from_stderr else self.printed


def _provider(
    runner: ScriptedSecurity,
    counter: ScriptedCounter | None = None,
    *,
    keychain: str | None = "/tmp/aart-scripted.keychain",
) -> MacOsKeychainProvider:
    return MacOsKeychainProvider(
        keychain=keychain,
        run=runner,
        count=counter or ScriptedCounter(printed=None),
        timeout_seconds=5.0,
    )


class TransientSecretTest(unittest.TestCase):
    def test_it_redacts_itself_in_every_string_form(self) -> None:
        secret = TransientSecret("correct-horse-battery-staple")
        for rendered in (repr(secret), str(secret), f"{secret}", f"{secret!s}", format(secret)):
            self.assertNotIn("horse", rendered)
            self.assertIn("redacted", rendered)

    def test_it_refuses_to_be_serialized_or_copied(self) -> None:
        secret = TransientSecret("correct-horse-battery-staple")
        with self.assertRaises(TypeError):
            pickle.dumps(secret)
        with self.assertRaises(TypeError):
            copy.copy(secret)
        with self.assertRaises(TypeError):
            copy.deepcopy(secret)
        self.assertFalse(secret.consumed)

    def test_it_yields_its_value_exactly_once(self) -> None:
        secret = TransientSecret("correct-horse-battery-staple")
        self.assertEqual(secret.consume(), "correct-horse-battery-staple")
        self.assertTrue(secret.consumed)
        with self.assertRaises(SecretConsumedError):
            secret.consume()

    def test_an_empty_value_is_not_a_secret(self) -> None:
        with self.assertRaises(ValueError):
            TransientSecret("")


class KeychainInterpreterTest(unittest.TestCase):
    def test_a_missing_item_reads_as_absent_not_as_a_failure(self) -> None:
        runner = ScriptedSecurity(find_generic_password=ProcessOutcome(ITEM_NOT_FOUND))

        result = _provider(runner).inspect(REFERENCE)

        assert isinstance(result, Ok), result
        self.assertEqual(result.value.state, CredentialState.ABSENT)
        self.assertEqual(result.value.provider_state, ProviderState.AVAILABLE)
        argv, capture = runner.calls[0]
        self.assertEqual(argv[:2], (SECURITY_TOOL, "find-generic-password"))
        self.assertEqual(argv[2:6], ("-a", "agent", "-s", "com.example.forge"))
        self.assertEqual(argv[-1], "/tmp/aart-scripted.keychain")
        self.assertTrue(capture)

    def test_a_present_item_is_described_by_length_and_never_by_content(self) -> None:
        runner = ScriptedSecurity(find_generic_password=ProcessOutcome(0))
        counter = ScriptedCounter(printed=12, hex_encoded=0)

        result = _provider(runner, counter).inspect(REFERENCE)

        assert isinstance(result, Ok), result
        self.assertEqual(result.value.state, CredentialState.PRESENT)
        self.assertEqual(result.value.detail, "a value of 11 bytes is present")
        self.assertEqual([argv[-2] for argv in counter.calls], ["-w", "-g"])

    def test_a_value_sitting_on_the_prompt_ceiling_is_reported_as_probably_cut(self) -> None:
        runner = ScriptedSecurity(find_generic_password=ProcessOutcome(0))
        counter = ScriptedCounter(printed=PROMPT_CEILING_BYTES + 1, hex_encoded=0)

        result = _provider(runner, counter).inspect(REFERENCE)

        assert isinstance(result, Ok), result
        self.assertIn(str(PROMPT_CEILING_BYTES), result.value.detail)
        self.assertIn("cuts", result.value.detail)

    def test_a_hex_encoded_value_is_measured_in_bytes_not_in_printed_characters(self) -> None:
        runner = ScriptedSecurity(find_generic_password=ProcessOutcome(0))
        counter = ScriptedCounter(printed=25, hex_encoded=1)

        result = _provider(runner, counter).inspect(REFERENCE)

        assert isinstance(result, Ok), result
        self.assertEqual(result.value.detail, "a value of 12 bytes is present")

    def test_an_unmeasurable_length_is_stated_as_such_rather_than_guessed(self) -> None:
        runner = ScriptedSecurity(find_generic_password=ProcessOutcome(0))

        result = _provider(runner, ScriptedCounter(printed=None)).inspect(REFERENCE)

        assert isinstance(result, Ok), result
        self.assertEqual(result.value.detail, "a value is present")

    def test_the_default_store_path_keeps_the_value_inside_the_provider(self) -> None:
        runner = ScriptedSecurity(
            add_generic_password=ProcessOutcome(0),
            find_generic_password=ProcessOutcome(0),
        )

        result = _provider(runner, ScriptedCounter(printed=None)).store(REFERENCE)

        assert isinstance(result, Ok), result
        self.assertEqual(result.value.state, CredentialState.PRESENT)
        write, capture = runner.calls[0]
        self.assertEqual(write[1], "add-generic-password")
        self.assertEqual(write[-2], "-w")  # `-w` with nothing after it makes `security` prompt.
        self.assertFalse(capture)  # The terminal stays attached, which is what the prompt needs.
        self.assertEqual(
            MacOsKeychainProvider.store_exposure(interactive=True),
            BindingExposure.PRIVATE,
        )

    def test_the_non_interactive_store_names_the_exposure_it_accepts(self) -> None:
        runner = ScriptedSecurity(
            add_generic_password=ProcessOutcome(0),
            find_generic_password=ProcessOutcome(0),
        )
        secret = TransientSecret("value-from-a-pipeline")

        result = _provider(runner, ScriptedCounter(printed=None)).store(REFERENCE, secret)

        assert isinstance(result, Ok), result
        self.assertTrue(secret.consumed)
        self.assertIn("value-from-a-pipeline", runner.flat())
        self.assertEqual(
            MacOsKeychainProvider.store_exposure(interactive=False),
            BindingExposure.PROCESS_TABLE,
        )

    def test_replacement_removes_then_adds_and_never_reads_the_previous_value(self) -> None:
        # `add-generic-password -U` asks the window server for authorization and waits, so an
        # unattended replacement can only go through the pair. See DECISIONS.md D-017.
        timeline: list[str] = []
        runner = ScriptedSecurity(
            timeline,
            delete_generic_password=ProcessOutcome(0),
            add_generic_password=ProcessOutcome(0),
            find_generic_password=ProcessOutcome(0),
        )
        counter = ScriptedCounter(printed=8, hex_encoded=0, timeline=timeline)

        result = _provider(runner, counter).store(REFERENCE, replace=True)

        assert isinstance(result, Ok), result
        self.assertNotIn("-U", runner.flat())
        # Nothing reads the old value: the only measurement follows the write of the new one.
        self.assertEqual(
            timeline,
            [
                "delete-generic-password",
                "add-generic-password",
                "find-generic-password",
                "measure-w",
                "measure-g",
            ],
        )

    def test_a_replacement_that_fails_after_removal_says_the_credential_is_gone(self) -> None:
        runner = ScriptedSecurity(
            delete_generic_password=ProcessOutcome(0),
            add_generic_password=ProcessOutcome(51, stderr="write permissions error"),
        )

        result = _provider(runner).store(REFERENCE, TransientSecret("new-value"), replace=True)

        assert isinstance(result, Err), result
        self.assertIn("now absent", result.diagnostics[0].message)

    def test_deleting_an_item_that_is_already_gone_settles_on_absent(self) -> None:
        runner = ScriptedSecurity(delete_generic_password=ProcessOutcome(ITEM_NOT_FOUND))

        result = _provider(runner).delete(REFERENCE)

        assert isinstance(result, Ok), result
        self.assertEqual(result.value.state, CredentialState.ABSENT)

    def test_a_provider_failure_is_reported_with_its_output_redacted(self) -> None:
        leaked = credential_url("forge.example.com", "/repo.git")
        runner = ScriptedSecurity(find_generic_password=ProcessOutcome(1, stderr=leaked))

        result = _provider(runner).inspect(REFERENCE)

        assert isinstance(result, Err), result
        message = result.diagnostics[0].message
        self.assertNotIn("secret", message)
        self.assertIn("status 1", message)

    def test_an_unavailable_provider_is_an_observation_not_an_invention(self) -> None:
        runner = ScriptedSecurity()
        with mock.patch.object(io_credentials, "SECURITY_TOOL", "/nonexistent/security"):
            provider = _provider(runner)
            observed = provider.inspect(REFERENCE)
            stored = provider.store(REFERENCE, TransientSecret("unused"))

        assert isinstance(observed, Ok), observed
        self.assertEqual(observed.value.provider_state, ProviderState.UNAVAILABLE)
        self.assertEqual(observed.value.state, CredentialState.UNKNOWN)
        assert isinstance(stored, Err), stored
        self.assertEqual(runner.calls, [])


class PlannedLifecycleAgainstAProviderTest(unittest.TestCase):
    """The planner and the interpreter meeting, which is where a value could leak and does not."""

    def test_a_store_plan_runs_against_the_provider_and_carries_no_value(self) -> None:
        runner = ScriptedSecurity(
            find_generic_password=ProcessOutcome(ITEM_NOT_FOUND),
            add_generic_password=ProcessOutcome(0),
        )
        provider = _provider(runner, ScriptedCounter(printed=None))

        observed = provider.inspect(REFERENCE)
        assert isinstance(observed, Ok), observed
        planned = plan_credential_mutation(
            CredentialIntent.STORE, observed.value, policy=EffectivePolicy()
        )
        assert isinstance(planned, Ok), planned

        rendered = json.dumps(credential_plan_to_data(planned.value), sort_keys=True)
        self.assertNotIn("value-from-a-pipeline", rendered)
        self.assertIn("store-credential", rendered)
        self.assertIn("verify-credential", rendered)

        runner.statuses["find_generic_password"] = ProcessOutcome(0)
        applied = provider.store(REFERENCE, TransientSecret("value-from-a-pipeline"))
        assert isinstance(applied, Ok), applied
        self.assertEqual(applied.value.state, CredentialState.PRESENT)

    def test_storing_over_an_existing_credential_is_refused_before_any_process_runs(self) -> None:
        runner = ScriptedSecurity(find_generic_password=ProcessOutcome(0))
        provider = _provider(runner, ScriptedCounter(printed=None))

        observed = provider.inspect(REFERENCE)
        assert isinstance(observed, Ok), observed
        planned = plan_credential_mutation(
            CredentialIntent.STORE, observed.value, policy=EffectivePolicy()
        )

        assert isinstance(planned, Err), planned
        self.assertEqual(planned.diagnostics[0].code, CREDENTIAL_STATE_CONFLICT)
        self.assertEqual(runner.subcommands, ("find-generic-password",))


def _keychain_is_usable() -> bool:
    return sys.platform == "darwin" and os.access(SECURITY_TOOL, os.X_OK)


@unittest.skipUnless(_keychain_is_usable(), "the macOS Keychain is not available here")
class RealKeychainRoundTripTest(unittest.TestCase):
    """The full lifecycle against `security`, scoped to a keychain created for this test.

    Every command names that keychain explicitly, so the developer's login keychain is never in
    the search path and never touched. Items keep their default access control, exactly as they
    would in production; the creating tool is trusted to read them back, so nothing prompts.
    """

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.keychain = str(Path(self.directory.name) / f"aart-{uuid.uuid4().hex}.keychain")
        unlock = uuid.uuid4().hex
        self._security("create-keychain", "-p", unlock, self.keychain)
        self.addCleanup(self._destroy)
        self._security("set-keychain-settings", self.keychain)  # No idle lock during the test.
        self._security("unlock-keychain", "-p", unlock, self.keychain)
        self.provider = MacOsKeychainProvider(keychain=self.keychain, timeout_seconds=20.0)

    def _security(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (SECURITY_TOOL, *arguments),
            shell=False,
            capture_output=True,
            text=True,
            timeout=20.0,
            check=True,
        )

    def _destroy(self) -> None:
        subprocess.run(
            (SECURITY_TOOL, "delete-keychain", self.keychain),
            shell=False,
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
        )

    def test_inspect_store_replace_and_delete_against_a_real_keychain(self) -> None:
        absent = self.provider.inspect(REFERENCE)
        assert isinstance(absent, Ok), absent
        self.assertEqual(absent.value.state, CredentialState.ABSENT)

        stored = self.provider.store(REFERENCE, TransientSecret("a" * 20))
        assert isinstance(stored, Ok), stored
        self.assertEqual(stored.value.state, CredentialState.PRESENT)
        self.assertEqual(stored.value.detail, "a value of 20 bytes is present")

        replaced = self.provider.store(REFERENCE, TransientSecret("b" * 41), replace=True)
        assert isinstance(replaced, Ok), replaced
        self.assertEqual(replaced.value.detail, "a value of 41 bytes is present")

        removed = self.provider.delete(REFERENCE)
        assert isinstance(removed, Ok), removed
        self.assertEqual(removed.value.state, CredentialState.ABSENT)
        self.assertIsNone(self.provider.stored_length(REFERENCE))

        again = self.provider.delete(REFERENCE)
        assert isinstance(again, Ok), again
        self.assertEqual(again.value.state, CredentialState.ABSENT)

    def test_a_value_that_is_not_printable_ascii_is_still_measured_in_bytes(self) -> None:
        stored = self.provider.store(REFERENCE, TransientSecret("\u00e9" * 8))

        assert isinstance(stored, Ok), stored
        # Eight characters, sixteen UTF-8 bytes, which `security` prints back as thirty-two hex
        # digits. Counting what is printed would have said thirty-two.
        self.assertEqual(stored.value.detail, "a value of 16 bytes is present")

    def test_a_value_on_the_prompt_ceiling_is_flagged_by_a_real_measurement(self) -> None:
        stored = self.provider.store(REFERENCE, TransientSecret("c" * PROMPT_CEILING_BYTES))

        assert isinstance(stored, Ok), stored
        self.assertIn("cuts", stored.value.detail)

    def test_a_planned_delete_and_its_execution_agree_on_the_observed_state(self) -> None:
        stored = self.provider.store(REFERENCE, TransientSecret("d" * 12))
        assert isinstance(stored, Ok), stored

        planned = plan_credential_mutation(
            CredentialIntent.DELETE, stored.value, policy=EffectivePolicy()
        )
        assert isinstance(planned, Ok), planned
        rendered = json.dumps(credential_plan_to_data(planned.value), sort_keys=True)
        self.assertNotIn("dddd", rendered)

        applied = self.provider.delete(REFERENCE)
        assert isinstance(applied, Ok), applied
        self.assertEqual(applied.value.state, CredentialState.ABSENT)


if __name__ == "__main__":
    unittest.main()
