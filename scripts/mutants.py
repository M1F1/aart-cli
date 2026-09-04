#!/usr/bin/env python3
"""Run mutmut over one scope, and put the configuration back afterwards.

Mutation adequacy answers the question coverage cannot: a line that ran is not a line whose
behaviour anything asserts. mutmut answers it by changing the code and asking whether the suite
notices -- a mutant that survives is a claim nothing holds.

Two facts shape this script. mutmut 3.x takes no scope on the command line; it reads `[mutmut]` from
`setup.cfg` in the working directory and nothing else. And mutating this repository whole is days of
compute: ~40k statements at roughly three mutants a second. So the scope belongs to the run rather
than to the repository, and the only way to pass it is to write it into the config -- which this
script does, and then restores, so a tracked file is never left changed. Do not run it while a
quality gate is running: `scripts/quality.py` fails a run whose tracked files moved under it, and
that is the guard working, not a false alarm.

    python scripts/mutants.py --only agent_artifacts/setup_render.py \
        --tests tests/setup_render_test.py tests/verification_failure_e2e_test.py

Survivors are findings to read, not a number to drive to zero. A survivor outside the claims the
current slice makes is a backlog note; a survivor inside them is a test that does not hold what its
name says. Never weaken a test to change the figure. See `docs/refactor/DECISIONS.md` D-134.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "setup.cfg"


def _source_paths(only: list[str]) -> tuple[str, ...]:
    """Top-level trees mutmut must copy so every requested module is importable.

    The original runner always copied ``agent_artifacts``.  That made a request for a repository
    script look scoped while generating zero mutants, then fail test collection because the
    script was absent from mutmut's working copy.  The requested files already name the required
    roots; derive the copy set from them instead of carrying a package-specific second scope.
    """

    roots: set[str] = set()
    for raw in only:
        path = PurePosixPath(raw)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise ValueError(f"mutation scope must be a repository-relative path: {raw!r}")
        roots.add(path.parts[0])
    return tuple(sorted(roots))


def _section(only: list[str], tests: list[str]) -> str:
    source_paths = _source_paths(only)
    lines = ["[mutmut]"]
    if len(source_paths) == 1:
        lines.append(f"source_paths = {source_paths[0]}")
    else:
        lines.append("source_paths =")
        lines.extend(f"    {path}" for path in source_paths)
    if only:
        lines.append("only_mutate =")
        lines.extend(f"    {path}" for path in only)
    if tests:
        lines.append("pytest_add_cli_args_test_selection =")
        lines.extend(f"    {path}" for path in tests)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        nargs="+",
        required=True,
        metavar="PATH",
        help="source files to mutate; scope this to what the current slice changed",
    )
    parser.add_argument(
        "--tests",
        nargs="*",
        default=[],
        metavar="PATH",
        help="test files to run against each mutant; the whole suite when omitted, which is slow",
    )
    parser.add_argument("--max-children", type=int, default=4)
    arguments = parser.parse_args(argv)

    original = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else None
    CONFIG.write_text(_section(arguments.only, arguments.tests), encoding="utf-8")
    try:
        run = subprocess.run(
            [sys.executable, "-m", "mutmut", "run", "--max-children", str(arguments.max_children)],
            cwd=ROOT,
        )
        # Results are the point of the run, so print them even when mutmut exits non-zero: a run
        # that found survivors has done its job and still has something to say.
        subprocess.run([sys.executable, "-m", "mutmut", "results"], cwd=ROOT)
        return run.returncode
    finally:
        if original is None:
            CONFIG.unlink(missing_ok=True)
        else:
            CONFIG.write_text(original, encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
