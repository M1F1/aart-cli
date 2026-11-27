"""§218: aart-cli edits `opencode.jsonc` without losing what the person wrote in it (D-530).

The owner: OpenCode 2 started by a launcher reads `opencode.jsonc` whenever it exists, so aart-cli
writes there; the person's comments must survive, and what aart-cli adds says it is aart-cli's.
"""

from __future__ import annotations

import json
import unittest

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from aart_cli.domain.jsonc import JsoncError, has_comments, loads, rewrite

MARK = "managed by aart-cli: "


def _note(path, value):
    return f"{MARK}{path[-1]}" if path and path[0] == "mcp" and len(path) == 2 else None


def _owned(comment: str) -> bool:
    return comment.startswith(MARK)


SERVER = {"type": "local", "command": ["/home/a/.aart-cli/bin/github"]}

OPENCODE_EMPTY = '{\n  "$schema": "https://opencode.ai/config.json"\n}\n'

ANNOTATED = """// my opencode settings
{
  "$schema": "https://opencode.ai/config.json",
  /* the model I use */
  "model": "anthropic/claude", // keep this
  "mcp": {
    // my own server
    "mine": { "type": "remote", "url": "https://example.test/mcp" },
  },
}
"""


class ReadingTest(unittest.TestCase):
    def test_comments_and_trailing_commas_are_read_past(self) -> None:
        self.assertEqual(
            loads(ANNOTATED),
            {
                "$schema": "https://opencode.ai/config.json",
                "model": "anthropic/claude",
                "mcp": {"mine": {"type": "remote", "url": "https://example.test/mcp"}},
            },
        )
        self.assertTrue(has_comments(ANNOTATED))
        self.assertFalse(has_comments(OPENCODE_EMPTY))

    def test_comment_markers_inside_strings_are_text(self) -> None:
        self.assertEqual(
            loads('{"url": "http://x/*y*/", "c": "//"}'), {"url": "http://x/*y*/", "c": "//"}
        )

    def test_malformed_text_is_refused_with_where(self) -> None:
        for text in (
            '{"a": 1',
            '{"a" 1}',
            "{,}",
            '{"a": 1 "b": 2}',
            "/* open",
            "[1,,2]",
            '{"a": 1} x',
        ):
            with self.subTest(text=text), self.assertRaises(JsoncError):
                loads(text)
        with self.assertRaisesRegex(JsoncError, "line 2"):
            loads('{\n  "a": }')

    def test_text_with_no_value_is_refused_by_loads(self) -> None:
        with self.assertRaises(JsoncError):
            loads("  // nothing here\n")


