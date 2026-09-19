"""B-090/QA-016: a Maintainer can create the registry the rest of the mode needs, in the TUI.

Maintainer Mode could promote into a registry and audit one, but had no way to bring one into
existence: the operator left for a terminal, ran five separate `aart-cli registry` commands in the
right order, and came back.  Screen 46 now owns that: one form, one review, and one run of
init -> lock -> build -> validate -> audit against the project checkout.

Two boundaries are the point of the slice rather than incidental to it.  The run is local: it may
create a commit when the operator asked for one, and it never pushes or merges, because publishing
a registry is a decision a person makes with the repository's own review process.  And it stays
inside the TUI: `QA-017` forbids a screen that answers with a command line, so the review states
the five stages in prose and the result states what each one did.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest import mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    ConsumerUiState,
    RegistryInitDraft,
    key_event,
    reduce_consumer_ui,
)
from aart_cli.application.consumer_views import ConsumerSession, ConsumerSettings
from aart_cli.application.maintainer_views import (
    MaintainerScreen,
    maintainer_navigation_targets,
)
from aart_cli.domain.result import Err, Ok
from aart_cli.io.registry_bootstrap import (
    REGISTRY_BOOTSTRAP_STAGES,
    RegistryBootstrapReport,
    RegistryBootstrapStage,
    bootstrap_registry_workspace,
    registry_identity_refusal,
)
from aart_cli.tui_consumer import CanonicalScreenSource, frame
from aart_cli.tui_layout import CONTENT_MEASURE
from tests.consumer_shell_test import screens


def _state(screen, **changes) -> ConsumerUiState:
    return ConsumerUiState(
        ConsumerSession(screen),
        settings=ConsumerSettings().with_maintainer_mode(True),
        **changes,
    )


_FORM_ROWS = ("id", "name", "commit", "initialize")

#: What screen 46a can put in a text row: one printable key at a time, never a line break.
_TYPEABLE = " \t-abcMANUAL/.0"


def _repository(root: str) -> None:
    os.makedirs(root, exist_ok=True)
    for arguments in (
        ("init", "-q"),
        ("config", "user.email", "maintainer@example.invalid"),
        ("config", "user.name", "Maintainer"),
    ):
        subprocess.run(("git", "-C", root, *arguments), check=True, capture_output=True)


class MaintainerRegistryInitInteractionTest(unittest.TestCase):
    def test_the_registry_screen_offers_a_real_initialization_route(self) -> None:
        state = _state(MaintainerScreen.REGISTRY)

        event = key_event("n", state)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.NAVIGATE)
        self.assertIs(event.screen, MaintainerScreen.REGISTRY_INIT)

    def test_the_route_exists_in_the_accepted_navigation_map(self) -> None:
        self.assertIn(
            MaintainerScreen.REGISTRY_INIT,
            maintainer_navigation_targets(MaintainerScreen.REGISTRY),
        )
        self.assertEqual(
            maintainer_navigation_targets(MaintainerScreen.REGISTRY_INIT),
            (MaintainerScreen.REGISTRY_INIT_REVIEW,),
        )
        self.assertEqual(
            maintainer_navigation_targets(MaintainerScreen.REGISTRY_INIT_REVIEW),
            (MaintainerScreen.REGISTRY,),
        )

    def test_the_form_names_what_a_registry_needs_and_what_it_will_not_do(self) -> None:
        state = _state(MaintainerScreen.REGISTRY_INIT)
        source = CanonicalScreenSource(screens())
        state, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(ConsumerUiEventKind.SET_ROWS, rows=source.rows(state)),
        )

        drawn = "\n".join(frame(source, state))

        self.assertIn("Registry ID", drawn)
        self.assertIn("Display name", drawn)
        self.assertNotIn("Usage reporting", drawn)
        self.assertIn("Local commit", drawn)
        self.assertNotIn("aart ", drawn)
        self.assertIn("pushed", drawn)

    def test_space_chooses_whether_a_local_commit_is_made(self) -> None:
        state = _state(MaintainerScreen.REGISTRY_INIT, rows=_FORM_ROWS, cursor=2)

        self.assertIs(state.registry_init_draft.commit, False)
        state, _ = reduce_consumer_ui(state, key_event(" ", state))  # type: ignore[arg-type]
        self.assertIs(state.registry_init_draft.commit, True)
        state, _ = reduce_consumer_ui(state, key_event(" ", state))  # type: ignore[arg-type]
        self.assertIs(state.registry_init_draft.commit, False)

    def test_typing_an_identifier_stays_text_rather_than_firing_hotkeys(self) -> None:
        state = _state(MaintainerScreen.REGISTRY_INIT, rows=_FORM_ROWS)

        for character in "acme-registry":
            state, _ = reduce_consumer_ui(state, key_event(character, state))  # type: ignore[arg-type]

        self.assertEqual(state.registry_init_draft.registry_id, "acme-registry")
        self.assertEqual(state.cursor, 0)

    def test_confirming_the_form_carries_the_exact_draft_into_one_review(self) -> None:
        draft = RegistryInitDraft("acme-registry", "ACME Registry", True)
        state = _state(
            MaintainerScreen.REGISTRY_INIT,
            rows=_FORM_ROWS,
            registry_init_draft=draft,
            cursor=3,
        )

        event = key_event("enter", state)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIs(event.kind, ConsumerUiEventKind.REQUEST_ACTION)

        reviewed, commands = reduce_consumer_ui(state, event)

        self.assertIs(reviewed.session.screen, MaintainerScreen.REGISTRY_INIT_REVIEW)
        self.assertIs(reviewed.action, ConsumerActionKind.REGISTRY_INIT)
        self.assertEqual(commands[0].registry_init_draft, draft)
        self.assertIs(commands[0].action, ConsumerActionKind.REGISTRY_INIT)

    def test_a_recorded_run_returns_to_the_registry_screen(self) -> None:
        """The result of creating a registry is the registry screen, not the form it was typed on."""

        state = ConsumerUiState(
            ConsumerSession(
                MaintainerScreen.REGISTRY_INIT_REVIEW,
                history=(MaintainerScreen.REGISTRY, MaintainerScreen.REGISTRY_INIT),
                review_digest="sha256:" + "0" * 64,
            ),
            settings=ConsumerSettings().with_maintainer_mode(True),
            action=ConsumerActionKind.REGISTRY_INIT,
        )

        recorded, _ = reduce_consumer_ui(
            state,
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=ConsumerActionKind.REGISTRY_INIT,
                text="2026-01-01T00:00:00Z",
            ),
        )

        self.assertIs(recorded.session.screen, MaintainerScreen.REGISTRY)
        self.assertIsNone(recorded.action)


class RegistryBootstrapTest(unittest.TestCase):
    """The five stages, run in order over a real checkout, and nothing published."""

    def _workspace(self) -> str:
        from tempfile import mkdtemp

        root = os.path.realpath(mkdtemp(prefix="aart-registry-init-"))
        self.addCleanup(lambda: subprocess.run(("rm", "-rf", root), check=False))
        _repository(root)
        return root

    def test_one_run_initializes_locks_builds_validates_and_audits(self) -> None:
        root = self._workspace()

        report = bootstrap_registry_workspace(
            root=root, registry_id="acme-registry", display_name="ACME Registry"
        )

        self.assertIsInstance(report, Ok, report)
        assert isinstance(report, Ok)
        self.assertEqual(
            tuple(stage.name for stage in report.value.stages), REGISTRY_BOOTSTRAP_STAGES
        )
        self.assertTrue(report.value.passed, report.value.stages)
        for name in (
            "aart-cli-registry.json",
            "aart-cli-source.json",
            "registry/index.json",
            "registry/snapshot.json",
        ):
            self.assertTrue(os.path.isfile(os.path.join(root, name)), name)
        # `CP-26.5`: the bootstrap writes the approved representation and only it.
        for retired in ("aart.lock.json", "aart.index.json"):
            self.assertFalse(os.path.exists(os.path.join(root, retired)), retired)

    def test_nothing_is_committed_unless_the_operator_asked_for_it(self) -> None:
        root = self._workspace()

        report = bootstrap_registry_workspace(
            root=root, registry_id="acme-registry", display_name="ACME Registry"
        )

        assert isinstance(report, Ok)
        self.assertEqual(report.value.revision, "")
        log = subprocess.run(
            ("git", "-C", root, "log", "--oneline"), capture_output=True, text=True, check=False
        )
        self.assertEqual(log.stdout.strip(), "")

    def test_a_requested_commit_is_local_and_never_pushed_or_merged(self) -> None:
        root = self._workspace()
        from aart_cli.io import registry_bootstrap

        calls: list[tuple[str, ...]] = []
        real = registry_bootstrap._git

        def recorded(target: str, *arguments: str):
            calls.append(arguments)
            return real(target, *arguments)

        with mock.patch.object(registry_bootstrap, "_git", recorded):
            report = bootstrap_registry_workspace(
                root=root,
                registry_id="acme-registry",
                display_name="ACME Registry",
                commit=True,
            )

        assert isinstance(report, Ok), report
        self.assertTrue(report.value.passed, report.value.stages)
        self.assertTrue(report.value.revision)
        subjects = subprocess.run(
            ("git", "-C", root, "log", "--format=%s"),
            capture_output=True,
            text=True,
            check=False,
        ).stdout.splitlines()
        self.assertEqual(subjects, ["Initialize AART registry: ACME Registry"])
        self.assertEqual(
            [arguments for arguments in calls if arguments and arguments[0] in ("push", "merge")],
            [],
        )

    def test_asking_for_a_commit_outside_a_checkout_refuses_before_anything_is_written(
        self,
    ) -> None:
        from tempfile import mkdtemp

        root = os.path.realpath(mkdtemp(prefix="aart-registry-plain-"))
        self.addCleanup(lambda: subprocess.run(("rm", "-rf", root), check=False))

        refused = bootstrap_registry_workspace(
            root=root, registry_id="acme-registry", display_name="ACME Registry", commit=True
        )

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertFalse(os.path.exists(os.path.join(root, "aart-cli-registry.json")))
        self.assertNotIn("aart ", "\n".join(refused.diagnostics[0].interactive))

    def test_a_stage_refusing_mid_run_stops_the_ones_after_it(self) -> None:
        """Fail-fast is the ordering's whole point: build over an unlocked registry is a lie."""

        from aart_cli.curation.model import CurationAction
        from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
        from aart_cli.io import registry_bootstrap

        root = self._workspace()
        real = registry_bootstrap.load_local_curation_service

        def refusing_lock(target: str):
            loaded = real(target)
            assert isinstance(loaded, Ok)
            service = loaded.value
            prepare = service.prepare

            def guarded(request):
                if request.action is CurationAction.LOCK:
                    return Err(
                        (
                            Diagnostic(
                                DiagnosticCode("test-lock-refused"),
                                Severity.ERROR,
                                "upstream reference is unreachable",
                            ),
                        )
                    )
                return prepare(request)

            service.prepare = guarded  # type: ignore[method-assign]
            return loaded

        with mock.patch.object(registry_bootstrap, "load_local_curation_service", refusing_lock):
            report = bootstrap_registry_workspace(
                root=root, registry_id="acme-registry", display_name="ACME Registry"
            )

        assert isinstance(report, Ok), report
        self.assertFalse(report.value.passed)
        self.assertEqual(tuple(stage.name for stage in report.value.stages), ("init", "lock"))
        self.assertIn("unreachable", "\n".join(report.value.stages[-1].lines))
        # build never ran, so the index that would have described an unpinned registry is absent.
        self.assertFalse(os.path.isfile(os.path.join(root, "aart.index.json")))

    def test_a_gate_that_fails_is_reported_as_failed_and_stops_the_run(self) -> None:
        """A registry that did not validate is not a registry this flow may call finished."""

        from aart_cli.io import registry_bootstrap
        from aart_cli.registry_commands.model import (
            RegistryQualityCheck,
            RegistryQualityReport,
        )

        root = self._workspace()
        from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity

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
            report = bootstrap_registry_workspace(
                root=root, registry_id="acme-registry", display_name="ACME Registry"
            )

        assert isinstance(report, Ok), report
        self.assertFalse(report.value.passed)
        self.assertEqual(
            tuple(stage.name for stage in report.value.stages),
            ("init", "lock", "build", "validate"),
        )
        self.assertIn(
            "the manifest does not describe this payload",
            "\n".join(report.value.stages[-1].lines),
        )

    def test_a_refused_stage_stops_the_run_and_says_which_one(self) -> None:
        root = self._workspace()

        report = bootstrap_registry_workspace(
            root=root, registry_id="Not A Slug", display_name="ACME Registry"
        )

        assert isinstance(report, Ok), report
        self.assertFalse(report.value.passed)
        self.assertEqual(tuple(stage.name for stage in report.value.stages), ("init",))
        self.assertFalse(os.path.isfile(os.path.join(root, "aart.lock.json")))


