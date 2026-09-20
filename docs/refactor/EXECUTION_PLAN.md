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

CP-18 met the product contract in force at its completion. CP-19 through CP-26 add accepted
requirements and corrections. Historical VERIFIED records remain evidence of their original
behavior; they do not prove the revised contract. Product Specification §169 and the current
`INVARIANT_TRACEABILITY.md` identify outstanding CP-26 implementation/proof obligations. Read
`CONTRACT_ALIGNMENT.md` for superseded decisions and the current-versus-target documentation rule.

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
Inventory current `aart_cli` modules, CLI/TUI behavior, protocols, tests, quality gates and
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
Implement `aart-cli doctor` as environment-wide inspection/reconciliation, readable Activity/Receipt
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
walkthrough from its recorded checkpoint. Both TUI maintenance and generated Registry CI must
operate on the canonical versioned representation produced by promotion. A refused run must
terminate as a result rather than retain a confirmation for a discarded plan. Run the full batch
gates before handback. The first real Consumer also exposed the missing Git-publication transition;
after that critical repair, finish workflow progress/back context, shared visual hierarchy,
promotion-mode explanation and honest Registry/Source rows before handback.

### CP-20–CP-22 — Completed manual acceptance increments

CP-20 added consumer configuration and isolated manual acceptance; CP-21 refined the shared screen
skeleton and lifecycle behavior; CP-22 established one frame structure and incorporated the third
manual run. CP-22 was closed by the product owner on 2026-09-14 (D-248). Historical gate results
remain in their slice records; closure does not assert a new full-suite run.

### CP-23 — Actionable TUI workflows after the fourth manual run

Implement the 2026-09-14 screen reports as fourteen bounded product/audit tasks plus final acceptance:
Source Sync guidance, Candidate table/detail, Verbose file diffs, Validation progression, the
historical D-255 manual-publication handoff, functional Success actions, Marketplace descriptions, clear
Remediation effects, durable post-promotion Candidate state, explicit harness selection, Artifact
Details controls, navigable credential actions, explicit credential guidance from Source through
approved metadata to secure entry, and a complete screen/state audit of Frame and `v` semantics.
Cursor descriptions are Verbose-only throughout; essential input guidance stays visible in Fast.
Product Specification §167 records the owner's
revisions. The ordered tasks and completion criteria are in
`docs/refactor/slices/CP-23-actionable-tui-workflows.md`; start at task 01.

CP-23's manual-publication choice is historical: Product Specification §164.7, D-312 and CP-26.18
supersede D-255 by restoring explicit Push on Registry Maintainer's local-workspace row. Promotion
success screens still stop at the local commit.

### CP-24 — Field reports from the first released version

Repair what `v0.1.1` does to somebody using it, from the owner's GitHub issues #7 and #8. First,
and the reason the slice exists: a Source whose stored Candidate history no longer binds its pinned
revision makes the **whole** local state unloadable, and the only way back is deleting files by
hand. That is one defect from three ends — the projection that refuses, the Sync that can leave the
state, and the missing repair. Then the installation review: an installer named twice for one
artifact, effect counts a reader cannot reconcile with their own request, and an installation that
reports nothing while it runs. The slice ends by cutting the release that carries the fixes. The
ordered tasks and completion criteria are in
`docs/refactor/slices/CP-24-post-release-field-reports.md`; start at task 01.

### CP-26 — Canonical Registry removal, authoring tools, local consumption and MCP verification

Remove the older unversioned Registry representation without a compatibility window, retain
`registry publish` as the canonical approved-Registry aggregate, and add parser-derived author
manifest generation/checking plus the focused README paths. Generated Registry content carries no
maintainer-specific default, and Registry Maintainer exposes publication readiness and safe review-
branch push from the exact canonical workspace. The canonical maintenance commands themselves
remain: only their legacy-representation branches are removed. `publish` ends at the reviewed local
commit; Push is a distinct explicit Registry Maintainer action.

