from __future__ import annotations

import unittest

from aart_cli.domain.result import Ok
from aart_cli.protocol.capabilities import Capability
from aart_cli.protocol.semver import SemVer
from aart_cli.registry_commands.planning import (
    audit_registry_workspace,
    plan_registry_format,
    project_registry_workspace_plan,
    validate_registry_workspace,
)
from aart_cli.registry_commands.planning import (
    test_registry_compatibility as check_registry_compatibility,
)
from tests.registry_maintenance_fixtures import (
    append_snapshot_file,
    approved_registry_snapshot,
    empty_registry_snapshot,
    replace_snapshot_file,
    snapshot_file,
)

CAPABILITIES = (
    Capability("artifact-manifest-v1"),
    Capability("lockfile-v1"),
    Capability("registry-entry-v1"),
)
VERSION = SemVer(1, 0, 0)


class RegistryQualityPlanningTest(unittest.TestCase):
    def test_format_is_canonical_and_checkable_without_mutation(self) -> None:
        snapshot = replace_snapshot_file(
            empty_registry_snapshot(),
            "aart-registry.json",
            b'{ "schema_version": 1, "protocol_version": 1, "registry_id": "test-registry", '
            b'"display_name": "Test Registry", "requires_aart": {"min_inclusive": "1.0.0", '
            b'"max_exclusive": "2.0.0"}, "required_capabilities": [], '
            b'"default_channel": "main", "services": {} }',
        )
        plan = plan_registry_format(snapshot)
        assert isinstance(plan, Ok), plan
        # One path: the marker this test spelled non-canonically, and nothing else.
        self.assertEqual(plan.value.changed_paths, 1)
        projected = project_registry_workspace_plan(snapshot, plan.value)
        assert isinstance(projected, Ok)
        canonical = plan_registry_format(projected.value)
        assert isinstance(canonical, Ok)
        self.assertEqual(canonical.value.changed_paths, 0)

    def test_format_never_rewrites_json_that_belongs_to_artifact_payload(self) -> None:
        payload = b'{ "command": "leave-byte-exact" }\n'
        snapshot = append_snapshot_file(
            empty_registry_snapshot(),
            "artifacts/mcp/demo/payload/mcp.json",
            payload,
        )

        planned = plan_registry_format(snapshot)
        assert isinstance(planned, Ok)
        projected = project_registry_workspace_plan(snapshot, planned.value)
        assert isinstance(projected, Ok)

        self.assertEqual(
            snapshot_file(projected.value, "artifacts/mcp/demo/payload/mcp.json"),
            payload,
        )

    def test_validate_audit_and_the_compatibility_matrix_are_read_only(self) -> None:
        """An approved Registry passes every quality gate without any of them proposing a write."""

        registry = approved_registry_snapshot()
        formatted = plan_registry_format(registry)
        assert isinstance(formatted, Ok)
        self.assertEqual(formatted.value.changed_paths, 0)
        validated = validate_registry_workspace(
            registry,
            executable_version=VERSION,
            available_capabilities=CAPABILITIES,
        )
        assert isinstance(validated, Ok), validated
        self.assertTrue(validated.value.passed)
        audited = audit_registry_workspace(
            registry,
            executable_version=VERSION,
            available_capabilities=CAPABILITIES,
        )
        assert isinstance(audited, Ok), audited
        self.assertTrue(audited.value.passed)
        matrix = check_registry_compatibility(
            registry,
            minimum=SemVer(1, 0, 0),
            latest=SemVer(1, 9, 9),
            available_capabilities=CAPABILITIES,
        )
        assert isinstance(matrix, Ok), matrix
        self.assertEqual(tuple(item.name for item in matrix.value.checks), ("minimum", "latest"))
        self.assertTrue(matrix.value.passed)

    def test_a_registry_carrying_the_retired_representation_is_refused_by_name(self) -> None:
        """CP-26.5: the workspace compiler is gone, so an unversioned package is named, not built."""

        retired = append_snapshot_file(
            empty_registry_snapshot(),
            "artifacts/mcp/demo/artifact.json",
            b"{}",
        )

        validated = validate_registry_workspace(
            retired,
            executable_version=VERSION,
            available_capabilities=CAPABILITIES,
        )

        assert isinstance(validated, Ok), validated
        self.assertFalse(validated.value.passed)
        messages = " ".join(
            diagnostic.message
            for check in validated.value.checks
            for diagnostic in check.diagnostics
        )
        self.assertIn("retired authoring-workspace representation", messages)
        self.assertIn("artifacts/mcp/demo/artifact.json", messages)


if __name__ == "__main__":
    unittest.main()
