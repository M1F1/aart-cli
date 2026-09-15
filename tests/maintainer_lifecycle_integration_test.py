"""Pinned author source through Candidate review to upstream-independent vendoring."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.application.promotion import (
    PromotionEvidence,
    plan_bulk_promotion,
    project_promotion,
)
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.domain.candidates import assess_candidate
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import SnapshotEntryKind, SnapshotOrigin, SourceSnapshot
from agent_artifacts.sources.local import read_local_snapshot
from agent_artifacts.sources.model import LocalSnapshotRequest, SnapshotLimits, source_instance_id


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


class MaintainerLifecycleIntegrationTest(unittest.TestCase):
    def test_vendored_promotion_survives_author_checkout_disappearance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            author = Path(temporary) / "author"
            package = author / "github"
            package.mkdir(parents=True)
            manifest = {
                "schema": "aart.dev/mcp/v1",
                "artifact": {"name": "github-mcp", "kind": "mcp", "version": "1.0.0"},
                "payload": {"include": ["server.py"]},
                "transport": {"type": "stdio"},
                "runtime": {"type": "python", "version": ">=3.11"},
                "launch": {"type": "python", "entrypoint": "server.py"},
            }
            (package / "aart.json").write_text(json.dumps(manifest), encoding="utf-8")
            (package / "server.py").write_text("print('durable')\n", encoding="utf-8")
            alias = SourceAlias("authors")
            configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(author), None, True)
            acquired = read_local_snapshot(
                LocalSnapshotRequest(
                    source_instance_id(configured),
                    alias,
                    str(author),
                    SnapshotLimits(),
                )
            )
            assert isinstance(acquired, Ok)
            compiled = compile_author_snapshot(
                acquired.value.snapshot,
                source_alias=alias,
                source="https://git.example/authors.git",
                revision="a" * 40,
            )
            assert isinstance(compiled, Ok)
            scanned = reconcile_source_scan(
                alias,
                "a" * 40,
                compiled.value,
                previous=(),
                approved=(),
                target_registry=SourceAlias("company"),
            )
            assert isinstance(scanned, Ok)
            ready = scanned.value.active[0]
            ready = ready.__class__(assess_candidate(ready.candidate), ready.artifact)
            planned = plan_bulk_promotion(
                SourceSnapshot(SnapshotOrigin.LOCAL, ()),
                (ready,),
                evidence=((ready.candidate.id, PromotionEvidence(_digest("7"), _digest("8"))),),
                approved=(),
            )
            assert isinstance(planned, Ok)
            vendored = project_promotion(SourceSnapshot(SnapshotOrigin.LOCAL, ()), planned.value)
            assert isinstance(vendored, Ok)

        files = {
            str(item.path): item.content
            for item in vendored.value.entries
            if item.kind is SnapshotEntryKind.FILE
        }
        self.assertEqual(
            files["artifacts/mcp/github-mcp/1.0.0/payload/server.py"],
            b"print('durable')\n",
        )
        self.assertIn("artifacts/mcp/github-mcp/1.0.0/artifact.json", files)
        self.assertIn("artifacts/mcp/github-mcp/1.0.0/provenance.json", files)


if __name__ == "__main__":
    unittest.main()
