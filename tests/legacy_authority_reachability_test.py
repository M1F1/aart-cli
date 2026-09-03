"""CP-18: shipped modules are reachable, or their deliberate exception is named.

The package entry point is the public runtime root.  A production module that can be reached only
from tests is not evidence of shipped behaviour: it is parallel authority whose callers have
already disappeared.

Unreachability is a reason to *ask* whether a module is legacy, never on its own an answer.  This
graph is evidence about imports, and it is silent about every consumer that addresses a file by
its path.  ``domain/outcomes.py`` was deleted on this test's verdict and took the release contract
with it: ``scripts/release.py:SCHEMA_INPUTS`` names it, and its sha256 is pinned in every issued
schema freeze (D-154).

The exception list is a claim about each name in it, so each one states its reason:

* ``_commit`` -- written by the build, which stamps a commit into release artifacts.
* ``application.credential_lifecycle`` -- retained for the still-incomplete credential lifecycle,
  rather than falsely claiming that capability was replaced.
* ``profiles.loader`` -- reads ``<project>/.agent-artifacts/profiles.json`` over the built-ins.
  Kept, and *not* legacy: INV-001 requires enterprise profiles to live outside the public tool, and
  this is the only mechanism by which a profile defined outside it can get in.  What is wrong is
  that nothing calls it -- ``consumer/runtime.py`` passes ``builtin()`` straight into the consumer
  context, so a project's ``profiles.json`` is read by tests and ignored by the product.  That is a
  capability gap, not dead code; B-072 carries the wiring, D-155 the verdict.

``domain.collections`` and ``domain.ports`` were on this list and are gone: each was the unadopted
half of a proposed kernel.  Thirty ``Protocol`` classes are defined across the shipped subsystems,
none of them the generic ``QueryPort``/``CommandPort`` pair, and the sorted-collection helpers had
no caller at all.  ``domain.outcomes`` stays for the release-contract reason above, even though the
shipped session vocabulary really does live in ``reporting/model.py`` and carries a ``no-op`` state
the domain enum never had; retiring it is B-071, a release-contract change rather than a cleanup.

Reachability follows package ``__init__`` files for the reason the walk itself records.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "agent_artifacts"
RUNTIME_ROOTS = frozenset({"agent_artifacts.__main__", "agent_artifacts.cli"})
DELIBERATE_NON_RUNTIME_MODULES = frozenset(
    {
        "agent_artifacts._commit",
        "agent_artifacts.application.credential_lifecycle",
        "agent_artifacts.profiles.loader",
    }
)


def _module_name(path: pathlib.Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = relative.parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _resolved_imports(path: pathlib.Path, modules: frozenset[str]) -> frozenset[str]:
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        targets: tuple[str, ...] = ()
        if isinstance(node, ast.Import):
            targets = tuple(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                prefix = ".".join(parts[: len(parts) - node.level + 1])
                base = ".".join(part for part in (prefix, node.module or "") if part)
            else:
                base = node.module or ""
            targets = (base,) + tuple(
                f"{base}.{alias.name}" for alias in node.names if alias.name != "*"
            )
        imported.update(target for target in targets if target in modules)
    return frozenset(imported)


def _runtime_unreachable_modules() -> frozenset[str]:
    paths = tuple(sorted(PACKAGE.rglob("*.py")))
    by_module = {_module_name(path): path for path in paths}
    modules = frozenset(by_module)
    graph = {module: _resolved_imports(path, modules) for module, path in by_module.items()}
    reachable: set[str] = set()
    pending = list(RUNTIME_ROOTS)
    while pending:
        module = pending.pop()
        if module in reachable:
            continue
        reachable.add(module)
        # Importing `a.b.c` executes `a/__init__.py` and `a/b/__init__.py` first, so whatever
        # those re-export is imported too. Walking only the explicit edges misses that entirely:
        # `domain/__init__.py` re-exported `.outcomes`, so every `domain.*` import loaded it,
        # while this graph called it unreachable. Ancestors are reached by anything beneath them.
        ancestors = {module.rsplit(".", index)[0] for index in range(1, module.count(".") + 1)}
        pending.extend((graph[module] | (ancestors & modules)) - reachable)
    return frozenset(
        module
        for module, path in by_module.items()
        if module not in reachable and path.name != "__init__.py"
    )


class LegacyAuthorityReachabilityTest(unittest.TestCase):
    def test_only_deliberate_non_runtime_modules_are_shipped(self) -> None:
        self.assertEqual(_runtime_unreachable_modules(), DELIBERATE_NON_RUNTIME_MODULES)

    def test_the_runtime_root_and_exception_list_are_not_vacuous(self) -> None:
        modules = frozenset(_module_name(path) for path in PACKAGE.rglob("*.py"))

        self.assertTrue(RUNTIME_ROOTS)
        self.assertTrue(DELIBERATE_NON_RUNTIME_MODULES)
        self.assertLess(len(DELIBERATE_NON_RUNTIME_MODULES), len(modules) // 20)
        self.assertTrue(RUNTIME_ROOTS <= modules)
        self.assertTrue(DELIBERATE_NON_RUNTIME_MODULES <= modules)


if __name__ == "__main__":
    unittest.main()
