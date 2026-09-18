"""Parser-owned authoring field surface for the CP-26 generator oracle.

Steps 7 to 12 generate `aart.yaml` from the fields `protocol/authoring.py` accepts. Transcribing
those names into the generator would make every later parser change silently produce a manifest
that is one field short, so they are read out of the parser instead.

Two rules make the reading trustworthy. Which functions accept fields is taken from their
signatures -- a keyword-only `required` or `optional` parameter -- rather than from a list kept
here, so a new helper is discovered. And a field set the reader cannot resolve statically is
reported as unresolved rather than as empty, so a computed field set can never be mistaken for a
site that accepts nothing.

Runtime code never reads its own Python source; this lives in the test tree and is imported by the
generator tests.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

AUTHORING_PARSER = Path(__file__).resolve().parents[1] / "agent_artifacts/protocol/authoring.py"

#: The keyword-only parameters that make a function a field-accepting helper.
FIELD_KEYWORDS = ("required", "optional")


@dataclass(frozen=True, slots=True)
class FieldSet:
    """One site where the parser accepts a fixed set of field names."""

    owner: str
    helper: str
    label: str | None
    required: tuple[str, ...]
    optional: tuple[str, ...]
    unresolved: tuple[str, ...]


def _literal_names(node: ast.expr | None) -> tuple[str, ...] | None:
    """The string literals a field-set expression denotes, or None when it is computed.

    `frozenset({"a", "b"})`, `{"a"}` and `()` are readable; a name, an f-string or a set built by
    an operator is not, and saying so is the point -- a computed set read as empty would claim the
    site accepts no field.
    """

    if node is None:
        return None
    if isinstance(node, ast.Call):
        callee = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        if callee not in {"frozenset", "set", "tuple", "list"} or node.keywords:
            return None
        if not node.args:
            return ()
        if len(node.args) != 1:
            return None
        return _literal_names(node.args[0])
    if isinstance(node, ast.Set | ast.Tuple | ast.List):
        names: list[str] = []
        for element in node.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                return None
            names.append(element.value)
        return tuple(sorted(set(names)))
    return None


def _definitions(tree: ast.Module) -> tuple[ast.FunctionDef, ...]:
    return tuple(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))


def _keyword_only(definition: ast.FunctionDef) -> dict[str, ast.expr | None]:
    """Keyword-only parameter names mapped to their default expression."""

    arguments = definition.args
    padding: list[ast.expr | None] = list(arguments.kw_defaults)
    return {
        argument.arg: default
        for argument, default in zip(arguments.kwonlyargs, padding, strict=True)
    }


def _positional_names(definition: ast.FunctionDef) -> tuple[str, ...]:
    arguments = definition.args
    return tuple(argument.arg for argument in (*arguments.posonlyargs, *arguments.args))


def _call_name(node: ast.Call) -> str:
    return node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")


def field_helpers(source: str) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Field-accepting helpers, mapped to the fields their own body always demands.

    A wrapper such as `_nested_type` calls the base helper with a fixed `required` of its own, so
    every call to the wrapper accepts those fields too even when it passes no field keyword. That
    inherited requirement is read from the wrapper's body rather than declared here.
    """

    tree = ast.parse(source)
    definitions = {
        definition.name: definition
        for definition in _definitions(tree)
        if any(keyword in _keyword_only(definition) for keyword in FIELD_KEYWORDS)
    }
    inherited: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for name, definition in definitions.items():
        carried: dict[str, set[str]] = {keyword: set() for keyword in FIELD_KEYWORDS}
        for node in ast.walk(definition):
            if not isinstance(node, ast.Call) or _call_name(node) not in definitions:
                continue
            if _call_name(node) == name:
                continue
            passed = {keyword.arg: keyword.value for keyword in node.keywords}
            for keyword in FIELD_KEYWORDS:
                names = _literal_names(passed.get(keyword))
                if names:
                    carried[keyword].update(names)
        inherited[name] = (tuple(sorted(carried["required"])), tuple(sorted(carried["optional"])))
    return inherited


def accepted_fields(source: str) -> tuple[FieldSet, ...]:
    """Every site outside a helper's own body where the parser accepts fields, in source order."""

    tree = ast.parse(source)
    helpers = field_helpers(source)
    definitions = {definition.name: definition for definition in _definitions(tree)}
    internal = {
        node
        for name in helpers
        if name in definitions
        for node in ast.walk(definitions[name])
        if isinstance(node, ast.Call)
    }
    # A nested function owns the calls in its own body, so the innermost enclosing definition --
    # the one declared last among those containing the call -- wins.
    owners: dict[ast.Call, str] = {}
    for definition in sorted(_definitions(tree), key=lambda item: item.lineno):
        for node in ast.walk(definition):
            if isinstance(node, ast.Call) and _call_name(node) in helpers:
                owners[node] = definition.name
    found: list[FieldSet] = []
    for node in sorted(
        (item for item in ast.walk(tree) if isinstance(item, ast.Call)),
        key=lambda item: (item.lineno, item.col_offset),
    ):
        helper = _call_name(node)
        if helper not in helpers or node in internal:
            continue
        definition = definitions.get(helper)
        bound: dict[str, ast.expr | None] = {
            keyword.arg: keyword.value for keyword in node.keywords if keyword.arg is not None
        }
        if definition is not None:
            for name, argument in zip(_positional_names(definition), node.args, strict=False):
                bound.setdefault(name, argument)
            defaults = _keyword_only(definition)
        else:  # pragma: no cover - a helper always has a definition in the parsed source
            defaults = {}
        inherited_required, inherited_optional = helpers[helper]
        resolved: dict[str, tuple[str, ...]] = {}
        unresolved: list[str] = []
        for keyword, carried in zip(
            FIELD_KEYWORDS, (inherited_required, inherited_optional), strict=True
        ):
            expression = bound.get(keyword, defaults.get(keyword))
            names = _literal_names(expression)
            if names is None and keyword in bound:
                unresolved.append(keyword)
                names = ()
            elif names is None:
                names = ()
            resolved[keyword] = tuple(sorted({*names, *carried}))
        label_node = bound.get("label")
        label = (
            label_node.value
            if isinstance(label_node, ast.Constant) and isinstance(label_node.value, str)
            else None
        )
        if label is None:
            unresolved.append("label")
        found.append(
            FieldSet(
                owners.get(node, "<module>"),
                helper,
                label,
                resolved["required"],
                resolved["optional"],
                tuple(sorted(unresolved)),
            )
        )
    return tuple(found)


def parser_field_surface() -> tuple[FieldSet, ...]:
    return accepted_fields(AUTHORING_PARSER.read_text(encoding="utf-8"))
