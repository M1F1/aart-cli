from __future__ import annotations

import ast
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "agent_artifacts"

# The terminal driver is the one module allowed to be a terminal.  It exists to start curses, fall
# back to text when curses is not there, and hand the failure back as a typed record; every screen
# module below it is a projection that never learns which of the two it is being drawn into.
TERMINAL_DRIVER = "tui.py"

# Everything a frontend must not become.  INV-064 does not forbid the TUI from *causing* an effect
# -- it forbids the TUI from *being* the implementation of one, which is what importing these
# would make it.
FORBIDDEN = frozenset(
    {
        "ftplib",
        "http",
        "keyring",
        "os",
        "pathlib",
        "platform",
        "shutil",
        "socket",
        "sqlite3",
        "ssl",
        "subprocess",
        "sys",
        "tempfile",
        "urllib",
    }
)

# The one place a screen module is permitted to reach the effect boundary, and the reason.  The
# Marketplace is read once at the top of a session so that drawing a frame never reaches the source
# store (D-051); a redraw that re-read the disk would make the frame rate a filesystem property.
# Anything else appearing here is a screen that has started doing I/O behind a draw.
DECLARED_EFFECT_SEAMS = {
    ("tui_consumer.py", "read_consumer_offers"): "agent_artifacts.io.configured_offers",
}


def _screen_modules() -> list[Path]:
    """The frontend layer: the screen modules plus the shared screen kernel, minus the driver."""

    modules = [p for p in sorted(PACKAGE.glob("tui*.py")) if p.name != TERMINAL_DRIVER]
    modules.append(PACKAGE / "wizard.py")
    return modules


