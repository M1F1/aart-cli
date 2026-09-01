"""The production terminal composition reaches durable Maintainer Source state."""

from __future__ import annotations

import json
import pathlib
import shutil
import time
import unittest

from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEventKind,
    opening_state,
)
from agent_artifacts.application.consumer_views import ConsumerSettings
from agent_artifacts.application.maintainer_views import MaintainerScreen
from agent_artifacts.configuration.model import (
    ConfiguredSource,
    ReportingSettings,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.schema import user_configuration_bytes
from agent_artifacts.domain.identifiers import SourceAlias, SourceId
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.candidate_store import (
    candidate_history_paths,
    read_candidate_history,
    write_candidate_history,
)
from agent_artifacts.io.consumer_settings import write_consumer_settings
from agent_artifacts.io.source_store import publish_source_snapshot, read_current_source
from agent_artifacts.sources.model import (
    CurrentSourceRequest,
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from agent_artifacts.tui_consumer import run_consumer_shell
from tests.candidate_history_test import _ready_scan
from tests.configured_install_command_e2e_test import _environment
from tests.consumer_application_e2e_test import _actions
from tests.consumer_shell_test import DOWN, ENTER, FakeTerminal
from tests.maintainer_composition_test import _snapshot
from tests.marketplace_fixtures import configured_source


class MaintainerProductionCompositionTest(unittest.TestCase):
    def test_dashboard_to_source_detail_uses_the_real_persisted_scan(self) -> None:
        with _environment() as env:
            authors = configured_source("authors", SourceKind.SOURCE_GIT)
            configuration = UserConfiguration(
                1,
                (env.source, authors),
                env.source.alias,
                SyncSettings(),
                ReportingSettings(),
            )
            pathlib.Path(env.paths.user_config_file).write_bytes(
                user_configuration_bytes(configuration)
            )
            source_paths = source_store_paths(
                env.paths.data_root,
                source_instance_id(authors),
            )
            candidate = make_source_candidate(
                source_instance_id(authors),
                authors.alias,
                "a" * 40,
                _snapshot(),
            )
            assert isinstance(candidate, Ok)
            self.assertIsInstance(
                publish_source_snapshot(
                    SourcePublishCommand(
                        source_paths,
                        ValidatedSourceCandidate(candidate.value, SourceId("author-source")),
                        int(time.time()),
                    )
                ),
                Ok,
            )
            self.assertIsInstance(
                write_candidate_history(
                    candidate_history_paths(source_paths),
                    _ready_scan(),
                ),
                Ok,
            )
            settings = ConsumerSettings().with_maintainer_mode(True)
            self.assertIsInstance(
                write_consumer_settings(settings, data_root=env.paths.data_root),
                Ok,
            )

            handler = _actions(env)
            terminal = FakeTerminal(*(DOWN for _ in range(8)), ENTER, ENTER, ENTER)
            finished = run_consumer_shell(
                handler.source(),
                terminal,
                state=opening_state(handler.settings),
                action_handler=handler,
                settings_writer=handler.save_settings,
            )

            self.assertIs(finished.session.screen, MaintainerScreen.SOURCE_DETAILS)
            self.assertTrue(terminal.screen_containing("AART / Maintainer Dashboard"))
            self.assertIn("Candidates: 1", terminal.screen_containing("Maintainer overview"))
            self.assertIn("authors", terminal.screen_containing("AART / Sources"))
            detail = terminal.screen_containing("AART / Source Details")
            self.assertIn("branch: main", detail)
            self.assertIn("Candidates: 1", detail)

    def test_source_sync_review_reads_but_does_not_create_the_source_store(self) -> None:
        with _environment() as env:
            author_root = env.root / "authors"
            author_root.mkdir()
            authors = ConfiguredSource(
                SourceAlias("authors"),
                SourceKind.SOURCE_LOCAL,
                str(author_root),
                None,
                True,
            )
            configuration = UserConfiguration(
                1,
                (env.source, authors),
                env.source.alias,
                SyncSettings(),
                ReportingSettings(),
            )
            pathlib.Path(env.paths.user_config_file).write_bytes(
                user_configuration_bytes(configuration)
            )
            author_paths = source_store_paths(env.paths.data_root, source_instance_id(authors))
            registry_paths = source_store_paths(env.paths.data_root, source_instance_id(env.source))
            registry_before = read_current_source(
                CurrentSourceRequest(registry_paths, env.source.alias)
            )
            self.assertFalse(pathlib.Path(author_paths.root).exists())

            handler = _actions(env)
            update = handler.handle(
                ConsumerUiCommand(
                    ConsumerUiCommandKind.PREPARE_ACTION,
                    action=ConsumerActionKind.SOURCE_SYNC,
                    focus="authors",
                )
            )

            self.assertIs(update.event.kind, ConsumerUiEventKind.ACTION_PREPARED)
            self.assertTrue(update.event.review_digest)
            self.assertFalse(pathlib.Path(author_paths.root).exists())
            self.assertEqual(
                read_current_source(CurrentSourceRequest(registry_paths, env.source.alias)),
                registry_before,
            )

    def test_reviewed_local_source_sync_persists_candidates_and_never_mutates_registry(
        self,
    ) -> None:
        with _environment() as env:
            author_root = env.root / "authors"
            shutil.copytree(
                pathlib.Path(__file__).parent / "fixtures" / "protocol" / "native-source-v1",
                author_root,
            )
            package = author_root / "authoring" / "github"
            package.mkdir(parents=True)
            package.joinpath("aart.json").write_text(
                json.dumps(
                    {
                        "schema": "aart.dev/mcp/v1",
                        "artifact": {
                            "name": "github",
                            "kind": "mcp",
                            "version": "1.0.0",
                        },
                        "payload": {"include": ["server.py"]},
                        "transport": {"type": "stdio"},
                        "runtime": {"type": "python", "version": ">=3.11"},
                        "launch": {"type": "python", "entrypoint": "server.py"},
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            package.joinpath("server.py").write_text("print('ready')\n", encoding="utf-8")
            authors = ConfiguredSource(
                SourceAlias("authors"),
                SourceKind.SOURCE_LOCAL,
                str(author_root),
                None,
                True,
            )
            configuration = UserConfiguration(
                1,
                (env.source, authors),
                env.source.alias,
                SyncSettings(),
                ReportingSettings(),
            )
            pathlib.Path(env.paths.user_config_file).write_bytes(
                user_configuration_bytes(configuration)
            )
            settings = ConsumerSettings().with_maintainer_mode(True)
            self.assertIsInstance(
                write_consumer_settings(settings, data_root=env.paths.data_root),
                Ok,
            )
            registry_paths = source_store_paths(env.paths.data_root, source_instance_id(env.source))
            registry_before = read_current_source(
                CurrentSourceRequest(registry_paths, env.source.alias)
            )
            self.assertIsInstance(registry_before, Ok)

            handler = _actions(env)
            terminal = FakeTerminal(
                *(DOWN for _ in range(8)),
                ENTER,
                ENTER,
                ENTER,
                ord("s"),
                ENTER,
            )
            finished = run_consumer_shell(
                handler.source(),
                terminal,
                state=opening_state(handler.settings),
                action_handler=handler,
                settings_writer=handler.save_settings,
            )

            self.assertIs(finished.session.screen, MaintainerScreen.SOURCE_SYNC_RESULT)
            review = terminal.screen_containing("AART / Source Sync")
            self.assertIn("Registry mutations: none", review)
            self.assertIn("Review identity: sha256:", review)
            result = terminal.screen_containing("AART / Source Sync Result")
            self.assertIn("Discovered manifests: 1", result)
            self.assertIn("Candidates: 1", result)
            self.assertIn("Registry mutations: none", result)

            author_paths = source_store_paths(env.paths.data_root, source_instance_id(authors))
            history = read_candidate_history(candidate_history_paths(author_paths))
            self.assertIsInstance(history, Ok)
            assert isinstance(history, Ok) and history.value is not None
            self.assertEqual(history.value.manifest_count, 1)
            self.assertTrue(history.value.revision.startswith("local:"))
            registry_after = read_current_source(
                CurrentSourceRequest(registry_paths, env.source.alias)
            )
            self.assertEqual(registry_after, registry_before)

    def test_candidate_list_detail_and_diff_draw_the_scan_composition_already_read(self) -> None:
        """Screens 35-37 reached in one real session, from the scan composition read once.

        Nothing here re-scans: the shell is handed the durable Candidate history at composition
        time, and walking the three screens only projects what it was already holding.
        """

        with _environment() as env:
            authors = configured_source("authors", SourceKind.SOURCE_GIT)
            pathlib.Path(env.paths.user_config_file).write_bytes(
                user_configuration_bytes(
                    UserConfiguration(
                        1,
                        (env.source, authors),
                        env.source.alias,
                        SyncSettings(),
                        ReportingSettings(),
                    )
                )
            )
            source_paths = source_store_paths(env.paths.data_root, source_instance_id(authors))
            candidate = make_source_candidate(
                source_instance_id(authors),
                authors.alias,
                "a" * 40,
                _snapshot(),
            )
            assert isinstance(candidate, Ok)
            self.assertIsInstance(
                publish_source_snapshot(
                    SourcePublishCommand(
                        source_paths,
                        ValidatedSourceCandidate(candidate.value, SourceId("author-source")),
                        int(time.time()),
                    )
                ),
                Ok,
            )
            scan = _ready_scan()
            self.assertIsInstance(
                write_candidate_history(candidate_history_paths(source_paths), scan),
                Ok,
            )
            self.assertIsInstance(
                write_consumer_settings(
                    ConsumerSettings().with_maintainer_mode(True),
                    data_root=env.paths.data_root,
                ),
                Ok,
            )

            handler = _actions(env)
            terminal = FakeTerminal(
                *(DOWN for _ in range(8)),
                ENTER,
                DOWN,
                ENTER,
                ENTER,
                ord("d"),
                ord("f"),
            )
            finished = run_consumer_shell(
                handler.source(),
                terminal,
                state=opening_state(handler.settings),
                action_handler=handler,
                settings_writer=handler.save_settings,
            )

            expected = scan.active[0].candidate
            self.assertIs(finished.session.screen, MaintainerScreen.CANDIDATE_DIFF)
            self.assertEqual(finished.focus, expected.id.value)

            listed = terminal.screen_containing("AART / Candidates")
            self.assertIn("STATUS", listed)
            self.assertIn("authors", listed)
            self.assertNotIn(expected.id.value, listed)

            detail = terminal.screen_containing("AART / Candidate Details")
            self.assertIn("Manifest:", detail)
            self.assertIn("Target registry: company", detail)
            self.assertIn("Press d for semantic diff.", detail)

            summary = terminal.screen_containing("Semantic changes:")
            self.assertIn("File changes (secondary):", summary)
            self.assertNotIn("Bounded redacted file diffs:", summary)
            self.assertIn(
                "Bounded redacted file diffs:",
                terminal.screen_containing("Bounded redacted file diffs:"),
            )


if __name__ == "__main__":
    unittest.main()
