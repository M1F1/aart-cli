from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "refactor" / "INVARIANT_TRACEABILITY.md"
TESTS = ROOT / "tests"

_ROW = re.compile(r"^\| (INV-\d+) \|")
_CITED_TEST = re.compile(r"`([a-z0-9_]+_test)\.py")
# Package modules are cited package-relative (`domain/effects.py`), not from the repository
# root -- the first draft of this regex demanded an `agent_artifacts/` prefix that appears in
# the matrix exactly zero times, so it matched nothing and passed for that reason (M38).
_CITED_MODULE = re.compile(r"`([a-z0-9_]+(?:/[a-z0-9_]+)+\.py)")
# `file_test.py::Class::method` or `file_test.py::method`. Naming the test is what makes a row
# checkable by a reader; naming one that no longer exists is worse than naming none, because it
# reads as evidence.
_CITED_CASE = re.compile(
    r"`([a-z0-9_]+_test)\.py::([A-Za-z_][A-Za-z0-9_]*)(?:::([A-Za-z_][A-Za-z0-9_]*))?`"
)
_STATUSES = frozenset({"EVIDENCED", "PARTIAL", "CONFLICT"})


def _rows() -> list[list[str]]:
    rows = []
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if _ROW.match(line):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


class TheTraceabilityMatrixCitesThingsThatExistTest(unittest.TestCase):
    """The matrix is the repository's claim about which invariants are proven, and its evidence
    column is a list of file names -- so it drifts exactly like any other hand-maintained list of
    paths, and it drifts *hardest* when a slice deletes something, which is the moment the claim
    matters most.

    CP-18 step 3 removed `policy.py` and `policy_test.py` with it, and five rows (INV-028 to
    INV-032) went on citing both as their evidence. Nothing noticed, because nothing was looking.
    """

    def test_every_cited_test_file_exists(self) -> None:
        text = MATRIX.read_text(encoding="utf-8")

        missing = sorted(
            name for name in set(_CITED_TEST.findall(text)) if not (TESTS / f"{name}.py").is_file()
        )

        self.assertEqual(
            missing,
            [],
            "the matrix offers these as evidence and they are not in the tree; a deleted test "
            "does not stop being cited on its own",
        )

    def test_every_cited_package_module_exists(self) -> None:
        text = MATRIX.read_text(encoding="utf-8")

        cited = {path for path in _CITED_MODULE.findall(text) if not path.endswith("_test.py")}
        # Package modules are written package-relative and repository tooling from the root, so a
        # citation resolves if either reading finds a file.
        missing = sorted(
            path
            for path in cited
            if not (ROOT / "agent_artifacts" / path).is_file() and not (ROOT / path).is_file()
        )

        self.assertGreater(len(cited), 10, "this claim is worthless if it resolves nothing")
        self.assertEqual(missing, [], "the matrix names owners that are no longer in the tree")

    def test_every_cited_test_case_exists_under_the_name_it_is_cited_by(self) -> None:
        """A file that still exists can have lost the test the row was actually pointing at."""

        text = MATRIX.read_text(encoding="utf-8")
        sources: dict[str, str] = {}
        missing: list[str] = []
        cited = _CITED_CASE.findall(text)
        for module, first, second in cited:
            path = TESTS / f"{module}.py"
            if not path.is_file():
                missing.append(f"{module}.py")
                continue
            source = sources.setdefault(module, path.read_text(encoding="utf-8"))
            for name in (first, second):
                if not name:
                    continue
                if f"def {name}(" not in source and f"class {name}(" not in source:
                    missing.append(f"{module}.py::{name}")

        self.assertGreater(len(cited), 30, "this claim is worthless if it resolves nothing")
        self.assertEqual(
            sorted(missing),
            [],
            "a row names a test case that is not in the file it names",
        )

    def test_every_row_carries_a_status_the_legend_defines(self) -> None:
        for row in _rows():
            with self.subTest(invariant=row[0]):
                self.assertIn(row[-1], _STATUSES)

    def test_this_guard_is_not_vacuous(self) -> None:
        text = MATRIX.read_text(encoding="utf-8")

        self.assertGreater(len(_rows()), 200)
        self.assertGreater(len(set(_CITED_TEST.findall(text))), 20)
        self.assertFalse((TESTS / "policy_test.py").is_file())
        # The case matcher must be matching the real shape, not a shape nobody writes.
        self.assertGreater(len(set(_CITED_CASE.findall(text))), 30)


if __name__ == "__main__":
    unittest.main()
