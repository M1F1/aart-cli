"""CP-30 step 9: what a skip left as `AART_NOT_SET` is said, before and after it is stored (§172.3).

Ready lists every input that will be stored as the placeholder. Once installed, Doctor, Installed
and Credentials and variables warn about each one. An ordinary value is compared as text; a secret
is compared by the provider in its own processes and only the answer comes back (D-421), so no
secret value is read to give the warning.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_views import (
    PLACEHOLDER_WARNING,
    ConfigurationFileView,
    ConsumerScreen,
)
from aart_cli.domain.inputs import SKIPPED_INPUT
from aart_cli.domain.result import Ok
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.consumer_application_e2e_test import BothBackendsMeasured, _actions, _at, _drive
from tests.consumer_shell_test import BACKSPACE, DOWN, ENTER, INSTALL_CUSTOM, RIGHT, SPACE, UP
from tests.install_credentials_test import _Keeping

_TO_FORM = (SPACE, *INSTALL_CUSTOM, RIGHT, SPACE, RIGHT, SPACE, ENTER)
#: 07: the declared default cleared, then Set later; 07a passed; 07b: Set later.
_SKIP_ALL = (*_TO_FORM, *((BACKSPACE,) * len("acme")), UP, ENTER, ENTER, ENTER, UP, ENTER)
#: 07 answered; 07a passed; 07b: the credential entered, then Continue.
_ANSWER_ALL = (*_TO_FORM, "platform-team", ENTER, ENTER, ENTER, ENTER, ENTER, DOWN, ENTER)


class _Comparing(_Keeping):
    """Answers `placeholder` the way a provider does: about what it holds, never with it."""

    def __init__(self) -> None:
        super().__init__()
        self.placeholders: set[str] = set()

    def store(self, reference, secret=None, *, replace: bool = False):
        if secret is not None:
            held = secret.consume()
            self.handed.append(held)
            if held == SKIPPED_INPUT:
                self.placeholders.add(self._address(reference))
        self.stored.add(self._address(reference))
        return self.inspect(reference)

    def inspect(self, reference):
        observed = super().inspect(reference).value
        return Ok(replace(observed, placeholder=self._address(reference) in self.placeholders))


def _installed(keys):
    """Install with `keys`, then open Doctor, Installed details, 22 and 22a on the same machine."""

    provider = _Comparing()
    with _environment(authored=AUTHORED_MCP) as env:
        base = _actions(env)
        handler = type(base)(
            replace(base._context, credential_providers=(provider,)),  # noqa: SLF001
            secret_reader=lambda prompt: "typed-on-07b",
        )
        finished, install, _ = _drive(
            env, _at(ConsumerScreen.MARKETPLACE), *keys, ENTER, actions=handler
        )
        assert finished.session.screen is ConsumerScreen.SUCCESS, install.last
        drawn = {}
        for screen in (ConsumerScreen.DOCTOR, ConsumerScreen.INSTALLED, ConsumerScreen.CREDENTIALS):
            _, terminal, _ = _drive(env, _at(screen), ENTER, actions=handler)
            drawn[screen] = terminal.frames
    return install, drawn


def _text(frames) -> str:
    return "\n\n".join("\n".join(frame) for frame in frames)


class ReadyListsWhatWillBePlaceholderE2ETest(BothBackendsMeasured):
    def test_a_skipped_value_and_an_unentered_secret_are_listed_before_confirming(self) -> None:
        install, _ = _installed(_SKIP_ALL)

        ready = install.screen_containing("ready to install")
        self.assertIn(f"as {SKIPPED_INPUT}, to set later in Credentials and variables:", ready)
        self.assertIn("company/mcp/github: github-org", ready)
        self.assertIn("company/mcp/github: github-token", ready)

    def test_nothing_is_listed_when_everything_was_answered(self) -> None:
        install, _ = _installed(_ANSWER_ALL)

        ready = install.screen_containing("ready to install")
        self.assertTrue(ready)
        self.assertNotIn(SKIPPED_INPUT, ready)


class InstalledPlaceholdersWarnE2ETest(BothBackendsMeasured):
    def test_doctor_installed_and_credentials_warn_about_each_placeholder(self) -> None:
        _, drawn = _installed(_SKIP_ALL)

        doctor = _text(drawn[ConsumerScreen.DOCTOR])
        for harness in ("opencode", "tabnine"):
            self.assertIn(f"⚠ company/mcp/github@1.5.0 · {harness} · project", doctor)
        self.assertIn(f"github-org: {PLACEHOLDER_WARNING}", doctor)
        self.assertIn(f"github-token: {PLACEHOLDER_WARNING}", doctor)
        self.assertIn(f"2 still hold {SKIPPED_INPUT}", doctor)

        details = _text(drawn[ConsumerScreen.INSTALLED])
        self.assertIn(f"github-org: {PLACEHOLDER_WARNING}.", details)
        self.assertIn(f"github-token: {PLACEHOLDER_WARNING}.", details)

        inputs = _text(drawn[ConsumerScreen.CREDENTIALS])
        self.assertIn(f"    github-org: {PLACEHOLDER_WARNING}", inputs)
        # 22a: under the value, and in place of "Configured securely" for the credential.
        self.assertIn(f"      {PLACEHOLDER_WARNING}", inputs)
        self.assertIn(f"  github-token: {PLACEHOLDER_WARNING}", inputs)

    def test_nothing_warns_once_every_input_was_answered(self) -> None:
        _, drawn = _installed(_ANSWER_ALL)

        for screen, frames in drawn.items():
            with self.subTest(screen=screen):
                self.assertNotIn(PLACEHOLDER_WARNING, _text(frames))
        self.assertIn("Configured securely", _text(drawn[ConsumerScreen.CREDENTIALS]))
        self.assertNotIn("still hold", _text(drawn[ConsumerScreen.DOCTOR]))


class ConfigurationPlaceholdersTest(unittest.TestCase):
    def test_only_a_value_that_is_exactly_the_placeholder_is_one(self) -> None:
        file = ConfigurationFileView(
            "company/mcp/github@1.5.0",
            "opencode",
            "/x/opencode.conf",
            "matched",
            values=(
                ("org", SKIPPED_INPUT),
                ("team", f"{SKIPPED_INPUT} "),
                ("project", SKIPPED_INPUT.lower()),
                ("region", "eu"),
            ),
        )

        self.assertEqual(file.placeholders, ("org",))


if __name__ == "__main__":
    unittest.main()