class RewritingTest(unittest.TestCase):
    def test_a_server_added_to_opencodes_own_file_is_laid_out_and_marked(self) -> None:
        written = rewrite(
            OPENCODE_EMPTY,
            {"$schema": "https://opencode.ai/config.json", "mcp": {"github": SERVER}},
            annotate=_note,
        )
        self.assertEqual(
            written,
            "{\n"
            '  "$schema": "https://opencode.ai/config.json",\n'
            '  "mcp": {\n'
            "    // managed by aart-cli: github\n"
            '    "github": {\n'
            '      "type": "local",\n'
            '      "command": [\n'
            '        "/home/a/.aart-cli/bin/github"\n'
            "      ]\n"
            "    }\n"
            "  }\n"
            "}\n",
        )

    def test_every_comment_survives_an_addition(self) -> None:
        document = loads(ANNOTATED)
        document["mcp"]["github"] = SERVER
        written = rewrite(ANNOTATED, document, annotate=_note)
        for comment in (
            "// my opencode settings",
            "/* the model I use */",
            "// keep this",
            "// my own server",
        ):
            self.assertIn(comment, written)
        self.assertIn("// managed by aart-cli: github", written)
        self.assertEqual(loads(written), document)
        # What was there is still there, byte for byte, up to the addition.
        self.assertTrue(written.startswith(ANNOTATED.split('"url"')[0]))

    def test_removing_a_server_takes_its_marker_and_nothing_else(self) -> None:
        document = loads(ANNOTATED)
        document["mcp"]["github"] = SERVER
        added = rewrite(ANNOTATED, document, annotate=_note)
        del document["mcp"]["github"]
        removed = rewrite(added, document, annotate=_note, owned=_owned)
        self.assertNotIn("aart-cli", removed)
        self.assertEqual(loads(removed), loads(ANNOTATED))
        for comment in (
            "// my opencode settings",
            "/* the model I use */",
            "// keep this",
            "// my own server",
        ):
            self.assertIn(comment, removed)

    def test_a_persons_comment_above_a_removed_member_stays(self) -> None:
        text = '{\n  "mcp": {\n    // my own server\n    "mine": 1,\n    "other": 2\n  }\n}\n'
        written = rewrite(text, {"mcp": {"other": 2}}, owned=_owned)
        self.assertIn("// my own server", written)
        self.assertEqual(loads(written), {"mcp": {"other": 2}})

    def test_an_unchanged_document_is_the_same_bytes(self) -> None:
        self.assertEqual(rewrite(ANNOTATED, loads(ANNOTATED)), ANNOTATED)

    def test_a_changed_value_keeps_its_marker(self) -> None:
        start = rewrite(
            OPENCODE_EMPTY, {**loads(OPENCODE_EMPTY), "mcp": {"github": SERVER}}, annotate=_note
        )
        moved = {**SERVER, "command": ["/elsewhere/github"]}
        written = rewrite(
            start, {**loads(OPENCODE_EMPTY), "mcp": {"github": moved}}, annotate=_note
        )
        self.assertEqual(written.count("managed by aart-cli: github"), 1)
        self.assertIn("/elsewhere/github", written)

    def test_plugin_items_are_appended_and_removed_with_their_marker(self) -> None:
        text = '{\n  "plugin": [\n    "./mine" // my plugin\n  ]\n}\n'
        added = rewrite(
            text,
            {"plugin": ["./mine", "./aart-cli/x"]},
            annotate=lambda path, value: f"{MARK}x" if path[0] == "plugin" else None,
        )
        self.assertEqual(
            added,
            '{\n  "plugin": [\n    "./mine", // my plugin\n    // managed by aart-cli: x\n'
            '    "./aart-cli/x"\n  ]\n}\n',
        )
        self.assertEqual(
            rewrite(added, {"plugin": ["./mine"]}, owned=_owned),
            '{\n  "plugin": [\n    "./mine" // my plugin\n  ]\n}\n',
        )

    def test_a_trailing_comma_stays_a_trailing_comma(self) -> None:
        text = '{\n  "a": 1,\n}\n'
        written = rewrite(text, {"a": 1, "b": 2})
        self.assertEqual(written, '{\n  "a": 1,\n  "b": 2,\n}\n')

    def test_tabs_are_kept_as_the_files_indent(self) -> None:
        written = rewrite('{\n\t"a": 1\n}\n', {"a": 1, "b": {"c": 2}})
        self.assertEqual(written, '{\n\t"a": 1,\n\t"b": {\n\t\t"c": 2\n\t}\n}\n')

    def test_empty_and_comment_only_text_get_the_document(self) -> None:
        self.assertEqual(rewrite("", {"a": 1}), '{\n  "a": 1\n}\n')
        self.assertEqual(rewrite("// keep\n", {"a": 1}), '// keep\n{\n  "a": 1\n}\n')

    def test_an_empty_object_opens_up(self) -> None:
        self.assertEqual(rewrite('{"mcp": {}}', {"mcp": {"a": 1}}), '{"mcp": {\n  "a": 1\n}}')
        self.assertEqual(rewrite("{\n}\n", {"a": 1}), '{\n  "a": 1\n}\n')

    def test_each_edit_lands_exactly_where_a_person_would_put_it(self) -> None:
        cases = (
            # A comment on the opening line stays there; the addition goes under it.
            ("{ // settings\n}\n", {"a": 1}, '{ // settings\n  "a": 1\n}\n'),
            (
                '{ // settings\n  "b": 2\n}\n',
                {"b": 2, "a": 1},
                '{ // settings\n  "b": 2,\n  "a": 1\n}\n',
            ),
            # A removed entry takes the comment on its own line with it, and nothing else.
            ('[\n  "a", // first\n  "b"\n]\n', ["b"], '[\n  "b"\n]\n'),
            ('[\n  "a",\n  "b" // last\n]\n', ["a"], '[\n  "a"\n]\n'),
            # An addition after an entry with a comment goes after that comment, not into it.
            (
                '[\n  "a", // first\n  "b"\n]\n',
                ["a", "b", "c"],
                '[\n  "a", // first\n  "b",\n  "c"\n]\n',
            ),
            ('{\n  "a": 1 // one\n}\n', {"a": 1, "b": 2}, '{\n  "a": 1, // one\n  "b": 2\n}\n'),
            (
                '{\n\t"a": 1\n}\n',
                {"a": 1, "b": {"c": 2}},
                '{\n\t"a": 1,\n\t"b": {\n\t\t"c": 2\n\t}\n}\n',
            ),
            (
                '{\n  "x": [\n    "a",\n    "b"\n  ]\n}\n',
                {"x": ["a"]},
                '{\n  "x": [\n    "a"\n  ]\n}\n',
            ),
            (
                '{\n  "x": [\n    "a",\n    "b",\n  ]\n}\n',
                {"x": ["b"]},
                '{\n  "x": [\n    "b",\n  ]\n}\n',
            ),
        )
        for text, document, expected in cases:
            with self.subTest(text=text, document=document):
                self.assertEqual(expected, rewrite(text, document))

    def test_text_outside_ascii_is_written_as_itself(self) -> None:
        self.assertEqual(
            '{\n  "a": 1,\n  "opis": "zażółć"\n}\n',
            rewrite('{\n  "a": 1\n}\n', {"a": 1, "opis": "zażółć"}),
        )
        self.assertEqual('["zażółć"]', rewrite('["x", "y"]', ["zażółć"]))

    def test_the_same_members_in_another_order_change_nothing(self) -> None:
        text = '{\n  "m": {"a": 1, "b": 2},\n  "z": 0\n}\n'

        self.assertEqual(text, rewrite(text, {"z": 0, "m": {"b": 2, "a": 1}}))

    def test_a_member_written_twice_is_left_alone_unless_it_is_the_one_changed(self) -> None:
        text = '{\n  "a": 1,\n  "a": 2,\n  "b": 3\n}\n'

        self.assertEqual('{\n  "a": 1,\n  "a": 2,\n  "b": 4\n}\n', rewrite(text, {"a": 2, "b": 4}))
        with self.assertRaisesRegex(JsoncError, "'a' is written more than once"):
            rewrite(text, {"a": 5, "b": 3})

    def test_a_container_emptied_of_everything_closes_up(self) -> None:
        text = '{\n  "plugin": [\n    // managed by aart-cli: x\n    "./aart-cli/x"\n  ]\n}\n'

        self.assertEqual('{\n  "plugin": []\n}\n', rewrite(text, {"plugin": []}, owned=_owned))
        kept = '{\n  "plugin": [\n    // mine\n    "a"\n  ]\n}\n'
        self.assertEqual('{\n  "plugin": [\n    // mine\n  ]\n}\n', rewrite(kept, {"plugin": []}))

    def test_a_one_line_value_rewritten_whole_stays_on_one_line(self) -> None:
        self.assertEqual(
            rewrite('{"plugin": ["mine", "x"]}', {"plugin": ["mine"]}), '{"plugin": ["mine"]}'
        )
        self.assertEqual(
            rewrite('{"u": ["https://a"]}', {"u": ["https://b", "c"]}), '{"u": ["https://b", "c"]}'
        )

    def test_a_container_holding_comments_is_never_rewritten_whole(self) -> None:
        with self.assertRaises(JsoncError):
            rewrite('{"mcp": {"a": 1 /* mine */}}', {"mcp": {"a": 1, "b": 2}})
        with self.assertRaises(JsoncError):
            rewrite('{\n  "mcp": [ /* mine */ ]\n}', {"mcp": {}})

    def test_a_duplicated_member_is_not_guessed_at(self) -> None:
        with self.assertRaises(JsoncError):
            rewrite('{\n  "a": 1,\n  "a": 2\n}', {"a": 3})

    def test_a_document_that_is_not_json_is_refused(self) -> None:
        with self.assertRaises(JsoncError):
            rewrite("{}", {"a": float("nan")})


