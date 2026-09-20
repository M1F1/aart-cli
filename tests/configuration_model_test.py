from __future__ import annotations

import unittest

from aart_cli.configuration.model import (
    CompanyReviewedSource,
    ConfiguredSource,
    OrganizationPolicy,
    SourceKind,
    SyncMode,
    SyncSettings,
    UserConfiguration,
    git_location_parts,
)
from aart_cli.domain.identifiers import SourceAlias, SourceId
from tests.credential_fixtures import credential_url


class ConfigurationModelTest(unittest.TestCase):
    def test_domain_values_reject_invalid_direct_construction(self) -> None:
        source = ConfiguredSource(
            SourceAlias("valid"), SourceKind.SOURCE_LOCAL, "/valid", None, True
        )
        first_git = ConfiguredSource(
            SourceAlias("first-git"),
            SourceKind.SOURCE_GIT,
            "https://example.test/team/artifacts.git",
            "main",
            True,
        )
        # SRC02 keys the source store by (origin, ref), so a *different* ref of one origin is now
        # legitimate.  The same origin at the same ref still resolves to one mirror and one
        # pointer, so it stays rejected — including across equivalent transport spellings.
        same_origin_same_ref = ConfiguredSource(
            SourceAlias("second-git"),
            SourceKind.SOURCE_GIT,
            "git@EXAMPLE.test:team/artifacts",
            "main",
            True,
        )
        invalid_constructors = (
            lambda: ConfiguredSource(SourceAlias(""), SourceKind.SOURCE_LOCAL, "/a", None, True),
            lambda: ConfiguredSource(SourceAlias("a"), "local", "/a", None, True),  # type: ignore[arg-type]
            lambda: ConfiguredSource(SourceAlias("a"), SourceKind.SOURCE_LOCAL, "/a", "main", True),
            lambda: ConfiguredSource(
                SourceAlias("a"), SourceKind.SOURCE_GIT, "https://example.test/a", None, True
            ),
            lambda: SyncSettings("auto", 1),  # type: ignore[arg-type]
            lambda: SyncSettings(SyncMode.AUTO, -1),
            lambda: SyncSettings(SyncMode.AUTO, True),
            lambda: UserConfiguration(2, (source,), None, SyncSettings()),
            lambda: UserConfiguration(1, (source, source), None, SyncSettings()),
            lambda: UserConfiguration(1, (first_git, same_origin_same_ref), None, SyncSettings()),
            lambda: OrganizationPolicy(2),
            lambda: OrganizationPolicy(1, allow_direct_sources="yes"),  # type: ignore[arg-type]
            lambda: OrganizationPolicy(1, minimum_trust_for_user_scope="trusted-by-name"),
            lambda: OrganizationPolicy(1, allowed_setup_capabilities=("keychain",)),  # type: ignore[arg-type]
            lambda: OrganizationPolicy(
                1,
                recommended_sources=(SourceAlias("same"),),
                required_sources=(SourceAlias("same"),),
            ),
            lambda: OrganizationPolicy(1, company_reviewed_sources=("source",)),  # type: ignore[arg-type]
            lambda: OrganizationPolicy(
                1,
                company_reviewed_sources=(
                    CompanyReviewedSource(SourceId("source"), "example.test", "team/repo"),
                    CompanyReviewedSource(SourceId("source"), "EXAMPLE.TEST", "team/repo.git"),
                ),
            ),
        )

        for constructor in invalid_constructors:
            with self.subTest(constructor=constructor), self.assertRaises(ValueError):
                constructor()

        # The positive half of the same invariant: one origin at two refs is now representable.
        accepted = UserConfiguration(
            1,
            (
                first_git,
                ConfiguredSource(
                    SourceAlias("second-git"),
                    SourceKind.SOURCE_GIT,
                    "https://example.test/team/artifacts.git",
                    "release/1.0",
                    True,
                ),
            ),
            None,
            SyncSettings(),
        )
        self.assertEqual(len(accepted.sources), 2)

    def test_git_locations_are_normalized_and_credentials_are_rejected(self) -> None:
        accepted = {
            "git@GitHub.Example:agents/repo.git": ("github.example", "agents/repo"),
            "https://GitHub.Example/agents/repo.git": ("github.example", "agents/repo"),
            "ssh://git@GitHub.Example/agents/repo.git": ("github.example", "agents/repo"),
        }
        for location, expected in accepted.items():
            with self.subTest(location=location):
                self.assertEqual(git_location_parts(location), expected)

        rejected = (
            "",
            "file:///work/repo",
            "https://example.test/",
            "https://example.test/a/../b",
            "https://example.test/a//b",
            "https://example.test/a repo",
            "https://example.test/a%20repo",
            "https://example.test/a\\repo",
            "https://example.test/repo?ref=main",
            "https://example.test/repo#main",
            "https://user@example.test/repo",
            credential_url("example.test", "/repo"),
            "ssh://admin@example.test/repo",
            "https://[invalid/repo",
            "git@example.test:repo/",
        )
        for location in rejected:
            with self.subTest(location=location):
                self.assertIsNone(git_location_parts(location))


if __name__ == "__main__":
    unittest.main()
