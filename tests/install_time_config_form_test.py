"""CP-23 task 16.2: screen 07 collects ordinary configuration before review."""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    CONFIG_CONTINUE_ROW,
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    InstallationConfigDraft,
    InstallationConfigField,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConfigInputView,
    ConsumerScreen,
    ConsumerSession,
    CredentialInputView,
)
from aart_cli.domain.credentials import (
    CredentialObservation,
    CredentialState,
    ProviderState,
)
from aart_cli.domain.inputs import InputValidation, PromptedConfigValue
from aart_cli.domain.result import Ok
from aart_cli.tui_consumer import CanonicalScreenSource, compose_frame, frame
from tests.artifact_installation_e2e_test import ORG
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import DOWN, ENTER, SPACE, screens
from tests.credential_fixtures import access_token


def _config_view() -> ConfigInputView:
    return ConfigInputView(
        "organization",
        "GitHub organization",
        True,
        "environment",
        "process",
        "Organization used for GitHub requests.",
        "platform-team",
        None,
        None,
        "letters, digits and dashes",
        "acme",
        None,
        False,
        None,
        InputValidation("identifier"),
    )


def _credential_view() -> CredentialInputView:
    return CredentialInputView(
        "github-token",
        "GitHub token",
        True,
        "environment",
        "process",
        "Token used for GitHub requests.",
        "opaque token",
        ("GitHub settings", "https://github.example.test/settings/tokens"),
        "github-token@test-keychain:aart:github-token",
        "test-keychain",
        "available",
        "absent",
        "",
    )


def _draft() -> InstallationConfigDraft:
    return InstallationConfigDraft(
        (
            InstallationConfigField(
                "organization",
                "acme",
                InputValidation("identifier"),
            ),
        )
    )


def _state(draft: InstallationConfigDraft | None = None) -> ConsumerUiState:
    current = _draft() if draft is None else draft
    return ConsumerUiState(
        ConsumerSession(
            ConsumerScreen.REQUIRED_INPUTS,
            history=(ConsumerScreen.MARKETPLACE,),
        ),
        selection=("company/mcp/github@1.0.0",),
        action=ConsumerActionKind.INSTALL,
        config_draft=current,
        config_form_active=True,
        rows=("organization", CONFIG_CONTINUE_ROW),
    )


class InstallTimeConfigFormInteractionTest(unittest.TestCase):
    def test_default_is_prefilled_but_continue_submits_nothing_until_enter_accepts_it(self) -> None:
        state = _state()
        self.assertFalse(state.config_draft.ready)
        self.assertIsNone(key_event("enter", replace(state, cursor=1)))

        state, commands = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_INSTALL_CONFIG,
                key="organization",
                accepted=True,
            ),
        )

        self.assertEqual(commands, ())
        self.assertTrue(state.config_draft.ready)
        self.assertEqual(state.cursor, 1)
        event = key_event("enter", state)
        self.assertIsNotNone(event)
        reviewed, commands = reduce_consumer_ui(state, event)  # type: ignore[arg-type]
        self.assertIs(reviewed.session.screen, ConsumerScreen.REVIEW_SELECTION)
        self.assertEqual(commands[0].config_answers, (("organization", "acme"),))
        self.assertIs(commands[0].action, ConsumerActionKind.INSTALL)

    def test_editing_an_accepted_field_requires_enter_again(self) -> None:
        accepted = _draft().accept("organization")
        state = _state(accepted)

        event = key_event("backspace", state)
        self.assertIsNotNone(event)
        edited, _ = reduce_consumer_ui(state, event)  # type: ignore[arg-type]

        self.assertEqual(edited.config_draft.value("organization"), "acm")
        self.assertFalse(edited.config_draft.ready)

    def test_invalid_and_credential_shaped_values_stay_on_the_field(self) -> None:
        for value, expected in (
            ("not an identifier", "expected an identifier"),
            (access_token("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"), "looks like a credential"),
        ):
            with self.subTest(value=value):
                draft = _draft().edit("organization", value)
                state = _state(draft)
                event = key_event("enter", state)
                self.assertIsNotNone(event)
                refused, commands = reduce_consumer_ui(state, event)  # type: ignore[arg-type]
                self.assertEqual(commands, ())
                self.assertFalse(refused.config_draft.ready)
                self.assertEqual(refused.cursor, 0)
                self.assertIn(expected, refused.config_draft.problem("organization") or "")

    def test_printable_keys_and_whole_paste_follow_the_existing_form_pattern(self) -> None:
        state = _state(_draft().edit("organization", ""))
        for character in "team-a":
            event = key_event(character, state)
            state, _ = reduce_consumer_ui(state, event)  # type: ignore[arg-type]
        self.assertEqual(state.config_draft.value("organization"), "team-a")

        pasted = key_event("platform-team", state)
        state, _ = reduce_consumer_ui(state, pasted)  # type: ignore[arg-type]
        self.assertEqual(state.config_draft.value("organization"), "platform-team")


