"""§204, INV-308, D-492: a manifest may say how long its credential is, and a stored value of another length
is reported as not configured.

The owner's Jira token was stored as 128 characters: macOS's own password prompt keeps at most 128
and drops the rest, so an Atlassian token of about 190 arrived cut, and nothing said so. A length
is the one thing about a credential that can be measured without anybody holding it, so it is the
one check a manifest may declare; a pattern would need the value read to judge it.
"""

from __future__ import annotations

import json
import subprocess
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.domain.credentials import (
    CredentialCheck,
    CredentialLength,
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
    checked_observation,
)
from aart_cli.domain.effects import StoreCredential
from aart_cli.domain.identifiers import InputId
from aart_cli.domain.inputs import EnvironmentBinding, SecretInput, input_to_data
from aart_cli.domain.receipts import installation_receipt_from_data, installation_receipt_to_data
from aart_cli.domain.result import Err
from aart_cli.io.credential_entry import (
    EntryOutcome,
    KeychainAccessInstructions,
    MacOsDialogEntry,
    dialog_script,
    enter_another_way,
)
from aart_cli.io.credentials import PROMPT_CEILING_BYTES, ProcessOutcome
from aart_cli.io.execution import CredentialEffectInterpreter
from tests.authoring_inputs_test import TOKEN, _parsed, _reason
from tests.consumer_machine_read_test import RememberedEnvironmentTest
from tests.credential_lifecycle_integration_test import REFERENCE as KEYCHAIN_REFERENCE
from tests.credential_lifecycle_integration_test import ScriptedCounter, ScriptedSecurity, _provider

BOUND = st.one_of(st.none(), st.integers(1, 400))
REFERENCE = CredentialReference(
    InputId("jira-api-token"),
    CredentialProviderRef("macos-keychain", "aart-cli/company/mcp/jira", "jira-api-token"),
)


def _observed(state: CredentialState, length: int | None, **keywords) -> CredentialObservation:
    return CredentialObservation(
        REFERENCE, ProviderState.AVAILABLE, state, length=length, **keywords
    )


class CredentialLengthTest(unittest.TestCase):
    @given(BOUND, BOUND, st.integers(0, 500))
    def test_a_length_fails_exactly_when_it_is_outside_the_declared_bounds(
        self, low: int | None, high: int | None, length: int
    ) -> None:
        if low is None and high is None or (low and high and low > high):
            with self.assertRaises(ValueError):
                CredentialLength(low, high)
            return
        declared = CredentialLength(low, high)
        inside = (low is None or length >= low) and (high is None or length <= high)

        failure = declared.failure(length)

        self.assertEqual(failure is None, inside)
        if failure is not None:
            self.assertIn(f"has {length} characters", failure)

    def test_the_failure_says_what_was_expected_and_the_authors_message(self) -> None:
        declared = CredentialLength(150, 200, "Atlassian API tokens are about 190 characters")

        self.assertEqual(
            declared.failure(128),
            "the stored value has 128 characters, expected at least 150: "
            "Atlassian API tokens are about 190 characters",
        )
        self.assertIn("expected at most 200", declared.failure(201))

    def test_a_bound_below_one_or_not_a_whole_number_is_refused(self) -> None:
        for low, high in ((0, None), (None, 0), (True, None), (1.5, None), (-3, 5)):
            with self.subTest(low=low, high=high), self.assertRaises(ValueError):
                CredentialLength(low, high)  # type: ignore[arg-type]

    def test_a_check_names_a_reference_and_its_length(self) -> None:
        with self.assertRaises(ValueError):
            CredentialCheck(REFERENCE, None)  # type: ignore[arg-type]
        self.assertEqual(CredentialCheck(REFERENCE, CredentialLength(150)).length.min_length, 150)


