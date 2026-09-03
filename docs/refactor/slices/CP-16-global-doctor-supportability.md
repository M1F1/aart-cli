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
2. **VERIFIED:** report 165.11's three offline capabilities before installation (B-051), without
   collapsing them into one online/offline answer.
3. **VERIFIED:** add safe repair review and finalize entry points. Re-inspect and re-plan under the same
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

### Step 2 — three offline capabilities remain three observations (D-140)

`tests/doctor_offline_readiness_e2e_test.py` drives the public `aart doctor` before any install. A
real approved vendored Skill reports source and artifact metadata cached, its canonical payload
cached, and runtime dependencies not required. A real referenced publication keeps the metadata
but reports the payload missing. A packaged MCP declaration proves that a cached payload does not
invent dependency readiness: because AART has no durable package-manager cache inventory, declared
dependencies are honestly `unverified`. Removing the real Source store reports cold metadata and
no invented artifacts. Human output names the same three capabilities separately and does not call
the artifact installed.

The observation is environment-wide rather than a single-source shortcut. One scenario configures
an ignored disabled registry, an unsynchronized registry, a synchronized local Source and the
approved registry; Doctor reports every enabled source and does not parse the ordinary Source as a
registry. A mixed referenced/vendored registry proves one missing payload does not stop later
artifacts from being reported. A real lifecycle transition to deprecated proves unavailable
metadata is not presented as installable offline.

The first five tests were RED with `KeyError: offline_readiness` (and absent human text). Three
manual mutations independently made the canonical payload always cached, dependencies always
`not-required`, and cold metadata cached; each turned only its named public claim red. Fresh scoped
mutation runs then found and closed the multi-source, ordinary-Source, multi-artifact and lifecycle
filter gaps. The pure application projection killed all 30 mutants. The final I/O run killed 73 of
76; two survivors alter the currently unproducible Collection filter spelling, and one changes
`False` to `None` in a falsey input whose public state is identically `missing/unverified`. Per
D-134 they are findings, not a score or a reason to invent a fixture outside the active capability.

### Step 3 — one reviewed plan is applied, and only that one (D-141)

`tests/doctor_repair_command_e2e_test.py` drives `aart doctor --repair` over a real canonical
installation whose delivered file has been removed outside AART. Review and finalize are two
separate command invocations, and the digest the first returns is authorization input to the second.

Without `--yes`, the command returns a complete plan — the review digest, the components changing,
and the same minimal plan the read-only report already serializes — and the delivered file is still
absent afterwards, so the review did not quietly apply its own repair. The human rendering names the
same delta, the review identity and the confirmation boundary, and neither surface contains the word
`reinstall`. With `--yes` and the matching digest, the repair runs, records a `repair` receipt whose
steps equal the observed drift, and a following `aart doctor` reports `{"ready": 1,
"needs_attention": 0}` — health measured by the same read that found the damage, not by the repair
reporting on itself.

The refusals are the substance. `--yes` without `--expect` is refused as `consumer-review-mismatch`
and repairs nothing. A machine moved between review and confirmation returns the *recomputed* plan
alongside the stale expectation instead of applying the old one, and leaves the new drift untouched.
And because a digest comparison in the command would only prove the command re-planned, the last
scenario moves the machine *after* the command's own re-plan, inside the lifecycle call: the effect
is refused as `execution-review-stale`, which is the adapter re-observing under its lease rather than
the command trusting what it computed a moment earlier.

Five mutations, each turning red only the claim it belongs to: inverting the review branch (7 tests);
never comparing `--expect` to the recomputed digest (2); dropping the version half of exactness (1
subtest); dropping the source half (1 subtest); and hardcoding project scope (1).

**The finding is in the exactness test.** It was named "source and version", but its only input
omitted the source — so removing the version requirement entirely killed nothing, and half the name
was unheld. It now runs both under-specified forms as subtests, and each half of the mutation kills
exactly its own subtest. This is the same shape as CP-15's D-138 finding, arriving from the opposite
direction: there an absence was asserted where it could not have been present, here a conjunction was
asserted with only one conjunct ever supplied.

One survivor is recorded rather than chased: weakening the exactly-one-match guard from `!= 1` to
`< 1` kills nothing, because a second installation of one identical coordinate in one scope is not
known to be representable. B-059 records it as defensive code of unproven reachability; per D-134 a
survivor outside the increment's claims is a finding, not a reason to invent a fixture.

## Quality gates

- Baseline before CP-16: `make quality` green (3,237 tests, 1 skipped, 85.32% branch coverage) and
  `make integration` green (273 E2E tests) at `33054a0`.
- Step 1 focused: six Doctor E2E tests green; nearby consumer navigation/shell tests and typecheck
  were green before the final receipt-refusal addition. Fresh scoped mutation run: 132 total, 104
  killed, 28 survivors, none untested.
- Step 1 full gates: `make quality` green -- all nine gates, 3,243 tests, 1 skipped, 85.34% branch
  coverage -- and `make integration` separately green with 279 E2E tests.
- Step 2 focused: eight offline-readiness E2E tests and all 24 tests in the four nearest suites are
  green; ruff, mypy over 255 source files, repository validation and diff checks are green. Scoped
  mutation: application projection 30/30 killed; I/O observation 73/76 killed with three reviewed
  survivors.
- Step 2 full gates: `make quality` green -- all nine gates, 3,251 tests, 1 skipped, 85.37% branch
  coverage -- and `make integration` separately green with 287 E2E tests.
- Step 3 focused: eight repair E2E tests (ten including subtests) green; five targeted mutations each red only where claimed.

## Remaining

Steps 4–5 above. Doctor now reviews and applies one explicitly confirmed minimal plan; the
remaining work is making Activity, Receipt, configuration, credential and orphaned-run diagnostics
reachable from the global report.

## Known compromises

- The current canonical inspection does not calculate Marketplace update availability, so Doctor
  reports installed health and machine drift without an update offer.
- Credential state is observable only where the platform provider exists; broader provider and
  configuration diagnostics belong to step 4.

## Backlog discoveries

- B-058: scoped mutmut results can remain stale after test-only changes.
- B-059: Doctor's exactly-one-match repair guard is defensive code of unproven reachability.

## Blockers

None for step 4.

## Legacy removal criteria

This slice adds a public support surface; it authorizes no legacy deletion by itself.

## Handoff

- Current working state: steps 1, 2 and 3 are VERIFIED; CP-16 remains IN PROGRESS.
- Exact next action: begin step 4 with a public RED over the support diagnostics the global
  report cannot yet reach.
- Do not undo: one observed installation set feeds both `project_doctor` and
  `prepare_configured_repair`; offline readiness reuses the installation package verifier but stops
  before object publication; Doctor mutates nothing unless
  `--repair --yes --expect` are all present, and the lifecycle adapter, not the command, is what
  re-observes the machine under its lease before any effect runs.
- Tests last run/results: `make quality` -- 3,251 green, 1 skipped, 85.37%; `make integration` --
  287 green.
- Failure evidence: the report's absence was the initial RED; payload, dependency, cold-metadata,
  source-loop and artifact-loop mutations each turn their named E2E assertion RED.
