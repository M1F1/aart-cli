"""#32, D-404: `tach.toml` is the package's import graph, and it cannot quietly fall behind it.

`tach check` refuses an edge the file does not declare, but only between modules the file names:
a top-level module added without an entry is outside every rule. This test holds the coverage half
in the unit gate, which needs no tach, and ties the one declared target -- `domain` reaches only
the `redaction` leaf -- to the hand-written rule that has always held it.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

from tests.architecture_boundary_test import DOMAIN_ALLOWED_LEAVES

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "aart_cli"
_MODULE = re.compile(r'^\[\[modules\]\]\npath = "([^"]+)"\ndepends_on = \[([^\]]*)\]', re.M)


def _declared() -> dict[str, tuple[str, ...]]:
    text = (ROOT / "tach.toml").read_text(encoding="utf-8")
    return {
        path: tuple(item.strip().strip('"') for item in edges.split(",") if item.strip())
        for path, edges in _MODULE.findall(text)
    }


class TachDeclaresTheWholePackageTest(unittest.TestCase):
    def test_every_top_level_module_is_a_tach_module(self) -> None:
        present = {
            f"aart_cli.{path.stem if path.suffix == '.py' else path.name}"
            for path in PACKAGE.iterdir()
            if path.name not in ("__init__.py", "__pycache__")
            and (path.suffix == ".py" or (path / "__init__.py").exists())
        }

        self.assertEqual(present - set(_declared()), set())

    def test_domain_reaches_only_the_leaves_the_boundary_test_allows(self) -> None:
        self.assertEqual(_declared()["aart_cli.domain"], DOMAIN_ALLOWED_LEAVES)

    def test_the_declared_graph_has_no_cycle_and_tach_forbids_one(self) -> None:
        """B-186, D-409: the graph was cut acyclic once, and the flag keeps it that way."""

        declared = _declared()
        done: set[str] = set()

        def cycle(module: str, path: tuple[str, ...]) -> tuple[str, ...]:
            if module in path:
                return (*path[path.index(module) :], module)
            if module in done:
                return ()
            for edge in declared.get(module, ()):
                found = cycle(edge, (*path, module))
                if found:
                    return found
            done.add(module)
            return ()

        self.assertEqual([found for module in declared if (found := cycle(module, ()))], [])
        text = (ROOT / "tach.toml").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^forbid_circular_dependencies = true$")

    def test_tach_is_one_of_the_quality_gates(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import quality

        self.assertIn("tach", quality.QUALITY_GATES)


if __name__ == "__main__":
    unittest.main()
