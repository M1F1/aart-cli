# CP-12 — Installed lifecycle on reconciliation
Status: VERIFIED

## Goal

Execute a `RepairPlan` through the real interpreters, re-inspect afterwards and report what
actually happened — then express install, update, configure, repair, credential rotation, harness
reconfiguration, downgrade and uninstall as desired states over the same machinery rather than as
eight separate procedures.

## Product Specification sections/invariants

Sections 158.2–158.10, 159 and 165.12–165.20; INV-169–INV-186 and INV-224–INV-230.

## Legacy/current paths

- `setup.py` and `lifecycle/application.py` own the current public install/apply workflow.
- `setup_undo.py` owns legacy rollback; `setup_verify.py` owns legacy verification.
- `store/` and `setup_receipt.py` own current receipt persistence.
- `io/store_lock.py` provides the hardened lease primitive reused by the canonical executor.

## Target paths/owners

- `application/execution.py`: reviewed executor, terminal outcome/receipt projection, re-inspection,
  update restoration and scope-lock port.
- `io/execution.py`: artifact-owned file/runtime/harness/credential effect interpreters and the
  hashed per-scope filesystem mutation lease.
- `application/intents.py`: all eight lifecycle intents, ownership retention and installed/
  Collection health propagation.
- `application/installed_state.py`: present and absent desired states derived from receipts.

## Dependencies

CP-07 through CP-11 are verified.

## Non-goals

- No TUI (CP-13/14).
- No new transports, providers, installer backends or harnesses.
- No orphan detection (B-023); uninstall removes only receipt-owned entries.

## Characterization / RED evidence

RED covered: a plan that runs but does not converge on re-inspection; a failure part-way leaving
later steps unattempted; an unclaimed effect; an incomplete plan; interruption and adapter
exceptions; a changed reviewed precondition; a busy scope; a reversible failed update; a
non-reversible partial update; ownership-retained uninstall; reverse-order real uninstall; and
component-specific intents trying to change unrelated components.

## Implementation steps

1. `execute_repair` applies in dependency order, stops after failure/interruption and always
   re-inspects; clean effect reports without convergence are not success.
2. `execute_lifecycle` acquires a per-scope lease, re-inspects and re-digests the reviewed plan
   inside the lease, executes, and releases on every terminal path.
3. Install/update/configure/repair/credential rotation/harness reconfiguration/downgrade/uninstall
   all create `LifecycleIntent` and call `plan_repair`; component-specific builders reject scope
   expansion.
4. An absent component is an explicit desired target. Uninstall lowers to owned removals in reverse
   dependency order; harness entries are removed before launchers/runtimes/roots.
5. Collection/direct/dependency ownership is subtracted before uninstall. Remaining ownership
   produces a no-mutation retained outcome. Credential removal is absent unless explicitly added.
6. Failed update restoration is a new reconciliation against the previous desired state, and is
   attempted only when every effect already applied declared itself reversible.

## Property tests

Executing a plan with no steps never touches an interpreter. Re-inspection runs after success,
failure, interruption and refusal. Review invalidation and scope contention mutate nothing.

## Integration tests

Real launcher, runtime and harness damage is repaired through the real interpreters and converges
on fresh inspection. The real filesystem lease proves same-scope exclusion and different-scope
independence.

## E2E/live acceptance

An MCP server damaged in each component in turn is minimally repaired and started through its
launcher. The same installation is then uninstalled by reverse reconciliation; its harness entry
and artifact root disappear while its credential provider entry remains.

## Quality gates

- Focused CP-12/cross-slice regression: 124 tests + 23 subtests green.
- Repository unit gate: 2,196 tests green.
- Repository integration gate: 65 E2E tests green.
- Coverage: 83.25% branch coverage.
- All ten repository quality gates green: format, lint, typecheck, unit, integration, validation,
  coverage, packaging, docs and secret-shape.

## Done

- CP-12 opened from verified commit `b109843`.
- Immutable execution outcomes distinguish converged, unconverged, failed, interrupted and
  unverified results and serialize the plan digest, applied/failed/unattempted steps and residual
  drift without a secret-value field.
- All eight lifecycle intents share `plan_repair` and keep update/downgrade direction semantic.
- Installed health projects Ready/Update/Attention/Broken; Collection health propagates the worst
  member and retains the member identities requiring attention.
- `RemoveOwnedPath` and `UnconfigureHarness` are explicit policy-visible effects; interpreters
  re-check ownership/context before acting.
- Same-scope mutations are serialized by a lease derived from a hash of the scope identity.

## Remaining

- Public consumer lifecycle migration and Fast/Verbose projections belong to CP-13.

## Known compromises

The legacy consumer CLI/TUI still invokes the characterized lifecycle application. CP-13 is the
public-flow migration point; this slice establishes and verifies the canonical path without
deleting that authority early.

## Blockers

None.

## Backlog discoveries

B-023 remains deferred: uninstall removes only entries named by its receipt and does not classify
unowned harness entries as orphans.

## Legacy removal criteria

`setup_verify.py`, `setup_undo.py` and the `lifecycle/application.py` replay path become removable
once CP-13 routes public lifecycle flows through this executor with characterization evidence
green.

## Handoff

- Current working state: CP-12 is VERIFIED and ready to commit.
- Exact next action: commit CP-12, then open CP-13 Consumer TUI 01–29.
- Do not undo: absent desired targets; reverse teardown order; compare-under-lock review digest;
  fresh-state resume; explicit credential retention; capability-gated update restoration.
- Tests last run/results: 2,196 unit + 65 E2E, 83.25% branch coverage and all ten gates green.
- Failure evidence: none outstanding.