class InstallTimeConfigFormRenderingTest(unittest.TestCase):
    def _source(self) -> CanonicalScreenSource:
        base = screens()
        return CanonicalScreenSource(
            replace(base, installation_inputs=(_config_view(), _credential_view()))
        )

    def test_form_has_config_rows_continue_and_a_visibly_separate_credential_section(self) -> None:
        source = self._source()
        state = _state()
        state = replace(state, rows=source.rows(state))

        drawn = "\n".join(frame(source, state))

        self.assertEqual(source.rows(state), ("organization", CONFIG_CONTINUE_ROW))
        self.assertIn("Configuration", drawn)
        self.assertIn("GitHub organization", drawn)
        self.assertIn("[acme]", drawn)
        self.assertIn("Credentials", drawn)
        self.assertIn("GitHub token", drawn)
        self.assertIn("Enter securely during installation", drawn)
        self.assertIn("Continue", drawn)
        self.assertIn("[Type] Edit", drawn)
        # §167: the fields are the rows; the credentials a provider will ask for are not rows a
        # cursor can stand on, so they are the state of the view (CP-23 task 14).
        blocks = compose_frame(source, state)
        self.assertEqual(blocks.actions[0], "Configuration")
        self.assertNotIn("Credentials", blocks.actions)
        self.assertNotIn("GitHub token", "\n".join(blocks.actions))
        self.assertIn("- Credentials", blocks.status)
        self.assertIn("- GitHub token: Enter securely during installation", blocks.status)

    def test_each_installation_has_its_own_visible_config_and_credential_row(self) -> None:
        owners = (
            "claude/project:company/mcp/github",
            "tabnine/project:company/mcp/github",
        )
        base = screens()
        source = CanonicalScreenSource(
            replace(
                base,
                installation_inputs=tuple(
                    item
                    for owner in owners
                    for item in (
                        replace(_config_view(), owner=owner),
                        replace(_credential_view(), owner=owner),
                    )
                ),
            )
        )
        draft = InstallationConfigDraft(
            tuple(
                InstallationConfigField(
                    "organization",
                    "acme",
                    InputValidation("identifier"),
                    owner=owner,
                )
                for owner in owners
            )
        )
        state = replace(_state(draft), rows=source.rows(_state(draft)))

        drawn = "\n".join(frame(source, state))

        self.assertEqual(
            source.rows(state),
            tuple(f"{owner}\torganization" for owner in owners) + (CONFIG_CONTINUE_ROW,),
        )
        for owner in owners:
            self.assertIn(f"GitHub organization — {owner}", drawn)
            self.assertIn(f"GitHub token — {owner}: Enter securely during installation", drawn)

    def test_verbose_describes_what_the_field_under_the_cursor_binds_to(self) -> None:
        source = self._source()
        state = _state()
        state = replace(state, rows=source.rows(state))
        verbose, _ = reduce_consumer_ui(
            replace(state, cursor=1), ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE)
        )
        verbose = replace(verbose, cursor=0)

        self.assertEqual(compose_frame(source, verbose).described[0].split()[0], "Binding:")
        self.assertEqual(source.actions(verbose), source.actions(state))

    def test_problem_is_inline_and_a_credential_shaped_value_is_not_drawn(self) -> None:
        secret_like = access_token("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        state = _state(_draft().edit("organization", secret_like))
        source = self._source()

        drawn = "\n".join(frame(source, state))

        self.assertIn("looks like a credential", drawn)
        self.assertNotIn(secret_like, drawn)

    def test_successful_preparation_turns_screen_07_back_into_a_summary(self) -> None:
        state = _state(_draft().accept("organization"))
        prepared, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.INSTALL,
                semantic_identity="semantic",
                selection_identity="selection",
                review_digest="sha256:" + "1" * 64,
            ),
        )

        self.assertFalse(prepared.config_form_active)

    def test_a_preparation_that_needs_answers_opens_07_without_the_previous_review(self) -> None:
        """Task 15: nothing held that the form replaces an earlier plan's identities (mutmut)."""

        review = replace(
            _state(),
            session=ConsumerSession(
                ConsumerScreen.REVIEW_SELECTION,
                history=(ConsumerScreen.MARKETPLACE,),
                semantic_identity="semantic",
                selection_identity="selection",
                review_digest="sha256:" + "1" * 64,
            ),
            config_draft=InstallationConfigDraft(),
            config_form_active=False,
        )
        needs = ConsumerUiEvent(
            ConsumerUiEventKind.ACTION_PREPARED,
            action=ConsumerActionKind.INSTALL,
            config_draft=_draft(),
        )

        prepared, commands = reduce_consumer_ui(review, needs)
        elsewhere, ignored = reduce_consumer_ui(
            replace(review, session=replace(review.session, screen=ConsumerScreen.READY)), needs
        )

        self.assertIs(prepared.session.screen, ConsumerScreen.REQUIRED_INPUTS)
        self.assertIsNone(prepared.session.semantic_identity)
        self.assertIsNone(prepared.session.selection_identity)
        self.assertIsNone(prepared.session.review_digest)
        self.assertEqual(prepared.config_draft, _draft())
        self.assertTrue(prepared.config_form_active)
        self.assertEqual(
            commands,
            (ConsumerUiCommand(ConsumerUiCommandKind.LOAD_SCREEN, ConsumerScreen.REQUIRED_INPUTS),),
        )
        self.assertIs(elsewhere.session.screen, ConsumerScreen.READY)
        self.assertEqual(ignored, ())


