"""Read the run root once and report every working copy still standing in it."""

from __future__ import annotations

import os

from agent_artifacts.application.orphaned_runs import OrphanedRun, OrphanedRuns


def read_orphaned_runs(*, run_root: str) -> OrphanedRuns:
    """Every directory under the run root, which a completed run removes and a stopped one does not.

    The root is handed in rather than derived here. `LAF-66` was this path being composed in two
    places that disagreed -- the probe from the project root, the engine from the data root -- so
    the claim answered `true` in every scope without ever looking where runs are made. There is one
    source for it and the caller supplies it, exactly as `orphan_run_directories` now does.
    """

    if not run_root:
        return OrphanedRuns(readable=False)
    runs_root = os.path.join(run_root, ".agent-artifacts", "setup-runs")
    try:
        entries = sorted(os.listdir(runs_root))
    except FileNotFoundError:
        # No run has ever opened a working copy here, which is a real "none", not a failure to look.
        return OrphanedRuns()
    except OSError:
        return OrphanedRuns(readable=False)
    found = []
    for entry in entries:
        path = os.path.join(runs_root, entry)
        if not os.path.isdir(path):
            continue
        prefix, separator, _ = entry.partition("-")
        if not separator or not prefix:
            continue
        found.append(OrphanedRun(path, prefix))
    return OrphanedRuns(tuple(found))
