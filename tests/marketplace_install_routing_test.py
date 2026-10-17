"""B-038: which installs `aart-cli consume install` sends to the canonical registry seam.

The strangler moves one source kind at a time, and the decision that says which is
`_configured_registry_selection`. Nothing named it, so the route could change -- in either
direction -- without a test noticing, which is the one thing a strangler cannot afford: a
half-migrated command silently installing through the path nobody meant.

What is pinned here is the decision and each of its reasons, not a preference for either route.
Two of the reasons are capabilities the canonical seam does not have yet rather than policy, and
they are asserted as what they are, so that closing either one turns exactly one of these tests
red instead of leaving the routing to be re-derived from scratch.
"""

from __future__ import annotations

import unittest

from aart_cli.commands.marketplace import _configured_registry_selection
from aart_cli.configuration.model import SourceKind
from aart_cli.consumer.coordinates import ArtifactSelector
from aart_cli.domain.identifiers import ArtifactIdentity, ObjectDigest, SourceAlias
from aart_cli.domain.selection import Collection, CollectionCoordinate
from tests.marketplace_fixtures import configured_source, effective_configuration

REGISTRY = configured_source("company", SourceKind.REGISTRY_GIT)
FEED = configured_source("authors", SourceKind.SOURCE_LOCAL)
UPSTREAM = configured_source("upstream", SourceKind.SOURCE_GIT)


def _selector(source: str | None, kind: str = "skill", name: str = "code-review"):
    return ArtifactSelector(
        ArtifactIdentity(kind, name), None if source is None else SourceAlias(source)
    )


class ConfiguredRoutingTest(unittest.TestCase):
    def test_an_approved_registry_coordinate_takes_the_canonical_seam(self) -> None:
        selection = _configured_registry_selection(
            (_selector("company"),), effective_configuration((REGISTRY,))
        )

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(selection.artifacts[0].source, SourceAlias("company"))

    def test_an_unqualified_coordinate_follows_the_configured_default_registry(self) -> None:
        """A default binds the Registry; without one the resolver decides among Registries (D-444)."""

        effective = effective_configuration((REGISTRY,), default_registry="company")

        bound = _configured_registry_selection((_selector(None),), effective)
        unbound = _configured_registry_selection(
            (_selector(None),), effective_configuration((REGISTRY,))
        )

        assert bound is not None and unbound is not None
        self.assertEqual([item.source for item in bound.artifacts], [REGISTRY.alias])
        # Left for the resolver, which installs the one Registry offering it or names them all.
        self.assertEqual([item.source for item in unbound.artifacts], [None])

    def test_a_direct_source_coordinate_stays_on_the_characterized_path(self) -> None:
        """An Upstream repository is never the seam's to resolve: a consumer reads only Registries.

        The `None` sends the command to `_outside_registries`, which refuses it as an Upstream
        repository (INV-269, D-444).
        """

        for source in (FEED, UPSTREAM):
            with self.subTest(kind=source.kind.value):
                self.assertIsNone(
                    _configured_registry_selection(
                        (_selector(source.alias.value),), effective_configuration((source,))
                    )
                )

    def test_a_registry_coordinate_beside_a_direct_source_still_takes_the_seam(self) -> None:
        """The decision is about the selector's source, not about what else is configured."""

        selection = _configured_registry_selection(
            (_selector("company"),), effective_configuration((REGISTRY, FEED))
        )

        self.assertIsNotNone(selection)

    def test_a_collection_routes_as_the_collection_at_its_highest_approved_version(self) -> None:
        """D-422: the seam installs the Collection itself, not its members picked one by one."""

        approved = tuple(
            Collection(
                CollectionCoordinate(SourceAlias("company"), "essentials", version),
                "Essentials.",
                (),
                ObjectDigest("sha256", "e" * 64),
            )
            for version in ("1.2.0", "1.10.0", "1.9.3")
        )

        selection = _configured_registry_selection(
            (_selector("company", kind="collection", name="essentials"),),
            effective_configuration((REGISTRY,)),
            approved,
        )

        assert selection is not None
        self.assertEqual(selection.artifacts, ())
        self.assertEqual(
            [str(item) for item in selection.collections], ["company/collection/essentials@1.10.0"]
        )

    def test_a_disabled_registry_is_not_a_registry_for_routing(self) -> None:
        disabled = configured_source("company", SourceKind.REGISTRY_GIT, enabled=False)

        self.assertIsNone(
            _configured_registry_selection(
                (_selector("company"),), effective_configuration((disabled,))
            )
        )

    def test_one_direct_selector_declines_the_whole_batch(self) -> None:
        """A Selection is executed as one transaction, so it cannot be split across two routes."""

        self.assertIsNone(
            _configured_registry_selection(
                (_selector("company"), _selector("authors")),
                effective_configuration((REGISTRY, FEED)),
            )
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
