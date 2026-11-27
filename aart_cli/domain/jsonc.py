"""JSON with comments, read and edited without losing what a person wrote in it (§218, D-530).

OpenCode reads `opencode.jsonc` -- JSON that may carry `//` and `/* */` comments and a comma after
the last member -- and an OpenCode 2 started by a launcher reads that file instead of
`opencode.json` whenever it exists. aart-cli has to write its MCP servers and plugins there, into a
file the person owns and may have annotated.

So this is an editor, not a serializer. `rewrite` takes the text as it stands and the document it
should now describe, and changes only the members and items that differ: everything else -- the
person's comments, ordering, indentation, blank lines and trailing commas -- is the same bytes
afterwards. What it inserts is laid out like its neighbours and, when asked, carries one line
comment saying aart-cli manages it; removing a member takes that comment with it and nothing else.

Two promises hold for every edit, and the second is checked rather than assumed: no comment outside
a removed member is lost, and the text written parses back to exactly the document asked for. An
edit that cannot keep the first -- replacing a container whose own text holds comments, say -- is
refused with `JsoncError` rather than approximated.

Pure: text in, text out. Reading and writing the file is the caller's.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

__all__ = ["JsoncError", "document", "has_comments", "loads", "rewrite"]

_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
_LITERALS = {"true": True, "false": False, "null": None}
_WHITESPACE = " \t\r\n"
_BOM = "﻿"

#: Where a member or item sits: object keys and array indices from the document root.
Path = tuple[str | int, ...]


class JsoncError(ValueError):
    """The text is not JSONC, or this edit cannot be made without losing what is in it."""


@dataclass(frozen=True, slots=True)
class _Node:
    kind: str  # "object", "array" or "scalar"
    start: int
    end: int
    value: object = None
    members: tuple[_Entry, ...] = ()
    duplicates: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class _Entry:
    """One object member or array item: where it starts, its value, and the comma after it."""

    start: int
    value: _Node
    comma: int | None
    key: str | None = None


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 1 if text.startswith(_BOM) else 0
        self.comments: list[tuple[int, int]] = []

    def fail(self, message: str) -> JsoncError:
        line = self.text.count("\n", 0, self.pos) + 1
        column = self.pos - (self.text.rfind("\n", 0, self.pos) + 1) + 1
        return JsoncError(f"{message} at line {line} column {column}")

    def skip(self) -> None:
        text, length = self.text, len(self.text)
        while self.pos < length:
            character = text[self.pos]
            if character in _WHITESPACE:
                self.pos += 1
            elif text.startswith("//", self.pos):
                end = text.find("\n", self.pos)
                end = length if end < 0 else end
                self.comments.append((self.pos, end))
                self.pos = end
            elif text.startswith("/*", self.pos):
                end = text.find("*/", self.pos + 2)
                if end < 0:
                    raise self.fail("unterminated comment")
                self.comments.append((self.pos, end + 2))
                self.pos = end + 2
            else:
                return

    def document(self) -> _Node | None:
        self.skip()
        if self.pos >= len(self.text):
            return None
        root = self.value()
        self.skip()
        if self.pos < len(self.text):
            raise self.fail("unexpected text after the document")
        return root

    def value(self) -> _Node:
        self.skip()
        if self.pos >= len(self.text):
            raise self.fail("unexpected end of text")
        character = self.text[self.pos]
        if character == "{":
            return self.container("object", "}")
        if character == "[":
            return self.container("array", "]")
        start = self.pos
        if character == '"':
            match = _STRING.match(self.text, self.pos)
            if match is None:
                raise self.fail("invalid string")
            self.pos = match.end()
            return _Node("scalar", start, self.pos, json.loads(match.group()))
        for literal, value in _LITERALS.items():
            if self.text.startswith(literal, self.pos):
                self.pos += len(literal)
                return _Node("scalar", start, self.pos, value)
        match = _NUMBER.match(self.text, self.pos)
        if match is None or not match.group():
            raise self.fail("expected a value")
        self.pos = match.end()
        return _Node("scalar", start, self.pos, json.loads(match.group()))

    def container(self, kind: str, closer: str) -> _Node:
        start = self.pos
        self.pos += 1
        entries: list[_Entry] = []
        while True:
            self.skip()
            if self.pos >= len(self.text):
                raise self.fail(f"expected {closer!r}")
            if self.text[self.pos] == closer:
                self.pos += 1
                break
            if entries and entries[-1].comma is None:
                raise self.fail("expected ','")
            entry_start = self.pos
            key: str | None = None
            if kind == "object":
                match = _STRING.match(self.text, self.pos)
                if match is None:
                    raise self.fail("expected a member name")
                key = json.loads(match.group())
                self.pos = match.end()
                self.skip()
                if not self.text.startswith(":", self.pos):
                    raise self.fail("expected ':'")
                self.pos += 1
            value = self.value()
            self.skip()
            comma: int | None = None
            if self.text.startswith(",", self.pos):
                comma = self.pos
                self.pos += 1
            entries.append(_Entry(entry_start, value, comma, key))
        if kind == "object":
            data: dict[str, object] = {}
            seen: set[str] = set()
            duplicates: set[str] = set()
            for entry in entries:
                assert entry.key is not None
                if entry.key in seen:
                    duplicates.add(entry.key)
                seen.add(entry.key)
                data[entry.key] = entry.value.value
            return _Node(kind, start, self.pos, data, tuple(entries), frozenset(duplicates))
        return _Node(
            kind, start, self.pos, [entry.value.value for entry in entries], tuple(entries)
        )


def _parse(text: str) -> tuple[_Node | None, list[tuple[int, int]]]:
    if not isinstance(text, str):
        raise JsoncError("JSONC is text")
    parser = _Parser(text)
    root = parser.document()
    return root, parser.comments


def loads(text: str) -> object:
    """The document `text` holds. Comments and trailing commas are read past; a later duplicate
    member wins, as it does for the harness. Text holding no value at all is refused, since what
    it means is the caller's to decide."""

    root, _ = _parse(text)
    if root is None:
        raise JsoncError("the text holds no value")
    return root.value


