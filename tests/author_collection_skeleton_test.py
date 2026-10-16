"""`aart-cli author init --kind collection` writes a Collection the Collection parser accepts (§173.3).

A Collection is a different document from an artifact manifest -- top-level `name` and `artifacts`
rather than an `artifact` block -- so it has its own generator and its own half of the oracle in
`tests/author_skeleton_test.py`: every field `parse_author_collection_manifest` accepts is named,
what is written parses, and the same text with every disabled line enabled parses too. It writes
no version, because the Registry assigns one (§173.1).
"""

from __future__ import annotations

import unittest

from aart_cli.authoring.skeleton import (
    COLLECTION_KIND,
    GENERATED_KINDS,
    INIT_KINDS,
    author_skeleton,
)
from aart_cli.cli_parser import build_parser
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import (
    AUTHORED_KINDS,
    DiscoveredAuthorManifest,
    parse_author_collection_manifest,
)
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.protocol.registry_versions import NO_REGISTRY
from tests.author_skeleton_test import _keys, _uncommented
from tests.authoring_field_surface import parser_field_surface

_NAME = "data-engineer"


def _skeleton(name: str = _NAME):
    result = author_skeleton(COLLECTION_KIND, name)
    assert isinstance(result, Ok), result
    return result.value


def _parsed(text: str):
    path = parse_relative_path("aart-cli.yaml")
    assert isinstance(path, Ok), path
    return parse_author_collection_manifest(
        DiscoveredAuthorManifest(path.value, text.encode()),
        source_alias=SourceAlias("authors"),
        source="https://git.example/authors.git",
        revision="a" * 40,
        versions=NO_REGISTRY,
    )


class CollectionSkeletonTest(unittest.TestCase):
    def test_what_is_written_parses_with_the_collection_parser(self) -> None:
        parsed = _parsed(_skeleton().manifest)

        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        assert isinstance(parsed, Ok)
        self.assertEqual(parsed.value.name, _NAME)
        self.assertTrue(parsed.value.members)

    def test_every_field_the_collection_parser_accepts_is_named(self) -> None:
        keys = _keys(_skeleton().manifest)
        missing = sorted(
            name
            for site in parser_field_surface()
            if site.owner == "parse_author_collection_manifest"
            for name in (*site.required, *site.optional)
            if name not in keys
        )

        self.assertEqual(missing, [])

    def test_the_same_text_with_every_disabled_line_enabled_parses_too(self) -> None:
        enabled = _uncommented(_skeleton().manifest)

        parsed = _parsed(enabled)

        self.assertIsInstance(parsed, Ok, getattr(parsed, "diagnostics", ()))
        assert isinstance(parsed, Ok)
        self.assertNotEqual(parsed.value.summary, _NAME.replace("-", " ").capitalize())

    def test_it_writes_no_version(self) -> None:
        self.assertNotIn("version", _keys(_skeleton().manifest))

    def test_it_writes_no_payload(self) -> None:
        """A Collection ships nothing of its own; its members carry the payload."""

        self.assertEqual(_skeleton().payload, ())

    def test_the_skeleton_reports_the_kind_and_name_it_was_asked_for(self) -> None:
        skeleton = _skeleton("platform-team")

        self.assertEqual((skeleton.kind, skeleton.name), (COLLECTION_KIND, "platform-team"))
        self.assertIn("name: platform-team\n", skeleton.manifest)

    def test_a_name_that_is_not_a_slug_is_refused_by_the_collection_parser(self) -> None:
        result = author_skeleton(COLLECTION_KIND, "Not A Slug")

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].message, "Collection name must be a lowercase slug")


class InitKindsTest(unittest.TestCase):
    def test_init_offers_every_artifact_kind_and_a_collection(self) -> None:
        self.assertEqual(INIT_KINDS, tuple(sorted((*GENERATED_KINDS, COLLECTION_KIND))))

    def test_init_generates_exactly_the_kinds_the_parser_reads(self) -> None:
        """The CLI offers `AUTHORED_KINDS`; a kind on it with no generator would be refused."""

        self.assertEqual(INIT_KINDS, AUTHORED_KINDS)

    def test_the_cli_accepts_a_collection_kind(self) -> None:
        parsed = build_parser().parse_args(
            ["author", "init", "--kind", "collection", "--name", _NAME]
        )

        self.assertEqual(parsed.artifact_kind, COLLECTION_KIND)

    def test_an_unknown_kind_is_refused_naming_a_collection_among_the_offers(self) -> None:
        result = author_skeleton("agent", _NAME)

        assert isinstance(result, Err), result
        self.assertIn(COLLECTION_KIND, result.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
