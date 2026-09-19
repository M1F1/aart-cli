"""CP-26.18: promotion ends locally and Push belongs only to screen 46's workspace row.

The owner reversed D-228 for the terminal surface. Screen 45 reviews and writes the exact local
transaction and then says what happens next outside AART: push the Registry branch, get it
reviewed and merged where the Registry requires that, update the local checkout, and run Registry
Sync to observe the approved state. No key on any state of screen 45 can prepare or execute a push,
and the supported `aart-cli registry push` CLI contract is untouched.
"""

from __future__ import annotations

import dataclasses
import inspect
import unittest
from types import SimpleNamespace
from unittest import mock

from aart_cli import tui_consumer
from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    key_bindings,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import PresentationProfile, project_dashboard
from aart_cli.application.maintainer_promotion import CandidatePromotionExecutionResult
from aart_cli.application.maintainer_views import (
    REGISTRY_WORKSPACE_READY_ROW,
    MaintainerRegistryCommitView,
    MaintainerScreen,
    project_maintainer_registry_commit,
    project_registry_workspace,
)
from aart_cli.domain.publication import RegistryCommitOrigin
from aart_cli.domain.result import Ok
from aart_cli.io.consumer_actions import LocalConsumerActions
from aart_cli.io.maintainer_promotion import PreparedConfiguredCandidatePromotion
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    ConsumerScreens,
    _reload,
    compose_frame,
)
from aart_cli.tui_layout import CONTENT_MEASURE
from aart_cli.tui_maintainer import render_maintainer_registry_commit
from tests.maintainer_promotion_shell_execution_test import _on, _prepared
from tests.screen_cases import screen_cases

