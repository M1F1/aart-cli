"""`QA-033`/`B-101`: a run that refused is finished, and the screen has to say so.

The operator confirmed a Registry rebuild, `lock` refused, and the session stayed on
`Review Rebuild` -- title, `press Enter to start it` header and an `Enter Confirm` footer all
intact over a plan the action adapter had already discarded.  Pressing the advertised key could
only answer `nothing was prepared for this action; review it again`, which is true and useless: the
plan is gone because the run happened, not because the review was never made.

The defect is not the refusal and not this one action.  Every confirmed action reaches
`_failed`, which emits an event the reducer reads as "nothing was recorded" and therefore as no
transition at all.  So the claim held here is general: once an attempted run stops, the review it
was confirmed from becomes a terminal result, Enter leaves for the screen that owns the run, and
nothing on screen offers a confirmation any more.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
)
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.tui_consumer import CanonicalScreenSource, frame
from tests.consumer_shell_test import screens

#: One confirmed action per review screen that owns one, with the screen its run belongs to.
CONFIRMED_RUNS: tuple[tuple[ConsumerActionKind, object, object], ...] = (
    (
        ConsumerActionKind.REGISTRY_REBUILD,
        MaintainerScreen.REGISTRY_REBUILD_REVIEW,
        MaintainerScreen.REGISTRY,
    ),
    (
        ConsumerActionKind.REGISTRY_INIT,
        MaintainerScreen.REGISTRY_INIT_REVIEW,
        MaintainerScreen.REGISTRY,
    ),
    (
        ConsumerActionKind.SOURCE_ADD,
        MaintainerScreen.SOURCE_ADD_REVIEW,
        MaintainerScreen.SOURCES,
    ),
    (
        ConsumerActionKind.REGISTRY_ADD,
        ConsumerScreen.REGISTRY_REVIEW,
        ConsumerScreen.REGISTRIES,
    ),
)


def _confirmed(action: ConsumerActionKind, screen) -> ConsumerUiState:
    """The state a session is in at the moment its confirmed run is executing."""

    return ConsumerUiState(
        ConsumerSession(screen, review_digest="sha256:" + "0" * 64),
        settings=ConsumerSettings().with_maintainer_mode(True),
        action=action,
    )


def _refused(action: ConsumerActionKind, screen) -> ConsumerUiState:
    state, _ = reduce_consumer_ui(
        _confirmed(action, screen),
        ConsumerUiEvent(ConsumerUiEventKind.ACTION_FAILED, action=action),
    )
    return state


class FailedActionTerminalStateTest(unittest.TestCase):
    def test_a_refused_run_is_not_still_waiting_to_be_confirmed(self) -> None:
        for action, screen, _ in CONFIRMED_RUNS:
            with self.subTest(action=action, screen=screen):
                refused = _refused(action, screen)

                self.assertIsNone(refused.action)
                self.assertIs(refused.failed_action, action)
                self.assertIs(refused.session.screen, screen)

    def test_the_footer_stops_advertising_a_confirmation_nothing_can_answer(self) -> None:
        for action, screen, _ in CONFIRMED_RUNS:
            with self.subTest(action=action, screen=screen):
                labels = {binding.label for binding in key_bindings(_refused(action, screen))}

                self.assertNotIn("Confirm", labels)

    def test_enter_leaves_the_finished_run_for_the_screen_that_owns_it(self) -> None:
        for action, screen, owner in CONFIRMED_RUNS:
            with self.subTest(action=action, screen=screen):
                refused = _refused(action, screen)

                event = key_event("enter", refused)

                self.assertIsNotNone(event)
                assert event is not None
                self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
                self.assertIs(event.screen, owner)

    def test_leaving_the_result_makes_the_next_review_a_review_again(self) -> None:
        """The terminal state belongs to one attempt, not to the screen for the rest of a session."""

        for action, screen, owner in CONFIRMED_RUNS:
            with self.subTest(action=action, screen=screen):
                refused = _refused(action, screen)

                left, _ = reduce_consumer_ui(
                    refused, ConsumerUiEvent(ConsumerUiEventKind.NAVIGATE, screen=owner)
                )

                self.assertIsNone(left.failed_action)

    def test_a_review_that_has_not_run_still_asks_for_its_confirmation(self) -> None:
        """`QA-024` must survive this: an unexecuted review is not a finished one."""

        for action, screen, _ in CONFIRMED_RUNS:
            with self.subTest(action=action, screen=screen):
                waiting = _confirmed(action, screen)

                event = key_event("enter", waiting)

                self.assertIsNotNone(event)
                assert event is not None
                self.assertIs(event.kind, ConsumerUiEventKind.CONFIRM_ACTION)
                self.assertIn("Confirm", {binding.label for binding in key_bindings(waiting)})

    def test_a_recorded_run_is_not_a_failed_one(self) -> None:
        """A run that did record something keeps moving to its result screen unchanged."""

        recorded, _ = reduce_consumer_ui(
            _confirmed(
                ConsumerActionKind.REGISTRY_REBUILD,
                MaintainerScreen.REGISTRY_REBUILD_REVIEW,
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=ConsumerActionKind.REGISTRY_REBUILD,
                text="2026-01-01T00:00:00Z",
            ),
        )

        self.assertIs(recorded.session.screen, MaintainerScreen.REGISTRY)
        self.assertIsNone(recorded.action)
        self.assertIsNone(recorded.failed_action)


class FailedActionFrameTest(unittest.TestCase):
    """What the operator sees, which is where `QA-033` was actually reported from."""

    def _frame(self, action: ConsumerActionKind, screen) -> tuple[str, ...]:
        refused_screens = replace(
            screens(),
            notice=("registry rebuild stopped at lock: required file is missing",),
        )
        return frame(CanonicalScreenSource(refused_screens), _refused(action, screen))

    def test_the_screen_stops_telling_somebody_to_start_a_run_that_already_stopped(self) -> None:
        drawn = self._frame(
            ConsumerActionKind.REGISTRY_REBUILD, MaintainerScreen.REGISTRY_REBUILD_REVIEW
        )

        self.assertNotIn("Press Enter to start this run.", drawn)
        self.assertNotIn("Enter Confirm", " ".join(drawn))

    def test_the_heading_says_the_attempt_is_over(self) -> None:
        drawn = self._frame(
            ConsumerActionKind.REGISTRY_REBUILD, MaintainerScreen.REGISTRY_REBUILD_REVIEW
        )

        self.assertIn("did not run", drawn[0])

    def test_the_reason_it_stopped_is_still_on_the_screen(self) -> None:
        """The refusal is why the screen did not move; losing it would be the worse defect."""

        drawn = self._frame(
            ConsumerActionKind.REGISTRY_REBUILD, MaintainerScreen.REGISTRY_REBUILD_REVIEW
        )

        self.assertIn(
            "registry rebuild stopped at lock: required file is missing",
            " ".join(drawn),
        )

    def test_a_review_nobody_has_confirmed_still_reads_as_a_review(self) -> None:
        """`QA-090` moved where a review asks: the legend offers the key, not a sentence."""

        drawn = frame(
            CanonicalScreenSource(screens()),
            _confirmed(
                ConsumerActionKind.REGISTRY_REBUILD,
                MaintainerScreen.REGISTRY_REBUILD_REVIEW,
            ),
        )

        self.assertIn("[Enter] Confirm", " ".join(drawn))
        self.assertNotIn("This run stopped", " ".join(drawn))
        self.assertNotIn("did not run", drawn[0])


class FailedActionShellTest(unittest.TestCase):
    """The keys in order, through the real shell loop, over a run that genuinely stops.

    `QA-024` is why this exists: every piece of the flow can be individually right and the loop can
    still refuse the update, because the loop is the only place that decides what an execution is
    allowed to answer with. An attempted run that stopped is one of those answers.
    """

    def test_a_run_that_stops_leaves_a_result_the_operator_can_walk_out_of(self) -> None:
        import os
        from unittest import mock

        from agent_artifacts import tui
        from agent_artifacts.domain.result import Ok
        from agent_artifacts.io.registry_bootstrap import bootstrap_registry_workspace
        from agent_artifacts.tui_consumer import run_consumer_shell
        from tests.configured_install_command_e2e_test import _environment
        from tests.consumer_shell_test import ENTER, FakeTerminal
        from tests.maintainer_registry_rebuild_test import _repository

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            _repository(str(env.project))
            created = bootstrap_registry_workspace(
                root=str(env.project), registry_id="acme-registry", display_name="ACME Registry"
            )
            assert isinstance(created, Ok) and created.value.passed, created
            # The marker still exists, so the review is prepared exactly as it would be; the run
            # itself is what cannot complete.
            marker = os.path.join(str(env.project), "aart-registry.json")
            with open(marker, "w", encoding="utf-8") as handle:
                handle.write("{ this is not a registry manifest")
            composed = tui._canonical_consumer_actions(
                project=str(env.project), user_home=str(env.home), today=tui.date.today()
            )
            assert isinstance(composed, Ok), composed
            handler = composed.value

            terminal = FakeTerminal(ord("b"), ENTER, ENTER, ENTER, ord("q"), ord("y"))
            run_consumer_shell(
                handler.source(),
                terminal,
                state=ConsumerUiState(
                    ConsumerSession(MaintainerScreen.REGISTRY),
                    settings=ConsumerSettings().with_maintainer_mode(True),
                ),
                action_handler=handler,
                settings_writer=handler.save_settings,
            )

            stopped = next("\n".join(item) for item in terminal.frames if "did not run" in item[0])

            self.assertIn("This run stopped", stopped)
            self.assertIn("lock: refused", stopped)
            self.assertIn("[Enter] Back to list", stopped)
            self.assertNotIn("Enter Confirm", stopped)
            self.assertNotIn("press Enter to start it", stopped)
            # The fourth Enter is the way out the screen advertises, and it has to work.
            self.assertIn("AART / Registry Maintainer", terminal.frames[-1][0])


if __name__ == "__main__":
    unittest.main()