class MaintainerRegistryInitActionTest(unittest.TestCase):
    """The action boundary: reviewed before it runs, and drawn as stages afterwards."""

    def _composed(self, env):
        from aart_cli import tui

        composed = tui._canonical_consumer_actions(
            project=str(env.project), user_home=str(env.home), today=tui.date.today()
        )
        assert isinstance(composed, Ok), composed
        return composed.value

    def _prepare(self, actions, draft: RegistryInitDraft):
        return actions.handle(
            ConsumerUiCommand(
                ConsumerUiCommandKind.PREPARE_ACTION,
                action=ConsumerActionKind.REGISTRY_INIT,
                registry_init_draft=draft,
            )
        )

    def test_the_review_states_all_five_stages_and_that_nothing_is_published(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = self._composed(env)
            prepared = self._prepare(
                actions, RegistryInitDraft("acme-registry", "ACME Registry", False)
            )

        self.assertTrue(prepared.event.review_digest)
        notice = "\n".join(prepared.source.screens.notice)
        for stage in REGISTRY_BOOTSTRAP_STAGES:
            self.assertIn(stage, notice)
        self.assertIn("acme-registry", notice)
        self.assertNotIn("aart ", notice)
        self.assertIn("push", notice)

    def test_an_unusable_identifier_is_refused_before_anything_is_prepared(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = self._composed(env)
            update = self._prepare(actions, RegistryInitDraft("", "ACME Registry", False))

        self.assertEqual(update.event.review_digest, "")
        self.assertNotIn("aart ", "\n".join(update.source.screens.notice))

    def test_a_stray_space_around_an_answer_still_reviews_the_registry(self) -> None:
        """`QA-058`: the identity is judged by what was named, not by the spaces around it."""

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = self._composed(env)
            prepared = self._prepare(
                actions, RegistryInitDraft("acme-registry ", " ACME Registry", False)
            )

        self.assertTrue(prepared.event.review_digest, "a stray space refused a usable identity")
        notice = "\n".join(prepared.source.screens.notice)
        self.assertIn("  registry ID: acme-registry\n", notice + "\n")
        self.assertIn("  display name: ACME Registry\n", notice + "\n")
        self.assertNotIn("usage reporting", notice.lower())

    def test_one_confirmation_really_creates_the_registry_in_this_project(self) -> None:
        """End to end through the action boundary: no stubbed port, real files afterwards."""

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            # A registry is a Git repository: canonical mutation refuses to write anywhere the
            # maintainer could not review and revert what it wrote.
            _repository(str(env.project))
            actions = self._composed(env)
            draft = RegistryInitDraft("acme-registry", "ACME Registry", False)
            prepared = self._prepare(actions, draft)
            self.assertTrue(prepared.event.review_digest)
            finished = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REGISTRY_INIT,
                    review_digest=prepared.event.review_digest,
                )
            )
            project = str(env.project)
            markers = (
                "aart-cli-registry.json",
                "aart-cli-source.json",
                "aart.lock.json",
                "aart.index.json",
            )
            written = sorted(name for name in os.listdir(project) if name in markers)
            catalogs = sorted(
                name
                for name in os.listdir(os.path.join(project, "registry"))
                if name in ("index.json", "snapshot.json")
            )

        self.assertTrue(finished.event.text, "the run recorded nothing")
        self.assertEqual(written, ["aart-cli-registry.json", "aart-cli-source.json"])
        self.assertEqual(catalogs, ["index.json", "snapshot.json"])
        notice = "\n".join(finished.source.screens.notice)
        for stage in REGISTRY_BOOTSTRAP_STAGES:
            self.assertIn(f"  {stage}: done", notice)
        self.assertNotIn("aart ", notice)

    def test_the_reviewed_plan_includes_whether_it_will_commit(self) -> None:
        """Two different runs are two different plans (D-069).

        A digest that ignored the commit choice would let a review of "write the files, make no
        commit" be confirmed into a run that writes a commit into the repository's history.
        """

        from tests.configured_install_command_e2e_test import _environment

        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = self._composed(env)
            quiet = self._prepare(
                actions, RegistryInitDraft("acme-registry", "ACME Registry", False)
            )
            committing = self._prepare(
                actions, RegistryInitDraft("acme-registry", "ACME Registry", True)
            )

        self.assertTrue(quiet.event.review_digest)
        self.assertNotEqual(quiet.event.review_digest, committing.event.review_digest)

    def test_a_failed_stage_is_drawn_and_records_nothing(self) -> None:
        from tests.configured_install_command_e2e_test import _environment

        failing = RegistryBootstrapReport(
            (
                RegistryBootstrapStage("init", True, ("added 6 managed paths",)),
                RegistryBootstrapStage("lock", False, ("upstream reference is unreachable",)),
            )
        )
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            from aart_cli.io.consumer_actions import RegistryBootstrapCompletion

            actions = self._composed(env)
            actions._registry_bootstrap = lambda draft: Ok(  # type: ignore[assignment]
                RegistryBootstrapCompletion(failing)
            )
            draft = RegistryInitDraft("acme-registry", "ACME Registry", False)
            prepared = self._prepare(actions, draft)
            finished = actions.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.EXECUTE_ACTION,
                    action=ConsumerActionKind.REGISTRY_INIT,
                    review_digest=prepared.event.review_digest,
                )
            )

        self.assertEqual(finished.event.text, "")
        notice = "\n".join(finished.source.screens.notice)
        self.assertIn("lock", notice)
        self.assertIn("unreachable", notice)


