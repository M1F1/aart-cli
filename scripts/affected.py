#!/usr/bin/env python3
"""Which tests a change could possibly have broken.

Three gates -- `unit`, `integration` and `coverage` -- account for essentially all of the suite's
wall time, and each one runs a superset or a copy of the others' tests.  Narrowing them makes the
developer loop usable, but a narrowing that is wrong is worse than no narrowing at all: it reports
green for a test that never ran.

So every rule here is written to refuse.  The analysis narrows only when it can name a complete
reason to, and any path it does not understand -- a build file, a script, a fixture, a module it
cannot parse or find -- makes it decline and hand back the whole suite.  `complete=False` is not an
error; it is the analysis saying it has nothing to contribute to this change.

This is a developer-loop tool.  The release gate stays `make quality`, which runs every test.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["AffectedSelection", "closure", "module_graph", "opaque_tests", "select"]

#: Where a test reaches the package other than by importing it.  A test that starts a process, or
#: drives the CLI's own entry point, depends on code the import graph never links it to, so the
#: graph cannot clear it: it runs whenever any source module changes.
_OPAQUE_RE = re.compile(
    r"\bsubprocess\.|\bos\.exec|\bos\.spawn|"
    r"\bimportlib\.import_module|\b__import__\(|"
    r"\bfrom agent_artifacts\.cli\b|\bagent_artifacts\.cli\.main\b"
)


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _sources(root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (*(root / "agent_artifacts").rglob("*.py"), *(root / "tests").glob("*.py")),
        )
    )


def module_graph(root: Path) -> dict[str, frozenset[str]]:
    """Every canonical module and the modules it imports.

    Names that are not modules in this repository are dropped rather than guessed at, and a
    ``from package import name`` is recorded under both readings because only the filesystem says
    which one ``name`` is.
    """

    paths = {_module_name(path, root): path for path in _sources(root)}
    graph: dict[str, frozenset[str]] = {}
    for name, path in paths.items():
        found: set[str] = set()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            # A module nobody can parse is a module nobody can reason about. It keeps no edges,
            # so anything importing it is still selected by its own text changing.
            graph[name] = frozenset()
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = name.rsplit(".", node.level)[0] if node.level else ""
                if node.level and node.level > name.count("."):
                    base = name.split(".")[0]
                module = f"{base}.{node.module}" if base and node.module else (node.module or base)
                if not module:
                    continue
                found.add(module)
                found.update(f"{module}.{alias.name}" for alias in node.names)
        graph[name] = frozenset(item for item in found if item in paths)
    return graph


def closure(start: str, graph: dict[str, frozenset[str]]) -> frozenset[str]:
    """Every module `start` reaches, directly or through anything it imports."""

    seen: set[str] = set()
    stack = [start]
    while stack:
        for dependency in graph.get(stack.pop(), ()):
            if dependency not in seen:
                seen.add(dependency)
                stack.append(dependency)
    return frozenset(seen)


def opaque_tests(root: Path) -> frozenset[str]:
    """Test modules the import graph cannot speak for, because they leave the process."""

    found: set[str] = set()
    for path in sorted((root / "tests").glob("*_test.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            found.add(_module_name(path, root))
            continue
        if _OPAQUE_RE.search(text):
            found.add(_module_name(path, root))
    return frozenset(found)


@dataclass(frozen=True)
class AffectedSelection:
    """The tests worth running for one change, or a refusal to narrow it.

    `complete` is the whole contract: when it is false, `tests` means nothing and the caller must
    run everything.  A caller that reads `tests` without reading `complete` will silently skip.
    """

    tests: tuple[str, ...] = ()
    complete: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.complete and self.tests:
            raise ValueError("a refusal names no tests, because it speaks for none of them")


def _declined(reason: str) -> AffectedSelection:
    return AffectedSelection((), False, reason)


def select(
    changed: tuple[str, ...],
    *,
    root: Path,
    graph: dict[str, frozenset[str]] | None = None,
) -> AffectedSelection:
    """Which test modules could be affected by `changed`, or a refusal.

    `changed` is repository-relative, as `git diff --name-only` gives it.
    """

    graph = module_graph(root) if graph is None else graph
    sources: set[str] = set()
    tests: set[str] = set()
    for raw in changed:
        path = Path(raw)
        if path.suffix != ".py" or path.parts[0] not in ("agent_artifacts", "tests"):
            return _declined(f"{raw} is not a canonical Python module, so nothing can be ruled out")
        if not (root / path).is_file():
            return _declined(f"{raw} no longer exists, so what depended on it cannot be read")
        name = _module_name(root / path, root)
        if name not in graph:
            return _declined(f"{raw} is outside the module graph, so nothing can be ruled out")
        (tests if name.startswith("tests.") else sources).add(name)

    if not sources and not tests:
        return AffectedSelection((), True, "nothing changed")

    every = tuple(name for name in graph if name.startswith("tests.") and name.endswith("_test"))
    selected = {name for name in tests if name.endswith("_test")}
    if sources:
        selected.update(opaque_tests(root))
        selected.update(name for name in every if closure(name, graph) & sources)
    else:
        # A test-only change still reaches any test that imports the changed one as a fixture.
        selected.update(name for name in every if closure(name, graph) & tests)
    return AffectedSelection(
        tuple(sorted(selected)),
        True,
        f"{len(selected)} of {len(every)} test modules reach what changed",
    )
