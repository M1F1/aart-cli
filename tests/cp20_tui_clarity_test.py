"""CP-20 regressions reported by the manual TUI operator."""

from __future__ import annotations

import unittest

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    DoctorView,
    project_dashboard,
)
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload


class DoctorSubjectTest(unittest.TestCase):
    def test_repair_from_doctor_targets_an_installed_issue_not_the_screen_identifier(self) -> None:
        coordinate = "company/skill/broken@1.0.0"
        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                doctor=DoctorView(0, 1, (coordinate,), (coordinate,), ("repair-issues",)),
            )
        )
        state = _reload(
            source,
            ConsumerUiState(
                ConsumerSession(ConsumerScreen.DOCTOR, history=(ConsumerScreen.DASHBOARD,)),
                focus=ConsumerScreen.DOCTOR.value,
            ),
            entering=True,
        )

        self.assertEqual(state.rows, (coordinate,))
        event = key_event("r", state, detail=source.detail(state))
        self.assertIsNotNone(event)
        assert event is not None
        _review, commands = reduce_consumer_ui(state, event)

        self.assertIs(commands[0].action, ConsumerActionKind.VERIFY_REPAIR)
        self.assertEqual(commands[0].focus, coordinate)
        self.assertNotEqual(commands[0].focus, ConsumerScreen.DOCTOR.value)


if __name__ == "__main__":
    unittest.main()
