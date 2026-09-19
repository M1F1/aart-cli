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
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.authoring import (
    DiscoveredAuthorManifest,
    compile_author_snapshot,
    parse_author_manifest,
)
from agent_artifacts.protocol.paths import parse_relative_path
from agent_artifacts.protocol.yaml import emit_yaml, parse_yaml
from tests.authoring_compiler_test import _file, _snapshot
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


class CompilationTest(unittest.TestCase):
    """What an author runs next is a compile, so the skeleton is held to compiling."""

    def _compiled(self):
        skeleton = _skeleton()
        files = [_file(f"{_NAME}/aart.yaml", skeleton.manifest.encode())]
        files.extend(
            _file(f"{_NAME}/{path}", content.encode()) for path, content in skeleton.payload
        )
        compiled = compile_author_snapshot(
            _snapshot(*files),
            source_alias=SourceAlias("example"),
            source="https://example.invalid/skeleton.git",
            revision="a" * 40,
        )
        assert isinstance(compiled, Ok), getattr(compiled, "diagnostics", ())
        self.assertEqual(len(compiled.value), 1)
        return compiled.value[0]

    def test_the_generated_workspace_compiles_to_one_canonical_package(self) -> None:
        self.assertEqual(str(self._compiled().package.coordinate.artifact.name), _NAME)

    def test_the_payload_arrives_under_its_own_names_and_not_a_second_time(self) -> None:
        """A `payload/` written into the manifest lands as `payload/payload/`, and compiles.

        The compiler puts the author's files under the package's payload directory itself, so the
        paths in `aart.yaml` are relative to the manifest. Nothing refuses the doubled form, which
        is exactly why this is asserted rather than left to a gate.
        """

        entries = {str(entry.path) for entry in self._compiled().canonical_entries}

        for path, _ in _skeleton().payload:
            self.assertIn(f"payload/{path}", entries)
        self.assertEqual([entry for entry in entries if "payload/payload/" in entry], [])


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
        """A written file the manifest does not name is not part of the artifact."""

        skeleton = _skeleton()
        parsed = _parsed(skeleton.manifest)
        assert isinstance(parsed, Ok), parsed

        self.assertTrue(skeleton.payload)
        self.assertEqual(
            sorted(path for path, _content in skeleton.payload), sorted(parsed.value.includes)
        )

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
