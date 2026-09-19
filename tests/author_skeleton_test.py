"""`aart-cli author init` writes a skeleton the parser accepts and no field it forgot.

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
from typing import get_args

from aart_cli.authoring.skeleton import (
    ALTERNATIVE_PREFIX,
    COMMENTED_YAML_PREFIX,
    GENERATED_KINDS,
    PROSE_PREFIX,
    author_skeleton,
)
from aart_cli.domain.artifacts import ArtifactKind
from aart_cli.domain.identifiers import SourceAlias
from aart_cli.domain.result import Err, Ok
from aart_cli.protocol.authoring import (
    AuthorKind,
    DiscoveredAuthorManifest,
    compile_author_snapshot,
    package_hook,
    parse_author_manifest,
)
from aart_cli.protocol.paths import parse_relative_path
from aart_cli.protocol.yaml import _plain_safe, emit_yaml, parse_yaml
from tests.authoring_compiler_test import _file, _snapshot
from tests.authoring_field_surface import parser_field_surface

_NAME = "github-mcp"

#: A plausible name per generated kind, so each skeleton is read the way an author would get it.
_NAMES: dict[str, str] = {
    "guideline": "commit-style",
    "hook": "guard-bash",
    "mcp": _NAME,
    "memory": "team-context",
    "skill": "code-review",
}


def _name_for(kind: str) -> str:
    return _NAMES[kind]


def _skeleton(kind: str = "mcp", name: str | None = None):
    result = author_skeleton(kind, _name_for(kind) if name is None else name)
    assert isinstance(result, Ok), result
    return result.value


def _every():
    """Every kind this build generates, so a claim is made about all of them or about none."""

    return tuple((kind, _skeleton(kind)) for kind in GENERATED_KINDS)


def _parsed(text: str):
    path = parse_relative_path("aart-cli.yaml")
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
        for kind, skeleton in _every():
            with self.subTest(kind=kind):
                self.assertIsInstance(_parsed(skeleton.manifest), Ok)

    def test_the_same_document_with_every_optional_block_live_parses_too(self) -> None:
        for kind, skeleton in _every():
            with self.subTest(kind=kind):
                emitted = emit_yaml(skeleton.full)
                assert isinstance(emitted, Ok), emitted

                self.assertIsInstance(_parsed(emitted.value), Ok)

    def test_uncommenting_the_skeleton_yields_exactly_that_document(self) -> None:
        """The commented text is the live document, not prose that resembles it."""

        for kind, skeleton in _every():
            with self.subTest(kind=kind):
                emitted = emit_yaml(skeleton.full)
                assert isinstance(emitted, Ok), emitted

                self.assertEqual(
                    parse_yaml(_uncommented(skeleton.manifest)),
                    parse_yaml(emitted.value),
                )

    def test_the_required_only_document_is_what_the_skeleton_parses_to(self) -> None:
        for kind, skeleton in _every():
            with self.subTest(kind=kind):
                self.assertEqual(parse_yaml(skeleton.manifest), Ok(skeleton.live))


class CompilationTest(unittest.TestCase):
    """What an author runs next is a compile, so the skeleton is held to compiling."""

    def _compiled(self, kind: str = "mcp"):
        skeleton = _skeleton(kind)
        root = skeleton.name
        files = [_file(f"{root}/aart-cli.yaml", skeleton.manifest.encode())]
        files.extend(
            _file(f"{root}/{file.path}", file.content.encode(), executable=file.executable)
            for file in skeleton.payload
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
        for kind in GENERATED_KINDS:
            with self.subTest(kind=kind):
                compiled = self._compiled(kind)

                self.assertEqual(str(compiled.package.coordinate.artifact.name), _name_for(kind))
                self.assertEqual(compiled.package.coordinate.artifact.kind, kind)

    def test_the_payload_arrives_under_its_own_names_and_not_a_second_time(self) -> None:
        """A `payload/` written into the manifest lands as `payload/payload/`, and compiles.

        The compiler puts the author's files under the package's payload directory itself, so the
        paths in `aart-cli.yaml` are relative to the manifest. Nothing refuses the doubled form, which
        is exactly why this is asserted rather than left to a gate.
        """

        for kind, skeleton in _every():
            with self.subTest(kind=kind):
                entries = {str(entry.path) for entry in self._compiled(kind).canonical_entries}

                for file in skeleton.payload:
                    self.assertIn(f"payload/{file.path}", entries)
                self.assertEqual([e for e in entries if "payload/payload/" in e], [])


class AntiDriftTest(unittest.TestCase):
    """The oracle of CP-26.6 §1.5: the parser decides what the skeleton must carry."""

    def test_every_field_name_the_parser_accepts_appears_as_a_key(self) -> None:
        for kind, skeleton in _every():
            missing = sorted(
                name
                for site in parser_field_surface()
                # A collection manifest is a different document with a different generator; step
                # 12 gives it its own skeleton and its own half of this oracle.
                if site.owner != "parse_author_collection_manifest"
                for name in (*site.required, *site.optional)
                if name not in _keys(skeleton.manifest)
            )

            with self.subTest(kind=kind):
                self.assertEqual(
                    missing, [], f"the parser accepts fields the skeleton never names: {missing}"
                )

    def test_an_unresolved_site_is_still_covered(self) -> None:
        """The three computed sites are where a skeleton silently loses fields."""

        for kind, skeleton in _every():
            for name in ("required", "help", "default", "validation", "pyproject", "lock"):
                with self.subTest(kind=kind, field=name):
                    self.assertIn(name, skeleton.manifest)


class AlternativeTest(unittest.TestCase):
    """An alternative is offered so it can be enabled, so it has to be enable-able."""

    def _alternatives(self, kind: str = "mcp") -> tuple[str, ...]:
        return tuple(
            line.strip()[len(ALTERNATIVE_PREFIX) :]
            for line in _skeleton(kind).manifest.splitlines()
            if line.strip().startswith(ALTERNATIVE_PREFIX)
        )

    def test_the_skeleton_offers_alternatives_at_all(self) -> None:
        for kind in GENERATED_KINDS:
            with self.subTest(kind=kind):
                self.assertTrue(self._alternatives(kind))

    def test_no_alternative_uses_a_construct_this_yaml_subset_cannot_read(self) -> None:
        """Flow mappings and sequences parse in YAML at large and are refused here."""

        for kind in GENERATED_KINDS:
            for line in self._alternatives(kind):
                with self.subTest(kind=kind, line=line):
                    value = line.split(":", 1)[1].strip() if ":" in line else ""

                    self.assertFalse(value.startswith(("{", "[", "&", "*", "!", "|", ">")), line)

    def test_every_alternative_is_a_mapping_entry_or_a_sequence_item(self) -> None:
        for kind in GENERATED_KINDS:
            for line in self._alternatives(kind):
                with self.subTest(kind=kind, line=line):
                    self.assertTrue(":" in line or line.strip().startswith("- "), line)

    def test_a_sequence_item_an_author_uncomments_is_quoted_when_it_has_to_be(self) -> None:
        """`- --once` reads as a reserved opening character and does not parse.

        The rule is the emitter's own: what `_plain_safe` would not write bare, an alternative
        written by hand has to carry quoted, or uncommenting it produces a refusal.
        """

        for kind in GENERATED_KINDS:
            for line in self._alternatives(kind):
                value = line.strip()
                if not value.startswith("- "):
                    continue
                value = value[2:].strip()
                with self.subTest(kind=kind, value=value):
                    self.assertTrue(value.startswith('"') or _plain_safe(value), value)


class ShapeTest(unittest.TestCase):
    def test_the_generator_is_deterministic(self) -> None:
        for kind in GENERATED_KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(_skeleton(kind).manifest, _skeleton(kind).manifest)

    def test_the_payload_skeleton_matches_what_the_manifest_includes(self) -> None:
        """A written file the manifest does not name is not part of the artifact."""

        for kind, skeleton in _every():
            with self.subTest(kind=kind):
                parsed = _parsed(skeleton.manifest)
                assert isinstance(parsed, Ok), parsed

                self.assertTrue(skeleton.payload)
                self.assertEqual(
                    sorted(file.path for file in skeleton.payload),
                    sorted(parsed.value.includes),
                )

    def test_the_manifest_declares_the_entrypoint_the_payload_provides(self) -> None:
        """An `mcp` launches; the claim is about the kinds that declare an entrypoint at all."""

        skeleton = _skeleton("mcp")
        parsed = _parsed(skeleton.manifest)
        assert isinstance(parsed, Ok), parsed

        self.assertIsNotNone(parsed.value.entrypoint)
        self.assertIn(str(parsed.value.entrypoint), [file.path for file in skeleton.payload])

    def test_the_skeleton_reports_the_kind_and_name_it_was_asked_for(self) -> None:
        """What the writer names its files and the command prints comes from these two fields.

        Found by mutation: either could be replaced with `None` and every other test still passed,
        because they all read the manifest text rather than the value carrying it.
        """

        for kind, skeleton in _every():
            with self.subTest(kind=kind):
                self.assertEqual(skeleton.kind, kind)
                self.assertEqual(skeleton.name, _name_for(kind))

    def test_the_name_the_caller_gave_is_the_artifact_name(self) -> None:
        parsed = _parsed(_skeleton(name="atlassian").manifest)
        assert isinstance(parsed, Ok), parsed

        self.assertEqual(parsed.value.name, "atlassian")


class SkillTest(unittest.TestCase):
    """A skill is delivered as a tree, which makes it a different document, not a smaller one."""

    def test_the_payload_carries_the_file_a_skill_package_requires(self) -> None:
        """`native_tree` refuses a skill package without `payload/SKILL.md`."""

        self.assertIn("SKILL.md", [file.path for file in _skeleton("skill").payload])

    def test_the_skill_markdown_is_not_empty(self) -> None:
        contents = {file.path: file.content for file in _skeleton("skill").payload}

        self.assertIn("#", contents["SKILL.md"])

    def test_no_launch_block_is_generated_for_a_tree_delivered_kind(self) -> None:
        """The parser accepts one; enabling it makes the package advertise a protocol it does
        not speak, so the generator does not write it live or into `full`."""

        skeleton = _skeleton("skill")

        for block in ("transport", "runtime", "launch"):
            with self.subTest(block=block):
                self.assertIsNone(skeleton.live.get(block))
                self.assertIsNone(skeleton.full.get(block))

    def test_the_blocks_it_does_not_generate_are_still_named(self) -> None:
        """Not generating a block is a choice; hiding that the parser accepts it is drift."""

        manifest = _skeleton("skill").manifest

        for block in ("transport", "runtime", "launch"):
            with self.subTest(block=block):
                self.assertIn(block, _keys(manifest))

    def test_a_skill_compiles_without_declaring_a_protocol(self) -> None:
        compiled = CompilationTest()._compiled("skill")

        self.assertIsNone(compiled.package.protocol)


class DocumentArtifactTest(unittest.TestCase):
    """Guidelines and memories are installed as one Markdown document."""

    def test_each_document_kind_carries_exactly_one_markdown_payload(self) -> None:
        for kind in ("guideline", "memory"):
            with self.subTest(kind=kind):
                payload = _skeleton(kind).payload

                self.assertEqual(len(payload), 1)
                self.assertTrue(payload[0].path.endswith(".md"))


class HookTest(unittest.TestCase):
    """The generated declaration and script form an installable hook package."""

    def test_the_generated_hook_is_accepted_by_the_install_time_reader(self) -> None:
        compiled = CompilationTest()._compiled("hook")

        packaged = package_hook(ArtifactKind.HOOK, compiled.canonical_entries)

        assert isinstance(packaged, Ok), packaged
        self.assertEqual(packaged.value.event, "PreToolUse")
        self.assertEqual(packaged.value.matcher, "Bash")
        self.assertEqual(packaged.value.command, "run.sh")


class RefusalTest(unittest.TestCase):
    def test_this_build_generates_every_kind_the_parser_accepts(self) -> None:
        """The refusal path is still reachable; there is simply no accepted kind left in it.

        `AuthorKind` is the parser's list, and a kind on it with no blueprint would be a `--kind`
        the CLI offers and the generator refuses.
        """

        self.assertEqual(GENERATED_KINDS, tuple(sorted(get_args(AuthorKind))))

    def test_a_kind_the_parser_does_not_know_is_refused(self) -> None:
        result = author_skeleton("plugin", _NAME)

        assert isinstance(result, Err), result
        self.assertIn("plugin", result.diagnostics[0].message)

    def test_the_refusal_names_the_kinds_this_build_does_generate(self) -> None:
        """Naming the kind that failed without naming the alternatives is half an answer.

        Found by mutation: the list could be replaced with `None` and nothing noticed, because the
        only assertion on this message was about the rejected kind.
        """

        result = author_skeleton("plugin", _NAME)

        assert isinstance(result, Err), result
        for kind in GENERATED_KINDS:
            with self.subTest(kind=kind):
                self.assertIn(kind, result.diagnostics[0].message)

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
