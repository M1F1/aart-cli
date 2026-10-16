"""CP-23 task 16.2: screen 07 collects ordinary configuration before review."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    CONFIG_CONTINUE_ROW,
    CONFIG_SET_LATER_ROW,
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
    HarnessTargetView,
    matrix_from_row,
    pair_key,
)
from aart_cli.domain.credentials import (
    CredentialObservation,
    CredentialState,
    ProviderState,
)
from aart_cli.domain.inputs import SKIPPED_INPUT, InputValidation, PromptedConfigValue
from aart_cli.domain.result import Ok
from aart_cli.tui_consumer import CanonicalScreenSource, compose_frame, frame
from tests.artifact_installation_e2e_test import ORG
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.consumer_application_e2e_test import _actions, _at, _drive
from tests.consumer_shell_test import BACKSPACE, ENTER, RIGHT, SPACE, UP, screens
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

    def test_the_form_opens_on_its_first_field_not_on_set_later(self) -> None:
        state = replace(_state(), rows=("elsewhere",), cursor=0)

        opened, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.SET_ROWS,
                rows=(CONFIG_SET_LATER_ROW, "organization", CONFIG_CONTINUE_ROW),
            ),
        )

        self.assertEqual(opened.current_row, "organization")

    def test_set_later_keeps_valid_values_and_skips_the_rest_then_goes_on(self) -> None:
        """§172.3-4: a default left in place is an answer; an empty or invalid value is skipped."""

        draft = InstallationConfigDraft(
            (
                InstallationConfigField("organization", "acme", InputValidation("identifier")),
                InstallationConfigField("project", ""),
                InstallationConfigField("team", "not an id", InputValidation("identifier")),
            )
        )
        state = replace(
            _state(draft),
            rows=(CONFIG_SET_LATER_ROW, "organization", "project", "team", CONFIG_CONTINUE_ROW),
            cursor=0,
        )
        self.assertFalse(state.config_draft.ready)

        event = key_event("enter", state)
        assert event is not None
        reviewed, commands = reduce_consumer_ui(state, event)

        self.assertIs(reviewed.session.screen, ConsumerScreen.REVIEW_SELECTION)
        self.assertTrue(reviewed.config_draft.ready)
        self.assertEqual(
            commands[0].config_answers,
            (("organization", "acme"), ("project", SKIPPED_INPUT), ("team", SKIPPED_INPUT)),
        )
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

    def test_form_has_config_rows_continue_and_nothing_else_under_it(self) -> None:
        """D-380: the credential is asked for by its provider, with its guidance, when it asks."""

        source = self._source()
        state = _state()
        state = replace(state, rows=source.rows(state), cursor=1)

        drawn = "\n".join(frame(source, state))
        on_set_later = "\n".join(frame(source, replace(state, cursor=0)))

        self.assertEqual(
            source.rows(state), (CONFIG_SET_LATER_ROW, "organization", CONFIG_CONTINUE_ROW)
        )
        self.assertIn("[Enter] Set later", on_set_later)
        # §172.3: Set later comes first.
        self.assertRegex(drawn, r"\n[> ] Set later\n")
        self.assertIn("GitHub organization", drawn)
        self.assertIn("[acme]", drawn)
        self.assertIn("Continue", drawn)
        self.assertIn("[Type] Edit", drawn)
        blocks = compose_frame(source, state)
        self.assertEqual(blocks.actions[0], "Configuration")
        for gone in ("Credentials", "GitHub token", "kept beside", "AART keeps only references"):
            self.assertNotIn(gone, drawn)

    def test_each_artifact_is_one_group_of_fields_set_apart_by_blank_lines(self) -> None:
        """§172.4: a field per artifact, headed by its artifact once there are two to tell apart."""

        artifacts = ("company/mcp/github", "company/mcp/jira")
        base = screens()
        source = CanonicalScreenSource(
            replace(
                base,
                installation_inputs=tuple(
                    replace(_config_view(), owner=artifact) for artifact in artifacts
                ),
            )
        )
        draft = InstallationConfigDraft(
            tuple(
                InstallationConfigField(
                    "organization", "acme", InputValidation("identifier"), owner=artifact
                )
                for artifact in artifacts
            )
        )
        state = replace(_state(draft), rows=source.rows(_state(draft)))

        actions = compose_frame(source, state).actions

        self.assertEqual(
            source.rows(state),
            (
                CONFIG_SET_LATER_ROW,
                *(f"{artifact}\torganization" for artifact in artifacts),
                CONFIG_CONTINUE_ROW,
            ),
        )
        headings = [actions.index(artifact) for artifact in artifacts]
        self.assertLess(headings[0], headings[1])
        fields = [index for index, line in enumerate(actions) if "GitHub organization" in line]
        self.assertEqual(len(fields), 2, actions)
        self.assertTrue(all(headings[n] < fields[n] for n in range(2)))
        for index in (*headings, *fields):
            self.assertEqual(actions[index - 1], "", "a group or field is not set apart")
        self.assertNotIn("—", "\n".join(actions))

    def test_one_artifact_has_no_heading_of_its_own(self) -> None:
        source = self._source()
        state = replace(_state(), rows=source.rows(_state()))

        self.assertNotIn("company/mcp/github", compose_frame(source, state).actions)

    def test_05_without_a_plan_offers_the_harnesses_and_continues_only_once_chosen(self) -> None:
        """#50: before any field is drawn, 05 asks only which harnesses to install into."""

        base = screens()
        source = CanonicalScreenSource(
            replace(
                base,
                plan=None,
                install_targets=(
                    HarnessTargetView("opencode", ("company/mcp/github@1.5.0",)),
                    HarnessTargetView("tabnine", ("company/mcp/github@1.5.0",)),
                ),
            )
        )
        state = replace(
            _state(),
            session=ConsumerSession(
                ConsumerScreen.REVIEW_SELECTION, history=(ConsumerScreen.MARKETPLACE,)
            ),
            config_form_active=False,
        )
        state = replace(state, rows=source.rows(state))
        unchosen = "\n".join(frame(source, state))
        chosen = replace(
            state,
            targets=("tabnine",),
            pairs=(pair_key("company/mcp/github@1.5.0", "tabnine"),),
        )
        empty = replace(chosen, config_draft=InstallationConfigDraft())

        self.assertEqual(
            [matrix_from_row(row) for row in source.rows(state)],
            [("company/mcp/github@1.5.0", ("opencode", "tabnine"))],
        )
        self.assertRegex(unchosen, r"company/mcp/github +>\[ \] +\[ \]")
        self.assertIn("choose at least one harness", unchosen)
        self.assertNotIn("GitHub organization", unchosen)
        self.assertIsNone(source.detail(state))
        self.assertIs(source.detail(chosen), ConsumerScreen.REQUIRED_INPUTS)
        # D-401: the ticked box is the choice; Fast does not restate it.
        self.assertNotIn("installing into", "\n".join(frame(source, chosen)).lower())
        # A choice whose preparation has not yet answered with its fields has nothing to open.
        self.assertIsNone(source.detail(empty))

    def test_verbose_describes_what_the_field_under_the_cursor_binds_to(self) -> None:
        source = self._source()
        state = _state()
        state = replace(state, rows=source.rows(state), cursor=1)
        verbose, _ = reduce_consumer_ui(
            replace(state, cursor=2), ConsumerUiEvent(ConsumerUiEventKind.TOGGLE_PROFILE)
        )
        verbose = replace(verbose, cursor=1)

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

    def test_a_preparation_that_needs_answers_stays_on_05_without_the_previous_review(self) -> None:
        """#50: the harness is chosen on 05 before the form; an earlier plan's identities go."""

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

        self.assertIs(prepared.session.screen, ConsumerScreen.REVIEW_SELECTION)
        self.assertIsNone(prepared.session.semantic_identity)
        self.assertIsNone(prepared.session.selection_identity)
        self.assertIsNone(prepared.session.review_digest)
        self.assertEqual(prepared.config_draft, _draft())
        self.assertFalse(prepared.config_form_active)
        self.assertEqual(
            commands,
            (
                ConsumerUiCommand(
                    ConsumerUiCommandKind.LOAD_SCREEN, ConsumerScreen.REVIEW_SELECTION
                ),
            ),
        )
        self.assertIs(elsewhere.session.screen, ConsumerScreen.READY)
        self.assertEqual(ignored, ())

    def test_05_opens_the_form_only_before_a_plan_and_only_with_fields_to_ask(self) -> None:
        """#50: Continue from 05 is the way into the form; after review 07 is a summary."""

        review = replace(
            _state(),
            session=ConsumerSession(
                ConsumerScreen.REVIEW_SELECTION,
                history=(ConsumerScreen.MARKETPLACE,),
            ),
            config_form_active=False,
        )
        go = ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.REQUIRED_INPUTS)

        form, _ = reduce_consumer_ui(review, go)
        empty, _ = reduce_consumer_ui(replace(review, config_draft=InstallationConfigDraft()), go)
        reviewed, _ = reduce_consumer_ui(
            replace(
                review,
                session=replace(review.session, review_digest="sha256:" + "1" * 64),
            ),
            go,
        )

        self.assertIs(form.session.screen, ConsumerScreen.REQUIRED_INPUTS)
        self.assertTrue(form.config_form_active)
        self.assertFalse(empty.config_form_active)
        self.assertFalse(reviewed.config_form_active)

        # Submitting the form returns to 05 by rewinding: the form is not left on the stack.
        accepted = replace(form, config_draft=form.config_draft.accept("organization"))
        submitted, _ = reduce_consumer_ui(accepted, key_event("enter", replace(accepted, cursor=1)))  # type: ignore[arg-type]
        self.assertIs(submitted.session.screen, ConsumerScreen.REVIEW_SELECTION)
        self.assertEqual(submitted.session.history, (ConsumerScreen.MARKETPLACE,))


