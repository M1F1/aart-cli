from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.domain.identifiers import SourceAlias, SourceId
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.capabilities import parse_capability
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.protocol.semver import parse_semver
from agent_artifacts.sources.local import read_local_snapshot
from agent_artifacts.sources.model import (
    LocalSnapshotRequest,
    SnapshotLimits,
    SourceInstanceId,
    SourceValidationRequest,
    make_source_candidate,
)
from agent_artifacts.sources.validation import (
    validate_authoring_source_candidate,
    validate_source_candidate,
)
from tests.credential_fixtures import secret_field

_FIXTURE = Path(__file__).parent / "fixtures" / "protocol" / "native-source-v1"


def _unwrap(result):
    assert isinstance(result, Ok), result
    return result.value


def _entry(raw: str, content: bytes = b"x\n") -> SnapshotEntry:
    return SnapshotEntry(_unwrap(parse_relative_path(raw)), SnapshotEntryKind.FILE, content)


def _candidate(root: Path = _FIXTURE):
    return _unwrap(
        read_local_snapshot(
            LocalSnapshotRequest(
                SourceInstanceId("local-" + "a" * 32),
                SourceAlias("reference"),
                str(root.resolve()),
                SnapshotLimits(),
            )
        )
    )


class SourceValidationTest(unittest.TestCase):
    def test_reference_native_source_is_accepted_with_declared_identity(self) -> None:
        request = SourceValidationRequest(
            _candidate(),
            _unwrap(parse_semver("1.0.0")),
            (_unwrap(parse_capability("artifact-manifest-v1")),),
        )

        result = validate_source_candidate(request)

        self.assertIsInstance(result, Ok)
        assert isinstance(result, Ok)
        self.assertEqual(result.value.candidate, request.candidate)
        self.assertEqual(result.value.declared_source_id, SourceId("reference-native-source"))

    def test_incompatible_version_or_capability_never_returns_validated_candidate(self) -> None:
        candidate = _candidate()
        requests = (
            SourceValidationRequest(candidate, _unwrap(parse_semver("2.0.0")), ()),
            SourceValidationRequest(candidate, _unwrap(parse_semver("1.0.0")), ()),
        )

        for request in requests:
            with self.subTest(request=request):
                result = validate_source_candidate(request)
                self.assertIsInstance(result, Err)
                assert isinstance(result, Err)
                self.assertEqual(result.diagnostics[0].code.value, "source-incompatible")

    def test_corrupt_source_marker_is_rejected_without_mutating_acquired_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "aart-source.json"
            marker.write_bytes(
                b'{"schema_version":1,' + secret_field("token", "secret").encode("utf-8")
            )
            candidate = _candidate(Path(root))
            before = candidate.snapshot

            result = validate_source_candidate(
                SourceValidationRequest(candidate, _unwrap(parse_semver("1.0.0")), ())
            )

            self.assertIsInstance(result, Err)
            self.assertEqual(candidate.snapshot, before)
            assert isinstance(result, Err)
            self.assertNotIn("secret", repr(result.diagnostics))


if __name__ == "__main__":
    unittest.main()


class AuthoringSourceAdmissionRuleTest(unittest.TestCase):
    """B-094: the seam rule behind the E2E, stated over generated trees.

    `authoring_source_admission_e2e_test` proves the public command admits one real repository.
    This proves the rule that made it do so is a rule: for *any* tree carrying no
    `aart-source.json`, admission is exactly whether an explicit manifest basename is present
    anywhere in it (INV-201), and the alias is the identity a tree that declares none receives.
    """

    def _request(self, snapshot):
        candidate = _unwrap(
            make_source_candidate(
                SourceInstanceId("git-" + "b" * 32),
                SourceAlias("authors"),
                "c" * 40,
                snapshot,
            )
        )
        return SourceValidationRequest(
            candidate,
            _unwrap(parse_semver("1.0.0")),
            (_unwrap(parse_capability("artifact-manifest-v1")),),
        )

    def _configured(self):
        return ConfiguredSource(
            SourceAlias("authors"),
            SourceKind.SOURCE_GIT,
            "https://git.example/authors.git",
            "main",
            True,
        )

    @given(
        st.lists(
            st.tuples(
                st.lists(
                    st.sampled_from(("skills", "servers", "team", "a")),
                    min_size=0,
                    max_size=3,
                ).map(tuple),
                st.sampled_from(("aart.yaml", "aart.json", "README.md", "server.py", "SKILL.md")),
            ),
            min_size=1,
            max_size=6,
            unique=True,
        )
    )
    def test_admission_is_exactly_whether_an_explicit_manifest_is_declared(
        self,
        raw: list[tuple[tuple[str, ...], str]],
    ) -> None:
        by_directory: dict[tuple[str, ...], set[str]] = {}
        entries = []
        for parts, name in raw:
            directory = parts
            by_directory.setdefault(directory, set()).add(name)
            entries.append(_entry("/".join((*parts, name))))
        # Two manifest spellings in one directory is a tree-shape refusal of its own, and it is
        # discovery's to make, not this rule's; excluding it keeps the property about admission.
        both = any({"aart.yaml", "aart.json"} <= names for names in by_directory.values())
        snapshot = SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, tuple(entries))

        result = validate_authoring_source_candidate(self._configured(), self._request(snapshot))

        declared = any(name in {"aart.yaml", "aart.json"} for _, name in raw)
        if both:
            self.assertIsInstance(result, Err)
        elif declared:
            self.assertIsInstance(result, Ok, result)
            assert isinstance(result, Ok)
            self.assertEqual(result.value.declared_source_id, SourceId("authors"))
        else:
            self.assertIsInstance(result, Err)

    def test_a_tree_that_claims_the_native_marker_is_still_judged_as_a_native_source(self) -> None:
        """The two rules stay separate: claiming the marker is not a way to skip its loader."""

        snapshot = SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry("aart-source.json", b"{ not json\n"),
                _entry("skills/review/aart.yaml", b"schema: aart.dev/skill/v1\n"),
            ),
        )

        result = validate_authoring_source_candidate(self._configured(), self._request(snapshot))

        self.assertIsInstance(result, Err)
