"""B-038: which installs `aart marketplace install` sends to the canonical registry seam.

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

from agent_artifacts.commands.marketplace import _configured_registry_selection
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.consumer.coordinates import ArtifactSelector
from agent_artifacts.domain.identifiers import ArtifactIdentity, SourceAlias
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
        """Choosing a source here would be new product policy, so only a default can decide."""

        effective = effective_configuration((REGISTRY,), default_registry="company")

        self.assertIsNotNone(_configured_registry_selection((_selector(None),), effective))
        self.assertIsNone(
            _configured_registry_selection((_selector(None),), effective_configuration((REGISTRY,)))
        )

    def test_a_direct_source_coordinate_stays_on_the_characterized_path(self) -> None:
        """The residue B-038 names, and the reason it is not a one-line change.

        `tests/marketplace_lifecycle_e2e_test.py` installs, updates, symlinks and uninstalls
        against a real synchronized `SOURCE_LOCAL` source through this command. Every one of those
        goes down the legacy path because of this `None`, so the route is load-bearing today
        whatever is eventually decided about it.
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

    def test_a_collection_is_declined_whatever_its_source(self) -> None:
        """A capability, not a policy: the canonical seam expands no Collection yet.

        `marketplace_lifecycle_e2e_test.py::test_collection_install_materializes_every_expanded_
        member` is what would stop working if this `None` were removed before that exists.
        """

        self.assertIsNone(
            _configured_registry_selection(
                (_selector("company", kind="collection", name="essentials"),),
                effective_configuration((REGISTRY,)),
            )
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
