"""D-380: once the form is submitted, the install goes forward and never asks for the harness again.

§161.5 orders the fast flow Review Selection, Required Inputs, then Ready, which since D-403 also
lists the material changes Remediation used to stop for. The form used to return to 05, which drew the harness rows a second time, and
then to 07 again as a summary, before reaching Ready.
"""

from __future__ import annotations

import datetime as dt
import unittest
from dataclasses import replace

from aart_cli.application.consumer_session import assemble_consumer_machine
from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    HarnessTargetView,
    PythonInstallerChoiceView,
    installer_row,
    matrix_rows,
    project_install_plan,
)
from aart_cli.tui_consumer import CanonicalScreenSource, screens_from
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AUTHORED_MCP
from tests.consumer_application_e2e_test import _actions, _drive
from tests.consumer_shell_test import ENTER, RIGHT, SPACE, UP, _at
from tests.consumer_views_test import _plan as _view_plan
from tests.install_time_config_form_test import _MemoryCredentialProvider, _state

DIGEST = "sha256:" + "1" * 64


def _prepared(screen: ConsumerScreen | None) -> ConsumerUiEvent:
    return ConsumerUiEvent(
        ConsumerUiEventKind.ACTION_PREPARED,
        action=ConsumerActionKind.INSTALL,
        semantic_identity="semantic",
        selection_identity="selection",
        review_digest=DIGEST,
        screen=screen,
    )


def _submitted() -> ConsumerUiState:
    """Through the real route: 05, Continue into the form, accept the field, submit."""

    review = replace(
        _state(),
        session=ConsumerSession(
            ConsumerScreen.REVIEW_SELECTION, history=(ConsumerScreen.MARKETPLACE,)
        ),
        config_form_active=False,
    )
    form, _ = reduce_consumer_ui(
        review, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=ConsumerScreen.REQUIRED_INPUTS)
    )
    accepted = replace(form, config_draft=form.config_draft.accept("organization"), cursor=1)
    submitted, _ = reduce_consumer_ui(accepted, key_event("enter", accepted))  # type: ignore[arg-type]
    return submitted


class TheFormGoesForwardE2ETest(unittest.TestCase):
    def test_after_the_form_no_screen_asks_for_the_harness_again(self) -> None:
        value = "platform-team-forward"
        with _environment(authored=AUTHORED_MCP) as env:
            handler = _actions(env)
            handler._context = replace(  # noqa: SLF001 - production composition under test
                handler._context,
                credential_providers=(_MemoryCredentialProvider(),),
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
                value,
                ENTER,
                # Submit the form. The plan offers a choice of Python backend, which 05 asks, then
                # 07a the scope; Continue on each, then confirm Ready. Nothing else.
                ENTER,
                ENTER,
                ENTER,
                # 07b: Set later, above the credential the cursor opens on (§172.6).
                UP,
                ENTER,
                ENTER,
                actions=handler,
            )

            self.assertIs(finished.session.screen, ConsumerScreen.SUCCESS, terminal.last)
            frames = ["\n".join(frame) for frame in terminal.frames]
            first_form = next(i for i, text in enumerate(frames) if "/ Required Inputs" in text)
            after = frames[first_form:]
            self.assertTrue(after)
            # D-380: 05 after the form is the backend alone; the harness matrix is not drawn again,
            # and the scope is asked on 07a only (§172.5).
            self.assertTrue(any("/ Scope" in text for text in after))
            for text in after:
                self.assertNotRegex(text, r"claude +opencode +tabnine")
                self.assertNotIn("company/mcp/github  ", text)
                self.assertNotIn("Install into:", text)


class TheReducerFollowsTheAdapterForwardTest(unittest.TestCase):
    def test_submitting_the_form_marks_the_inputs_submitted(self) -> None:
        self.assertTrue(_submitted().inputs_submitted)
        self.assertFalse(_state().inputs_submitted)

    def test_a_prepared_plan_after_the_form_moves_to_the_screen_the_adapter_names(self) -> None:
        moved, _ = reduce_consumer_ui(_submitted(), _prepared(ConsumerScreen.READY))

        self.assertIs(moved.session.screen, ConsumerScreen.READY)
        self.assertEqual(moved.session.review_digest, DIGEST)
        self.assertEqual(
            moved.session.history, (ConsumerScreen.MARKETPLACE, ConsumerScreen.REVIEW_SELECTION)
        )

    def test_without_a_submitted_form_the_named_screen_is_ignored(self) -> None:
        review = replace(
            _submitted(),
            inputs_submitted=False,
        )
        stayed, _ = reduce_consumer_ui(review, _prepared(ConsumerScreen.READY))

        self.assertIs(stayed.session.screen, ConsumerScreen.REVIEW_SELECTION)

    def test_backing_out_to_05_lets_the_harness_be_chosen_again(self) -> None:
        moved, _ = reduce_consumer_ui(_submitted(), _prepared(ConsumerScreen.READY))
        back, _ = reduce_consumer_ui(moved, ConsumerUiEvent(ConsumerUiEventKind.BACK))

        self.assertIs(back.session.screen, ConsumerScreen.REVIEW_SELECTION)
        self.assertFalse(back.inputs_submitted)

    def test_an_answer_that_needs_inputs_again_clears_the_mark(self) -> None:
        from aart_cli.application.consumer_ui import InstallationConfigDraft

        again, _ = reduce_consumer_ui(
            _submitted(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.INSTALL,
                config_draft=InstallationConfigDraft(),
            ),
        )

        self.assertFalse(again.inputs_submitted)


class TheAmendmentsScreenTest(unittest.TestCase):
    """When the plan still offers a real choice, 05 is drawn with that choice and no harness."""

    def _source(self) -> CanonicalScreenSource:
        view = project_install_plan(_view_plan())
        artifact = view.selection.resolved[0]
        plan = replace(
            view,
            targets=(HarnessTargetView("claude", (artifact,)),),
            installer_choice=PythonInstallerChoiceView(("pip", "uv"), "pip"),
        )
        machine = assemble_consumer_machine((), today=dt.date(2026, 10, 14))
        return CanonicalScreenSource(screens_from(machine, plan=plan))

    def _state(self, *, submitted: bool) -> ConsumerUiState:
        return ConsumerUiState(
            ConsumerSession(ConsumerScreen.REVIEW_SELECTION, review_digest=DIGEST),
            selection=("company/mcp/github@1.0.0",),
            targets=("claude",),
            action=ConsumerActionKind.INSTALL,
            inputs_submitted=submitted,
        )

    def test_after_the_form_only_the_choice_is_a_row(self) -> None:
        source = self._source()

        self.assertEqual(
            source.rows(self._state(submitted=True)), (installer_row("pip"), installer_row("uv"))
        )
        self.assertEqual(
            source.rows(self._state(submitted=False)),
            (
                *matrix_rows((HarnessTargetView("claude", ("company/mcp/github@1.0.0",)),)),
                installer_row("pip"),
                installer_row("uv"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
