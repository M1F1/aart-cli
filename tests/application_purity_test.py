from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / "agent_artifacts" / "application"

# The same set the four existing per-package boundary tests use, plus the network and database
# modules a planner has no business reaching.  `urllib`/`http` matter because a plan that resolves
# something over the network is not the same plan twice (INV-005), and a planner that reaches the
# network has mutated nothing but has already left the boundary INV-003 draws.
FORBIDDEN = frozenset(
    {
        "http",
        "os",
        "pathlib",
        "shutil",
        "socket",
        "sqlite3",
        "subprocess",
        "tempfile",
        "urllib",
        "agent_artifacts.cli",
        "agent_artifacts.io",
        "agent_artifacts.tui",
    }
)


def _imports(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return frozenset(names)


def _violations(path: Path) -> list[str]:
    return sorted(
        name
        for name in _imports(path)
        for denied in FORBIDDEN
        if name == denied or name.startswith(f"{denied}.")
    )


class ApplicationLayerIsPureTest(unittest.TestCase):
    """INV-003 and INV-004 over the whole application layer, not four packages of it.

    Boundary tests existed for `compiler`, `marketplace`, `source` and `store`, and none of them
    named `application/installation_planning.py` -- the module that plans installations, which is
    what INV-004 ("planning never mutates the environment") is most directly about. That was
    measured rather than supposed: giving its policy-refusal path a `Path(...).write_text` and a
    `subprocess.run` left all 3,364 tests passing.

    Stated over the directory rather than a list of module names, because a list is a second place
    to forget and goes stale in the same direction as the code it guards.
    """

    def test_no_application_module_reaches_a_durable_or_terminal_boundary(self) -> None:
        offenders = {
            path.name: found
            for path in sorted(APPLICATION.glob("*.py"))
            if (found := _violations(path))
        }

        self.assertEqual(
            offenders,
            {},
            "application modules plan; they do not touch the filesystem, processes, the network "
            "or the terminal. An effect belongs in a plan, interpreted at an io/ boundary.",
        )

    def test_the_planners_this_invariant_is_about_are_actually_covered(self) -> None:
        """A directory sweep passes vacuously if the directory is not what anyone thinks it is."""

        covered = {path.name for path in APPLICATION.glob("*.py")}

        for planner in ("installation_planning.py", "reconciliation.py", "execution.py"):
            with self.subTest(module=planner):
                self.assertIn(planner, covered)

    def test_this_guard_is_not_vacuous(self) -> None:
        modules = list(APPLICATION.glob("*.py"))

        self.assertGreater(len(modules), 20)
        self.assertTrue(FORBIDDEN)
        # The detector must actually detect: a module that really does import these exists.
        self.assertTrue(_violations(ROOT / "agent_artifacts" / "io" / "execution.py"))


if __name__ == "__main__":
    unittest.main()
