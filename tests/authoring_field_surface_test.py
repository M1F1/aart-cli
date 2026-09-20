"""The CP-26.6 oracle derives the authoring field surface from the parser's own source.

Steps 7 to 12 generate `aart-cli.yaml`. A generator that transcribes the accepted field names goes
stale the moment the parser gains one, and nothing fails. So the field surface is collected from
`protocol/authoring.py` by reading it, and these tests hold the collector to the two properties a
generator oracle has to have: it reaches *every* site where the parser accepts fields, and it never
reports a field set it could not actually resolve.
"""

from __future__ import annotations

import ast
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.authoring_field_surface import (
    AUTHORING_PARSER,
    accepted_fields,
    field_helpers,
    parser_field_surface,
)

_SOURCE = AUTHORING_PARSER.read_text(encoding="utf-8")


def _naive_call_sites(source: str) -> int:
    """The specification of "every site": every call to a field helper from outside one.

    Deliberately simpler than the collector, and written from the rule rather than from it: a
    helper's own body configures the helper, every other call is a place the parser accepts
    fields.
    """

    tree = ast.parse(source)
    helpers = set(field_helpers(source))
    internal = {
        node
        for definition in ast.walk(tree)
        if isinstance(definition, ast.FunctionDef) and definition.name in helpers
        for node in ast.walk(definition)
    }
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and node not in internal
        and (node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", ""))
        in helpers
    )


class FieldHelperDiscoveryTest(unittest.TestCase):
    """Which functions accept fields is read from their signatures, never listed here."""

    def test_a_function_taking_a_field_keyword_is_a_helper(self) -> None:
        source = "def take(value, *, required, path):\n    return value\n"

        self.assertIn("take", field_helpers(source))

    def test_a_function_taking_neither_field_keyword_is_not_a_helper(self) -> None:
        source = "def plain(value, *, path):\n    return value\n"

        self.assertEqual(field_helpers(source), {})

    def test_a_helper_inherits_the_fields_its_own_body_always_demands(self) -> None:
        source = (
            "def base(value, *, required, optional=frozenset(), path):\n"
            "    return value\n"
            "def wrapper(value, label, *, optional=frozenset(), path):\n"
            "    return base(value, required=frozenset({'type'}), optional=optional, path=path)\n"
        )

        self.assertEqual(field_helpers(source)["wrapper"], (("type",), ()))


class ParserSurfaceTest(unittest.TestCase):
    def test_every_field_helper_call_in_the_parser_reaches_the_surface(self) -> None:
        self.assertEqual(len(parser_field_surface()), _naive_call_sites(_SOURCE))

    def test_a_call_that_passes_no_field_keyword_still_carries_the_helper_requirement(self) -> None:
        """`_nested_type(value, "transport", path=path)` accepts `type`, and the surface says so."""

        bare = [
            item
            for item in parser_field_surface()
            if not item.unresolved and not item.required and not item.optional
        ]

        self.assertEqual(bare, [], f"a resolved call site accepts no field at all: {bare}")

    def test_the_top_level_author_manifest_group_is_the_specified_one(self) -> None:
        top = {item.label: item for item in parser_field_surface()}["author manifest"]

        self.assertEqual(top.required, ("artifact", "payload", "schema"))
        self.assertIn("inputs", top.optional)
        self.assertEqual(top.unresolved, ())


class UnresolvedSiteTest(unittest.TestCase):
    """A field set the collector cannot read is reported, never reported as empty."""

    _BASE = "def base(value, *, required, optional=frozenset(), path):\n    return value\n"

    def test_a_computed_field_set_is_marked_unresolved(self) -> None:
        source = self._BASE + (
            "def parse(value, required, path):\n"
            "    return base(value, required=required, path=path, label='thing')\n"
        )

        (site,) = [item for item in accepted_fields(source) if item.owner == "parse"]

        self.assertEqual(site.unresolved, ("required",))
        self.assertEqual(site.required, ())

    def test_a_computed_label_is_marked_unresolved_and_left_unnamed(self) -> None:
        source = self._BASE + (
            "def parse(value, kind, path):\n"
            "    return base(value, required=frozenset({'id'}), path=path, label=f'{kind} thing')\n"
        )

        (site,) = [item for item in accepted_fields(source) if item.owner == "parse"]

        self.assertIsNone(site.label)
        self.assertEqual(site.unresolved, ("label",))
        self.assertEqual(site.required, ("id",))

    def test_a_computed_set_still_reports_the_names_it_could_read(self) -> None:
        """Unresolved means "maybe more", not "none" -- the visible names still have to come out."""

        source = self._BASE + (
            "def parse(value, extra, path):\n"
            "    return base(value, required=frozenset({'type'} | extra), path=path, label='t')\n"
        )

        (site,) = [item for item in accepted_fields(source) if item.owner == "parse"]

        self.assertEqual(site.required, ("type",))
        self.assertEqual(site.unresolved, ("required",))

    def test_a_field_set_assigned_in_branches_is_read_from_those_branches(self) -> None:
        """`required = frozenset({...})` in one branch or another is where the names actually are."""

        source = self._BASE + (
            "def parse(value, kind, path):\n"
            "    if kind == 'a':\n"
            "        required = frozenset({'type', 'path'})\n"
            "    else:\n"
            "        required = frozenset({'type', 'pyproject', 'lock'})\n"
            "    return base(value, required=required, path=path, label='t')\n"
        )

        (site,) = [item for item in accepted_fields(source) if item.owner == "parse"]

        self.assertEqual(site.required, ("lock", "path", "pyproject", "type"))
        self.assertEqual(site.unresolved, ("required",))

    def test_the_parser_input_and_dependency_names_are_not_lost_to_a_computed_set(self) -> None:
        """The two sites CP-26.8 would otherwise generate a skeleton without."""

        names = {
            name for item in parser_field_surface() for name in (*item.required, *item.optional)
        }

        self.assertLessEqual({"required", "help", "default", "validation"}, names)
        self.assertLessEqual({"pyproject", "lock", "path"}, names)

    def test_every_unresolved_parser_site_names_what_could_not_be_read(self) -> None:
        for item in parser_field_surface():
            with self.subTest(owner=item.owner, label=item.label):
                self.assertEqual(item.label is None, "label" in item.unresolved)


class CollectedNameTest(unittest.TestCase):
    _BASE = UnresolvedSiteTest._BASE

    @given(st.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_every_new_literal_optional_field_is_collected(self, name: str) -> None:
        source = self._BASE + (
            "def parse(value, path):\n"
            "    return base(value, required=frozenset({'id'}), "
            f"optional=frozenset({{{name!r}}}), path=path, label='thing')\n"
        )

        (site,) = [item for item in accepted_fields(source) if item.owner == "parse"]

        self.assertEqual(site.optional, (name,))

    def test_a_string_that_is_not_a_field_keyword_does_not_enter_the_surface(self) -> None:
        source = self._BASE + (
            "def parse(value, path):\n"
            "    return base(value, required=frozenset({'id'}), path=path, "
            "label='not-a-field', message='not-a-field-either')\n"
        )

        (site,) = [item for item in accepted_fields(source) if item.owner == "parse"]

        self.assertEqual((site.required, site.optional), (("id",), ()))


if __name__ == "__main__":
    unittest.main()