def document(text: str) -> object | None:
    """The document `text` holds, or `None` when it holds only whitespace and comments."""

    root, _ = _parse(text)
    return None if root is None else root.value


def has_comments(text: str) -> bool:
    """Whether `text` carries a comment anywhere outside its strings."""

    _, comments = _parse(text)
    return bool(comments)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _line_start(text: str, position: int) -> int:
    return text.rfind("\n", 0, position) + 1


def _line_indent(text: str, position: int) -> str:
    start = _line_start(text, position)
    end = start
    while end < len(text) and text[end] in " \t":
        end += 1
    return text[start:end]


def _indent_unit(text: str) -> str:
    """The step this file indents by: the first indented line's, or two spaces."""

    for line in text.splitlines():
        stripped = line.lstrip(" \t")
        if stripped and stripped != line:
            leading = line[: len(line) - len(stripped)]
            return "\t" if leading.startswith("\t") else " " * len(leading)
    return "  "


@dataclass(frozen=True, slots=True)
class _Edit:
    start: int
    end: int
    text: str


Annotate = Callable[[Path, object], "str | None"]
Owned = Callable[[str], bool]


class _Rewriter:
    def __init__(
        self,
        text: str,
        comments: list[tuple[int, int]],
        annotate: Annotate | None,
        owned: Owned | None,
    ) -> None:
        self.text = text
        self.comments = comments
        self.unit = _indent_unit(text)
        self.annotate = annotate
        self.owned = owned
        self.edits: list[_Edit] = []
        #: How many annotations have been written, so a one-line value that gains none stays one.
        self.notes = 0

    # -- rendering ---------------------------------------------------------------------------

    def render(self, value: object, indent: str, path: Path = ()) -> str:
        """`value` laid out as `json.dumps` would at this depth, each new member annotated."""

        if isinstance(value, dict) and value:
            inner = indent + self.unit
            body = ",".join(
                self.rendered_entry((*path, key), key, item, inner) for key, item in value.items()
            )
            return "{" + body + "\n" + indent + "}"
        if isinstance(value, list) and value:
            inner = indent + self.unit
            body = ",".join(
                self.rendered_entry((*path, index), None, item, inner)
                for index, item in enumerate(value)
            )
            return "[" + body + "\n" + indent + "]"
        return json.dumps(value, ensure_ascii=False, allow_nan=False)

    def rendered_entry(self, path: Path, key: str | None, value: object, indent: str) -> str:
        """One new member or item, starting with its own newline and indentation."""

        lines = ""
        if self.annotate is not None:
            note = self.annotate(path, value)
            if note:
                if any(character in note for character in "\r\n"):
                    raise JsoncError("an annotation is one line")
                self.notes += 1
                lines += f"\n{indent}// {note}"
        prefix = "" if key is None else json.dumps(key, ensure_ascii=False) + ": "
        return f"{lines}\n{indent}{prefix}{self.render(value, indent, path)}"

    # -- inspection --------------------------------------------------------------------------

    def holds_comment(self, start: int, end: int) -> bool:
        return any(start <= begin and finish <= end for begin, finish in self.comments)

    def holds_foreign_comment(self, start: int, end: int) -> bool:
        """Whether a comment between `start` and `end` is anything but an aart-cli marker."""

        for begin, finish in self.comments:
            if start <= begin and finish <= end:
                comment = self.text[begin:finish]
                body = comment[2:-2] if comment.startswith("/*") else comment[2:]
                if self.owned is None or not self.owned(body.strip()):
                    return True
        return False

    def multiline(self, node: _Node) -> bool:
        """Whether every entry of `node` opens its own line, which is what line edits need."""

        if "\n" not in self.text[node.start : node.end]:
            return False
        previous = node.start
        for entry in node.members:
            if "\n" not in self.text[previous : entry.start]:
                return False
            previous = entry.value.end
        return True

    # -- edits -------------------------------------------------------------------------------

    def replace(self, node: _Node, value: object, path: Path) -> None:
        if self.holds_comment(node.start, node.end):
            raise JsoncError(
                "a value holding comments would have to be rewritten whole, losing them"
            )
        notes = self.notes
        rendered = self.render(value, _line_indent(self.text, node.start), path)
        if node.members and "\n" not in self.text[node.start : node.end] and self.notes == notes:
            # A list or object somebody wrote on one line stays on one line, unless it now carries
            # an annotation; an empty `{}` or `[]` opens up, as it says nothing about layout.
            rendered = json.dumps(value, ensure_ascii=False, allow_nan=False)
        self.edits.append(_Edit(node.start, node.end, rendered))

    def diff(self, node: _Node, value: object, path: Path) -> None:
        if _canonical(node.value) == _canonical(value):
            return
        if node.kind == "object" and isinstance(value, dict):
            self.diff_object(node, value, path)
        elif node.kind == "array" and isinstance(value, list):
            self.diff_array(node, value, path)
        else:
            self.replace(node, value, path)

    def diff_object(self, node: _Node, value: dict[str, object], path: Path) -> None:
        current = node.value
        assert isinstance(current, dict)
        touched = {key for key in current if key not in value} | {
            key
            for key in current
            if key in value and _canonical(current[key]) != _canonical(value[key])
        }
        if touched & node.duplicates:
            raise JsoncError(
                f"member {sorted(touched & node.duplicates)[0]!r} is written more than once, so "
                "which one to change is not clear"
            )
        removed = [entry for entry in node.members if entry.key not in value]
        added = [key for key in value if key not in current]
        if (removed or added) and not self.multiline(node):
            self.replace(node, value, path)
            return
        for entry in node.members:
            assert entry.key is not None
            if entry.key in value and entry.key not in node.duplicates:
                self.diff(entry.value, value[entry.key], (*path, entry.key))
        self.membership(
            node,
            removed,
            [((*path, key), key, value[key]) for key in added],
        )

    def diff_array(self, node: _Node, value: list[object], path: Path) -> None:
        current = node.value
        assert isinstance(current, list)
        if len(current) == len(value):
            for index, (entry, item) in enumerate(zip(node.members, value, strict=True)):
                self.diff(entry.value, item, (*path, index))
            return
        wanted = [_canonical(item) for item in value]
        remaining = list(wanted)
        kept: list[_Entry] = []
        removed: list[_Entry] = []
        for entry in node.members:
            spelled = _canonical(entry.value.value)
            if spelled in remaining:
                remaining.remove(spelled)
                kept.append(entry)
            else:
                removed.append(entry)
        kept_spelled = [_canonical(entry.value.value) for entry in kept]
        if wanted[: len(kept)] != kept_spelled or not self.multiline(node):
            self.replace(node, value, path)
            return
        offset = len(kept)
        self.membership(
            node,
            removed,
            [((*path, offset + index), None, item) for index, item in enumerate(value[offset:])],
        )

    def removal_span(self, entry: _Entry) -> tuple[int, int]:
        """The text one entry occupies: its own lines, its comma and same-line comment, and an
        aart-cli comment directly above it."""

        text = self.text
        start = _line_start(text, entry.start)
        if text[start : entry.start].strip(" \t"):
            start = entry.start
        else:
            above_end = start - 1
            if above_end >= 0:
                above_start = _line_start(text, above_end)
                above = text[above_start:above_end].strip(" \t")
                if (
                    above.startswith("//")
                    and self.owned is not None
                    and self.owned(above[2:].strip())
                ):
                    start = above_start
        end = entry.comma + 1 if entry.comma is not None else entry.value.end
        cursor = end
        while cursor < len(text) and text[cursor] in " \t":
            cursor += 1
        if text.startswith("//", cursor):
            newline = text.find("\n", cursor)
            cursor = len(text) if newline < 0 else newline
        if cursor < len(text) and text[cursor] == "\n" and start == _line_start(text, start):
            end = cursor + 1
        return start, end

    def membership(
        self,
        node: _Node,
        removed: list[_Entry],
        added: list[tuple[Path, str | None, object]],
    ) -> None:
        for entry in removed:
            if self.holds_foreign_comment(entry.start, entry.value.end):
                raise JsoncError(
                    "removing this would take a comment somebody wrote inside it, losing it"
                )
        removed_ids = {id(entry) for entry in removed}
        kept = [entry for entry in node.members if id(entry) not in removed_ids]
        if removed and not kept and not added:
            opener, closer = node.start + 1, node.end - 1
            spans = sorted((self.removal_span(entry) for entry in removed), reverse=True)
            if all(opener <= start and end <= closer for start, end in spans):
                survivors = self.text[opener:closer]
                for start, end in spans:
                    survivors = survivors[: start - opener] + survivors[end - opener :]
                if not survivors.strip():
                    # Emptied, with nothing of anybody's left inside: `[]`, not a bracket on
                    # one line and its partner on the next.
                    self.edits.append(_Edit(opener, closer, ""))
                    return
        for entry in removed:
            start, end = self.removal_span(entry)
            self.edits.append(_Edit(start, end, ""))
            if entry.comma is None and kept and kept[-1].comma is not None and not added:
                # The last entry carried no comma, so the one now last gives up its own. With
                # something added, that comma separates it from the addition instead.
                comma = kept[-1].comma
                self.edits.append(_Edit(comma, comma + 1, ""))
        if not added:
            return
        if kept:
            anchor = kept[-1]
            indent = _line_indent(self.text, anchor.start)
            block = ",".join(self.rendered_entry(p, k, v, indent) for p, k, v in added)
            # A trailing comma the anchor had stays a trailing comma, now after the last addition.
            trailing = anchor.comma is not None and anchor is node.members[-1]
            if trailing:
                block += ","
            cursor = anchor.comma + 1 if anchor.comma is not None else anchor.value.end
            scan = cursor
            while scan < len(self.text) and self.text[scan] in " \t":
                scan += 1
            if self.text.startswith("//", scan):
                newline = self.text.find("\n", scan)
                cursor = len(self.text) if newline < 0 else newline
            if anchor.comma is None:
                if cursor == anchor.value.end:
                    self.edits.append(_Edit(cursor, cursor, "," + block))
                else:
                    self.edits.append(_Edit(anchor.value.end, anchor.value.end, ","))
                    self.edits.append(_Edit(cursor, cursor, block))
            elif trailing:
                # `a,` becomes `a,` + block + `,`; the existing comma separates them.
                self.edits.append(_Edit(cursor, cursor, block))
            else:
                self.edits.append(_Edit(cursor, cursor, block))
            return
        outer = _line_indent(self.text, node.start)
        indent = outer + self.unit
        block = ",".join(self.rendered_entry(p, k, v, indent) for p, k, v in added)
        opener = node.start + 1
        inner = self.text[opener : node.end - 1]
        covered = [(start, end) for start, end in (self.removal_span(e) for e in removed)]
        survivors = inner
        for start, end in sorted(covered, reverse=True):
            survivors = survivors[: start - opener] + survivors[end - opener :]
        if "\n" in survivors:
            # The closing bracket already has its own line; the addition goes after `{` and any
            # comment sharing its line, so that comment stays where it was written.
            cursor = opener
            while cursor < len(self.text) and self.text[cursor] in " \t":
                cursor += 1
            if self.text.startswith("//", cursor):
                cursor = self.text.find("\n", cursor)
            else:
                cursor = opener
            self.edits.append(_Edit(cursor, cursor, block))
        else:
            self.edits.append(_Edit(node.end - 1, node.end - 1, block + "\n" + outer))

    def result(self) -> str:
        ordered = sorted(
            enumerate(self.edits), key=lambda item: (item[1].start, item[1].end, item[0])
        )
        pieces: list[str] = []
        cursor = 0
        for _, edit in ordered:
            if edit.start < cursor:
                raise JsoncError("this edit overlaps another; the file is left as it is")
            pieces.append(self.text[cursor : edit.start])
            pieces.append(edit.text)
            cursor = max(cursor, edit.end)
        pieces.append(self.text[cursor:])
        return "".join(pieces)


