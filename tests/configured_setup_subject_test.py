"""The configured receipt store can answer the setup engine's installed-subject port."""

from __future__ import annotations

import pathlib
import unittest
from dataclasses import replace
from unittest import mock

from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactCoordinate, ArtifactIdentity, SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.installation.model import InstallLocation
from aart_cli.io.configured_installation_action import InstallationHost
from aart_cli.io.configured_setup import (
    LocalConfiguredSetupAdapter,
    configured_setup_subject,
)
from aart_cli.io.receipt_store import LocalReceiptStore
from aart_cli.io.reference_store import read_references
from aart_cli.marketplace.model import TrustClass
from aart_cli.setup_engine import (
    ApprovedObjectIdentity,
    SetupExecutionStatus,
    SetupRequest,
    finalize_setup,
    prepare_setup,
)
from aart_cli.setup_runtime import production_runtime
from aart_cli.store.model import ReferenceKind, ReferenceReadRequest, object_store_paths
from tests.configured_install_command_e2e_test import _environment
from tests.configured_installation_draft_e2e_test import AuthoredSetup
from tests.configured_setup_gap_test import AUTHORED, COORDINATE, RECIPE
from tests.marketplace_fixtures import effective_configuration
from tests.receipt_store_test import sole_record


class ConfiguredSetupSubjectTest(unittest.TestCase):
    def test_a_real_receipt_resolves_to_approved_registry_and_object_evidence(self) -> None:
        with _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE)) as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(code, 0, payload)
            effective = effective_configuration((env.source,), default_registry="company")
            host = InstallationHost(
                env.paths.data_root,
                str(env.project),
                str(env.home),
                Scope.PROJECT,
                ("claude",),
            )
            request = SetupRequest(
                ArtifactCoordinate(
                    SourceAlias("company"), ArtifactIdentity("skill", "code-review")
                ),
                "claude",
                "project",
                platform="darwin",
            )

            resolved = configured_setup_subject(effective, host)(request)

            self.assertIsInstance(resolved, Ok, getattr(resolved, "diagnostics", ()))
            assert isinstance(resolved, Ok)
            subject = resolved.value
            self.assertIs(subject.trust, TrustClass.REGISTRY_REVIEWED)
            self.assertIsInstance(subject.declaration, ApprovedObjectIdentity)
            assert isinstance(subject.declaration, ApprovedObjectIdentity)
            self.assertEqual(
                subject.declaration.approved_digest, subject.record.artifact.object_digest
            )
            self.assertNotEqual(
                subject.trust_evidence_digest,
                subject.record.artifact.object_digest,
                "registry approval and package identity are separate evidence",
            )
            self.assertEqual(subject.record.artifact.payload_digest.algorithm, "sha256")
            self.assertEqual(subject.record.artifact.manifest_digest.algorithm, "sha256")
            self.assertEqual(subject.record.profile, "claude")
            self.assertEqual(subject.record.scope, "project")
            self.assertEqual(
                [effect.destination for effect in subject.record.effects],
                [".claude/skills/code-review-company-project"],
                "receipt destinations must be relative to the project root in engine evidence",
            )
            self.assertEqual(
                subject.record_path,
                str(
                    next((pathlib.Path(env.paths.data_root) / "state/installations").glob("*.json"))
                ),
            )
            self.assertEqual(subject.record_lock_path, subject.record_path + ".lock")

    def test_a_subject_request_for_a_profile_the_receipt_did_not_install_is_refused(self) -> None:
        with _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE)) as env:
            env.run("marketplace", "install", COORDINATE, "--profile", "claude", "--yes")
            effective = effective_configuration((env.source,), default_registry="company")
            host = InstallationHost(
                env.paths.data_root,
                str(env.project),
                str(env.home),
                Scope.PROJECT,
                ("claude",),
            )
            request = SetupRequest(
                ArtifactCoordinate(
                    SourceAlias("company"), ArtifactIdentity("skill", "code-review")
                ),
                "tabnine",
                "project",
                platform="darwin",
            )

            refused = configured_setup_subject(effective, host)(request)

            self.assertNotIsInstance(refused, Ok)

    def test_setup_persists_its_record_pointer_and_object_reference_on_the_receipt(self) -> None:
        with _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE)) as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(code, 0, payload)
            effective = effective_configuration((env.source,), default_registry="company")
            host = InstallationHost(
                env.paths.data_root,
                str(env.project),
                str(env.home),
                Scope.PROJECT,
                ("claude",),
            )
            request = SetupRequest(
                ArtifactCoordinate(
                    SourceAlias("company"), ArtifactIdentity("skill", "code-review")
                ),
                "claude",
                "project",
                platform="darwin",
            )
            subject = configured_setup_subject(effective, host)
            adapter = LocalConfiguredSetupAdapter(host, subject)
            planned = prepare_setup(
                request,
                subject,
                effective,
                InstallLocation(str(env.project), str(env.home), env.paths.data_root),
                object_store_paths(env.paths.data_root),
                adapter,
            )
            self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
            assert isinstance(planned, Ok)

            completed = finalize_setup(
                planned.value,
                planned.value.review_digest,
                subject,
                effective,
                adapter,
                replace(production_runtime(), platform="darwin"),
                consent=lambda _effect: True,
            )

            self.assertIsInstance(completed, Ok, getattr(completed, "diagnostics", ()))
            assert isinstance(completed, Ok)
            self.assertIs(completed.value.setup_status, SetupExecutionStatus.CONFIGURED)
            self.assertTrue(completed.value.state_written)
            self.assertTrue((env.project / ".code-review.toml").is_file())
            exact = ArtifactCoordinate(
                SourceAlias("company"), ArtifactIdentity("skill", "code-review"), "1.2.0"
            )
            stored = sole_record(LocalReceiptStore(host.state_root), exact)
            self.assertIsInstance(stored, Ok, getattr(stored, "diagnostics", ()))
            assert isinstance(stored, Ok)
            self.assertEqual(stored.value.receipt.setup_state_ref, planned.value.setup_state_ref)
            self.assertTrue(pathlib.Path(planned.value.setup_state_path).is_file())
            references = read_references(ReferenceReadRequest(object_store_paths(host.data_root)))
            self.assertIsInstance(references, Ok, getattr(references, "diagnostics", ()))
            assert isinstance(references, Ok)
            self.assertIn(
                (
                    ReferenceKind.SETUP,
                    planned.value.setup_reference_owner,
                    planned.value.object_digest,
                ),
                tuple((item.kind, item.owner, item.digest) for item in references.value.references),
            )

    def test_reference_failure_restores_receipt_and_setup_state_pointer(self) -> None:
        with _environment(authored=AUTHORED, setup=AuthoredSetup(RECIPE)) as env:
            code, payload = env.run(
                "marketplace", "install", COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(code, 0, payload)
            effective = effective_configuration((env.source,), default_registry="company")
            host = InstallationHost(
                env.paths.data_root,
                str(env.project),
                str(env.home),
                Scope.PROJECT,
                ("claude",),
            )
            request = SetupRequest(
                ArtifactCoordinate(
                    SourceAlias("company"), ArtifactIdentity("skill", "code-review")
                ),
                "claude",
                "project",
                platform="darwin",
            )
            subject = configured_setup_subject(effective, host)
            adapter = LocalConfiguredSetupAdapter(host, subject)
            planned = prepare_setup(
                request,
                subject,
                effective,
                InstallLocation(str(env.project), str(env.home), env.paths.data_root),
                object_store_paths(env.paths.data_root),
                adapter,
            )
            assert isinstance(planned, Ok)
            exact = ArtifactCoordinate(
                SourceAlias("company"), ArtifactIdentity("skill", "code-review"), "1.2.0"
            )
            before = sole_record(LocalReceiptStore(host.state_root), exact)
            assert isinstance(before, Ok)
            setup_path = pathlib.Path(planned.value.setup_state_path)
            setup_before = setup_path.read_bytes() if setup_path.exists() else None
            unavailable = Err(
                (
                    Diagnostic(
                        DiagnosticCode("reference-write-failed"),
                        Severity.ERROR,
                        "reference store unavailable",
                    ),
                )
            )

            with mock.patch(
                "aart_cli.io.configured_setup._replace_setup_reference",
                return_value=unavailable,
            ):
                completed = finalize_setup(
                    planned.value,
                    planned.value.review_digest,
                    subject,
                    effective,
                    adapter,
                    replace(production_runtime(), platform="darwin"),
                    consent=lambda _effect: True,
                )

            self.assertIsInstance(completed, Ok)
            assert isinstance(completed, Ok)
            self.assertIs(completed.value.setup_status, SetupExecutionStatus.FAILED)
            standing = sole_record(LocalReceiptStore(host.state_root), exact)
            assert isinstance(standing, Ok)
            self.assertEqual(
                standing.value.receipt.setup_state_ref,
                before.value.receipt.setup_state_ref,
            )
            self.assertEqual(
                setup_path.read_bytes() if setup_path.exists() else None,
                setup_before,
            )


if __name__ == "__main__":
    unittest.main()
