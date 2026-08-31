"""What the canonical machine says about installations it did not record.

Canonical receipts are MCP-specific. Skills, Rules, Hooks and Memory are installed today through
the setup path, which records them in a project or user `manifest.json` the canonical reader has
never opened. The danger is not that they are missing from a list: it is that their absence reads
as a fact. A shell that says a Skill is not installed will happily install over it, and a repair
that sees no record has nothing to repair.

So the rule this file holds is narrow and absolute: the absence of a canonical receipt is never
evidence that an installation does not exist.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import tempfile
import unittest

from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    ObjectDigest,
    SourceAlias,
    SourceId,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.install_state.model import (
    ArtifactEvidence,
    EffectProof,
    InstallationRecord,
    InstallState,
    SourceEvidence,
)
from agent_artifacts.install_state.schema import install_state_bytes
from agent_artifacts.io.consumer_machine import read_consumer_machine
from agent_artifacts.protocol.semver import SemVer
from agent_artifacts.tui_consumer import PresentationProfile, render_installed_artifact

TODAY = dt.date(2026, 8, 31)


def _digest(character: str) -> ObjectDigest:
    return ObjectDigest("sha256", character * 64)


def _legacy_record(kind: str, name: str, scope: str = "project") -> InstallationRecord:
    """One installation of a kind no canonical receipt can describe yet."""

    identity = ArtifactIdentity(kind, name)
    destination = (
        f".claude/{kind}s/{name}" if scope == "project" else f"/home/alice/.claude/{kind}s/{name}"
    )
    return InstallationRecord(
        coordinate=ArtifactCoordinate(SourceAlias("company"), identity),
        source=SourceEvidence(
            alias=SourceAlias("company"),
            declared_id=SourceId("company-agent-artifacts"),
            kind=SourceKind.REGISTRY_GIT,
            origin="https://github.com/acme/agent-artifacts-registry.git",
            resolved_commit="a" * 40,
            subscription_ref="main",
        ),
        artifact=ArtifactEvidence(
            identity=identity,
            version=SemVer(2, 1, 0),
            manifest_digest=_digest("1"),
            payload_digest=_digest("2"),
            object_digest=_digest("3"),
        ),
        profile="claude",
        profile_version=1,
        scope=scope,
        requested_mode="copy",
        effects=(
            EffectProof(
                kind="copy-tree",
                destination=destination,
                actual_mode="copy",
                installed_digest=_digest("4"),
                source_path=f"{kind}s/{name}",
                created_destination=True,
                overwrote=False,
            ),
        ),
    )


class LegacyInstallVisibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.project = self.root / "project"
        self.data_root = self.root / "data"
        self.state_root = self.data_root / "state"
        self.state_root.mkdir(parents=True)
        (self.project / ".agent-artifacts").mkdir(parents=True)

    def _write(self, *records: InstallationRecord) -> None:
        (self.project / ".agent-artifacts/manifest.json").write_bytes(
            install_state_bytes(InstallState(2, records))
        )

    def _machine(self):
        read = read_consumer_machine(
            state_root=str(self.state_root),
            harness_root=str(self.project),
            today=TODAY,
            project_root=str(self.project),
            user_home=str(self.root / "home"),
            data_root=str(self.data_root),
        )
        self.assertIsInstance(read, Ok, getattr(read, "diagnostics", ()))
        return read.value

    def test_an_installation_only_the_legacy_manifest_knows_is_still_installed(self) -> None:
        self._write(_legacy_record("skill", "code-review"))

        machine = self._machine()

        self.assertEqual(
            [item.coordinate for item in machine.installed], ["company/skill/code-review"]
        )

    def test_its_health_is_unknown_rather_than_asserted(self) -> None:
        """Nothing canonical observed it, and a record is not an observation."""

        self._write(_legacy_record("guideline", "house-style"))

        machine = self._machine()

        self.assertEqual(machine.installed[0].health, "unknown")
        self.assertTrue(
            all(item.kind == "unobserved" for item in machine.installed[0].drift),
            machine.installed[0].drift,
        )

    def test_no_canonical_action_is_offered_for_something_canonical_cannot_describe(self) -> None:
        """Offering repair would promise a reconciliation against a desired state nobody has."""

        self._write(_legacy_record("hook", "pre-commit"))

        machine = self._machine()

        self.assertEqual(machine.installed[0].actions, ())

    def test_every_kind_the_setup_path_installs_survives_the_read(self) -> None:
        self._write(
            _legacy_record("skill", "code-review"),
            _legacy_record("guideline", "house-style"),
            _legacy_record("hook", "pre-commit"),
            _legacy_record("memory", "team-context"),
        )

        machine = self._machine()

        self.assertEqual(
            sorted(item.coordinate.rsplit("/", 2)[1] for item in machine.installed),
            ["guideline", "hook", "memory", "skill"],
        )

    def test_a_user_scope_manifest_is_read_beside_the_project_one(self) -> None:
        """Two scopes, two manifests. Reading one is the same omission as reading neither."""

        (self.state_root / "manifest.json").write_bytes(
            install_state_bytes(
                InstallState(2, (_legacy_record("memory", "team-context", "user"),))
            )
        )
        self._write(_legacy_record("skill", "code-review"))

        machine = self._machine()

        self.assertEqual(
            sorted(item.coordinate for item in machine.installed),
            ["company/memory/team-context", "company/skill/code-review"],
        )

    def test_it_is_drawn_without_claiming_a_fault_or_a_verification(self) -> None:
        self._write(_legacy_record("skill", "code-review"))

        drawn = render_installed_artifact(self._machine().installed[0], PresentationProfile.VERBOSE)

        self.assertIn("company/skill/code-review — unknown", drawn)
        self.assertIn("Installed here, but nothing canonical has observed it yet.", drawn)
        self.assertIn("No action is offered until it is observed.", drawn)
        self.assertNotIn("Verified against its desired state.", drawn)
        self.assertFalse([line for line in drawn if line.startswith("Needs attention")])

    def test_the_dashboard_counts_it_installed_without_counting_it_healthy(self) -> None:
        """Counting it ready would be the same lie in a smaller font."""

        self._write(_legacy_record("skill", "code-review"))

        dashboard = self._machine().dashboard

        self.assertEqual(dashboard.installed_count, 1)
        self.assertEqual(dashboard.ready_count, 0)
        self.assertEqual(dashboard.update_count, 0)
        self.assertEqual(dashboard.attention_count, 0)

    def test_the_doctor_neither_reports_it_as_an_issue_nor_offers_to_repair_it(self) -> None:
        self._write(_legacy_record("hook", "pre-commit"))

        doctor = self._machine().doctor

        assert doctor is not None
        self.assertEqual(doctor.issues, ())
        self.assertEqual(doctor.repairable_issues, ())
        self.assertEqual(doctor.actions, ())
        self.assertEqual(doctor.ready_count, 0)

    def test_no_manifest_is_no_legacy_installation_rather_than_a_failure(self) -> None:
        machine = self._machine()

        self.assertEqual(machine.installed, ())

    def test_an_unreadable_manifest_refuses_rather_than_reporting_nothing_installed(self) -> None:
        """The one answer that is never safe here is "nothing is installed"."""

        (self.project / ".agent-artifacts/manifest.json").write_text(
            json.dumps({"schema_version": 2, "installations": [{"broken": True}]}),
            encoding="utf-8",
        )

        read = read_consumer_machine(
            state_root=str(self.state_root),
            harness_root=str(self.project),
            today=TODAY,
            project_root=str(self.project),
            user_home=str(self.root / "home"),
            data_root=str(self.data_root),
        )

        self.assertNotIsInstance(read, Ok)


if __name__ == "__main__":
    unittest.main()
