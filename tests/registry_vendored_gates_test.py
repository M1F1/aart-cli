"""A copy that contradicts its own record fails validate and audit.

The check that matters is the one no compiled catalog could make: a vendored package records the
origin digest it was copied from, so substituting a payload byte contradicts the package's own
provenance. A catalog derived from the bytes that are there agrees with any substitution, which is
why this is asserted over the package rather than over anything generated beside it.

`CP-26.5` took the compiled lock and index away, so these gates now run over the checkout directly.
They were red for the length of `B-149`, because `project_vendored_package` still wrote the retired
unversioned `artifacts/<kind>/<name>/` layout that `registry_native_content` refuses by name. The
refusal was correct and the writer is what moved: `vendor` now projects into the approved
representation's versioned package and promotes it (`D-326`). The claims below were kept whole
through that, rather than deleted to reach green (`D-323`).
"""

from __future__ import annotations

import json
import unittest

from agent_artifacts.domain.identifiers import ArtifactIdentity
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.capabilities import Capability
from agent_artifacts.protocol.json import canonical_json_bytes
from agent_artifacts.protocol.native_schema import parse_provenance, provenance_to_json
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.protocol.registry_models import ReviewRecord
from agent_artifacts.protocol.semver import SemVer
from agent_artifacts.registry_commands.planning import (
    audit_registry_workspace,
    plan_artifact_vendor,
    project_registry_workspace_plan,
    validate_registry_workspace,
)
from agent_artifacts.registry_maintenance.model import NativeReferenceAcquisition
from agent_artifacts.registry_maintenance.vendoring import (
    VendorOptions,
)
from tests.registry_maintenance_fixtures import (
    empty_registry_snapshot,
    replace_snapshot_file,
    snapshot_file,
)

_CAPABILITIES = (Capability("artifact-manifest-v1"),)
_VERSION = SemVer(2, 4, 0)
_COMMIT = "c" * 40
_URL = "https://github.com/example/atlassian-mcp.git"
_MCP_JSON = (
    json.dumps({"name": "atlassian", "server": {"command": "npx", "args": ["-y", "srv"]}}).encode()
    + b"\n"
)
_BASE = "artifacts/mcp/atlassian/1.0.0"


def _path(raw: str):
    parsed = parse_relative_path(raw)
    assert isinstance(parsed, Ok), parsed
    return parsed.value


def _file(raw: str, content: bytes = b"x", *, executable: bool = False) -> SnapshotEntry:
    return SnapshotEntry(_path(raw), SnapshotEntryKind.FILE, content, executable)


def _directory(raw: str) -> SnapshotEntry:
    return SnapshotEntry(_path(raw), SnapshotEntryKind.DIRECTORY)


def _upstream() -> SourceSnapshot:
    return SourceSnapshot(
        SnapshotOrigin.IMMUTABLE_GIT,
        (
            _directory("servers"),
            _directory("servers/atlassian"),
            _file("servers/atlassian/index.js", b"console.log('serve');\n"),
            _directory("servers/atlassian/lib"),
            _file("servers/atlassian/lib/client.js", b"export const client = 1;\n"),
        ),
    )


def _vendored_registry() -> SourceSnapshot:
    """An otherwise empty registry that owns one vendored package."""

    snapshot = empty_registry_snapshot()
    staging = _file(f"{_BASE}/payload/mcp.json", _MCP_JSON)
    snapshot = SourceSnapshot(snapshot.origin, (*snapshot.entries, staging))
    planned = plan_artifact_vendor(
        snapshot,
        NativeReferenceAcquisition(_URL, "v1.4.0", _COMMIT, _upstream()),
        VendorOptions(
            ArtifactIdentity("mcp", "atlassian"),
            SemVer(1, 0, 0),
            "Atlassian MCP server, vendored from upstream.",
            ("claude",),
            ("darwin",),
            ("project",),
            ("copy",),
            license="MIT",
        ),
        path=_path("servers/atlassian"),
        review=ReviewRecord("approved", "manual-review-v1"),
        importer_version=_VERSION,
    )
    assert isinstance(planned, Ok), planned
    projected = project_registry_workspace_plan(snapshot, planned.value.plan)
    assert isinstance(projected, Ok), projected
    return projected.value


