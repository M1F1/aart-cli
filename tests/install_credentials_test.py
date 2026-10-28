"""CP-45 step 6, CP-46 step 8: screen 07b lists each secret once per artifact (§172.6, §207).

Nothing is typed into aart-cli. Enter on a 07b row lends the terminal to the credential store's own
prompt, there and then, once per installation the row reaches, and the macOS dialog only when the
prompt cut the value (§204). Storing changes the machine the review measured, so the install is
prepared again. What was entered is deleted when the install is abandoned or fails, and whatever
was not entered is stored as `AART_NOT_SET`.
"""

from __future__ import annotations

import contextlib
import unittest
from dataclasses import replace
from unittest import mock

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
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.inputs import SKIPPED_INPUT
from aart_cli.domain.inspection import RemediationCapability, RemediationCapabilityKind
from aart_cli.domain.result import Err, Ok
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.consumer_application_e2e_test import BothBackendsMeasured, _actions, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, ESCAPE, INSTALL_CUSTOM, RIGHT, SPACE, UP
from tests.credential_guidance_test import _Journal
from tests.install_time_config_form_test import _MemoryCredentialProvider

ROW = "company/mcp/github\tgithub-token"


class _Keeping(_MemoryCredentialProvider):
    """The memory provider, recording what each store was handed, asked for and deleted.

    A store with no carrier is the provider's own prompt: the person types into it, and the fake
    records only that it asked. `cancelled` makes that prompt come back with nothing stored, and
    `clipped` makes every stored item measure as the 128 bytes the macOS prompt keeps. An item
    whose address names `held_before` was stored by somebody before this review began.
    """

    def __init__(
        self, *, cancelled: bool = False, clipped: bool = False, held_before: str = ""
    ) -> None:
        super().__init__()
        self.handed: list[str] = []
        self.prompted: list[str] = []
        self.replacing: list[bool] = []
        self.deleted: list[str] = []
        self.cancelled = cancelled
        self.clipped = clipped
        self.held_before = held_before
        self._seen: set[str] = set()

    def store(self, reference, secret=None, *, replace: bool = False):
        if secret is None:
            self.prompted.append(self._address(reference))
            self.replacing.append(replace)
            if self.cancelled:
                return Err((Diagnostic(_CANCELLED, Severity.ERROR, "the prompt was cancelled"),))
        else:
            self.handed.append(secret.consume())
        self.stored.add(self._address(reference))
        return self.inspect(reference)

    def inspect(self, reference):
        address = self._address(reference)
        if self.held_before and self.held_before in address and address not in self._seen:
            self.stored.add(address)
        self._seen.add(address)
        observed = super().inspect(reference)
        if not self.clipped or not self.holds(reference):
            return observed
        return Ok(replace(observed.value, length=128, clipped=True))

    def delete(self, reference):
        self.deleted.append(self._address(reference))
        return super().delete(reference)


_CANCELLED = DiagnosticCode("test-prompt-cancelled")


def _install(*keys, provider: _Keeping | None = None, completed=None, after=None, scope=()):
    """Into opencode and tabnine: 05 and 07a passed, the field answered on 07, then `keys` on 07b.

    `completed`, when given, stands in for the install itself, so it can fail. `after`, when given,
    is called with the environment and the handler before the machine is thrown away. `scope` is
    pressed on 07a before going on to 07.
    """

    journal = _Journal()
    provider = provider or _Keeping()
    with _environment(authored=AUTHORED_MCP) as env:
        base = _actions(env)
        handler = type(base)(
            replace(base._context, credential_providers=(provider,)),  # noqa: SLF001
            terminal_handover=journal.handover,
        )
        patched = (
            mock.patch("aart_cli.consumer_actions.complete_configured_installation", completed)
            if completed is not None
            else contextlib.nullcontext()
        )
        with patched:
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
                *scope,
                ENTER,
                "platform-team",
                ENTER,
                ENTER,
                ENTER,
                *keys,
                actions=handler,
            )
        if after is not None:
            after(env, handler)
    return finished, terminal, provider, journal, handler


def _first(terminal, needle: str) -> int:
    """The index of the first frame saying `needle`, or the number of frames."""

    return next(
        (index for index, frame in enumerate(terminal.frames) if needle in "\n".join(frame)),
        len(terminal.frames),
    )


