"""CP-14 step 4: Candidate validation is a pipeline of named checks, not a flat findings list.

164.6 names the checks and makes three separations load-bearing: warnings and errors are distinct,
policy decides whether a warning blocks promotion, and policy-required manual approval is its own
Candidate state rather than a warning a renderer treats specially. These tests pin all three, and
pin each check to something the compiled artifact actually says rather than to a decorative tick.
"""

from __future__ import annotations

import dataclasses
import json
import unittest

from agent_artifacts.application.candidate_validation import (
    VALIDATION_PIPELINE,
    CandidateValidation,
    ValidationCheck,
    ValidationOutcome,
    validate_candidate,
    validated_candidate,
)
from agent_artifacts.application.maintainer import CandidateBundle, reconcile_source_scan
from agent_artifacts.domain.candidates import CandidateState, FindingSeverity
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path

_ENVIRONMENT_SECRET = {
    "id": "github-token",
    "kind": "secret",
    "inject": {"type": "environment", "variable": "GITHUB_TOKEN"},
    "help": {
        "label": "GitHub token",
        "format_hint": "provider-issued token",
        "obtain_from": {"label": "GitHub Settings", "url": "https://github.example/settings"},
    },
}
_ARGV_SECRET = {
    "id": "github-token",
    "kind": "secret",
    "inject": {"type": "cli-argument", "argument": "--github-token"},
    "help": {
        "label": "GitHub token",
        "format_hint": "provider-issued token",
        "obtain_from": {"label": "GitHub Settings", "url": "https://github.example/settings"},
    },
}
_UNGUIDED_SECRET = {
    "id": "github-token",
    "kind": "secret",
    "inject": {"type": "environment", "variable": "GITHUB_TOKEN"},
}


def _entry(path: str, content: str, *, executable: bool = False) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    assert isinstance(parsed, Ok)
    return SnapshotEntry(
        parsed.value, SnapshotEntryKind.FILE, content.encode(), executable=executable
    )


def _manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "github-mcp", "kind": "mcp", "version": "1.0.0"},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
    }
    manifest.update(overrides)
    return manifest


def _bundle(
    *,
    executable: bool = False,
    extra_files: tuple[tuple[str, str], ...] = (),
    **overrides: object,
) -> CandidateBundle:
    compiled = compile_author_snapshot(
        SourceSnapshot(
            SnapshotOrigin.IMMUTABLE_GIT,
            (
                _entry("github/aart.json", json.dumps(_manifest(**overrides), sort_keys=True)),
                _entry("github/server.py", "print('x')\n", executable=executable),
                *(_entry(path, content) for path, content in extra_files),
            ),
        ),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
    )
    assert isinstance(compiled, Ok), compiled
    scanned = reconcile_source_scan(
        SourceAlias("authors"),
        "a" * 40,
        compiled.value,
        previous=(),
        approved=(),
        target_registry=SourceAlias("company"),
    )
    assert isinstance(scanned, Ok), scanned
    return scanned.value.active[0]


def _tampered(bundle: CandidateBundle, entries: tuple[SnapshotEntry, ...]) -> CandidateBundle:
    """The same Candidate carrying a canonical tree nothing compiled — a corrupted store."""

    return CandidateBundle(
        bundle.candidate, dataclasses.replace(bundle.artifact, canonical_entries=entries)
    )


def _outcomes(validation: CandidateValidation) -> dict[ValidationCheck, ValidationOutcome]:
    return {item.check: item.outcome for item in validation.results}


class ValidationPipelineShapeTest(unittest.TestCase):
    def test_the_pipeline_is_the_named_check_list_the_specification_gives(self) -> None:
        self.assertEqual(
            VALIDATION_PIPELINE,
            (
                ValidationCheck.MANIFEST_SCHEMA,
                ValidationCheck.PAYLOAD_BOUNDARIES,
                ValidationCheck.SPECIAL_FILES,
                ValidationCheck.RUNTIME_DESCRIPTOR,
                ValidationCheck.DEPENDENCY_DESCRIPTOR,
                ValidationCheck.INPUT_DEFINITIONS,
                ValidationCheck.SECRET_METADATA,
                ValidationCheck.POLICY,
                ValidationCheck.SECURITY,
                ValidationCheck.LIVE_ACCEPTANCE,
            ),
        )

    def test_every_check_reports_exactly_once_in_pipeline_order(self) -> None:
        validation = validate_candidate(_bundle(), policy=EffectivePolicy())

        self.assertEqual(tuple(item.check for item in validation.results), VALIDATION_PIPELINE)
        self.assertEqual(validation.candidate_id, _bundle().candidate.id)

    def test_a_validation_missing_or_repeating_a_check_is_refused(self) -> None:
        validation = validate_candidate(_bundle(), policy=EffectivePolicy())

        with self.assertRaises(ValueError):
            dataclasses.replace(validation, results=validation.results[:-1])
        with self.assertRaises(ValueError):
            dataclasses.replace(
                validation, results=(*validation.results[:-1], validation.results[0])
            )


