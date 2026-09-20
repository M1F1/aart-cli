from __future__ import annotations

import unittest

from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.configuration.schema import (
    configured_source_from_input,
    validate_configured_source,
)
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from tests.credential_fixtures import credential_url


class ConfiguredSourceFromInputTest(unittest.TestCase):
    def test_accepts_registry_direct_and_local_sources(self) -> None:
        registry = configured_source_from_input(
            "company-registry",
            SourceKind.REGISTRY_GIT,
            "https://github.example/company/agent-artifacts-registry.git",
        )
        direct = configured_source_from_input(
            "team-artifacts",
            SourceKind.SOURCE_GIT,
            "git@git.example:team/agent-artifacts.git",
            "release/1.0",
        )
        local = configured_source_from_input(
            "local-dev",
            SourceKind.SOURCE_LOCAL,
            "/work/agent-artifacts",
        )

        for result in (registry, direct, local):
            self.assertIsInstance(result, Ok)

        assert isinstance(registry, Ok)
        assert isinstance(direct, Ok)
        assert isinstance(local, Ok)
        self.assertEqual(registry.value.alias.value, "company-registry")
        self.assertEqual(registry.value.ref, "main")
        self.assertEqual(direct.value.ref, "release/1.0")
        self.assertIsNone(local.value.ref)
        self.assertTrue(all(result.value.enabled for result in (registry, direct, local)))

    def test_rejects_invalid_alias_credential_url_unsafe_ref_and_relative_local_path(self) -> None:
        invalid = (
            configured_source_from_input(
                "Bad_Alias", SourceKind.REGISTRY_GIT, "https://github.example/company/registry.git"
            ),
            configured_source_from_input(
                "secret",
                SourceKind.SOURCE_GIT,
                credential_url("git.example", "/team/artifacts.git", held="token"),
            ),
            configured_source_from_input(
                "unsafe-ref",
                SourceKind.SOURCE_GIT,
                "https://git.example/team/artifacts.git",
                "--upload-pack=evil",
            ),
            configured_source_from_input("relative", SourceKind.SOURCE_LOCAL, "artifacts"),
        )

        for result in invalid:
            self.assertIsInstance(result, Err)

    def test_validates_existing_source_without_losing_its_enabled_state(self) -> None:
        source = ConfiguredSource(
            SourceAlias("disabled"),
            SourceKind.SOURCE_GIT,
            "https://git.example/team/artifacts.git",
            "main",
            False,
        )

        validated = validate_configured_source(source)

        self.assertIsInstance(validated, Ok)
        assert isinstance(validated, Ok)
        self.assertEqual(validated.value, source)

        unsafe = ConfiguredSource(
            SourceAlias("secret"),
            SourceKind.SOURCE_GIT,
            credential_url("git.example", "/team/artifacts.git", held="token"),
            "main",
            True,
        )
        self.assertIsInstance(validate_configured_source(unsafe), Err)


if __name__ == "__main__":
    unittest.main()


class LocalRegistryCheckoutTest(unittest.TestCase):
    """A Registry read out of a repository already on this machine (CP-26.20, D-350).

    It is a Registry, so it is admitted, projected, resolved and installed from through exactly
    the machinery `registry-git` uses. What separates it is where the bytes come from and what is
    therefore promised about them: one named branch's committed content, read without touching the
    checkout, so a repository whose worktree is mid-edit and whose HEAD is some other branch still
    publishes only what was committed to the branch that was named.
    """

    def _local(self, location: str = "/work/registry", ref: str | None = "test/candidate"):
        return configured_source_from_input(
            "local-registry", SourceKind.REGISTRY_LOCAL, location, ref
        )

    def test_a_path_and_a_branch_make_one_configured_registry(self) -> None:
        parsed = self._local()

        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        assert isinstance(parsed, Ok)
        self.assertEqual(parsed.value.location, "/work/registry")
        self.assertEqual(parsed.value.ref, "test/candidate")
        self.assertTrue(parsed.value.is_registry)
        self.assertTrue(parsed.value.is_local_checkout)

    def test_the_branch_is_required_rather_than_defaulted_to_the_checked_out_one(self) -> None:
        """`registry-git` defaults its ref to `main`; this cannot.

        A remote origin has one obvious default and no other candidate. A checkout has a branch
        somebody happens to have open, and silently reading `main` when they meant the branch they
        are on -- or the other way round -- installs content nobody selected. It is named or it is
        refused.
        """

        refused = self._local(ref=None)

        self.assertIsInstance(refused, Err)
        assert isinstance(refused, Err)
        self.assertIn("branch", refused.diagnostics[0].message)

    def test_it_is_not_governed_by_the_remote_git_host_rules(self) -> None:
        """`is_git` means an origin a host allowlist can be applied to, and a path is not one."""

        parsed = self._local()

        assert isinstance(parsed, Ok)
        self.assertFalse(parsed.value.is_git)

    def test_a_relative_or_unnormalized_path_is_refused(self) -> None:
        for location in ("work/registry", "/work/../registry", "/work/registry/"):
            with self.subTest(location=location):
                refused = self._local(location=location)

                self.assertIsInstance(refused, Err, location)

    def test_an_unsafe_branch_name_is_refused(self) -> None:
        for ref in ("--upload-pack=x", "branch with space", "-", "refs/heads/../x"):
            with self.subTest(ref=ref):
                self.assertIsInstance(self._local(ref=ref), Err, ref)
