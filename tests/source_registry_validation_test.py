from __future__ import annotations

import json
import unittest

from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.domain.identifiers import SourceAlias, SourceId
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.runtime_contract import EXECUTABLE_CAPABILITIES, EXECUTABLE_VERSION
from aart_cli.sources.model import (
    SourceValidationRequest,
    make_source_candidate,
    source_instance_id,
)
from aart_cli.sources.validation import validate_configured_source_candidate
from tests.registry_maintenance_fixtures import (
    append_snapshot_file,
    approved_registry_snapshot,
    empty_registry_snapshot,
    replace_snapshot_file,
)


def _unwrap(result):
    assert isinstance(result, Ok), result
    return result.value


def _registry_source() -> ConfiguredSource:
    return ConfiguredSource(
        SourceAlias("company"),
        SourceKind.REGISTRY_GIT,
        "https://github.com/example/reference-registry.git",
        "main",
        True,
    )


def _candidate(source: ConfiguredSource, snapshot: SourceSnapshot):
    return _unwrap(
        make_source_candidate(
            source_instance_id(source),
            source.alias,
            "a" * 40,
            snapshot,
        )
    )


def _validate(source: ConfiguredSource, candidate):
    return validate_configured_source_candidate(
        source,
        SourceValidationRequest(candidate, EXECUTABLE_VERSION, EXECUTABLE_CAPABILITIES),
    )


class RegistrySourceValidationTest(unittest.TestCase):
    def test_an_approved_registry_is_admitted_with_its_registry_identity(self) -> None:
        source = _registry_source()

        result = _validate(source, _candidate(source, approved_registry_snapshot()))

        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        self.assertEqual(result.value.declared_source_id, SourceId("test-registry"))
        self.assertEqual(result.value.candidate, _candidate(source, approved_registry_snapshot()))

    def test_a_registry_carrying_the_retired_representation_is_refused_by_name(self) -> None:
        """CP-26.4: the workspace compiler is not a second admission route to fall back on."""

        source = _registry_source()

        retired = approved_registry_snapshot()
        for name in ("aart.lock.json", "aart.index.json"):
            retired = SourceSnapshot(
                retired.origin,
                (
                    *retired.entries,
                    SnapshotEntry(
                        _unwrap(parse_relative_path(name)), SnapshotEntryKind.FILE, b"{}"
                    ),
                ),
            )

        result = _validate(source, _candidate(source, retired))

        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        message = result.diagnostics[0].message
        self.assertIn("retired authoring-workspace representation", message)
        self.assertIn("aart.lock.json", message)
        self.assertIn("aart.index.json", message)

    def test_a_registry_mixing_both_representations_is_refused_by_name(self) -> None:
        approved = approved_registry_snapshot()
        parsed = _unwrap(parse_relative_path("aart.lock.json"))
        mixed = SourceSnapshot(
            approved.origin,
            (*approved.entries, SnapshotEntry(parsed, SnapshotEntryKind.FILE, b"{}")),
        )
        source = _registry_source()

        result = _validate(source, _candidate(source, mixed))

        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertIn(
            "retired authoring-workspace representation",
            result.diagnostics[0].message,
        )

    def test_a_tree_that_declares_no_registry_is_refused_as_not_canonical(self) -> None:
        """The refusal has to say which shape was expected, not just that something was wrong."""

        source = _registry_source()
        anonymous = SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                SnapshotEntry(
                    _unwrap(parse_relative_path("README.md")), SnapshotEntryKind.FILE, b""
                ),
            ),
        )

        result = _validate(source, _candidate(source, anonymous))

        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        message = result.diagnostics[0].message
        self.assertIn("is not a canonical approved Registry", message)
        self.assertIn("aart-cli-registry.json", message)
        self.assertIn("aart-cli-source.json", message)

    def test_an_empty_approved_registry_still_has_to_bind_its_catalogs(self) -> None:
        """Nothing promoted yet is not nothing to check: the catalogs still describe this tree."""

        source = _registry_source()
        damaged = append_snapshot_file(empty_registry_snapshot(), "registry/index.json", b"{}")

        result = _validate(source, _candidate(source, damaged))

        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertIn("registry catalog is missing or stale", result.diagnostics[0].message)

    def test_registry_validator_rejects_a_stale_approved_registry_catalog(self) -> None:
        """An approved projection still has to bind its exact content snapshot."""

        source = _registry_source()
        stale = replace_snapshot_file(approved_registry_snapshot(), "registry/index.json", b"{}")

        result = _validate(source, _candidate(source, stale))

        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        self.assertIn("registry catalog is missing or stale", result.diagnostics[0].message)

    def test_registry_validator_rejects_source_registry_identity_mismatch(self) -> None:
        source = _registry_source()
        approved = approved_registry_snapshot()
        declared = json.loads(
            next(
                entry.content
                for entry in approved.entries
                if str(entry.path) == "aart-cli-source.json"
            )
        )
        declared["source_id"] = "different-registry"
        mismatched = replace_snapshot_file(
            approved,
            "aart-cli-source.json",
            json.dumps(declared).encode(),
        )

        result = _validate(source, _candidate(source, mismatched))

        self.assertIsInstance(result, Err)
        assert isinstance(result, Err)
        message = result.diagnostics[0].message
        self.assertIn("the two identity documents disagree", message)
        self.assertIn("different-registry", message)


if __name__ == "__main__":
    unittest.main()
