"""CP-23 task 05: TUI promotion ends at the local commit; publication is manual Git (D-249).

The owner reversed D-228 for the terminal surface. Screen 45 reviews and writes the exact local
transaction and then says what happens next outside AART: push the Registry branch, get it
reviewed and merged where the Registry requires that, update the local checkout, and run Registry
Sync to observe the approved state. No key on any state of screen 45 can prepare or execute a push,
and the supported `aart registry push` CLI contract is untouched.
"""

from __future__ import annotations

import dataclasses
import inspect
import string
import unittest

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts import tui_consumer
from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import PresentationProfile
from agent_artifacts.application.maintainer_promotion import CandidatePromotionExecutionResult
from agent_artifacts.application.maintainer_views import (
    MaintainerRegistryCommitView,
    MaintainerScreen,
    project_maintainer_registry_commit,
)
from agent_artifacts.io.consumer_actions import LocalConsumerActions
from agent_artifacts.tui_layout import CONTENT_MEASURE
from agent_artifacts.tui_maintainer import render_maintainer_registry_commit
from tests.maintainer_promotion_shell_execution_test import _on, _prepared

_STEPS = (
    "push this Registry branch",
    "pull request",
    "update this local checkout",
    "run Registry Sync",
)

_KEYS = st.one_of(
    st.sampled_from(("up", "down", "enter", "escape", "backspace", " ")),
    st.sampled_from(tuple(string.ascii_letters + string.digits + string.punctuation)),
)


def _completed(prepared) -> CandidatePromotionExecutionResult:
    return CandidatePromotionExecutionResult(
        prepared.review_digest,
        prepared.registry_snapshot,
        prepared.plan.next_workspace_digest,
        prepared.plan.changed_paths,
        prepared.approved_version_count,
        "c" * 40,
        "Promote mcp/github-mcp@1.0.0 to company",
    )


def _committed(**fields) -> ConsumerUiState:
    return dataclasses.replace(
        _on(MaintainerScreen.REGISTRY_COMMIT), registry_commit_applied=True, **fields
    )


class RegistryCommitScreenExplainsManualPublicationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.prepared = _prepared()
        self.ready = project_maintainer_registry_commit(self.prepared)
        self.applied = project_maintainer_registry_commit(
            self.prepared, result=_completed(self.prepared)
        )

    def test_before_the_commit_enter_commits_and_no_push_is_promised(self) -> None:
        for profile in PresentationProfile:
            with self.subTest(profile=profile):
                drawn = "\n".join(render_maintainer_registry_commit(self.ready, profile))

                self.assertIn("Enter commits this exact local transaction.", drawn)
                self.assertIn("AART does not push", drawn)
                self.assertNotIn("separate explicit action", drawn)
                self.assertNotIn("press p", drawn)

    def test_after_the_commit_the_manual_steps_are_listed_in_order(self) -> None:
        for profile in PresentationProfile:
            with self.subTest(profile=profile):
                lines = render_maintainer_registry_commit(self.applied, profile)
                drawn = "\n".join(lines)

                self.assertIn("Approved registry state written locally", drawn)
                self.assertIn("Subscribers cannot see this commit yet", drawn)
                positions = [drawn.find(step) for step in _STEPS]
                self.assertTrue(all(position >= 0 for position in positions), positions)
                self.assertEqual(positions, sorted(positions))
                self.assertTrue(all(len(line) <= CONTENT_MEASURE for line in lines))

    def test_nothing_after_the_commit_calls_it_published_or_offers_a_push(self) -> None:
        drawn = "\n".join(
            render_maintainer_registry_commit(self.applied, PresentationProfile.VERBOSE)
        )

        for claim in ("Published", "published", "press p", "Enter pushes", "Publication"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, drawn)
        # Source Sync reads authoring repositories; it is not how an approved Registry is observed.
        self.assertNotIn("Source Sync", drawn)

    def test_the_commit_view_and_renderer_carry_no_publication_target(self) -> None:
        fields = {field.name for field in dataclasses.fields(MaintainerRegistryCommitView)}
        projection = set(inspect.signature(project_maintainer_registry_commit).parameters)
        renderer = set(inspect.signature(render_maintainer_registry_commit).parameters)

        self.assertFalse({name for name in fields if "publication" in name})
        self.assertEqual(projection, {"prepared", "result"})
        self.assertEqual(renderer, {"view", "profile"})

    def test_initialization_does_not_promise_a_push_from_registry_commit(self) -> None:
        intro = " ".join(tui_consumer._REGISTRY_INIT_INTRO)

        self.assertNotIn("can publish", intro)
        self.assertNotIn("review branch", intro)
        self.assertIn("Nothing is pushed and nothing is merged", intro)
        self.assertIn("in Git yourself", intro)


class NoTuiKeyReachesAPushTest(unittest.TestCase):
    def test_the_ui_vocabulary_has_no_publication_action_event_or_field(self) -> None:
        names = (
            *(item.name for item in ConsumerActionKind),
            *(item.name for item in ConsumerUiEventKind),
            *(field.name.upper() for field in dataclasses.fields(ConsumerUiState)),
            *(field.name.upper() for field in dataclasses.fields(ConsumerUiCommand)),
        )

        self.assertEqual([name for name in names if "PUBLICATION" in name], [])

    def test_the_tui_action_handler_accepts_no_push_or_remote_port(self) -> None:
        parameters = set(inspect.signature(LocalConsumerActions).parameters)

        self.assertNotIn("registry_publication", parameters)
        self.assertNotIn("registry_default_branch", parameters)

    def test_p_on_the_committed_screen_is_not_a_key_and_the_legend_does_not_offer_it(
        self,
    ) -> None:
        state = _committed()

        legend = key_bindings(state, detail=None)

        self.assertIsNone(key_event("p", state))
        self.assertIsNone(key_event("P", state))
        self.assertNotIn("p", {binding.key.lower() for binding in legend})
        self.assertFalse(any("ublish" in binding.label for binding in legend))
        self.assertIn(("Enter", "Continue"), {(item.key, item.label) for item in legend})

    @given(keys=st.lists(_KEYS, max_size=12))
    def test_no_key_sequence_after_the_commit_prepares_or_executes_anything(
        self, keys: list[str]
    ) -> None:
        state = _committed()
        for key in keys:
            if state.session.screen is not MaintainerScreen.REGISTRY_COMMIT or state.quit_pending:
                break
            event = key_event(key, state)
            if event is None:
                continue
            self.assertNotIn(
                event.kind,
                (ConsumerUiEventKind.REQUEST_ACTION, ConsumerUiEventKind.CONFIRM_ACTION),
                key,
            )
            state, commands = reduce_consumer_ui(state, event)
            self.assertFalse(
                {command.kind for command in commands}
                & {ConsumerUiCommandKind.PREPARE_ACTION, ConsumerUiCommandKind.EXECUTE_ACTION},
                key,
            )


if __name__ == "__main__":
    unittest.main()
