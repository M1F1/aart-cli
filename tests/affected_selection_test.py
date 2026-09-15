"""Choosing what a change could possibly have broken, and failing safe when it cannot be known.

The developer loop pays for the whole suite on every edit, and almost all of that cost is three
gates re-running the same tests.  Narrowing them is only sound if the narrowing is conservative:
every rule here exists to make the analysis say "run everything" rather than guess.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("_affected", ROOT / "scripts" / "affected.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


affected = _load()


class ModuleGraphTest(unittest.TestCase):
    def test_a_module_depends_on_what_it_imports_transitively(self) -> None:
        graph = affected.module_graph(ROOT)

        closure = affected.closure("tests.consumer_flow_test", graph)

        self.assertIn("agent_artifacts.application.consumer_session", closure)
        # Reached only through consumer_session, so the graph is transitive rather than direct.
        self.assertIn("agent_artifacts.domain.result", closure)

    def test_a_relative_import_resolves_inside_its_own_package(self) -> None:
        graph = affected.module_graph(ROOT)

        self.assertIn(
            "agent_artifacts.tui_consumer", affected.closure("agent_artifacts.tui", graph)
        )


class SelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = affected.module_graph(ROOT)

    def _select(self, *paths: str):
        return affected.select(tuple(paths), root=ROOT, graph=self.graph)

    def test_changing_one_module_selects_the_tests_that_reach_it(self) -> None:
        selection = self._select("agent_artifacts/application/consumer_views.py")

        self.assertTrue(selection.complete)
        self.assertIn("tests.consumer_flow_test", selection.tests)
        # Reaches none of it, and stays in its own process, so nothing here can have broken it.
        self.assertNotIn("tests.authoring_compiler_test", selection.tests)

    def test_a_changed_test_runs_even_when_nothing_it_imports_changed(self) -> None:
        selection = self._select("tests/consumer_flow_test.py")

        self.assertTrue(selection.complete)
        self.assertIn("tests.consumer_flow_test", selection.tests)

    def test_a_test_that_shells_out_runs_whenever_any_source_changes(self) -> None:
        """A subprocess boundary is not in the import graph, so the graph cannot clear it."""

        selection = self._select("agent_artifacts/domain/result.py")

        self.assertIn("tests.mcp_stdio_e2e_test", selection.tests)

    def test_an_unmapped_path_refuses_to_narrow_anything(self) -> None:
        for path in ("pyproject.toml", "Makefile", "scripts/quality.py", "docs/refactor/NEXT.md"):
            with self.subTest(path=path):
                selection = self._select(path)

                self.assertFalse(selection.complete, path)
                self.assertEqual(selection.tests, ())
                self.assertIn(path, selection.reason)

    def test_one_unmapped_path_among_many_still_refuses(self) -> None:
        selection = self._select("agent_artifacts/domain/result.py", "poetry.lock")

        self.assertFalse(selection.complete)

    def test_nothing_changed_selects_nothing_rather_than_everything(self) -> None:
        selection = self._select()

        self.assertTrue(selection.complete)
        self.assertEqual(selection.tests, ())

    def test_a_deleted_module_refuses_rather_than_reasoning_about_a_missing_file(self) -> None:
        selection = self._select("agent_artifacts/domain/does_not_exist.py")

        self.assertFalse(selection.complete)


if __name__ == "__main__":
    unittest.main()