class _MemoryCredentialProvider:
    """A provider reference/observation fake; it never receives or stores credential material.

    One item per address, not one state for the provider. A real provider holds an item per
    service/account pair, and each installation addresses its own (§169.4-6), so a fake with a
    single flag answers `present` for an installation whose item nobody stored -- which made the
    second harness of a two-harness install read as state that changed after Review, and its
    member was abandoned while the transaction still reported success.
    """

    provider = "test-keychain"

    def __init__(self) -> None:
        self.stored: set[str] = set()

    @staticmethod
    def _address(reference) -> str:
        return f"{reference.provider.service}/{reference.provider.account}"

    @property
    def state(self) -> CredentialState:
        """Whether anything at all is held, for the assertions that ask about the provider."""

        return CredentialState.PRESENT if self.stored else CredentialState.ABSENT

    def holds(self, reference) -> bool:
        return self._address(reference) in self.stored

    def available(self) -> ProviderState:
        return ProviderState.AVAILABLE

    def inspect(self, reference) -> Ok:
        return Ok(
            CredentialObservation(
                reference,
                ProviderState.AVAILABLE,
                CredentialState.PRESENT if self.holds(reference) else CredentialState.ABSENT,
            )
        )

    def resolution_argv(self, reference) -> tuple[str, ...]:
        return ("/usr/bin/false", "--service", reference.provider.service)

    def store(self, reference, secret=None, *, replace: bool = False) -> Ok:
        # §172.4: with nothing entered before Ready, only the placeholder may arrive here.
        if secret is not None and secret.consume() != SKIPPED_INPUT:
            raise AssertionError("the application handed credential material to the provider fake")
        self.stored.add(self._address(reference))
        return self.inspect(reference)

    def delete(self, reference) -> Ok:
        self.stored.discard(self._address(reference))
        return self.inspect(reference)