def rewrite(
    text: str,
    document: object,
    *,
    annotate: Annotate | None = None,
    owned: Owned | None = None,
) -> str:
    """`text` changed to describe `document`, with everything that did not change left as it was.

    `annotate` is asked about each member or item this edit inserts, with its path and value, and
    may answer one line that is written as a `//` comment directly above it. `owned` says which
    comment text marks a member as aart-cli's, so that removing the member removes that comment
    too; no other comment is ever removed except one inside a removed member's own text.

    Text holding no value yet -- empty, or only comments -- gets the document after whatever it
    held. The answer is checked by parsing it back: a rewrite that would describe anything other
    than `document` raises `JsoncError` instead of being returned.
    """

    try:
        json.dumps(document, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise JsoncError(f"the document is not JSON: {error}") from None
    root, comments = _parse(text)
    rewriter = _Rewriter(text, comments, annotate, owned)
    if root is None:
        head = text.rstrip()
        body = rewriter.render(document, "")
        written = (head + "\n" if head else "") + body + "\n"
    else:
        rewriter.diff(root, document, ())
        written = rewriter.result()
    reread, _ = _parse(written)
    if reread is None or _canonical(reread.value) != _canonical(document):
        raise JsoncError("the edit would not say what it was asked to; the file is left as it is")
    return written