def _imports(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return frozenset(names)


def _violations(path: Path, denied: frozenset[str] = FORBIDDEN) -> list[str]:
    return sorted(
        name
        for name in _imports(path)
        for bad in denied
        if name == bad or name.startswith(f"{bad}.")
    )


def _effect_reaches(path: Path) -> dict[tuple[str, str], str]:
    """Every `agent_artifacts.io` import in the file, keyed by the function that performs it.

    A module-level reach is keyed by `<module>` so it can never collide with, and never be excused
    by, a function-scoped one that happens to be declared.
    """

    found: dict[tuple[str, str], str] = {}

    def imported(node: ast.AST) -> str | None:
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            return node.module
        if isinstance(node, ast.Import):
            return next(
                (a.name for a in node.names if a.name.startswith("agent_artifacts.io")), None
            )
        return None

    def descend(node: ast.AST, where: str) -> None:
        for child in ast.iter_child_nodes(node):
            module = imported(child)
            if module and module.startswith("agent_artifacts.io"):
                found[(path.name, where)] = module
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                descend(child, child.name)
            else:
                descend(child, where)

    descend(ast.parse(path.read_text(encoding="utf-8")), "<module>")
    return found


def _is_dynamic_import(func: ast.AST) -> bool:
    if isinstance(func, ast.Name):
        return func.id in {"__import__", "import_module"}
    return isinstance(func, ast.Attribute) and func.attr == "import_module"


def _platform_reads(path: Path) -> list[str]:
    """Any syntactic route to the host platform, however the module got hold of the module."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        base = node.value
        if isinstance(base, ast.Name) and base.id in {"os", "platform", "sys"}:
            found.add(f"{base.id}.{node.attr}")
        elif isinstance(base, ast.Call) and _is_dynamic_import(base.func):
            # `__import__("sys").platform` reaches the host with no import statement to find.
            found.add(f"<dynamic>.{node.attr}")
    return sorted(found)


def _dynamic_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_dynamic_import(node.func):
            target = node.func
            if isinstance(target, ast.Name):
                found.add(target.id)
            elif isinstance(target, ast.Attribute):
                found.add(target.attr)
    return sorted(found)


class TheFrontendIsAProjectionTest(unittest.TestCase):
    """INV-062 and INV-064 over the frontend layer rather than over one screen at a time.

    The screen tests that existed asserted what a given frame contains.  None of them asserted
    what a screen module is permitted to *be*, which is the half of the invariant that decays
    silently: a screen that grows a `subprocess.run` still renders correctly and every frame
    assertion still passes.
    """

    def test_no_screen_module_is_an_implementation_of_infrastructure(self) -> None:
        offenders = {path.name: found for path in _screen_modules() if (found := _violations(path))}

        self.assertEqual(
            offenders,
            {},
            "screens render state and emit intent. Filesystem, process, network and credential "
            "work belongs behind an io/ port that the composition root calls.",
        )

    def test_the_terminal_driver_is_the_only_module_that_is_a_terminal(self) -> None:
        """The exception is one named module, so its existence stays a decision rather than a habit."""

        driver = PACKAGE / TERMINAL_DRIVER
        self.assertIn("curses", _imports(driver))

        for path in _screen_modules():
            with self.subTest(module=path.name):
                self.assertNotIn("curses", _imports(path))

    def test_no_screen_module_decides_anything_from_the_platform(self) -> None:
        """INV-066: choices are produced by capability and policy evaluation, not by `if darwin`.

        The composition root is where the platform is read once, into a typed capability probe.
        A screen that reads it again is a screen synthesising a remediation the core did not offer.

        Read off the syntax rather than off the import list, because `__import__("sys").platform`
        reaches the platform without an import statement to find -- the first draft of this test
        searched for the text `sys.platform` and that mutation survived it.
        """

        offenders = {
            path.name: found for path in _screen_modules() if (found := _platform_reads(path))
        }

        self.assertEqual(
            offenders,
            {},
            "a screen that branches on the platform is deciding what is available, which is the "
            "capability probe's answer to give.",
        )

    def test_screens_import_statically_so_the_sweep_above_can_be_complete(self) -> None:
        """A dynamic import is a boundary crossing with no import statement to find."""

        offenders = {
            path.name: found for path in _screen_modules() if (found := _dynamic_imports(path))
        }

        self.assertEqual(offenders, {})

    def test_the_effect_boundary_is_crossed_only_where_it_is_declared(self) -> None:
        reaches: dict[tuple[str, str], str] = {}
        for path in _screen_modules():
            reaches.update(_effect_reaches(path))

        self.assertEqual(
            reaches,
            DECLARED_EFFECT_SEAMS,
            "a screen module that reads the world is a screen whose redraw cost is a disk cost. "
            "Read at the seam, then draw from what was read.",
        )


class TheFrontendIsHeadlesslyTestableTest(unittest.TestCase):
    """INV-068: the interaction model must be exercisable without a terminal existing at all."""

    def test_every_screen_module_imports_with_no_terminal_available(self) -> None:
        saved = sys.modules.pop("curses", None)
        try:
            # `None` in `sys.modules` is the documented way to make an import fail as if the
            # module were not installed, which is the condition CI and a piped run both meet.
            sys.modules["curses"] = None  # type: ignore[assignment]
            for path in _screen_modules():
                name = f"agent_artifacts.{path.stem}"
                with self.subTest(module=name):
                    sys.modules.pop(name, None)
                    self.assertTrue(importlib.import_module(name))
        finally:
            sys.modules.pop("curses", None)
            if saved is not None:
                sys.modules["curses"] = saved


class TheseGuardsAreNotVacuousTest(unittest.TestCase):
    def test_the_layer_being_swept_is_the_layer_that_draws(self) -> None:
        names = {path.name for path in _screen_modules()}

        self.assertIn("tui_consumer.py", names)
        self.assertIn("tui_marketplace.py", names)
        self.assertIn("tui_maintainer.py", names)
        self.assertIn("wizard.py", names)
        self.assertNotIn(TERMINAL_DRIVER, names)

    def test_the_infrastructure_detector_detects(self) -> None:
        self.assertTrue(_violations(PACKAGE / "io" / "execution.py"))

    def test_the_platform_and_dynamic_import_detectors_detect(self) -> None:
        driver = PACKAGE / TERMINAL_DRIVER

        self.assertIn("sys.platform", _platform_reads(driver))
        self.assertTrue(_dynamic_imports(driver))

    def test_the_effect_seam_detector_detects(self) -> None:
        """The declared seam must be found by the same walk that would find an undeclared one."""

        found = _effect_reaches(PACKAGE / "tui_consumer.py")

        self.assertEqual(found, DECLARED_EFFECT_SEAMS)
        self.assertTrue(_effect_reaches(PACKAGE / "commands" / "doctor.py"))


if __name__ == "__main__":
    unittest.main()