_STEPS = (
    "push this Registry branch",
    "pull request",
    "update this local checkout",
    "run Registry Sync",
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


class RegistryMaintainerOwnsPushTest(unittest.TestCase):
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

    def test_p_on_a_ready_local_workspace_opens_the_separate_push_review(self) -> None:
        state = dataclasses.replace(
            _on(MaintainerScreen.REGISTRY),
            rows=(REGISTRY_WORKSPACE_READY_ROW, "connected-registry"),
            cursor=0,
        )

        event = key_event("p", state)
        self.assertEqual(
            event,
            ConsumerUiEvent(
                ConsumerUiEventKind.REQUEST_ACTION,
                action=ConsumerActionKind.REGISTRY_PUSH,
            ),
        )
        assert event is not None
        moved, commands = reduce_consumer_ui(state, event)

        self.assertIs(moved.session.screen, MaintainerScreen.REGISTRY_PUSH)
        self.assertEqual(commands[0].kind, ConsumerUiCommandKind.PREPARE_ACTION)
        self.assertIs(commands[0].action, ConsumerActionKind.REGISTRY_PUSH)

    def test_p_is_absent_on_a_connected_snapshot_or_unready_workspace(self) -> None:
        for row in ("connected-registry", "registry-workspace"):
            with self.subTest(row=row):
                state = dataclasses.replace(_on(MaintainerScreen.REGISTRY), rows=(row,), cursor=0)
                self.assertIsNone(key_event("p", state))
                self.assertNotIn("Push", {item.label for item in key_bindings(state)})

    def test_default_branch_review_accepts_an_edited_new_branch_before_confirmation(self) -> None:
        state = dataclasses.replace(
            _on(
                MaintainerScreen.REGISTRY_PUSH,
                action=ConsumerActionKind.REGISTRY_PUSH,
                digest="sha256:" + "a" * 64,
            ),
            rows=("branch", "continue"),
            publication_branch="aart-cli/registry-update",
        )

        edited, commands = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_PUBLICATION_BRANCH,
                text="review/registry-update",
            ),
        )

        self.assertEqual((), commands)
        self.assertEqual("review/registry-update", edited.publication_branch)
        self.assertIsNone(edited.session.review_digest)
        continued = dataclasses.replace(edited, cursor=1)
        event = key_event("enter", continued)
        self.assertEqual(
            event,
            ConsumerUiEvent(
                ConsumerUiEventKind.REQUEST_ACTION,
                action=ConsumerActionKind.REGISTRY_PUSH,
            ),
        )
        assert event is not None
        _prepared, prepare_commands = reduce_consumer_ui(continued, event)
        self.assertEqual("review/registry-update", prepare_commands[0].publication_branch)

    def test_each_producing_action_carries_its_branch_suggestion_to_push(self) -> None:
        cases = (
            (
                ConsumerActionKind.REGISTRY_INIT,
                MaintainerScreen.REGISTRY_INIT_REVIEW,
                "",
                RegistryCommitOrigin.INIT_REGISTRY,
                "aart-cli/init-registry",
            ),
            (
                ConsumerActionKind.REGISTRY_REBUILD,
                MaintainerScreen.REGISTRY_REBUILD_REVIEW,
                "",
                RegistryCommitOrigin.REBUILD_REGISTRY,
                "aart-cli/rebuild-registry",
            ),
            (
                ConsumerActionKind.CANDIDATE_PROMOTION,
                MaintainerScreen.REGISTRY_COMMIT,
                "github-mcp-1.0.0",
                RegistryCommitOrigin.PROMOTE,
                "aart-cli/promote-github-mcp-1.0.0",
            ),
            (
                ConsumerActionKind.BULK_PROMOTION,
                MaintainerScreen.REGISTRY_COMMIT,
                "",
                RegistryCommitOrigin.BULK_PROMOTE,
                "aart-cli/bulk-promote",
            ),
        )
        for action, screen, subject, origin, expected in cases:
            with self.subTest(action=action):
                state = _on(screen, action=action)
                recorded, _commands = reduce_consumer_ui(
                    state,
                    ConsumerUiEvent(
                        ConsumerUiEventKind.ACTION_RECORDED,
                        action=action,
                        text="2026-09-19T12:00:00+00:00",
                        registry_commit_subject=subject,
                    ),
                )
                self.assertIs(recorded.registry_commit_origin, origin)
                self.assertEqual(recorded.registry_commit_subject, subject)
                ready = dataclasses.replace(
                    recorded,
                    session=dataclasses.replace(recorded.session, screen=MaintainerScreen.REGISTRY),
                    rows=(REGISTRY_WORKSPACE_READY_ROW,),
                    cursor=0,
                )
                event = key_event("p", ready)
                assert event is not None
                _moved, commands = reduce_consumer_ui(ready, event)
                self.assertEqual(expected, commands[0].suggested_branch)

    def test_push_preparation_prefers_the_session_suggestion_and_keeps_the_restart_fallback(
        self,
    ) -> None:
        workspace = project_registry_workspace(
            "company",
            commit="a" * 12,
            branch="main",
            root="/registry",
            revision="a" * 40,
            content_digest="sha256:" + "b" * 64,
            publication_review_digest="sha256:" + "c" * 64,
            push_blockers=(),
        )
        for suggested, expected in (
            ("aart-cli/init-registry", "aart-cli/init-registry"),
            ("", "aart-cli/registry-update"),
        ):
            with self.subTest(suggested=suggested):
                actions = LocalConsumerActions.__new__(LocalConsumerActions)
                actions._context = SimpleNamespace(host=SimpleNamespace(project_root="/registry"))
                actions._pending = None
                actions._pending_action = None
                actions.source = lambda **_views: SimpleNamespace()
                command = ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REGISTRY_PUSH,
                    suggested_branch=suggested,
                )

                with mock.patch(
                    "aart_cli.io.consumer_actions.read_registry_workspace",
                    return_value=workspace,
                ):
                    actions._prepare_registry_push(command)

                assert actions._pending is not None
                self.assertEqual(expected, actions._pending.command.branch.value)

    def test_single_promotion_execution_records_the_artifact_and_version_as_its_subject(
        self,
    ) -> None:
        transaction = _prepared()
        pending = PreparedConfiguredCandidatePromotion(transaction, "/registry", "/data")
        actions = LocalConsumerActions.__new__(LocalConsumerActions)
        actions._context = SimpleNamespace(
            effective=object(),
            host=SimpleNamespace(project_root="/registry"),
            maintainer=None,
        )
        actions._data_root = "/data"
        actions._promotion_transaction = None
        actions._promotion_result = None
        actions._now = lambda: SimpleNamespace(timestamp=lambda: 0)
        actions._moment = lambda: ("2026-09-19T12:00:00+00:00", object())
        actions._recorded = mock.Mock(return_value=object())

        def replace_context(context, **changes):
            fields = vars(context).copy()
            fields.update(changes)
            return SimpleNamespace(**fields)

        command = ConsumerUiCommand(
            ConsumerUiCommandKind.EXECUTE_ACTION,
            action=ConsumerActionKind.CANDIDATE_PROMOTION,
            review_digest=str(transaction.review_digest),
        )
        with (
            mock.patch(
                "aart_cli.io.consumer_actions.complete_configured_candidate_promotion",
                return_value=Ok(_completed(transaction)),
            ),
            mock.patch(
                "aart_cli.io.consumer_actions.read_maintainer_views",
                return_value=Ok(object()),
            ),
            mock.patch("aart_cli.io.consumer_actions.replace", side_effect=replace_context),
        ):
            actions._execute_candidate_promotion(command, pending)

        self.assertEqual(
            "github-mcp-1.0.0",
            actions._recorded.call_args.kwargs["registry_commit_subject"],
        )


