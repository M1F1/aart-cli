"""Screens 44–45 use the one reducer and one key interpreter for promotion execution."""

from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

from agent_artifacts.application.candidate_validation import validate_candidate
from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    project_dashboard,
)
from agent_artifacts.application.maintainer_promotion import (
    prepare_candidate_promotion_transaction,
)
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    project_maintainer_registry_commit,
    project_maintainer_registry_validation,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.native_tree import SnapshotOrigin, SourceSnapshot
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, _reload, frame
from tests.maintainer_promotion_execution_test import _approved
from tests.maintainer_promotion_test import _bundle


def _prepared():
    workspace = SourceSnapshot(SnapshotOrigin.LOCAL, ())
    bundle = _bundle()
    policy = EffectivePolicy()
    prepared = prepare_candidate_promotion_transaction(
        bundle,
        validate_candidate(bundle, policy=policy),
        policy,
        _approved(workspace),
        workspace,
    )
    assert isinstance(prepared, Ok), prepared
    return prepared.value


def _on(screen: MaintainerScreen, *, action=None, digest=None) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen, review_digest=digest),
        settings=ConsumerSettings().with_maintainer_mode(True),
        focus="a" * 64,
        action=action,
    )


class PromotionShellExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.prepared = _prepared()
        self.source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                promotion_validation=project_maintainer_registry_validation(self.prepared),
                promotion_commit=project_maintainer_registry_commit(self.prepared),
            )
        )

    def test_enter_on_screen_43_requests_one_typed_promotion_in_the_chosen_mode(self) -> None:
        state = dataclasses.replace(
            _on(MaintainerScreen.REGISTRY_DIFF),
            promotion_mode=PromotionMode.REFERENCED,
        )

        event = key_event("enter", state)
        self.assertEqual(
            event,
            ConsumerUiEvent(
                ConsumerUiEventKind.REQUEST_ACTION,
                action=ConsumerActionKind.CANDIDATE_PROMOTION,
            ),
        )
        assert event is not None
        moved, commands = reduce_consumer_ui(state, event)

        self.assertIs(moved.session.screen, MaintainerScreen.REGISTRY_VALIDATION)
        self.assertIn(
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.CANDIDATE_PROMOTION,
                focus="a" * 64,
                promotion_mode=PromotionMode.REFERENCED,
            ),
            commands,
        )

    def test_screen_44_draws_the_composed_validation_and_enter_opens_45(self) -> None:
        state = _reload(
            self.source,
            _on(MaintainerScreen.REGISTRY_VALIDATION),
            entering=True,
        )

        self.assertIn("Registry validation: Passed", "\n".join(frame(self.source, state)))
        self.assertIs(self.source.detail(state), MaintainerScreen.REGISTRY_COMMIT)

    def test_drawing_44_and_45_opens_no_file(self) -> None:
        with mock.patch("builtins.open", side_effect=AssertionError("draw performed IO")):
            for screen in (
                MaintainerScreen.REGISTRY_VALIDATION,
                MaintainerScreen.REGISTRY_COMMIT,
            ):
                with self.subTest(screen=screen):
                    state = _reload(self.source, _on(screen), entering=True)
                    self.assertTrue(frame(self.source, state))

    def test_screen_45_confirms_the_prepared_digest_and_stays_for_the_result(self) -> None:
        state = _on(
            MaintainerScreen.REGISTRY_COMMIT,
            action=ConsumerActionKind.CANDIDATE_PROMOTION,
            digest=str(self.prepared.review_digest),
        )

        event = key_event("enter", state)
        self.assertEqual(event, ConsumerUiEvent(ConsumerUiEventKind.CONFIRM_ACTION))
        assert event is not None
        confirmed, commands = reduce_consumer_ui(state, event)
        self.assertEqual(confirmed, state)
        self.assertEqual(
            commands,
            (
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.CANDIDATE_PROMOTION,
                    focus="a" * 64,
                    review_digest=str(self.prepared.review_digest),
                ),
            ),
        )

        recorded, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=ConsumerActionKind.CANDIDATE_PROMOTION,
                text="written",
            ),
        )
        self.assertIs(recorded.session.screen, MaintainerScreen.REGISTRY_COMMIT)
        self.assertIsNone(recorded.action)


if __name__ == "__main__":
    unittest.main()
