"""Executable dependency rules for the canonical strangler seam."""

from __future__ import annotations

import ast
import dataclasses
import importlib
import pathlib
import unittest
from typing import Protocol, cast

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "agent_artifacts"


class _DataclassParams(Protocol):
    frozen: bool


def _imports(path: pathlib.Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return tuple(modules)


class CanonicalArchitectureBoundaryTest(unittest.TestCase):
    def test_domain_depends_only_on_stdlib_and_canonical_domain(self) -> None:
        violations: list[str] = []
        for path in sorted((PACKAGE / "domain").glob("*.py")):
            for module in _imports(path):
                if module.startswith("agent_artifacts.") and not module.startswith(
                    "agent_artifacts.domain"
                ):
                    violations.append(f"{path.name}: {module}")

        self.assertEqual(violations, [])

    def test_application_does_not_import_concrete_io_or_interfaces(self) -> None:
        forbidden = (
            "agent_artifacts.io",
            "agent_artifacts.cli",
            "agent_artifacts.tui",
        )
        violations: list[str] = []
        for path in sorted((PACKAGE / "application").glob("*.py")):
            for module in _imports(path):
                if module.startswith(forbidden):
                    violations.append(f"{path.name}: {module}")

        self.assertEqual(violations, [])

    def test_every_canonical_domain_dataclass_is_frozen(self) -> None:
        mutable: list[str] = []
        found: list[str] = []
        for path in sorted((PACKAGE / "domain").glob("*.py")):
            if path.name == "__init__.py":
                continue
            module = importlib.import_module(f"agent_artifacts.domain.{path.stem}")
            for value in vars(module).values():
                if (
                    not isinstance(value, type)
                    or value.__module__ != module.__name__
                    or not dataclasses.is_dataclass(value)
                ):
                    continue
                name = f"{path.stem}.{value.__name__}"
                found.append(name)
                params = cast(_DataclassParams, vars(value)["__dataclass_params__"])
                if not params.frozen:
                    mutable.append(name)

        self.assertTrue(found)
        self.assertEqual(mutable, [])


if __name__ == "__main__":
    unittest.main()
