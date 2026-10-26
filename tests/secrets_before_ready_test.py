"""§172.4, §172.6, INV-259, D-487: the transaction asks the store only for what 07b marked.

The person marks a credential on 07b for the credential store to ask while installing, or leaves it.
A marked one is stored by the store's own prompt on the lent terminal, so no value passes through
aart-cli. Anything else is written as the `AART_NOT_SET` placeholder through stdin, so even that
never reaches the process table, and nothing else blocks.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

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


class TheTransactionAsksOnlyForWhatWasMarkedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = _Provider()
        self.handed_over: list[object] = []

    def _interpreter(self, prompted=frozenset(), references=(REFERENCE,)):
        return CredentialEffectInterpreter(
            self.provider,
            references,
            interactive_store=bool(prompted),
            prompted=frozenset(prompted),
            skipped_as_placeholder=True,
            terminal_handover=lambda briefing=(): _lent(self.handed_over, briefing),
        )

    def test_a_marked_credential_is_asked_by_the_store_on_the_lent_terminal(self) -> None:
        interpreter = self._interpreter({str(REFERENCE)})

        applied = interpreter.apply(StoreCredential(str(REFERENCE), "macos-keychain"))

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertEqual(self.provider.journal, ["prompted"])
        self.assertEqual(len(self.handed_over), 1)

    def test_an_unmarked_secret_is_written_as_the_placeholder(self) -> None:
        applied = self._interpreter().apply(StoreCredential(str(REFERENCE), "macos-keychain"))

        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertEqual(self.provider.journal, ["placeholder"])
        self.assertEqual(self.handed_over, [])

    def test_a_replacement_nobody_marked_keeps_the_value_it_would_overwrite(self) -> None:
        """A placeholder stands in for a value nobody gave; it never displaces one somebody did."""

        applied = self._interpreter().apply(ReplaceCredential(str(REFERENCE), "macos-keychain"))

        # Nothing blocks either: the item is left as it is, and nothing is asked for.
        self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))
        self.assertIn("Credentials and variables", applied.value)  # type: ignore[union-attr]
        self.assertEqual(self.provider.journal, [])
        self.assertEqual(self.handed_over, [])

    @given(st.lists(st.booleans(), min_size=1, max_size=6))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_each_reference_is_asked_exactly_when_marked_and_no_value_is_carried(
        self, marks
    ) -> None:
        references = tuple(
            CredentialReference(
                InputId("token"),
                CredentialProviderRef("macos-keychain", "aart-test", f"token-{index}"),
            )
            for index in range(len(marks))
        )
        self.provider, self.handed_over = _Provider(), []
        interpreter = self._interpreter(
            {str(item) for item, marked in zip(references, marks, strict=True) if marked},
            references,
        )

        for reference in references:
            applied = interpreter.apply(StoreCredential(str(reference), "macos-keychain"))
            self.assertIsInstance(applied, Ok, getattr(applied, "diagnostics", ()))

        self.assertEqual(
            self.provider.journal, ["prompted" if marked else "placeholder" for marked in marks]
        )
        self.assertEqual(len(self.handed_over), sum(marks))


def _lent(journal: list[object], briefing):
    import contextlib

    journal.append(briefing)
    return contextlib.nullcontext()


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
