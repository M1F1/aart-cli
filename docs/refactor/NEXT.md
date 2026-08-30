# AART Refactor — Next Work

## Current objective

Open **CP-12 Installed lifecycle on reconciliation**: route install, update, configure, repair,
credential rotation, harness reconfiguration, downgrade and uninstall through the CP-11 engine, so
each intent becomes a desired state rather than its own procedure.

CP-11 produced a `RepairPlan` and nothing executes one yet. `repair_converged` exists, is tested,
and has never been called after real effects. That is the gap: this slice is where a plan becomes
an execution, and where the re-inspection that §158.8 requires actually runs.

## Immediate next actions

1. Read Product Specification sections 158.2–158.6 and the installed-lifecycle sections alongside
   `setup.py`, `lifecycle/application.py` and `setup_undo.py`, then characterize the current
   install/repair/uninstall behaviour before changing anything.
2. Write CP-12 RED tests for the property that matters: after executing a repair plan, a fresh
   inspection converges — and when it does not, that is reported as a failed repair rather than a
   successful one.
3. Build the executor over the existing interpreters (`LocalPythonRuntime`, `LocalProjectionWriter`,
   `LocalHarnessRegistry`, `MacOsKeychainProvider`), dispatching by effect type with no interpreter
   ever acting outside the artifact it was constructed for.
4. Express each intent as a desired state, per §158.6 — the intents share reconciliation machinery
   and must not grow parallel procedures.
5. Handle interrupted and partial outcomes explicitly: a plan that stopped halfway is a state to
   re-inspect, not a rollback to guess at.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker or OCI distribution (B-003);
- no changes to old AART repositories;
- no Source Sync promotion;
- no orphan detection (B-023) unless uninstall proves to need it;
- no additional harness targets that have not been measured on a live build (B-020);
- no additional secret providers (B-004), installer backends, or transports beyond stdio;
- no backlog work unless it becomes a proven critical-path blocker.

## Carried forward

- CP-08: `TransientSecret` lives only in `io/`; nothing in `domain` or `application` may gain a
  field that can hold a secret value. Keychain replacement is delete-then-add (D-017).
- CP-09: `ArtifactEnvironment` paths are derived, never supplied. Interpreters refuse effects
  outside the artifact they were constructed for, and the tests assert no process ran.
- CP-10: a launcher carries the command that reads a secret, never the secret (D-022). Stdin and
  file bindings stay refused. Harness settings are merged, never replaced (D-026). An unmeasurable
  launcher counts as drift (D-028).
- CP-11: desired and current are different types, and unobserved is drift, not a match (D-029).
  Establishing and correcting are separate effect lists (D-030). Steps run in dependency order
  (D-031). A forbidden repair fails the plan rather than being dropped (D-032) — CP-12 must not
  soften any of these to make an execution succeed.
