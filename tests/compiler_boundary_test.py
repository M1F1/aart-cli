from __future__ import annotations

import ast
import unittest
from pathlib import Path


class CompilerBoundaryTest(unittest.TestCase):
    def test_compiler_domain_and_application_have_no_durable_io_imports(self) -> None:
        root = Path(__file__).parents[1] / "agent_artifacts"
        # `application/compiler.py` was here until CP-18 step 3 removed it: its callers had
        # already disappeared, so it was parallel authority rather than shipped behaviour.  The
        # two files left are the ones the marketplace, catalog and installation paths really
        # import, which is what makes this boundary worth holding.
        files = (
            root / "compiler" / "model.py",
            root / "compiler" / "graph.py",
        )
        self.assertTrue(all(path.exists() for path in files), files)
        forbidden = {
            "os",
            "pathlib",
            "shutil",
            "socket",
            "subprocess",
            "urllib",
            "agent_artifacts.io",
            "agent_artifacts.github_source",
        }
        for path in files:
            with self.subTest(path=path):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imported: set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.update(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module is not None:
                        imported.add(node.module)
                self.assertFalse(
                    any(
                        name == forbidden_name or name.startswith(f"{forbidden_name}.")
                        for name in imported
                        for forbidden_name in forbidden
                    ),
                    imported,
                )


if __name__ == "__main__":
    unittest.main()
