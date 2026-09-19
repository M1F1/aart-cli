"""`aart author init` writes a skeleton the parser accepts and no field it forgot.

The maintainer's requirement is that the skeleton carries the *full* accepted surface, so an agent
or a person deletes down to what they need instead of discovering fields by reading the parser.
The risk that creates is a generator that quietly drifts from the parser it is supposed to mirror,
and the answer to it is the oracle CP-26.6 built: `tests/authoring_field_surface.py` reads the
parser, and every name it reports has to appear in the skeleton. Adding a field to the parser turns
this module red until the skeleton carries it.

The other two claims are the ones that make the skeleton useful rather than merely complete: what
is written parses with the real `parse_author_manifest`, and the same document with every optional
block live parses too -- so uncommenting a block is a working edit, not a guess.
"""

from __future__ import annotations

import unittest

from agent_artifacts.authoring.skeleton import (
    ALTERNATIVE_PREFIX,
    COMMENTED_YAML_PREFIX,
    PROSE_PREFIX,
    author_skeleton,
)
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import DiscoveredAuthorManifest, parse_author_manifest
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.protocol.yaml import emit_yaml, parse_yaml
from tests.authoring_field_surface import parser_field_surface

_NAME = "github-mcp"


def _skeleton(kind: str = "mcp", name: str = _NAME):
    result = author_skeleton(kind, name)
    assert isinstance(result, Ok), result
    return result.value


def _parsed(text: str):
    path = parse_relative_path("aart.yaml")
    assert isinstance(path, Ok), path
    return parse_author_manifest(DiscoveredAuthorManifest(path.value, text.encode()))


def _keys(text: str) -> frozenset[str]:
    """Every field name the skeleton names, live, disabled, or offered as an alternative."""

    found: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        for prefix in (PROSE_PREFIX, ALTERNATIVE_PREFIX, COMMENTED_YAML_PREFIX):
            if line.startswith(prefix):
                line = line[len(prefix) :].strip()
                break
        line = line.removeprefix("- ").strip()
        if ":" in line:
            found.add(line.split(":", 1)[0].strip())
    return frozenset(found)


def _uncommented(text: str) -> str:
    """Turn every commented-out YAML line back into the line it stands for."""

    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        if stripped.startswith(PROSE_PREFIX) or stripped.startswith(ALTERNATIVE_PREFIX):
            continue
        if stripped.startswith(COMMENTED_YAML_PREFIX):
            indent = len(line) - len(stripped)
            lines.append(" " * indent + stripped[len(COMMENTED_YAML_PREFIX) :])
            continue
        lines.append(line)
    return "".join(f"{line}\n" for line in lines)


class ParseabilityTest(unittest.TestCase):
    def test_what_is_written_parses_with_the_real_parser(self) -> None:
        parsed = _parsed(_skeleton().manifest)

        self.assertIsInstance(parsed, Ok, parsed)

    def test_the_same_document_with_every_optional_block_live_parses_too(self) -> None:
        emitted = emit_yaml(_skeleton().full)
        assert isinstance(emitted, Ok), emitted

        parsed = _parsed(emitted.value)

        self.assertIsInstance(parsed, Ok, parsed)

    def test_uncommenting_the_skeleton_yields_exactly_that_document(self) -> None:
        """The commented text is the live document, not prose that resembles it."""

        skeleton = _skeleton()
        emitted = emit_yaml(skeleton.full)
        assert isinstance(emitted, Ok), emitted

        self.assertEqual(
            parse_yaml(_uncommented(skeleton.manifest)),
            parse_yaml(emitted.value),
        )

    def test_the_required_only_document_is_what_the_skeleton_parses_to(self) -> None:
        parsed = parse_yaml(_skeleton().manifest)

        self.assertEqual(parsed, Ok(_skeleton().live))


