# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**, step 2: compose the now-durable screen 30–32 Source Scan /
Candidate history into the production application, then implement Source Sync screens 33–34.

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

The next pure increment is also green (D-093): `MaintainerDashboardView`,
`MaintainerSourceView`, `MaintainerViews` and `tui_maintainer.py` render screen 30, Source list and
Source detail from matching typed `ConfiguredSource` + `SourceHealth` + `SourceScan` observations.
They are integrated with `CanonicalScreenSource` but intentionally not yet composed in production.
Affected evidence: 1,255 tests and all changed-file gates green.

The durability prerequisite is now implemented (D-094): a strict canonical Candidate-history index
references retained content-addressed compiled artifact envelopes beneath each managed Source
instance. Private atomic writes publish objects before replacing the index; reads distinguish absent
history from corrupt, missing-object or symlinked state. RED-first evidence lives in
`candidate_history_test.py` and `candidate_store_test.py`.

Latest full repository evidence: 2,982 unit tests, 204 E2E tests, 83.37% branch coverage and every
quality, validation, packaging, documentation and secret-shape gate green on 2026-09-01.

## Exact next action

Start RED tests for one Maintainer composition reader and its production application journey:

1. Read configured authoring Source health and the matching persisted scan once, project D-093's
   views, and carry them in `ConsumerActionContext` so every redraw/action refresh retains the
   Maintainer snapshot.
2. Compose this reader in `_canonical_consumer_actions`; add a real-filesystem application test that
   enables Maintainer Mode and reaches screen 30 → Sources → Source detail without hand-injected
   views.
3. Implement screens 33–34 as reviewed Source Sync/result commands. Persist every successful
   compile + reconcile result with `write_candidate_history` while the configured Source instance
   lease remains held. A scan with `registry_mutations != ()` remains unrepresentable (INV-200).
4. Sync may fetch/discover,
   compile and update Candidate history, but must produce no registry mutation and no promotion
   (INV-200); discovery remains exact `aart.yaml`/`aart.json` only (INV-201).

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
