"""The production terminal composition reaches durable Maintainer Source state."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import shutil
import subprocess
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
from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.application.maintainer_views import MaintainerScreen, parse_validation_row
from agent_artifacts.application.promotion import (
    PromotionSourceKind,
    load_registry_promotions,
    load_registry_versions,
    validate_promoted_registry,
)
from agent_artifacts.configuration.model import (
    ConfiguredSource,
    ReportingSettings,
    SourceKind,
    SyncSettings,
    UserConfiguration,
)
from agent_artifacts.configuration.schema import user_configuration_bytes
from agent_artifacts.domain.candidates import assess_candidate
from agent_artifacts.domain.identifiers import SourceAlias, SourceId
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.candidate_store import (
    candidate_history_paths,
    read_candidate_history,
    write_candidate_history,
)
from agent_artifacts.io.consumer_settings import write_consumer_settings
from agent_artifacts.io.registry_promotion import FilesystemPromotionOutput
from agent_artifacts.io.source_store import publish_source_snapshot, read_current_source
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
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


def _digest_line(drawn: str) -> str:
    return next(line for line in drawn.splitlines() if line.strip().startswith("Review digest:"))


def _git(root: pathlib.Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _materialize(root: pathlib.Path, snapshot: SourceSnapshot) -> None:
    root.mkdir(exist_ok=True)
    for entry in snapshot.entries:
        target = root.joinpath(*entry.path.parts)
        if entry.kind is SnapshotEntryKind.DIRECTORY:
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(entry.content)
        target.chmod(0o700 if entry.executable else 0o600)


def _two_ready_candidates():
    """One Source Scan holding two Ready Candidates for the same registry.

    Bulk promotion only means anything with more than one, and both have to come from one scan so
    the durable history the shell reads is the one thing that says they exist.
    """

    entries: list[SnapshotEntry] = []
    for name in ("github-mcp", "jira-mcp"):
        manifest = {
            "schema": "aart.dev/mcp/v1",
            "artifact": {"name": name, "kind": "mcp", "version": "1.0.0"},
            "payload": {"include": ["server.py"]},
            "transport": {"type": "stdio"},
            "runtime": {"type": "python", "version": ">=3.11"},
            "launch": {"type": "python", "entrypoint": "server.py"},
        }
        parsed_manifest = parse_relative_path(f"{name}/aart.json")
        parsed_payload = parse_relative_path(f"{name}/server.py")
        assert isinstance(parsed_manifest, Ok) and isinstance(parsed_payload, Ok)
        entries.append(
            SnapshotEntry(
                parsed_manifest.value,
                SnapshotEntryKind.FILE,
                json.dumps(manifest, sort_keys=True).encode(),
            )
        )
        entries.append(SnapshotEntry(parsed_payload.value, SnapshotEntryKind.FILE, b"print('x')\n"))
    compiled = compile_author_snapshot(
        SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, tuple(entries)),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok), scanned
    ready = tuple(
        CandidateBundle(assess_candidate(item.candidate), item.artifact)
        for item in scanned.value.active
    )
    # Active Candidates stay in canonical manifest-path order; history is keyed by Candidate ID.
    return dataclasses.replace(
        scanned.value,
        active=ready,
        history=tuple(sorted(ready, key=lambda item: item.candidate.id.value)),
    )


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
            assert isinstance(registry_before, Ok) and registry_before.value is not None
            registry_root = env.project
            _materialize(registry_root, registry_before.value.candidate.snapshot)
            subprocess.run(
                ("git", "init", "-b", "main", str(registry_root)),
                check=True,
                capture_output=True,
            )
            _git(registry_root, "config", "user.name", "AART Test")
            _git(registry_root, "config", "user.email", "aart@example.invalid")
            _git(registry_root, "add", "-A")
            _git(registry_root, "commit", "-m", "Initial approved registry")
            before_revision = _git(registry_root, "rev-parse", "HEAD")

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

            promotion_terminal = FakeTerminal(
                *(DOWN for _ in range(8)),
                ENTER,
                DOWN,
                ENTER,
                ENTER,
                ord("d"),
                ENTER,
                ord("p"),
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                ENTER,
            )
            promoted = run_consumer_shell(
                handler.source(),
                promotion_terminal,
                state=opening_state(handler.settings),
                action_handler=handler,
                settings_writer=handler.save_settings,
            )

            self.assertIs(promoted.session.screen, MaintainerScreen.REGISTRY)
            self.assertNotIn(
                "cannot be promoted",
                promotion_terminal.screen_containing("AART / Registry Diff"),
            )
            self.assertIn(
                "Approved registry state written locally",
                promotion_terminal.screen_containing("Approved registry state written locally"),
            )
            self.assertNotEqual(_git(registry_root, "rev-parse", "HEAD"), before_revision)
            self.assertEqual(_git(registry_root, "status", "--porcelain=v1"), "")
            persisted = FilesystemPromotionOutput(str(registry_root)).current()
            assert isinstance(persisted, Ok), persisted
            versions = load_registry_versions(persisted.value)
            assert isinstance(versions, Ok), versions
            self.assertIsInstance(validate_promoted_registry(persisted.value, versions.value), Ok)
            audits = load_registry_promotions(persisted.value)
            assert isinstance(audits, Ok), audits
            local_audits = tuple(
                item
                for item in audits.value
                if item.source_provenance.kind is PromotionSourceKind.LOCAL_SNAPSHOT
            )
            self.assertEqual(len(local_audits), 1)
            provenance = local_audits[0].source_provenance
            self.assertIs(provenance.kind, PromotionSourceKind.LOCAL_SNAPSHOT)
            self.assertIsNone(provenance.git_revision)
            assert provenance.local_snapshot_digest is not None
            self.assertEqual(
                provenance.local_snapshot_digest.value,
                history.value.revision.removeprefix("local:"),
            )

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

    def test_the_review_walk_runs_from_the_diff_through_to_the_promotion_review(self) -> None:
        """Screens 38-41 in the same real session, judged once at composition time.

        The run a Maintainer reads on screen 38 and the policy judgement on screen 40 are the same
        run: nothing re-validates while drawing, so the two screens cannot disagree.
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
                ENTER,
                ord("p"),
                ENTER,
                ENTER,
                ord("m"),
            )
            finished = run_consumer_shell(
                handler.source(),
                terminal,
                state=opening_state(handler.settings),
                action_handler=handler,
                settings_writer=handler.save_settings,
            )

            expected = scan.active[0].candidate
            self.assertIs(finished.session.screen, MaintainerScreen.PROMOTION_MODE)
            # Choosing a mode is a different promotion to confirm, not a relabelled one.
            self.assertIs(finished.promotion_mode, PromotionMode.REFERENCED)
            # Screen 40 was entered from a check row rather than from a bare Candidate ID, which is
            # the whole reason the row identity is a parsed pair and not a split string.
            entered = parse_validation_row(finished.focus)
            assert entered is not None
            self.assertEqual(entered.candidate_id, expected.id.value)

            checks = terminal.screen_containing("AART / Validation")
            self.assertIn("Manifest schema", checks)
            self.assertIn("Live acceptance", checks)
            # Live acceptance has not run, and no undemanding policy may report it as passed.
            self.assertIn("Not run", checks)

            review = terminal.screen_containing("AART / Policy Review")
            self.assertIn("Policy allows:", review)
            self.assertIn("Runtimes: unconstrained", review)
            self.assertIn("nothing beyond the pipeline itself", review)
            self.assertIn("none; nothing here refuses promotion", review)

            promotion = terminal.screen_containing("AART / Promotion Review")
            self.assertIn("Target registry: company", promotion)
            self.assertIn("Promotion mode: vendored", promotion)
            # This walk reaches a confirmable review against the registry this machine actually
            # synchronized, rather than the refusal an unsynchronized one would show.
            self.assertIn("Review digest:", promotion)
            self.assertNotIn("cannot be promoted", promotion)
            self.assertIn("Validation report:", promotion)

            chosen = terminal.screen_containing("Promotion mode: referenced")
            self.assertIn("Review digest:", chosen)
            self.assertNotEqual(
                _digest_line(promotion), _digest_line(chosen), "mode must change the review"
            )

    def test_validated_promotion_is_committed_locally_and_never_pushed(self) -> None:
        """Screens 43–45 replan, validate, write, read back and commit one real checkout."""

        with _environment() as env:
            original_paths = source_store_paths(
                env.paths.data_root,
                source_instance_id(env.source),
            )
            original = read_current_source(CurrentSourceRequest(original_paths, env.source.alias))
            assert isinstance(original, Ok) and original.value is not None
            approved_snapshot = original.value.candidate.snapshot

            registry_root = env.project
            _materialize(registry_root, approved_snapshot)
            subprocess.run(
                ("git", "init", "-b", "main", str(registry_root)),
                check=True,
                capture_output=True,
            )
            _git(registry_root, "config", "user.name", "AART Test")
            _git(registry_root, "config", "user.email", "aart@example.invalid")
            _git(registry_root, "add", "-A")
            _git(registry_root, "commit", "-m", "Initial approved registry")
            before_revision = _git(registry_root, "rev-parse", "HEAD")

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
            author_paths = source_store_paths(
                env.paths.data_root,
                source_instance_id(authors),
            )
            source_candidate = make_source_candidate(
                source_instance_id(authors),
                authors.alias,
                "a" * 40,
                _snapshot(),
            )
            assert isinstance(source_candidate, Ok)
            self.assertIsInstance(
                publish_source_snapshot(
                    SourcePublishCommand(
                        author_paths,
                        ValidatedSourceCandidate(
                            source_candidate.value,
                            SourceId("author-source"),
                        ),
                        int(time.time()),
                    )
                ),
                Ok,
            )
            scan = _ready_scan()
            self.assertIsInstance(
                write_candidate_history(candidate_history_paths(author_paths), scan),
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
            composed = handler.source().screens.maintainer
            assert composed is not None
            self.assertEqual(
                tuple(item.id for item in (composed.candidates or ())),
                tuple(item.candidate.id.value for item in scan.active),
                composed.sources,
            )
            terminal = FakeTerminal(
                *(DOWN for _ in range(8)),
                ENTER,
                DOWN,
                ENTER,
                ENTER,
                ord("d"),
                ENTER,
                ord("p"),
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                ENTER,
                ENTER,
            )
            finished = run_consumer_shell(
                handler.source(),
                terminal,
                state=opening_state(handler.settings),
                action_handler=handler,
                settings_writer=handler.save_settings,
            )

            self.assertIs(
                finished.session.screen,
                MaintainerScreen.REGISTRY,
                terminal.last,
            )
            validation = terminal.screen_containing("AART / Registry Validation")
            self.assertIn("Registry validation: Passed", validation)
            self.assertIn("No approved registry state has been written", validation)
            committed = terminal.screen_containing("Approved registry state written locally")
            self.assertIn("Local Git revision:", committed)
            self.assertIn("Git push: no", committed)
            self.assertIn("Canonical-branch publication remains external", committed)

            # Screen 46 draws the registry the walk just wrote into.  The local commit is
            # deliberately not a sync, so the checkout is ahead of the synchronized approved
            # snapshot here -- and saying so is the point of the working-tree line.
            registry = terminal.screen_containing("AART / Registry Maintainer")
            self.assertIn(env.source.alias.value, registry)
            self.assertIn("Approved versions:", registry)
            self.assertIn("Working tree:", registry)
            self.assertIn("differs from the approved snapshot", registry)

            after_revision = _git(registry_root, "rev-parse", "HEAD")
            self.assertNotEqual(after_revision, before_revision)
            self.assertEqual(_git(registry_root, "status", "--porcelain=v1"), "")
            self.assertEqual(_git(registry_root, "remote", "-v"), "")
            persisted = FilesystemPromotionOutput(str(registry_root)).current()
            assert isinstance(persisted, Ok), persisted
            versions = load_registry_versions(persisted.value)
            assert isinstance(versions, Ok), versions
            self.assertGreaterEqual(len(versions.value), 2)
            self.assertIsInstance(
                validate_promoted_registry(persisted.value, versions.value),
                Ok,
            )
            # Screen 48 reads the just-committed checkout rather than mistaking the older
            # synchronized registry snapshot for the complete Maintainer lifecycle. Promotion is
            # still proven by the persisted version and audit pair, never by Candidate state.
            refreshed = handler.source().screens.maintainer
            assert refreshed is not None
            lifecycle = refreshed.lifecycle(scan.active[0].candidate.id.value)
            assert lifecycle is not None
            self.assertTrue(
                any(
                    stage.phase.value == "promotion" and stage.outcome == "promoted"
                    for stage in lifecycle.stages
                )
            )

    def test_bulk_promotion_writes_both_candidates_in_one_commit(self) -> None:
        """Screen 47 selects two Candidates and they reach the registry as one transaction."""

        with _environment() as env:
            original_paths = source_store_paths(
                env.paths.data_root,
                source_instance_id(env.source),
            )
            original = read_current_source(CurrentSourceRequest(original_paths, env.source.alias))
            assert isinstance(original, Ok) and original.value is not None

            registry_root = env.project
            _materialize(registry_root, original.value.candidate.snapshot)
            subprocess.run(
                ("git", "init", "-b", "main", str(registry_root)),
                check=True,
                capture_output=True,
            )
            _git(registry_root, "config", "user.name", "AART Test")
            _git(registry_root, "config", "user.email", "aart@example.invalid")
            _git(registry_root, "add", "-A")
            _git(registry_root, "commit", "-m", "Initial approved registry")
            before_revision = _git(registry_root, "rev-parse", "HEAD")

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
            author_paths = source_store_paths(
                env.paths.data_root,
                source_instance_id(authors),
            )
            source_candidate = make_source_candidate(
                source_instance_id(authors),
                authors.alias,
                "a" * 40,
                _snapshot(),
            )
            assert isinstance(source_candidate, Ok)
            self.assertIsInstance(
                publish_source_snapshot(
                    SourcePublishCommand(
                        author_paths,
                        ValidatedSourceCandidate(
                            source_candidate.value,
                            SourceId("author-source"),
                        ),
                        int(time.time()),
                    )
                ),
                Ok,
            )
            scan = _two_ready_candidates()
            self.assertIsInstance(
                write_candidate_history(candidate_history_paths(author_paths), scan),
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
            composed = handler.source().screens.maintainer
            assert composed is not None
            offered = composed.bulk_promotion(env.source.alias.value)
            assert offered is not None
            self.assertEqual(len(offered.candidates), 2)

            # Dashboard → maintainer dashboard → registry (46) → bulk promotion (47); tick both
            # rows, then Enter to assemble the transaction, and Enter again to commit it.
            terminal = FakeTerminal(
                *(DOWN for _ in range(8)),
                ENTER,
                DOWN,
                DOWN,
                ENTER,
                ENTER,
                ord(" "),
                DOWN,
                ord(" "),
                ENTER,
                ENTER,
                ENTER,
            )
            finished = run_consumer_shell(
                handler.source(),
                terminal,
                state=opening_state(handler.settings),
                action_handler=handler,
                settings_writer=handler.save_settings,
            )

            self.assertIs(
                finished.session.screen,
                MaintainerScreen.REGISTRY_COMMIT,
                terminal.last,
            )
            committed = terminal.screen_containing("Approved registry state written locally")
            self.assertIn("Promote 2 candidates", committed)
            self.assertIn("Git push: no", committed)

            # One transaction, not two: a loop over single promotions would have made two commits
            # and two registry snapshots.
            revisions = _git(registry_root, "rev-list", "--count", "HEAD")
            self.assertEqual(int(revisions), 2, terminal.last)
            self.assertNotEqual(_git(registry_root, "rev-parse", "HEAD"), before_revision)
            self.assertEqual(_git(registry_root, "status", "--porcelain=v1"), "")

            persisted = FilesystemPromotionOutput(str(registry_root)).current()
            assert isinstance(persisted, Ok), persisted
            versions = load_registry_versions(persisted.value)
            assert isinstance(versions, Ok), versions
            self.assertEqual(
                len({str(item.registry_snapshot) for item in versions.value}),
                1,
                "both promoted versions must name the one snapshot their transaction produced",
            )
            self.assertIsInstance(
                validate_promoted_registry(persisted.value, versions.value),
                Ok,
            )


if __name__ == "__main__":
    unittest.main()