class _MemoryCredentialProvider:
    """A provider reference/observation fake; it never receives or stores credential material."""

    provider = "test-keychain"

    def __init__(self) -> None:
        self.state = CredentialState.ABSENT

    def available(self) -> ProviderState:
        return ProviderState.AVAILABLE

    def inspect(self, reference) -> Ok:
        return Ok(
            CredentialObservation(
                reference,
                ProviderState.AVAILABLE,
                self.state,
            )
        )

    def resolution_argv(self, reference) -> tuple[str, ...]:
        return ("/usr/bin/false", "--service", reference.provider.service)

    def store(self, reference, secret=None, *, replace: bool = False) -> Ok:
        if secret is not None:
            raise AssertionError("the application handed credential material to the provider fake")
        self.state = CredentialState.PRESENT
        return self.inspect(reference)

    def delete(self, reference) -> Ok:
        self.state = CredentialState.ABSENT
        return self.inspect(reference)


class InstallTimeConfigPreparationE2ETest(unittest.TestCase):
    def test_answer_reissues_the_real_preparation_as_a_prompted_source(self) -> None:
        with _environment(authored=AUTHORED_MCP) as env:
            handler = _actions(env)
            handler._context = replace(  # noqa: SLF001 - production composition under test
                handler._context,
                credential_providers=(_MemoryCredentialProvider(),),
            )
            first = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/mcp/github@1.5.0",),
                )
            )

            self.assertFalse(first.event.review_digest)
            self.assertIsNotNone(first.event.config_draft)
            assert first.event.config_draft is not None
            config_views = tuple(
                item
                for item in first.source.screens.installation_inputs
                if isinstance(item, ConfigInputView)
            )
            config_rows = tuple(item.row for item in config_views)
            self.assertGreater(len(config_rows), 1)
            self.assertEqual(len(config_rows), len(set(config_rows)))
            for row in config_rows:
                self.assertEqual(first.event.config_draft.value(row), "acme")
            self.assertFalse(first.event.config_draft.ready)
            self.assertTrue(first.source.screens.installation_inputs)
            credentials = tuple(
                item
                for item in first.source.screens.installation_inputs
                if isinstance(item, CredentialInputView)
            )
            self.assertEqual(len(credentials), len(config_views))
            self.assertEqual(len({item.owner for item in credentials}), len(credentials))
            self.assertTrue(all(item.provider_reference is not None for item in credentials))

            incomplete = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/mcp/github@1.5.0",),
                    config_answers=((config_rows[0], "platform-team"),),
                )
            )
            self.assertFalse(incomplete.event.review_digest)

            second = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/mcp/github@1.5.0",),
                    config_answers=tuple((row, "platform-team") for row in config_rows),
                )
            )

        self.assertTrue(second.event.review_digest)
        pending = handler._pending  # noqa: SLF001 - held reviewed action is the assertion subject
        self.assertIsNotNone(pending)
        # Each answer typed on screen 07 reaches only the installation named by its row (D-353).
        composed = pending.prepared.draft.inputs  # type: ignore[union-attr]
        owners = tuple(pending.prepared.draft.owners)  # type: ignore[union-attr]
        self.assertEqual(len(owners), len(config_rows))
        for owner in owners:
            self.assertIn(
                PromptedConfigValue(ORG, "platform-team"),
                composed.sources_for(owner),
            )

    def test_form_to_success_writes_only_the_two_chosen_harness_files(self) -> None:
        value = "platform-team-form-e2e"
        with _environment(authored=AUTHORED_MCP) as env:
            handler = _actions(env)
            provider = _MemoryCredentialProvider()
            handler._context = replace(  # noqa: SLF001 - production composition under test
                handler._context,
                credential_providers=(provider,),
            )
            finished, terminal, _ = _drive(
                env,
                _at(ConsumerScreen.MARKETPLACE),
                SPACE,
                ord("i"),
                value,
                ENTER,
                value,
                ENTER,
                value,
                ENTER,
                ENTER,
                DOWN,
                SPACE,
                DOWN,
                SPACE,
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                actions=handler,
            )

            self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
            config = env.project / ".aart-cli/runtimes/company/mcp/github/config"
            self.assertFalse((config / "claude.conf").exists())
            for harness in ("opencode", "tabnine"):
                path = config / f"{harness}.conf"
                self.assertTrue(path.is_file(), f"{harness} configuration was not written")
                self.assertIn(f"{ORG}={value}\n", path.read_text(encoding="utf-8"))

            aart_state = env.paths.data_root
            leaked = [
                path
                for path in __import__("pathlib").Path(aart_state).rglob("*")
                if path.is_file() and value in path.read_text(encoding="utf-8", errors="replace")
            ]
            self.assertEqual(leaked, [])
            self.assertIs(provider.state, CredentialState.PRESENT)


if __name__ == "__main__":
    unittest.main()
