# AART Refactor — Next Work

## Current objective

Finish **CP-00 Canonical planning baseline**, then start
**CP-01 Repository characterization and invariant map**.

## Immediate next actions

1. Commit this bootstrap package to `M1F1/aart-cli`.
2. Verify `docs/product-specification/PRODUCT_SPECIFICATION.md` is readable and authoritative.
3. Verify root `AGENTS.md` establishes target, precedence, autonomy and backlog rules.
4. Create `docs/refactor/slices/CP-01-repository-characterization.md` from the slice template.
5. Inventory current `agent_artifacts` package and tests without moving modules.
6. Build invariant traceability:
   Product Specification invariant → current behavior/module → target owner → tests → missing evidence.
7. Add characterization tests for high-risk behavior before structural refactors.
8. Update MIGRATION_STATUS, DECISIONS, BACKLOG and this file before CP-02.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker-first MCP design;
- no changes to old AART repositories;
- no optional artifact families;
- no backlog work unless it becomes a proven critical-path blocker.
