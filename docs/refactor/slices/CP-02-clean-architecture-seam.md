# CP-02 — Clean architecture migration seam
Status: VERIFIED

## Goal

Make the existing domain/application/port boundary an executable constraint so canonical domain
work can be added incrementally without importing legacy infrastructure or interface authority.

## Product Specification sections/invariants

INV-002 through INV-009, INV-061 through INV-069, INV-106 through INV-111.

## Legacy/current paths

- Canonical seed kernel: `agent_artifacts/domain/`.
- Existing application orchestration: `agent_artifacts/application/` plus subsystem application
  modules.
- Existing concrete effects: `agent_artifacts/io/` and subsystem `io.py` modules.
- Legacy orchestration/interfaces: `cli.py`, `tui.py`, `setup.py`, `setup_runtime.py`.

## Target paths/owners

- Domain: frozen values, validation and pure transformations only.
- Application: use-case orchestration over explicit ports and typed results.
- Adapters/interpreters: filesystem, Git, subprocess, credentials, network, clocks and terminal IO.
- Interfaces: CLI/JSON/TUI projection and user intent only.

## Dependencies

CP-00 and CP-01 are verified.

## Non-goals

- No broad package move.
- No five-algebra implementation (CP-03).
- No legacy deletion before a vertical flow is migrated and verified.

## Characterization / RED evidence

Existing `domain_kernel_test.py` proves the seed domain is IO-free but permits some dependency
directions that are too broad for new canonical modules. The new architecture test makes the
intended seam explicit and scans all domain dataclasses rather than a fixed module allowlist.

## Implementation steps

1. Enforce domain-only inward dependencies.
2. Enforce application independence from concrete IO and interfaces.
3. Enforce frozen canonical domain dataclasses dynamically.
4. Verify existing commands remain covered by the focused characterization suite.

## Property tests

Not applicable to this structural seam; CP-03 adds Hypothesis for algebraic invariants.

## Integration tests

Existing compiler, marketplace, lifecycle and TUI focused characterization remains green.

## E2E/live acceptance

No new live flow in this structural slice; the existing Tabnine MCP E2E remains characterization.

## Quality gates

Focused architecture/domain tests plus validate, docs-check and secret-shape-check.

## Done

- Existing seams inventoried.
- Conservative seam decision recorded as D-005.
- Domain inward-only imports enforced dynamically.
- Application independence from concrete IO/CLI/TUI enforced.
- All canonical domain dataclasses checked dynamically for frozen semantics.
- Pre-existing security JSON narrowing errors fixed with fail-closed string guards and malformed
  evidence tests so the canonical type gate is green.

## Remaining

None for this seam. Concrete legacy flows remain intentionally in place for strangler migration.

## Known compromises

Subsystem-local pure models remain outside `agent_artifacts/domain`. They are migration inputs, not
canonical new-domain dependencies.

## Backlog discoveries

None.

## Blockers

None.

## Legacy removal criteria

No legacy path is removed in CP-02. Later slices must migrate public flows and prove replacement.

## Handoff

- Current working state: CP-02 verified; dependency and frozen-value rules are executable.
- Exact next action: start CP-03 with RED tests for the five canonical algebras.
- Do not undo: existing characterized public commands or zero-runtime-dependency packaging.
- Tests last run/results: 15 architecture/domain tests and 22 security/architecture tests pass;
  pinned format, lint, typecheck, validate, docs and secret-shape gates pass.
- Failure evidence: Poetry-backed packaging remains unavailable locally and explicitly unverified.