# -- properties ------------------------------------------------------------------------------

_KEYS = st.text(alphabet="abcdefgh-$_", min_size=1, max_size=4)
_SCALARS = st.one_of(
    st.none(), st.booleans(), st.integers(-1000, 1000), st.text(alphabet='ab /*"\\é', max_size=5)
)
_VALUES = st.recursive(
    _SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=4), st.dictionaries(_KEYS, children, max_size=4)
    ),
    max_leaves=12,
)
_DOCUMENTS = st.dictionaries(_KEYS, _VALUES, max_size=5)


def _annotated(document: dict, comments: list[bool], indent: int) -> str:
    """`document` as a person might keep it: indented, with whole-line comments between lines."""

    lines = json.dumps(document, indent=indent, ensure_ascii=False).split("\n")
    out = []
    for index, line in enumerate(lines):
        if index and index < len(comments) and comments[index]:
            out.append(f"{' ' * (len(line) - len(line.lstrip()))}// note {index}")
        out.append(line)
    return "\n".join(out) + "\n"


@st.composite
def _edited(draw):
    document = draw(_DOCUMENTS)
    edited = json.loads(json.dumps(document))
    for _ in range(draw(st.integers(1, 3))):
        containers = [edited]
        stack = [edited]
        while stack:
            current = stack.pop()
            children = current.values() if isinstance(current, dict) else current
            for child in children:
                if isinstance(child, (dict, list)):
                    containers.append(child)
                    stack.append(child)
        target = draw(st.sampled_from(containers))
        action = draw(st.sampled_from(["add", "remove", "change"]))
        if isinstance(target, dict):
            if action == "add" or not target:
                target[draw(_KEYS)] = draw(_VALUES)
            elif action == "remove":
                del target[draw(st.sampled_from(sorted(target)))]
            else:
                target[draw(st.sampled_from(sorted(target)))] = draw(_SCALARS)
        else:
            if action == "add" or not target:
                target.append(draw(_VALUES))
            elif action == "remove":
                del target[draw(st.integers(0, len(target) - 1))]
            else:
                target[draw(st.integers(0, len(target) - 1))] = draw(_SCALARS)
    return document, edited