class ValidationCheckContentTest(unittest.TestCase):
    def test_a_clean_candidate_passes_the_automatic_checks_and_leaves_acceptance_unrun(
        self,
    ) -> None:
        validation = validate_candidate(
            _bundle(inputs=[_ENVIRONMENT_SECRET]), policy=EffectivePolicy()
        )

        outcomes = _outcomes(validation)
        self.assertEqual(outcomes[ValidationCheck.MANIFEST_SCHEMA], ValidationOutcome.PASSED)
        self.assertEqual(outcomes[ValidationCheck.PAYLOAD_BOUNDARIES], ValidationOutcome.PASSED)
        self.assertEqual(outcomes[ValidationCheck.SPECIAL_FILES], ValidationOutcome.PASSED)
        self.assertEqual(outcomes[ValidationCheck.RUNTIME_DESCRIPTOR], ValidationOutcome.PASSED)
        self.assertEqual(outcomes[ValidationCheck.SECRET_METADATA], ValidationOutcome.PASSED)
        self.assertEqual(outcomes[ValidationCheck.POLICY], ValidationOutcome.PASSED)
        # Live acceptance is CP-17's, and "not run" is not "passed".
        self.assertEqual(outcomes[ValidationCheck.LIVE_ACCEPTANCE], ValidationOutcome.NOT_RUN)

    def test_a_secret_delivered_through_argv_is_an_error_not_a_warning(self) -> None:
        validation = validate_candidate(_bundle(inputs=[_ARGV_SECRET]), policy=EffectivePolicy())

        result = validation.result(ValidationCheck.SECRET_METADATA)
        self.assertEqual(result.outcome, ValidationOutcome.ERROR)
        detail = result.details[0]
        self.assertIn("github-token", detail.message)
        self.assertEqual(detail.declared, "cli-argument")
        self.assertIsNotNone(detail.expected)
        self.assertTrue(all(item.severity is FindingSeverity.ERROR for item in result.findings))

    def test_a_secret_without_acquisition_guidance_warns_without_blocking(self) -> None:
        validation = validate_candidate(
            _bundle(inputs=[_UNGUIDED_SECRET]), policy=EffectivePolicy()
        )

        result = validation.result(ValidationCheck.SECRET_METADATA)
        self.assertEqual(result.outcome, ValidationOutcome.WARNING)
        self.assertTrue(all(item.severity is FindingSeverity.WARNING for item in result.findings))

    def test_executable_payload_files_are_named_by_the_security_check(self) -> None:
        validation = validate_candidate(_bundle(executable=True), policy=EffectivePolicy())

        result = validation.result(ValidationCheck.SECURITY)
        self.assertEqual(result.outcome, ValidationOutcome.WARNING)
        self.assertEqual([item.path for item in result.details], ["payload/server.py"])

    def test_a_declared_dependency_descriptor_must_be_in_the_payload_it_names(self) -> None:
        declared = _bundle(
            payload={"include": ["server.py", "requirements.txt"]},
            python={"dependencies": {"type": "requirements", "path": "requirements.txt"}},
            extra_files=(("github/requirements.txt", "mcp==1.14.0\n"),),
        )
        stripped = _tampered(
            declared,
            tuple(
                item
                for item in declared.artifact.canonical_entries
                if str(item.path) != "payload/requirements.txt"
            ),
        )

        self.assertEqual(
            validate_candidate(declared, policy=EffectivePolicy())
            .result(ValidationCheck.DEPENDENCY_DESCRIPTOR)
            .outcome,
            ValidationOutcome.PASSED,
        )
        missing = validate_candidate(stripped, policy=EffectivePolicy()).result(
            ValidationCheck.DEPENDENCY_DESCRIPTOR
        )
        self.assertEqual(missing.outcome, ValidationOutcome.ERROR)
        self.assertEqual(missing.details[0].declared, "payload/requirements.txt")

    def test_an_artifact_that_declares_no_dependencies_has_nothing_to_verify(self) -> None:
        result = validate_candidate(_bundle(), policy=EffectivePolicy()).result(
            ValidationCheck.DEPENDENCY_DESCRIPTOR
        )

        self.assertEqual(result.outcome, ValidationOutcome.PASSED)

    def test_policy_refuses_a_runtime_or_transport_it_does_not_allow(self) -> None:
        by_runtime = validate_candidate(
            _bundle(), policy=EffectivePolicy(allowed_runtimes=frozenset({"node"}))
        ).result(ValidationCheck.POLICY)
        by_transport = validate_candidate(
            _bundle(), policy=EffectivePolicy(allowed_transports=frozenset({"http"}))
        ).result(ValidationCheck.POLICY)
        by_binding = validate_candidate(
            _bundle(inputs=[_ENVIRONMENT_SECRET]),
            policy=EffectivePolicy(allowed_secret_bindings=frozenset({"file"})),
        ).result(ValidationCheck.POLICY)

        self.assertEqual(by_runtime.outcome, ValidationOutcome.ERROR)
        self.assertEqual(by_runtime.details[0].declared, "python")
        self.assertEqual(by_runtime.details[0].expected, "node")
        self.assertEqual(by_transport.outcome, ValidationOutcome.ERROR)
        self.assertEqual(by_binding.outcome, ValidationOutcome.ERROR)

    def test_a_tampered_canonical_tree_fails_the_reverification_checks(self) -> None:
        clean = _bundle()
        entries = clean.artifact.canonical_entries
        parsed = parse_relative_path("payload/link")
        assert isinstance(parsed, Ok)
        symlinked = _tampered(
            clean, (*entries, SnapshotEntry(parsed.value, SnapshotEntryKind.SYMLINK, b"../.."))
        )
        stray = _tampered(clean, (*entries, _entry("notes.txt", "hello\n")))
        gutted = _tampered(
            clean, tuple(item for item in entries if str(item.path) != "artifact.json")
        )

        special = validate_candidate(symlinked, policy=EffectivePolicy())
        outside = validate_candidate(stray, policy=EffectivePolicy())
        unreadable = validate_candidate(gutted, policy=EffectivePolicy())

        self.assertEqual(
            special.result(ValidationCheck.SPECIAL_FILES).outcome, ValidationOutcome.ERROR
        )
        self.assertEqual(
            special.result(ValidationCheck.SPECIAL_FILES).details[0].path, "payload/link"
        )
        self.assertEqual(
            outside.result(ValidationCheck.PAYLOAD_BOUNDARIES).outcome, ValidationOutcome.ERROR
        )
        self.assertEqual(
            outside.result(ValidationCheck.PAYLOAD_BOUNDARIES).details[0].path, "notes.txt"
        )
        self.assertEqual(
            unreadable.result(ValidationCheck.MANIFEST_SCHEMA).outcome, ValidationOutcome.ERROR
        )

    def test_no_check_detail_repeats_a_declared_config_value(self) -> None:
        configured = _bundle(
            inputs=[
                {
                    "id": "user-id",
                    "kind": "config",
                    "inject": {"type": "cli-argument", "argument": "--user-id"},
                    "help": {"label": "User ID", "example": "pl847362"},
                    "default": "ghp-not-a-real-token-value",
                }
            ]
        )

        validation = validate_candidate(configured, policy=EffectivePolicy())

        rendered = "\n".join(
            f"{item.path} {item.declared} {item.expected} {item.message}"
            for result in validation.results
            for item in result.details
        )
        self.assertNotIn("ghp-not-a-real-token-value", rendered)


