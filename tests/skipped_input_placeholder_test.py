"""§172.3, INV-261: a skipped input is the literal `SKIP`, accepted as stored and then recognised.

Nothing blocks on the placeholder. Validation applies to entered answers, so `SKIP` passes every
rule a real value would have to meet. A provider recognises it as a placeholder without this
process reading the stored secret.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.domain.credentials import (
    CredentialObservation,
    CredentialProviderRef,
    CredentialReference,
    CredentialState,
    ProviderState,
)
from aart_cli.domain.identifiers import InputId
from aart_cli.domain.inputs import (
    SKIPPED_INPUT,
    InputValidation,
    is_skipped_value,
    validate_config_value,
)
from aart_cli.io.credentials import MacOsKeychainProvider

REFERENCE = CredentialReference(
    InputId("github-token"), CredentialProviderRef("macos-keychain", "aart-test", "github-token")
)


class ThePlaceholderIsAcceptedAsStoredTest(unittest.TestCase):
    def test_it_is_the_literal_skip(self) -> None:
        self.assertEqual(SKIPPED_INPUT, "SKIP")

    def test_validation_does_not_judge_the_placeholder(self) -> None:
        for validation in (
            InputValidation("url", allowed_hosts=("github.company",)),
            InputValidation("identifier"),
            InputValidation("pattern", pattern=r"[0-9]{6}"),
        ):
            with self.subTest(kind=validation.kind):
                self.assertIsNone(validate_config_value(validation, SKIPPED_INPUT))
                self.assertIsNotNone(validate_config_value(validation, "skip me"))

    @given(st.text(max_size=12))
    def test_only_the_exact_placeholder_counts_as_skipped(self, value: str) -> None:
        self.assertEqual(is_skipped_value(value), value == "SKIP")

    def test_an_observation_says_placeholder_only_for_a_present_item(self) -> None:
        held = CredentialObservation(
            REFERENCE, ProviderState.AVAILABLE, CredentialState.PRESENT, placeholder=True
        )
        self.assertTrue(held.placeholder)
        with self.assertRaises(ValueError):
            CredentialObservation(
                REFERENCE, ProviderState.AVAILABLE, CredentialState.ABSENT, placeholder=True
            )


@unittest.skipUnless(sys.platform == "darwin", "the macOS Keychain is measured only on macOS")
class TheKeychainRecognisesThePlaceholderTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.keychain = os.path.join(directory.name, "placeholder.keychain-db")
        subprocess.run(
            ("/usr/bin/security", "create-keychain", "-p", "test", self.keychain), check=True
        )
        self.addCleanup(
            subprocess.run, ("/usr/bin/security", "delete-keychain", self.keychain), check=False
        )
        subprocess.run(
            ("/usr/bin/security", "unlock-keychain", "-p", "test", self.keychain), check=True
        )
        self.provider = MacOsKeychainProvider(keychain=self.keychain)

    def _hold(self, value: str) -> None:
        command = (
            f"add-generic-password -a {REFERENCE.provider.account} "
            f"-s {REFERENCE.provider.service} -X {value.encode().hex()} {self.keychain}\n"
        )
        subprocess.run(("/usr/bin/security", "-i"), input=command, text=True, check=True)

    def test_the_placeholder_is_reported_and_a_value_is_not(self) -> None:
        for value, placeholder in (("SKIP", True), ("ghp_" + "x" * 36, False), ("SKIPPED", False)):
            with self.subTest(value=value[:4]):
                self.provider.delete(REFERENCE)
                self._hold(value)

                observed = self.provider.inspect(REFERENCE)

                self.assertIs(observed.value.state, CredentialState.PRESENT)  # type: ignore[union-attr]
                self.assertIs(observed.value.placeholder, placeholder)  # type: ignore[union-attr]
                if not placeholder:
                    self.assertNotIn(value, repr(observed))


if __name__ == "__main__":
    unittest.main()
