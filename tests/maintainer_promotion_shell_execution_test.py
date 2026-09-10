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
    RegistryPublicationDraft,
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
        self.assertTrue(recorded.registry_commit_applied)

    def test_applied_screen_45_collects_the_publication_target_and_requests_review(self) -> None:
        state = dataclasses.replace(
            _on(MaintainerScreen.REGISTRY_COMMIT),
            rows=("publication-remote", "publication-branch", "publish"),
            cursor=1,
            registry_commit_applied=True,
            registry_publication_configuring=True,
            registry_publication_draft=RegistryPublicationDraft("origin", "review/registry"),
        )

        event = key_event("enter", state)
        self.assertEqual(event, ConsumerUiEvent(ConsumerUiEventKind.MOVE, text="down"))
        assert event is not None
        on_publish, _ = reduce_consumer_ui(state, event)
        event = key_event("enter", on_publish)
        self.assertEqual(
            event,
            ConsumerUiEvent(
                ConsumerUiEventKind.REQUEST_ACTION,
                action=ConsumerActionKind.REGISTRY_PUBLICATION,
            ),
        )
        assert event is not None
        reviewing, commands = reduce_consumer_ui(on_publish, event)

        self.assertIs(reviewing.session.screen, MaintainerScreen.REGISTRY_COMMIT)
        self.assertIs(reviewing.action, ConsumerActionKind.REGISTRY_PUBLICATION)
        self.assertEqual(
            commands,
            (
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REGISTRY_PUBLICATION,
                    registry_publication_draft=RegistryPublicationDraft(
                        "origin", "review/registry"
                    ),
                ),
            ),
        )

    def test_publication_receipt_stays_on_screen_45_then_enter_opens_registry(self) -> None:
        state = dataclasses.replace(
            _on(
                MaintainerScreen.REGISTRY_COMMIT,
                action=ConsumerActionKind.REGISTRY_PUBLICATION,
                digest=str(self.prepared.review_digest),
            ),
            registry_commit_applied=True,
        )

        recorded, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=ConsumerActionKind.REGISTRY_PUBLICATION,
                text="published",
            ),
        )
        self.assertTrue(recorded.registry_publication_completed)
        self.assertIsNone(recorded.action)
        self.assertIs(recorded.session.screen, MaintainerScreen.REGISTRY_COMMIT)

        event = key_event("enter", recorded)
        self.assertEqual(
            event,
            ConsumerUiEvent(
                ConsumerUiEventKind.NAVIGATE,
                screen=MaintainerScreen.REGISTRY,
            ),
        )

    def test_refused_publication_target_stays_on_the_filled_commit_screen(self) -> None:
        state = dataclasses.replace(
            _on(
                MaintainerScreen.REGISTRY_COMMIT,
                action=ConsumerActionKind.REGISTRY_PUBLICATION,
            ),
            registry_commit_applied=True,
            registry_publication_draft=RegistryPublicationDraft("origin", "main"),
        )

        refused, commands = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.REGISTRY_PUBLICATION,
            ),
        )

        self.assertIs(refused.session.screen, MaintainerScreen.REGISTRY_COMMIT)
        self.assertIsNone(refused.action)
        self.assertTrue(refused.registry_commit_applied)
        self.assertEqual(
            RegistryPublicationDraft("origin", "main"), refused.registry_publication_draft
        )
        self.assertEqual((), commands)


class CommittedRegistryScreenIsNotAFormTest(unittest.TestCase):
    """A written commit that has not been sent to publication is a screen, not a form.

    Screen 45 becomes a form only once the operator presses `p`. Before that it is an ordinary
    reading screen and has to answer the global keys like every other one. Interpreting keys for
    the publication form whenever the commit merely *exists* swallowed all of them -- `q`
    included -- and a screen that cannot be quit is a hang, not a misprint: the shell asks for
    the next key forever.
    """

    def _committed(self, **overrides) -> ConsumerUiState:
        return dataclasses.replace(
            _on(MaintainerScreen.REGISTRY_COMMIT),
            registry_commit_applied=True,
            **overrides,
        )

    def test_quit_still_quits_before_the_publication_form_is_opened(self) -> None:
        event = key_event("q", self._committed())

        self.assertEqual(event, ConsumerUiEvent(ConsumerUiEventKind.QUIT))

    def test_the_global_keys_still_answer_before_the_form_is_opened(self) -> None:
        state = self._committed()

        for key, kind in (
            ("?", ConsumerUiEventKind.HELP),
            ("v", ConsumerUiEventKind.TOGGLE_PROFILE),
        ):
            with self.subTest(key=key):
                event = key_event(key, state)

                self.assertIsNotNone(event, f"{key} was swallowed by the publication form")
                assert event is not None
                self.assertIs(event.kind, kind)

    def test_p_opens_the_form_and_then_typing_reaches_the_draft(self) -> None:
        opened = key_event("p", self._committed())

        self.assertEqual(
            opened, ConsumerUiEvent(ConsumerUiEventKind.CONFIGURE_REGISTRY_PUBLICATION)
        )

        typing = self._committed(
            registry_publication_configuring=True,
            rows=("publication-remote", "publication-branch", "publish"),
            cursor=1,
        )
        event = key_event("r", typing)

        self.assertEqual(
            event,
            ConsumerUiEvent(ConsumerUiEventKind.EDIT_REGISTRY_PUBLICATION, key="branch", text="r"),
        )

    def test_the_form_owns_q_once_it_is_open_because_a_branch_may_contain_one(self) -> None:
        """The swallow is right here and wrong before: `q` is a legal character in a branch."""

        typing = self._committed(
            registry_publication_configuring=True,
            rows=("publication-remote", "publication-branch", "publish"),
            cursor=1,
        )

        event = key_event("q", typing)

        self.assertEqual(
            event,
            ConsumerUiEvent(ConsumerUiEventKind.EDIT_REGISTRY_PUBLICATION, key="branch", text="q"),
        )

    def test_the_legend_offers_the_key_the_screen_tells_the_reader_to_press(self) -> None:
        """`QA-058` inverted: a key that works but is advertised nowhere is as unusable as one
        that is advertised and does not work. The body says `press p`, so the legend must too."""

        from agent_artifacts.application.consumer_ui import key_bindings

        legend = key_bindings(self._committed(), detail=None)

        self.assertIn(
            "p",
            {binding.key.lower() for binding in legend},
            [binding.key for binding in legend],
        )

    def test_the_legend_drops_it_again_once_publication_is_done(self) -> None:
        from agent_artifacts.application.consumer_ui import key_bindings

        legend = key_bindings(self._committed(registry_publication_completed=True), detail=None)

        self.assertNotIn("p", {binding.key.lower() for binding in legend})


if __name__ == "__main__":
    unittest.main()
