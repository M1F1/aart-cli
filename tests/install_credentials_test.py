"""CP-30 step 8, CP-45 step 6: screen 07b lists each secret once per artifact (§172.6, D-487).

Nothing is typed on 07b. Enter marks a credential for the credential store to ask while installing,
and the store's own prompt takes it on the lent terminal, once per installation, so no value passes
through aart-cli. The screen, the state and every frame know only which rows are marked; leaving
before Ready forgets that, and whatever was not marked is stored as `AART_NOT_SET`.
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
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import ConsumerScreen, ConsumerSession
from aart_cli.domain.inputs import SKIPPED_INPUT
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.consumer_application_e2e_test import BothBackendsMeasured, _actions, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, ESCAPE, INSTALL_CUSTOM, RIGHT, SPACE, UP
from tests.credential_guidance_test import _Journal
from tests.install_time_config_form_test import _MemoryCredentialProvider

ROW = "company/mcp/github\tgithub-token"


class _Keeping(_MemoryCredentialProvider):
    """The memory provider, recording what each store was handed, and each store it asked for.

    A store with no carrier is the provider's own prompt: the person types into it, and the fake
    records only that it asked.
    """

    def __init__(self) -> None:
        super().__init__()
        self.handed: list[str] = []
        self.prompted: list[str] = []

    def store(self, reference, secret=None, *, replace: bool = False):
        if secret is None:
            self.prompted.append(self._address(reference))
        else:
            self.handed.append(secret.consume())
        self.stored.add(self._address(reference))
        return self.inspect(reference)


def _install(*keys):
    """Into opencode and tabnine, the field answered, 05 and 07a passed, then `keys` on 07b."""

    journal = _Journal()
    provider = _Keeping()
    with _environment(authored=AUTHORED_MCP) as env:
        base = _actions(env)
        handler = type(base)(
            replace(base._context, credential_providers=(provider,)),  # noqa: SLF001
            terminal_handover=journal.handover,
        )
        finished, terminal, _ = _drive(
            env,
            _at(ConsumerScreen.MARKETPLACE),
            SPACE,
            *INSTALL_CUSTOM,
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
    return finished, terminal, provider, journal, handler


class AskedWhileInstallingE2ETest(BothBackendsMeasured):
    def test_a_marked_credential_is_asked_by_the_store_for_each_installation(self) -> None:
        finished, terminal, provider, journal, handler = _install(ENTER, DOWN, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        # Marked once for the artifact, asked by the store in each installation's own item.
        self.assertEqual(len(provider.prompted), 2)
        self.assertEqual(len(set(provider.prompted)), 2)
        self.assertEqual(provider.handed, [])
        # The terminal was lent for each prompt and taken back, after the credential's briefing.
        self.assertEqual(len(journal.briefings), 2)
        self.assertEqual(journal.entries[-1], "restored")
        for briefing in journal.briefings:
            self.assertIn("test-keychain asks for it next", "\n".join(briefing))
        self.assertTrue(terminal.screen_containing("github-token): asked when installing"))
        ready = terminal.screen_containing("ready to install")
        self.assertIn("the credential store asks you for each of these", ready)
        self.assertIn("company/mcp/github: github-token", ready)
        self.assertNotIn(SKIPPED_INPUT, ready)
        self.assertEqual(handler._asked_rows, set())  # noqa: SLF001

    def test_set_later_stores_the_placeholder_and_never_prompts(self) -> None:
        # 07b opens on the credential; Set later is the row above it.
        finished, terminal, provider, journal, _ = _install(UP, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(provider.prompted, [])
        self.assertEqual(journal.briefings, [])
        self.assertEqual(provider.handed, [SKIPPED_INPUT, SKIPPED_INPUT])

    def test_marking_twice_unmarks_and_the_placeholder_is_stored(self) -> None:
        finished, terminal, provider, journal, _ = _install(ENTER, ENTER, DOWN, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(provider.prompted, [])
        self.assertEqual(journal.briefings, [])
        self.assertEqual(provider.handed, [SKIPPED_INPUT, SKIPPED_INPUT])
        self.assertIn("company/mcp/github: github-token", terminal.screen_containing("ready to"))

    def test_set_later_after_marking_asks_for_nothing(self) -> None:
        finished, terminal, provider, journal, _ = _install(ENTER, UP, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(provider.prompted, [])
        self.assertEqual(journal.briefings, [])
        self.assertEqual(provider.handed, [SKIPPED_INPUT, SKIPPED_INPUT])
        self.assertNotIn("the credential store asks", terminal.screen_containing("ready to"))

    def test_leaving_07b_forgets_what_was_marked(self) -> None:
        finished, terminal, provider, _, handler = _install(ENTER, ESCAPE, ord("q"))

        self.assertNotIn(finished.session.screen, (ConsumerScreen.SUCCESS,), terminal.last)
        self.assertEqual(handler._asked_rows, set())  # noqa: SLF001
        self.assertEqual((provider.handed, provider.prompted), ([], []))


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
    def test_the_footer_says_what_enter_does_to_the_row(self) -> None:
        def offered(state: ConsumerUiState) -> list[str]:
            return [item.label for item in key_bindings(state) if item.key == "Enter"]

        self.assertEqual(offered(_on_07b()), ["Ask when installing"])
        self.assertEqual(offered(_on_07b(asked_secrets=(ROW,))), ["Don't ask"])

    def test_enter_on_a_secret_row_asks_the_adapter_for_that_row(self) -> None:
        state = _on_07b()
        event = key_event("enter", state)
        assert event is not None

        _, commands = reduce_consumer_ui(state, event)

        self.assertEqual(
            [(item.kind, item.focus) for item in commands],
            [(ConsumerUiCommandKind.ASK_SECRET, ROW)],
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
        marked, _ = reduce_consumer_ui(
            _on_07b(),
            ConsumerUiEvent(
                ConsumerUiEventKind.SECRET_ASKED,
                action=ConsumerActionKind.INSTALL,
                key=ROW,
                accepted=True,
            ),
        )
        self.assertEqual(marked.asked_secrets, (ROW,))
        withdrawn, _ = reduce_consumer_ui(
            marked,
            ConsumerUiEvent(
                ConsumerUiEventKind.SECRET_ASKED,
                action=ConsumerActionKind.INSTALL,
                key=ROW,
                accepted=False,
            ),
        )
        self.assertEqual(withdrawn.asked_secrets, ())

    def test_backing_out_of_07b_discards_and_ready_keeps(self) -> None:
        held = _on_07b(
            asked_secrets=(ROW,),
            session=ConsumerSession(
                ConsumerScreen.INSTALL_CREDENTIALS,
                history=(ConsumerScreen.INSTALL_SCOPE,),
                review_digest="sha256:" + "1" * 64,
            ),
        )

        back, commands = reduce_consumer_ui(held, ConsumerUiEvent(ConsumerUiEventKind.BACK))

        self.assertIs(back.session.screen, ConsumerScreen.INSTALL_SCOPE)
        self.assertEqual(back.asked_secrets, ())
        self.assertIn(ConsumerUiCommandKind.DISCARD_SECRETS, [item.kind for item in commands])
        ready, kept = reduce_consumer_ui(
            held,
            ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.READY),
        )
        self.assertIs(ready.session.screen, ConsumerScreen.READY)
        self.assertEqual(ready.asked_secrets, (ROW,))
        self.assertNotIn(ConsumerUiCommandKind.DISCARD_SECRETS, [item.kind for item in kept])


if __name__ == "__main__":
    unittest.main()
