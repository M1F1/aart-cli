"""A configured Registry's versions are addressed by the alias, not by the name inside it (D-362).

The version records in a Registry name the registry that approved them, and that name is *content*:
the maintainer writes it once, and every branch, mirror and checkout of the repository carries it
unchanged. An alias is this machine's name for one connection, and D-350 allows two connections to
one Registry at once -- a checkout of it on this disk and its remote -- under two distinct aliases.

So the alias has to win, and it has to win in one place. `load_configured_registry_versions` is that
place: every reader of a configured Registry's published versions goes through it, because a version
addressed one way where it is resolved and another way where it is installed is a version no install
can find. The Registry in this fixture calls itself `company` and is configured here as
`local-registry`, so a reader that preferred the stored name would say so out loud.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from aart_cli.configuration.model import SourceKind
from aart_cli.domain.identifiers import SourceId
from aart_cli.domain.result import Ok
from aart_cli.io.configured_selection import load_configured_approved_marketplace
from aart_cli.io.source_store import publish_source_snapshot
from aart_cli.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.marketplace_fixtures import configured_source, effective_configuration
from tests.registry_maintenance_fixtures import approved_registry_snapshot

#: What the Registry's own content calls it, and what this machine has configured it as. They
#: differ on purpose: were either one the other, no assertion here could tell them apart.
REGISTRY_NAME = "company"
ALIAS = "local-registry"

NAMES = ("github-mcp", "helper-mcp")


class ConfiguredRegistryAliasTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_root = str(pathlib.Path(temporary.name).resolve() / "data")
        self.source = configured_source(ALIAS, SourceKind.REGISTRY_GIT)
        self.effective = effective_configuration((self.source,), default_registry=ALIAS)

        snapshot = approved_registry_snapshot(names=NAMES, registry_alias=REGISTRY_NAME)
        candidate = make_source_candidate(
            source_instance_id(self.source), self.source.alias, "a" * 40, snapshot
        )
        assert isinstance(candidate, Ok), candidate
        written = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(self.source)),
                ValidatedSourceCandidate(candidate.value, SourceId(f"{REGISTRY_NAME}-registry")),
                90,
            )
        )
        assert isinstance(written, Ok), getattr(written, "diagnostics", ())

    def _approved(self):
        loaded = load_configured_approved_marketplace(self.effective, data_root=self.data_root)
        assert isinstance(loaded, Ok), getattr(loaded, "diagnostics", ())
        return loaded.value

    def test_every_approved_version_is_addressed_by_the_alias_not_by_the_registry_name(
        self,
    ) -> None:
        approved = self._approved()

        addressed = sorted(
            (item.version.coordinate.source.value, item.version.coordinate.artifact.name)
            for item in approved.artifacts
        )

        self.assertEqual(addressed, [(ALIAS, name) for name in sorted(NAMES)])

    def test_a_registry_configured_under_its_own_name_is_addressed_the_same_way(self) -> None:
        """The re-addressing is not a special case for a renamed Registry.

        Whether the alias happens to equal the name inside the Registry is a coincidence of this
        machine's configuration, so the reader must not have two behaviours that a coincidence
        chooses between. The published versions are identical content either way.
        """

        source = configured_source(REGISTRY_NAME, SourceKind.REGISTRY_GIT)
        effective = effective_configuration((source,), default_registry=REGISTRY_NAME)
        snapshot = approved_registry_snapshot(names=NAMES, registry_alias=REGISTRY_NAME)
        candidate = make_source_candidate(
            source_instance_id(source), source.alias, "a" * 40, snapshot
        )
        assert isinstance(candidate, Ok), candidate
        written = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(source)),
                ValidatedSourceCandidate(candidate.value, SourceId(f"{REGISTRY_NAME}-registry")),
                90,
            )
        )
        assert isinstance(written, Ok), getattr(written, "diagnostics", ())

        loaded = load_configured_approved_marketplace(effective, data_root=self.data_root)

        assert isinstance(loaded, Ok), getattr(loaded, "diagnostics", ())
        self.assertEqual(
            sorted(
                (item.version.coordinate.source.value, item.version.coordinate.artifact.name)
                for item in loaded.value.artifacts
            ),
            [(REGISTRY_NAME, name) for name in sorted(NAMES)],
        )