# `differing_executors` is suppressed for the reason `doctor_properties_test` records: the scoped
# `make mutants` run re-runs the same test method object from a fresh runner per mutant.
_MUTATION = (HealthCheck.differing_executors,)


class RewriteProperties(unittest.TestCase):
    @settings(max_examples=400, deadline=None, suppress_health_check=_MUTATION)
    @given(_edited(), st.lists(st.booleans(), max_size=60), st.sampled_from([2, 4]))
    def test_a_rewrite_says_exactly_the_new_document_or_refuses(
        self, pair, comments, indent
    ) -> None:
        before, after = pair
        text = _annotated(before, comments, indent)
        try:
            written = rewrite(text, after)
        except JsoncError:
            # Refused only to keep a comment a whole-container rewrite would have lost.
            self.assertTrue(has_comments(text))
            return
        self.assertEqual(
            json.dumps(loads(written), sort_keys=True), json.dumps(after, sort_keys=True)
        )

    @settings(max_examples=300, deadline=None, suppress_health_check=_MUTATION)
    @given(_DOCUMENTS, _KEYS, _VALUES, st.lists(st.booleans(), max_size=60))
    def test_adding_a_member_keeps_every_comment(self, document, key, value, comments) -> None:
        assume(key not in document)
        text = _annotated(document, comments, 2)
        after = {**document, key: value}
        written = rewrite(text, after)
        kept = [line.strip() for line in text.splitlines() if line.strip().startswith("//")]
        for comment in kept:
            self.assertIn(comment, written)
        self.assertEqual(
            json.dumps(loads(written), sort_keys=True), json.dumps(after, sort_keys=True)
        )

    @settings(max_examples=200, deadline=None, suppress_health_check=_MUTATION)
    @given(_DOCUMENTS, st.lists(st.booleans(), max_size=60))
    def test_an_unchanged_document_is_never_touched(self, document, comments) -> None:
        text = _annotated(document, comments, 2)
        self.assertEqual(rewrite(text, json.loads(json.dumps(document))), text)

    @settings(max_examples=200, deadline=None, suppress_health_check=_MUTATION)
    @given(_DOCUMENTS, _KEYS, st.lists(st.booleans(), max_size=60))
    def test_add_then_remove_a_marked_member_restores_the_meaning(
        self, document, key, comments
    ) -> None:
        text = _annotated({k: v for k, v in document.items() if k != "mcp"}, comments, 2)
        base = loads(text) if text.strip() else {}
        mcp = dict(base.get("mcp", {})) if isinstance(base.get("mcp"), dict) else {}
        added_doc = {**base, "mcp": {**mcp, key: SERVER}}
        added = rewrite(text, added_doc, annotate=_note)
        self.assertEqual(added.count(MARK), 1)
        removed = rewrite(added, {**base, "mcp": mcp}, owned=_owned)
        self.assertNotIn(MARK, removed)
        for line in text.splitlines():
            if line.strip().startswith("//"):
                self.assertIn(line.strip(), removed)


if __name__ == "__main__":
    unittest.main()
