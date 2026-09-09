# AART Refactor Execution Plan

> **Target:** `M1F1/aart-cli` only.
> **Authority:** `docs/product-specification/PRODUCT_SPECIFICATION.md`.
> **Mode:** autonomous, TDD-first, strangler migration, critical-path first.

## Definition of success

The refactor is complete when the public `aart-cli` implementation satisfies the accepted Product
Specification, all mandatory invariants are covered by appropriate tests, consumer and maintainer
flows are implemented, the MCP vertical slice works end-to-end, desired-state reconciliation drives
lifecycle operations, Git-backed live acceptance passes, legacy paths no longer hold product
authority, and the repository's full quality/release gates are green.

That definition was met by CP-18. CP-19 is the follow-on post-refactor manual acceptance program;
its open status does not retroactively reopen the verified refactor or its invariant evidence.

## Non-negotiable execution rules

1. Do not refactor old AART repositories. They are read-only reference material.
2. Do not rewrite everything at once. Deliver vertical slices with characterization and acceptance evidence.
3. Product Specification invariants are mandatory acceptance criteria, not suggestions.
4. Preserve zero runtime dependencies.
5. Planning is pure; effects are explicit and interpreted at boundaries.
6. Secrets never enter plans, receipts, registry, provenance, logs, JSON output, TUI history or tests.
7. Fast and Verbose are projections of the same semantic plan/state.
8. Installation/update/configure/repair/credential rotation/uninstall share reconciliation machinery.
9. Registry/source/candidate/marketplace remain distinct.
10. Anything noncritical discovered during a slice goes to BACKLOG instead of expanding scope.

## Critical path

### CP-00 — Canonical planning baseline
Create and commit Product Specification, AGENTS contract, execution plan, migration tracker,
decision log, next-work file, slice template, Codex goal and discovery backlog. Confirm target is
`M1F1/aart-cli`.

### CP-01 — Repository characterization and invariant map
Inventory current `agent_artifacts` modules, CLI/TUI behavior, protocols, tests, quality gates and
live acceptance. Build a traceability matrix from Product Specification invariants to existing/new
modules and tests. Add characterization tests where refactoring could change accepted behavior. No
broad moves yet.

### CP-02 — Clean architecture migration seam
Establish/normalize target boundaries:
domain → application services → ports → adapters/interpreters → interfaces.
Introduce typed immutable results/diagnostics and pure state transitions without breaking existing
commands. Enforce domain import boundaries with tests/static checks.

### CP-03 — Five core algebras
Implement/refine Artifact, Requirement, Remediation, Effect and Policy ADTs plus risk classes,
capabilities, compatibility, provenance and shared identifiers. Add determinism, serialization and
policy monotonicity property tests.

### CP-04 — Native authoring manifest and canonical compiler
Implement explicit `aart.yaml`/`aart.json` discovery, safe payload selection,
authoring→canonical compilation, input digesting, canonical `artifact.json + payload/`, compliance
states and importer boundary. No heuristic repository crawling.

### CP-05 — Source, Candidate, Registry and Promotion lifecycle
Implement source synchronization, candidate lifecycle/diff/validation/rejection/superseding,
vendored promotion, immutable coordinate@version rules, provenance, registry
validation/snapshots, last-known-good, deprecation/revocation and publication semantics.
Promotion never pushes.

### CP-06 — Marketplace Selection, Collections and resolution
Implement aggregated multi-registry marketplace semantics, explicit ambiguity, multi-select
Selection, exact Collections vs custom selections, ownership reasons, dependency/version resolution
and conflicts. One active version per coordinate/scope in V1.

### CP-07 — Inspection, remediation, policy and immutable planning
Implement environment facts, requirement assessment, allowed remediation derivation, policy
composition, minimal immutable Mutation/Install plans, risk escalation and review-first semantics.

### CP-08 — Runtime inputs and credential lifecycle
Separate ConfigInput from SecretInput, value sources from process bindings and CredentialReference
from secret values. Implement inspect/store/verify/replace/delete with dependency awareness and
macOS Keychain first. Never expose old values. Registry help/examples are metadata only.

### CP-09 — Isolated Python runtime/dependency effects
Implement per-artifact isolated Python environments, RequirementsFile/PyProject descriptors and
pip/uv installer capability/remediation separation. Launchers never install dependencies at runtime.
Preserve system Python.

