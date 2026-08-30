# AART Refactor — Next Work

## Current objective

Open **CP-11 Desired-state reconciliation engine** on the verified CP-07 planning pipeline, CP-08
input and credential algebras, CP-09 artifact-owned Python environments and the CP-10 runtime
projection.

CP-10 produced the first real drift vocabulary: `VerificationFinding` already names six ways an
installation stops matching its receipt, and `observe_installation` already measures them on a real
machine. CP-11's job is to generalise that into `DesiredState` / `CurrentState` / `Drift` and a
*minimal* `MutationPlan` — repairing only what drifted, using the `EffectCapabilities` metadata that
CP-07 put on every effect and nothing has yet consumed.

## Immediate next actions

1. Read Product Specification sections 116–130 alongside the CP-07 effect capability metadata, then
   characterize the legacy `setup_verify.py` and `setup_undo.py` behaviour before changing anything.
2. Write CP-11 RED tests for minimality: a plan that repairs one drifted thing touches nothing else,
   and a re-run after a successful repair produces an empty plan.
3. Model `DesiredState` and `CurrentState` as separate types. A reconciler that can read one as the
   other is a reconciler that can report "no drift" because it compared a thing to itself.
4. Re-inspect after mutation and prove convergence, rather than assuming the effects worked.
5. Make unsupported repair semantics explicit — an effect that is not `independently_repairable`
   must say so and escalate, not be quietly rebuilt.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker or OCI distribution (B-003);
- no changes to old AART repositories;
- no Source Sync promotion;
- no routing of the public install/repair flow yet — that is CP-12, on top of CP-11;
- no additional harness targets that have not been measured on a live build (B-020);
- no additional secret providers (B-004), installer backends, or transports beyond stdio;
- no backlog work unless it becomes a proven critical-path blocker.

## Carried forward

- CP-08: `TransientSecret` lives only in `io/`; nothing in `domain` or `application` may gain a
  field that can hold a secret value. `plan_credential_mutation` takes `policy` as a required
  keyword. Keychain replacement is delete-then-add (D-017). `domain/inputs.py` parses URLs itself.
- CP-09: `ArtifactEnvironment` paths are derived, never supplied. The runtime interpreters refuse
  effects outside the artifact they were constructed for, and the tests assert no process ran. A
  declared lock is refused, not ignored (D-021).
- CP-10: a launcher carries the command that reads a secret, never the secret (D-022). Stdin and
  file bindings stay refused (D-023, D-024). `LocalProjectionWriter` checks artifact ownership and
  re-digests after writing. Harness settings are merged, never replaced, and keep their permissions
  (D-026). Receipts fingerprint config values rather than copying them (D-027). An unmeasurable
  launcher counts as drift, never as a pass (D-028) — CP-11 must not soften this to make a
  reconciler converge.
