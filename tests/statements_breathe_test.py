"""D-402: the statements on a screen are parted by blank lines, and a heading reads as one.

The operator asked, screen by screen, for a blank line after the sentence that opens a list and
between the things a list holds -- Remediation (now on Ready, D-403), Installing, the MCP test's offer and its results --
and for the Dashboard's recent activity to be marked and laid out as the AART block above it.
"""

from __future__ import annotations

import dataclasses
import unittest

from aart_cli.application.consumer_ui import ConsumerUiState
from aart_cli.application.consumer_views import (
    McpTestEntryView,
    McpTestResultView,
    McpTestStageView,
    McpTestView,
    PresentationProfile,
)
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    _reload,
    frame,
    render_mcp_test,
    render_progress,
)
from tests.consumer_install_flow_shell_test import screens

INSTALLATIONS = ("company/mcp/github@1.0.0#opencode", "company/mcp/jira@2.0.0#opencode")


class StatementsBreatheTest(unittest.TestCase):
    def test_progress_parts_its_heading_from_the_steps(self) -> None:
        lines = render_progress(screens().outcome, PresentationProfile.FAST)

        self.assertEqual(lines[1], "")
        self.assertTrue(lines[2].lstrip().startswith(("✓", "·", "✗")))

    def test_the_mcp_offer_is_a_marked_heading_then_its_calls_then_each_statement_apart(
        self,
    ) -> None:
        view = McpTestView(
            INSTALLATIONS,
            (
                McpTestEntryView(INSTALLATIONS[0], "get_me", "{}"),
                McpTestEntryView(INSTALLATIONS[1], "", ""),
            ),
        )
        lines = render_mcp_test(view)

        self.assertTrue(lines[0].startswith("- confirming starts each installed MCP"))
        self.assertEqual(lines[1], "")
        self.assertEqual(lines[4:], ("", lines[5], "", lines[7]))

    def test_mcp_results_are_parted_from_the_heading_from_each_other_and_from_the_last_word(
        self,
    ) -> None:
        stage = McpTestStageView("call", "PASS", "get_me returned")
        view = McpTestView(
            INSTALLATIONS, (), tuple(McpTestResultView(item, (stage,)) for item in INSTALLATIONS)
        )
        lines = render_mcp_test(view)

        self.assertEqual(lines[:2], ("Test results:", ""))
        self.assertEqual([index for index, line in enumerate(lines) if not line], [1, 4, 7])
        self.assertTrue(lines[-1].startswith("The installation is unchanged"))

    def test_the_dashboard_marks_recent_activity_as_it_marks_aart(self) -> None:
        activity = ("installed company/mcp/github@1.0.0", "uninstalled public/mcp/jira@2.2.0")
        source = CanonicalScreenSource(
            dataclasses.replace(
                screens(),
                dashboard=dataclasses.replace(screens().dashboard, recent_activity=activity),
            )
        )
        lines = frame(source, _reload(source, ConsumerUiState(), entering=True))
        heading = lines.index("- recent activity")

        self.assertIn("- AART", lines)
        self.assertEqual(lines[heading + 1 : heading + 3], tuple(f"  {item}" for item in activity))


if __name__ == "__main__":
    unittest.main()