def _failed_install(*_args, **_kwargs):
    return Err((Diagnostic(_CANCELLED, Severity.ERROR, "the install stopped half-way"),))


class ScopeComesBeforeConfigurationE2ETest(BothBackendsMeasured):
    """§209: where each installation goes is chosen before what it is told and what it holds."""

    def test_05_then_07a_then_07_then_07b(self) -> None:
        finished, terminal, _, _, _ = _install()

        self.assertIs(finished.session.screen, ConsumerScreen.INSTALL_CREDENTIALS, terminal.last)
        scope = _first(terminal, "Review Selection / Scope")
        form = _first(terminal, "Scope / Required Inputs")
        credentials = _first(terminal, "github-token): not set")
        self.assertLess(scope, form)
        self.assertLess(form, credentials)
        # 07a opens on where each installation would go, before any plan exists to say so.
        self.assertIn("company/mcp/github → opencode   (*)", "\n".join(terminal.frames[scope]))
        self.assertLess(credentials, len(terminal.frames))

    def test_a_scope_chosen_before_the_form_is_the_one_installed(self) -> None:
        finished, terminal, provider, _, _ = _install(
            ENTER, DOWN, ENTER, ENTER, scope=(RIGHT, SPACE)
        )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        # The form was still asked after the scope was prepared again, and it was answered.
        self.assertNotIn(SKIPPED_INPUT, terminal.screen_containing("ready to install"))
        # The credentials were entered for the installations in that scope.
        self.assertEqual(len(provider.prompted), 2)
        self.assertTrue(all("user" in item for item in provider.prompted), provider.prompted)

    def test_07_goes_on_to_07b_without_asking_the_scope_again(self) -> None:
        """With one Python installer there is nothing left on 05, so 07 leads straight on."""

        only_pip = (RemediationCapability(RemediationCapabilityKind.PYTHON_INSTALLER, "pip"),)
        with (
            mock.patch(
                "aart_cli.io.configured_installation_action.observe_python_installers",
                return_value=only_pip,
            ),
            _environment(authored=AUTHORED_MCP) as env,
        ):
            # A stand-in store, so 07b has rows wherever this runs: Linux has no Keychain.
            base = _actions(env)
            handler = type(base)(
                replace(base._context, credential_providers=(_Keeping(),))  # noqa: SLF001
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
                ENTER,
                "platform-team",
                ENTER,
                ENTER,
                ESCAPE,
                actions=handler,
            )

        submitted = _first(terminal, "github-token): not set")
        self.assertLess(submitted, len(terminal.frames), terminal.last)
        self.assertFalse(
            any(frame[0].endswith("/ Scope") for frame in terminal.frames[submitted:]),
            "07a was asked again after 07",
        )

    def test_what_was_typed_survives_going_back_to_choose_another_scope(self) -> None:
        with _environment(authored=AUTHORED_MCP) as env:
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
                ENTER,
                "platform-team",
                ESCAPE,
                RIGHT,
                SPACE,
                ENTER,
                # Out of the form again, so the shell can be left.
                ESCAPE,
                actions=_actions(env),
            )

        self.assertIs(finished.session.screen, ConsumerScreen.INSTALL_SCOPE, terminal.last)
        self.assertTrue(all(item.endswith("user") for item in finished.pair_scopes), finished)
        # The form opened again after the scope was prepared anew, still holding what was typed.
        last_form = next(
            frame for frame in reversed(terminal.frames) if "/ Required Inputs" in frame[0]
        )
        self.assertIn("[platform-team]", "\n".join(last_form))
        chosen = next(
            index
            for index, frame in enumerate(terminal.frames)
            if "/ Scope" in frame[0] and "(*)       ( )" not in "\n".join(frame)
        )
        self.assertLess(chosen, terminal.frames.index(last_form))


