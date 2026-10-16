"""CP-30 step 8: screen 07b asks each secret once per artifact, before Ready (§172.6, D-419).

What is typed goes through a hidden prompt on the lent terminal into one single-use carrier per
installation. The screen, the state and every frame only know that something was entered; leaving
before Ready forgets it, and whatever was not entered is stored as `AART_NOT_SET`.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    CONFIG_CONTINUE_ROW,
    CONFIG_SET_LATER_ROW,
    ConsumerActionKind,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.domain.inputs import SKIPPED_INPUT
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, ESCAPE, RIGHT, SPACE, UP
from tests.credential_guidance_test import _Journal
from tests.install_time_config_form_test import _MemoryCredentialProvider

#: What the hidden prompt answers in these tests. Not credential-shaped on purpose: it is a marker
#: to look for in frames and files, and the secret-shape gate has nothing to say about it.
TYPED = "typed-on-07b"
ROW = "company/mcp/github\tgithub-token"


class _Keeping(_MemoryCredentialProvider):
    """The memory provider, recording what each store was handed instead of refusing a value."""

    def __init__(self) -> None:
        super().__init__()
        self.handed: list[str] = []

    def store(self, reference, secret=None, *, replace: bool = False):
        if secret is not None:
            self.handed.append(secret.consume())
        self.stored.add(self._address(reference))
        return self.inspect(reference)


def _install(*keys, answer: str = TYPED):
    """Into opencode and tabnine, the field answered, 05 and 07a passed, then `keys` on 07b."""

    asked: list[str] = []

    def reader(prompt: str) -> str:
        asked.append(prompt)
        return answer

    journal = _Journal()
    provider = _Keeping()
    with _environment(authored=AUTHORED_MCP) as env:
        base = _actions(env)
        handler = type(base)(
            replace(base._context, credential_providers=(provider,)),  # noqa: SLF001
            terminal_handover=journal.handover,
            secret_reader=reader,
        )
        finished, terminal, _ = _drive(
            env,
            _at(ConsumerScreen.MARKETPLACE),
            SPACE,
            ord("i"),
            RIGHT,
            SPACE,
            RIGHT,
            SPACE,
            ENTER,
            "platform-team",
            ENTER,
            ENTER,
            ENTER,
            ENTER,
            *keys,
            actions=handler,
        )
        files = [
            path.read_text(encoding="utf-8", errors="replace")
            for path in (env.project, env.paths.data_root)
            for path in __import__("pathlib").Path(path).rglob("*")
            if path.is_file()
        ]
    return finished, terminal, provider, journal, asked, handler, files


class EnteredBeforeReadyE2ETest(unittest.TestCase):
    def test_an_entered_value_reaches_the_provider_for_each_installation_and_nowhere_else(
        self,
    ) -> None:
        finished, terminal, provider, journal, asked, handler, files = _install(
            ENTER, DOWN, ENTER, ENTER
        )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        # Asked once for the artifact, written into both installations (§172.6, INV-259).
        self.assertEqual(len(asked), 1)
        self.assertEqual(provider.handed, [TYPED, TYPED])
        self.assertEqual(len(provider.stored), 2)
        # The terminal was lent for the prompt and taken back, with a briefing that says where
        # the value goes and that nothing is echoed.
        self.assertEqual(journal.entries[-1], "restored")
        (briefing,) = journal.briefings
        said = "\n".join(briefing)
        self.assertIn("each of these 2 installations", said)
        self.assertIn("nothing is shown", said)
        self.assertTrue(terminal.screen_containing("github-token): entered, hidden"))
        for drawn in terminal.frames:
            self.assertNotIn(TYPED, "\n".join(drawn))
        self.assertEqual([text for text in files if TYPED in text], [])
        self.assertEqual(handler._entered_secrets, {})  # noqa: SLF001

    def test_set_later_stores_the_placeholder_and_never_prompts(self) -> None:
        # 07b opens on the credential; Set later is the row above it.
        finished, terminal, provider, journal, asked, _, _ = _install(UP, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(asked, [])
        self.assertEqual(journal.briefings, [])
        self.assertEqual(provider.handed, [SKIPPED_INPUT, SKIPPED_INPUT])

    def test_an_empty_answer_is_not_an_entry(self) -> None:
        finished, terminal, provider, _, asked, _, _ = _install(
            ENTER, DOWN, ENTER, ENTER, answer=""
        )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(len(asked), 1)
        self.assertFalse(terminal.screen_containing("entered, hidden"))
        self.assertEqual(provider.handed, [SKIPPED_INPUT, SKIPPED_INPUT])

    def test_leaving_07b_forgets_what_was_entered(self) -> None:
        finished, terminal, provider, _, asked, handler, _ = _install(ENTER, ESCAPE, ord("q"))

        self.assertEqual(len(asked), 1)
        self.assertNotIn(finished.session.screen, (ConsumerScreen.SUCCESS,), terminal.last)
        self.assertEqual(handler._entered_secrets, {})  # noqa: SLF001
        self.assertEqual(provider.handed, [])


def _on_07b(**changes) -> ConsumerUiState:
    return replace(
        ConsumerUiState(
            ConsumerSession(ConsumerScreen.INSTALL_CREDENTIALS, review_digest="sha256:" + "1" * 64),
            action=ConsumerActionKind.INSTALL,
            rows=(CONFIG_SET_LATER_ROW, ROW, CONFIG_CONTINUE_ROW),
            cursor=1,
        ),
        **changes,
    )


class TheReducerHoldsOnlyRowsTest(unittest.TestCase):
    def test_enter_on_a_secret_row_asks_the_adapter_for_that_row(self) -> None:
        state = _on_07b()
        event = key_event("enter", state)
        assert event is not None

        _, commands = reduce_consumer_ui(state, event)

        self.assertEqual(
            [(item.kind, item.focus) for item in commands],
            [(ConsumerUiCommandKind.ENTER_SECRET, ROW)],
        )

    def test_only_a_shown_secret_row_on_07b_is_asked(self) -> None:
        for state, key in (
            (_on_07b(), CONFIG_SET_LATER_ROW),
            (_on_07b(), CONFIG_CONTINUE_ROW),
            (_on_07b(), "company/mcp/other\tgithub-token"),
            (_on_07b(session=ConsumerSession(ConsumerScreen.READY)), ROW),
        ):
            _, commands = reduce_consumer_ui(
                state, ConsumerUiEvent(ConsumerUiEventKind.REQUEST_SECRET, key=key)
            )
            self.assertEqual(commands, (), key)

    def test_the_answer_marks_the_row_and_a_refusal_unmarks_it(self) -> None:
        entered, _ = reduce_consumer_ui(
            _on_07b(),
            ConsumerUiEvent(
                ConsumerUiEventKind.SECRET_ENTERED,
                action=ConsumerActionKind.INSTALL,
                key=ROW,
                accepted=True,
            ),
        )
        self.assertEqual(entered.entered_secrets, (ROW,))
        withdrawn, _ = reduce_consumer_ui(
            entered,
            ConsumerUiEvent(
                ConsumerUiEventKind.SECRET_ENTERED,
                action=ConsumerActionKind.INSTALL,
                key=ROW,
                accepted=False,
            ),
        )
        self.assertEqual(withdrawn.entered_secrets, ())

    def test_backing_out_of_07b_discards_and_ready_keeps(self) -> None:
        held = _on_07b(
            entered_secrets=(ROW,),
            session=ConsumerSession(
                ConsumerScreen.INSTALL_CREDENTIALS,
                history=(ConsumerScreen.INSTALL_SCOPE,),
                review_digest="sha256:" + "1" * 64,
            ),
        )

        back, commands = reduce_consumer_ui(held, ConsumerUiEvent(ConsumerUiEventKind.BACK))

        self.assertIs(back.session.screen, ConsumerScreen.INSTALL_SCOPE)
        self.assertEqual(back.entered_secrets, ())
        self.assertIn(ConsumerUiCommandKind.DISCARD_SECRETS, [item.kind for item in commands])
        ready, kept = reduce_consumer_ui(
            held,
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.READY),
        )
        self.assertIs(ready.session.screen, ConsumerScreen.READY)
        self.assertEqual(ready.entered_secrets, (ROW,))
        self.assertNotIn(ConsumerUiCommandKind.DISCARD_SECRETS, [item.kind for item in kept])


if __name__ == "__main__":
    unittest.main()