class AntiDriftTest(unittest.TestCase):
    """The oracle of CP-26.6 §1.5: the parser decides what the skeleton must carry."""

    def test_every_field_name_the_parser_accepts_appears_as_a_key(self) -> None:
        missing = sorted(
            name
            for site in parser_field_surface()
            # A collection manifest is a different document with a different generator; step 12
            # gives it its own skeleton and its own half of this oracle.
            if site.owner != "parse_author_collection_manifest"
            for name in (*site.required, *site.optional)
            if name not in _keys(_skeleton().manifest)
        )

        self.assertEqual(
            missing, [], f"the parser accepts fields the skeleton never names: {missing}"
        )

    def test_an_unresolved_site_is_still_covered(self) -> None:
        """The three computed sites are where a skeleton silently loses fields."""

        skeleton = _skeleton().manifest

        for name in ("required", "help", "default", "validation", "pyproject", "lock"):
            with self.subTest(field=name):
                self.assertIn(name, skeleton)


class AlternativeTest(unittest.TestCase):
    """An alternative is offered so it can be enabled, so it has to be enable-able."""

    def _alternatives(self) -> tuple[str, ...]:
        return tuple(
            line.strip()[len(ALTERNATIVE_PREFIX) :]
            for line in _skeleton().manifest.splitlines()
            if line.strip().startswith(ALTERNATIVE_PREFIX)
        )

    def test_the_skeleton_offers_alternatives_at_all(self) -> None:
        self.assertTrue(self._alternatives())

    def test_no_alternative_uses_a_construct_this_yaml_subset_cannot_read(self) -> None:
        """Flow mappings and sequences parse in YAML at large and are refused here."""

        for line in self._alternatives():
            with self.subTest(line=line):
                value = line.split(":", 1)[1].strip() if ":" in line else ""

                self.assertFalse(value.startswith(("{", "[", "&", "*", "!", "|", ">")), line)

    def test_every_alternative_is_a_mapping_entry(self) -> None:
        for line in self._alternatives():
            with self.subTest(line=line):
                self.assertIn(":", line)


class ShapeTest(unittest.TestCase):
    def test_the_generator_is_deterministic(self) -> None:
        self.assertEqual(_skeleton().manifest, _skeleton().manifest)

    def test_the_payload_skeleton_matches_what_the_manifest_includes(self) -> None:
        skeleton = _skeleton()

        self.assertTrue(skeleton.payload)
        for path, _content in skeleton.payload:
            self.assertTrue(path.startswith("payload/"), path)

    def test_the_manifest_declares_the_entrypoint_the_payload_provides(self) -> None:
        skeleton = _skeleton()
        parsed = _parsed(skeleton.manifest)
        assert isinstance(parsed, Ok), parsed

        self.assertIsNotNone(parsed.value.entrypoint)
        self.assertIn(str(parsed.value.entrypoint), [path for path, _content in skeleton.payload])

    def test_the_name_the_caller_gave_is_the_artifact_name(self) -> None:
        parsed = _parsed(_skeleton(name="atlassian").manifest)
        assert isinstance(parsed, Ok), parsed

        self.assertEqual(parsed.value.name, "atlassian")


class RefusalTest(unittest.TestCase):
    def test_a_kind_this_step_does_not_generate_is_refused_by_name(self) -> None:
        result = author_skeleton("guideline", _NAME)

        assert isinstance(result, Err), result
        self.assertIn("guideline", result.diagnostics[0].message)

    def test_a_kind_the_parser_does_not_know_is_refused(self) -> None:
        result = author_skeleton("plugin", _NAME)

        assert isinstance(result, Err), result
        self.assertIn("plugin", result.diagnostics[0].message)

    def test_a_name_that_is_not_a_slug_is_refused_before_anything_is_written(self) -> None:
        result = author_skeleton("mcp", "Not A Slug")

        assert isinstance(result, Err), result
        self.assertIn("slug", result.diagnostics[0].message)

    def test_the_name_rule_is_the_parser_own_rule_and_not_a_copy_of_it(self) -> None:
        """`github-mcp-` reads as a slug to a scan over the alphabet and is not one."""

        result = author_skeleton("mcp", "github-mcp-")

        assert isinstance(result, Err), result
        self.assertEqual(result.diagnostics[0].message, "artifact.name must be a lowercase slug")

    def test_a_generated_manifest_is_parsed_before_it_is_returned(self) -> None:
        """Whatever the generator produces, what comes back has been through the real parser."""

        skeleton = _skeleton()

        self.assertIsInstance(_parsed(skeleton.manifest), Ok)


if __name__ == "__main__":
    unittest.main()
