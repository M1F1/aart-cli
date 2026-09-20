"""Publishing a reviewed registry commit is an action AART takes, and bounds (`QA-082`, `D-228`)."""

from __future__ import annotations

import unittest

from aart_cli.application.registry_publication import (
    PublicationOutcome,
    RegistryPublicationCommand,
    RegistryPublicationReceipt,
    prepare_registry_publication,
    publication_summary,
)
from aart_cli.domain.identifiers import ObjectDigest, SourceAlias
from aart_cli.domain.publication import PublicationBranch
from aart_cli.domain.result import Err, Ok

_REVISION = "b" * 40
_DIGEST = ObjectDigest("sha256", "c" * 64)


def _prepare(**overrides: object) -> object:
    arguments: dict[str, object] = {
        "registry": SourceAlias("company"),
        "remote": "origin",
        "default_branch": "main",
        "requested_branch": "registry-update",
        "revision": _REVISION,
        "review_digest": _DIGEST,
    }
    arguments.update(overrides)
    return prepare_registry_publication(**arguments)  # type: ignore[arg-type]


class PreparePublicationTest(unittest.TestCase):
    def test_a_reviewed_commit_prepares_one_push_to_the_configured_branch(self) -> None:
        prepared = _prepare()
        assert isinstance(prepared, Ok)
        command = prepared.value
        self.assertEqual(PublicationBranch("registry-update"), command.branch)
        self.assertEqual("origin", command.remote)
        self.assertEqual(_REVISION, command.revision)
        self.assertEqual(SourceAlias("company"), command.registry)

    def test_the_default_branch_is_refused_before_any_remote_is_touched(self) -> None:
        refused = _prepare(requested_branch="main")
        assert isinstance(refused, Err)
        self.assertEqual("registry-default-branch-publication", refused.diagnostics[0].code.value)

    def test_a_revision_that_is_not_a_git_commit_is_refused(self) -> None:
        self.assertIsInstance(_prepare(revision="HEAD"), Err)
        self.assertIsInstance(_prepare(revision=""), Err)

    def test_a_remote_name_git_would_not_carry_is_refused(self) -> None:
        for remote in ("", " ", "with space", "-dashfirst", "new\nline", "a/b"):
            with self.subTest(remote=remote):
                self.assertIsInstance(_prepare(remote=remote), Err)

    def test_the_command_carries_no_way_to_force_or_merge(self) -> None:
        prepared = _prepare()
        assert isinstance(prepared, Ok)
        fields = set(RegistryPublicationCommand.__dataclass_fields__)
        self.assertEqual(set(), fields & {"force", "merge", "fast_forward", "delete"})


class PublicationReceiptTest(unittest.TestCase):
    def _receipt(self, outcome: PublicationOutcome) -> RegistryPublicationReceipt:
        return RegistryPublicationReceipt(
            SourceAlias("company"),
            "origin",
            PublicationBranch("registry-update"),
            _REVISION,
            _DIGEST,
            outcome,
        )

    def test_a_receipt_says_where_the_bytes_went_and_what_moved(self) -> None:
        receipt = self._receipt(PublicationOutcome.CREATED)
        self.assertEqual(PublicationOutcome.CREATED, receipt.outcome)
        self.assertEqual(_REVISION, receipt.revision)

    def test_a_receipt_refuses_a_revision_that_is_not_a_commit(self) -> None:
        with self.assertRaises(ValueError):
            RegistryPublicationReceipt(
                SourceAlias("company"),
                "origin",
                PublicationBranch("registry-update"),
                "not-a-commit",
                _DIGEST,
                PublicationOutcome.UPDATED,
            )

    def test_the_summary_says_a_push_is_not_a_merge(self) -> None:
        summary = publication_summary(self._receipt(PublicationOutcome.UPDATED))
        joined = " ".join(summary)
        self.assertIn("registry-update", joined)
        self.assertIn("origin", joined)
        self.assertIn(_REVISION[:12], joined)
        self.assertTrue(any("merge" in line for line in summary))

    def test_the_summary_distinguishes_a_push_that_moved_nothing(self) -> None:
        moved = publication_summary(self._receipt(PublicationOutcome.UPDATED))
        unchanged = publication_summary(self._receipt(PublicationOutcome.ALREADY_CURRENT))
        self.assertNotEqual(moved, unchanged)


if __name__ == "__main__":
    unittest.main()
