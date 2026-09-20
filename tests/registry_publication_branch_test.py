"""Publication is a push to a branch, and never to the one consumers read (`QA-082`, `D-228`)."""

from __future__ import annotations

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.domain.publication import (
    DEFAULT_PUBLICATION_BRANCH,
    PUBLICATION_BRANCH_NAMESPACE,
    PublicationBranch,
    RegistryCommitOrigin,
    resolve_publication_branch,
    suggested_publication_branch,
)
from aart_cli.domain.result import Err, Ok


class PublicationBranchNameTest(unittest.TestCase):
    def test_an_ordinary_branch_name_is_accepted(self) -> None:
        resolved = resolve_publication_branch(
            requested="registry/2026-09-10", default_branch="main"
        )
        self.assertIsInstance(resolved, Ok)
        assert isinstance(resolved, Ok)
        self.assertEqual(PublicationBranch("registry/2026-09-10"), resolved.value)

    def test_a_ref_qualified_request_keeps_its_short_name(self) -> None:
        resolved = resolve_publication_branch(
            requested="refs/heads/registry-update", default_branch="main"
        )
        assert isinstance(resolved, Ok)
        self.assertEqual("registry-update", resolved.value.value)

    def test_a_name_git_itself_would_refuse_is_refused_here(self) -> None:
        for requested in (
            "",
            " ",
            "with space",
            "a..b",
            "/leading",
            "trailing/",
            "tilde~1",
            "caret^",
            "colon:",
            "question?",
            "star*",
            "bracket[",
            "back\\slash",
            "new\nline",
            "dot.lock.lock",
            ".hidden",
            "double//slash",
            "@{seq}",
            "@",
        ):
            with self.subTest(requested=requested):
                self.assertIsInstance(
                    resolve_publication_branch(requested=requested, default_branch="main"), Err
                )


class DefaultBranchIsRefusedTest(unittest.TestCase):
    def test_publishing_to_the_default_branch_is_refused_by_name(self) -> None:
        refused = resolve_publication_branch(requested="main", default_branch="main")
        assert isinstance(refused, Err)
        self.assertEqual(
            ("registry-default-branch-publication",),
            tuple(item.code.value for item in refused.diagnostics),
        )
        self.assertIn("main", refused.diagnostics[0].message)

    def test_the_refusal_names_a_branch_to_use_instead(self) -> None:
        refused = resolve_publication_branch(requested="trunk", default_branch="trunk")
        assert isinstance(refused, Err)
        diagnostic = refused.diagnostics[0]
        self.assertTrue(diagnostic.remediation)
        self.assertTrue(diagnostic.interactive)

    def test_a_ref_qualified_default_branch_cannot_sneak_past(self) -> None:
        self.assertIsInstance(
            resolve_publication_branch(requested="refs/heads/main", default_branch="main"), Err
        )

    def test_head_is_refused_because_it_resolves_to_the_default_branch(self) -> None:
        self.assertIsInstance(
            resolve_publication_branch(requested="HEAD", default_branch="main"), Err
        )

    def test_a_case_variant_of_the_default_branch_is_refused(self) -> None:
        self.assertIsInstance(
            resolve_publication_branch(requested="Main", default_branch="main"), Err
        )

    def test_the_default_branch_must_itself_be_a_usable_name(self) -> None:
        self.assertIsInstance(
            resolve_publication_branch(requested="release", default_branch=""), Err
        )


_NAMES = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=24
)


class PublicationBranchPropertyTest(unittest.TestCase):
    @settings(max_examples=200, deadline=None)
    @given(default=_NAMES, requested=_NAMES)
    def test_an_accepted_branch_never_equals_the_default_branch(
        self, default: str, requested: str
    ) -> None:
        resolved = resolve_publication_branch(requested=requested, default_branch=default)
        if isinstance(resolved, Ok):
            self.assertNotEqual(resolved.value.value.casefold(), default.casefold())

    @settings(max_examples=200, deadline=None)
    @given(name=_NAMES)
    def test_a_branch_is_never_accepted_as_a_publication_target_for_itself(self, name: str) -> None:
        self.assertIsInstance(resolve_publication_branch(requested=name, default_branch=name), Err)


class PublicationBranchSuggestionTest(unittest.TestCase):
    def test_each_registry_commit_origin_has_a_readable_branch(self) -> None:
        self.assertEqual(
            "aart-cli/init-registry",
            suggested_publication_branch(RegistryCommitOrigin.INIT_REGISTRY).value,
        )
        self.assertEqual(
            "aart-cli/rebuild-registry",
            suggested_publication_branch(RegistryCommitOrigin.REBUILD_REGISTRY).value,
        )
        self.assertEqual(
            "aart-cli/promote-github-mcp-1.0.0",
            suggested_publication_branch(
                RegistryCommitOrigin.PROMOTE, subject="github-mcp-1.0.0"
            ).value,
        )
        self.assertEqual(
            "aart-cli/bulk-promote",
            suggested_publication_branch(RegistryCommitOrigin.BULK_PROMOTE).value,
        )

    def test_absent_origin_or_missing_or_unusable_subject_uses_the_default(self) -> None:
        self.assertEqual(DEFAULT_PUBLICATION_BRANCH, suggested_publication_branch(None).value)
        self.assertEqual(
            DEFAULT_PUBLICATION_BRANCH,
            suggested_publication_branch(RegistryCommitOrigin.PROMOTE).value,
        )
        self.assertEqual(
            DEFAULT_PUBLICATION_BRANCH,
            suggested_publication_branch(RegistryCommitOrigin.PROMOTE, subject="bad subject").value,
        )

    @settings(max_examples=200, deadline=None)
    @given(subject=st.text(max_size=80))
    def test_every_suggestion_is_usable_and_stays_in_the_product_namespace(
        self, subject: str
    ) -> None:
        for origin in RegistryCommitOrigin:
            suggested = suggested_publication_branch(origin, subject=subject)
            self.assertTrue(suggested.value.startswith(PUBLICATION_BRANCH_NAMESPACE + "/"))
            self.assertIsInstance(
                resolve_publication_branch(requested=suggested.value, default_branch="main"),
                Ok,
            )


if __name__ == "__main__":
    unittest.main()
