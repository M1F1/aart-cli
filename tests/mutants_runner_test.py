"""The scoped mutation runner copies the source tree that owns the requested module."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("_aart_mutants", ROOT / "scripts" / "mutants.py")
assert SPEC is not None and SPEC.loader is not None
mutants = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mutants)


class MutationScopeTest(unittest.TestCase):
    def test_a_script_scope_copies_scripts_instead_of_the_runtime_package(self) -> None:
        section = mutants._section(
            ["scripts/release_artifact.py"], ["tests/release_artifact_test.py"]
        )

        self.assertIn("source_paths = scripts\n", section)
        self.assertNotIn("source_paths = agent_artifacts\n", section)

    def test_multiple_source_roots_are_each_copied_once(self) -> None:
        section = mutants._section(
            [
                "scripts/release_artifact.py",
                "agent_artifacts/runtime_contract.py",
                "scripts/conventional_title.py",
            ],
            [],
        )

        self.assertIn(
            "source_paths =\n    agent_artifacts\n    scripts\n",
            section,
        )


if __name__ == "__main__":
    unittest.main()
