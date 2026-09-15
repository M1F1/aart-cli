"""A deliberately small, safe YAML subset for zero-dependency AART manifests.

The authoring contract needs ergonomic block mappings and sequences, not YAML's executable tags,
anchors, aliases, merge keys, or implicit timestamps/floats.  Keeping that finite grammar here
preserves the runtime's standard-library-only boundary and makes accepted syntax deterministic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from agent_artifacts.domain.diagnostics import Diagnostic, Severity, SourceLocation
from agent_artifacts.domain.result import Err, Ok, Result

from .codes import AUTHOR_MANIFEST_INVALID
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
    path: str = "aart.yaml",
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