if __name__ == "__main__":
    unittest.main()


class RegistryIdentityWhitespaceTest(unittest.TestCase):
    """`QA-058`: a space keystroke must not be able to make the form refuse itself.

    Screen 46a's status bar offers `[Space] Toggle`, and on a text row a printable key is text: the
    space it types lands in the answer instead of toggling anything. Neither text answer has a
    space at either end, so surrounding whitespace is not part of what the operator said
    and the identity is judged without it.  It is settled at the boundary rather than while typing,
    because `Manual Registry` has to remain typeable one key at a time.
    """

    def test_a_stray_space_is_not_part_of_what_the_operator_named(self) -> None:
        draft = RegistryInitDraft("manual-registry ", "  Manual Registry ", True)

        self.assertEqual(
            draft.settled(),
            RegistryInitDraft("manual-registry", "Manual Registry", True),
        )

    def test_settling_an_already_settled_draft_changes_nothing(self) -> None:
        settled = RegistryInitDraft("manual-registry", "Manual Registry", False)

        self.assertEqual(settled.settled(), settled)

    @given(
        st.text(alphabet=_TYPEABLE, max_size=24),
        st.text(alphabet=_TYPEABLE, max_size=24),
        st.booleans(),
    )
    def test_settling_drops_the_edges_and_nothing_else(
        self, identifier: str, name: str, commit: bool
    ) -> None:
        """Universal, so stated over generated input: whatever was typed, only the edges go."""

        settled = RegistryInitDraft(identifier, name, commit).settled()

        self.assertEqual(settled.registry_id, identifier.strip())
        self.assertEqual(settled.display_name, name.strip())
        self.assertEqual(settled.commit, commit)
        self.assertEqual(settled.settled(), settled)