The owner added CP-26.18a on 2026-09-19 (D-332): use `aart-cli` throughout active product
interfaces and tool-owned names, resolve one portable `~/.aart-cli` / `AART_CLI_HOME`, and define
harness-owned installation paths. It precedes CP-26.19, which makes runtime trees, configuration,
credential items, setup state, receipts and lifecycle ownership specific to a complete installation
(Registry alias + artifact + scope/root + harness/profile). Every new target collects its own
inputs; four harnesses mean four sets, with no sharing or copy option (D-333, B-144/B-150).
Task 19 also owns versionless artifact/Registry-alias/scope names under each harness's discovery
and naming rules, installed skill-name projection, and Keychain addresses derived from complete
owner/input identity with readable labels and opaque roots (D-349, §169.7, INV-253; issues #26/#28).
Updates preserve these addresses; collisions are refused before mutation. Enterprise index
release customization remains deferred outside this task (B-157).
CP-26.20 then adds local repository + selected branch acquisition through the same canonical
Registry pipeline (B-143/D-350), proves the same isolation for local and remote aliases and uses
ordinary installation before smoke testing. No separate Candidate Test Install flow is required.

D-334 accepts breaking changes throughout CP-26: no backward-compatibility aliases, fallback
formats, migrations or transition periods are required. Implementation checks are focused and
proportionate, especially for mechanical namespace changes; accepted isolation and secret boundaries
remain tested. Remote/local aliases are separate installation entities and filesystem namespaces
even for identical package bytes.

The owner added CP-26.20a (D-348, Product Specification §170): CLI-only smoke verification of all
or selected already installed MCPs in the local environment, including ordinary installations from
local Registry repositories/branches and remote Registries. Preserve configuration,
protocol, external-service, model-provider and actual harness-execution stages. Only a predeclared
read-only tool with fixed arguments may execute, both directly and through the harness. D-351
requires only `tool` and `read_only: true` in `smoke_test`; arguments default to empty, the
tool-call timeout to 15 seconds, and result expectations are optional. Generic MCP success is
distinct from external-service proof; no dedicated health tool or custom response is required.
D-365 requires direct-only Tabnine acceptance while its adapter lacks the allowed-tools boundary,
and full-route acceptance for eligible OpenCode and Claude adapters. No new TUI, scheduled CI, automatic setup mutation or production-wide scan
belongs to this increment. Document the recommended install → smoke test → publish workflow for
new MCPs and bulk checking of a user's installed MCPs. B-073's scheduled live CI work stays separate.

The ordered plan has 23 tasks; existing ids are preserved, with 18a between 18 and 19 and 20a
between 20 and 21. Implementation tasks, including 18a and 20a, use focused tests and measured
damage-radius gates. Execution remains 19 → 20 → 20a → 21 after completed step 18a.
CP-26.21 remains the sole broad quality/integration/E2E closeout after all implementation tasks.
The full order and acceptance criteria are in
`docs/refactor/slices/cp-26-authoring-and-legacy-removal.md`; `NEXT.md` names the current task.

## Dependency order

```text
CP-00 → CP-01 → CP-02 → CP-03 → CP-04 → CP-05 → CP-06 → CP-07
                                                ↓
CP-08 → CP-09 → CP-10 → CP-11 → CP-12 → CP-13 → CP-14 → CP-15
                                                          ↓
                                           CP-16 → CP-17 → CP-18 → CP-19
                                                                     ↓
                                           CP-23 ← CP-22 ← CP-21 ← CP-20
     ↓
   CP-24 → CP-26
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

### Current owner revision — capability-dependent smoke coverage (2026-09-20, D-365)

This supersedes earlier requirements for mandatory Tabnine harness execution, blanket prohibition
of model assessment and unconditional suppression of response display. Implement revised Product
Specification §170 / INV-250–252. Unsupported allowed-tools capability means direct MCP testing with
that installation's credentials and an explicit excluded harness stage; it does not block completion.
Eligible harnesses have a 120-second deadline, exact operation/argument enforcement and an English
prompt requesting `status` (`ok`, `error`, `uncertain`), `summary`, and `possible_error`. Human-readable
fields are English. Assessments remain separate from deterministic checks and service evidence.
Add default-off `--show-response` for bounded current-output inspection, without application
persistence. Keep zero runtime dependencies; use Python's standard library.

Implementation is pending for this revision. Required evidence includes direct-only Tabnine coverage,
capability-based aggregation, deadline/process cleanup, malformed assessment and uncertain/error
cases, argument enforcement, bounded opt-in display and default non-disclosure. Existing tests do not
establish these new claims. CP-26.20a remains in flight; do not mark it done.
