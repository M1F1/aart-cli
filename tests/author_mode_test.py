"""CP-32.12: an opt-in author area runs the CLI's author operations."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from unittest import TestCase, mock

from hypothesis import given
from hypothesis import strategies as st

from aart_cli import tui
from aart_cli.application.author_views import AuthorDraft, manifest_lines
from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
    ConsumerUiState,
)
from aart_cli.application.consumer_views import (
    ConsumerScreen,
    ConsumerSession,
    ConsumerSettings,
    navigation_targets,
    settings_from_data,
    settings_to_data,
)
from aart_cli.authoring.check import ManifestVerdict
from aart_cli.commands import author
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.result import Err, Ok
from aart_cli.io.author_operations import check_workspace, new_artifact, select_workspace
from aart_cli.io.consumer_settings import read_consumer_settings
from aart_cli.model import Request
from aart_cli.tui_consumer import frame, run_consumer_shell
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_shell_test import FakeTerminal


def _state(screen, **changes):
    return ConsumerUiState(
        ConsumerSession(screen), settings=ConsumerSettings(author_mode=True), **changes
    )


def _composed(env):
    result = tui._canonical_consumer_actions(
        project=str(env.project), user_home=str(env.home), today=date(2026, 10, 17)
    )
    assert isinstance(result, Ok), result
    result.value.save_settings(ConsumerSettings(author_mode=True))
    return result.value


def _run(actions, kind, draft=None):
    return actions.handle(
        ConsumerUiCommand(
            ConsumerUiCommandKind.RUN_AUTHOR,
            action=kind,
            author_draft=draft if draft is not None else AuthorDraft(),
        )
    )


class AuthorModeSettingsTest(TestCase):
    def test_modes_round_trip_and_gate_their_own_navigation(self):
        @given(
            author_mode=st.booleans(),
            maintainer_mode=st.booleans(),
            workspace=st.lists(
                st.text(
                    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ",
                    min_size=1,
                    max_size=8,
                ),
                min_size=1,
                max_size=4,
            ).map(lambda parts: "/" + "/".join(parts)),
        )
        def round_trip(author_mode, maintainer_mode, workspace):
            settings = ConsumerSettings(
                author_mode=author_mode, maintainer_mode=maintainer_mode, author_workspace=workspace
            )
            self.assertEqual(settings_from_data(settings_to_data(settings)), Ok(settings))
            targets = navigation_targets(
                ConsumerScreen.DASHBOARD, author_mode=author_mode, maintainer_mode=maintainer_mode
            )
            self.assertEqual(ConsumerScreen.AUTHOR in targets, author_mode)
            self.assertEqual(settings.toggled("author-mode").maintainer_mode, maintainer_mode)
            self.assertNotEqual(settings.toggled("author-mode").author_mode, author_mode)

        round_trip()

    def test_malformed_workspace_preferences_are_rejected(self):
        @given(
            value=st.one_of(
                st.none(),
                st.booleans(),
                st.integers(),
                st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1).map(
                    lambda text: "relative/" + text
                ),
                st.sampled_from(
                    ("/a/../b", "/a/./b", "/a//b", "/a/b/", "/a/\n/b", "/a/\r/b", "/a/\0/b")
                ),
            )
        )
        def rejected(value):
            self.assertIsInstance(settings_from_data({"author_workspace": value}), Err)

        rejected()

    def test_author_mode_is_off_by_default_and_cannot_be_opened_directly(self):
        self.assertFalse(ConsumerSettings().author_mode)
        with self.assertRaises(ValueError):
            ConsumerUiState(ConsumerSession(ConsumerScreen.AUTHOR))
        for value in (1, "yes", None):
            self.assertNotIsInstance(settings_from_data({"author_mode": value}), Ok)
        for workspace in ("relative/path", "/work/../elsewhere", "/work/\nrepo"):
            self.assertNotIsInstance(settings_from_data({"author_workspace": workspace}), Ok)


class AuthorModeCompositionTest(TestCase):
    def test_author_area_and_creation_work_in_the_real_shell_with_maintainer_mode_off(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            workspace = env.project / "authors"
            workspace.mkdir()
            _run(
                actions, ConsumerActionKind.AUTHOR_WORKSPACE, AuthorDraft(workspace=str(workspace))
            )
            _run(
                actions,
                ConsumerActionKind.AUTHOR_INIT,
                AuthorDraft(kind="skill", name="existing", into="00-existing"),
            )
            terminal = FakeTerminal(
                ord("n"), 258, *(ord(letter) for letter in "review"), 258, 258, 10
            )
            state = run_consumer_shell(
                actions.source(),
                terminal,
                state=ConsumerUiState(
                    ConsumerSession(ConsumerScreen.AUTHOR), settings=actions.settings
                ),
                action_handler=actions,
                settings_writer=actions.save_settings,
            )
            self.assertIs(state.session.screen, ConsumerScreen.AUTHOR_CHECK)
            self.assertEqual(state.current_row, "aart-cli.yaml")
            self.assertTrue(actions.source().screens.author_report.accepted)
            self.assertEqual(len(actions.source().screens.author_report.verdicts), 2)
            self.assertFalse(state.settings.maintainer_mode)
            self.assertTrue((workspace / "aart-cli.yaml").is_file())

    def test_workspace_is_normalized_remembered_and_opened_through_the_shell(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            workspace = env.project / "authors"
            workspace.mkdir()
            terminal = FakeTerminal(10)
            state = run_consumer_shell(
                actions.source(),
                terminal,
                state=_state(
                    ConsumerScreen.AUTHOR_WORKSPACE,
                    author_draft=AuthorDraft(workspace=str(workspace / ".." / "authors")),
                    rows=("workspace", "save"),
                    cursor=1,
                ),
                action_handler=actions,
                settings_writer=actions.save_settings,
            )
            expected = str(workspace.resolve())
            self.assertIs(state.session.screen, ConsumerScreen.AUTHOR)
            self.assertEqual(state.settings.author_workspace, expected)
            kept = read_consumer_settings(str(env.paths.data_root))
            self.assertIsInstance(kept, Ok)
            self.assertEqual(kept.value.author_workspace, expected)
            drawn = "\n".join(frame(actions.source(), state))
            for label in ("Workspace", "Check", "New artifact", expected):
                self.assertIn(label, drawn)

    def test_new_artifact_and_check_match_cli_and_never_connect_an_upstream(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            workspace = env.project / "authors"
            workspace.mkdir()
            chosen = _run(
                actions, ConsumerActionKind.AUTHOR_WORKSPACE, AuthorDraft(workspace=str(workspace))
            )
            self.assertIs(chosen.event.kind, ConsumerUiEventKind.ACTION_RECORDED)
            configured_before = actions._context.effective.configuration
            new = _run(
                actions,
                ConsumerActionKind.AUTHOR_INIT,
                AuthorDraft(kind="skill", name="review", into="tools/review"),
            )
            self.assertIs(new.event.kind, ConsumerUiEventKind.ACTION_RECORDED)
            manifest = workspace / "tools/review/aart-cli.yaml"
            self.assertTrue(manifest.is_file())
            checked = _run(actions, ConsumerActionKind.AUTHOR_CHECK)
            report = checked.source.screens.author_report
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = author.run(
                    Request(
                        "author", author_action="check", author_source=str(workspace), json=True
                    )
                )
            self.assertEqual(status, 0, output.getvalue())
            data = json.loads(output.getvalue())
            self.assertEqual(
                [(v.path, v.accepted, v.package) for v in report.verdicts],
                [(v["path"], v["ok"], v["package"]) for v in data["manifests"]],
            )
            self.assertEqual(actions._context.effective.configuration, configured_before)
            before = manifest.read_bytes()
            refused = _run(
                actions,
                ConsumerActionKind.AUTHOR_INIT,
                AuthorDraft(kind="skill", name="review", into="tools/review"),
            )
            self.assertIs(refused.event.kind, ConsumerUiEventKind.ACTION_FAILED)
            self.assertEqual(manifest.read_bytes(), before)

    def test_check_lists_diagnostics_and_can_be_rerun_with_one_key(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            workspace = env.project / "authors"
            workspace.mkdir()
            _run(
                actions, ConsumerActionKind.AUTHOR_WORKSPACE, AuthorDraft(workspace=str(workspace))
            )
            _run(actions, ConsumerActionKind.AUTHOR_INIT, AuthorDraft(kind="skill", name="review"))
            manifest = workspace / "aart-cli.yaml"
            manifest.write_text(
                manifest.read_text().replace("artifact:", "artifact:\n  version: 1.0.0")
            )
            terminal = FakeTerminal(ord("r"), 10)
            state = run_consumer_shell(
                actions.source(),
                terminal,
                state=_state(ConsumerScreen.AUTHOR_CHECK),
                action_handler=actions,
                settings_writer=actions.save_settings,
            )
            self.assertIs(state.session.screen, ConsumerScreen.AUTHOR_MANIFEST)
            drawn = "\n".join(frame(actions.source(), state))
            self.assertIn("Registry assigns versions", drawn)
            self.assertIn("aart-cli.yaml", drawn)
            with mock.patch("builtins.open", side_effect=AssertionError("draw did IO")):
                frame(actions.source(), state)

    def test_workspace_and_new_artifact_refuse_application_home_and_escaping_paths(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            for root in (Path(env.paths.data_root), Path(env.paths.data_root) / "content"):
                root.mkdir(parents=True, exist_ok=True)
                denied = _run(
                    actions, ConsumerActionKind.AUTHOR_WORKSPACE, AuthorDraft(workspace=str(root))
                )
                self.assertIs(denied.event.kind, ConsumerUiEventKind.ACTION_FAILED)
            workspace = env.project / "authors"
            workspace.mkdir()
            _run(
                actions, ConsumerActionKind.AUTHOR_WORKSPACE, AuthorDraft(workspace=str(workspace))
            )
            outside = env.project / "outside"
            outside.mkdir()
            (workspace / "linked").symlink_to(outside, target_is_directory=True)
            for into in ("../escape", str(env.home), "linked"):
                denied = _run(
                    actions,
                    ConsumerActionKind.AUTHOR_INIT,
                    AuthorDraft(kind="skill", name="review", into=into),
                )
                self.assertIs(denied.event.kind, ConsumerUiEventKind.ACTION_FAILED)
            self.assertFalse((env.project / "escape").exists())
            self.assertFalse((env.home / "aart-cli.yaml").exists())
            self.assertFalse((outside / "aart-cli.yaml").exists())
            application_home = Path(env.paths.data_root)
            _run(
                actions,
                ConsumerActionKind.AUTHOR_WORKSPACE,
                AuthorDraft(workspace=str(application_home.parent)),
            )
            denied = _run(
                actions,
                ConsumerActionKind.AUTHOR_INIT,
                AuthorDraft(kind="skill", name="review", into=application_home.name),
            )
            self.assertIs(denied.event.kind, ConsumerUiEventKind.ACTION_FAILED)
            self.assertFalse((application_home / "aart-cli.yaml").exists())

    def test_manifest_diagnostics_keep_errors_and_offer_interactive_recovery(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            workspace = env.project / "authors"
            workspace.mkdir()
            (workspace / "aart-cli.json").write_text(
                json.dumps({"schema": "aart-cli.dev/collection/v1"})
            )
            _run(
                actions, ConsumerActionKind.AUTHOR_WORKSPACE, AuthorDraft(workspace=str(workspace))
            )
            checked = _run(actions, ConsumerActionKind.AUTHOR_CHECK)
            verdict = checked.source.screens.author_report.verdicts[0]
            self.assertFalse(verdict.accepted)
            state = ConsumerUiState(
                ConsumerSession(ConsumerScreen.AUTHOR_MANIFEST),
                settings=actions.settings,
                focus=verdict.path,
            )
            drawn = "\n".join(frame(checked.source, state))
            self.assertIn("the Registry creates it", drawn)
            self.assertNotIn("aart-cli maintain", drawn)
            self.assertIn("run Check again", drawn)

    def test_a_failed_rerun_does_not_show_an_old_passing_report(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            workspace = env.project / "authors"
            workspace.mkdir()
            _run(
                actions, ConsumerActionKind.AUTHOR_WORKSPACE, AuthorDraft(workspace=str(workspace))
            )
            _run(actions, ConsumerActionKind.AUTHOR_INIT, AuthorDraft(kind="skill", name="review"))
            self.assertTrue(actions.source().screens.author_report.accepted)
            workspace.rename(workspace.with_name("moved-authors"))
            failed = _run(actions, ConsumerActionKind.AUTHOR_CHECK)
            self.assertIs(failed.event.kind, ConsumerUiEventKind.ACTION_FAILED)
            self.assertIsNone(failed.source.screens.author_report)

    def test_a_template_written_before_a_check_refusal_is_reported_as_written(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            actions = _composed(env)
            workspace = env.project / "authors"
            workspace.mkdir()
            (workspace / "visible-link").symlink_to(env.home, target_is_directory=True)
            _run(
                actions, ConsumerActionKind.AUTHOR_WORKSPACE, AuthorDraft(workspace=str(workspace))
            )
            result = _run(
                actions, ConsumerActionKind.AUTHOR_INIT, AuthorDraft(kind="skill", name="review")
            )
            self.assertTrue((workspace / "aart-cli.yaml").is_file())
            self.assertIs(result.event.kind, ConsumerUiEventKind.ACTION_RECORDED)
            self.assertIsNone(result.source.screens.author_report)
            notice = "\n".join(result.source.screens.notice)
            self.assertIn("Wrote aart-cli.yaml", notice)
            self.assertIn("Check could not read", notice)


class AuthorOperationBoundaryTest(TestCase):
    def test_workspace_and_destination_boundaries_return_readable_error_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for result in (
                select_workspace(str(root), application_home=str(root)),
                new_artifact(str(root), kind="skill", name="review", into="../escape"),
                new_artifact(
                    str(root),
                    kind="skill",
                    name="review",
                    into="managed",
                    application_home=str(root / "managed"),
                ),
            ):
                self.assertIsInstance(result, Err)
                self.assertEqual(result.diagnostics[0].code.value, "author-workspace-invalid")
                self.assertEqual(result.diagnostics[0].severity.value, "error")
                self.assertIsInstance(result.diagnostics[0].message, str)
                self.assertTrue(result.diagnostics[0].message.strip())

    def test_workspace_rejects_blank_missing_and_non_directory_paths_with_a_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "file"
            file.write_text("ordinary file")
            for path in ("", "   ", str(root / "absent"), str(file)):
                with self.subTest(path=path):
                    result = select_workspace(path, application_home=None)
                    self.assertIsInstance(result, Err)
                    self.assertTrue(result.diagnostics[0].message)
            self.assertEqual(
                select_workspace(str(root), application_home=None), Ok(str(root.resolve()))
            )

    def test_creation_requires_an_existing_workspace_and_refuses_an_invalid_template(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "absent"
            denied = new_artifact(str(missing), kind="skill", name="review", into=".")
            self.assertIsInstance(denied, Err)
            self.assertFalse(missing.exists())
            denied = new_artifact(str(root), kind="collection", name="review", into=".")
            self.assertIsInstance(denied, Err)
            self.assertFalse((root / "aart-cli.yaml").exists())

    def test_check_propagates_an_unreadable_workspace_and_a_missing_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            for root in (directory, str(Path(directory) / "absent")):
                with self.subTest(root=root):
                    result = check_workspace(root)
                    self.assertIsInstance(result, Err)
                    self.assertTrue(result.diagnostics[0].message)


class AuthorProjectionTest(TestCase):
    def test_a_successful_manifest_names_what_it_would_publish(self):
        self.assertEqual(
            manifest_lines(ManifestVerdict("aart-cli.yaml", (), "skill/review")),
            ("aart-cli.yaml", "ok", "skill/review"),
        )

    def test_diagnostics_use_interactive_recovery_while_cli_remediation_stays_out_of_frames(self):
        verdict = ManifestVerdict(
            "aart-cli.yaml",
            (
                Diagnostic(
                    DiagnosticCode("author-invalid"),
                    Severity.ERROR,
                    "bad manifest",
                    remediation=("aart-cli author check",),
                    interactive=("Fix the manifest in this workspace.",),
                ),
            ),
        )
        lines = manifest_lines(verdict)
        self.assertIn("Fix the manifest in this workspace.", lines)
        self.assertNotIn("aart-cli author check", "\n".join(lines))

    def test_multiline_errors_keep_every_character_in_valid_terminal_lines(self):
        @given(text=st.text(alphabet="abcdefghijklmnopqrstuvwxyz \r\n", min_size=1, max_size=80))
        def preserves(text):
            verdict = ManifestVerdict(
                "aart-cli.yaml",
                (Diagnostic(DiagnosticCode("author-invalid"), Severity.ERROR, "problem: " + text),),
            )
            lines = manifest_lines(verdict)
            self.assertTrue(all("\r" not in line and "\n" not in line for line in lines))
            normalized = text.replace("\r", "").replace("\n", "")
            self.assertIn("problem: " + normalized, "".join(lines))

        preserves()

    def test_command_only_recovery_is_replaced_with_an_action_in_the_author_area(self):
        @given(
            command=st.sampled_from(("aart-cli author check", "`command`", "$ command", "git diff"))
        )
        def remains_interactive(command):
            verdict = ManifestVerdict(
                "aart-cli.yaml",
                (
                    Diagnostic(
                        DiagnosticCode("author-invalid"),
                        Severity.ERROR,
                        "bad manifest",
                        remediation=(command,),
                    ),
                ),
            )
            lines = manifest_lines(verdict)
            self.assertNotIn(command, "\n".join(lines))
            self.assertIn("Edit this manifest in your workspace, then run Check again.", lines)

        remains_interactive()

    def test_command_free_recovery_is_preserved_beside_filtered_shell_commands(self):
        verdict = ManifestVerdict(
            "aart-cli.yaml",
            (
                Diagnostic(
                    DiagnosticCode("author-invalid"),
                    Severity.ERROR,
                    "bad manifest",
                    remediation=(
                        "Remove artifact.version.",
                        "aart-cli author check",
                        "Check the payload path.",
                    ),
                ),
            ),
        )
        lines = manifest_lines(verdict)
        self.assertIn("Remove artifact.version.", lines)
        self.assertIn("Check the payload path.", lines)
        self.assertNotIn("aart-cli author check", "\n".join(lines))

    def test_every_error_for_a_manifest_is_projected(self):
        verdict = ManifestVerdict(
            "aart-cli.yaml",
            tuple(
                Diagnostic(DiagnosticCode("author-invalid"), Severity.ERROR, message)
                for message in ("first problem", "second problem")
            ),
        )
        shown = "\n".join(manifest_lines(verdict))
        self.assertIn("first problem", shown)
        self.assertIn("second problem", shown)
