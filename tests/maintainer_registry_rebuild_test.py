"""`B-099`/`QA-025`: re-running a registry's generated files from the TUI, in order.

Screen 46 could bring a registry into existence (`B-090`) and promote into it, but every later
`lock -> build -> validate -> audit` was still four `aart_maintainer registry ...` commands typed by
hand, in an order the operator had to remember, with flags (`--strict --frozen`) nothing on screen
ever named.  That is the same product problem `B-090` had, one step further along: the ordering is
the knowledge, and a screen that makes somebody hold it in their head has not delivered it.

Screen 46h owns that run.  It offers the whole sequence and each stage on its own, because the two
are genuinely different jobs: after a promotion the maintainer wants all four, and while fixing one
refusal they want `validate` alone.  Both go through one review, and the review states which stages
will run -- so confirming it is confirming a named plan (`D-069`) rather than pressing a key that
means whatever the screen last thought.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest import mock

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
from agent_artifacts.application.consumer_views import ConsumerSession, ConsumerSettings
from agent_artifacts.application.maintainer_views import (
    MaintainerScreen,
    maintainer_navigation_targets,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.registry_bootstrap import (
    REGISTRY_MAINTENANCE_STAGES,
    bootstrap_registry_workspace,
    refresh_registry_workspace,
)
from agent_artifacts.tui_consumer import CanonicalScreenSource, frame
from tests.consumer_shell_test import screens

_PICKER_ROWS = ("all", "lock", "build", "validate", "audit")


def _state(screen, **changes) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        **changes,
    )


def _repository(root: str) -> None:
    os.makedirs(root, exist_ok=True)
    for arguments in (
        ("init", "-q"),
        ("config", "user.email", "maintainer@example.invalid"),
        ("config", "user.name", "Maintainer"),
    ):
        subprocess.run(("git", "-C", root, *arguments), check=True, capture_output=True)


class MaintainerRegistryRebuildInteractionTest(unittest.TestCase):
    def test_the_registry_screen_offers_the_run_it_used_to_make_people_type(self) -> None:
        event = key_event("b", _state(MaintainerScreen.REGISTRY))

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, MaintainerScreen.REGISTRY_REBUILD)

    def test_the_route_exists_in_the_accepted_navigation_map(self) -> None:
        self.assertIn(
            MaintainerScreen.REGISTRY_REBUILD,
            maintainer_navigation_targets(MaintainerScreen.REGISTRY),
        )
        self.assertEqual(
            maintainer_navigation_targets(MaintainerScreen.REGISTRY_REBUILD),
            (MaintainerScreen.REGISTRY_REBUILD_REVIEW,),
        )
        self.assertEqual(
            maintainer_navigation_targets(MaintainerScreen.REGISTRY_REBUILD_REVIEW),
            (MaintainerScreen.REGISTRY,),
        )

    def test_the_screen_offers_the_whole_run_and_each_stage_on_its_own(self) -> None:
        state = _state(MaintainerScreen.REGISTRY_REBUILD)
        source = CanonicalScreenSource(screens())

        self.assertEqual(source.rows(state), _PICKER_ROWS)

        state, _ = reduce_consumer_ui(
            state, ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=source.rows(state))
        )
        drawn = "\n".join(frame(source, state))
        for stage in REGISTRY_MAINTENANCE_STAGES:
            self.assertIn(stage, drawn.lower())
        # `QA-017`: a screen never answers with a command line, which is the whole point here.
        self.assertNotIn("aart ", drawn)
        self.assertNotIn("--frozen", drawn)

    def test_choosing_one_stage_carries_that_choice_into_the_review(self) -> None:
        state = _state(MaintainerScreen.REGISTRY_REBUILD, rows=_PICKER_ROWS, cursor=3)

        event = key_event("enter", state)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.REQUEST_ACTION)
        self.assertIs(event.action, ConsumerActionKind.REGISTRY_REBUILD)

        reviewed, commands = reduce_consumer_ui(state, event)

        self.assertIs(reviewed.session.screen, MaintainerScreen.REGISTRY_REBUILD_REVIEW)
        self.assertIs(reviewed.action, ConsumerActionKind.REGISTRY_REBUILD)
        self.assertEqual(commands[0].focus, "validate")

    def test_a_recorded_run_returns_to_the_registry_screen(self) -> None:
        state = ConsumerUiState(
            ConsumerSession(
                MaintainerScreen.REGISTRY_REBUILD_REVIEW,
                history=(MaintainerScreen.REGISTRY, MaintainerScreen.REGISTRY_REBUILD),
                review_digest="sha256:" + "0" * 64,
            ),
            settings=ConsumerSettings().with_maintainer_mode(True),
            action=ConsumerActionKind.REGISTRY_REBUILD,
        )

        recorded, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=ConsumerActionKind.REGISTRY_REBUILD,
                text="2026-01-01T00:00:00Z",
            ),
        )

        self.assertIs(recorded.session.screen, MaintainerScreen.REGISTRY)
        self.assertIsNone(recorded.action)


class ReviewedActionConfirmationTest(unittest.TestCase):
    """`QA-024`: a review screen whose Enter does nothing is a dead end, not a review.

    Three Maintainer reviews reach the execution boundary the same way, and Enter is the only key
    that gets them there.  Leaving one out means the operator types a form, reads the plan, presses
    the key the screen tells them to press, and nothing happens at all.
    """

    def test_enter_confirms_every_maintainer_review_that_asks_for_it(self) -> None:
        for screen in (
            MaintainerScreen.SOURCE_ADD_REVIEW,
            MaintainerScreen.REGISTRY_INIT_REVIEW,
            MaintainerScreen.REGISTRY_REBUILD_REVIEW,
        ):
            with self.subTest(screen=screen):
                event = key_event("enter", _state(screen))

                self.assertIsNotNone(event, screen)
                assert event is not None
                self.assertIs(event.kind, ConsumerUiEventKind.CONFIRM_ACTION)


class RegistryRefreshTest(unittest.TestCase):
    """The four stages over a registry that already exists, in the one order that means anything."""

    def _registry(self) -> str:
        from tempfile import mkdtemp

        root = os.path.realpath(mkdtemp(prefix="aart-registry-rebuild-"))
        self.addCleanup(lambda: subprocess.run(("rm", "-rf", root), check=False))
        _repository(root)
        created = bootstrap_registry_workspace(
            root=root, registry_id="acme-registry", display_name="ACME Registry"
        )
        assert isinstance(created, Ok) and created.value.passed, created
        return root

    def test_one_run_locks_builds_validates_and_audits_without_initializing_again(self) -> None:
        root = self._registry()
        identity = open(os.path.join(root, "aart-registry.json"), "rb").read()
        os.remove(os.path.join(root, "aart.index.json"))

        report = refresh_registry_workspace(root=root)

        self.assertIsInstance(report, Ok, report)
        assert isinstance(report, Ok)
        self.assertEqual(
            tuple(stage.name for stage in report.value.stages), REGISTRY_MAINTENANCE_STAGES
        )
        self.assertTrue(report.value.passed, report.value.stages)
        self.assertTrue(os.path.isfile(os.path.join(root, "aart.index.json")))
        # `init` is not part of this run: the registry's identity is left exactly as it was.
        self.assertEqual(open(os.path.join(root, "aart-registry.json"), "rb").read(), identity)

    def test_one_named_stage_runs_alone(self) -> None:
        root = self._registry()
        os.remove(os.path.join(root, "aart.index.json"))

        report = refresh_registry_workspace(root=root, stages=("validate",))

        assert isinstance(report, Ok), report
        self.assertEqual(tuple(stage.name for stage in report.value.stages), ("validate",))
        # `build` was not asked for, so nothing rebuilt the index behind the operator's back.
        self.assertFalse(os.path.isfile(os.path.join(root, "aart.index.json")))

    def test_the_named_stages_run_in_the_canonical_order_whatever_order_they_arrive_in(
        self,
    ) -> None:
        root = self._registry()

        report = refresh_registry_workspace(root=root, stages=("audit", "lock"))

        assert isinstance(report, Ok), report
        self.assertEqual(tuple(stage.name for stage in report.value.stages), ("lock", "audit"))

    def test_a_workspace_that_is_not_a_registry_is_refused_before_anything_runs(self) -> None:
        from tempfile import mkdtemp

        root = os.path.realpath(mkdtemp(prefix="aart-registry-absent-"))
        self.addCleanup(lambda: subprocess.run(("rm", "-rf", root), check=False))
        _repository(root)

        refused = refresh_registry_workspace(root=root)

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertFalse(os.path.exists(os.path.join(root, "aart.lock.json")))
        self.assertNotIn("aart ", "\n".join(refused.diagnostics[0].interactive))

    def test_a_stage_nobody_named_is_refused_rather_than_quietly_ignored(self) -> None:
        root = self._registry()

        for stages in ((), ("init",), ("publish",)):
            with self.subTest(stages=stages):
                refused = refresh_registry_workspace(root=root, stages=stages)

                self.assertIsInstance(refused, Err, stages)

    def test_a_failing_gate_stops_the_run_and_says_which_one(self) -> None:
        from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
        from agent_artifacts.io import registry_bootstrap
        from agent_artifacts.registry_commands.model import (
            RegistryQualityCheck,
            RegistryQualityReport,
        )

        root = self._registry()
        failing = RegistryQualityReport(
            (
                RegistryQualityCheck(
                    "validate",
                    (
                        Diagnostic(
                            DiagnosticCode("test-validate-failed"),
                            Severity.ERROR,
                            "the manifest does not describe this payload",
                        ),
                    ),
                ),
            )
        )
        with mock.patch.object(
            registry_bootstrap, "validate_registry_workspace", return_value=Ok(failing)
        ):
            report = refresh_registry_workspace(root=root)

        assert isinstance(report, Ok), report
        self.assertFalse(report.value.passed)
        self.assertEqual(
            tuple(stage.name for stage in report.value.stages), ("lock", "build", "validate")
        )
        self.assertIn(
            "the manifest does not describe this payload", "\n".join(report.value.stages[-1].lines)
        )


class MaintainerRegistryRebuildActionTest(unittest.TestCase):
    """The action boundary: reviewed by name, run once, and drawn as stages afterwards."""

    def _composed(self, env):
        from agent_artifacts import tui

        composed = tui._canonical_consumer_actions(
            project=str(env.project), user_home=str(env.home), today=tui.date.today()
        )
        assert isinstance(composed, Ok), composed
        return composed.value

    def _prepare(self, actions, focus: str):
        return actions.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.REGISTRY_REBUILD,
                focus=focus,
            )
        )

    def test_the_review_names_the_stages_it_will_run_and_no_command_line(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            _repository(str(env.project))
            created = bootstrap_registry_workspace(
                root=str(env.project), registry_id="acme-registry", display_name="ACME Registry"
            )
            assert isinstance(created, Ok) and created.value.passed, created
            actions = self._composed(env)
            prepared = self._prepare(actions, "all")

        self.assertTrue(prepared.event.review_digest)
        notice = "\n".join(prepared.source.screens.notice)
        for stage in REGISTRY_MAINTENANCE_STAGES:
            self.assertIn(stage, notice)
        self.assertNotIn("aart ", notice)
        self.assertIn("push", notice)

    def test_two_different_stage_choices_are_two_different_plans(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            _repository(str(env.project))
            created = bootstrap_registry_workspace(
                root=str(env.project), registry_id="acme-registry", display_name="ACME Registry"
            )
            assert isinstance(created, Ok) and created.value.passed, created
            actions = self._composed(env)
            everything = self._prepare(actions, "all")
            one = self._prepare(actions, "validate")

        self.assertTrue(everything.event.review_digest)
        self.assertNotEqual(everything.event.review_digest, one.event.review_digest)

    def test_a_project_with_no_registry_is_refused_on_the_review(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            actions = self._composed(env)
            refused = self._prepare(actions, "all")

        self.assertEqual(refused.event.review_digest, "")
        self.assertNotIn("aart ", "\n".join(refused.source.screens.notice))

    def test_one_confirmation_really_rebuilds_this_project_registry(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(env.xdg, clear=False):
            _repository(str(env.project))
            created = bootstrap_registry_workspace(
                root=str(env.project), registry_id="acme-registry", display_name="ACME Registry"
            )
            assert isinstance(created, Ok) and created.value.passed, created
            index = os.path.join(str(env.project), "aart.index.json")
            os.remove(index)
            actions = self._composed(env)
            prepared = self._prepare(actions, "all")
            self.assertTrue(prepared.event.review_digest)
            finished = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REGISTRY_REBUILD,
                    review_digest=prepared.event.review_digest,
                )
            )
            rebuilt = os.path.isfile(index)

        self.assertTrue(finished.event.text, "the run recorded nothing")
        self.assertTrue(rebuilt, "the index the run exists to write is missing")
        notice = "\n".join(finished.source.screens.notice)
        for stage in REGISTRY_MAINTENANCE_STAGES:
            self.assertIn(f"  {stage}: done", notice)
        self.assertNotIn("aart ", notice)


class MaintainerRegistryRebuildShellTest(unittest.TestCase):
    """The whole path a person actually walks: four key presses, no command line at all.

    `QA-024` is why this exists as a shell test rather than three more adapter tests. Every piece
    of the initialization flow was individually correct and confirmed by tests, and Enter on its
    review still did nothing, because no test had ever pressed the keys in order.
    """

    def test_four_key_presses_rebuild_the_registry_of_this_project(self) -> None:
        import os as _os
        from unittest import mock as _mock

        from agent_artifacts import tui
        from agent_artifacts.tui_consumer import run_consumer_shell
        from tests.configured_install_command_e2e_test import _environment
        from tests.consumer_shell_test import ENTER, FakeTerminal

        with _environment() as env, _mock.patch.dict(env.xdg, clear=False):
            _repository(str(env.project))
            created = bootstrap_registry_workspace(
                root=str(env.project), registry_id="acme-registry", display_name="ACME Registry"
            )
            assert isinstance(created, Ok) and created.value.passed, created
            index = _os.path.join(str(env.project), "aart.index.json")
            _os.remove(index)
            composed = tui._canonical_consumer_actions(
                project=str(env.project), user_home=str(env.home), today=tui.date.today()
            )
            assert isinstance(composed, Ok), composed
            handler = composed.value
            terminal = FakeTerminal(ord("b"), ENTER, ENTER, ord("q"), ord("y"))
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
            rebuilt = _os.path.isfile(index)

        drawn = "\n".join(line for screen in terminal.frames for line in screen)
        self.assertTrue(rebuilt, "the run the maintainer confirmed did not write the index")
        for stage in REGISTRY_MAINTENANCE_STAGES:
            self.assertIn(f"  {stage}: done", drawn)
        self.assertNotIn("aart_maintainer", drawn)


if __name__ == "__main__":
    unittest.main()
