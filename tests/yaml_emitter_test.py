"""The emitter is the parser's inverse over the AART YAML subset.

`aart author init` (CP-26.8) writes `aart.yaml`. Zero runtime dependencies means AART emits that
document itself, and a hand-written emitter is only trustworthy if it cannot produce a document
that reads back as something else -- a string `"true"` that returns as a boolean, a value that a
`#` turns into a comment, a sequence item that reads as a mapping. So the claim held here is
round-trip: whatever `emit_yaml` writes, `parse_yaml` returns unchanged.

The claim is universal over the subset, so it is stated as a property over generated documents
rather than over a handful of examples. The example-based tests below cover the specific shapes
`aart.yaml` uses and the refusals the emitter owes its caller.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.protocol.json import JsonArray, JsonObject, JsonValue
from agent_artifacts.protocol.yaml import emit_yaml, parse_yaml

_KEYS = st.from_regex(r"[A-Za-z][A-Za-z0-9_-]{0,8}", fullmatch=True)
_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**63), max_value=2**63 - 1),
    st.text(max_size=12),
)


def _documents() -> st.SearchStrategy[JsonValue]:
    def extend(children: st.SearchStrategy[JsonValue]) -> st.SearchStrategy[JsonValue]:
        return st.one_of(
            st.lists(children, min_size=1, max_size=3).map(lambda items: JsonArray(tuple(items))),
            st.dictionaries(_KEYS, children, min_size=1, max_size=3).map(
                lambda entries: JsonObject(tuple(entries.items()))
            ),
        )

    return extend(st.recursive(_SCALARS, extend, max_leaves=6))


def _emitted(value: JsonValue, **kwargs: object) -> str:
    result = emit_yaml(value, **kwargs)  # type: ignore[arg-type]
    assert isinstance(result, Ok), result
    return result.value


def _reparsed(text: str) -> JsonValue:
    result = parse_yaml(text)
    assert isinstance(result, Ok), f"{result}\n---\n{text}"
    return result.value


def _refusal(result: object) -> str:
    assert isinstance(result, Err), f"expected a refusal, got {result}"
    return " ".join(diagnostic.message for diagnostic in result.diagnostics)


class RoundTripTest(unittest.TestCase):
    @given(_documents())
    @settings(max_examples=250, suppress_health_check=(HealthCheck.differing_executors,))
    def test_every_emitted_document_parses_back_to_the_value_it_came_from(
        self, value: JsonValue
    ) -> None:
        self.assertEqual(_reparsed(_emitted(value)), value)

    @given(_documents())
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_emitting_is_deterministic_and_a_fixed_point(self, value: JsonValue) -> None:
        once = _emitted(value)

        self.assertEqual(_emitted(value), once)
        self.assertEqual(_emitted(_reparsed(once)), once)

    @given(st.text(max_size=12))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_a_string_never_comes_back_as_another_type(self, text: str) -> None:
        document = JsonObject((("value", text),))

        self.assertEqual(_reparsed(_emitted(document)), document)

    @given(st.text(max_size=12))
    @settings(suppress_health_check=(HealthCheck.differing_executors,))
    def test_a_string_is_a_sequence_item_and_not_a_mapping_or_a_comment(self, text: str) -> None:
        document = JsonObject((("values", JsonArray((text, "tail"))),))

        self.assertEqual(_reparsed(_emitted(document)), document)

    def test_every_character_python_ends_a_line_on_is_quoted(self) -> None:
        """`str.splitlines` breaks on more than `\n`, and the tokenizer inherits every one of them.

        The set is taken from `str.splitlines` rather than listed here, so a Python release that
        ends a line on one more character is caught instead of quietly splitting a scalar in two.
        Hypothesis found this hole once and did not find it again on the next run, which is why the
        rule is held by an exhaustive test and not by a search.
        """

        breaking = [
            chr(point) for point in range(0x20, 0x2100) if len(f"a{chr(point)}b".splitlines()) > 1
        ]

        self.assertTrue(breaking)
        for character in breaking:
            with self.subTest(codepoint=hex(ord(character))):
                document = JsonObject((("value", f"a{character}b"),))

                self.assertEqual(_reparsed(_emitted(document)), document)


class LayoutTest(unittest.TestCase):
    def test_nesting_indents_by_two_spaces_and_never_uses_a_tab(self) -> None:
        document = JsonObject((("artifact", JsonObject((("kind", "mcp"), ("name", "github")))),))

        self.assertEqual(_emitted(document), "artifact:\n  kind: mcp\n  name: github\n")

    def test_a_sequence_of_scalars_hangs_under_its_key(self) -> None:
        document = JsonObject((("include", JsonArray(("payload/**", "SETUP.md"))),))

        self.assertEqual(_emitted(document), "include:\n  - payload/**\n  - SETUP.md\n")

    def test_a_mapping_in_a_sequence_opens_on_the_marker_line(self) -> None:
        document = JsonObject(
            (("artifacts", JsonArray((JsonObject((("name", "review"), ("type", "skill"))),))),)
        )

        self.assertEqual(_emitted(document), "artifacts:\n  - name: review\n    type: skill\n")

    def test_a_mapping_whose_first_value_is_a_block_opens_below_the_marker(self) -> None:
        """`- key:` with a nested block is not in the grammar, so the marker stands alone."""

        item = JsonObject((("a", JsonArray(("x",))), ("b", "y")))
        document = JsonObject((("items", JsonArray((item,))),))

        emitted = _emitted(document)

        self.assertEqual(emitted, "items:\n  -\n    a:\n      - x\n    b: y\n")
        self.assertEqual(_reparsed(emitted), document)

    def test_a_document_ends_with_exactly_one_newline(self) -> None:
        emitted = _emitted(JsonObject((("kind", "mcp"),)))

        self.assertTrue(emitted.endswith("\n"))
        self.assertFalse(emitted.endswith("\n\n"))


class CommentTest(unittest.TestCase):
    _DOCUMENT = JsonObject((("artifact", JsonObject((("kind", "mcp"),))), ("schema", 1)))

    def test_a_header_comment_precedes_the_document(self) -> None:
        emitted = _emitted(self._DOCUMENT, comments={"": ("Generated by aart author init.",)})

        self.assertTrue(emitted.startswith("# Generated by aart author init.\nartifact:\n"))
        self.assertEqual(_reparsed(emitted), self._DOCUMENT)

    def test_a_key_comment_sits_above_its_key_at_the_key_indentation(self) -> None:
        emitted = _emitted(self._DOCUMENT, comments={"artifact.kind": ("What this artifact is.",)})

        self.assertIn("artifact:\n  # What this artifact is.\n  kind: mcp\n", emitted)
        self.assertEqual(_reparsed(emitted), self._DOCUMENT)

    def test_a_comment_reaches_a_key_inside_a_sequence(self) -> None:
        document = JsonObject((("items", JsonArray((JsonObject((("name", "a"),)),))),))

        emitted = _emitted(document, comments={"items.0.name": ("The artifact name.",)})

        self.assertIn("# The artifact name.", emitted)
        self.assertEqual(_reparsed(emitted), document)

    def test_a_comment_aimed_at_a_key_the_document_does_not_have_is_refused(self) -> None:
        message = _refusal(emit_yaml(self._DOCUMENT, comments={"artifact.absent": ("note",)}))

        self.assertIn("artifact.absent", message)
        self.assertIn("no such", message)

    def test_a_comment_line_that_would_break_out_of_its_comment_is_refused(self) -> None:
        message = _refusal(emit_yaml(self._DOCUMENT, comments={"schema": ("one\ntwo",)}))

        self.assertIn("newline", message)


class RefusalTest(unittest.TestCase):
    def test_an_empty_mapping_is_refused_because_the_grammar_cannot_express_it(self) -> None:
        message = _refusal(emit_yaml(JsonObject((("install", JsonObject(())),))))

        self.assertIn("install", message)
        self.assertIn("empty", message)

    def test_an_empty_sequence_is_refused_for_the_same_reason(self) -> None:
        message = _refusal(emit_yaml(JsonObject((("include", JsonArray(())),))))

        self.assertIn("include", message)
        self.assertIn("empty", message)

    def test_an_empty_document_is_refused(self) -> None:
        self.assertIn("empty", _refusal(emit_yaml(JsonObject(()))))

    def test_a_scalar_document_is_refused_because_the_parser_requires_a_block(self) -> None:
        self.assertIn("mapping or a sequence", _refusal(emit_yaml("just a string")))

    def test_a_key_the_parser_would_reject_is_refused_by_name(self) -> None:
        message = _refusal(emit_yaml(JsonObject((("not a key", "value"),))))

        self.assertIn("not a key", message)

    def test_an_integer_outside_the_protocol_range_is_refused(self) -> None:
        message = _refusal(emit_yaml(JsonObject((("size", 2**63),))))

        self.assertIn("size", message)
        self.assertIn("64-bit", message)


if __name__ == "__main__":
    unittest.main()
