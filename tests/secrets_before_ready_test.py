"""§172.4, INV-259: a secret is captured before Ready and written by the transaction, never asked for.

The person enters a value on 07b, or skips it. The transaction then holds a single-use carrier per
reference. It writes the value to the provider through stdin, so the value never reaches the process
table. A skipped secret is written as the `SKIP` placeholder. In neither case is there a prompt
mid-transaction, and nothing blocks.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import uuid

from aart_cli.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from aart_cli.domain.effects import ReplaceCredential, StoreCredential
from aart_cli.domain.identifiers import InputId
from aart_cli.domain.inputs import SKIPPED_INPUT, BindingExposure
from aart_cli.domain.result import Err, Ok
from aart_cli.io.credentials import (
    ITEM_NOT_FOUND,
    SECURITY_TOOL,
    MacOsKeychainProvider,
    ProcessOutcome,
    TransientSecret,
)
from aart_cli.io.execution import CredentialEffectInterpreter

REFERENCE = CredentialReference(
    InputId("github-token"), CredentialProviderRef("macos-keychain", "aart-test", "github-token")
)
VALUE = "ghp_" + "q" * 36


class _Security:
    """Records each argv with the stdin it was given, and answers per subcommand."""

    def __init__(self, **statuses: ProcessOutcome) -> None:
        self.statuses = statuses
        self.calls: list[tuple[tuple[str, ...], str | None]] = []

    def __call__(self, argv, *, capture, timeout, stdin=None):
        self.calls.append((argv, stdin))
        subcommand = stdin.split()[0] if argv[1:] == ("-i",) and stdin else argv[1]
        return self.statuses.get(subcommand.replace("-", "_"), ProcessOutcome(0))


def _provider(security: _Security) -> MacOsKeychainProvider:
    return MacOsKeychainProvider(
        keychain="/tmp/aart-scripted.keychain",
        run=security,
        count=lambda *arguments, **options: None,
        timeout_seconds=5.0,
        available_on_host=lambda: True,
    )


class TheValueTravelsThroughStdinTest(unittest.TestCase):
    def test_a_carried_value_is_never_on_argv(self) -> None:
        security = _Security()

        stored = _provider(security).store(REFERENCE, TransientSecret(VALUE))

        self.assertIsInstance(stored, Ok, getattr(stored, "diagnostics", ()))
        argv, stdin = security.calls[0]
        self.assertEqual(argv, (SECURITY_TOOL, "-i"))
        self.assertNotIn(VALUE, "\x00".join(part for call, _ in security.calls for part in call))
        assert stdin is not None
        self.assertIn(f"-X {VALUE.encode().hex()} ", stdin)
        self.assertNotIn(VALUE, stdin)
        self.assertEqual(
            MacOsKeychainProvider.store_exposure(interactive=False), BindingExposure.PRIVATE
        )

    def test_a_write_the_keychain_did_not_take_is_a_failure(self) -> None:
        """`security -i` answers 0 for some failed commands, so the item is looked for afterwards."""

        security = _Security(find_generic_password=ProcessOutcome(ITEM_NOT_FOUND))

        stored = _provider(security).store(REFERENCE, TransientSecret(VALUE))

        self.assertIsInstance(stored, Err)
        self.assertIn("did not take", stored.diagnostics[0].message)  # type: ignore[union-attr]

    def test_a_refusal_does_not_echo_the_encoded_value(self) -> None:
        encoded = VALUE.encode().hex()
        security = _Security(
            add_generic_password=ProcessOutcome(45, stderr=f"bad command -X {encoded}")
        )

        stored = _provider(security).store(REFERENCE, TransientSecret(VALUE))

        assert isinstance(stored, Err)
        self.assertNotIn(encoded, stored.diagnostics[0].message)


class _Provider:
    provider = "macos-keychain"

    def __init__(self) -> None:
        self.journal: list[str] = []

    def store(self, reference, secret=None, *, replace=False):
        if secret is None:
            self.journal.append("prompted")
        else:
            held = secret.consume()
            self.journal.append("placeholder" if held == SKIPPED_INPUT else "carried")
        return Ok(
            CredentialObservation(reference, ProviderState.AVAILABLE, CredentialState.PRESENT)
        )

    def inspect(self, reference):
        return Ok(
            CredentialObservation(reference, ProviderState.AVAILABLE, CredentialState.PRESENT)
        )

    def delete(self, reference):
        return Ok(CredentialObservation(reference, ProviderState.AVAILABLE, CredentialState.ABSENT))


class TheTransactionNeverPromptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = _Provider()
        self.handed_over: list[object] = []

    def _interpreter(self, secrets) -> CredentialEffectInterpreter:
        return CredentialEffectInterpreter(
            self.provider,
            (REFERENCE,),
            secrets=secrets,
            skipped_as_placeholder=True,
            terminal_handover=lambda briefing=(): self.handed_over.append(briefing),  # type: ignore[arg-type,return-value]
        )

    def test_an_entered_value_is_written_once_without_the_terminal(self) -> None:
        carrier = TransientSecret(VALUE)
        interpreter = self._interpreter({str(REFERENCE): carrier})

        applied = interpreter.apply(StoreCredential(str(REFERENCE), "macos-keychain"))

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertEqual(self.provider.journal, ["carried"])
        self.assertTrue(carrier.consumed)
        self.assertEqual(self.handed_over, [])

    def test_a_skipped_secret_is_written_as_the_placeholder(self) -> None:
        applied = self._interpreter({}).apply(StoreCredential(str(REFERENCE), "macos-keychain"))

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertEqual(self.provider.journal, ["placeholder"])
        self.assertEqual(self.handed_over, [])

    def test_a_replacement_with_nothing_entered_keeps_the_value_it_would_overwrite(self) -> None:
        """A placeholder stands in for a value nobody gave; it never displaces one somebody did."""

        applied = self._interpreter({}).apply(ReplaceCredential(str(REFERENCE), "macos-keychain"))

        # Nothing blocks either: the item is left as it is, and nothing is asked for.
        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertIn("Credentials and variables", applied.value)  # type: ignore[union-attr]
        self.assertEqual(self.provider.journal, [])
        self.assertEqual(self.handed_over, [])


@unittest.skipUnless(sys.platform == "darwin", "the macOS Keychain is measured only on macOS")
class TheKeychainTakesAnyValueThroughStdinTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.keychain = os.path.join(directory.name, f"{uuid.uuid4().hex}.keychain-db")
        for arguments in (
            ("create-keychain", "-p", "test", self.keychain),
            ("unlock-keychain", "-p", "test", self.keychain),
        ):
            subprocess.run((SECURITY_TOOL, *arguments), check=True, capture_output=True)
        self.addCleanup(
            subprocess.run,
            (SECURITY_TOOL, "delete-keychain", self.keychain),
            check=False,
            capture_output=True,
        )
        self.provider = MacOsKeychainProvider(keychain=self.keychain, timeout_seconds=20.0)

    def test_quotes_spaces_and_non_ascii_survive_in_the_value_and_the_address(self) -> None:
        reference = CredentialReference(
            InputId("odd"), CredentialProviderRef("macos-keychain", 'svc "x" \\ y', 'a "b" \\c')
        )
        value = 'pa ss "w\\o" rd é'

        stored = self.provider.store(reference, TransientSecret(value))

        self.assertIsInstance(stored, Ok, getattr(stored, "diagnostics", ()))
        self.assertEqual(
            stored.value.detail,  # type: ignore[union-attr]
            f"a value of {len(value.encode())} bytes is present",
        )
        found = subprocess.run(
            (
                SECURITY_TOOL,
                "find-generic-password",
                "-a",
                'a "b" \\c',
                "-s",
                'svc "x" \\ y',
                self.keychain,
            ),
            capture_output=True,
            check=False,
        )
        self.assertEqual(found.returncode, 0)

    def test_a_replacement_through_stdin_holds_the_new_value(self) -> None:
        self.assertIsInstance(self.provider.store(REFERENCE, TransientSecret("a" * 10)), Ok)

        replaced = self.provider.store(REFERENCE, TransientSecret(SKIPPED_INPUT), replace=True)

        self.assertIsInstance(replaced, Ok, getattr(replaced, "diagnostics", ()))
        self.assertTrue(replaced.value.placeholder)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
