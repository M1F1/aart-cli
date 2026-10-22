"""D-466: the parallel runner runs the same suite as `unittest discover`, and fails when it does.

The gate used to run every test module in one process, twice per interpreter. The runner keeps
unittest and splits modules across processes. What has to hold is that the split loses nothing,
runs each module once, imports modules the way discovery does, and reports a failure as one.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

from hypothesis import given
from hypothesis import strategies as st

ROOT = pathlib.Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "_parallel_tests", ROOT / "scripts" / "parallel_tests.py"
)
assert _SPEC is not None and _SPEC.loader is not None
parallel = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = parallel
_SPEC.loader.exec_module(parallel)

_NAMES = st.from_regex(r"[a-z]{1,8}_test", fullmatch=True)


class ChunkingTest(unittest.TestCase):
    @given(
        st.dictionaries(_NAMES, st.integers(min_value=1, max_value=50_000), max_size=60),
        st.integers(min_value=1, max_value=16),
    )
    def test_every_module_is_in_exactly_one_chunk_heaviest_first(self, weights, workers) -> None:
        chunks = parallel.chunked(weights, workers)

        listed = [module for chunk in chunks for module in chunk.modules]
        self.assertEqual(sorted(listed), sorted(weights))
        self.assertEqual(
            [chunk.weight for chunk in chunks], sorted((c.weight for c in chunks), reverse=True)
        )
        for chunk in chunks:
            self.assertEqual(chunk.weight, sum(weights[module] for module in chunk.modules))

    def test_discovery_matches_the_unittest_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tests = pathlib.Path(raw)
            for name in (
                "a_test.py",
                "b_e2e_test.py",
                "helper.py",
                "c_test.txt",
                "bad-name_test.py",
            ):
                (tests / name).write_text("", encoding="utf-8")

            self.assertEqual(parallel.discover("*_test.py", tests), ("a_test", "b_e2e_test"))
            self.assertEqual(parallel.discover("*e2e_test.py", tests), ("b_e2e_test",))

    def test_the_worker_count_comes_from_the_variable_or_the_usable_cpus(self) -> None:
        self.assertEqual(parallel.worker_count({parallel.WORKERS_VARIABLE: "3"}), 3)
        self.assertGreaterEqual(parallel.worker_count({}), 1)
        for bad in ("0", "-1", "two"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parallel.worker_count({parallel.WORKERS_VARIABLE: bad})


def _suite(tests: pathlib.Path, *, failing: bool) -> None:
    (tests / "helper.py").write_text("VALUE = 2\n", encoding="utf-8")
    # Imported by its top-level name, as discovery imports it: `from helper import` only works
    # with tests/ on sys.path.
    (tests / "one_test.py").write_text(
        textwrap.dedent(
            """
            import unittest
            from helper import VALUE

            class One(unittest.TestCase):
                def test_value(self):
                    self.assertEqual(VALUE, 2)

                def test_name(self):
                    self.assertEqual(__name__, "one_test")
            """
        ),
        encoding="utf-8",
    )
    (tests / "two_test.py").write_text(
        textwrap.dedent(
            f"""
            import unittest

            class Two(unittest.TestCase):
                def test_holds(self):
                    self.assertTrue({not failing})
            """
        ),
        encoding="utf-8",
    )


def _run(tests: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, str(ROOT / "scripts" / "parallel_tests.py"), "--tests", str(tests)),
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", parallel.WORKERS_VARIABLE: "2"},
        check=False,
    )


class ParallelRunTest(unittest.TestCase):
    def test_a_passing_suite_runs_every_test_once_and_says_ok(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tests = pathlib.Path(raw)
            _suite(tests, failing=False)

            completed = _run(tests)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("Ran 3 tests", completed.stdout)
        self.assertTrue(completed.stdout.rstrip().endswith("OK"), completed.stdout)

    def test_a_failing_test_fails_the_run_and_its_output_is_shown(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tests = pathlib.Path(raw)
            _suite(tests, failing=True)

            completed = _run(tests)

        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("FAIL: test_holds", completed.stdout)
        self.assertIn("Ran 3 tests", completed.stdout)
        self.assertIn("FAILED (1 of", completed.stdout)

    def test_a_slow_example_is_not_a_failure_under_load(self) -> None:
        # Hypothesis's 200 ms deadline measures the machine: ten workers under coverage pushed
        # sound property tests to 300 ms. The runner turns the deadline off, not the property.
        with tempfile.TemporaryDirectory() as raw:
            tests = pathlib.Path(raw)
            (tests / "slow_test.py").write_text(
                textwrap.dedent(
                    """
                    import time
                    import unittest
                    from hypothesis import given, settings, strategies as st

                    class Slow(unittest.TestCase):
                        @settings(max_examples=2, database=None)
                        @given(st.integers())
                        def test_slow(self, value):
                            time.sleep(0.3)
                    """
                ),
                encoding="utf-8",
            )

            completed = _run(tests)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("Ran 1 test", completed.stdout)


if __name__ == "__main__":
    unittest.main()
