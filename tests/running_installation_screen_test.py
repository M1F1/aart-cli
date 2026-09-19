"""`QA-082` at the shell: what is running is drawn, in the frame every other screen is drawn in.

Issue #7 asked for it plainly: the Ready screen lists what will happen, and then the installation
runs silently. The shell already drew one frame before handing over to the effect boundary; it now
lends the handler somewhere to report each step, and redraws that same frame as the report changes.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    PresentationProfile,
    project_running_installation,
)
from aart_cli.application.execution import StepProgress, StepStatus
from aart_cli.domain.effects import ConfigureHarness, WriteFile
from aart_cli.domain.reconciliation import Component, ComponentId
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    ConsumerActionUpdate,
    render_running,
    run_consumer_shell,
)
from aart_cli.tui_layout import CONTENT_MEASURE, SECTION_RULE
from tests.consumer_action_shell_test import RECORDED_AT, _prepared_source
from tests.consumer_install_flow_shell_test import plan_view
from tests.consumer_install_flow_shell_test import screens as flow_screens
from tests.consumer_marketplace_shell_test import screens as marketplace_screens
from tests.consumer_shell_test import ENTER, FakeTerminal

LAUNCHER = ComponentId(Component.LAUNCHER)
HARNESS = ComponentId(Component.HARNESS, "tabnine")
WRITE = WriteFile("/opt/agents/mcp/github/launch", "sha256:" + "a" * 64, True)
CONFIGURE = ConfigureHarness("tabnine", "mcp/github", ".tabnine/agent/settings.json")


class ReportingHandler:
    """A handler that runs two steps and says so, the way the real one does."""

    def __init__(self, *, fail: bool = False) -> None:
        self._report = None
        self._fail = fail
        self.reported_with_no_screen = 0

    def observe_progress(self, report) -> None:
        self._report = report

    def handle(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if command.kind is ConsumerUiCommandKind.PREPARE_ACTION:
            return ConsumerActionUpdate(
                _prepared_source(),
                ConsumerUiEvent(
                    ConsumerUiEventKind.ACTION_PREPARED,
                    action=command.action,
                    semantic_identity=plan_view().semantic_identity,
                    selection_identity=plan_view().selection.semantic_identity,
                    review_digest=plan_view().review_digest,
                ),
            )
        seen: list[StepProgress] = []
        finish = StepStatus.FAILED if self._fail else StepStatus.APPLIED
        for report in (
            StepProgress(LAUNCHER, WRITE, 1, 2),
            StepProgress(LAUNCHER, WRITE, 1, 2, StepStatus.APPLIED, "written"),
            StepProgress(HARNESS, CONFIGURE, 2, 2),
            StepProgress(HARNESS, CONFIGURE, 2, 2, finish, "it broke" if self._fail else "done"),
        ):
            seen.append(report)
            if self._report is None:
                self.reported_with_no_screen += 1
                continue
            self._report(project_running_installation(tuple(seen)))
        return ConsumerActionUpdate(
            CanonicalScreenSource(
                replace(marketplace_screens(), plan=plan_view(), outcome=flow_screens().outcome)
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=command.action,
                text=RECORDED_AT,
            ),
        )


def _drive(handler: ReportingHandler) -> FakeTerminal:
    terminal = FakeTerminal(ENTER)
    plan = plan_view()
    state = ConsumerUiState(
        ConsumerSession(
            ConsumerScreen.READY,
            semantic_identity=plan.semantic_identity,
            selection_identity=plan.selection.semantic_identity,
            review_digest=plan.review_digest,
        ),
        selection=("public/mcp/github@1.6.0",),
        action=ConsumerActionKind.INSTALL,
    )
    run_consumer_shell(_prepared_source(), terminal, state=state, action_handler=handler)
    return terminal


class RunningInstallationScreenTest(unittest.TestCase):
    def test_each_step_is_drawn_while_it_runs_rather_than_only_when_it_is_over(self) -> None:
        terminal = _drive(ReportingHandler())

        drawn = ["\n".join(item) for item in terminal.frames]
        self.assertTrue(any("▸ launcher" in item for item in drawn))
        self.assertTrue(any("✓ launcher" in item and "▸ harness:tabnine" in item for item in drawn))
        # The count is the steps that are over, so it moves through every number in turn: a frame
        # reading the final count before the final step is counting something else.
        counts = [
            line.split("(")[-1]
            for item in drawn
            for line in item.splitlines()
            if "Installing" in line and " done)" in line
        ]
        self.assertEqual(counts, ["0 of 2 done)", "1 of 2 done)", "1 of 2 done)", "2 of 2 done)"])

    def test_the_running_report_is_drawn_inside_the_shared_frame(self) -> None:
        terminal = _drive(ReportingHandler())

        running = next(
            "\n".join(item) for item in terminal.frames if "▸ launcher" in "\n".join(item)
        )
        self.assertIn("AART /", running.splitlines()[0])
        self.assertIn(SECTION_RULE, running)
        self.assertIn("[q] Quit", running)

    def test_a_step_that_failed_is_named_where_it_failed(self) -> None:
        terminal = _drive(ReportingHandler(fail=True))

        drawn = ["\n".join(item) for item in terminal.frames]
        self.assertTrue(any("✗ harness:tabnine" in item for item in drawn))

    def test_the_reporter_is_given_back_when_the_execution_is_over(self) -> None:
        handler = ReportingHandler()

        _drive(handler)

        self.assertIsNone(handler._report)
        self.assertEqual(handler.reported_with_no_screen, 0)

    def test_a_narrow_screen_keeps_the_running_report_within_the_structured_measure(self) -> None:
        """The running report is the finished report's shape, so it keeps the same bound.

        What a step reported can be arbitrarily long -- it is whatever the effect boundary said --
        and the default profile draws the component rather than the detail, exactly as the finished
        report does. No screen-specific skeleton, and so no screen-specific overflow.
        """

        loud = "wrote " + "/opt/agents/mcp/github/launch" * 20
        view = project_running_installation(
            (
                StepProgress(LAUNCHER, WRITE, 1, 2),
                StepProgress(LAUNCHER, WRITE, 1, 2, StepStatus.APPLIED, loud),
                StepProgress(HARNESS, CONFIGURE, 2, 2),
            )
        )

        lines = render_running(view, PresentationProfile.FAST)

        self.assertGreater(len(loud), CONTENT_MEASURE)
        self.assertTrue(all(len(line) <= CONTENT_MEASURE for line in lines), lines)
        self.assertNotIn(loud, "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
