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
    INSTALLED_NAME_COLLISION,
    INSTALLED_NAME_INVALID,
    MAX_CREDENTIAL_SERVICE_LENGTH,
    MAX_INSTALLED_NAME_LENGTH,
    InstallationOwner,
    credential_address,
    installation_key,
    installation_owner,
    installed_name,
    installed_name_for,
    installed_names,
)
from aart_cli.domain.result import Err, Ok

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


class InstallationKeyTest(unittest.TestCase):
    """§169.3: what addresses one installation, where the coordinate addresses an artifact.

    The keys a row, a focus and a lookup are built from. They have to be distinct per installation
    -- two rows spelled the same make one of them unreachable and aim an action at whichever a
    dictionary kept -- and they have to stay distinguishable from a plain coordinate, because both
    travel through the same string-typed fields.
    """

    def test_the_harness_is_what_separates_two_installations_of_one_artifact(self) -> None:
        coordinate = "company/mcp/github@1.5.0"

        keys = [
            installation_key(coordinate, _owner(harness=harness))
            for harness in ("claude", "opencode")
        ]

        self.assertEqual(keys, [f"{coordinate}#claude", f"{coordinate}#opencode"])

    def test_two_profiles_of_one_harness_are_two_keys(self) -> None:
        """A profile is part of the installation, so a key that dropped it would address both."""

        coordinate = "company/mcp/github@1.5.0"

        self.assertEqual(
            installation_key(coordinate, _owner(profile="work")), f"{coordinate}#claude+work"
        )
        self.assertNotEqual(
            installation_key(coordinate, _owner(profile="work")),
            installation_key(coordinate, _owner()),
        )

    def test_a_record_naming_no_owner_is_addressed_by_what_it_is(self) -> None:
        """The callers below the boundary that knows an owner. Nothing is invented for them."""

        self.assertEqual(
            installation_key("company/mcp/github@1.5.0", None), "company/mcp/github@1.5.0"
        )

    def test_a_key_is_never_spelled_like_a_coordinate(self) -> None:
        """`#` cannot occur in an alias, kind, name or version, so the two never collide."""

        key = installation_key("company/mcp/github@1.5.0", _owner())

        self.assertNotIn("#", "company/mcp/github@1.5.0")
        self.assertEqual(key.count("#"), 1)

    def test_only_an_owner_or_nothing_will_do(self) -> None:
        with self.assertRaises(ValueError):
            installation_key("company/mcp/github@1.5.0", "claude")  # type: ignore[arg-type]


class InstallationKeyPropertyTest(unittest.TestCase):
    _owners = CredentialAddressPropertyTest._owners

    @given(first=_owners, second=_owners)
    @settings(max_examples=200, suppress_health_check=(HealthCheck.differing_executors,))
    def test_two_installations_of_one_artifact_share_a_key_only_when_the_harness_is_the_same(
        self, first: InstallationOwner, second: InstallationOwner
    ) -> None:
        """The claim a row list depends on, stated over owners rather than over two examples.

        Only the harness and profile can separate two keys, because the rest of the owner is what
        the coordinate already says. So the key is the same exactly when the label is -- and an
        owner differing only in scope or root is deliberately *not* a second row, which is a fact
        worth pinning rather than discovering from a duplicate row later.
        """

        coordinate = "company/mcp/github@1.5.0"

        same = installation_key(coordinate, first) == installation_key(coordinate, second)

        self.assertEqual(same, first.label == second.label)


