# AART Refactor — Next Work

## Current objective

Open **CP-13 Consumer TUI 01–29**: reuse the existing persistent stdlib/curses TUI and route its
consumer install and installed-lifecycle surfaces through the canonical Selection, plan,
input/credential, reconciliation and execution seams verified in CP-06–CP-12.

The semantic core now exists, but the public consumer still sees the characterized legacy catalog,
setup and lifecycle procedures. CP-13 is the strangler cutover: Fast and Verbose become two
projections of the same immutable plan/state, and the accepted screen catalog becomes executable
public behavior rather than documentation alone.

## Immediate next actions

1. Read Product Specification sections 149–163 and inventory current `tui.py`,
   `tui_marketplace.py`, `tui_layout.py`, `tui_failures.py`, `wizard.py`, consumer commands and their
   tests against accepted screens 01–29.
2. Create the CP-13 slice file and a screen-by-screen coverage table: existing/partial/missing,
   canonical application input, Fast projection, Verbose projection and acceptance test.
3. Characterize navigation/state persistence before changing it. Keep arrows/Enter/Esc/`/`/`?`/`q`,
   context shortcuts, Fast default and remembered presentation preference.
4. Introduce pure consumer view models over CP-06 Selection/Collections, CP-07 InstallPlan,
   CP-08 inputs/credential references and CP-11/12 health/reconciliation outcomes. Render both
   levels from those models; never plan inside a renderer.
5. Route one complete public vertical flow first: Marketplace multi-select → Collection preview →
   Required Inputs/remediation → review → progress/outcome → Installed/receipt → drift/repair.
6. Add accepted uninstall ownership explanations, credential retention choice, Registries,
   Credentials, Activity, Settings and Doctor entry point without implementing CP-16 doctor logic
   twice.

## Do not do yet

- no replacement with Textual/Rich or a second TUI framework;
- no Maintainer Mode screens 30–53 (CP-14), beyond preserving the existing opt-in boundary;
- no broad package moves or deletion of legacy authority before public replacement evidence;
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
