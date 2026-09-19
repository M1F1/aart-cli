"""`QA-098`: the registry this project publishes is a place in a life, not a sentence.

The operator's third manual run found screen 46 saying *what a registry is* and never *where this
one has got to*: no row to put a cursor on, nothing naming the repository, the branch, whether that
branch exists on the remote, or whether anything was waiting to be pushed. Their own frame made the
registry a row carrying its name and its sha -- so two checkouts of one name on different branches
or remotes are told apart -- with the rest under the key that opens explanations.

What this module holds is the projection: which state the checkout is in, derived from what a read
of it established rather than from what a command would return if run now. Whether a *remote* branch
exists is a network answer and drawing a frame does no I/O, so the fact projected here is the
checkout's own knowledge of its remote, which `[u] Check upstream` is the key that refreshes.
"""

from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from agent_artifacts.application.consumer_ui import ConsumerUiState
from agent_artifacts.application.consumer_views import (
    ConsumerSession,
    ConsumerSettings,
    PresentationProfile,
    project_dashboard,
)
from agent_artifacts.application.maintainer_views import (
    REGISTRY_WORKSPACE_READY_ROW,
    REGISTRY_WORKSPACE_ROW,
    MaintainerPublicationState,
    MaintainerRegistryWorkspaceView,
    MaintainerScreen,
    MaintainerViews,
    project_maintainer_candidates,
    project_maintainer_dashboard,
    project_registry_workspace,
)
from agent_artifacts.tui_consumer import CanonicalScreenSource, ConsumerScreens, frame
from agent_artifacts.tui_maintainer import (
    maintainer_workspace_detail,
    maintainer_workspace_row,
)


class RegistryWorkspaceProjectionTest(TestCase):
    def test_a_checkout_nothing_could_be_read_from_says_so_rather_than_guessing(self) -> None:
        view = project_registry_workspace("manual-registry")

        self.assertIs(view.state, MaintainerPublicationState.UNOBSERVED)
        self.assertEqual(view.name, "manual-registry")
        self.assertIsNone(view.commit)

    def test_a_branch_the_checkout_knows_no_remote_for_has_never_been_published(self) -> None:
        view = project_registry_workspace(
            "manual-registry",
            commit="eed6c4f",
            origin="https://git.example.test/acme/registry.git",
            branch="registry-main",
        )

        self.assertIs(view.state, MaintainerPublicationState.UNPUBLISHED)
        self.assertEqual(view.branch, "registry-main")
        self.assertIsNone(view.remote_branch)

    def test_commits_the_remote_branch_does_not_have_are_work_waiting_to_be_pushed(self) -> None:
        view = project_registry_workspace(
            "manual-registry",
            commit="eed6c4f",
            origin="https://git.example.test/acme/registry.git",
            branch="registry-main",
            remote_branch="origin/registry-main",
            unpushed=3,
        )

        self.assertIs(view.state, MaintainerPublicationState.AHEAD)
        self.assertEqual(view.unpushed, 3)

    def test_a_branch_level_with_its_remote_has_nothing_waiting(self) -> None:
        view = project_registry_workspace(
            "manual-registry",
            commit="eed6c4f",
            branch="registry-main",
            remote_branch="origin/registry-main",
            unpushed=0,
        )

        self.assertIs(view.state, MaintainerPublicationState.PUBLISHED)

    def test_a_remote_branch_whose_distance_is_unknown_is_not_claimed_either_way(self) -> None:
        """Knowing a remote branch exists is not knowing where this checkout stands against it."""

        view = project_registry_workspace(
            "manual-registry",
            commit="eed6c4f",
            branch="registry-main",
            remote_branch="origin/registry-main",
        )

        self.assertIs(view.state, MaintainerPublicationState.UNOBSERVED)
        self.assertEqual(view.remote_branch, "origin/registry-main")

    def test_a_registry_workspace_needs_a_name(self) -> None:
        with self.assertRaises(ValueError):
            project_registry_workspace("")

    def test_a_count_of_unpushed_commits_is_never_negative(self) -> None:
        with self.assertRaises(ValueError):
            project_registry_workspace("r", commit="a", remote_branch="origin/main", unpushed=-1)