class CheckedObservationTest(unittest.TestCase):
    def test_a_present_value_of_the_wrong_length_is_invalid_and_says_why(self) -> None:
        checked = checked_observation(
            _observed(CredentialState.PRESENT, 128), CredentialLength(150)
        )

        self.assertIs(checked.state, CredentialState.INVALID)
        self.assertIn("128 characters, expected at least 150", checked.detail)

    @given(st.integers(150, 300))
    def test_a_present_value_of_a_fitting_length_is_left_as_it_was(self, length: int) -> None:
        observed = _observed(CredentialState.PRESENT, length)

        self.assertEqual(checked_observation(observed, CredentialLength(150, 300)), observed)

    def test_what_cannot_be_judged_is_not_judged(self) -> None:
        declared = CredentialLength(150)
        for observed in (
            _observed(CredentialState.PRESENT, None),
            _observed(CredentialState.PRESENT, 1, placeholder=True),
            _observed(CredentialState.UNKNOWN, 1),
            _observed(CredentialState.ABSENT, None),
        ):
            with self.subTest(observed=observed):
                self.assertEqual(checked_observation(observed, declared), observed)
        unchecked = _observed(CredentialState.PRESENT, 1)
        self.assertEqual(checked_observation(unchecked, None), unchecked)

    def test_an_absent_value_has_no_length(self) -> None:
        with self.assertRaises(ValueError):
            _observed(CredentialState.ABSENT, 3)
        with self.assertRaises(ValueError):
            _observed(CredentialState.ABSENT, None, clipped=True)


class DeclaredLengthTest(unittest.TestCase):
    def test_a_secret_may_declare_the_length_of_its_value(self) -> None:
        declared = {**TOKEN, "validation": {"min_length": 150, "message": "about 190"}}

        secret = _parsed(inputs=[declared]).value.inputs[0]

        assert isinstance(secret, SecretInput)
        self.assertEqual(secret.validation, CredentialLength(150, None, "about 190"))

    def test_a_secret_declaring_no_length_judges_nothing(self) -> None:
        secret = _parsed(inputs=[TOKEN]).value.inputs[0]

        assert isinstance(secret, SecretInput)
        self.assertIsNone(secret.validation)

    def test_a_length_that_is_not_one_is_refused_by_name(self) -> None:
        for validation, said in (
            ({}, "min_length, max_length or both"),
            ({"min_length": 0}, "validation.min_length"),
            ({"max_length": "190"}, "validation.max_length"),
            ({"min_length": 200, "max_length": 100}, "not above max_length"),
            ({"min_length": 10, "pattern": "^ATATT"}, "unknown field 'pattern'"),
            ({"type": "url"}, "unknown field 'type'"),
            ("long", "validation"),
        ):
            with self.subTest(validation=validation):
                refused = _parsed(inputs=[{**TOKEN, "validation": validation}])

                self.assertIsInstance(refused, Err)
                self.assertIn(said, _reason(refused))

    def test_a_secret_without_a_length_keeps_the_data_it_had(self) -> None:
        """Declaring nothing must not move the digest of any artifact published before §204."""

        plain = SecretInput(InputId("jira-api-token"), EnvironmentBinding("JIRA_API_TOKEN"))
        checked = SecretInput(
            InputId("jira-api-token"),
            EnvironmentBinding("JIRA_API_TOKEN"),
            validation=CredentialLength(150),
        )

        self.assertNotIn("validation", input_to_data(plain))
        self.assertEqual(
            input_to_data(checked)["validation"],
            {"max_length": None, "message": "", "min_length": 150},
        )


class RecordedLengthTest(unittest.TestCase):
    def _receipt(self, **overrides):
        return RememberedEnvironmentTest.receipt(
            RememberedEnvironmentTest(), **{"credentials": (REFERENCE,), **overrides}
        )

    def test_a_receipt_keeps_the_declared_length_through_its_document(self) -> None:
        checked = self._receipt(
            credential_checks=(CredentialCheck(REFERENCE, CredentialLength(150)),)
        )

        read = installation_receipt_from_data(
            json.loads(json.dumps(installation_receipt_to_data(checked)))
        )

        self.assertEqual(read.value, checked)
        self.assertEqual(read.value.credential_length(REFERENCE), CredentialLength(150))

    def test_a_receipt_declaring_nothing_reads_as_it_did_before(self) -> None:
        self.assertNotIn("credential_checks", installation_receipt_to_data(self._receipt()))
        self.assertIsNone(self._receipt().credential_length(REFERENCE))

    def test_a_check_of_a_credential_the_receipt_does_not_record_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self._receipt(
                credentials=(),
                credential_checks=(CredentialCheck(REFERENCE, CredentialLength(150)),),
            )
        written = installation_receipt_to_data(
            self._receipt(credential_checks=(CredentialCheck(REFERENCE, CredentialLength(150)),))
        )
        written["credential_checks"][0]["input"] = "another-token"
        self.assertIsInstance(installation_receipt_from_data(written), Err)


