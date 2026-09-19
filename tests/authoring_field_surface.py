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

AUTHORING_PARSER = Path(__file__).resolve().parents[1] / "aart_cli/protocol/authoring.py"

#: The keyword-only parameters that make a function a field-accepting helper.
FIELD_KEYWORDS = ("required", "optional")


@dataclass(frozen=True, slots=True)
class FieldSet:
    """One site where the parser accepts a fixed set of field names."""

    owner: str
    helper: str
    label: str | None
    #: Every field name the reader could see at this site. When the matching keyword appears in
    #: `unresolved` these are what could be read, not necessarily all of them.
    required: tuple[str, ...]
    optional: tuple[str, ...]
    #: The parts of this site -- "required", "optional", "label" -- that are computed rather than
    #: written out, so the reader cannot promise the set above is complete.
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


def _visible_names(node: ast.expr | None) -> tuple[str, ...]:
    """Every string literal anywhere inside a computed field set.

    `frozenset({"type"} | extra)` resolves to nothing exact, but `type` is still a field this site
    accepts. Reporting it alongside the `unresolved` marker is strictly better than reporting the
    empty set, which reads as "accepts no field" -- the one answer a generator must not be handed.
    """

    if node is None:
        return ()
    return tuple(
        sorted(
            {
                item.value
                for item in ast.walk(node)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
        )
    )


def _assigned_names(owner: ast.FunctionDef | None, target: str) -> tuple[str, ...]:
    """The field names a local variable is assigned anywhere in the function that passes it.

    `_parse_dependencies` picks `required` in three branches and passes the variable. The names are
    literals in the same body, one branch apart from the call, so the union over the branches is
    what that site may demand. It is an over-approximation, which is why the site stays unresolved.
    """

    if owner is None:
        return ()
    found: set[str] = set()
    for node in ast.walk(owner):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        if not any(isinstance(item, ast.Name) and item.id == target for item in targets):
            continue
        found.update(_visible_names(node.value))
    return tuple(sorted(found))


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

    def owner_of(call: ast.Call) -> str:
        return owners.get(call, "<module>")

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
            exact = _literal_names(expression)
            if exact is not None:
                names: tuple[str, ...] = exact
            elif keyword in bound:
                unresolved.append(keyword)
                names = _visible_names(expression)
                if isinstance(expression, ast.Name):
                    names = (
                        *names,
                        *_assigned_names(definitions.get(owner_of(node)), expression.id),
                    )
            else:
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
                owner_of(node),
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
