"""CP-23 task 14: what the audit found each frame saying twice, saying about keys, or naming wrongly.

Ready counted stored credentials twice, once from the plan's effects and once from its inputs, and
claimed a credential would be stored even where the plan stores none. Credential Details and the
installed details screens closed their facts with an `Actions: …` sentence the legend already
states -- and §167's Artifact Details rule calls such a sentence insufficient. Review 24a was titled
`Review Credential Action` whether it reviewed a replacement, a deletion, or showed what Verify
found. And a trail five places deep ran past the content measure, so the frame's first line
wrapped.
"""

from __future__ import annotations

import dataclasses
import unittest

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    InstalledHealth,
    MemberHealth,
    PresentationProfile,
    project_credential_record,
    project_installed_collection,
)
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    _reload,
    compose_frame,
    render_credential,
    render_installed_artifact,
    render_installed_collection,
    render_ready,
)
from agent_artifacts.tui_layout import CONTENT_MEASURE
from tests.consumer_install_flow_shell_test import plan_view, screens
from tests.consumer_shell_test import installed
from tests.consumer_views_test import _credential_input
from tests.credential_action_rows_test import _prepared, _reviewing
from tests.frame_contract import frame_violations

_STORED = "credential(s) stored securely"


class ReadyCountsEachChangeOnceTest(unittest.TestCase):
    def test_a_credential_the_plan_stores_is_counted_once(self) -> None:
        drawn = "\n".join(render_ready(plan_view(), PresentationProfile.FAST))

        self.assertEqual(drawn.count(_STORED), 1)

    def test_a_credential_the_plan_does_not_store_is_not_said_to_be_stored(self) -> None:
        view = plan_view()
        kept = tuple(item for item in view.effects if not item.kind.startswith("store-"))
        drawn = "\n".join(
            render_ready(dataclasses.replace(view, effects=kept), PresentationProfile.FAST)
        )

        self.assertNotIn(_STORED, drawn)


class NoActionsSentenceTest(unittest.TestCase):
    """The legend says what can be done; a sentence restating it is not a control (§167)."""

    def test_details_screens_state_facts_and_leave_the_actions_to_the_legend(self) -> None:
        _, _, observation = _credential_input()
        record = project_credential_record(observation, dependants=("public/mcp/github",))
        collection = project_installed_collection(
            "company/collection/developer@1.0.0",
            (MemberHealth("public/mcp/github", InstalledHealth.READY),),
        )
        for profile in PresentationProfile:
            for drawn in (
                render_credential(record, profile),
                render_installed_artifact(installed("public/mcp/jira@2.2.0", "update"), profile),
                render_installed_collection(collection, profile),
            ):
                with self.subTest(first=drawn[0], profile=profile):
                    self.assertFalse(any(line.startswith("Actions:") for line in drawn))


class ReviewTitleTest(unittest.TestCase):
    def test_24a_is_named_for_what_it_reviews(self) -> None:
        for row, title in (
            ("replace", "Review Replacement"),
            ("delete", "Review Deletion"),
            ("verify", "Verification"),
        ):
            with self.subTest(row=row):
                source, state = _reviewing(row)
                state = _prepared(state)

                trail = compose_frame(source, state).trail[0]

                self.assertTrue(trail.endswith(f" / {title}"), trail)
                self.assertEqual(frame_violations(source, state), ())


class TrailFitsTheMeasureTest(unittest.TestCase):
    def _trail(self, *history: ConsumerScreen, screen: ConsumerScreen) -> str:
        source = CanonicalScreenSource(screens())
        state = ConsumerUiState(ConsumerSession(screen, history=history))
        return compose_frame(source, _reload(source, state, entering=True)).trail[0]

    def test_a_deep_trail_elides_the_middle_and_keeps_where_esc_goes(self) -> None:
        trail = self._trail(
            ConsumerScreen.DASHBOARD,
            ConsumerScreen.CREDENTIALS,
            ConsumerScreen.USER_INPUT_DETAILS,
            ConsumerScreen.CREDENTIAL_DETAILS,
            ConsumerScreen.CREDENTIAL_ACTION,
            screen=ConsumerScreen.CREDENTIAL_REVIEW,
        )

        self.assertLessEqual(len(trail), CONTENT_MEASURE)
        self.assertTrue(trail.startswith("AART / User Variables And Credentials / … / "), trail)
        self.assertIn(" / Credential Action / ", trail)

    def test_a_trail_that_fits_is_drawn_whole(self) -> None:
        trail = self._trail(
            ConsumerScreen.DASHBOARD,
            ConsumerScreen.CREDENTIALS,
            screen=ConsumerScreen.USER_INPUT_DETAILS,
        )

        self.assertEqual(
            trail, "AART / User Variables And Credentials / Artifact Variables And Credentials"
        )


if __name__ == "__main__":
    unittest.main()
