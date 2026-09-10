# CP-20 — Operator clarity and reproducible testing

Status: IMPLEMENTED — AWAITING MANUAL RETEST

## Goal

Close the second manual-acceptance feedback batch without exposing internal screen identifiers,
mixing a connected Registry with the current project, or requiring hidden state from an earlier
test run. Give the operator a reviewed Registry-disconnect action, an installable MCP credential
scenario, a reproducible disposable lab and a separately reviewed CLI factory reset that touches
only AART-owned state.

## Product Specification authority

- 161.1 and INV-187: navigation and presentation remain understandable and safe.
- 161.5 and INV-197: automatic inspection is work in the canonical install flow, while conditional
  screens appear only when operator input or a decision is required.
- 161.7 and INV-199: Registry connections determine Marketplace availability and remain distinct
  from the local Registry workspace.
- 161.8, 161.9 and INV-206/INV-207: credential values stay out of plans, receipts and output.
- 161.10 and 164.8: Settings and Registry Maintainer use the accepted grouped projections.

## Scope and ordered work

1. **Finding capture (QA-044 through QA-052) — DONE.** The operator's exact observations are
   recorded in root `TODO.md`; this slice and `docs/refactor/plan.json` are the executable plan.
2. **Clarity and navigation (QA-044 through QA-048) — DONE.** Separate connected Registry
   snapshots from the local project, remove internal screen-number language, make Doctor repair
   target its visible row, omit a no-decision Automatic Inspection page from the Fast flow, let
   Success finish directly at Marketplace, and apply the requested vertical spacing.
3. **Registry disconnection (QA-050) — DONE.** Review the exact connection and local snapshot
   effects, preserve installed artifacts/receipts, and execute through the same configuration and
   managed-source transaction as `source remove`.
4. **Credential-capable MCP fixture (QA-049) — DONE.** Publish a safe local dummy MCP whose declared
   input exercises required-input and credential-management views without placing its value in
   tracked files or output.
5. **Disposable manual lab (QA-051) — DONE.** One setup command creates fresh isolated maintainer,
   consumer and Git state; one reset command removes only a marker-owned lab and can be rerun.
6. **Application factory reset (QA-052) — DONE.** A CLI-only, doubly confirmed command plans exact
   AART-owned configuration/data/cache paths, refuses unsafe targets and leaves projects, harness
   files, credentials owned by other tools and unrelated files alone.
7. **Verification and handoff — DONE.** Kill named semantic mutations, run scoped mutmut, relevant
   focused suites, full quality and integration gates, then update every durable status surface.

## Current evidence

Characterization tests were RED against the CP-19 state before each boundary changed. The focused
CP-20 set is green across 177 tests plus eight subtests. Six deliberate semantic mutations — section
spacing, credential observation, disconnect identity binding, lab ownership, reset confirmation and
fresh run identity — each turned its named test red before being reverted. Scoped mutmut killed
111/113 factory-reset mutants; its two survivors are equivalent normalization/encoding spellings.
The new section composition has no survivor; older width-arithmetic survivors remain B-107.

`make quality` is green: 3,677 tests, one skipped, 85.36% branch coverage, plus format, lint,
typecheck, validation, packaging, docs and secret-shape gates. The separate `make integration` is
green across all 381 E2E tests. A real disposable-lab smoke created three working repositories and
three local bare remotes on one unique `manual/7fd37689f593` branch, then the marker-bounded reset
removed the lab completely. B-108 did not reproduce in either closing gate and remains recorded as
an intermittent historical test-isolation finding rather than product behavior.

## Do not undo

- Never show internal screen numbers as operator guidance.
- Do not compare an arbitrary consumer project working tree with a connected Registry snapshot.
- Do not turn automatic inspection into a claim that requirements passed when no harness observation
  exists; omit a page that asks for no decision from the Fast path.
- Do not implement Registry disconnection as deletion of installed artifacts or receipts.
- Do not put a reusable credential value in a repository, plan, receipt, log or rendered frame.
- Do not let either reset command infer a broad deletion target or follow an unverified symlink.

## Handoff

- Current working state: all seven CP-20 implementation steps are complete and uncommitted on top
  of CP-19 commit `e9616dd`.
- Exact next action: operator manual retest through `make manual-test-setup`; accepted findings can
  then be checked in root `TODO.md` and the increment committed.
- Tests last run/results: 3,677-test quality gate green at 85.36% branch coverage; separate 381-test
  integration gate green; real setup/branch/reset smoke green.
- Failure evidence: retained in the characterization tests and QA-044 through QA-052.