class EnteredOn07bE2ETest(BothBackendsMeasured):
    def test_enter_on_07b_lets_the_store_ask_there_and_the_install_asks_nothing(self) -> None:
        finished, terminal, provider, journal, handler = _install(ENTER, DOWN, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        # Entered once for the artifact, asked by the store in each installation's own item.
        self.assertEqual(len(provider.prompted), 2)
        self.assertEqual(len(set(provider.prompted)), 2)
        # Both were stored before the install, so it had no placeholder to store and asked nothing.
        self.assertEqual(provider.handed, [])
        self.assertEqual(provider.deleted, [])
        self.assertEqual(provider.stored, set(provider.prompted))
        self.assertEqual(len(journal.briefings), 2)
        self.assertEqual(journal.entries[-1], "restored")
        for briefing in journal.briefings:
            self.assertIn("test-keychain asks for it next", "\n".join(briefing))
        # The store asked on 07b, before Ready was even drawn.
        self.assertLess(_first(terminal, "github-token): stored"), _first(terminal, "/ Ready"))
        ready = terminal.screen_containing("ready to install")
        self.assertIn("stored by the credential store on the previous screen", ready)
        self.assertIn("company/mcp/github: github-token", ready)
        self.assertNotIn(SKIPPED_INPUT, ready)
        self.assertEqual(handler._entered, {})  # noqa: SLF001

    def test_set_later_stores_the_placeholder_and_never_prompts(self) -> None:
        # 07b opens on the credential; Set later is the row above it.
        finished, terminal, provider, journal, _ = _install(UP, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(provider.prompted, [])
        self.assertEqual(journal.briefings, [])
        self.assertEqual(provider.handed, [SKIPPED_INPUT, SKIPPED_INPUT])

    def test_enter_again_asks_the_store_again(self) -> None:
        finished, terminal, provider, journal, _ = _install(ENTER, ENTER, DOWN, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(len(provider.prompted), 4)
        self.assertEqual(len(journal.briefings), 4)
        self.assertEqual((provider.handed, provider.deleted), ([], []))
        # The second time the items exist, so the store is asked to replace them, not add them.
        self.assertEqual(provider.replacing, [False, False, True, True])

    def test_an_item_stored_before_this_review_is_left_alone(self) -> None:
        provider = _Keeping(held_before="opencode")
        finished, terminal, _, journal, _ = _install(ENTER, DOWN, ENTER, ENTER, provider=provider)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        # Only tabnine's item was asked for; opencode's was somebody's already, and stays theirs.
        self.assertEqual(len(provider.prompted), 1)
        self.assertNotIn("opencode", provider.prompted[0])
        self.assertEqual(len(journal.briefings), 1)
        self.assertEqual((provider.handed, provider.deleted), ([], []))

    def test_set_later_after_entering_keeps_what_was_entered(self) -> None:
        finished, terminal, provider, _, _ = _install(ENTER, UP, ENTER, ENTER)

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(len(provider.prompted), 2)
        self.assertEqual((provider.handed, provider.deleted), ([], []))
        self.assertEqual(provider.stored, set(provider.prompted))

    def test_leaving_07b_deletes_what_was_entered(self) -> None:
        finished, terminal, provider, _, handler = _install(ENTER, ESCAPE, ord("q"))

        self.assertIsNot(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertEqual(len(provider.prompted), 2)
        self.assertEqual(sorted(provider.deleted), sorted(provider.prompted))
        self.assertEqual(provider.stored, set())
        self.assertEqual(handler._entered, {})  # noqa: SLF001

    def test_quitting_from_ready_deletes_what_was_entered(self) -> None:
        finished, terminal, provider, _, _ = _install(ENTER, DOWN, ENTER, ord("q"))

        self.assertTrue(finished.exited, terminal.last)
        self.assertEqual(len(provider.prompted), 2)
        self.assertEqual(sorted(provider.deleted), sorted(provider.prompted))
        self.assertEqual(provider.stored, set())

    def test_a_failed_install_deletes_what_was_entered(self) -> None:
        finished, terminal, provider, _, handler = _install(
            ENTER, DOWN, ENTER, ENTER, completed=_failed_install
        )

        self.assertIsNot(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertTrue(terminal.screen_containing("the install stopped half-way"), terminal.last)
        self.assertEqual(sorted(provider.deleted), sorted(provider.prompted))
        self.assertEqual(provider.stored, set())
        self.assertEqual(handler._entered, {})  # noqa: SLF001

    def test_a_cancelled_prompt_stores_nothing_and_says_so(self) -> None:
        finished, terminal, provider, _, _ = _install(
            ENTER, DOWN, ENTER, ENTER, provider=_Keeping(cancelled=True)
        )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertTrue(terminal.screen_containing("the prompt was cancelled"), terminal.last)
        self.assertTrue(terminal.screen_containing("github-token): not set"))
        # Not stored on 07b, so the install stores the placeholder as for any secret not entered.
        self.assertEqual(provider.handed, [SKIPPED_INPUT, SKIPPED_INPUT])

    def test_a_value_still_cut_is_deleted_and_the_reason_said(self) -> None:
        finished, terminal, provider, _, _ = _install(
            ENTER, DOWN, ENTER, ENTER, provider=_Keeping(clipped=True)
        )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertTrue(terminal.screen_containing("exactly 128 characters"), terminal.last)
        self.assertTrue(terminal.screen_containing("github-token): not set"))
        self.assertEqual(sorted(provider.deleted), sorted(set(provider.prompted)))


class UninstallDeletesTheInstallationsCredentialsE2ETest(BothBackendsMeasured):
    """§208: a removed installation takes its own credential items with it, and nobody else's."""

    def test_uninstalling_one_installation_deletes_its_items_and_keeps_the_others(self) -> None:
        removed: list[ConsumerUiState] = []

        def uninstall_opencode(env, handler) -> None:
            row = next(
                item.row
                for item in handler.source().screens.installed
                if item.harness == "opencode"
            )
            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus=row),
                ord("u"),
                ENTER,
                actions=handler,
            )
            review = terminal.screen_containing("Confirm to apply this exact reviewed plan")
            # The review says the credential goes, before anything is confirmed.
            self.assertIn("credential:github-token", review, terminal.last)
            self.assertIn("credential mutation", review)
            removed.append(finished)

        finished, terminal, provider, _, _ = _install(
            ENTER, DOWN, ENTER, ENTER, after=uninstall_opencode
        )

        self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
        self.assertIs(removed[0].session.screen, ConsumerScreen.ACTIVITY_DETAILS)
        opencode = [item for item in provider.prompted if "opencode" in item]
        tabnine = [item for item in provider.prompted if "tabnine" in item]
        self.assertEqual((len(opencode), len(tabnine)), (1, 1))
        self.assertEqual(provider.deleted, opencode)
        self.assertEqual(provider.stored, set(tabnine))

    def test_a_placeholder_leaves_with_its_installation_too(self) -> None:
        def uninstall_everything(env, handler) -> None:
            for item in handler.source().screens.installed:
                _drive(
                    env,
                    _at(ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, focus=item.row),
                    ord("u"),
                    ENTER,
                    actions=handler,
                )

        _, _, provider, _, _ = _install(UP, ENTER, ENTER, after=uninstall_everything)

        self.assertEqual(provider.handed, [SKIPPED_INPUT, SKIPPED_INPUT])
        self.assertEqual(len(provider.deleted), 2)
        self.assertEqual(provider.stored, set())


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

        self.assertEqual(offered(_on_07b()), ["Enter value"])
        self.assertEqual(offered(_on_07b(asked_secrets=(ROW,))), ["Enter again"])

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

    def test_a_stored_answer_carries_the_review_prepared_again(self) -> None:
        digest = "sha256:" + "2" * 64
        stored, _ = reduce_consumer_ui(
            _on_07b(),
            ConsumerUiEvent(
                ConsumerUiEventKind.SECRET_ASKED,
                action=ConsumerActionKind.INSTALL,
                key=ROW,
                accepted=True,
                semantic_identity="sha256:" + "3" * 64,
                selection_identity="sha256:" + "4" * 64,
                review_digest=digest,
            ),
        )
        self.assertEqual(stored.session.review_digest, digest)
        self.assertEqual(stored.session.semantic_identity, "sha256:" + "3" * 64)
        refused, _ = reduce_consumer_ui(
            _on_07b(),
            ConsumerUiEvent(
                ConsumerUiEventKind.SECRET_ASKED,
                action=ConsumerActionKind.INSTALL,
                key=ROW,
                accepted=False,
            ),
        )
        self.assertEqual(refused.session.review_digest, "sha256:" + "1" * 64)

    def test_set_later_keeps_what_was_entered(self) -> None:
        held = _on_07b(asked_secrets=(ROW,), cursor=0)

        later, commands = reduce_consumer_ui(
            held, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.READY)
        )

        self.assertIs(later.session.screen, ConsumerScreen.READY)
        self.assertEqual(later.asked_secrets, (ROW,))
        self.assertNotIn(ConsumerUiCommandKind.DISCARD_SECRETS, [item.kind for item in commands])

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
