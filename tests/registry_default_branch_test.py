"""§188, INV-289, D-470: the Registry's default branch takes only an upstream's default branch.

A maintainer can adopt an artifact from any branch of its upstream, which is what trying a change
before it lands needs. But a version adopted from a feature branch holds what the upstream never
accepted, and once the Registry's default branch has it, everyone installs it. `upstream adopt`
now records whether the adopted commit is reachable from the upstream's default branch, and the
generated Registry CI (`registry audit --for-default-branch`) refuses every version without that
record saying so. The record is read from committed bytes, so the CI needs no access to the
upstream.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aart_cli.domain.diagnostics import Severity
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Ok
from aart_cli.io.git_acquisition import acquire_git_snapshot, commit_on_default_branch
from aart_cli.protocol.capabilities import Capability
from aart_cli.protocol.json import JsonObject
from aart_cli.protocol.semver import SemVer
from aart_cli.registry_commands.planning import audit_registry_workspace
from aart_cli.registry_maintenance.model import adoption_record
from aart_cli.sources.model import GitSnapshotRequest, SnapshotLimits, SourceInstanceId
from tests.registry_maintenance_fixtures import approved_registry_snapshot

CAPABILITIES = (
    Capability("artifact-manifest-v1"),
    Capability("lockfile-v1"),
    Capability("registry-entry-v1"),
)
FIXTURE = Path(__file__).parent / "fixtures" / "protocol" / "native-source-v1"


def _branch_findings(snapshot, *, strict: bool):
    audited = audit_registry_workspace(
        snapshot,
        executable_version=SemVer(1, 0, 0),
        available_capabilities=CAPABILITIES,
        for_default_branch=strict,
    )
    assert isinstance(audited, Ok), audited
    findings = tuple(
        diagnostic
        for check in audited.value.checks
        for diagnostic in check.diagnostics
        if "default branch" in diagnostic.message
    )
    return audited.value.passed, findings


class AuditTest(unittest.TestCase):
    def test_a_version_adopted_from_the_default_branch_passes(self) -> None:
        for strict in (False, True):
            with self.subTest(strict=strict):
                passed, findings = _branch_findings(
                    approved_registry_snapshot(adoption=adoption_record("v1.2.0", True)),
                    strict=strict,
                )

                self.assertTrue(passed)
                self.assertEqual(findings, ())

    def test_a_version_adopted_from_another_branch_is_told_and_refused_by_ci(self) -> None:
        snapshot = approved_registry_snapshot(adoption=adoption_record("feature/jira", False))
        for strict, severity in ((False, Severity.WARNING), (True, Severity.ERROR)):
            with self.subTest(strict=strict):
                passed, findings = _branch_findings(snapshot, strict=strict)

                self.assertEqual(passed, not strict)
                self.assertEqual(len(findings), 1, findings)
                self.assertIs(findings[0].severity, severity)
                self.assertIn("mcp/github-mcp@1.0.0", findings[0].message)
                self.assertIn("feature/jira", findings[0].message)
                self.assertIn("https://git.example/servers.git", findings[0].message)
                self.assertIn("maintain upstream adopt", " ".join(findings[0].remediation))

    def test_ci_refuses_a_remote_version_nothing_shows_came_from_the_default_branch(self) -> None:
        unproven = (
            ("promoted", approved_registry_snapshot()),
            ("pinned", approved_registry_snapshot(mode="pinned-reference")),
            ("unrecorded", approved_registry_snapshot(adoption=JsonObject((("ref", "main"),)))),
        )
        for label, snapshot in unproven:
            with self.subTest(label=label):
                self.assertEqual(_branch_findings(snapshot, strict=False), (True, ()))
                passed, findings = _branch_findings(snapshot, strict=True)

                self.assertFalse(passed)
                self.assertEqual(len(findings), 1, findings)
                self.assertIs(findings[0].severity, Severity.ERROR)


class AdoptionRecordTest(unittest.TestCase):
    def test_the_record_says_the_branch_only_when_it_is_known(self) -> None:
        self.assertEqual(adoption_record("main", True).get("default_branch"), True)
        self.assertEqual(adoption_record("topic", False).get("default_branch"), False)
        self.assertIsNone(adoption_record("main", None).get("default_branch"))
        self.assertEqual(adoption_record("main", None).get("ref"), "main")


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


class ReachabilityTest(unittest.TestCase):
    def test_a_tag_on_the_default_branch_is_on_it_and_a_feature_branch_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = Path(root) / "repository"
            shutil.copytree(FIXTURE, repository)
            _git("init", "-b", "main", str(repository))
            _git("-C", str(repository), "config", "user.email", "test@example.invalid")
            _git("-C", str(repository), "config", "user.name", "AART Test")
            _git("-C", str(repository), "add", ".")
            _git("-C", str(repository), "commit", "-m", "initial")
            _git("-C", str(repository), "tag", "v1")
            _git("-C", str(repository), "switch", "-c", "feature")
            _git("-C", str(repository), "commit", "--allow-empty", "-m", "unreviewed")
            _git("-C", str(repository), "switch", "main")
            _git("-C", str(repository), "commit", "--allow-empty", "-m", "later")

            def on_default(ref: str) -> bool | None:
                request = GitSnapshotRequest(
                    SourceInstanceId("git-" + "d" * 32),
                    SourceAlias("upstream"),
                    repository.as_uri(),
                    ref,
                    str(Path(root) / "managed" / "mirror.git"),
                    str(Path(root) / "managed" / "tmp"),
                    SnapshotLimits(),
                    30,
                    allow_local_transport=True,
                )
                acquired = acquire_git_snapshot(request)
                assert isinstance(acquired, Ok), acquired
                return commit_on_default_branch(request, acquired.value.resolved_revision)

            self.assertIs(on_default("main"), True)
            self.assertIs(on_default("v1"), True)
            self.assertIs(on_default("feature"), False)


if __name__ == "__main__":
    unittest.main()