class RegistryWorkspaceFrameTest(TestCase):
    """What the row says, and what `[v]` opens under it."""

    def _view(self, **changes: object) -> MaintainerRegistryWorkspaceView:
        base = dict(
            commit="eed6c4f",
            origin="https://git.example.test/acme/registry.git",
            branch="registry-main",
        )
        base.update(changes)
        return project_registry_workspace("manual-registry", **base)  # type: ignore[arg-type]

    def test_the_row_is_the_name_and_the_sha_that_tells_two_checkouts_apart(self) -> None:
        self.assertEqual(
            maintainer_workspace_row(self._view(), selected=True), "> manual-registry  eed6c4f"
        )

    def test_a_checkout_with_no_commit_still_has_a_row_to_stand_on(self) -> None:
        row = maintainer_workspace_row(project_registry_workspace("manual-registry"))

        self.assertEqual(row, "  manual-registry")

    def test_the_description_names_the_repository_and_the_branch(self) -> None:
        described = maintainer_workspace_detail(self._view())

        self.assertIn("Remote: origin (https://git.example.test/acme/registry.git)", described)
        self.assertIn("Branch: registry-main", described)

    def test_a_branch_never_pushed_says_so_and_lists_why_push_is_unavailable(self) -> None:

        described = maintainer_workspace_detail(self._view())

        self.assertIn("Remote branch: none — this branch has not been pushed yet.", described)
        self.assertIn("Push unavailable:", described)
        self.assertIn("- publication readiness has not been established", described)

    def test_work_waiting_to_be_pushed_is_counted_rather_than_hinted_at(self) -> None:
        described = maintainer_workspace_detail(
            self._view(remote_branch="origin/registry-main", unpushed=3)
        )

        self.assertIn("Remote branch: origin/registry-main", described)
        self.assertIn("3 commits here are not on origin/registry-main yet.", described)

    def test_one_commit_waiting_is_counted_in_the_singular(self) -> None:
        described = maintainer_workspace_detail(
            self._view(remote_branch="origin/registry-main", unpushed=1)
        )

        self.assertIn("1 commit here is not on origin/registry-main yet.", described)

    def test_nothing_waiting_says_nobody_has_to_push_anything(self) -> None:
        described = maintainer_workspace_detail(
            self._view(remote_branch="origin/registry-main", unpushed=0)
        )

        self.assertIn("Nothing here is waiting to be pushed.", described)
        self.assertIn("Push unavailable:", described)

    def test_a_ready_workspace_names_the_exact_commit_content_and_target(self) -> None:
        described = maintainer_workspace_detail(
            self._view(
                root="/lab/registry",
                revision="a" * 40,
                content_digest="sha256:" + "b" * 64,
                publication_review_digest="sha256:" + "c" * 64,
                push_blockers=(),
            )
        )

        self.assertIn("Workspace: /lab/registry", described)
        self.assertIn(f"Local HEAD: {'a' * 40}", described)
        self.assertIn(f"Local canonical content: sha256:{'b' * 64}", described)
        self.assertIn("Push: ready — review target origin/registry-main.", described)

    def test_a_remote_branch_nobody_has_measured_against_is_not_reported_either_way(self) -> None:
        described = maintainer_workspace_detail(self._view(remote_branch="origin/registry-main"))

        self.assertIn(
            "Whether anything is waiting to be pushed was not established; "
            "press u to check upstream.",
            described,
        )

    def test_who_may_subscribe_to_what_is_said_where_the_branch_is(self) -> None:
        """*"maintainer moze subskrybowac po remote'a brancha ale user tylko po main'a"*."""

        described = maintainer_workspace_detail(self._view())

        self.assertIn(
            "A maintainer may subscribe to this branch; everyone else subscribes to the "
            "repository's main.",
            described,
        )


class RegistryMaintainerScreenTest(TestCase):
    """Screen 46 with the registry this project publishes on it, read off the real composition."""

    def _state(self, *, verbose: bool = False, cursor: int = 0, workspace: bool = True):
        profile = PresentationProfile.VERBOSE if verbose else PresentationProfile.FAST
        views = MaintainerViews(
            project_maintainer_dashboard(()),
            (),
            project_maintainer_candidates(()),
            (),
            registry_workspace=(
                project_registry_workspace(
                    "manual-registry",
                    commit="eed6c4f",
                    origin="https://git.example.test/acme/registry.git",
                    branch="registry-main",
                )
                if workspace
                else None
            ),
        )
        source = CanonicalScreenSource(
            ConsumerScreens(project_dashboard((), registry_count=0), maintainer=views)
        )
        state = ConsumerUiState(
            ConsumerSession(MaintainerScreen.REGISTRY, profile=profile),
            settings=ConsumerSettings(profile=profile).with_maintainer_mode(True),
            workspace="/lab/registry",
        )
        return source, replace(state, rows=source.rows(state), cursor=cursor)

    def test_the_registry_this_project_publishes_is_a_row(self) -> None:
        """It had been prose, so there was nothing on the screen to put a cursor on."""

        source, state = self._state()

        self.assertEqual(state.rows[0], REGISTRY_WORKSPACE_ROW)
        self.assertEqual(source.actions(state)[0], "> manual-registry  eed6c4f")

    def test_a_project_that_publishes_nothing_has_no_such_row(self) -> None:
        source, state = self._state(workspace=False)

        self.assertNotIn(REGISTRY_WORKSPACE_ROW, state.rows)

    def test_where_the_registry_stands_is_what_the_cursor_opens(self) -> None:
        source, state = self._state(verbose=True)
        drawn = "\n".join(frame(source, state))

        self.assertIn("Remote: origin (https://git.example.test/acme/registry.git)", drawn)
        self.assertIn("Branch: registry-main", drawn)
        self.assertIn("Push unavailable:", drawn)

    def test_fast_keeps_all_of_that_collapsed(self) -> None:
        """`QA-070`: `[v]` opens every explanation, and this is no exception."""

        source, state = self._state(verbose=False)
        drawn = "\n".join(frame(source, state))

        self.assertNotIn("Repository:", drawn)
        self.assertIn("> manual-registry  eed6c4f", drawn)

    def test_enter_on_the_registry_row_opens_nothing_it_is_not(self) -> None:
        """Screen 46's Enter assembles a bulk promotion, which this row is not the subject of."""

        source, state = self._state()

        self.assertIsNone(source.detail(state))

    def test_only_a_ready_workspace_row_carries_the_push_identity(self) -> None:
        source, state = self._state()
        workspace = project_registry_workspace(
            "manual-registry",
            commit="eed6c4f",
            branch="registry-main",
            root="/lab/registry",
            revision="a" * 40,
            content_digest="sha256:" + "b" * 64,
            publication_review_digest="sha256:" + "c" * 64,
            push_blockers=(),
        )
        assert source._screens.maintainer is not None
        ready_source = CanonicalScreenSource(
            ConsumerScreens(
                project_dashboard((), registry_count=0),
                maintainer=replace(source._screens.maintainer, registry_workspace=workspace),
            )
        )
        ready_state = replace(state, rows=())
        ready_state = replace(ready_state, rows=ready_source.rows(ready_state), cursor=0)

        self.assertEqual((REGISTRY_WORKSPACE_READY_ROW,), ready_state.rows)
