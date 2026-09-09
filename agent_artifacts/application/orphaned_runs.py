"""Pure projection of the working copies interrupted runs leave behind.

`setup_verify_probes.orphan_run_directories` already answers this question, but only for one
receipt's plan hash -- so an operator has to already know which run was interrupted. Being
interrupted is usually the reason they stopped watching, which makes that the one thing they
cannot supply. This projection carries whatever the run root holds, keyed by the plan-hash prefix
each run directory's own name encodes, so the global report can name a working copy without being
told where to look.

Reporting is the whole of it. `LAF-61` makes the probe report and never repair, and nothing here
widens that: a working copy is named, and left.

"Nothing is there" and "we could not look" are kept apart deliberately. A run root that cannot be
read is not an empty one, and an operator who is told there are no leftovers stops looking for
them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrphanedRun:
    """One working copy under the run root, and the plan its directory name points back at."""

    path: str
    plan_hash_prefix: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path:
            raise ValueError("an orphaned run needs the path it was left at")
        if not isinstance(self.plan_hash_prefix, str) or not self.plan_hash_prefix:
            raise ValueError("an orphaned run needs the plan-hash prefix its name encodes")


@dataclass(frozen=True, slots=True)
class OrphanedRuns:
    """Every working copy under one run root, or the fact that the root could not be read."""

    runs: tuple[OrphanedRun, ...] = ()
    readable: bool = True

    def __post_init__(self) -> None:
        # `readable` reaches JSON, where a falsey non-bool is `null` rather than `false` and a
        # consumer testing for `false` silently stops seeing the case.
        if not isinstance(self.readable, bool):
            raise ValueError("whether the run root could be read is a boolean")
        if any(not isinstance(item, OrphanedRun) for item in self.runs):
            raise ValueError("orphaned runs are inconsistent")
        if not self.readable and self.runs:
            raise ValueError("a run root that could not be read reports no runs")
        object.__setattr__(self, "runs", tuple(sorted(self.runs, key=lambda item: item.path)))


def orphaned_runs_to_data(observed: OrphanedRuns) -> dict[str, object]:
    """The machine-complete form, keeping "none" and "unknown" distinguishable."""

    return {
        "readable": observed.readable,
        "working_copies": [
            {"path": item.path, "plan_hash_prefix": item.plan_hash_prefix} for item in observed.runs
        ],
    }


def orphaned_run_lines(observed: OrphanedRuns) -> tuple[str, ...]:
    """The human rendering, which never offers to remove what it found."""

    if not observed.readable:
        return ("Interrupted runs: could not read the run directory, so leftovers are unknown.",)
    if not observed.runs:
        return ("Interrupted runs: no working copy was left behind.",)
    return (
        f"Interrupted runs: {len(observed.runs)} working "
        f"{'copy' if len(observed.runs) == 1 else 'copies'} left behind, not removed:",
        *(f"  {item.path} (plan {item.plan_hash_prefix})" for item in observed.runs),
        "Inspect each one before removing it yourself; AART reports these and does not delete them.",
    )