class InstallTimeConfigPreparationE2ETest(unittest.TestCase):
    def test_answer_reissues_the_real_preparation_as_a_prompted_source(self) -> None:
        with _environment(authored=AUTHORED_MCP) as env:
            handler = _actions(env)
            handler._context = replace(  # noqa: SLF001 - production composition under test
                handler._context,
                credential_providers=(_MemoryCredentialProvider(),),
            )
            unchosen = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/mcp/github@1.5.0",),
                )
            )
            # #50: nothing is asked before the harness is chosen; the answer is the choice.
            self.assertFalse(unchosen.event.review_digest)
            self.assertEqual(unchosen.event.config_draft, InstallationConfigDraft())
            self.assertEqual(unchosen.source.screens.installation_inputs, ())
            offered = tuple(item.harness for item in unchosen.source.screens.install_targets)
            self.assertEqual(set(offered), {"claude", "opencode", "tabnine"})

            chosen = ("opencode", "tabnine")
            first = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/mcp/github@1.5.0",),
                    targets=chosen,
                )
            )

            self.assertFalse(first.event.review_digest)
            self.assertEqual(
                first.source.screens.install_targets, unchosen.source.screens.install_targets
            )
            self.assertIsNotNone(first.event.config_draft)
            assert first.event.config_draft is not None
            config_views = tuple(
                item
                for item in first.source.screens.installation_inputs
                if isinstance(item, ConfigInputView)
            )
            config_rows = tuple(item.row for item in config_views)
            # §172.4: one field for the artifact, however many harnesses it goes into.
            self.assertEqual(config_rows, ("company/mcp/github\tgithub-org",))
            for row in config_rows:
                self.assertEqual(first.event.config_draft.value(row), "acme")
            self.assertFalse(first.event.config_draft.ready)
            self.assertTrue(first.source.screens.installation_inputs)
            credentials = tuple(
                item
                for item in first.source.screens.installation_inputs
                if isinstance(item, CredentialInputView)
            )
            # Secrets stay per installation until 07b asks them once per artifact (step 8).
            self.assertEqual(len(credentials), len(chosen))
            self.assertEqual(len({item.owner for item in credentials}), len(credentials))
            self.assertTrue(all(item.provider_reference is not None for item in credentials))

            second = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.INSTALL,
                    selection=("company/mcp/github@1.5.0",),
                    targets=chosen,
                    config_answers=tuple((row, "platform-team") for row in config_rows),
                )
            )

        self.assertTrue(second.event.review_digest)
        pending = handler._pending  # noqa: SLF001 - held reviewed action is the assertion subject
        self.assertIsNotNone(pending)
        # The one answer typed on 07 is copied into each installation of its artifact (INV-259).
        composed = pending.prepared.draft.inputs  # type: ignore[union-attr]
        owners = tuple(pending.prepared.draft.owners)  # type: ignore[union-attr]
        self.assertEqual(sorted(owner.harness for owner in owners), sorted(chosen))
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
                # #50: the harnesses first, then one field for the artifact (§172.4).
                RIGHT,
                SPACE,
                RIGHT,
                SPACE,
                ENTER,
                value,
                ENTER,
                # Submit. The plan still offers a choice of scope, so 05 shows only that (D-380);
                # Continue goes on to Ready (which holds Remediation's changes since D-403).
                ENTER,
                ENTER,
                ENTER,
                actions=handler,
            )

            self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
            # Each chosen harness is its own installation, so each has its own tree with its own
            # configuration in it (§169.3), and the harness nobody chose has no tree at all.
            self.assertFalse((env.project / ".claude/aart-cli").exists())
            for harness, directory in (("opencode", ".opencode"), ("tabnine", ".tabnine")):
                path = (
                    env.project
                    / directory
                    / "aart-cli/mcp/company/github/config"
                    / f"{harness}.conf"
                )
                self.assertTrue(path.is_file(), f"{harness} configuration was not written")
                self.assertIn(f"{ORG}={value}\n", path.read_text(encoding="utf-8"))

            registrations = (
                json.loads((env.project / "opencode.json").read_text(encoding="utf-8"))["mcp"],
                json.loads(
                    (env.project / ".tabnine/agent/settings.json").read_text(encoding="utf-8")
                )["mcpServers"],
            )
            for registered in registrations:
                self.assertIn("github-company-project", registered)
                self.assertNotIn("github", registered)

            aart_state = env.paths.data_root
            leaked = [
                path
                for path in __import__("pathlib").Path(aart_state).rglob("*")
                if path.is_file() and value in path.read_text(encoding="utf-8", errors="replace")
            ]
            self.assertEqual(leaked, [])
            # One item per installation, not one per artifact (§169.4-6). Two were stored, each
            # naming its own harness, and the harness nobody chose has none. The addresses are
            # asserted by what distinguishes them rather than recomposed here, because composing
            # the expectation from `credential_address` would assert that function against itself.
            held = sorted(provider.stored)
            self.assertEqual(len(held), 2, held)
            self.assertEqual(
                [1, 1], [sum(h in item for item in held) for h in ("opencode", "tabnine")]
            )
            self.assertEqual([], [item for item in held if "claude" in item])

    def test_set_later_installs_with_the_placeholder_in_each_installation(self) -> None:
        """§172.3, INV-261: skipping the form blocks nothing; each copy holds `AART_NOT_SET`."""

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
                RIGHT,
                SPACE,
                RIGHT,
                SPACE,
                ENTER,
                # The form opens on its field. Its declared default would be an answer (§172.4),
                # so it is cleared first; Set later is the row above it.
                *((BACKSPACE,) * len("acme")),
                UP,
                ENTER,
                ENTER,
                ENTER,
                actions=handler,
            )

            self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
            for harness, directory in (("opencode", ".opencode"), ("tabnine", ".tabnine")):
                path = (
                    env.project
                    / directory
                    / "aart-cli/mcp/company/github/config"
                    / f"{harness}.conf"
                )
                self.assertIn(f"{ORG}={SKIPPED_INPUT}\n", path.read_text(encoding="utf-8"))
            self.assertEqual(len(provider.stored), 2)


if __name__ == "__main__":
    unittest.main()
