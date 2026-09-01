# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**, step 2: implement screen 30 and Sources screens 31–34
over the canonical Source scan and Candidate lifecycle.

CP-14 step 1 is complete (D-092):

- `MaintainerScreen` names every accepted screen 30–53 exactly once without widening the
  consumer-only catalog used by CP-13's completeness tests;
- the existing `ConsumerSession`, `ConsumerUiEvent`, `ConsumerUiCommand`, reducer, keymap and shell
  carry both catalogs, so there is still one application state machine;
- disabled Maintainer Mode removes the entire Maintainer graph and refuses a forged direct
  navigation event or invalid seeded state;
- enabled Maintainer Mode adds only screen 30 to the Dashboard roots, from which all screens 30–53
  are reachable through the accepted forward graph;
- the Dashboard now exposes its navigation roots as real cursor rows. This closes the discovered
  CP-13 reachability gap that otherwise made Settings—and therefore the Maintainer opt-in—unreachable
  from a default terminal session.

Evidence: `tests/maintainer_navigation_test.py`; 2,963 unit tests, 204 E2E tests, 83.45% branch
coverage, and every repository quality gate green on 2026-09-01.

## Exact next action

Start RED tests for immutable `MaintainerDashboardView` and Source list/detail projections in
`application/maintainer_views.py`:

1. Project screen 30 counts for configured Sources, Candidates, validation failures and Ready
   candidates, plus supplied recent maintainer activity. The projection takes already-read
   canonical values and no clock or IO.
2. Project screens 31–32 from canonical configured Source state and the CP-05 source scan: alias,
   URL, branch, last successful revision, explicit manifest count, invalid count and candidate
   summary.
3. Add a maintainer machine reader under `io/` that reads those inputs once at composition. Draws
   remain pure and never fetch, discover, validate or promote.
4. Add pure Fast/Verbose renderers in `tui_maintainer.py`, then compose them into the existing
   `CanonicalScreenSource` so screen 30 and Sources are reachable through the step-1 graph.
5. Add Source Sync review/result commands only after the read-only projections are green. Prove
   sync creates or updates Candidates while returning no registry mutation (INV-200), and prove
   discovery accepts only `aart.yaml`/`aart.json` (INV-201).

## Critical boundaries for this slice

- Product Specification is the sole product authority.
- Source, Candidate, Registry and Marketplace remain distinct values and screens (INV-199).
- Source Sync never promotes and never mutates approved registry state (INV-200).
- Maintainer review will be semantic diff first and raw file diff on demand (INV-202).
- Promotion vendors by default, does not push, and bulk promotion has one transaction boundary
  (INV-204–INV-206).
- Secret values never enter views, state, plans, receipts, logs, fixtures or committed files.
- `key_event` remains the only place a key's meaning is decided; no second TUI reducer or framework.
- Machine state is assembled once outside draw functions; application projections have no IO or
  clock.
- Do not retire legacy direct/local or Collection authority until the corresponding CP-14 public
  flow is proven. B-031, B-038 and B-039 remain ordered behind that evidence (D-091).
- Do not modify older AART repositories.

## Durable handoff rule

At the end of the next increment update `MIGRATION_STATUS.md`, this file, the CP-14 slice file,
`DECISIONS.md` for material choices and `BACKLOG.md` for noncritical discoveries. Run focused gates
after each TDD cycle and the full repository quality suite before calling a CP-14 segment verified.