class MeasuredLengthTest(unittest.TestCase):
    def _inspected(self, printed: int):
        runner = ScriptedSecurity(find_generic_password=ProcessOutcome(0))
        return _provider(runner, ScriptedCounter(printed=printed, hex_encoded=0)).inspect(
            KEYCHAIN_REFERENCE
        )

    def test_the_keychain_says_how_long_the_value_is_without_reading_it(self) -> None:
        observed = self._inspected(191).value

        self.assertEqual(observed.length, 190)
        self.assertFalse(observed.clipped)

    def test_a_value_as_long_as_the_prompt_keeps_is_marked_clipped(self) -> None:
        observed = self._inspected(PROMPT_CEILING_BYTES + 1).value

        self.assertEqual(observed.length, PROMPT_CEILING_BYTES)
        self.assertTrue(observed.clipped)


class _Store:
    """A provider whose prompt stores a value of `length` bytes, and a fallback may change it."""

    provider = "macos-keychain"

    def __init__(self, length: int) -> None:
        self.length = length

    def inspect(self, reference):
        from aart_cli.domain.result import Ok

        return Ok(_observed(CredentialState.PRESENT, self.length, clipped=self.length == 128))

    def store(self, reference, secret=None, *, replace=False):
        return self.inspect(reference)


class _Way:
    def __init__(self, outcome: EntryOutcome, store: _Store | None = None, length: int = 190):
        self.outcome, self.store, self.length = outcome, store, length
        self.asked: list[str] = []

    def enter(self, reference, *, reason: str) -> EntryOutcome:
        self.asked.append(reason)
        if self.store is not None and self.outcome is EntryOutcome.ENTERED:
            self.store.length = self.length
        return self.outcome


class InterpreterFallbackTest(unittest.TestCase):
    def _apply(self, store: _Store, *ways: _Way, length: CredentialLength | None = None):
        interpreter = CredentialEffectInterpreter(
            store,  # type: ignore[arg-type]
            (REFERENCE,),
            interactive_store=True,
            lengths=None if length is None else {str(REFERENCE): length},
            fallbacks=ways,
        )
        return interpreter.apply(StoreCredential(str(REFERENCE), "macos-keychain"))

    def test_a_value_failing_its_declared_length_is_entered_another_way(self) -> None:
        store = _Store(128)
        way = _Way(EntryOutcome.ENTERED, store)

        applied = self._apply(store, way, length=CredentialLength(150))

        self.assertEqual(applied.value, f"{REFERENCE} is present")
        self.assertIn("expected at least 150", way.asked[0])

    def test_without_a_declaration_a_value_on_the_ceiling_is_offered_another_way(self) -> None:
        store = _Store(128)
        way = _Way(EntryOutcome.ENTERED, store)

        self._apply(store, way)

        self.assertIn("exactly 128 characters", way.asked[0])

    def test_a_declared_length_that_fits_decides_even_on_the_ceiling(self) -> None:
        way = _Way(EntryOutcome.ENTERED)

        applied = self._apply(_Store(128), way, length=CredentialLength(100, 128))

        self.assertEqual(way.asked, [])
        self.assertEqual(applied.value, f"{REFERENCE} is present")

    def test_a_value_still_unfit_is_said_to_be_invalid_and_why(self) -> None:
        store = _Store(128)
        applied = self._apply(
            store, _Way(EntryOutcome.CANCELLED, store), length=CredentialLength(150)
        )

        self.assertTrue(applied.value.startswith(f"{REFERENCE} is invalid: "))
        self.assertIn("expected at least 150", applied.value)

    def test_the_first_way_that_can_ask_is_the_only_one_asked(self) -> None:
        store = _Store(128)
        missing, asked, never = (
            _Way(EntryOutcome.UNAVAILABLE),
            _Way(EntryOutcome.ENTERED, store),
            _Way(EntryOutcome.ENTERED, store),
        )

        self._apply(store, missing, asked, never, length=CredentialLength(150))

        self.assertEqual((len(missing.asked), len(asked.asked), len(never.asked)), (1, 1, 0))
        self.assertIs(
            enter_another_way((missing,), REFERENCE, reason="cut"), EntryOutcome.UNAVAILABLE
        )