class ValidationToCandidateStateTest(unittest.TestCase):
    def test_an_error_makes_the_candidate_invalid_and_a_warning_does_not(self) -> None:
        failed = validated_candidate(_bundle(inputs=[_ARGV_SECRET]), policy=EffectivePolicy())
        warned = validated_candidate(_bundle(inputs=[_UNGUIDED_SECRET]), policy=EffectivePolicy())

        self.assertIs(failed.candidate.state, CandidateState.INVALID)
        self.assertIs(warned.candidate.state, CandidateState.WARNING)
        self.assertTrue(warned.candidate.findings)

    def test_a_required_check_that_did_not_pass_is_approval_required(self) -> None:
        """Policy asked for evidence AART cannot produce on its own, so a person must decide."""

        approval = validated_candidate(
            _bundle(inputs=[_ENVIRONMENT_SECRET]),
            policy=EffectivePolicy(required_checks=frozenset({"live-acceptance"})),
        )

        self.assertIs(approval.candidate.state, CandidateState.APPROVAL_REQUIRED)

    def test_policy_decides_whether_a_warning_blocks_promotion(self) -> None:
        permissive = validated_candidate(
            _bundle(inputs=[_UNGUIDED_SECRET]), policy=EffectivePolicy()
        )
        strict = validated_candidate(
            _bundle(inputs=[_UNGUIDED_SECRET]),
            policy=EffectivePolicy(required_checks=frozenset({"secret-metadata"})),
        )

        self.assertIs(permissive.candidate.state, CandidateState.WARNING)
        self.assertIs(strict.candidate.state, CandidateState.APPROVAL_REQUIRED)

    def test_an_error_outranks_a_required_check_that_did_not_pass(self) -> None:
        both = validated_candidate(
            _bundle(inputs=[_ARGV_SECRET]),
            policy=EffectivePolicy(required_checks=frozenset({"live-acceptance"})),
        )

        self.assertIs(both.candidate.state, CandidateState.INVALID)

    def test_a_clean_candidate_under_an_undemanding_policy_is_ready(self) -> None:
        ready = validated_candidate(_bundle(inputs=[_ENVIRONMENT_SECRET]), policy=EffectivePolicy())

        self.assertIs(ready.candidate.state, CandidateState.READY)
        self.assertEqual(ready.artifact, _bundle(inputs=[_ENVIRONMENT_SECRET]).artifact)


if __name__ == "__main__":
    unittest.main()