### CP-10 — Production MCP stdio vertical slice
Deliver source-tree Python MCP over stdio with declarative launch/input contract, generated
launcher/runtime projection, one real harness adapter, Keychain secret binding, config binding,
verification and receipt. AART must not be required on PATH after installation unless explicitly
declared.

### CP-11 — Desired-state reconciliation engine
Model DesiredState, CurrentState, Drift/Diff and minimal independently-repairable MutationPlan.
Add effect capability metadata (inspectable/idempotent/reversible/independently repairable).
Re-inspect after mutation. Unsupported repair semantics remain explicit.

### CP-12 — Installed lifecycle on reconciliation
Route install, update, configure, repair, credential rotation, harness reconfiguration, downgrade
and uninstall through reconciliation. Implement health propagation, collection ownership, update
rollback where genuinely supported, interrupted/partial outcomes, scope mutation locks and drift
detection.

### CP-13 — Consumer TUI 01–29
Refactor/reuse the existing persistent TUI rather than replacing it. Implement accepted Dashboard,
Marketplace, Artifact/Collection details, bulk install, Required Inputs, conditional remediation,
Ready/Progress/Success, Installed, Updates, Uninstall, Repair, Registries, Credentials, Activity,
Settings and Doctor screens. Fast is default; Verbose is the same semantics with more detail.

### CP-14 — Maintainer TUI 30–53
Implement opt-in Maintainer Mode: sources, discovery, candidates, semantic diff,
validation/policy review, promotion, bulk promotion, registry diff/validation/commit, provenance,
conflicts, collection candidates and filters. Source sync never promotes.

### CP-15 — Accepted lifecycle/edge-case hardening 54–100
Implement and test source disappearance, deprecated/revoked states, dependency revocation
propagation, exact collection drift, invalid registry HEAD, version immutability, compromised
artifact flow, exceptional purge boundaries, offline state distinctions, verification failure,
partial/interrupted execution, concurrency, manual drift, superseding, downgrade, changed
input/auth contracts, policy drift, multi-registry collision, dev installs, candidate rejection and
publication/audit semantics.

### CP-16 — Global doctor and supportability
Implement `aart doctor` as environment-wide inspection/reconciliation, readable Activity/Receipt
diagnostics, safe repair entry points and machine-complete JSON. Do not implement reinstall-all as
repair.

### CP-17 — Git-backed live acceptance
Build realistic temporary Git source repos with manifests, synthetic registry, consumer/harness
project and tests covering:
source change → candidate → validation → promotion/vendoring → registry snapshot → consumer sync →
marketplace → collection/bulk install → MCP start → receipt → update → drift/repair →
rollback/uninstall.
Acceptance tests assert public contracts, not module layout.

### CP-18 — Migration completion and release gate
Remove only legacy code whose authority has been replaced and verified. Reconcile docs with Product
Specification, complete traceability for all mandatory invariants, run full quality + packaging +
security + mutation/deep acceptance gates, confirm zero runtime deps, and prepare
Release Please/release workflow according to the accepted release model.

### CP-19 — Manual TUI acceptance hardening
Convert findings from the real post-refactor Registry → Marketplace → lifecycle walkthrough into
bounded work without reopening the verified refactor slices. Complete the contextual keyboard
footer, result-screen exits, fresh-form lifecycle, review layout and stable tables; preserve the
Registry baseline safety check while making each mismatch and recovery actionable; then resume the
walkthrough from its recorded checkpoint and run the full batch gates before handback.

## Dependency order

```text
CP-00 → CP-01 → CP-02 → CP-03 → CP-04 → CP-05 → CP-06 → CP-07
                                                ↓
CP-08 → CP-09 → CP-10 → CP-11 → CP-12 → CP-13 → CP-14 → CP-15
                                                          ↓
                                           CP-16 → CP-17 → CP-18 → CP-19
```

Parallelism is allowed only when slices do not share unsettled domain contracts and neither depends
on the other's acceptance evidence.

## Slice completion gate

A critical-path slice is not complete until:

- its Product Specification invariants are identified;
- characterization/red tests exist where behavior changes;
- unit/property tests cover pure domain behavior;
- port/adapter integration tests cover IO boundaries;
- the smallest relevant E2E/live acceptance is green;
- no secrets or enterprise-private values are committed;
- quality gates for touched code are green;
- migration status, next work, decisions and backlog are updated;
- remaining legacy authority/removal criteria are explicit.
