"""`requires` is intra-registry, and the refusal says so.

`registry build` refuses `skill/la-probe requires missing skill/using-residues` when the dependency
lives in another configured registry.  The restriction is deliberate — a cross-registry dependency
breaks whenever a maintainer who does not own the artifact changes their own registry — and the
refusal has to say so.  "requires missing" reads as "not published yet", so a maintainer
waits for a publication that will never make the build pass.

These tests hold the wording to the rule: every refusal is produced by the real planning path, never
by a literal written here.  `CP-26.5` removed the second site of the rule along with the retired
workspace's compiled index, so the graph validator is bound into the approved representation's own
maintenance path and checked there (`D-325`).
"""

from __future__ import annotations

import json
import unittest

from agent_artifacts.domain.identifiers import SourceId
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.native_tree import SnapshotEntry, SourceSnapshot
from agent_artifacts.protocol.registry_index import (
    index_artifact_from_package,
    validate_registry_graph,
)
from agent_artifacts.protocol.registry_schema import parse_registry_manifest
from agent_artifacts.protocol.semver import parse_semver
from agent_artifacts.registry_maintenance.planning import registry_native_content
from tests.registry_index_test import _digest, _package
from tests.registry_maintenance_fixtures import (
    append_snapshot_file,
    approved_registry_snapshot,
    replace_snapshot_file,
    snapshot_file,
)
from tests.source_remediation_test import _COMMAND, _parse_failure

_OWNED = "mcp/github-mcp"


def _collection(name: str, *members: str) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "name": name,
            "summary": "One collection.",
            "artifacts": [
                {"type": member.split("/")[0], "name": member.split("/")[1]} for member in members
            ],
        }
    ).encode()


def _with_collection(name: str, *members: str) -> SourceSnapshot:
    """An approved Registry that declares a collection root and holds one collection in it."""

    registry = approved_registry_snapshot()
    source = json.loads(snapshot_file(registry, "aart-source.json"))
    source["collection_roots"] = ["collections"]
    declared = replace_snapshot_file(registry, "aart-source.json", json.dumps(source).encode())
    return append_snapshot_file(declared, f"collections/{name}.json", _collection(name, *members))


def _compiled(snapshot: SourceSnapshot):
    """Compile the registry's own content exactly as every maintainer command does."""

    files: dict[str, SnapshotEntry] = {str(entry.path): entry for entry in snapshot.entries}
    registry = parse_registry_manifest(files["aart-registry.json"].content)
    assert isinstance(registry, Ok), registry
    version = parse_semver("2.1.0")
    assert isinstance(version, Ok), version
    return registry_native_content(
        snapshot,
        files,
        registry.value,
        executable_version=version.value,
        available_capabilities=(),
    )


def _refusal(result) -> tuple[str, tuple[str, ...]]:
    assert isinstance(result, Err), f"expected a refusal, got {result}"
    assert len(result.diagnostics) == 1, result.diagnostics
    diagnostic = result.diagnostics[0]
    return diagnostic.message, diagnostic.remediation


class DependencyScopeRefusalTest(unittest.TestCase):
    def test_the_index_graph_refuses_a_dependency_the_registry_does_not_publish(self) -> None:
        artifact = index_artifact_from_package(
            _package("review", requires=[{"type": "skill", "name": "helper"}]),
            source_id=SourceId("company-registry"),
            object_digest=_digest("3"),
        )

        message, remediation = _refusal(validate_registry_graph((artifact,), ()))

        self.assertIn("skill/review requires skill/helper", message)
        self.assertIn("this registry does not publish", message)
        self.assertIn("requires resolves inside one registry", message)
        self.assertNotIn("missing", message)
        self.assertTrue(remediation)


class ApprovedRegistryGraphTest(unittest.TestCase):
    """`CP-26.5`: the rule's second site moved with the representation, it did not disappear.

    `build_registry_index` compiled the retired workspace's catalog and was where the maintenance
    path met `validate_registry_graph`. Deleting it would have left the approved representation with
    no graph check at all, so `registry_native_content` calls the validator directly (`D-325`).
    """

    def test_an_approved_registry_with_nothing_unresolved_compiles(self) -> None:
        self.assertIsInstance(_compiled(approved_registry_snapshot()), Ok)

    def test_a_collection_naming_an_artifact_the_registry_does_not_publish_is_refused(self) -> None:
        message, _remediation = _refusal(_compiled(_with_collection("essentials", "mcp/absent")))

        self.assertIn("absent", message)

    def test_membership_reaches_the_maintenance_path_derived_rather_than_declared(self) -> None:
        compiled = _compiled(_with_collection("essentials", _OWNED))

        assert isinstance(compiled, Ok), compiled
        artifacts, collections = compiled.value
        self.assertEqual(tuple(item.name for item in collections), ("essentials",))
        self.assertEqual(
            {str(item.identity): item.collections for item in artifacts},
            {_OWNED: ("essentials",)},
        )


class DependencyScopeRemediationTest(unittest.TestCase):
    """Every command the remediation names must exist."""

    def _remediation(self) -> tuple[str, ...]:
        artifact = index_artifact_from_package(
            _package("review", requires=[{"type": "skill", "name": "helper"}]),
            source_id=SourceId("company-registry"),
            object_digest=_digest("3"),
        )
        _message, remediation = _refusal(validate_registry_graph((artifact,), ()))
        return remediation

    def test_every_command_the_remediation_names_is_one_the_parser_accepts(self) -> None:
        remediation = self._remediation()

        commands = tuple(match for line in remediation for match in _COMMAND.findall(line))
        self.assertTrue(commands, f"remediation names no command: {remediation}")
        for command in commands:
            failure = _parse_failure(command)
            self.assertIsNone(failure, f"`{command}` is not accepted: {failure}")

    def test_the_remediation_names_the_route_that_works_in_this_release(self) -> None:
        """The dependency is authored outside the Registry, then scanned and promoted."""

        joined = " ".join(self._remediation())

        self.assertIn("aart registry scan", joined)
        self.assertIn("aart registry promote", joined)
        self.assertIn("copy the upstream content into an artifact this registry owns", joined)


if __name__ == "__main__":
    unittest.main()
