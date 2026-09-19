"""A deliberately small, safe YAML subset for zero-dependency AART manifests.

The authoring contract needs ergonomic block mappings and sequences, not YAML's executable tags,
anchors, aliases, merge keys, or implicit timestamps/floats.  Keeping that finite grammar here
preserves the runtime's standard-library-only boundary and makes accepted syntax deterministic.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from aart_cli.domain.diagnostics import Diagnostic, Severity, SourceLocation
from aart_cli.domain.result import Err, Ok, Result

from .codes import AUTHOR_MANIFEST_INVALID, AUTHOR_MANIFEST_UNWRITABLE
from .json import JsonArray, JsonObject, JsonValue

_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_INTEGER_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)$")


@dataclass(frozen=True, slots=True)
class _Line:
    indent: int
    text: str
    number: int


class _YamlProblem(ValueError):
    def __init__(self, message: str, line: int, column: int = 1):
        super().__init__(message)
        self.line = line
        self.column = column


def _strip_comment(raw: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(raw):
        if quote == '"' and escaped:
            escaped = False
            continue
        if quote == '"' and character == "\\":
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "#" and (index == 0 or raw[index - 1].isspace()):
            return raw[:index]
    return raw


def _tokenize(text: str) -> tuple[_Line, ...]:
    lines: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw:
            raise _YamlProblem("tabs are forbidden in AART YAML", number)
        content = _strip_comment(raw).rstrip()
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip(" "))
        if indent % 2:
            raise _YamlProblem("indentation must use multiples of two spaces", number)
        lines.append(_Line(indent, content[indent:], number))
    return tuple(lines)


def _mapping_pair(text: str, line: int) -> tuple[str, str]:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(text):
        if quote == '"' and escaped:
            escaped = False
            continue
        if quote == '"' and character == "\\":
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == ":" and (index + 1 == len(text) or text[index + 1].isspace()):
            key = text[:index].strip()
            if _KEY_RE.fullmatch(key) is None:
                raise _YamlProblem(f"invalid mapping key {key!r}", line)
            return key, text[index + 1 :].strip()
    raise _YamlProblem("mapping entry requires ':'", line)


def _scalar(raw: str, line: int) -> JsonValue:
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise _YamlProblem(f"invalid double-quoted string: {error.msg}", line) from error
        if not isinstance(value, str):
            raise _YamlProblem("quoted YAML scalar must be a string", line)
        return value
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            raise _YamlProblem("unterminated single-quoted string", line)
        return raw[1:-1].replace("''", "'")
    lowered = raw.lower()
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if _INTEGER_RE.fullmatch(raw):
        value = int(raw)
        if not -(2**63) <= value <= 2**63 - 1:
            raise _YamlProblem("integer is outside signed 64-bit range", line)
        return value
    if raw.startswith(("[", "{", "&", "*", "!", "|", ">")) or raw == "---":
        raise _YamlProblem("unsupported YAML feature in AART manifest", line)
    if not raw or any(ord(character) < 32 for character in raw):
        raise _YamlProblem("invalid plain scalar", line)
    return raw


def _parse_mapping(lines: tuple[_Line, ...], index: int, indent: int) -> tuple[JsonObject, int]:
    entries: list[tuple[str, JsonValue]] = []
    keys: set[str] = set()
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if line.text.startswith("-"):
            break
        key, raw_value = _mapping_pair(line.text, line.number)
        if key in keys:
            raise _YamlProblem(f"duplicate mapping key {key!r}", line.number)
        keys.add(key)
        index += 1
        if raw_value:
            value = _scalar(raw_value, line.number)
        else:
            if index >= len(lines) or lines[index].indent <= indent:
                raise _YamlProblem(f"mapping key {key!r} requires a nested value", line.number)
            if lines[index].indent != indent + 2:
                raise _YamlProblem("nested blocks must indent by two spaces", lines[index].number)
            value, index = _parse_block(lines, index, indent + 2)
        entries.append((key, value))
    return JsonObject(tuple(entries)), index


def _parse_sequence(lines: tuple[_Line, ...], index: int, indent: int) -> tuple[JsonArray, int]:
    items: list[JsonValue] = []
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if not line.text.startswith("-"):
            break
        if line.text != "-" and not line.text.startswith("- "):
            raise _YamlProblem("sequence marker must be followed by a space", line.number)
        raw_item = line.text[1:].strip()
        index += 1
        if not raw_item:
            if index >= len(lines) or lines[index].indent != indent + 2:
                raise _YamlProblem("sequence item requires a nested value", line.number)
            value, index = _parse_block(lines, index, indent + 2)
            items.append(value)
            continue
        try:
            first_key, first_raw = _mapping_pair(raw_item, line.number)
        except _YamlProblem:
            items.append(_scalar(raw_item, line.number))
            continue
        if not first_raw:
            raise _YamlProblem("a sequence mapping must begin with a scalar field", line.number)
        mapping_entries: list[tuple[str, JsonValue]] = [
            (first_key, _scalar(first_raw, line.number))
        ]
        if index < len(lines) and lines[index].indent > indent:
            if lines[index].indent != indent + 2:
                raise _YamlProblem(
                    "sequence mappings must indent by two spaces", lines[index].number
                )
            remainder, index = _parse_mapping(lines, index, indent + 2)
            existing = {first_key}
            for key, value in remainder.entries:
                if key in existing:
                    raise _YamlProblem(f"duplicate mapping key {key!r}", line.number)
                existing.add(key)
                mapping_entries.append((key, value))
        items.append(JsonObject(tuple(mapping_entries)))
    return JsonArray(tuple(items)), index


def _parse_block(lines: tuple[_Line, ...], index: int, indent: int) -> tuple[JsonValue, int]:
    if index >= len(lines) or lines[index].indent != indent:
        line = 1 if index >= len(lines) else lines[index].number
        raise _YamlProblem("invalid block indentation", line)
    if lines[index].text.startswith("-"):
        return _parse_sequence(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def parse_yaml(
    data: bytes | str,
    *,
    path: str = "aart-cli.yaml",
) -> Result[JsonValue]:
    """Parse the finite YAML subset accepted by native AART authoring manifests."""

    try:
        text = data.decode("utf-8", errors="strict") if isinstance(data, bytes) else data
    except UnicodeDecodeError:
        return Err(
            (
                Diagnostic(
                    AUTHOR_MANIFEST_INVALID,
                    Severity.ERROR,
                    "AART YAML is not valid UTF-8",
                    SourceLocation(path=path),
                ),
            )
        )
    try:
        lines = _tokenize(text)
        if not lines:
            raise _YamlProblem("AART YAML document is empty", 1)
        if lines[0].indent != 0:
            raise _YamlProblem("top-level YAML must start at column one", lines[0].number)
        value, index = _parse_block(lines, 0, 0)
        if index != len(lines):
            raise _YamlProblem("unexpected indentation or mixed block types", lines[index].number)
        return Ok(value)
    except _YamlProblem as error:
        return Err(
            (
                Diagnostic(
                    AUTHOR_MANIFEST_INVALID,
                    Severity.ERROR,
                    str(error),
                    SourceLocation(path=path, line=error.line, column=error.column),
                ),
            )
        )


class _EmitProblem(ValueError):
    """A value the AART YAML subset cannot express, named by where it sits."""


#: Characters that open a YAML construct, so a plain scalar may never begin with one.
_RESERVED_PREFIX = "-?,[]{}#&*!|>'\"%@`"


def _plain_safe(text: str) -> bool:
    """Whether `text` survives being written without quotes.

    The test is the parser's own: a plain scalar is safe when `_scalar` hands the identical string
    back. That catches `true`, `null`, `12` and `---` without a second list of special forms to
    keep in step. The checks before it rule out the shapes that never reach `_scalar` intact --
    surrounding space that `rstrip` eats, a `#` that starts a comment, a `:` that reads as a
    mapping key inside a sequence item, and any character that opens another construct.
    """

    if not text or text != text.strip():
        return False
    if any(ord(character) < 32 for character in text):
        return False
    # `str.splitlines` breaks on more than `\n`: NEL, the line and paragraph separators and the
    # file separators all end a line for the tokenizer, so a plain scalar holding one would be
    # emitted as a single line and read back as two.
    if text.splitlines() != [text]:
        return False
    if "#" in text or ":" in text or text[0] in _RESERVED_PREFIX:
        return False
    try:
        return _scalar(text, 0) == text
    except _YamlProblem:
        return False


def _emit_scalar(value: JsonValue, path: str) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if not -(2**63) <= value <= 2**63 - 1:
            raise _EmitProblem(f"{path}: integer is outside the signed 64-bit range")
        return str(value)
    if isinstance(value, str):
        return value if _plain_safe(value) else json.dumps(value)
    raise _EmitProblem(f"{path}: value is not a scalar")


def _is_scalar(value: JsonValue) -> bool:
    return not isinstance(value, JsonObject | JsonArray)


def _child_path(path: str, segment: str) -> str:
    return segment if not path else f"{path}.{segment}"


def _refuse_empty(value: JsonValue, path: str) -> None:
    """Neither empty block has a spelling in the grammar, so neither may be written."""

    if isinstance(value, JsonObject) and not value.entries:
        raise _EmitProblem(f"{path}: an empty mapping cannot be written in AART YAML")
    if isinstance(value, JsonArray) and not value.items:
        raise _EmitProblem(f"{path}: an empty sequence cannot be written in AART YAML")


class _Writer:
    def __init__(self, comments: dict[str, tuple[str, ...]], trailing: dict[str, tuple[str, ...]]):
        self._comments = comments
        self._trailing = trailing
        self.used: set[str] = set()
        self.closed: set[str] = set()
        self.lines: list[str] = []

    def _write(self, lines: tuple[str, ...], indent: int) -> None:
        """Write comment lines at `indent`.

        A line that already begins with `#` is written as it stands rather than commented again, so
        a caller can put a doubled `##` note or a `#?` alternative beside plain disabled YAML and
        have the three remain distinguishable to whoever reads the file.
        """

        pad = " " * indent
        self.lines.extend(
            f"{pad}{line}" if line.startswith("#") else f"{pad}#{f' {line}' if line else ''}"
            for line in lines
        )

    def comment(self, path: str, indent: int) -> None:
        lines = self._comments.get(path)
        if lines is None:
            return
        self.used.add(path)
        self._write(lines, indent)

    def close(self, path: str, indent: int) -> None:
        """Write what belongs after a block's last entry, at the entries' own indentation."""

        lines = self._trailing.get(path)
        if lines is None:
            return
        self.closed.add(path)
        self._write(lines, indent)

    def block(self, value: JsonValue, indent: int, path: str) -> None:
        if isinstance(value, JsonObject):
            self.mapping(value.entries, indent, path)
        elif isinstance(value, JsonArray):
            self.sequence(value, indent, path)
        else:  # pragma: no cover - callers check before descending
            raise _EmitProblem(f"{path}: value is not a block")

    def mapping(
        self,
        entries: tuple[tuple[str, JsonValue], ...],
        indent: int,
        path: str,
    ) -> None:
        pad = " " * indent
        for key, value in entries:
            if _KEY_RE.fullmatch(key) is None:
                raise _EmitProblem(f"{_child_path(path, key)}: {key!r} is not a valid mapping key")
            here = _child_path(path, key)
            self.comment(here, indent)
            if _is_scalar(value):
                self.lines.append(f"{pad}{key}: {_emit_scalar(value, here)}")
                continue
            _refuse_empty(value, here)
            self.lines.append(f"{pad}{key}:")
            self.block(value, indent + 2, here)
        self.close(path, indent)

    def sequence(self, value: JsonArray, indent: int, path: str) -> None:
        pad = " " * indent
        for position, item in enumerate(value.items):
            here = _child_path(path, str(position))
            if _is_scalar(item):
                self.comment(here, indent)
                self.lines.append(f"{pad}- {_emit_scalar(item, here)}")
                continue
            _refuse_empty(item, here)
            if isinstance(item, JsonObject) and _is_scalar(item.entries[0][1]):
                # `- key: scalar` is the grammar's only compact item, and its first field has to be
                # a scalar; the comment on that field belongs above the marker line it shares.
                first_key, first_value = item.entries[0]
                if _KEY_RE.fullmatch(first_key) is None:
                    raise _EmitProblem(
                        f"{_child_path(here, first_key)}: {first_key!r} is not a valid mapping key"
                    )
                self.comment(here, indent)
                self.comment(_child_path(here, first_key), indent)
                scalar = _emit_scalar(first_value, _child_path(here, first_key))
                self.lines.append(f"{pad}- {first_key}: {scalar}")
                self.mapping(item.entries[1:], indent + 2, here)
                continue
            self.comment(here, indent)
            self.lines.append(f"{pad}-")
            self.block(item, indent + 2, here)
        self.close(path, indent)


def emit_yaml(
    value: JsonValue,
    *,
    comments: Mapping[str, Sequence[str]] = MappingProxyType({}),
    trailing: Mapping[str, Sequence[str]] = MappingProxyType({}),
    path: str = "aart-cli.yaml",
) -> Result[str]:
    """Write the finite YAML subset `parse_yaml` accepts, or refuse to write at all.

    The emitter is the parser's inverse: anything it returns parses back to the value it was given.
    Where the subset cannot express a value -- an empty block, a key the grammar rejects, an
    integer outside the protocol range -- it refuses and names the position, rather than writing a
    document that reads back as something else.

    `comments` maps a position to the lines written above it: `""` for the document header, and
    otherwise a dotted path of mapping keys and sequence indices, such as `artifact.kind` or
    `payload.include.0`. `trailing` does the same below a *block's* last entry, at the entries' own
    indentation, for the lines that have no following key to sit above. A comment aimed at a
    position the document does not have is a refusal in either map, because silently dropping it is
    how a generated manifest loses its documentation.
    """

    fixed = {key: tuple(lines) for key, lines in comments.items()}
    closers = {key: tuple(lines) for key, lines in trailing.items()}
    for position, lines in sorted((*fixed.items(), *closers.items())):
        where = position or "the document header"
        for line in lines:
            if line.splitlines() not in ([], [line]):
                return _emit_error(f"comment at {where} contains a newline", path)
            if any(ord(character) < 32 for character in line):
                return _emit_error(f"comment at {where} is not text", path)
    if not isinstance(value, JsonObject | JsonArray):
        return _emit_error("an AART YAML document must be a mapping or a sequence", path)
    writer = _Writer(fixed, closers)
    try:
        _refuse_empty(value, "the document")
        writer.comment("", 0)
        writer.block(value, 0, "")
    except _EmitProblem as error:
        return _emit_error(str(error), path)
    unused = sorted(set(fixed) - writer.used)
    if unused:
        return _emit_error(f"comment at {unused[0]} names no such key in the document", path)
    unclosed = sorted(set(closers) - writer.closed)
    if unclosed:
        return _emit_error(
            f"trailing comment at {unclosed[0] or 'the document'} names no such block", path
        )
    return Ok("".join(f"{line}\n" for line in writer.lines))


def _emit_error(message: str, path: str) -> Err:
    return Err(
        (
            Diagnostic(
                AUTHOR_MANIFEST_UNWRITABLE,
                Severity.ERROR,
                message,
                SourceLocation(path=path),
            ),
        )
    )
