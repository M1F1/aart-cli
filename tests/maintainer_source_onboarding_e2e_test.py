"""CP-23/01: a newly connected Source remains the subject of explicit discovery."""

from __future__ import annotations

import os
import shutil
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from aart_cli.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
    ConsumerUiState,
    SourceDraft,
)
from aart_cli.application.consumer_views import ConsumerSession
from aart_cli.application.maintainer_views import MaintainerScreen
from aart_cli.domain.result import Ok
from aart_cli.io.candidate_store import candidate_history_paths, read_candidate_history
from aart_cli.io.source_store import read_current_source
from aart_cli.sources.model import (
    CurrentSourceRequest,
    source_instance_id,
    source_store_paths,
)
from aart_cli.tui_consumer import run_consumer_shell
from tests.authoring_source_admission_e2e_test import SKILL_BODY, SKILL_MANIFEST
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions
from tests.consumer_shell_test import ENTER, ESCAPE, FakeTerminal
from tests.screen_block_structure_test import _blocks, _spoken


def _add(handler, draft):
    prepared = handler.handle(
        ConsumerUiCommand(
            ConsumerUiCommandKind.PREPARE_ACTION,
            action=ConsumerActionKind.SOURCE_ADD,
            source_draft=draft,
        )
    )
    assert prepared.event.review_digest, prepared.source.screens.notice
    return handler.handle(
        ConsumerUiCommand(
            ConsumerUiCommandKind.EXECUTE_ACTION,
            action=ConsumerActionKind.SOURCE_ADD,
            review_digest=prepared.event.review_digest,
        )
    )


class MaintainerSourceOnboardingTest(unittest.TestCase):
    def test_add_return_sync_and_repeat_discover_candidates_without_changing_registry(self):
        with _environment() as env, mock.patch.dict(os.environ, env.xdg, clear=False):
            author_root = env.root / "authors"
            author_root.mkdir()
            manifest = author_root / "aart-cli.yaml"
            manifest.write_text(SKILL_MANIFEST, encoding="utf-8")
            (author_root / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
            handler = _actions(env)
            settings = handler.settings.with_maintainer_mode(True)
            handler.save_settings(settings)
            registry_paths = source_store_paths(env.paths.data_root, source_instance_id(env.source))
            registry_request = CurrentSourceRequest(registry_paths, env.source.alias)
            registry_before = read_current_source(registry_request)
            self.assertIsInstance(registry_before, Ok)

            # An earlier alphabetic Source makes defaulting the cursor to row zero observable.
            other_root = env.root / "earlier-authors"
            shutil.copytree(author_root, other_root)
            first = _add(handler, SourceDraft("a-authors", "source-local", str(other_root), ""))
            self.assertIs(first.event.kind, ConsumerUiEventKind.ACTION_RECORDED)
            draft = SourceDraft("z-authors", "source-local", str(author_root), "")
            state = ConsumerUiState(
                ConsumerSession(MaintainerScreen.SOURCE_ADD),
                settings=settings,
                source_draft=draft,
                rows=("alias", "kind", "location", "ref", "connect"),
                cursor=4,
            )
            # Exercise real form keys, review, commit, refreshed rows and the returned notice.
            terminal = FakeTerminal(ENTER, ENTER)
            added = run_consumer_shell(
                handler.source(), terminal, state=state, action_handler=handler
            )
            self.assertIs(added.session.screen, MaintainerScreen.SOURCES, terminal.frames)
            self.assertEqual(added.current_row, draft.alias)
            success = terminal.screen_containing("Source z-authors added")
            self.assertIn("[s] Sync", success)
            self.assertIn("discover artifacts", success)
            self.assertIn("new upstream versions", success)
            self.assertIn("Adding a Source only connects it", success)
            self.assertIn("does not promote Candidates or update installed artifacts", success)
            blocks = _blocks(tuple(success.splitlines()))
            rows = next(block for block in blocks if any("> z-authors" in line for line in block))
            notice = next(
                block for block in blocks if any("Source z-authors added" in line for line in block)
            )
            self.assertIsNot(rows, notice)
            self.assertFalse(any("Run Source Sync" in line for line in rows))
            self.assertEqual(
                _spoken(notice),
                (
                    "- Source z-authors added.",
                    "- Run Source Sync to discover artifacts and create or refresh Candidates, "
                    "including new upstream versions. Adding a Source only connects it.",
                    "- Source Sync does not promote Candidates or update installed artifacts.",
                ),
            )

            sources = {
                source.alias.value: source
                for source in handler._context.effective.configuration.sources
            }
            paths = source_store_paths(
                env.paths.data_root, source_instance_id(sources[draft.alias])
            )
            history_paths = candidate_history_paths(paths)
            self.assertEqual(read_candidate_history(history_paths), Ok(None))
            view = next(
                source
                for source in handler._context.maintainer.sources
                if source.alias == draft.alias
            )
            self.assertEqual(view.manifest_count, 0)
            self.assertEqual(view.candidate_states, ())

            # Returning via Source Details still offers Sync for precisely the added Source.
            returning = FakeTerminal(ENTER, ord("s"), ESCAPE, ESCAPE, ord("s"), ENTER)
            synced = run_consumer_shell(
                handler.source(),
                returning,
                state=replace(added, exited=False),
                action_handler=handler,
            )
            self.assertIs(synced.session.screen, MaintainerScreen.SOURCE_SYNC_RESULT)
            self.assertEqual(synced.focus, draft.alias)
            self.assertIn(
                "Current Candidates: 0",
                returning.screen_containing("Sync authoring Source z-authors"),
            )
            self.assertIn("Candidates: 1", returning.screen_containing("/ Source Sync Result"))
            history = read_candidate_history(history_paths)
            self.assertIsInstance(history, Ok)
            assert isinstance(history, Ok) and history.value is not None
            self.assertEqual(len(history.value.active), 1)
            self.assertEqual(read_current_source(registry_request), registry_before)
            other_paths = source_store_paths(
                env.paths.data_root, source_instance_id(sources["a-authors"])
            )
            self.assertEqual(read_candidate_history(candidate_history_paths(other_paths)), Ok(None))

            for version in (None, "1.1.0"):
                if version is not None:
                    manifest.write_text(SKILL_MANIFEST.replace("1.0.0", version), encoding="utf-8")
                repeated = FakeTerminal(ENTER, ord("s"), ENTER)
                synced = run_consumer_shell(
                    handler.source(),
                    repeated,
                    state=replace(synced, exited=False),
                    action_handler=handler,
                )
                self.assertIs(synced.session.screen, MaintainerScreen.SOURCE_SYNC_RESULT)
                self.assertEqual(synced.focus, draft.alias)
                refreshed = read_candidate_history(history_paths)
                self.assertIsInstance(refreshed, Ok)
                assert isinstance(refreshed, Ok) and refreshed.value is not None
                self.assertEqual(len(refreshed.value.active), 1)
                if version is None:
                    self.assertEqual(refreshed, history)
                else:
                    self.assertEqual(
                        str(refreshed.value.active[0].candidate.artifact.coordinate.version),
                        version,
                    )
                self.assertEqual(read_current_source(registry_request), registry_before)
            self.assertFalse(any(Path(env.project).iterdir()))


if __name__ == "__main__":
    unittest.main()
