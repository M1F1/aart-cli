"""B-095/QA-021: the one-off repository adoption path is operable from the TUI.

The application service already scans one repository without subscribing to it and prepares one
atomic vendored transaction for the selected manifests.  These tests hold the terminal boundary:
screen 46 opens a repository form, the read-only result is selectable, and one review names the
resolved commit and every path before confirmation reaches the adoption port.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date
from unittest import mock

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    RepositoryScanDraft,
    key_event,
    reduce_consumer_ui,
)
from agent_artifacts.application.consumer_views import ConsumerSession, ConsumerSettings
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    maintainer_navigation_targets,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.registry_adoption import PreparedAdoption, RepositoryScan, ScannedArtifact
from agent_artifacts.sources.git import acquire_git_snapshot
from agent_artifacts.tui_consumer import CanonicalScreenSource, frame
from tests.consumer_shell_test import screens
from tests.registry_repository_scan_test import _Lab


def _state(screen: MaintainerScreen, **changes) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        **changes,
    )


_FORM_ROWS = ("url", "ref", "scan")
_COMMIT = "8bf8bac" + "0" * 33


def _scan() -> RepositoryScan:
    artifacts = (
        ScannedArtifact(
            "skill/brainstorming@2.1.0",
            "skill",
            "brainstorming",
            "2.1.0",
            "Explore an idea before implementation.",
            "skills/brainstorming/aart.yaml",
            "sha256:" + "1" * 64,
            "ready",
            ("payload/SKILL.md",),
            True,
        ),
        ScannedArtifact(
            "skill/unfinished@1.0.0",
            "skill",
            "unfinished",
            "1.0.0",
            "An invalid example.",
            "skills/unfinished/aart.yaml",
            "sha256:" + "2" * 64,
            "invalid",
            ("payload/SKILL.md",),
            False,
        ),
    )
    return RepositoryScan(
        "https://github.com/M1F1/superpowers-aart-test.git",
        "main",
        _COMMIT,
        2,
        artifacts,
        mock.Mock(),
        (),
        "aart-test-registry",
    )


class RepositoryAdoptionInteractionTest(unittest.TestCase):
    def test_registry_screen_opens_the_scan_form_with_s(self) -> None:
        state = _state(MaintainerScreen.REGISTRY)
        event = key_event("s", state)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, MaintainerScreen.REPOSITORY_SCAN)
        self.assertIn("Scan Repository", "\n".join(frame(CanonicalScreenSource(screens()), state)))

    def test_the_lettered_route_is_in_the_accepted_navigation_map(self) -> None:
        self.assertIn(
            MaintainerScreen.REPOSITORY_SCAN,
            maintainer_navigation_targets(MaintainerScreen.REGISTRY),
        )
        self.assertEqual(
            maintainer_navigation_targets(MaintainerScreen.REPOSITORY_SCAN),
            (MaintainerScreen.SCAN_RESULT,),
        )
        self.assertEqual(
            maintainer_navigation_targets(MaintainerScreen.SCAN_RESULT),
            (MaintainerScreen.ADOPTION_REVIEW,),
        )
        self.assertEqual(
            maintainer_navigation_targets(MaintainerScreen.ADOPTION_REVIEW),
            (MaintainerScreen.REGISTRY,),
        )

    def test_form_collects_a_url_and_ref_without_describing_a_subscription(self) -> None:
        source = CanonicalScreenSource(screens())
        state = _state(MaintainerScreen.REPOSITORY_SCAN)
        state, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=source.rows(state)),
        )

        drawn = "\n".join(frame(source, state))

        self.assertIn("Repository URL", drawn)
        self.assertIn("Branch or tag", drawn)
        self.assertIn("not saved as a Source", drawn)
        self.assertNotIn("aart ", drawn)

    def test_confirming_the_form_carries_the_exact_draft_to_the_scan(self) -> None:
        draft = RepositoryScanDraft("https://github.com/M1F1/superpowers-aart-test.git", "main")
        state = _state(
            MaintainerScreen.REPOSITORY_SCAN,
            rows=_FORM_ROWS,
            cursor=2,
            repository_scan_draft=draft,
        )

        event = key_event("enter", state)
        self.assertIsNotNone(event)
        assert event is not None
        scanned, commands = reduce_consumer_ui(state, event)

        self.assertIs(scanned.session.screen, MaintainerScreen.SCAN_RESULT)
        self.assertIs(scanned.action, ConsumerActionKind.REPOSITORY_SCAN)
        self.assertEqual(commands[0].repository_scan_draft, draft)

    def test_scan_result_is_selectable_and_a_requests_adoption(self) -> None:
        from agent_artifacts.io.consumer_actions import _project_repository_scan
        from agent_artifacts.tui_consumer import ConsumerScreens

        projected = _project_repository_scan(_scan())
        source = CanonicalScreenSource(
            ConsumerScreens(screens().dashboard, repository_scan=projected)
        )
        state = _state(MaintainerScreen.SCAN_RESULT)
        state, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=source.rows(state)),
        )

        drawn = "\n".join(frame(source, state))
        self.assertEqual(state.rows, ("skill/brainstorming@2.1.0",))
        self.assertIn("skill/brainstorming@2.1.0", drawn)
        self.assertIn("ready", drawn.lower())
        self.assertIn("invalid", drawn.lower())
        self.assertIn("payload/SKILL.md", drawn)

        selected, _ = reduce_consumer_ui(state, key_event(" ", state))  # type: ignore[arg-type]
        event = key_event("a", selected)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.REQUEST_ACTION)
        self.assertIs(event.action, ConsumerActionKind.REPOSITORY_ADOPT)

        reviewed, commands = reduce_consumer_ui(selected, event)
        self.assertIs(reviewed.session.screen, MaintainerScreen.ADOPTION_REVIEW)
        self.assertEqual(commands[0].selection, ("skill/brainstorming@2.1.0",))

    def test_scan_completion_leaves_no_mutation_waiting_for_confirmation(self) -> None:
        requested = _state(
            MaintainerScreen.SCAN_RESULT,
            action=ConsumerActionKind.REPOSITORY_SCAN,
        )

        completed, _ = reduce_consumer_ui(
            requested,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=ConsumerActionKind.REPOSITORY_SCAN,
                review_digest="sha256:" + "4" * 64,
            ),
        )

        self.assertIsNone(completed.action)
        self.assertIs(completed.session.screen, MaintainerScreen.SCAN_RESULT)


class RepositoryAdoptionActionTest(unittest.TestCase):
    def _composed(self, env):
        from agent_artifacts import tui

        composed = tui._canonical_consumer_actions(
            project=str(env.project), user_home=str(env.home), today=tui.date.today()
        )
        assert isinstance(composed, Ok), composed
        return composed.value

    def test_scan_then_adopt_uses_two_ports_and_draws_the_exact_review(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        scan = _scan()
        plan = mock.Mock(review_digest="sha256:" + "3" * 64)
        prepared = PreparedAdoption(
            scan.url,
            scan.ref,
            scan.commit,
            ("skill/brainstorming@2.1.0",),
            (
                "artifacts/skill/brainstorming/2.1.0/artifact.json",
                "artifacts/skill/brainstorming/2.1.0/payload/SKILL.md",
            ),
            plan,
        )
        calls: list[tuple[object, ...]] = []

        class Adoption:
            def prepare(self, observed, selected):
                calls.append(("prepare", observed, selected))
                return Ok(prepared)

            def apply(self, reviewed, digest):
                calls.append(("apply", reviewed, digest))
                return Ok(reviewed)

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            actions = self._composed(env)
            actions._repository_scan = lambda draft: (  # type: ignore[assignment]
                calls.append(("scan", draft)) or Ok(scan)
            )
            actions._repository_adoption = Adoption()  # type: ignore[assignment]
            draft = RepositoryScanDraft(scan.url, scan.ref)

            scanned = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REPOSITORY_SCAN,
                    repository_scan_draft=draft,
                )
            )
            self.assertTrue(scanned.event.review_digest)
            self.assertEqual(scanned.source.screens.repository_scan.commit, scan.commit)

            adoption = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REPOSITORY_ADOPT,
                    selection=("skill/brainstorming@2.1.0",),
                )
            )
            review = adoption.source.screens.adoption_review
            self.assertIsNotNone(review)
            assert review is not None
            self.assertEqual(review.selected, prepared.selected)
            self.assertEqual(review.commit, scan.commit)
            self.assertEqual(review.changed_paths, prepared.changed_paths)
            rendered = "\n".join(frame(adoption.source, _state(MaintainerScreen.ADOPTION_REVIEW)))
            self.assertIn("skill/brainstorming@2.1.0", rendered)
            self.assertIn(scan.commit, rendered)
            for path in prepared.changed_paths:
                self.assertIn(path, rendered)
            self.assertNotIn("aart ", rendered)

            applied = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REPOSITORY_ADOPT,
                    review_digest=prepared.review_digest,
                )
            )

        self.assertEqual(applied.event.kind, ConsumerUiEventKind.ACTION_RECORDED)
        self.assertEqual(calls[0], ("scan", draft))
        self.assertEqual(
            calls[1],
            ("prepare", scan, ("skill/brainstorming@2.1.0",)),
        )
        self.assertEqual(calls[2], ("apply", prepared, prepared.review_digest))


class RepositoryAdoptionCompositionTest(_Lab):
    def test_the_canonical_tui_ports_scan_real_git_and_write_the_reviewed_copy(self) -> None:
        """The public composition joins the already-tested scan/adoption stages without a Source."""

        from agent_artifacts import tui

        home = self.root / "home"
        home.mkdir()
        xdg = {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
        }

        def local_transport(request):
            self.assertFalse(request.allow_local_transport)
            return acquire_git_snapshot(
                replace(
                    request,
                    location=self.author.path.as_uri(),
                    allow_local_transport=True,
                )
            )

        with (
            mock.patch.dict("os.environ", xdg, clear=False),
            mock.patch(
                "agent_artifacts.curation.runtime.acquire_git_snapshot",
                side_effect=local_transport,
            ),
        ):
            composed = tui._canonical_consumer_actions(
                project=str(self.registry),
                user_home=str(home),
                today=date(2026, 9, 8),
            )
            self.assertIsInstance(composed, Ok, composed)
            assert isinstance(composed, Ok)
            actions = composed.value
            scan = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REPOSITORY_SCAN,
                    repository_scan_draft=RepositoryScanDraft(self.url, "main"),
                )
            )
            self.assertEqual(scan.source.screens.repository_scan.commit, self.author.head)
            prepared = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.REPOSITORY_ADOPT,
                    selection=("skill/brainstorming@2.1.0",),
                )
            )
            actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REPOSITORY_ADOPT,
                    review_digest=prepared.event.review_digest,
                )
            )

        adopted = self.registry / "artifacts" / "skill" / "brainstorming" / "2.1.0"
        self.assertTrue((adopted / "artifact.json").is_file())
        self.assertTrue((adopted / "payload" / "SKILL.md").is_file())
        self.assertFalse((adopted / "payload" / "NOTES.md").exists())
        self.assertFalse((self.registry / "aart.config.json").exists())


if __name__ == "__main__":
    unittest.main()