class RegistryPushReviewFrameTest(unittest.TestCase):
    """What screen 46j says, and which block says it.

    The facts live in the view's status and the rows in the actions block, because §167 admits no
    labelled value among the rows. Splitting them is why nothing here asserts the drawn string of
    the whole screen: the recorded frame matrix already holds the shape, and it would go on
    passing over a review that had quietly stopped saying what is being pushed -- which is the
    only thing that makes "Enter pushes this exact commit" a sentence the reader can act on.
    """

    def _case(self):
        return next(
            case for case in screen_cases() if case.screen is MaintainerScreen.REGISTRY_PUSH
        )

    def test_the_actions_block_is_the_two_rows_and_nothing_else(self) -> None:
        case = self._case()

        blocks = compose_frame(case.source, case.state)

        self.assertEqual(
            blocks.actions, ("> Review branch: aart-cli/registry-update", "  Continue")
        )

    def test_the_status_states_what_would_be_pushed_and_where(self) -> None:
        case = self._case()

        said = " ".join(line.strip() for line in compose_frame(case.source, case.state).status)

        for fact in (
            "Registry: manual-registry",
            "Workspace: /lab/registry",
            f"Exact commit: {'a' * 40}",
            f"Canonical content: sha256:{'b' * 64}",
            "Remote: origin",
            "Target branch: aart-cli/registry-update",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, said)
        self.assertIn("The current branch is the one subscribers read", said)

    def test_editing_the_field_moves_the_target_the_status_names(self) -> None:
        case = self._case()

        edited, _commands = reduce_consumer_ui(
            case.state,
            ConsumerUiEvent(
                ConsumerUiEventKind.EDIT_PUBLICATION_BRANCH, text="review/registry-update"
            ),
        )
        said = " ".join(compose_frame(case.source, edited).status)

        self.assertIn("Target branch: review/registry-update", said)
        self.assertNotIn("Target branch: aart-cli/registry-update", said)

    def test_a_checkout_already_on_its_own_branch_has_no_row_and_still_states_the_facts(
        self,
    ) -> None:
        """There is nothing left to choose, so §167 gives the screen no actions block at all."""

        case = self._case()
        assert case.source._screens.maintainer is not None
        workspace = case.source._screens.maintainer.registry_workspace
        assert workspace is not None
        source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                maintainer=dataclasses.replace(
                    case.source._screens.maintainer,
                    registry_workspace=dataclasses.replace(
                        workspace, branch="aart-cli/registry-update"
                    ),
                ),
            )
        )
        state = _reload(
            source,
            dataclasses.replace(case.state, rows=(), cursor=0, publication_branch=""),
            entering=True,
        )

        blocks = compose_frame(source, state)

        self.assertEqual((), state.rows)
        self.assertEqual((), blocks.actions)
        said = " ".join(blocks.status)
        self.assertIn("Target branch: aart-cli/registry-update", said)
        self.assertIn(f"Exact commit: {'a' * 40}", said)
        self.assertNotIn("subscribers read", said)


if __name__ == "__main__":
    unittest.main()