def _ran(code: int, said: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(("osascript",), code, said, "")


class DialogTest(unittest.TestCase):
    def test_the_script_carries_no_value_and_writes_hex_to_security_on_a_pipe(self) -> None:
        script = dialog_script(REFERENCE, "cut at 128", "/tmp/aart-test.keychain")

        self.assertIn("hiddenAnswer: true", script)
        self.assertIn('task.arguments = ["-i"]', script)
        self.assertIn('-X " + hex', script)
        self.assertIn("delete-generic-password", script)
        self.assertNotIn("-U", script)
        self.assertIn(json.dumps("/tmp/aart-test.keychain")[1:-1], script)

    @given(st.text(min_size=1, max_size=40).filter(lambda text: text == text.strip()))
    def test_whatever_a_service_is_called_it_stays_inside_a_json_literal(self, name: str) -> None:
        try:
            reference = CredentialReference(
                InputId("jira-api-token"), CredentialProviderRef("macos-keychain", name, "me")
            )
        except ValueError:
            return
        script = dialog_script(reference, "cut")
        line = next(item for item in script.splitlines() if "var commands" in item)
        literal = line.split(" = ", 1)[1].split(" + ")[0]

        self.assertTrue(json.loads(literal).startswith("delete-generic-password"))

    def test_what_osascript_says_is_what_the_dialog_did(self) -> None:
        for ran, outcome in (
            (_ran(0, "entered\n"), EntryOutcome.ENTERED),
            (_ran(0, "cancelled\n"), EntryOutcome.CANCELLED),
            (_ran(1, ""), EntryOutcome.UNAVAILABLE),
            (_ran(0, "something else"), EntryOutcome.UNAVAILABLE),
        ):
            with self.subTest(said=ran.stdout, code=ran.returncode):
                entry = MacOsDialogEntry(run=lambda *_, said=ran: said, available=lambda: True)
                self.assertIs(entry.enter(REFERENCE, reason="cut"), outcome)

    def test_no_desktop_or_no_osascript_means_the_next_way_is_tried(self) -> None:
        def missing(*_):
            raise OSError("no osascript")

        self.assertIs(
            MacOsDialogEntry(available=lambda: False).enter(REFERENCE, reason="cut"),
            EntryOutcome.UNAVAILABLE,
        )
        self.assertIs(
            MacOsDialogEntry(run=missing, available=lambda: True).enter(REFERENCE, reason="cut"),
            EntryOutcome.UNAVAILABLE,
        )


class InstructionsTest(unittest.TestCase):
    def _entry(self, answer: str | None):
        said: list[str] = []
        opened: list[bool] = []

        def read() -> str:
            if answer is None:
                raise EOFError
            return answer

        entry = KeychainAccessInstructions(
            write=said.append,
            read_line=read,
            open_app=lambda: opened.append(True),
            available=lambda: True,
        )
        return entry, said, opened

    def test_they_name_the_item_open_keychain_access_and_wait_for_enter(self) -> None:
        entry, said, opened = self._entry("")

        self.assertIs(entry.enter(REFERENCE, reason="the value was cut"), EntryOutcome.ENTERED)
        text = "\n".join(said)
        self.assertIn("the value was cut", text)
        self.assertIn(f"Keychain Item Name: {REFERENCE.provider.service}", text)
        self.assertIn(f"Account Name:       {REFERENCE.provider.account}", text)
        self.assertIn("Always Allow", text)
        self.assertEqual(opened, [True])

    def test_s_or_no_input_leaves_it_for_now(self) -> None:
        for answer in ("s", " S ", None):
            with self.subTest(answer=answer):
                entry, _, _ = self._entry(answer)
                self.assertIs(entry.enter(REFERENCE, reason="cut"), EntryOutcome.CANCELLED)


if __name__ == "__main__":
    unittest.main()
