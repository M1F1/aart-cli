"""An empty registry's audit reports what does not apply, not what is missing.

`QA-015`/`B-089`. A registry that was just initialized has no artifacts at all, and the audit of it
passes. It nevertheless printed two warnings — that provenance coverage was partial and that no
per-object installation-risk evidence had been supplied — which read as defects in a registry that
has nothing to be defective about. `REGISTRY_AUDIT_NOTE` already exists for exactly this: a report
of what the audit did rather than what it found, carrying no remediation because there is nothing to
remedy (`_upstream_check_note` is the precedent). These two checks now use it when, and only when,
the registry holds no artifacts. The moment a package exists the findings are warnings again,
because then there really is an object whose risk nobody assessed.
"""

from __future__ import annotations

import unittest

from agent_artifacts.domain.diagnostics import Severity
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.capabilities import Capability
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.protocol.semver import SemVer
from agent_artifacts.registry_commands.planning import audit_registry_workspace
from tests.registry_maintenance_fixtures import (
    append_snapshot_file,
    empty_registry_snapshot,
    registry_with_owned_package,
    snapshot_file,
)

CAPABILITIES = (
    Capability("artifact-manifest-v1"),
    Capability("lockfile-v1"),
    Capability("registry-entry-v1"),
)
VERSION = SemVer(1, 0, 0)


def _audit(snapshot):
    audited = audit_registry_workspace(
        snapshot,
        executable_version=VERSION,
        available_capabilities=CAPABILITIES,
    )
    assert isinstance(audited, Ok), audited
    return audited.value


def _diagnostics(report):
    return tuple(item for check in report.checks for item in check.diagnostics)


class EmptyRegistryAuditTest(unittest.TestCase):
    def test_an_empty_registry_audit_raises_no_warnings_at_all(self) -> None:
        report = _audit(empty_registry_snapshot())

        self.assertTrue(report.passed)
        self.assertEqual(
            tuple(
                item.message for item in _diagnostics(report) if item.severity is not Severity.INFO
            ),
            (),
        )

    def test_an_empty_registry_states_both_checks_as_not_applicable(self) -> None:
        report = _audit(empty_registry_snapshot())

        messages = tuple(item.message for item in _diagnostics(report))
        self.assertTrue(
            any("provenance" in message and "no artifacts" in message for message in messages),
            messages,
        )
        self.assertTrue(
            any(
                "installation risk" in message and "no artifacts" in message for message in messages
            ),
            messages,
        )

    def test_a_not_applicable_note_offers_no_remediation(self) -> None:
        report = _audit(empty_registry_snapshot())

        for item in _diagnostics(report):
            self.assertEqual(item.remediation, (), item.message)

    def test_a_manifest_outside_the_declared_roots_is_not_a_package_of_this_registry(
        self,
    ) -> None:
        """`aart-source.json` declares where this registry's packages live, and only there.

        A valid `artifact.json` sitting outside those roots belongs to something else — a vendored
        working copy, a fixture, an unrelated tree committed alongside — so it must not make an
        empty registry look occupied and it must not be audited as content this registry publishes.
        """

        stray = append_snapshot_file(
            empty_registry_snapshot(),
            "vendor/example/artifact.json",
            snapshot_file(
                registry_with_owned_package(), "artifacts/skill/code-review/artifact.json"
            ),
        )

        report = _audit(stray)

        self.assertTrue(report.passed)
        self.assertEqual(
            tuple(
                item.message for item in _diagnostics(report) if item.severity is not Severity.INFO
            ),
            (),
        )

    def test_a_workspace_holding_a_symlink_is_refused_rather_than_audited(self) -> None:
        """Nothing about "empty" relaxes the snapshot safety boundary.

        A registry workspace containing a symlink — including one named `artifact.json` under a
        declared artifact root — is refused as a whole before any per-file check runs, so a link
        can neither be read as a manifest nor make an empty registry look occupied. The refusal is
        an error, which is what keeps it distinct from the notes this audit reports on an empty
        registry that is genuinely fine.
        """

        base = empty_registry_snapshot()
        path = parse_relative_path("artifacts/skill/linked/artifact.json")
        assert isinstance(path, Ok)
        linked = SourceSnapshot(
            base.origin,
            (
                *base.entries,
                SnapshotEntry(path.value, SnapshotEntryKind.SYMLINK, b"../../../elsewhere"),
            ),
        )

        report = _audit(linked)

        self.assertFalse(report.passed)
        self.assertEqual(tuple(item.severity for item in _diagnostics(report)), (Severity.ERROR,))
        self.assertIn("safe inert workspace snapshot", _diagnostics(report)[0].message)

    def test_a_registry_holding_a_package_still_warns_that_risk_is_unassessed(self) -> None:
        report = _audit(registry_with_owned_package())

        warnings = tuple(
            item.message for item in _diagnostics(report) if item.severity is Severity.WARNING
        )
        self.assertTrue(
            any("installation-risk evidence" in message for message in warnings), warnings
        )

    def test_a_registry_holding_a_package_still_records_the_coverage_limit(self) -> None:
        report = _audit(registry_with_owned_package())

        warnings = tuple(
            item.message for item in _diagnostics(report) if item.severity is Severity.WARNING
        )
        self.assertTrue(any("no external references" in message for message in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