def _validate(snapshot: SourceSnapshot):
    report = validate_registry_workspace(
        snapshot,
        executable_version=_VERSION,
        available_capabilities=_CAPABILITIES,
    )
    assert isinstance(report, Ok), report
    return report.value


def _audit(snapshot: SourceSnapshot):
    report = audit_registry_workspace(
        snapshot, executable_version=_VERSION, available_capabilities=_CAPABILITIES
    )
    assert isinstance(report, Ok), report
    return report.value


def _messages(report) -> str:
    return "; ".join(
        diagnostic.message for check in report.checks for diagnostic in check.diagnostics
    )


def _tampered(snapshot: SourceSnapshot) -> SourceSnapshot:
    return replace_snapshot_file(
        snapshot, f"{_BASE}/payload/index.js", b"console.log('exfiltrate');\n"
    )


class VendoredCopyGateTest(unittest.TestCase):
    def test_an_untouched_vendored_registry_passes_both_gates(self) -> None:
        registry = _vendored_registry()
        self.assertTrue(_validate(registry).passed, _messages(_validate(registry)))
        self.assertTrue(_audit(registry).passed, _messages(_audit(registry)))

    def test_a_substituted_payload_fails_validate_and_audit_after_relocking(self) -> None:
        """A substituted payload, end to end and offline."""

        registry = _tampered(_vendored_registry())
        validated = _validate(registry)
        audited = _audit(registry)
        self.assertFalse(validated.passed)
        self.assertFalse(audited.passed)
        for report in (validated, audited):
            self.assertIn("no longer matches the origin it records", _messages(report))
            self.assertIn("mcp/atlassian", _messages(report))

    def test_the_finding_names_both_digests(self) -> None:
        recorded = parse_provenance(
            snapshot_file(_vendored_registry(), f"{_BASE}/provenance.json"),
            path=f"{_BASE}/provenance.json",
        )
        assert isinstance(recorded, Ok), recorded
        message = _messages(_audit(_tampered(_vendored_registry())))
        self.assertIn(str(recorded.value.origin.input_digest), message)
        self.assertIn("copied payload files digest to sha256:", message)

    def test_a_hand_edited_authored_list_does_not_hide_the_substitution(self) -> None:
        """Declaring the edited file authored removes it from the copy, which is still a mismatch."""

        registry = _tampered(_vendored_registry())
        document = parse_provenance(
            snapshot_file(registry, f"{_BASE}/provenance.json"), path=f"{_BASE}/provenance.json"
        )
        assert isinstance(document, Ok), document
        raw = json.loads(canonical_json_bytes(provenance_to_json(document.value)))
        raw["aart.vendor"]["authored"] = ["payload/index.js", "payload/mcp.json"]
        edited = replace_snapshot_file(
            registry, f"{_BASE}/provenance.json", json.dumps(raw).encode() + b"\n"
        )
        self.assertFalse(_audit(edited).passed)
        self.assertFalse(_validate(edited).passed)

    def test_an_approved_package_without_provenance_is_refused(self) -> None:
        """The approved package digest binds provenance as well as payload."""

        registry = _vendored_registry()
        without = SourceSnapshot(
            registry.origin,
            tuple(
                entry for entry in registry.entries if str(entry.path) != f"{_BASE}/provenance.json"
            ),
        )
        self.assertFalse(_validate(without).passed)
        self.assertNotIn("no longer matches", _messages(_audit(without)))

    def test_a_provenance_written_by_another_importer_is_not_verified(self) -> None:
        registry = _vendored_registry()
        raw = json.loads(snapshot_file(registry, f"{_BASE}/provenance.json"))
        raw["importer"]["id"] = "native-promote-v1"
        del raw["aart.vendor"]
        foreign = replace_snapshot_file(
            _tampered(registry), f"{_BASE}/provenance.json", json.dumps(raw).encode() + b"\n"
        )
        self.assertNotIn("no longer matches", _messages(_validate(foreign)))
        self.assertNotIn("no longer matches", _messages(_audit(foreign)))


if __name__ == "__main__":
    unittest.main()
