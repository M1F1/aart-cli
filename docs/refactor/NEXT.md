# AART Refactor — Next Work

## Current objective

Finish **CP-13 Consumer TUI 01–29**. Steps 1–4 of the slice are complete and verified: all 29
accepted screens have canonical projections and Fast/Verbose renderers over CP-06–CP-12 values, the
keyboard and the persistent application loop are pure and headlessly driven, and a consumer flow
E2E runs the real CP-12 installation through Installed → drift → repair → Activity → receipt →
ownership-aware uninstall.

What remains is the wiring that makes the canonical application the one a person actually reaches.

## Immediate next actions

1. **B-024** — continue the canonical screen assembly. Marketplace, artifact details and
   Collection preview/customize (02–04a) now draw from `MarketplaceEntry`/`MarketplaceCollectionEntry`
   offers. What remains is the plan-bearing half: screens 05–11 and 15–24 need a `ConsumerPlanView`
   and lifecycle views assembled from resolution, inspection and input binding, refreshed after an
   action rather than derived inside a draw. Build it once: CP-14 needs the same assembly for the
   maintainer catalog.
2. **B-025** — route the default TTY entry in `tui.py::run` to `run_consumer` behind the existing
   curses-availability check, keeping the legacy wizard reachable until step 6 evidence exists.
3. Route the public consumer commands (`install`, `update`, `uninstall`, `status`) through
   `plan_lifecycle_intent`/`execute_lifecycle` rather than the legacy setup queue, projecting their
   output with `consumer_plan_to_data` and `receipt_detail_to_data` so text, curses and `--json`
   are three renderings of one plan.
4. Only then step 6: retire legacy consumer semantic authority (`consumer/application.py`,
   `installation/*`, `setup_engine/*`, `lifecycle/application.py`) path by path, each removal
   preceded by a public-flow test proving the canonical path already carries it.
5. Update the CP-13 coverage table as each screen group moves from projection to live flow.

## Do not do yet

- no replacement with Textual/Rich or a second TUI framework;
- no Maintainer Mode screens 30–53 (CP-14), beyond preserving the existing opt-in boundary;
- no broad package moves or deletion of legacy authority before public replacement evidence;
- no second place where a key's meaning is decided: `key_event` is the only one (D-041);
- no clock in `application/`: `today` and a record's own timestamp are supplied (D-039);
- no new transport, credential provider, installer backend or unmeasured harness target;
- no Docker/OCI foundation (B-003), orphan classifier (B-023) or other backlog work;
- no changes to older AART repositories.

## Carried forward

- Product Specification is the only product authority; accepted screen numbers are contracts, not
  optional mockups.
- Fast and Verbose share selection, requirements, policy, plan digest, risks, effects and execution;
  only detail changes. Fast may compress review but never bypass it or hide material risk.
- Secret values never enter view models, history, snapshots, receipts or JSON. Credential UI is
  reference/provider/health/dependant oriented.
- CP-12 absent desired targets and reverse teardown order stay intact. Uninstall retains artifacts
  with remaining ownership and credentials by default.
- Scope mutations use compare-under-lock reviewed execution. Interrupted work is re-inspected and
  replanned; no UI action resumes an imperative instruction number.
- The legacy curses behavior is characterization evidence. Reuse it until canonical public-flow
  tests prove a specific path replaceable.
- Persisted identity is structural, never a printed form re-parsed (D-044); an unreadable record is
  reported rather than skipped, because a skipped receipt reads as an installation that never
  happened (D-045).
- An action that took effect is recorded even when it did not finish, and a rolled-back update
  leaves the previous record standing (D-046). Health is inspected, never inferred from the
  existence of a record.
