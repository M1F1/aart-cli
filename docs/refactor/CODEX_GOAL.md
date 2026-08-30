# Codex Goal — Complete the AART refactor end-to-end

Refactor and complete the public **`M1F1/aart-cli`** repository until it implements the canonical
AART Product Specification end-to-end. Work autonomously and continue through the critical path
until completion or until a true external blocker makes further compliant work impossible.

## Mandatory first action

Read root `AGENTS.md`, then read:

`docs/product-specification/PRODUCT_SPECIFICATION.md`

This file is the sole product source of truth. Then read:

- `docs/refactor/EXECUTION_PLAN.md`
- `docs/refactor/MIGRATION_STATUS.md`
- `docs/refactor/NEXT.md`
- `docs/refactor/DECISIONS.md`
- `docs/refactor/BACKLOG.md`
- `docs/refactor/slices/README.md`

Do not begin architecture changes until you have done this.

## Repository boundary

Modify only `M1F1/aart-cli` for this refactor. Older repositories such as `M1F1/aart`,
`agent-artifacts`, `Agent Artifacts`, old registries and experiments are read-only reference
material. You may inspect them to recover behavior, fixtures or proven ideas, but never make them
the target, never merge their history into `aart-cli`, and never let them override the Product
Specification.

## Execution objective

Execute **all critical-path slices CP-00 through CP-18** in
`docs/refactor/EXECUTION_PLAN.md`.

Everything accepted in the Product Specification is mandatory. Use a strangler/vertical-slice
migration rather than a big-bang rewrite. Preserve current valid behavior with characterization
tests while progressively routing the product through the new domain/application/effect boundaries.

Do not stop after producing plans. Implement, test, integrate, migrate, remove obsolete authority
when verified, and continue to the next unblocked slice.

## Autonomous decision policy

This job may run unattended overnight. Do **not** wait for user answers when a safe answer can be
derived from:

1. the Product Specification and its invariants;
2. current `aart-cli` code and characterization tests;
3. current public standards intentionally supported by the specification;
4. the smallest conservative design that preserves every applicable invariant.

When you encounter an implementation ambiguity that does not change product semantics, choose the
smallest safe option, record the decision in `docs/refactor/DECISIONS.md`, add tests where needed,
and continue.

Ask/stop only for a genuine critical-path blocker requiring unavailable
credentials/permissions/infrastructure or a product choice where all available options would
violate or materially alter the Product Specification.

Before stopping, document the blocker, evidence, what remains possible independently, and continue
any independent critical-path work.

## Critical path vs discovery backlog

Do not allow incidental cleanup, refactoring opportunities or attractive features to derail the
critical path.

Any useful discovery that is not required to satisfy a mandatory invariant, current slice
acceptance criterion, security boundary or dependency must be appended to
`docs/refactor/BACKLOG.md` using its template and left for later.

Promote a backlog item to critical path only when concrete evidence proves the mandatory refactor
cannot be completed correctly without it. Record the evidence and update the execution documents.

## Engineering constraints

- Preserve **zero Python runtime dependencies** unless the Product Specification is explicitly
  changed. Dev/test tooling may use repository-approved dependencies.
- Use functional core / imperative shell: immutable typed domain data and pure transformations;
  explicit effects and interpreters for filesystem, Git, subprocess, credentials, network,
  terminal and clocks.
- Domain code must not perform IO or import interface/adapters.
- Planning never mutates. Effects never execute before policy/review semantics allow them.
- Secret values must never appear in registry content, plans, receipts, provenance, logs,
  exceptions, JSON output, snapshots, tests or TUI history.
- `CredentialReference` and credential values are distinct; planning does not read secret values.
- Use TDD: characterize/RED → GREEN → refactor → negative/property → integration →
  E2E/live acceptance.
- Use Hypothesis/property testing for invariants where appropriate and mutation testing for
  high-value pure domain logic when repository tooling supports it.
- Never weaken or delete a quality/security gate merely to make CI green.
- Reuse/refactor the existing persistent TUI; do not replace it with Textual/Rich unless the Product
  Specification is explicitly amended.
- Docker is not foundational for MCP. First required vertical slice is Python source-tree + stdio +
  isolated runtime + declarative inputs + generated runtime projection + harness adapter.
- AART is an installer/compiler/configurator, not an implicit runtime dependency after installation.
- Source, Candidate, Registry and Marketplace are separate domains.
- Source sync never promotes.
- Published coordinate@version content is immutable.
- Enterprise promotion vendors canonical payload by default and never pushes.
- Install/update/configure/repair/credential rotation/harness reconfiguration/downgrade/uninstall
  use desired-state reconciliation and minimal repair, not replay-everything workflows.
- Fast and Verbose UX are projections of the same plan/state; Fast cannot hide material risk.

## Durable progress protocol

At the start of each slice, create/update its file in `docs/refactor/slices/`.

During and after work keep the repository sufficient for another agent to resume without chat
context. At every meaningful checkpoint update:

- `docs/refactor/MIGRATION_STATUS.md`
- `docs/refactor/NEXT.md`
- the active slice file with done/remaining/tests/blockers/handoff
- `docs/refactor/DECISIONS.md` for material implementation choices
- `docs/refactor/BACKLOG.md` for noncritical discoveries

Never mark work complete based only on code existing. `VERIFIED` requires evidence; `MIGRATED`
requires real flows using the new path; `LEGACY REMOVED` requires safe removal after replacement is
proven.

## Git and quality behavior

Respect repository branch/PR/CI conventions. Keep commits/slices reviewable. Do not rewrite
unrelated user work. Do not force push or bypass protection.

Run focused tests while developing and the strongest relevant repository gates before each slice is
considered verified; run the complete quality/packaging/security/live-acceptance suite before final
completion.

## Completion condition

Continue until CP-00..CP-18 are completed with evidence, all mandatory Product Specification
behavior/invariants are implemented or explicitly proven already satisfied, accepted consumer TUI
01–29 and Maintainer TUI 30–53 are implemented, accepted edge cases 54–100 are covered, the
Git-backed end-to-end lifecycle passes, reconciliation and doctor work as specified, zero runtime
dependencies remain true, and the repository is release-ready under the accepted release model.

When finished, leave a final durable handoff containing: implemented slices, invariant/test
traceability, full gate results, any genuinely deferred backlog items, known limitations permitted
by the Product Specification, and the exact release readiness state.
