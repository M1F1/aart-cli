"""CP-18 — INV-071, held by the source tree rather than by its declaration.

`dev_tools_test` proves `pyproject.toml` declares no runtime dependency, and `packaging_check`
proves the built wheel carries no `Requires-Dist`. Both are statements about *declarations*, and
INV-071 is about the dependency graph: development verification tooling "MUST remain outside the
production/runtime dependency graph". A module that imported `hypothesis` inside a function would
satisfy every existing check and violate the invariant -- the wheel would still declare nothing,
and the import would fail at the moment a user reached that code path, on a machine that has no
dev group installed.

So this reads the shipped source. The forbidden set is derived from the dev group rather than
written out, because a list copied by hand stops being true the first time someone adds a tool.

`tomllib` is not used to read it. The gates run on Python 3.10, where `tomllib` does not exist, and
this test must run on every supported interpreter -- `dev_tools_test` documents the same constraint
for `poetry.lock`. The table is small and flat, so it is read with the same kind of shortcut, held
by the emptiness guard below.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "agent_artifacts"

#: Distribution names whose import names differ from them. Only what the dev group actually holds.
IMPORT_NAMES = {"poetry-core": "poetry"}

DEV_GROUP = "[tool.poetry.group.dev.dependencies]"


def _table(manifest: str, header: str) -> list[str]:
    """The keys of one flat TOML table, in order, stopping at the next table header."""

    after = manifest.split(header, 1)[1] if header in manifest else ""
    keys = []
    for line in after.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            break
        if stripped and not stripped.startswith("#") and "=" in stripped:
            keys.append(stripped.split("=", 1)[0].strip().strip('"'))
    return keys


def _development_tools() -> frozenset[str]:
    """Every dev-group distribution, as the module name an import statement would use."""

    manifest = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return frozenset(
        IMPORT_NAMES.get(name, name).replace("-", "_") for name in _table(manifest, DEV_GROUP)
    )


def _imported_roots(tree: ast.AST) -> set[str]:
    """Every top-level module this file imports, wherever the statement sits.

    Deliberately not import-time introspection: a tool imported inside a function body is the
    case that matters most, because it is the one that survives every check until a user reaches
    it. `ast` sees those; importing the module does not.
    """

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


class RuntimePurityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tools = _development_tools()
        self.sources = sorted(PACKAGE.rglob("*.py"))

    def test_the_dev_group_is_known_and_not_silently_empty(self) -> None:
        """The guard that makes every assertion below mean something.

        A forbidden set read from a file can become empty by accident -- a renamed group, a moved
        table -- and an empty set forbids nothing while every test still passes.
        """

        self.assertIn("hypothesis", self.tools)
        self.assertIn("mutmut", self.tools)
        self.assertGreaterEqual(len(self.tools), 4)

    def test_the_shortcut_reads_the_table_it_names_and_stops_at_the_next_one(self) -> None:
        """The hand parser is the one part of this file that could quietly read the wrong thing.

        It must take every key of the table it is given, take them from *that* table rather than
        the one after it, and answer nothing at all for a header the manifest does not carry --
        which is what the emptiness guard above then catches.
        """

        manifest = '[a]\nfirst = "1"\n# comment\n\nsecond = { version = "2" }\n\n[b]\nthird = "3"\n'
        self.assertEqual(["first", "second"], _table(manifest, "[a]"))
        self.assertEqual(["third"], _table(manifest, "[b]"))
        self.assertEqual([], _table(manifest, "[c]"))

    def test_the_package_really_is_the_tree_being_read(self) -> None:
        """Likewise: a glob that matched nothing would prove the package imports nothing."""

        self.assertGreater(len(self.sources), 100)
        self.assertIn(PACKAGE / "cli.py", self.sources)

    def test_no_runtime_module_imports_a_development_tool(self) -> None:
        offences = []
        for source in self.sources:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for name in sorted(_imported_roots(tree) & self.tools):
                offences.append(f"{source.relative_to(ROOT)} imports {name}")
        self.assertEqual([], offences, "INV-071: a dev tool reached the runtime dependency graph")

    def test_no_runtime_module_imports_the_test_suite_or_the_gate_scripts(self) -> None:
        """The same leak by another route. `tests` and `scripts` ship in no wheel, so importing
        either would fail for every installed user while passing every check run from a checkout.
        """

        offences = []
        for source in self.sources:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for name in sorted(_imported_roots(tree) & {"tests", "scripts"}):
                offences.append(f"{source.relative_to(ROOT)} imports {name}")
        self.assertEqual([], offences)
