#!/usr/bin/env python3
"""Run the unittest suite in parallel processes, optionally under coverage (D-466).

One process ran every test module in turn, and the full gate ran the suite twice -- once for
`unit` and again for `coverage` -- on each interpreter, so a pull request waited about forty
minutes for work a four-core runner can do in a fraction of that. This runner keeps unittest and
its discovery semantics and changes only how many processes do the work.

The test modules are split into chunks, heaviest first, and a pool of worker processes takes the
next chunk as it finishes the last one, so one slow module does not hold a fixed shard back. Each
worker imports its modules exactly as `python -m unittest discover -s tests` does: `tests/` first
on `sys.path` and every module by its top-level name. With `--coverage DATAFILE` every worker runs
under `coverage run --parallel-mode` and the data files are combined into DATAFILE at the end.

Standard library only, plus `coverage` when asked for: the runtime has no dependencies and this
script is not part of it.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
WORKERS_VARIABLE = "AART_CLI_TEST_WORKERS"
#: Chunks per worker. More chunks balance better and cost one interpreter start each.
_CHUNKS_PER_WORKER = 4
_RAN = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    modules: tuple[str, ...]
    weight: int


@dataclass(frozen=True)
class Outcome:
    chunk: Chunk
    returncode: int
    tests: int
    seconds: float
    output: str


def discover(pattern: str, tests: Path = TESTS) -> tuple[str, ...]:
    """The modules `unittest discover -s tests -p PATTERN` would load, by top-level name."""

    return tuple(
        sorted(
            path.stem
            for path in tests.glob("*.py")
            if fnmatch.fnmatch(path.name, pattern) and path.stem.isidentifier()
        )
    )


def chunked(weights: dict[str, int], workers: int) -> tuple[Chunk, ...]:
    """Split modules into about `workers * 4` chunks of similar weight, heaviest first.

    A module heavier than a chunk's share is a chunk of its own. Every module is in exactly one
    chunk, which is what makes the parallel run the same suite as the serial one.
    """

    if not weights:
        return ()
    share = max(sum(weights.values()) // max(workers * _CHUNKS_PER_WORKER, 1), 1)
    chunks: list[Chunk] = []
    current: list[str] = []
    load = 0
    for module in sorted(weights, key=lambda name: (-weights[name], name)):
        if current and load + weights[module] > share:
            chunks.append(Chunk(tuple(current), load))
            current, load = [], 0
        current.append(module)
        load += weights[module]
    if current:
        chunks.append(Chunk(tuple(current), load))
    return tuple(sorted(chunks, key=lambda chunk: (-chunk.weight, chunk.modules)))


def worker_count(environ: dict[str, str] | None = None) -> int:
    """The processes to run at once: AART_CLI_TEST_WORKERS, else the CPUs this process may use."""

    environment = os.environ if environ is None else environ
    raw = environment.get(WORKERS_VARIABLE, "").strip()
    if raw:
        if not raw.isdigit() or int(raw) < 1:
            raise ValueError(f"{WORKERS_VARIABLE} must be a positive whole number, not {raw!r}")
        return int(raw)
    affinity = getattr(os, "sched_getaffinity", None)
    return max(len(affinity(0)) if affinity is not None else (os.cpu_count() or 1), 1)


def _command(chunk: Chunk, python: str, coverage: Path | None, tests: Path) -> tuple[str, ...]:
    runner = (str(Path(__file__).resolve()), "--tests", str(tests), "--worker", *chunk.modules)
    if coverage is None:
        return (python, *runner)
    return (
        python,
        "-m",
        "coverage",
        "run",
        "--branch",
        "--source=aart_cli",
        "--parallel-mode",
        f"--data-file={coverage}",
        *runner,
    )


def _run_chunk(chunk: Chunk, python: str, coverage: Path | None, tests: Path) -> Outcome:
    started = time.monotonic()
    completed = subprocess.run(
        _command(chunk, python, coverage, tests),
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    output = completed.stdout or ""
    tests = sum(int(match) for match in _RAN.findall(output))
    return Outcome(chunk, completed.returncode, tests, time.monotonic() - started, output)


def _without_deadline() -> None:
    """Turn off Hypothesis's per-example deadline in this worker, when Hypothesis is installed.

    The deadline is a wall-clock limit of 200 ms. With every core busy, and more so under
    coverage, sound property tests took 300 ms and failed as `DeadlineExceeded`. What a property
    holds does not depend on how loaded the machine is; a test that sets its own deadline keeps it.
    """

    try:
        from hypothesis import settings
    except ImportError:
        return
    settings.register_profile("aart-cli-parallel", deadline=None)
    settings.load_profile("aart-cli-parallel")


def run_worker(modules: tuple[str, ...], tests: Path = TESTS) -> int:
    """Run `modules` in this process the way `unittest discover -s tests` imports them."""

    for path in (str(ROOT), str(tests)):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
    _without_deadline()
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def run(
    modules: tuple[str, ...],
    *,
    workers: int,
    python: str = sys.executable,
    coverage: Path | None = None,
    tests: Path = TESTS,
) -> int:
    weights = {module: (tests / f"{module}.py").stat().st_size for module in modules}
    chunks = chunked(weights, workers)
    workers = max(min(workers, len(chunks)), 1)
    print(
        f"running {len(modules)} test modules in {len(chunks)} chunks on {workers} worker(s)"
        + (" under coverage" if coverage is not None else ""),
        flush=True,
    )
    started = time.monotonic()
    failed: list[Outcome] = []
    total = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for outcome in pool.map(lambda chunk: _run_chunk(chunk, python, coverage, tests), chunks):
            total += outcome.tests
            state = "ok" if outcome.returncode == 0 else f"FAILED ({outcome.returncode})"
            print(
                f"  {state}: {outcome.tests} tests in {outcome.seconds:.0f}s "
                f"({len(outcome.chunk.modules)} modules, first {outcome.chunk.modules[0]})",
                flush=True,
            )
            if outcome.returncode:
                failed.append(outcome)
    for outcome in failed:
        print(f"\n===== {' '.join(outcome.chunk.modules)}\n{outcome.output}", flush=True)
    elapsed = time.monotonic() - started
    print(f"\nRan {total} tests in {elapsed:.3f}s across {workers} worker(s)", flush=True)
    if failed:
        print(f"FAILED ({len(failed)} of {len(chunks)} chunks)", flush=True)
        return 1
    if coverage is not None:
        combined = subprocess.run(
            (python, "-m", "coverage", "combine", "--quiet", f"--data-file={coverage}"),
            cwd=ROOT,
            check=False,
        )
        if combined.returncode:
            return combined.returncode
    print("OK", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pattern", default="*_test.py", help="discovery pattern under tests/")
    parser.add_argument("--tests", type=Path, default=TESTS, help="the test directory")
    parser.add_argument("--coverage", type=Path, help="run under coverage into this data file")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("modules", nargs="*", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if arguments.worker:
        return run_worker(tuple(arguments.modules), arguments.tests.resolve())
    try:
        workers = worker_count()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    tests = arguments.tests.resolve()
    modules = tuple(arguments.modules) or discover(arguments.pattern, tests)
    return run(modules, workers=workers, coverage=arguments.coverage, tests=tests)


if __name__ == "__main__":
    sys.exit(main())
