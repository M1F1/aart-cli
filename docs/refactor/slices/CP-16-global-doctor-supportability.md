# CP-16 — Global doctor and supportability
Status: IN PROGRESS (opened 2026-09-03)

## Goal

Implement `aart doctor` as an environment-wide inspection and reconciliation surface: readable
diagnostics for people, machine-complete JSON for automation, and safe repair entry points backed by
the canonical reconciliation engine. Doctor must never mean reinstall-all.

## Product Specification sections/invariants

- Section 161.11, accepted screen 29 / CLI equivalent `aart doctor`.
- INV-194: Doctor uses reconciliation, not reinstall-all.
- Section 165.11 / INV-223: offline installability remains three separately reportable
  capabilities -- metadata, canonical payload and runtime dependencies.
- INV-191 and INV-192: Activity and Receipt remain the audit and recovery evidence; Doctor must not
  invent stronger undo guarantees than a receipt carries.

## Legacy/current paths

- `application/consumer_views.py::project_doctor` and `tui_consumer.py::render_doctor` provide the
  accepted screen-29 projection and rendering.
- `io/consumer_machine.py::read_installed_inspections` observes durable canonical receipts.
- `application/reconciliation.py::plan_repair` is the sole minimal-repair planner, reached through
  `io/configured_repair_action.py::prepare_configured_repair`.
- `marketplace receipt show|verify|undo` and Activity views carry existing support evidence.

## Target paths/owners

- `agent_artifacts/commands/doctor.py` owns the public command composition and serialization.
- Existing application projections and reconciliation planning remain authoritative; the command
  does not calculate health or repair effects a second way.

## Non-goals

- Reinstall-all, implicit mutation, or applying a repair without review.
- Resolving Marketplace content merely to inspect what is already installed.
- Fixing noncritical supportability findings outside the active increment.

## Method

D-091 and D-134 apply. Each increment names the public verb, drives it over a real temporary
machine, and is proven red against a mutation of the behavior it claims. Hypothesis is used where a
claim is universal; scoped `make mutants` is advisory and its survivors are read as findings, not a
score.

## Implementation steps

1. **VERIFIED:** add the read-only, environment-wide `aart doctor` report over
   canonical project and user installations, using the existing health projection and canonical
   minimal-repair planner; expose complete JSON and readable screen-29 text.
2. **NEXT:** report 165.11's three offline capabilities before installation (B-051), without
   collapsing them into one online/offline answer.
3. Add safe repair review and finalize entry points. Re-inspect and re-plan under the same
   precondition discipline as every configured lifecycle action; apply only an explicitly reviewed
   minimal plan.
4. Make Activity, Receipt, configuration, credential and orphaned-run diagnostics usable from the
   global report without weakening their existing evidence or undo boundaries. Triage B-052 and
   B-055 here only where a mandatory invariant requires it.
5. Run the full public-flow, negative/property, integration and mutation-adequacy evidence; close
   the slice only when every declared invariant has a traceable public surface.

## Completed increments

### Step 1 — one observation feeds health and minimal repair planning (D-139)

`tests/doctor_command_e2e_test.py` installs two approved-registry Skills through the real public
command. On a healthy non-empty machine, `aart doctor` reports both and no repairs. After one
delivered file is edited outside AART, it reports one ready artifact and one needing attention,
names the divergent component, and serializes exactly one repair plan whose components equal the
observed drift. The human rendering lists the same two artifacts. A project installation and a
user-scope installation are both present in one run, proving "environment-wide" rather than merely
project-wide. Disabling the source after installation leaves Doctor functional, proving the read
does not turn into Marketplace resolution. Corrupting the real durable receipt yields a structured
`receipt-unreadable` refusal instead of an empty healthy machine.

The first characterization was RED because the top-level parser had no `doctor` command. Two
targeted mutations were then proven separately: including healthy plans made the healthy test RED,
and restricting the read to project scope made the project-plus-user test RED. Changing the state
directory's case survived on the case-insensitive Darwin filesystem and is equivalent on this
machine, so it is not claimed as evidence.

A fresh scoped run of
`make mutants ONLY=agent_artifacts/commands/doctor.py TESTS="tests/doctor_command_e2e_test.py"`
after the first five tests produced 132 mutants: 85 killed, 19 uncovered in the structured-error
branch, and 28 survivors. The receipt-corruption scenario was added specifically to execute that
branch. A second fresh run after its JSON and human assertions killed 104 and left 28 survivors,
with none untested. Survivors outside this increment's claims include equivalent JSON indentation,
unavailable platform credential providers, update metadata the current inspection does not compute,
and presentation whitespace. B-058 records that the wrapper otherwise reuses stale outcomes after
test-only changes.

## Quality gates

- Baseline before CP-16: `make quality` green (3,237 tests, 1 skipped, 85.32% branch coverage) and
  `make integration` green (273 E2E tests) at `33054a0`.
- Step 1 focused: six Doctor E2E tests green; nearby consumer navigation/shell tests and typecheck
  were green before the final receipt-refusal addition. Fresh scoped mutation run: 132 total, 104
  killed, 28 survivors, none untested.
- Step 1 full gates: `make quality` green -- all nine gates, 3,243 tests, 1 skipped, 85.34% branch
  coverage -- and `make integration` separately green with 279 E2E tests.

## Remaining

Steps 2–5 above. In particular, step 1 reports plans but deliberately applies none; a safe repair
entry point remains part of CP-16.

## Known compromises

- The current canonical inspection does not calculate Marketplace update availability, so Doctor
  reports installed health and machine drift without an update offer.
- Credential state is observable only where the platform provider exists; broader provider and
  configuration diagnostics belong to step 4.

## Backlog discoveries

- B-058: scoped mutmut results can remain stale after test-only changes.

## Blockers

None for step 2.

## Legacy removal criteria

This slice adds a public support surface; it authorizes no legacy deletion by itself.

## Handoff

- Current working state: step 1 is VERIFIED; CP-16 remains IN PROGRESS.
- Exact next action: implement step 2 from B-051, beginning with a public-flow RED for each of the
  three offline capabilities.
- Do not undo: one observed installation set feeds both `project_doctor` and
  `prepare_configured_repair`; Doctor is read-only and does not require source content.
- Tests last run/results: `python -m unittest tests.doctor_command_e2e_test` -- 6 green.
- Failure evidence: absent parser was the initial RED; healthy-plan and project-only mutations each
  turn their named E2E assertion RED.