class RegistryIdentityRefusalTest(unittest.TestCase):
    """`QA-058`: two answers are on the screen, so a refusal has to say which one it means.

    The form cannot answer with a command line (`QA-017`), which makes the refusal the operator's
    only instrument for finding the mistake.  One that says the identity is unusable without saying
    which one is unusable leaves them re-reading both.
    """

    def test_the_refusal_names_the_identifier_when_the_identifier_is_the_fault(self) -> None:
        refused = registry_identity_refusal(
            registry_id="manual registry", display_name="Manual Registry"
        )

        self.assertIsNotNone(refused)
        assert refused is not None
        lines = "\n".join((refused.diagnostics[0].message, *refused.diagnostics[0].interactive))
        self.assertIn("Registry ID", lines)
        self.assertNotIn("Display name", lines)

    def test_the_refusal_names_the_display_name_when_the_name_is_the_fault(self) -> None:
        refused = registry_identity_refusal(registry_id="manual-registry", display_name="")

        self.assertIsNotNone(refused)
        assert refused is not None
        lines = "\n".join((refused.diagnostics[0].message, *refused.diagnostics[0].interactive))
        self.assertIn("Display name", lines)
        self.assertNotIn("Registry ID", lines)

    def test_two_faults_are_all_named_and_all_fit_a_screen(self) -> None:
        """`QA-017`: a fault the headline drops, or truncates mid-word, is one nobody can act on."""

        refused = registry_identity_refusal(registry_id="", display_name="")

        self.assertIsNotNone(refused)
        assert refused is not None
        message = refused.diagnostics[0].message
        self.assertEqual(message, "Registry ID and Display name cannot be used as written")
        for line in (message, *refused.diagnostics[0].interactive):
            self.assertLessEqual(len(line), CONTENT_MEASURE, line)

    def test_a_usable_identity_is_not_refused(self) -> None:
        self.assertIsNone(
            registry_identity_refusal(registry_id="manual-registry", display_name="Manual Registry")
        )
