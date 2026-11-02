"""`scripts/secret_shape_check.py` sees a credential assigned to a key that ends in a credential
word, the `API_TOKEN=…` an environment file or a transcript holds, as push protection does."""

from __future__ import annotations

import importlib.util
import pathlib
import secrets
import sys
import unittest

from tests.credential_fixtures import assignment

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "_secret_shape_check", ROOT / "scripts" / "secret_shape_check.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = _load()


def _codes(line: str) -> list[str]:
    return [finding.code for finding in check._scan_text("example.py", line)]


def _said(name: str, value: str) -> str:
    return 'said = "' + assignment(name, value) + '"'


class SecretShapeCheckTest(unittest.TestCase):
    def test_a_key_that_ends_in_a_credential_word_assigned_a_value_is_refused(self) -> None:
        for name in ("API_TOKEN", "DB_PASSWORD", "client_secret", "SERVICE_CREDENTIAL"):
            with self.subTest(name=name):
                value = "held-" + secrets.token_hex(8)
                self.assertEqual(_codes(_said(name, value)), ["credential-assignment"])

    def test_a_key_that_names_where_a_secret_is_kept_is_allowed(self) -> None:
        self.assertEqual(_codes(_said("AART_CLI_PASSWORD_SECRET_NAME", "MINE")), [])

    def test_a_placeholder_assigned_to_such_a_key_is_allowed(self) -> None:
        for value in ("{held}", "<yours>", "[redacted]"):
            with self.subTest(value=value):
                self.assertEqual(_codes(_said("API_TOKEN", value)), [])


if __name__ == "__main__":
    unittest.main()
