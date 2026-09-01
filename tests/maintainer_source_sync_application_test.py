"""CP-14 Source Sync is one reviewed, leased, non-promoting application transaction."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from agent_artifacts.application.maintainer_sync import (
    ApprovedRegistryState,
    MaintainerSourceSyncPorts,
    execute_source_sync,
    prepare_source_sync,
)
from agent_artifacts.application.sources import SourceSyncPorts, SourceSyncRequest
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias, SourceId
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.capabilities import parse_capability
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.protocol.semver import parse_semver
from agent_artifacts.sources.model import (
    CurrentSource,
    SourceLockLease,
    SourcePublishReceipt,
    SyncFallback,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
)


def _unwrap(result):
    assert isinstance(result, Ok), result
    return result.value


def _entry(path: str, content: str) -> SnapshotEntry:
    return SnapshotEntry(
        _unwrap(parse_relative_path(path)),
        SnapshotEntryKind.FILE,
        content.encode(),
    )


def _snapshot() -> SourceSnapshot:
    manifest = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "github", "kind": "mcp", "version": "1.0.0"},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    return SourceSnapshot(
        SnapshotOrigin.LOCAL,
        (
            _entry("github/aart.json", json.dumps(manifest, sort_keys=True)),
            _entry("github/server.py", "print('ready')\n"),
        ),
    )


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _source() -> ConfiguredSource:
    return ConfiguredSource(
        SourceAlias("authors"), SourceKind.SOURCE_LOCAL, "/work/authors", None, True
    )


def _candidate():
    source = _source()
    provisional = _unwrap(
        make_source_candidate(
            source_instance_id(source),
            source.alias,
            "local:" + "0" * 64,
            _snapshot(),
        )
    )
    return replace(
        provisional,
        resolved_revision="local:" + provisional.snapshot_digest.value,
    )


def _request() -> SourceSyncRequest:
    return SourceSyncRequest(
        _source(),
        "/managed/data",
        _unwrap(parse_semver("1.0.0")),
        (_unwrap(parse_capability("artifact-manifest-v1")),),
        100,
        SyncFallback.REQUIRE_FRESH,
        False,
        30,
    )


def _approved(*, digest: ObjectDigest | None = None) -> ApprovedRegistryState:
    return ApprovedRegistryState(
        SourceAlias("company"),
        "f" * 40,
        _digest("e") if digest is None else digest,
        (),
    )


def _failure(message: str = "failed") -> Err:
    return Err(
        (Diagnostic(DiagnosticCode("maintainer-source-sync-test"), Severity.ERROR, message),)
    )


class _Ports:
    def __init__(self) -> None:
        self.source = _source()
        self.candidate = _candidate()
        self.current = None
        self.history = None
        self.approved = _approved()
        self.events: list[str] = []
        self.leased = False
        self.fail_compile = False

    def acquire_lock(self, request):
        self.events.append("lock")
        self.leased = True
        return Ok(SourceLockLease(request.lock_directory, "lease-token"))

    def release_lock(self, _lease):
        self.events.append("release")
        self.leased = False
        return Ok(None)

    def read_current(self, _request):
        self.events.append("current")
        return Ok(self.current)

    def acquire_local(self, _request):
        self.events.append("acquire-local")
        return Ok(self.candidate)

    def acquire_git(self, _request):
        raise AssertionError("local Source Sync cannot acquire Git")

    def validate(self, request):
        self.events.append("validate")
        return Ok(ValidatedSourceCandidate(request.candidate, SourceId("authors-source")))

    def publish(self, command):
        self.events.append("publish")
        self.current = CurrentSource(
            command.validated.candidate,
            command.validated.declared_source_id,
            command.observed_at_epoch_seconds,
            f"{command.paths.snapshots}/published/source",
        )
        return Ok(SourcePublishReceipt(self.current, created=True))

    def read_history(self, _paths):
        self.events.append("history")
        return Ok(self.history)

    def write_history(self, _paths, scan):
        self.events.append("write-history")
        if not self.leased:
            raise AssertionError("Candidate history escaped the Source lease")
        if scan.registry_mutations:
            raise AssertionError("Source Sync attempted a registry mutation")
        self.history = scan
        return Ok(None)

    def read_approved(self, alias):
        self.events.append("approved")
        if alias != self.approved.alias:
            return _failure("wrong registry")
        return Ok(self.approved)

    def compile(self, snapshot, source_alias, source, revision):
        self.events.append("compile")
        if self.fail_compile:
            return _failure("compile failed")
        return compile_author_snapshot(
            snapshot,
            source_alias=source_alias,
            source=source,
            revision=revision,
        )

    def ports(self) -> MaintainerSourceSyncPorts:
        return MaintainerSourceSyncPorts(
            SourceSyncPorts(
                self.acquire_lock,
                self.release_lock,
                self.read_current,
                self.acquire_local,
                self.acquire_git,
                self.validate,
                self.publish,
            ),
            self.read_history,
            self.write_history,
            self.read_approved,
            self.compile,
        )


class MaintainerSourceSyncApplicationTest(unittest.TestCase):
    def test_review_binds_source_baseline_and_approved_registry_without_effects(self) -> None:
        prepared = prepare_source_sync(_request(), None, None, _approved())
        changed_registry = prepare_source_sync(
            _request(), None, None, _approved(digest=_digest("d"))
        )

        self.assertIsInstance(prepared, Ok)
        self.assertIsInstance(changed_registry, Ok)
        assert isinstance(prepared, Ok) and isinstance(changed_registry, Ok)
        self.assertNotEqual(prepared.value.review_digest, changed_registry.value.review_digest)
        self.assertEqual(prepared.value.source_alias, SourceAlias("authors"))
        self.assertEqual(prepared.value.target_registry, SourceAlias("company"))
        self.assertIsNone(prepared.value.baseline.revision)

    def test_confirmed_sync_publishes_compiles_reconciles_and_reads_back_under_one_lease(
        self,
    ) -> None:
        ports = _Ports()
        prepared = _unwrap(prepare_source_sync(_request(), None, None, ports.approved))

        result = execute_source_sync(prepared, prepared.review_digest, ports.ports())

        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        self.assertEqual(result.value.scan, ports.history)
        self.assertEqual(result.value.scan.manifest_count, 1)
        self.assertEqual(result.value.scan.revision, ports.candidate.resolved_revision)
        self.assertEqual(result.value.scan.registry_mutations, ())
        self.assertFalse(ports.leased)
        self.assertEqual(
            ports.events,
            [
                "approved",
                "lock",
                "current",
                "history",
                "current",
                "acquire-local",
                "validate",
                "publish",
                "compile",
                "write-history",
                "history",
                "release",
            ],
        )

    def test_wrong_review_or_changed_registry_refuses_before_source_mutation(self) -> None:
        for changed_review in (True, False):
            with self.subTest(changed_review=changed_review):
                ports = _Ports()
                prepared = _unwrap(prepare_source_sync(_request(), None, None, ports.approved))
                reviewed = _digest("0") if changed_review else prepared.review_digest
                if not changed_review:
                    ports.approved = _approved(digest=_digest("d"))

                result = execute_source_sync(prepared, reviewed, ports.ports())

                self.assertIsInstance(result, Err)
                self.assertNotIn("lock", ports.events)
                self.assertNotIn("publish", ports.events)
                self.assertNotIn("write-history", ports.events)

    def test_failure_after_publication_releases_lease_and_does_not_publish_history(self) -> None:
        ports = _Ports()
        ports.fail_compile = True
        prepared = _unwrap(prepare_source_sync(_request(), None, None, ports.approved))

        result = execute_source_sync(prepared, prepared.review_digest, ports.ports())

        self.assertIsInstance(result, Err)
        self.assertEqual(ports.events[-1], "release")
        self.assertNotIn("write-history", ports.events)
        self.assertIsNone(ports.history)

    def test_changed_source_baseline_refuses_under_lease_before_acquisition(self) -> None:
        ports = _Ports()
        prepared = _unwrap(prepare_source_sync(_request(), None, None, ports.approved))
        ports.current = CurrentSource(
            ports.candidate,
            SourceId("authors-source"),
            99,
            "/managed/data/sources/changed/snapshots/source",
        )

        result = execute_source_sync(prepared, prepared.review_digest, ports.ports())

        self.assertIsInstance(result, Err)
        self.assertEqual(ports.events, ["approved", "lock", "current", "history", "release"])
        self.assertNotIn("acquire-local", ports.events)
        self.assertNotIn("publish", ports.events)


if __name__ == "__main__":
    unittest.main()
