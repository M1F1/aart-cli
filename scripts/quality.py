#!/usr/bin/env python3
"""Canonical, hermetic, non-mutating quality-gate runner for local use and CI."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
QUALITY_GATES = (
    "format-check",
    "lint",
    "typecheck",
    "unit",
    "integration",
    "validate",
    "coverage",
    "packaging-check",
    "docs-check",
    "secret-shape-check",
)


@dataclass(frozen=True)
class Gate:
    name: str
    commands: tuple[tuple[str, ...], ...]


def select_gates(requested: tuple[str, ...]) -> tuple[str, ...]:
    selected = QUALITY_GATES if not requested else requested
    unknown = tuple(name for name in selected if name not in QUALITY_GATES)
    if unknown:
        raise ValueError(f"unknown quality gate(s): {', '.join(unknown)}")
    if len(set(selected)) != len(selected):
        raise ValueError("quality gates must not be repeated")
    return selected


def snapshot_paths(paths: Iterable[Path]) -> tuple[tuple[str, int, str], ...]:
    snapshot: list[tuple[str, int, str]] = []
    for path in sorted(paths, key=lambda item: str(item)):
        if not path.exists() or not path.is_file():
            snapshot.append((str(path), -1, "missing"))
            continue
        stat = path.stat()
        snapshot.append(
            (str(path), stat.st_mode & 0o777, hashlib.sha256(path.read_bytes()).hexdigest())
        )
    return tuple(snapshot)


def git_listing(command: tuple[str, ...], root: Path) -> bytes:
    """Run a read-only git command, and say what git said when it refuses.

    ``check=True`` alone raises ``CalledProcessError``, which prints the argv and the exit code
    and throws away the one thing that explains the failure -- git's own message on stderr.  In a
    container that message is usually ``detected dubious ownership``, because the checkout belongs
    to the uid that ran ``actions/checkout`` and the job runs as another one.  Losing it turns a
    two-line fix into an afternoon.
    """
    result = subprocess.run(command, cwd=root, capture_output=True)
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip() or "(git said nothing)"
        raise SystemExit(
            f"{' '.join(command)} failed ({result.returncode}) in {root}\n"
            f"{detail}\n"
            "The gates read the working tree through git, so this stops them before any gate runs."
        )
    return result.stdout


def workspace_paths(root: Path) -> tuple[Path, ...]:
    listing = git_listing(
        ("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"), root
    )
    return tuple(root / raw.decode("utf-8") for raw in listing.split(b"\0") if raw)


def build_gates(temp_root: Path, python: str = sys.executable) -> tuple[Gate, ...]:
    coverage_data = temp_root / "coverage.data"
    paths = ("agent_artifacts", "tests", "scripts")
    return (
        Gate("format-check", ((python, "-m", "ruff", "format", "--check", *paths),)),
        Gate("lint", ((python, "-m", "ruff", "check", *paths),)),
        Gate("typecheck", ((python, "-m", "mypy", "--cache-dir", str(temp_root / "mypy")),)),
        Gate(
            "unit",
            ((python, "-m", "unittest", "discover", "-s", "tests", "-p", "*_test.py"),),
        ),
        # The end-to-end gate: every ``*e2e_test.py`` drives the real CLI over real trees.  It
        # replaced a shell script that drove the retired legacy commands and had no canonical
        # subject left once those were removed.
        Gate(
            "integration",
            ((python, "-m", "unittest", "discover", "-s", "tests", "-p", "*e2e_test.py"),),
        ),
        # `scripts/version.py check` used to run here too: it proved that three hand-maintained
        # version values agreed.  The release engine writes the one that is left, so there is
        # nothing left to reconcile and nothing for a gate to say about it (INV-085, INV-098).
        Gate("validate", ((python, "scripts/validate.py"),)),
        Gate(
            "coverage",
            (
                (
                    python,
                    "-m",
                    "coverage",
                    "run",
                    "--branch",
                    "--source=agent_artifacts",
                    f"--data-file={coverage_data}",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-p",
                    "*_test.py",
                ),
                (
                    python,
                    "-m",
                    "coverage",
                    "report",
                    f"--data-file={coverage_data}",
                ),
            ),
        ),
        Gate("packaging-check", ((python, "scripts/packaging_check.py"),)),
        Gate("docs-check", ((python, "scripts/docs_check.py"),)),
        Gate("secret-shape-check", ((python, "scripts/secret_shape_check.py"),)),
    )


# The three the developer extra installs.  Everything else a gate runs is either the standard
# library or a script in this repository.
_DEVELOPER_TOOLS = ("ruff", "mypy", "coverage")


def missing_tools(selected: tuple[str, ...], temp_root: Path) -> tuple[str, ...]:
    """Which developer tools the chosen gates need and this interpreter cannot import.

    Read off the gate commands rather than listed here, so a gate that starts using a tool is
    covered without anyone remembering to add it.
    """

    return tuple(
        tool for tool in _tools_for(selected, temp_root) if importlib.util.find_spec(tool) is None
    )


def _tools_for(selected: tuple[str, ...], temp_root: Path) -> tuple[str, ...]:
    by_name = {gate.name: gate for gate in build_gates(temp_root)}
    wanted: list[str] = []
    for name in selected:
        for command in by_name[name].commands:
            for index, argument in enumerate(command[:-1]):
                if argument == "-m" and command[index + 1] in _DEVELOPER_TOOLS:
                    wanted.append(command[index + 1])
    return tuple(dict.fromkeys(wanted))


def _report_tool_versions(absent: tuple[str, ...], selected: tuple[str, ...], temp: Path) -> None:
    """Say which version of each tool is about to run.

    `format-check` compares this machine's formatter against a file another machine's formatter
    wrote.  When the two differ the failure names a line and no cause, and the line looks fine.
    The versions are pinned in the developer extra for that reason; printing them makes a
    mismatch readable in the first four lines of a log instead of not at all.
    """

    if absent:
        return
    for tool in _tools_for(selected, temp):
        # From the installed distribution, not the module: `ruff` is a binary wrapper and carries
        # no `__version__`, which is exactly the tool whose version matters most here.
        try:
            found = importlib.metadata.version(tool)
        except importlib.metadata.PackageNotFoundError:  # pragma: no cover - importable, unlisted
            found = "(not an installed distribution)"
        print(f"{tool} {found}", flush=True)


def _discovered(pattern: str) -> frozenset[str] | None:
    """Every test id `pattern` would run, or ``None`` if discovery cannot say.

    Used to *prove* one gate's tests are a subset of another's before skipping it.  An import
    error during discovery makes this return ``None``, and an unprovable subset is never skipped.
    """

    import unittest

    def identifiers(suite) -> list[str]:
        found: list[str] = []
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                found.extend(identifiers(item))
            else:
                found.append(item.id())
        return found

    try:
        names = identifiers(unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern))
    except Exception:  # pragma: no cover - a broken discovery is the gate's job to report
        return None
    if any(name.startswith(("unittest.loader._FailedTest", "_FailedTest")) for name in names):
        return None
    return frozenset(names)


def redundant_gates(selected: tuple[str, ...]) -> dict[str, str]:
    """Which selected gates would re-run tests another selected gate already runs.

    `integration` discovers `*e2e_test.py`; `unit` discovers `*_test.py`, which matches those same
    files.  That containment is checked here rather than assumed, so changing either pattern makes
    the runner stop skipping instead of silently dropping a gate.
    """

    if "integration" not in selected or "unit" not in selected:
        return {}
    every, subset = _discovered("*_test.py"), _discovered("*e2e_test.py")
    if every is None or subset is None or not subset or not subset <= every:
        return {}
    return {
        "integration": (
            f"all {len(subset)} of its tests are among the {len(every)} the unit gate runs"
        )
    }


def changed_paths(root: Path, base: str | None = None) -> tuple[str, ...]:
    """Every tracked path this working tree has changed, including untracked new files.

    When `base` is given, changes against it are included, so a branch's whole diff is considered
    rather than only what is currently uncommitted.
    """

    found: set[str] = set()
    commands = [
        ("git", "diff", "--name-only", "HEAD"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    ]
    if base:
        commands.append(("git", "diff", "--name-only", f"{base}...HEAD"))
    for command in commands:
        for line in git_listing(command, root).decode("utf-8").splitlines():
            if line.strip():
                found.add(line.strip())
    return tuple(sorted(found))


def _affected_gates(
    selected: tuple[str, ...], temp_root: Path, root: Path, base: str | None
) -> tuple[tuple[Gate, ...], dict[str, str], str]:
    """Rewrite the test gates to run only what the change could have reached.

    Returns the gates to run, the gates to skip with their reason, and a line explaining the
    narrowing.  When the analysis declines, nothing is rewritten and every gate runs.
    """

    import importlib.util as _util

    specification = _util.spec_from_file_location("_affected", root / "scripts" / "affected.py")
    if specification is None or specification.loader is None:  # pragma: no cover - shipped file
        return build_gates(temp_root), {}, "affected-test analysis is unavailable"
    affected = _util.module_from_spec(specification)
    sys.modules[specification.name] = affected
    specification.loader.exec_module(affected)

    changed = changed_paths(root, base)
    selection = affected.select(changed, root=root)
    if not selection.complete:
        return build_gates(temp_root), {}, f"running every test: {selection.reason}"
    if not selection.tests:
        return (
            build_gates(temp_root),
            {name: "nothing changed that any test reaches" for name in ("unit", "integration")},
            "no test reaches what changed",
        )

    python = sys.executable
    rewritten = tuple(
        Gate("unit", ((python, "-m", "unittest", *selection.tests),))
        if gate.name == "unit"
        else gate
        for gate in build_gates(temp_root)
    )
    return (
        rewritten,
        {
            "integration": "its tests are among the affected ones the unit gate just ran",
            # A percentage measured over part of a suite is not this repository's percentage, and
            # a threshold read off one would be meaningless in both directions.
            "coverage": "coverage is measured over the whole suite, so it belongs to `make quality`",
        },
        f"{selection.reason}; {len(changed)} path(s) changed",
    )


def _run(
    selected: tuple[str, ...],
    temp_root: Path,
    *,
    changed_only: bool = False,
    base: str | None = None,
    executed: list[str] | None = None,
) -> int:
    absent = missing_tools(selected, temp_root)
    if absent:
        # Named before anything runs, with the fix.  Otherwise the first gate exits on
        # `No module named ruff`, which is true and tells nobody what to do about it.
        print(
            f"missing developer tool(s): {', '.join(absent)}\n"
            f"The installed runtime has no dependencies; these are the gates' own tools.\n"
            "  poetry install --with dev\n"
            # The second route is not a fallback for people without Poetry: it is what CI runs.
            # Poetry takes an install source only from a block inside pyproject.toml, so it cannot
            # be pointed at a per-fork internal index; pip reads PIP_INDEX_URL and always could.
            f"  {sys.executable} scripts/dev_tools.py install"
            "   (the same pinned versions, installed with pip, which reads PIP_INDEX_URL)\n"
            "Four gates -- unit, integration, validate, docs-check -- need none of them and can "
            f"be run alone:\n  {sys.executable} scripts/quality.py unit",
            file=sys.stderr,
        )
        return 2

    _report_tool_versions(absent, selected, temp_root)

    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "RUFF_CACHE_DIR": str(temp_root / "ruff"),
        }
    )
    gates = build_gates(temp_root)
    redundant = redundant_gates(selected)
    if changed_only:
        gates, redundant, narrowing = _affected_gates(selected, temp_root, ROOT, base)
        print(
            f"\n== changed-only run: {narrowing}\n"
            "== this is the developer loop, not the release gate; run `make quality` before "
            "calling work verified.",
            flush=True,
        )
    by_name = {gate.name: gate for gate in gates}
    ran = [] if executed is None else executed
    for name in selected:
        if name in redundant:
            # Named, never silent: a gate that vanishes from a log reads as a gate nobody runs.
            print(f"\n==> quality gate: {name} -- skipped, {redundant[name]}", flush=True)
            continue
        print(f"\n==> quality gate: {name}", flush=True)
        for command in by_name[name].commands:
            print("+ " + " ".join(command), flush=True)
            result = subprocess.run(command, cwd=ROOT, env=environment)
            if result.returncode:
                print(f"quality gate FAILED: {name} ({result.returncode})", file=sys.stderr)
                return result.returncode
        ran.append(name)
    return 0


def main(argv: tuple[str, ...] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    changed_only = "--changed" in arguments
    base = next(
        (item.split("=", 1)[1] for item in arguments if item.startswith("--since=")),
        None,
    )
    arguments = [
        item for item in arguments if item != "--changed" and not item.startswith("--since=")
    ]
    try:
        selected = select_gates(tuple(arguments))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    before_paths = workspace_paths(ROOT)
    before = snapshot_paths(before_paths)
    executed: list[str] = []
    with tempfile.TemporaryDirectory(prefix="aart-quality-") as raw:
        result = _run(selected, Path(raw), changed_only=changed_only, base=base, executed=executed)
    after_paths = workspace_paths(ROOT)
    after = snapshot_paths(after_paths)
    if before_paths != after_paths or before != after:
        print("quality gate mutated repository files", file=sys.stderr)
        return 3
    if result:
        return result
    # What ran, never what was asked for: a gate named on this line has actually passed.
    print("\nquality gates OK: " + ", ".join(executed))
    skipped = tuple(name for name in selected if name not in executed)
    if skipped:
        print("skipped as redundant or out of scope: " + ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
