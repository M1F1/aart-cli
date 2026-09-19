from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aart_cli.curation import runtime as curation_runtime
from aart_cli.curation.model import (
    CurationAction,
    CurationRequest,
)
from aart_cli.curation.runtime import LocalCurationService
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.identifiers import ObjectDigest, SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.sources.model import SourceInstanceId, make_source_candidate
from tests.registry_maintenance_fixtures import (
    native_snapshot,
)


def _git_checkout(root: Path) -> None:
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)


def _failure(message: str = "injected failure") -> Err:
    return Err((Diagnostic(DiagnosticCode("test-failure"), Severity.ERROR, message),))


class CurationRuntimeTest(unittest.TestCase):
    def test_default_native_acquisition_binds_a_pinned_immutable_candidate(self) -> None:
        native_candidate = make_source_candidate(
            SourceInstanceId("git-" + "a" * 32),
            SourceAlias("curation-native"),
            "a" * 40,
            native_snapshot(),
        )
        assert isinstance(native_candidate, Ok)
        with mock.patch.object(
            curation_runtime,
            "_candidate",
            return_value=native_candidate,
        ):
            native = curation_runtime.default_native_acquirer(
                "https://github.com/example/reference-skills.git",
                "main",
            )
        assert isinstance(native, Ok), native
        self.assertEqual(native.value.resolved_commit, "a" * 40)

        with mock.patch.object(curation_runtime, "_candidate", return_value=_failure()):
            self.assertIsInstance(
                curation_runtime.default_native_acquirer(
                    "https://github.com/example/reference-skills.git",
                    "main",
                ),
                Err,
            )
        invalid_revision = make_source_candidate(
            SourceInstanceId("git-" + "b" * 32),
            SourceAlias("curation-native"),
            "not-a-commit",
            native_snapshot(),
        )
        assert isinstance(invalid_revision, Ok)
        with mock.patch.object(
            curation_runtime,
            "_candidate",
            return_value=invalid_revision,
        ):
            self.assertIsInstance(
                curation_runtime.default_native_acquirer(
                    "https://github.com/example/reference-skills.git",
                    "main",
                ),
                Err,
            )

    def test_local_git_candidate_is_acquired_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            _git_checkout(root)
            (root / "README.md").write_text("source", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=AART Test",
                    "-c",
                    "user.email=aart@example.invalid",
                    "-C",
                    str(root),
                    "commit",
                    "-qm",
                    "fixture",
                ],
                check=True,
            )
            acquired = curation_runtime._candidate(
                str(root),
                "HEAD",
                alias="curation-local",
                allow_local_transport=True,
            )
            assert isinstance(acquired, Ok), acquired
            self.assertRegex(acquired.value.resolved_revision, r"^[0-9a-f]{40}$")

    def test_mutation_is_rejected_before_preview_without_a_local_git_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "plain"
            root.mkdir()
            service = LocalCurationService(str(root))
            prepared = service.prepare(
                CurationRequest(
                    CurationAction.INIT,
                    str(root),
                    source_id="test-registry",
                    display_name="Test Registry",
                )
            )
            self.assertIsInstance(prepared, Err)
            self.assertEqual(tuple(root.iterdir()), ())
            missing = Path(temporary) / "missing"
            read_only = LocalCurationService(str(missing)).prepare(
                CurationRequest(CurationAction.VALIDATE, str(missing))
            )
            self.assertIsInstance(read_only, Err)

    def test_invalid_or_incomplete_requests_fail_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "registry"
            other = Path(temporary) / "other"
            _git_checkout(root)
            other.mkdir()
            service = LocalCurationService(
                str(root),
                native_acquirer=lambda _url, _ref: _failure(),
            )
            requests = (
                CurationRequest(CurationAction.INIT, str(root)),
                CurationRequest(
                    CurationAction.INIT,
                    str(root),
                    source_id="registry",
                    display_name="Registry",
                    minimum_version="not-semver",
                ),
                CurationRequest(
                    CurationAction.INIT,
                    str(root),
                    source_id="registry",
                    display_name="Registry",
                    maximum_version="not-semver",
                ),
                CurationRequest(
                    CurationAction.INIT,
                    str(root),
                    source_id="registry",
                    display_name="Registry",
                    minimum_version="2.0.0",
                    maximum_version="1.0.0",
                ),
                CurationRequest(CurationAction.VENDOR, str(root)),
                CurationRequest(
                    CurationAction.VENDOR,
                    str(root),
                    kind="skill",
                    name="demo",
                    url="http://insecure.example/repo.git",
                    path="prompts/demo",
                ),
                CurationRequest(CurationAction.VALIDATE, str(other)),
            )
            for request in requests:
                with self.subTest(action=request.action, request=request):
                    self.assertIsInstance(service.prepare(request), Err)
            self.assertEqual(tuple(root.iterdir()), (root / ".git",))
            with self.assertRaises(ValueError):
                LocalCurationService("relative")

    def test_init_is_previewed_then_exactly_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "registry"
            _git_checkout(root)
            service = LocalCurationService(str(root))
            initialized = service.prepare(
                CurationRequest(
                    CurationAction.INIT,
                    str(root),
                    source_id="test-registry",
                    display_name="Test Registry",
                )
            )
            assert isinstance(initialized, Ok), initialized
            # `QA-013`/`D-180`: nothing inert is written, so nothing warns that it is. An
            # unrequested optional feature is not a finding about the registry that was created.
            self.assertNotIn(
                "usage-reporting",
                " ".join(initialized.value.review.warnings),
            )
            self.assertFalse(
                any("inert" in warning for warning in initialized.value.review.warnings),
                initialized.value.review.warnings,
            )
            self.assertIn(
                f"aart-cli registry validate --source {root}",
                initialized.value.review.follow_up_commands,
            )
            self.assertFalse(
                any(
                    "validate" in command and "--strict" in command
                    for command in initialized.value.review.follow_up_commands
                )
            )
            self.assertTrue(
                any(
                    "registry build" in command
                    for command in initialized.value.review.follow_up_commands
                )
            )
            self.assertFalse((root / "aart-registry.json").exists())
            wrong = service.finalize(
                initialized.value,
                ObjectDigest("sha256", "f" * 64),
            )
            self.assertIsInstance(wrong, Err)
            applied = service.finalize(
                initialized.value,
                initialized.value.review.review_digest,
            )
            assert isinstance(applied, Ok), applied
            self.assertTrue((root / "aart-registry.json").is_file())
            duplicate_init = service.prepare(
                CurationRequest(
                    CurationAction.INIT,
                    str(root),
                    source_id="test-registry",
                    display_name="Test Registry",
                )
            )
            self.assertIsInstance(duplicate_init, Err)

    def test_read_only_validate_audit_and_diff_never_require_a_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "snapshot"
            _git_checkout(root)
            service = LocalCurationService(str(root))
            initialized = service.prepare(
                CurationRequest(
                    CurationAction.INIT,
                    str(root),
                    source_id="test-registry",
                    display_name="Test Registry",
                )
            )
            assert isinstance(initialized, Ok)
            assert isinstance(
                service.finalize(initialized.value, initialized.value.review.review_digest), Ok
            )
            shutil.rmtree(root / ".git")
            for action in (CurationAction.VALIDATE, CurationAction.AUDIT, CurationAction.DIFF):
                with self.subTest(action=action):
                    prepared = service.prepare(CurationRequest(action, str(root)))
                    assert isinstance(prepared, Ok), prepared
                    self.assertFalse(prepared.value.review.mutating)
                    before = tuple(sorted(path.relative_to(root) for path in root.rglob("*")))
                    outcome = service.finalize(
                        prepared.value,
                        prepared.value.review.review_digest,
                    )
                    assert isinstance(outcome, Ok), outcome
                    after = tuple(sorted(path.relative_to(root) for path in root.rglob("*")))
                    self.assertEqual(before, after)

    def test_read_only_review_is_stale_if_the_workspace_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "registry"
            _git_checkout(root)
            service = LocalCurationService(str(root))
            initialized = service.prepare(
                CurationRequest(
                    CurationAction.INIT,
                    str(root),
                    source_id="test-registry",
                    display_name="Test Registry",
                )
            )
            assert isinstance(initialized, Ok)
            assert isinstance(
                service.finalize(initialized.value, initialized.value.review.review_digest), Ok
            )
            reviewed = service.prepare(CurationRequest(CurationAction.VALIDATE, str(root)))
            assert isinstance(reviewed, Ok), reviewed
            marker = root / "aart-registry.json"
            marker.write_bytes(marker.read_bytes() + b" ")
            stale = service.finalize(reviewed.value, reviewed.value.review.review_digest)
            self.assertIsInstance(stale, Err)

            second = service.prepare(CurationRequest(CurationAction.VALIDATE, str(root)))
            assert isinstance(second, Ok), second
            shutil.rmtree(root)
            missing = service.finalize(second.value, second.value.review.review_digest)
            self.assertIsInstance(missing, Err)


if __name__ == "__main__":
    unittest.main()