class InstalledNameTest(unittest.TestCase):
    """§169.7: what the harness shows is the artifact, the alias and the scope, never the version."""

    def test_the_portable_spelling_is_the_three_labels_joined_once(self) -> None:
        named = installed_name(_owner(artifact=ArtifactIdentity("skill", "github")))

        assert isinstance(named, Ok), named
        self.assertEqual("github-company-project", named.value)

    def test_user_scope_is_spelled_out_rather_than_left_off(self) -> None:
        named = installed_name(
            _owner(artifact=ArtifactIdentity("skill", "github"), scope=Scope.USER, root="/users/a")
        )

        assert isinstance(named, Ok), named
        self.assertEqual("github-company-user", named.value)

    def test_the_version_never_reaches_the_name(self) -> None:
        owner = installation_owner(
            ArtifactCoordinate(
                SourceAlias("company"), ArtifactIdentity("skill", "github"), "9.9.9"
            ),
            scope=Scope.PROJECT,
            root="/work/project",
            harness="opencode",
        )

        named = installed_name(owner)

        assert isinstance(named, Ok), named
        self.assertNotIn("9", named.value)

    def test_the_harness_and_root_are_not_in_the_visible_name(self) -> None:
        """A readable name is not an identity; §169.4's owner stays the authority."""

        first = installed_name(_owner(artifact=ArtifactIdentity("skill", "github")))
        second = installed_name(
            _owner(artifact=ArtifactIdentity("skill", "github"), harness="tabnine")
        )

        assert isinstance(first, Ok) and isinstance(second, Ok)
        self.assertEqual(first.value, second.value)

    def test_a_name_the_harness_contract_would_reject_is_refused(self) -> None:
        for owner in (
            _owner(artifact=ArtifactIdentity("skill", "a" + "-b" * 40)),
            _owner(source=SourceAlias("a" + "-b" * 40)),
        ):
            with self.subTest(owner=owner):
                refused = installed_name(owner)
                self.assertIsInstance(refused, Err, refused)
                diagnostic = refused.diagnostics[0]
                self.assertEqual(diagnostic.code.value, INSTALLED_NAME_INVALID.value)
                self.assertTrue(diagnostic.remediation, "a refusal must say what to do instead")

    def test_the_longest_name_the_contract_allows_is_still_a_name(self) -> None:
        """1-64 characters, so 64 is accepted and 65 is not. The bound is the contract's, exactly."""

        fixed = len("-company-project")
        longest = _owner(
            artifact=ArtifactIdentity("skill", "a" * (MAX_INSTALLED_NAME_LENGTH - fixed))
        )
        over = _owner(
            artifact=ArtifactIdentity("skill", "a" * (MAX_INSTALLED_NAME_LENGTH - fixed + 1))
        )

        named = installed_name(longest)

        assert isinstance(named, Ok), named
        self.assertEqual(MAX_INSTALLED_NAME_LENGTH, len(named.value))
        self.assertIsInstance(installed_name(over), Err)

    def test_every_composed_name_matches_the_published_skill_grammar(self) -> None:
        named = installed_name(_owner(artifact=ArtifactIdentity("skill", "github-mcp")))

        assert isinstance(named, Ok), named
        self.assertRegex(named.value, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertLessEqual(len(named.value), MAX_INSTALLED_NAME_LENGTH)


class InstalledNameCollisionTest(unittest.TestCase):
    """The join is ambiguous by construction, so the set is checked before anything is written."""

    def test_two_owners_that_would_spell_the_same_name_are_refused_together(self) -> None:
        """The hyphen that joins the labels is also a hyphen inside them, so the split can move."""

        plain = _owner(
            source=SourceAlias("company-user"), artifact=ArtifactIdentity("skill", "github")
        )
        hyphenated = _owner(
            source=SourceAlias("user"), artifact=ArtifactIdentity("skill", "github-company")
        )

        refused = installed_names((plain, hyphenated))

        self.assertIsInstance(refused, Err, refused)
        diagnostic = refused.diagnostics[0]
        self.assertEqual(diagnostic.code.value, INSTALLED_NAME_COLLISION.value)
        self.assertIn("github-company-user-project", diagnostic.message)
        self.assertTrue(diagnostic.remediation)

    def test_distinct_owners_with_distinct_names_are_all_returned(self) -> None:
        owners = (
            _owner(artifact=ArtifactIdentity("skill", "github")),
            _owner(artifact=ArtifactIdentity("skill", "gitlab")),
            _owner(artifact=ArtifactIdentity("skill", "github"), source=SourceAlias("other")),
        )

        named = installed_names(owners)

        assert isinstance(named, Ok), named
        self.assertEqual(
            dict(named.value),
            {
                owners[0]: "github-company-project",
                owners[1]: "gitlab-company-project",
                owners[2]: "github-other-project",
            },
        )

    def test_the_name_is_available_before_a_harness_is_known(self) -> None:
        """Placement composes the delivered directory before any owner exists to compose it from.

        The join carries the artifact, the Registry alias and the scope, and no harness and no
        root, so it can be asked for from a coordinate alone -- and must be the same answer the
        owner gives, or a directory would be delivered under one name and recorded under another.
        """

        owner = _owner(artifact=ArtifactIdentity("skill", "code-review"))

        self.assertEqual(
            installed_name(owner),
            installed_name_for(
                ArtifactCoordinate(owner.source, owner.artifact, "1.0.0"), owner.scope
            ),
        )

    def test_a_coordinate_that_cannot_be_a_name_is_refused_the_same_way(self) -> None:
        refused = installed_name_for(
            ArtifactCoordinate(
                SourceAlias("company"), ArtifactIdentity("skill", "a" * 80), "1.0.0"
            ),
            Scope.PROJECT,
        )

        assert isinstance(refused, Err), refused
        self.assertEqual(refused.diagnostics[0].code, INSTALLED_NAME_INVALID)

    def test_the_same_visible_name_in_two_harness_namespaces_is_not_a_collision(self) -> None:
        owners = (
            _owner(artifact=ArtifactIdentity("skill", "github"), harness="claude"),
            _owner(artifact=ArtifactIdentity("skill", "github"), harness="tabnine"),
        )

        named = installed_names(owners)

        assert isinstance(named, Ok), named
        self.assertEqual(dict(named.value), {owner: "github-company-project" for owner in owners})

    def test_one_owner_named_twice_is_not_a_collision_with_itself(self) -> None:
        owner = _owner(artifact=ArtifactIdentity("skill", "github"))

        named = installed_names((owner, owner))

        assert isinstance(named, Ok), named
        self.assertEqual(1, len(named.value))

    def test_a_name_that_cannot_be_composed_refuses_the_whole_set(self) -> None:
        refused = installed_names(
            (
                _owner(artifact=ArtifactIdentity("skill", "github")),
                _owner(artifact=ArtifactIdentity("skill", "a" + "-b" * 40)),
            )
        )

        self.assertIsInstance(refused, Err, refused)


if __name__ == "__main__":
    unittest.main()
