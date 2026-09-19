"""One installation owns its credentials, and the address proves it (§169.4-6, D-333/D-349).

What is here today is the thing this replaces: `io/consumer_actions.py` addresses a Keychain item
as `aart.<12 hex of the user home>` with the declared input id as the account. That names the
machine and the input and nothing else, so one artifact installed into two harnesses, two scopes or
from two Registry aliases reaches for the *same* item -- which is the sharing D-333 removed, in the
one place where sharing means a credential.

The owner is Registry alias, artifact kind and name, scope, the concrete root and the harness with
its profile. The version is deliberately not part of it, so a compatible update keeps the inputs
that owner already entered instead of asking again.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    SourceAlias,
)
from aart_cli.domain.installation_owner import (
    CREDENTIAL_SERVICE_PREFIX,
    MAX_CREDENTIAL_SERVICE_LENGTH,
    InstallationOwner,
    credential_address,
    installation_owner,
)

TOKEN = InputId("api-token")


def _owner(**changes: object) -> InstallationOwner:
    fields: dict[str, object] = {
        "source": SourceAlias("company"),
        "artifact": ArtifactIdentity("mcp", "github"),
        "scope": Scope.PROJECT,
        "root": "/work/project",
        "harness": "claude",
        "profile": "",
    }
    fields.update(changes)
    return InstallationOwner(**fields)  # type: ignore[arg-type]


class InstallationOwnerTest(unittest.TestCase):
    def test_the_version_is_not_part_of_the_owner(self) -> None:
        """A compatible update reconciles one installation, so its inputs must still be its own."""

        first = installation_owner(
            ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.5.0"),
            scope=Scope.PROJECT,
            root="/work/project",
            harness="claude",
        )
        second = installation_owner(
            ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", "github"), "2.0.0"),
            scope=Scope.PROJECT,
            root="/work/project",
            harness="claude",
        )

        self.assertEqual(first, second)
        self.assertEqual(credential_address(first, TOKEN), credential_address(second, TOKEN))

    def test_an_owner_carries_every_field_the_contract_names(self) -> None:
        owner = installation_owner(
            ArtifactCoordinate(SourceAlias("company"), ArtifactIdentity("mcp", "github")),
            scope=Scope.USER,
            root="/users/alice",
            harness="opencode",
            profile="work",
        )

        self.assertEqual(
            (owner.source, owner.artifact, owner.scope, owner.root, owner.harness, owner.profile),
            (
                SourceAlias("company"),
                ArtifactIdentity("mcp", "github"),
                Scope.USER,
                "/users/alice",
                "opencode",
                "work",
            ),
        )


class CredentialAddressSeparationTest(unittest.TestCase):
    """Each owner field, varied on its own, has to move the address."""

    def test_every_owner_field_separates_the_item(self) -> None:
        base = credential_address(_owner(), TOKEN)
        for field, value in (
            ("source", SourceAlias("company-local")),
            ("artifact", ArtifactIdentity("mcp", "gitlab")),
            ("artifact", ArtifactIdentity("skill", "github")),
            ("scope", Scope.USER),
            ("root", "/work/other-project"),
            ("harness", "tabnine"),
            ("profile", "work"),
        ):
            with self.subTest(field=field, value=value):
                self.assertNotEqual(base, credential_address(_owner(**{field: value}), TOKEN))

    def test_two_declared_inputs_under_one_owner_are_two_items(self) -> None:
        owner = _owner()

        self.assertNotEqual(
            credential_address(owner, TOKEN), credential_address(owner, InputId("api-secret"))
        )

    def test_the_same_owner_and_input_derive_the_same_address_every_time(self) -> None:
        """A retry has to reach the item the first attempt wrote, not a second one beside it."""

        self.assertEqual(credential_address(_owner(), TOKEN), credential_address(_owner(), TOKEN))

    def test_an_absent_profile_still_occupies_its_slot(self) -> None:
        """A fixed count of labels is what lets one address be read back to exactly one owner.

        Leave the slot out when there is no profile and the labels shift, so which component is
        the profile depends on whether the harness has one -- and `claude` with profile `user` no
        longer reads differently from `claude` at user scope.
        """

        without = credential_address(_owner(), TOKEN).service.split(".")
        with_profile = credential_address(_owner(profile="work"), TOKEN).service.split(".")

        self.assertEqual(len(without), len(with_profile))
        self.assertEqual("-", without[2])
        self.assertEqual("work", with_profile[2])
        self.assertNotEqual(
            credential_address(_owner(scope=Scope.PROJECT, profile="user"), TOKEN),
            credential_address(_owner(scope=Scope.USER, profile=""), TOKEN),
        )


class CredentialAddressShapeTest(unittest.TestCase):
    def test_the_labels_are_readable_and_the_root_is_not_in_them(self) -> None:
        address = credential_address(_owner(root="/work/secret-client-name"), TOKEN)

        self.assertTrue(address.service.startswith(CREDENTIAL_SERVICE_PREFIX + "."))
        for label in ("claude", "project", "company", "mcp", "github"):
            with self.subTest(label=label):
                self.assertIn(label, address.service)
        self.assertNotIn("secret-client-name", address.service)
        self.assertNotIn("/", address.service)
        self.assertEqual("api-token", address.account)

    def test_the_provider_is_the_one_asked_for(self) -> None:
        self.assertEqual("keychain", credential_address(_owner(), TOKEN).provider)
        self.assertEqual(
            "secret-service",
            credential_address(_owner(), TOKEN, provider="secret-service").provider,
        )

    def test_an_address_too_long_for_a_provider_is_refused_rather_than_truncated(self) -> None:
        """Truncation is how two owners silently become one item."""

        long_name = "a" + "-b" * 120

        with self.assertRaises(ValueError):
            credential_address(_owner(artifact=ArtifactIdentity("mcp", long_name)), TOKEN)


class InstallationOwnerRefusalTest(unittest.TestCase):
    def test_a_root_that_is_not_a_normalized_absolute_path_is_refused(self) -> None:
        for root in ("relative/root", "/work/../work", "/work/project/", "", "/work/pro\nject"):
            with self.subTest(root=root):
                with self.assertRaises(ValueError):
                    _owner(root=root)

    def test_a_harness_alias_or_name_that_is_not_a_slug_is_refused(self) -> None:
        for field, value in (
            ("harness", "Claude"),
            ("harness", "claude code"),
            ("harness", ""),
            ("source", SourceAlias("Company")),
            ("source", SourceAlias("a/b")),
            ("artifact", ArtifactIdentity("mcp", "GitHub")),
            ("artifact", ArtifactIdentity("mcp", "")),
            ("profile", "Work"),
            ("profile", "a.b"),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    _owner(**{field: value})

    def test_a_root_that_is_not_a_string_is_refused_as_a_root(self) -> None:
        """`posixpath` would answer a non-string with a `TypeError`, which is not a refusal."""

        for root in (5, None, ("/work", "project")):
            with self.subTest(root=root):
                with self.assertRaises(ValueError):
                    _owner(root=root)

    def test_something_that_is_not_a_scope_or_an_input_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _owner(scope="project")
        with self.assertRaises(ValueError):
            credential_address(_owner(), "api-token")  # type: ignore[arg-type]


class CredentialAddressPropertyTest(unittest.TestCase):
    _slugs = st.builds(
        "-".join,
        st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=6),
            min_size=1,
            max_size=3,
        ).filter(lambda parts: parts[0][0].isalpha()),
    )
    _owners = st.builds(
        lambda alias, name, scope, root, harness: _owner(
            source=SourceAlias(alias),
            artifact=ArtifactIdentity("mcp", name),
            scope=scope,
            root="/" + root,
            harness=harness,
        ),
        _slugs,
        _slugs,
        st.sampled_from(tuple(Scope)),
        _slugs,
        _slugs,
    )

    @given(first=_owners, second=_owners)
    @settings(max_examples=200, suppress_health_check=(HealthCheck.differing_executors,))
    def test_two_owners_share_an_address_only_when_they_are_the_same_owner(
        self, first: InstallationOwner, second: InstallationOwner
    ) -> None:
        same = credential_address(first, TOKEN) == credential_address(second, TOKEN)

        self.assertEqual(same, first == second)

    @given(owner=_owners)
    @settings(max_examples=200, suppress_health_check=(HealthCheck.differing_executors,))
    def test_every_address_stays_within_what_a_provider_will_hold(
        self, owner: InstallationOwner
    ) -> None:
        address = credential_address(owner, TOKEN)

        self.assertLessEqual(len(address.service), MAX_CREDENTIAL_SERVICE_LENGTH)
        self.assertNotIn(owner.root, address.service)


if __name__ == "__main__":
    unittest.main()
